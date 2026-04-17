"""
LightRAG Manager — 사용자별 격리된 지식 그래프 관리

GCS에 사용자별 prefix(`lightrag_graph/{uid}/`)로 그래프를 저장·복원하며,
프로필 데이터를 색인하고 주제 기반으로 검색한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import google.generativeai as genai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from firebase_admin import storage

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger("rag_manager")
logger.setLevel(logging.INFO)

BASE_WORKING_DIR = "/tmp/lightrag_data"
GCS_PREFIX_ROOT = "lightrag_graph"

# bio entry 타입 → 한글 라벨
_ENTRY_TYPE_LABELS: Dict[str, str] = {
    "self_introduction": "자기소개 및 출마선언문",
    "policy": "정책/공약",
    "legislation": "법안/조례",
    "experience": "경험/활동",
    "achievement": "성과/실적",
    "vision": "비전/목표",
    "reference": "참고자료",
}


# ---------------------------------------------------------------------------
# Gemini wrappers (LightRAG 콜백)
# ---------------------------------------------------------------------------

@retry(
    retry=(
        retry_if_exception_type(google_exceptions.ResourceExhausted)
        | retry_if_exception_type(google_exceptions.TooManyRequests)
    ),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(5),
)
async def gemini_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    **kwargs: Any,
) -> str:
    """LightRAG LLM 콜백 — Gemini 텍스트 생성."""
    if history_messages is None:
        history_messages = []

    hashing_kv = kwargs.get("hashing_kv")
    model_name = "gemini-2.5-flash"
    if hashing_kv and hasattr(hashing_kv, "global_config"):
        model_name = hashing_kv.global_config.get("llm_model_name", model_name)
    if "gemini" not in model_name:
        model_name = "gemini-2.5-flash"

    try:
        model = genai.GenerativeModel(model_name)

        full_prompt = ""
        if system_prompt:
            full_prompt += f"System: {system_prompt}\n\n"
        for msg in history_messages:
            full_prompt += f"{msg.get('role', 'User')}: {msg.get('content', '')}\n"
        full_prompt += f"User: {prompt}"

        response = await asyncio.wait_for(
            model.generate_content_async(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=kwargs.get("temperature", 0.7),
                    max_output_tokens=kwargs.get("max_tokens", 8192),
                ),
            ),
            timeout=30,
        )
        return response.text
    except asyncio.TimeoutError:
        logger.warning("Gemini LLM timeout (30s): model=%s", model_name)
        return ""
    except Exception as e:
        logger.error("Gemini LLM Error: %s", e)
        return ""


@retry(
    retry=(
        retry_if_exception_type(google_exceptions.ResourceExhausted)
        | retry_if_exception_type(google_exceptions.TooManyRequests)
    ),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(5),
)
async def gemini_embed(texts: list[str]) -> np.ndarray:
    """LightRAG 임베딩 콜백 — Gemini text-embedding-004."""
    model = "models/text-embedding-004"
    try:
        result = await genai.embed_content_async(
            model=model,
            content=texts,
            task_type="retrieval_document",
        )
        return np.array(result["embedding"])
    except Exception as e:
        logger.error("Gemini Embedding Error: %s", e)
        return np.zeros((len(texts), 768))


# ---------------------------------------------------------------------------
# GCS 동기화 (uid별 격리)
# ---------------------------------------------------------------------------

def _user_working_dir(uid: str) -> str:
    return os.path.join(BASE_WORKING_DIR, uid)


def _user_gcs_prefix(uid: str) -> str:
    return f"{GCS_PREFIX_ROOT}/{uid}"


@retry(
    retry=retry_if_exception_type((
        google_exceptions.NotFound,
        google_exceptions.ServiceUnavailable,
        google_exceptions.InternalServerError,
    )),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    stop=stop_after_attempt(3),
    before_sleep=lambda rs: logger.warning(
        "GCS download retry #%d after %s", rs.attempt_number, rs.outcome.exception()
    ),
)
def download_graph_from_gcs(bucket_name: str, uid: str) -> int:
    """사용자 그래프 파일을 GCS → /tmp 로 다운로드. 다운로드 파일 수 반환."""
    working_dir = _user_working_dir(uid)
    gcs_prefix = _user_gcs_prefix(uid)
    os.makedirs(working_dir, exist_ok=True)

    logger.info("Downloading graph: bucket=%s prefix=%s", bucket_name, gcs_prefix)
    bucket = storage.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=gcs_prefix))

    count = 0
    for blob in blobs:
        filename = os.path.basename(blob.name)
        if not filename:
            continue
        blob.download_to_filename(os.path.join(working_dir, filename))
        count += 1

    logger.info("Downloaded %d files from GCS %s/%s", count, bucket_name, gcs_prefix)
    return count


@retry(
    retry=retry_if_exception_type((
        google_exceptions.NotFound,
        google_exceptions.ServiceUnavailable,
        google_exceptions.InternalServerError,
    )),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    stop=stop_after_attempt(3),
    before_sleep=lambda rs: logger.warning(
        "GCS upload retry #%d after %s", rs.attempt_number, rs.outcome.exception()
    ),
)
def upload_graph_to_gcs(bucket_name: str, uid: str) -> int:
    """사용자 그래프 파일을 /tmp → GCS 로 업로드. 업로드 파일 수 반환."""
    working_dir = _user_working_dir(uid)
    gcs_prefix = _user_gcs_prefix(uid)

    if not os.path.exists(working_dir):
        logger.warning("Working dir %s does not exist, nothing to upload.", working_dir)
        return 0

    logger.info("Uploading graph: bucket=%s prefix=%s", bucket_name, gcs_prefix)
    bucket = storage.bucket(bucket_name)

    count = 0
    for f in os.listdir(working_dir):
        local_path = os.path.join(working_dir, f)
        if os.path.isfile(local_path):
            blob = bucket.blob(f"{gcs_prefix}/{f}")
            blob.upload_from_filename(local_path)
            count += 1

    logger.info("Uploaded %d files to GCS %s/%s", count, bucket_name, gcs_prefix)
    return count


def graph_exists_in_gcs(bucket_name: str, uid: str) -> bool:
    """GCS에 해당 사용자의 그래프 데이터가 존재하는지 확인."""
    try:
        bucket = storage.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=_user_gcs_prefix(uid), max_results=1))
        return len(blobs) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# bioEntries → 색인용 텍스트 변환
# ---------------------------------------------------------------------------

def _entries_to_document(entries: List[Dict[str, Any]]) -> str:
    """bioEntries 배열을 LightRAG ainsert()에 넣을 단일 문서 텍스트로 변환."""
    blocks: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip()
        title = str(entry.get("title") or "").strip()
        content = str(entry.get("content") or "").strip()
        if not content:
            continue

        label = _ENTRY_TYPE_LABELS.get(entry_type, entry_type)
        header = f"[{label}]"
        if title:
            header += f" {title}"
        blocks.append(f"{header}\n{content}")

    return "\n\n".join(blocks)


def _facebook_entries_to_document(entries: List[Dict[str, Any]]) -> str:
    """페이스북 다이어리 엔트리 배열을 LightRAG ainsert()용 텍스트로 변환.

    각 엔트리 헤더에 날짜·카테고리를 포함하면 LightRAG가 엔티티 관계를 더 잘 추출한다.
    """
    parts: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        created_at = entry.get("createdAt")
        date_str = str(created_at)[:10] if created_at else ""
        category = str(entry.get("category") or "").strip()
        header = f"[Facebook 입장문] {date_str} ({category})".strip()
        parts.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Manager Class
# ---------------------------------------------------------------------------

class LightRAGManager:
    """사용자별 격리된 LightRAG 인스턴스 관리."""

    def __init__(
        self,
        bucket_name: str,
        uid: str,
        model_name: str = "gemini-2.5-flash",
    ):
        self.bucket_name = bucket_name
        self.uid = uid
        self.model_name = model_name
        self.rag: LightRAG | None = None

    async def initialize(self, mode: str = "read") -> LightRAG:
        """LightRAG 인스턴스 초기화.

        mode='read': 기존 그래프 다운로드 후 읽기 전용 쿼리.
        mode='write': 기존 그래프 다운로드 후 쓰기(색인) 가능.
        """
        working_dir = _user_working_dir(self.uid)

        # 이전 데이터 정리 (컨테이너 재사용 시 다른 사용자 데이터 오염 방지)
        if os.path.exists(working_dir):
            shutil.rmtree(working_dir, ignore_errors=True)
        os.makedirs(working_dir, exist_ok=True)

        try:
            download_graph_from_gcs(self.bucket_name, self.uid)
        except Exception as e:
            logger.warning("Failed to download graph for %s (might be first run): %s", self.uid, e)

        self.rag = LightRAG(
            working_dir=working_dir,
            llm_model_func=gemini_complete,
            llm_model_name=self.model_name,
            embedding_func=EmbeddingFunc(
                embedding_dim=768,
                max_token_size=8192,
                func=gemini_embed,
            ),
        )

        await self.rag.initialize_storages()
        logger.info("LightRAG initialized for uid=%s in %s (Model: %s)", self.uid, working_dir, self.model_name)
        return self.rag

    async def index_entries(self, entries: List[Dict[str, Any]]) -> str:
        """bioEntries를 지식 그래프에 색인하고 GCS에 업로드한다.

        Returns:
            색인된 문서 텍스트 (디버깅용).
        """
        if self.rag is None:
            await self.initialize(mode="write")

        document = _entries_to_document(entries)
        if not document.strip():
            logger.warning("No indexable content for uid=%s", self.uid)
            return ""

        logger.info("Indexing %d entries (%d chars) for uid=%s", len(entries), len(document), self.uid)
        await self.rag.ainsert(document)

        upload_graph_to_gcs(self.bucket_name, self.uid)
        logger.info("Index + upload complete for uid=%s", self.uid)
        return document

    async def index_text(self, text: str) -> None:
        """임의 텍스트(페이스북 다이어리 등)를 지식 그래프에 색인하고 GCS에 업로드한다."""
        if self.rag is None:
            await self.initialize(mode="write")
        if not text.strip():
            logger.warning("index_text: 빈 텍스트 — uid=%s", self.uid)
            return
        logger.info("index_text: %d자 색인 시작 — uid=%s", len(text), self.uid)
        await self.rag.ainsert(text)
        upload_graph_to_gcs(self.bucket_name, self.uid)
        logger.info("index_text: 색인 + GCS 업로드 완료 — uid=%s", self.uid)

    def persist(self) -> None:
        """현재 그래프를 GCS에 업로드."""
        upload_graph_to_gcs(self.bucket_name, self.uid)


# ---------------------------------------------------------------------------
# 키워드 별칭(alias) 추출
# ---------------------------------------------------------------------------

_ALIAS_EXTRACT_PROMPT_TEMPLATE = (
    '아래 텍스트에서 **같은 대상**을 가리키는 서로 다른 명칭 쌍을 모두 찾아라.\n'
    '축약어, 영문 약어, 별칭, 괄호 병기 등 모든 유형을 포함한다.\n'
    '텍스트에 실제로 등장하는 표현만 추출하고, 추측하지 마라.\n\n'
    '출력 형식 (JSON 배열만, 다른 텍스트 없이):\n'
    '[{{"canonical": "정식 명칭", "aliases": ["축약어1", "별칭2"]}}]\n\n'
    '쌍이 없으면 빈 배열 [] 을 반환하라.\n\n---\n{text}'
)


async def extract_keyword_aliases(
    corpus_text: str,
    user_keywords: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """사용자 텍스트 코퍼스에서 동일 대상의 다른 명칭 쌍을 LLM으로 추출.

    Returns:
        {"정식명칭": ["축약어1", "별칭2"], ...}
    """
    if not corpus_text or not corpus_text.strip():
        return {}

    trimmed = corpus_text[:8000]
    prompt = _ALIAS_EXTRACT_PROMPT_TEMPLATE.format(text=trimmed)

    try:
        raw = await gemini_complete(prompt, temperature=0.1, max_tokens=2048)
    except Exception as exc:
        logger.warning("[AliasExtract] LLM 호출 실패: %s", exc)
        return {}

    match = re.search(r"\[.*\]", raw or "", re.DOTALL)
    if not match:
        return {}

    try:
        items = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        logger.warning("[AliasExtract] JSON 파싱 실패: %s", raw[:200])
        return {}

    result: Dict[str, List[str]] = {}
    kw_set = set(str(k).strip() for k in (user_keywords or []) if str(k).strip())

    for item in items:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical") or "").strip()
        aliases = item.get("aliases") or []
        if not canonical or not isinstance(aliases, list):
            continue
        clean_aliases = [str(a).strip() for a in aliases if str(a).strip() and str(a).strip() != canonical]
        if not clean_aliases:
            continue
        if kw_set and canonical not in kw_set:
            if not any(a in kw_set for a in clean_aliases):
                continue
            for a in clean_aliases:
                if a in kw_set:
                    result[a] = [canonical] + [x for x in clean_aliases if x != a]
                    break
            continue
        result[canonical] = clean_aliases

    return result
