"""사용자 stanceText 에서 상투어 대체어 후보를 추출하는 모듈.

핵심 알고리즘:
  1. GCS 에서 centroid 모델(TF-IDF vectorizer + SVD + centroids) 로드
  2. 미처리 posts 의 sources.stanceText 를 문장 분할
  3. 각 문장을 TF-IDF → SVD 변환 후 centroid 와 cosine similarity 비교
  4. similarity ≥ threshold AND 상투어 미포함 → 후보 매칭
  5. 형태소 슬롯 매칭으로 대체 표현 추출
  6. Firestore cliche_alt_candidates 에 저장
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── 설정 ──
SIMILARITY_THRESHOLD = 0.25
MIN_STANCE_LENGTH = 50
MAX_CANDIDATES_PER_BATCH = 500

_HTML_TAG_RE = re.compile(r"<[^>]*>")

# 형태소 슬롯 매칭용 POS 태그 그룹
_MODIFIER_TAGS = frozenset({"MM", "VA", "VV"})
_NOUN_TAGS = frozenset({"NNG", "NNP"})
_CONTENT_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> List[str]:
    from agents.common.korean_morph import split_sentences

    sents = split_sentences(text)
    if sents is not None:
        return sents
    return [s.strip() for s in re.split(r"[.!?]\s+", text) if s.strip()]


def _tokenize_to_content_words(text: str) -> str:
    from agents.common.korean_morph import tokenize

    tokens = tokenize(text)
    if tokens is None:
        return text
    content_tags = frozenset({"NNG", "NNP", "VV", "VA"})
    return " ".join(tok.form for tok in tokens if tok.tag in content_tags)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _classify_cliche_pos(cliche: str) -> Optional[str]:
    """상투어의 주요 품사 유형을 판별.

    Returns:
        "modifier" (관형사/형용사), "noun" (명사), "verb" (동사),
        "phrase" (다어절 구), None (판별 불가)
    """
    from agents.common.korean_morph import tokenize

    tokens = tokenize(cliche)
    if tokens is None or not tokens:
        return "phrase" if " " in cliche or len(cliche) > 4 else None

    tags = [t.tag for t in tokens]
    if any(t in ("MM",) for t in tags):
        return "modifier"
    if any(t in ("VA",) for t in tags) and not any(t in ("NNG", "NNP") for t in tags):
        return "modifier"
    if all(t in _NOUN_TAGS | {"XSN", "XSA"} for t in tags):
        return "noun"
    if any(t in ("VV",) for t in tags):
        return "verb"
    if len(tokens) >= 3:
        return "phrase"
    return "noun"


def _extract_alternative_expression(
    sentence: str,
    cliche: str,
    cliche_pos: Optional[str],
    context_nouns: List[str],
) -> Optional[str]:
    """매칭된 문장에서 상투어 대체 표현을 추출.

    전략:
      1. 상투어가 관형사/형용사이면 → 문장에서 context_nouns 를 수식하는 관형사/형용사 추출
      2. 상투어가 명사이면 → context_nouns 와 같은 위치의 다른 명사 추출
      3. 상투어가 구(phrase)이면 → 문맥 명사를 제외한 나머지 내용어 조합 추출
      4. 추출 실패 시 None

    Returns:
        추출된 대체 표현 문자열, 또는 None
    """
    from agents.common.korean_morph import tokenize

    tokens = tokenize(sentence)
    if tokens is None or not tokens:
        return None

    context_set = set(context_nouns)

    if cliche_pos == "modifier":
        # context 명사를 수식하는 MM/VA+ETM 을 찾는다
        for i, tok in enumerate(tokens):
            if tok.tag in _NOUN_TAGS and tok.form in context_set:
                # 이 명사 앞에 있는 수식어를 찾는다
                candidates = []
                for j in range(max(0, i - 3), i):
                    prev = tokens[j]
                    if prev.tag == "MM":
                        candidates.append(prev.form)
                    elif prev.tag in ("VA", "VV") and j + 1 < len(tokens):
                        nxt = tokens[j + 1]
                        if nxt.tag == "ETM":
                            candidates.append(f"{prev.form}{nxt.form}")
                if candidates:
                    return candidates[-1]  # 가장 가까운 수식어

    elif cliche_pos == "noun":
        # 문맥 명사 근처에 있는 다른 명사 추출
        for i, tok in enumerate(tokens):
            if tok.tag in _NOUN_TAGS and tok.form in context_set:
                # 인접 명사 중 context 에 없는 것
                for j in range(max(0, i - 2), min(len(tokens), i + 3)):
                    if j == i:
                        continue
                    near = tokens[j]
                    if near.tag in _NOUN_TAGS and near.form not in context_set:
                        return near.form

    elif cliche_pos == "verb":
        # 문장의 주 동사 추출 (context 명사를 목적어로 취하는)
        for i, tok in enumerate(tokens):
            if tok.tag == "VV" and tok.form not in context_set:
                return tok.form

    # phrase 또는 fallback: context 명사를 제외한 내용어 조합
    non_context = [
        tok.form for tok in tokens
        if tok.tag in _CONTENT_TAGS and tok.form not in context_set
    ]
    if non_context and len(non_context) <= 4:
        return " ".join(non_context)

    return None


def _get_context_nouns_for_cliche(
    cliche: str,
    sample_sentences: List[str],
) -> List[str]:
    """상투어의 centroid 샘플 문장들에서 공통 문맥 명사를 추출.

    상투어 자체의 형태소는 제외하고, 2회 이상 등장하는 명사만 선택.
    """
    from agents.common.korean_morph import tokenize

    # 상투어 자체의 형태소
    cliche_tokens = tokenize(cliche)
    cliche_forms = set()
    if cliche_tokens:
        cliche_forms = {t.form for t in cliche_tokens}

    noun_counts: Dict[str, int] = {}
    for sent in sample_sentences[:20]:
        tokens = tokenize(sent)
        if not tokens:
            continue
        seen_in_sent: set = set()
        for tok in tokens:
            if tok.tag in _NOUN_TAGS and tok.form not in cliche_forms and tok.form not in seen_in_sent:
                noun_counts[tok.form] = noun_counts.get(tok.form, 0) + 1
                seen_in_sent.add(tok.form)

    # 2회 이상 등장 명사, 빈도순
    result = [
        noun for noun, count in sorted(noun_counts.items(), key=lambda x: -x[1])
        if count >= 2
    ]
    return result[:10]


def extract_candidates_from_posts(
    db: Any,
    bucket_name: str,
) -> Dict[str, Any]:
    """미처리 stanceText 에서 대체어 후보를 추출.

    Returns:
        {"processed_posts": int, "candidates_found": int}
    """
    from .centroid_builder import load_model_from_gcs

    model = load_model_from_gcs(bucket_name)
    if model is None:
        logger.warning("[candidate_extractor] No centroid model found, skipping")
        return {"processed_posts": 0, "candidates_found": 0}

    centroids = model["centroids"]
    vectorizer = model["vectorizer"]
    svd = model["svd"]

    if not centroids or vectorizer is None or svd is None:
        logger.warning("[candidate_extractor] Invalid model, skipping")
        return {"processed_posts": 0, "candidates_found": 0}

    # centroid 별 샘플 문장 로드 (문맥 명사 추출용)
    centroid_docs = db.collection("cliche_centroids").stream()
    cliche_samples: Dict[str, List[str]] = {}
    cliche_pos_cache: Dict[str, Optional[str]] = {}
    for doc in centroid_docs:
        d = doc.to_dict() or {}
        cliche = d.get("cliche", "")
        if cliche:
            cliche_samples[cliche] = d.get("sample_sentences", [])
            cliche_pos_cache[cliche] = _classify_cliche_pos(cliche)

    # 문맥 명사 사전 캐시
    context_nouns_cache: Dict[str, List[str]] = {}
    for cliche, samples in cliche_samples.items():
        context_nouns_cache[cliche] = _get_context_nouns_for_cliche(cliche, samples)

    # 미처리 posts 조회
    query = (
        db.collection("posts")
        .where("sources.stanceText", "!=", "")
        .select(["sources.stanceText", "clicheDictProcessed"])
    )

    processed_posts = 0
    candidates_found = 0
    candidate_batch = []

    for doc in query.stream():
        data = doc.to_dict() or {}
        if data.get("clicheDictProcessed"):
            continue

        sources = data.get("sources")
        if not isinstance(sources, dict):
            continue
        stance_text = str(sources.get("stanceText", "")).strip()
        if len(stance_text) < MIN_STANCE_LENGTH:
            continue

        sentences = _split_sentences(_strip_html(stance_text))

        for sent in sentences:
            if len(sent) < 10:
                continue

            tokenized = _tokenize_to_content_words(sent)
            try:
                tfidf_vec = vectorizer.transform([tokenized])
                reduced = svd.transform(tfidf_vec)
                sent_vec = reduced[0]
            except Exception:
                continue

            for cliche, centroid in centroids.items():
                # 상투어가 이미 문장에 포함되어 있으면 스킵
                if cliche in sent:
                    continue

                sim = _cosine_similarity(sent_vec, centroid)
                if sim < SIMILARITY_THRESHOLD:
                    continue

                # 대체 표현 추출
                alternative = _extract_alternative_expression(
                    sent,
                    cliche,
                    cliche_pos_cache.get(cliche),
                    context_nouns_cache.get(cliche, []),
                )
                if not alternative or len(alternative) < 2 or alternative == cliche:
                    continue

                candidate_batch.append({
                    "cliche": cliche,
                    "alternative": alternative,
                    "source_sentence": sent[:300],
                    "similarity_score": round(sim, 4),
                })
                candidates_found += 1

                if candidates_found >= MAX_CANDIDATES_PER_BATCH:
                    break

            if candidates_found >= MAX_CANDIDATES_PER_BATCH:
                break

        # post 를 처리 완료로 마킹
        doc.reference.update({"clicheDictProcessed": True})
        processed_posts += 1

        if candidates_found >= MAX_CANDIDATES_PER_BATCH:
            break

    # 후보들을 Firestore 에 저장
    if candidate_batch:
        _save_candidates(db, candidate_batch)

    logger.info(
        "[candidate_extractor] Processed %d posts, found %d candidates",
        processed_posts,
        candidates_found,
    )
    return {"processed_posts": processed_posts, "candidates_found": candidates_found}


def _save_candidates(db: Any, candidates: List[Dict[str, Any]]) -> None:
    """후보들을 Firestore cliche_alt_candidates 컬렉션에 배치 저장."""
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    batch = db.batch()
    batch_size = 0

    for cand in candidates:
        ref = db.collection("cliche_alt_candidates").document()
        batch.set(ref, {
            "cliche": cand["cliche"],
            "alternative": cand["alternative"],
            "source_sentence": cand["source_sentence"],
            "similarity_score": cand["similarity_score"],
            "createdAt": SERVER_TIMESTAMP,
        })
        batch_size += 1

        if batch_size >= 400:
            batch.commit()
            batch = db.batch()
            batch_size = 0

    if batch_size > 0:
        batch.commit()

    logger.info("[candidate_extractor] Saved %d candidates to Firestore", len(candidates))
