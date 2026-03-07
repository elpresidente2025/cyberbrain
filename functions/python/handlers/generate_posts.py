"""
generatePosts Python onCall handler.

Node `handlers/posts.js`의 generatePosts 엔트리 역할을 Python으로 이관한다.
핵심 생성 로직은 기존 Step Functions 파이프라인(`pipeline_start` + Cloud Tasks)을 재사용한다.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

from firebase_admin import firestore
from firebase_functions import https_fn

from agents.common.poll_citation import build_poll_citation_text
from services.posts.content_processor import cleanup_post_content, remove_grammatical_errors
from services.posts.profile_loader import (
    get_or_create_session,
    increment_session_attempts,
    load_user_profile,
)
from services.posts.output_formatter import (
    build_keyword_validation,
    count_without_space,
    finalize_output,
    normalize_ascii_double_quotes,
    normalize_book_title_notation,
)
from services.posts.poll_fact_guard import (
    build_poll_matchup_fact_table,
    enforce_poll_fact_consistency,
)
from services.posts.validation import (
    enforce_repetition_requirements,
    enforce_keyword_requirements,
    repair_date_weekday_pairs,
    run_heuristic_validation_sync,
    validate_keyword_insertion,
)

logger = logging.getLogger(__name__)

DEFAULT_TARGET_WORD_COUNT = 2000
# onCall timeout(1200s) 대비 후처리 여유를 남기기 위해 파이프라인 폴링 상한을 17분으로 확장.
MAX_POLL_TIME_SECONDS = 17 * 60
POLL_INTERVAL_SECONDS = 0.8
KST = ZoneInfo("Asia/Seoul")

CATEGORY_MIN_WORD_COUNT = {
    "local-issues": 2000,
    "policy-proposal": 2000,
    "activity-report": 2000,
    "current-affairs": 2000,
    "daily-communication": 2000,
}
ROLE_FACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"([가-힣]{2,8})\s*현\s*부산시장(?!\s*후보)"), "현 부산시장"),
    (re.compile(r"([가-힣]{2,8})\s*부산시장(?!\s*후보)"), "부산시장"),
    (re.compile(r"([가-힣]{2,8})\s*국회의원"), "국회의원"),
)
ROLE_MENTION_PATTERN = re.compile(r"([가-힣]{2,8})\s*(현\s*)?(부산시장|국회의원)")
ROLE_TOKEN_PRIORITY: tuple[tuple[str, str], ...] = (
    ("부산시장", "부산시장"),
    ("국회의원", "국회의원"),
    ("의원", "국회의원"),
    ("시장", "부산시장"),
)
H2_TAG_PATTERN = re.compile(r"<h2\b[^>]*>([\s\S]*?)</h2\s*>", re.IGNORECASE)
PARAGRAPH_TAG_PATTERN = re.compile(r"<p\b[^>]*>([\s\S]*?)</p\s*>", re.IGNORECASE)

# 프론트 로딩 오버레이가 순환 메시지를 출력하는 기준 키.
LOADING_STAGE_STRUCTURE = "구조 설계 및 초안 작성 중"
LOADING_STAGE_BODY = "본문 작성 중"
LOADING_STAGE_SEO = "검색 노출 최적화(SEO) 중"

_STEP_NAME_TO_LOADING_STAGE = {
    "structureagent": LOADING_STAGE_STRUCTURE,
    "writeragent": LOADING_STAGE_STRUCTURE,
    "keywordinjectoragent": LOADING_STAGE_BODY,
    "styleagent": LOADING_STAGE_BODY,
    "complianceagent": LOADING_STAGE_BODY,
    "seoagent": LOADING_STAGE_SEO,
    "titleagent": LOADING_STAGE_SEO,
}


@dataclass
class ApiError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ProgressTracker:
    """Firestore generation_progress 동기 업데이트."""

    def __init__(self, session_id: str):
        self.session_id = str(session_id or "").strip()
        self.ref = firestore.client().collection("generation_progress").document(self.session_id)

    def update(self, step: int, progress: int, message: str, error: bool = False) -> None:
        payload = {
            "step": int(step),
            "progress": int(progress),
            "message": str(message or ""),
            "timestamp": datetime.now(KST).isoformat(timespec="milliseconds"),
            "updatedAt": int(time.time() * 1000),
        }
        if error:
            payload["error"] = True
        try:
            self.ref.set(payload, merge=True)
        except Exception as exc:
            logger.warning("진행 상황 업데이트 실패: %s", exc)

    def step_preparing(self) -> None:
        self.update(1, 10, "준비 중...")

    def step_collecting(self) -> None:
        self.update(2, 25, "자료 수집 중...")

    def step_generating(self) -> None:
        # 프론트 STEP_MESSAGES 키와 동일한 값으로 고정해 랜덤 순환을 활성화한다.
        self.update(3, 50, LOADING_STAGE_STRUCTURE)

    def step_validating(self) -> None:
        self.update(4, 80, "품질 검증 중...")

    def step_finalizing(self) -> None:
        self.update(5, 95, "마무리 중...")

    def complete(self) -> None:
        self.update(5, 100, "완료")

    def error(self, error_message: str) -> None:
        self.update(-1, 0, f"오류: {error_message}", error=True)


class _InternalRequest:
    """
    pipeline_start.handle_start 재사용을 위한 최소 Request 어댑터.
    """

    def __init__(self, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        self._payload = payload
        self.headers = headers or {}

    def get_json(self, silent: bool = True) -> Dict[str, Any]:
        _ = silent
        return self._payload


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_step_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _to_loading_stage_message(raw_step_name: Any) -> str:
    step_name = _normalize_step_name(raw_step_name)
    normalized = re.sub(r"\s+", "", step_name).lower()
    if not normalized:
        return LOADING_STAGE_BODY

    stage_message = _STEP_NAME_TO_LOADING_STAGE.get(normalized)
    if stage_message:
        return stage_message

    # step 명칭이 일부 변경되어도 키워드 기반으로 프론트 단계와 동기화한다.
    if "seo" in normalized or "title" in normalized:
        return LOADING_STAGE_SEO
    if "structure" in normalized or "writer" in normalized:
        return LOADING_STAGE_STRUCTURE
    if "keyword" in normalized or "style" in normalized or "compliance" in normalized:
        return LOADING_STAGE_BODY
    return LOADING_STAGE_BODY


def _to_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _count_chars_no_space(text: str) -> int:
    return int(count_without_space(str(text or "")))


def _normalize_title_surface_local(title: str) -> str:
    candidate = re.sub(r"\s+", " ", str(title or "")).strip().strip('"\'')
    if not candidate:
        return ""
    try:
        from agents.common.title_generation import normalize_title_surface

        normalized = normalize_title_surface(candidate)
        return str(normalized or "").strip() or candidate
    except Exception:
        candidate = re.sub(r"\s+([,.:;!?])", r"\1", candidate)
        candidate = re.sub(r"\(\s+", "(", candidate)
        candidate = re.sub(r"\s+\)", ")", candidate)
        candidate = re.sub(r"\s{2,}", " ", candidate)
        return candidate.strip(" ,")


def _normalize_keywords(raw_keywords: Any) -> list[str]:
    if isinstance(raw_keywords, list):
        return [str(item).strip() for item in raw_keywords if str(item).strip()]
    if isinstance(raw_keywords, str):
        return [part.strip() for part in raw_keywords.split(",") if part.strip()]
    return []


def _map_api_error(code: str, message: str) -> ApiError:
    normalized = str(code or "").strip().upper()
    mapping = {
        "INVALID_INPUT": "invalid-argument",
        "INVALID_ARGUMENT": "invalid-argument",
        "UNAUTHENTICATED": "unauthenticated",
        "PERMISSION_DENIED": "permission-denied",
        "FAILED_PRECONDITION": "failed-precondition",
        "RESOURCE_EXHAUSTED": "resource-exhausted",
        "NOT_FOUND": "not-found",
        "INTERNAL_ERROR": "internal",
        "EXECUTION_ERROR": "internal",
    }
    return ApiError(mapping.get(normalized, "internal"), message or "요청 처리에 실패했습니다.")


def _today_key() -> str:
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


def _month_key() -> str:
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def _clear_active_session(uid: str) -> None:
    try:
        firestore.client().collection("users").document(uid).update(
            {"activeGenerationSession": firestore.DELETE_FIELD}
        )
    except Exception as exc:
        logger.warning("기존 세션 삭제 실패(무시): %s", exc)


def _calc_daily_limit_warning(user_profile: Dict[str, Any]) -> bool:
    daily_usage = _safe_dict(user_profile.get("dailyUsage"))
    today = _today_key()
    return _to_int(daily_usage.get(today), 0) >= 3


def _apply_usage_updates_after_success(
    uid: str,
    *,
    is_admin: bool,
    is_tester: bool,
    session: Dict[str, Any],
) -> None:
    if is_admin:
        return
    if not bool(session.get("isNewSession")):
        return

    db = firestore.client()
    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    user_data = _safe_dict(user_data)

    subscription_status = str(user_data.get("subscriptionStatus") or "trial").strip().lower()
    current_month_key = _month_key()
    update_data: Dict[str, Any] = {}

    # system/config testMode 조회
    test_mode = False
    try:
        system_doc = db.collection("system").document("config").get()
        if system_doc.exists:
            system_data = _safe_dict(system_doc.to_dict())
            test_mode = bool(system_data.get("testMode") is True)
    except Exception:
        test_mode = False

    if is_tester or subscription_status == "active":
        update_data[f"monthlyUsage.{current_month_key}.generations"] = firestore.Increment(1)
    elif test_mode:
        update_data[f"monthlyUsage.{current_month_key}.generations"] = firestore.Increment(1)
    elif subscription_status == "trial":
        current_remaining = _to_int(
            user_data.get("generationsRemaining", user_data.get("trialPostsRemaining", 0)),
            0,
        )
        if current_remaining > 0:
            update_data["generationsRemaining"] = firestore.Increment(-1)

    if update_data:
        user_ref.update(update_data)


def _extract_start_payload(
    uid: str,
    data: Dict[str, Any],
    *,
    topic: str,
    category: str,
    target_word_count: int,
    user_keywords: list[str],
    pipeline_route: str,
) -> Dict[str, Any]:
    payload = dict(data)
    payload["topic"] = topic
    payload["category"] = category
    payload["subCategory"] = str(data.get("subCategory") or "")
    payload["targetWordCount"] = int(target_word_count)
    payload["uid"] = uid
    payload["userId"] = uid
    payload["pipeline"] = pipeline_route
    payload["keywords"] = user_keywords
    payload["userKeywords"] = user_keywords
    return payload


def _call_pipeline_start(start_payload: Dict[str, Any]) -> str:
    from handlers.pipeline_start import handle_start

    internal_req = _InternalRequest(payload={"data": start_payload}, headers={"X-User-Id": str(start_payload.get("uid") or "")})
    response = handle_start(internal_req)
    status_code = int(getattr(response, "status_code", 500))
    body_text = ""
    try:
        body_text = response.get_data(as_text=True)
    except Exception:
        body_text = ""

    payload = {}
    if body_text:
        try:
            payload = json.loads(body_text)
        except Exception:
            payload = {}

    if status_code >= 400:
        message = str(payload.get("error") or "파이프라인 시작에 실패했습니다.")
        raise _map_api_error(str(payload.get("code") or "INTERNAL_ERROR"), message)

    job_id = str(payload.get("jobId") or "").strip()
    if not job_id:
        raise ApiError("internal", "파이프라인 Job ID를 받지 못했습니다.")

    return job_id


def _poll_pipeline(job_id: str, progress: ProgressTracker) -> Dict[str, Any]:
    from services.job_manager import JobManager

    job_manager = JobManager()
    started_at = time.time()
    # step_generating()에서 이미 50%가 기록되므로 폴링 중 진행률이 역행하지 않게 고정한다.
    last_message = LOADING_STAGE_STRUCTURE
    last_progress = 50

    while time.time() - started_at < MAX_POLL_TIME_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)
        job_data = job_manager.get_job(job_id)
        if not job_data:
            continue

        status = str(job_data.get("status") or "running")
        total_steps = _to_int(job_data.get("totalSteps"), 1)
        steps = _safe_dict(job_data.get("steps"))
        completed_steps = 0
        for step_val in steps.values():
            step_obj = _safe_dict(step_val)
            if step_obj.get("status") == "completed":
                completed_steps += 1

        percentage = round((completed_steps / max(total_steps, 1)) * 100, 1)
        current_step_index = str(job_data.get("currentStep", 0))
        current_step_obj = _safe_dict(steps.get(current_step_index))
        current_step_name = _normalize_step_name(current_step_obj.get("name") or "파이프라인")

        if status == "running":
            current_percentage = int(round(30 + percentage * 0.5))
            current_percentage = max(last_progress, current_percentage)
            message = _to_loading_stage_message(current_step_name)
            if message != last_message or current_percentage > last_progress:
                progress.update(3, current_percentage, message)
                last_message = message
                last_progress = current_percentage
            continue

        if status == "completed":
            result = _safe_dict(job_data.get("result"))
            if not result:
                raise ApiError("internal", "파이프라인 결과가 비어 있습니다.")
            return result

        if status == "failed":
            error_obj = _safe_dict(job_data.get("error"))
            step = str(error_obj.get("step") or current_step_name or "unknown")
            message = str(error_obj.get("message") or "파이프라인 실행 실패")
            raise ApiError("internal", f"Pipeline failed at step {step}: {message}")

    timeout_min = round(MAX_POLL_TIME_SECONDS / 60, 1)
    raise ApiError("deadline-exceeded", f"Pipeline timeout: {timeout_min}분 내에 완료되지 않았습니다.")


def _ensure_user(uid: str) -> None:
    if not uid:
        raise ApiError("unauthenticated", "로그인이 필요합니다.")


def _topic_and_category(data: Dict[str, Any]) -> tuple[str, str]:
    topic = str(data.get("prompt") or data.get("topic") or "").strip()
    if not topic:
        raise ApiError("invalid-argument", "주제를 입력해주세요.")
    category = str(data.get("category") or "daily-communication").strip() or "daily-communication"
    return topic, category


def _target_word_count(data: Dict[str, Any], category: str) -> int:
    requested = _to_int(data.get("wordCount"), DEFAULT_TARGET_WORD_COUNT)
    minimum = _to_int(CATEGORY_MIN_WORD_COUNT.get(category), DEFAULT_TARGET_WORD_COUNT)
    return max(requested, minimum)


def _calc_min_required_chars(target_word_count: int, stance_count: int = 0) -> int:
    # StructureAgent._build_length_spec와 동일 기준(완화 아님)
    target_chars = max(1600, min(int(target_word_count), 3200))
    total_sections = round(target_chars / 400)
    total_sections = max(5, min(7, total_sections))
    if stance_count > 0:
        total_sections = max(total_sections, min(7, stance_count + 2))

    per_section_recommended = max(360, min(420, round(target_chars / total_sections)))
    per_section_min = max(320, per_section_recommended - 50)
    return max(int(target_chars * 0.88), total_sections * per_section_min)


def _extract_stance_count(pipeline_result: Dict[str, Any]) -> int:
    context_analysis = pipeline_result.get("contextAnalysis")
    if not isinstance(context_analysis, dict):
        return 0
    must_include = context_analysis.get("mustIncludeFromStance")
    if not isinstance(must_include, list):
        return 0
    return len([item for item in must_include if item])


def _validate_keyword_gate(keyword_validation: Dict[str, Any], user_keywords: list[str]) -> tuple[bool, str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords:
        return True, ""

    if not isinstance(keyword_validation, dict) or not keyword_validation:
        return False, "키워드 검증 결과가 없습니다."

    primary_keyword = normalized_user_keywords[0]
    info = keyword_validation.get(primary_keyword)
    if not isinstance(info, dict):
        return False, f"\"{primary_keyword}\" 검증 정보 없음"

    status = str(info.get("status") or "").strip().lower()
    count = _to_int(info.get("count"), 0)
    expected = _to_int(info.get("expected"), 0)
    max_count = _to_int(info.get("max"), 0)
    if status == "insufficient":
        return False, f"\"{primary_keyword}\" 부족 ({count}/{expected})"
    if status == "spam_risk":
        return False, f"\"{primary_keyword}\" 과다 ({count}/{max_count})"
    return True, ""


def _collect_secondary_keyword_soft_issues(
    keyword_validation: Dict[str, Any],
    user_keywords: list[str],
) -> list[str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if len(normalized_user_keywords) <= 1:
        return []
    if not isinstance(keyword_validation, dict) or not keyword_validation:
        return []

    issues: list[str] = []
    for keyword in normalized_user_keywords[1:]:
        info = keyword_validation.get(keyword)
        if not isinstance(info, dict):
            issues.append(f"\"{keyword}\" 검증 정보 없음")
            continue
        status = str(info.get("status") or "").strip().lower()
        count = _to_int(info.get("count"), 0)
        expected = _to_int(info.get("expected"), 0)
        max_count = _to_int(info.get("max"), 0)
        if status == "insufficient":
            issues.append(f"\"{keyword}\" 부족 ({count}/{expected})")
        elif status == "spam_risk":
            issues.append(f"\"{keyword}\" 과다 ({count}/{max_count})")
    return issues


def _normalize_person_name(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _clean_full_name_candidate(raw_name: Any) -> str:
    text = str(raw_name or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^가-힣A-Za-z\s]", "", text).strip()
    compact = _normalize_person_name(text)
    if len(compact) < 2 or len(compact) > 12:
        return ""
    return compact


def _extract_name_from_signature_text(raw_text: Any) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"<[^>]*>", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""

    patterns = [
        re.compile(r"(?:^|[\s\-—])([가-힣]{2,8})\s*드림(?:$|[\s.,])"),
        re.compile(r"(?:^|[\s\-—])([가-힣]{2,8})\s*올림(?:$|[\s.,])"),
    ]
    for pattern in patterns:
        match = pattern.search(normalized)
        if match:
            candidate = _clean_full_name_candidate(match.group(1))
            if candidate:
                return candidate
    return ""


def _resolve_full_name(
    *,
    data: Dict[str, Any],
    user_profile: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    provisional_name: str = "",
) -> str:
    direct_candidates = [
        provisional_name,
        data.get("fullName"),
        data.get("name"),
        user_profile.get("fullName"),
        user_profile.get("name"),
        pipeline_result.get("fullName"),
        pipeline_result.get("name"),
    ]
    for candidate in direct_candidates:
        cleaned = _clean_full_name_candidate(candidate)
        if cleaned:
            return cleaned

    text_candidates: list[str] = []
    for field in ("stanceText", "sourceInput", "sourceContent", "originalContent", "inputContent"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            text_candidates.append(value)

    instructions = data.get("instructions")
    if isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str) and item.strip():
                text_candidates.append(item)
    elif isinstance(instructions, str) and instructions.strip():
        text_candidates.append(instructions)

    for field in ("stanceText", "sourceInput"):
        value = pipeline_result.get(field)
        if isinstance(value, str) and value.strip():
            text_candidates.append(value)

    for text in text_candidates:
        candidate = _extract_name_from_signature_text(text)
        if candidate:
            return candidate
    return ""


def _is_same_speaker_name(candidate: str, full_name: str) -> bool:
    cand = _normalize_person_name(candidate)
    full = _normalize_person_name(full_name)
    if not cand or not full:
        return False
    return cand == full or cand in full or full in cand


def _extract_speaker_consistency_issues(content: str, full_name: str) -> list[str]:
    speaker_name = _normalize_person_name(full_name)
    if not speaker_name:
        return ["화자 실명이 없어 1인칭 정체성 검증을 수행할 수 없음"]

    plain = re.sub(r"<[^>]*>", " ", str(content or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return []

    role_expr = r"(?:시장|부산시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"
    patterns = [
        re.compile(
            rf"저는\s*([가-힣]{{2,8}})\s*(?:{role_expr})?\s*(?:로서|으로서|입니다|이라|라는)",
            re.IGNORECASE,
        ),
        re.compile(rf"저\s*([가-힣]{{2,8}})\s*(?:은|는)\s*(?:{role_expr})", re.IGNORECASE),
    ]

    issues: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(plain):
            detected_name = str(match.group(1) or "").strip()
            if not detected_name:
                continue
            if _is_same_speaker_name(detected_name, speaker_name):
                continue
            issues.append(f"1인칭 화자가 \"{detected_name}\"으로 표기됨")
            break
        if issues:
            break

    self_object_pattern = re.compile(rf"저는\s*{re.escape(speaker_name)}\s*(?:도|를|을)\s*", re.IGNORECASE)
    if self_object_pattern.search(plain):
        issues.append(f"1인칭 문장에서 \"{speaker_name}\" 이름 목적어 오용")

    reverse_pattern = re.compile(
        rf"([가-힣]{{2,8}})\s*(?:{role_expr})\s*로서\s*(저는|제가|저)\b",
        re.IGNORECASE,
    )
    reverse_match = reverse_pattern.search(plain)
    if reverse_match:
        reverse_name = str(reverse_match.group(1) or "").strip()
        if reverse_name and not _is_same_speaker_name(reverse_name, speaker_name):
            issues.append(f"화자 앞 수식어로 \"{reverse_name}\" 인명이 사용됨")
    return issues


def _repair_speaker_consistency_once(content: str, full_name: str) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _normalize_person_name(full_name)
    if not base.strip() or not speaker_name:
        return {"content": base, "edited": False, "appliedPatterns": []}

    applied_patterns: list[str] = []
    repaired = base
    role_expr = r"(?:부산시장|시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"

    def _replace_first_person_named(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        name = str(match.group(2) or "").strip()
        if not name or _is_same_speaker_name(name, speaker_name):
            return match.group(0)
        applied_patterns.append("first_person_named_role")
        return f"{pronoun} "

    pattern_first_person_named = re.compile(
        rf"(저는|제가|저)\s*([가-힣]{{2,8}})\s*(?:{role_expr})?\s*(?:로서|으로서|입니다|이라|라는|은|는)",
        re.IGNORECASE,
    )
    repaired = pattern_first_person_named.sub(_replace_first_person_named, repaired)

    def _replace_reverse_named(match: re.Match[str]) -> str:
        name = str(match.group(1) or "").strip()
        pronoun = str(match.group(2) or "저는").strip()
        if not name or _is_same_speaker_name(name, speaker_name):
            return match.group(0)
        applied_patterns.append("reverse_named_role")
        return f"{pronoun} "

    pattern_reverse_named = re.compile(
        rf"([가-힣]{{2,8}})\s*(?:{role_expr})\s*로서\s*(저는|제가|저)\b",
        re.IGNORECASE,
    )
    repaired = pattern_reverse_named.sub(_replace_reverse_named, repaired)

    self_object_pattern = re.compile(
        rf"(저는|제가)\s*{re.escape(speaker_name)}\s*(?:도|를|을)\s*",
        re.IGNORECASE,
    )

    def _replace_self_object(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        applied_patterns.append("self_name_object")
        return f"{pronoun} "

    repaired = self_object_pattern.sub(_replace_self_object, repaired)
    repaired = re.sub(r"(저는|제가)\s*[,，]\s*", r"\1 ", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired)

    return {
        "content": repaired,
        "edited": repaired != base,
        "appliedPatterns": sorted(set(applied_patterns)),
    }


def _canonical_role_label(role: str) -> str:
    normalized = re.sub(r"\s+", "", str(role or ""))
    if "부산시장" in normalized:
        return "부산시장"
    if "국회의원" in normalized:
        return "국회의원"
    return ""


def _extract_keyword_person_role(keyword: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
    if not normalized:
        return "", ""

    name_match = re.match(r"^([가-힣]{2,8})(?:\s|$)", normalized)
    name = _clean_full_name_candidate(name_match.group(1)) if name_match else ""
    if not name:
        return "", ""

    role_label = ""
    for token, mapped in ROLE_TOKEN_PRIORITY:
        if token in normalized:
            role_label = mapped
            break
    return name, role_label


def _find_conflicting_role_keyword(
    user_keywords: list[str],
    person_roles: Dict[str, str],
) -> str:
    normalized_user_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    if not normalized_user_keywords or not person_roles:
        return ""

    for keyword in normalized_user_keywords:
        name, keyword_role = _extract_keyword_person_role(keyword)
        if not name or not keyword_role:
            continue
        expected_role = _canonical_role_label(person_roles.get(name) or "")
        if expected_role and expected_role != keyword_role:
            return keyword
    return ""


def _build_keyword_intent_h2(keyword: str) -> str:
    normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
    if not normalized:
        return ""

    candidates = (
        f"{normalized} 왜 거론되나?",
        f"{normalized} 경쟁력은?",
        f"{normalized} 쟁점은?",
    )
    for candidate in candidates:
        if 10 <= len(candidate) <= 25:
            return candidate

    fallback = f"{normalized} 쟁점"
    if len(fallback) > 25:
        trimmed = normalized[: max(8, 25 - len(" 쟁점"))].rstrip(" ,.:;!?")
        fallback = f"{trimmed} 쟁점"
    if len(fallback) < 10:
        fallback = (fallback + " 분석")[:25]
    return fallback


def _ensure_keyword_in_subheading_once(content: str, keyword: str) -> Dict[str, Any]:
    base = str(content or "")
    target_keyword = str(keyword or "").strip()
    if not base or not target_keyword:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    # 이미 소제목에 키워드가 있으면 유지.
    for match in h2_matches:
        heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
        if target_keyword in heading:
            return {"content": base, "edited": False}

    replacement = _build_keyword_intent_h2(target_keyword)
    if not replacement:
        return {"content": base, "edited": False}

    person_name, _ = _extract_keyword_person_role(target_keyword)
    target_index = 0
    if person_name:
        for idx, match in enumerate(h2_matches):
            heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
            if person_name in heading:
                target_index = idx
                break

    target_match = h2_matches[target_index]
    updated = base[: target_match.start(1)] + replacement + base[target_match.end(1) :]
    return {
        "content": updated,
        "edited": updated != base,
        "keyword": target_keyword,
        "headingBefore": str(target_match.group(1) or "").strip(),
        "headingAfter": replacement,
    }


def _ensure_user_keyword_in_subheading_once(
    content: str,
    user_keywords: list[str],
    *,
    preferred_keyword: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    normalized_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    if not base or not normalized_keywords:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    for match in h2_matches:
        heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
        if any(keyword in heading for keyword in normalized_keywords):
            return {"content": base, "edited": False}

    target_keyword = ""
    preferred = str(preferred_keyword or "").strip()
    if preferred and preferred in normalized_keywords:
        target_keyword = preferred
    else:
        target_keyword = normalized_keywords[0]

    return _ensure_keyword_in_subheading_once(base, target_keyword)


def _collect_known_person_names(
    *,
    full_name: str,
    role_facts: Dict[str, str],
    user_keywords: list[str],
    poll_fact_table: Dict[str, Any],
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def _push(candidate: str) -> None:
        normalized = _normalize_person_name(candidate)
        if len(normalized) < 2 or len(normalized) > 8:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        names.append(normalized)

    _push(full_name)
    for name in (role_facts or {}).keys():
        _push(str(name))
    for keyword in user_keywords or []:
        extracted_name, _ = _extract_keyword_person_role(str(keyword))
        if extracted_name:
            _push(extracted_name)

    pairs = _safe_dict(poll_fact_table).get("pairs") or {}
    if isinstance(pairs, dict):
        for pair_key in pairs.keys():
            key_text = str(pair_key or "").strip()
            if "__" in key_text:
                left, right = key_text.split("__", 1)
                _push(left)
                _push(right)
    return names


def _pick_primary_person_name(text: str, known_names: list[str]) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain or not known_names:
        return ""

    best_name = ""
    best_score = 0
    for name in known_names:
        normalized = _normalize_person_name(name)
        if len(normalized) < 2:
            continue
        score = plain.count(normalized)
        if score > best_score:
            best_name = normalized
            best_score = score
    return best_name if best_score > 0 else ""


def _repair_subheading_entity_consistency_once(content: str, known_names: list[str]) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not known_names:
        return {"content": base, "edited": False, "replacements": []}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False, "replacements": []}

    replacements: list[Dict[str, str]] = []
    repaired = base
    for idx in range(len(h2_matches) - 1, -1, -1):
        match = h2_matches[idx]
        heading_inner = str(match.group(1) or "")
        heading_plain = re.sub(r"<[^>]*>", " ", heading_inner)
        heading_plain = re.sub(r"\s+", " ", heading_plain).strip()
        if not heading_plain:
            continue

        section_start = match.end()
        section_end = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(repaired)
        section_html = repaired[section_start:section_end]
        paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(section_html))
        if not paragraph_matches:
            continue
        paragraph_plain = " ".join(
            re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(p.group(1) or ""))).strip()
            for p in paragraph_matches[:2]
        ).strip()
        if not paragraph_plain:
            continue

        heading_name = _pick_primary_person_name(heading_plain, known_names)
        body_name = _pick_primary_person_name(paragraph_plain, known_names)
        if not heading_name or not body_name or heading_name == body_name:
            continue

        updated_heading_inner, changed = re.subn(
            re.escape(heading_name),
            body_name,
            heading_inner,
            count=1,
        )
        if changed <= 0:
            continue

        repaired = repaired[:match.start(1)] + updated_heading_inner + repaired[match.end(1):]
        replacements.append(
            {
                "from": heading_name,
                "to": body_name,
                "headingBefore": heading_plain,
                "headingAfter": re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", updated_heading_inner)).strip(),
            }
        )

    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _rewrite_paragraph_blocks(content: str, rewrite_fn) -> str:
    base = str(content or "")
    matches = list(PARAGRAPH_TAG_PATTERN.finditer(base))
    if not matches:
        return str(rewrite_fn(base))

    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(base[cursor: match.start(1)])
        rewritten_inner = str(rewrite_fn(str(match.group(1) or "")) or "")
        parts.append(rewritten_inner)
        cursor = match.end(1)
    parts.append(base[cursor:])
    return "".join(parts)


def _extract_role_check_plain_text(content: str) -> str:
    base = str(content or "")
    paragraph_texts = [
        re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
        for match in PARAGRAPH_TAG_PATTERN.finditer(base)
    ]
    if paragraph_texts:
        plain = " ".join(paragraph_texts)
    else:
        plain = re.sub(r"<[^>]*>", " ", base)
    return re.sub(r"\s+", " ", plain).strip()


def _extract_person_role_facts_from_text(text: Any) -> Dict[str, str]:
    source = re.sub(r"<[^>]*>", " ", str(text or ""))
    source = re.sub(r"\s+", " ", source).strip()
    if not source:
        return {}

    votes: Dict[str, Dict[str, int]] = {}
    for pattern, role in ROLE_FACT_PATTERNS:
        for match in pattern.finditer(source):
            name = _clean_full_name_candidate(match.group(1))
            if not name:
                continue
            role_votes = votes.setdefault(name, {})
            role_votes[role] = int(role_votes.get(role) or 0) + 1

    facts: Dict[str, str] = {}
    priority = {"현 부산시장": 3, "부산시장": 2, "국회의원": 1}
    for name, role_votes in votes.items():
        selected_role = ""
        selected_score = -1
        for role, count in role_votes.items():
            score = int(count) * 10 + int(priority.get(role, 0))
            if score > selected_score:
                selected_role = role
                selected_score = score
        if selected_role:
            facts[name] = selected_role
    return facts


def _build_person_role_facts(
    *,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    source_texts = [
        data.get("newsDataText"),
        pipeline_result.get("newsDataText"),
        data.get("stanceText"),
        data.get("sourceInput"),
    ]
    for text in source_texts:
        extracted = _extract_person_role_facts_from_text(text)
        for name, role in extracted.items():
            if name not in merged:
                merged[name] = role
                continue
            current = str(merged.get(name) or "")
            if _canonical_role_label(current) == _canonical_role_label(role):
                if "현 부산시장" in role and "현 부산시장" not in current:
                    merged[name] = role
                continue
            if "현 부산시장" in role:
                merged[name] = role
    return merged


def _extract_role_consistency_issues(
    content: str,
    person_roles: Dict[str, str],
) -> list[str]:
    if not person_roles:
        return []

    plain = _extract_role_check_plain_text(content)
    if not plain:
        return []

    issues: list[str] = []
    seen: set[str] = set()
    for match in ROLE_MENTION_PATTERN.finditer(plain):
        name = _clean_full_name_candidate(match.group(1))
        if not name or name not in person_roles:
            continue
        expected_role = str(person_roles.get(name) or "").strip()
        expected = _canonical_role_label(expected_role)
        detected_raw = f"{str(match.group(2) or '').strip()} {str(match.group(3) or '').strip()}".strip()
        detected = _canonical_role_label(detected_raw)
        if expected not in {"부산시장", "국회의원"}:
            continue
        if detected not in {"부산시장", "국회의원"}:
            continue
        if expected == detected:
            continue

        issue_key = f"{name}:{detected}->{expected}"
        if issue_key in seen:
            continue
        seen.add(issue_key)
        issues.append(f"\"{name} {detected_raw}\" 직함이 입력 근거(\"{expected_role}\")와 불일치")
        if len(issues) >= 3:
            break
    return issues


def _repair_role_consistency_once(
    content: str,
    person_roles: Dict[str, str],
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    replacements: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        if len(replacements) >= 8:
            return match.group(0)

        name = _clean_full_name_candidate(match.group(1))
        if not name or name not in person_roles:
            return match.group(0)

        expected_role = str(person_roles.get(name) or "").strip()
        expected = _canonical_role_label(expected_role)
        detected_raw = f"{str(match.group(2) or '').strip()} {str(match.group(3) or '').strip()}".strip()
        detected = _canonical_role_label(detected_raw)
        if expected not in {"부산시장", "국회의원"}:
            return match.group(0)
        if detected not in {"부산시장", "국회의원"} or expected == detected:
            return match.group(0)

        target_role = expected_role if expected == "부산시장" else "국회의원"
        normalized_target = re.sub(r"\s+", " ", target_role).strip()
        replacements.append(f"{name}:{detected_raw}->{normalized_target}")
        return f"{name} {normalized_target}"

    def _rewrite_text(text: str) -> str:
        return ROLE_MENTION_PATTERN.sub(_replace, text)

    repaired = _rewrite_paragraph_blocks(base, _rewrite_text)
    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _normalize_lawmaker_honorifics_once(
    content: str,
    person_roles: Dict[str, str],
    full_name: str,
) -> Dict[str, Any]:
    """본문에서 국회의원 인물의 직함 표기를 '의원'으로 통일한다."""
    base = str(content or "")
    if not base.strip() or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    speaker_name = _clean_full_name_candidate(full_name)
    repaired = base
    replacements: list[str] = []

    def _normalize_text(text: str) -> str:
        updated = str(text or "")
        for name, role in person_roles.items():
            cleaned_name = _clean_full_name_candidate(name)
            if not cleaned_name:
                continue
            if speaker_name and cleaned_name == speaker_name:
                continue
            if _canonical_role_label(role) != "국회의원":
                continue

            role_patterns = (
                rf"{re.escape(cleaned_name)}\s*(?:현\s*)?부산시장(?:\s*후보)?",
                rf"{re.escape(cleaned_name)}\s*국회의원(?:\s*후보)?",
                rf"{re.escape(cleaned_name)}\s*후보",
            )
            for pattern in role_patterns:
                changed = False

                def _replace(_: re.Match[str]) -> str:
                    nonlocal changed
                    changed = True
                    return f"{cleaned_name} 의원"

                updated = re.sub(pattern, _replace, updated)
                if changed:
                    replacements.append(pattern)
        return updated

    repaired = _rewrite_paragraph_blocks(base, _normalize_text)

    if repaired != base:
        repaired = repaired.replace("의원와", "의원과")
        repaired = repaired.replace("의원는", "의원은")
        repaired = repaired.replace("의원를", "의원을")
        repaired = repaired.replace("의원가", "의원이")

    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _detect_integrity_gate_issues(content: str) -> list[str]:
    text = str(content or "")
    if not text.strip():
        return ["본문이 비어 있습니다."]

    plain = re.sub(r"<[^>]*>", " ", text)
    plain = re.sub(r"[ \t]+", " ", plain)
    lines = [line.strip() for line in re.split(r"[\r\n]+", plain) if line.strip()]

    issues: list[str] = []
    if any(re.search(r"카테고리\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"검색어\s*삽입\s*횟수\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"생성\s*시간\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"^[\"'“”‘’]?\s*[^\"'“”‘’:\n]{1,80}\s*[\"'“”‘’]?\s*:\s*\d+\s*회$", line) for line in lines):
        issues.append("본문에 검색어 삽입 집계 라인이 포함됨")

    critical_sentence_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"선거까지\s+아직\s*[,，]", re.IGNORECASE),
            "문장 파손(선거까지 아직 ...)",
        ),
        (
            re.compile(r"제가\s+결과(?:는|가)", re.IGNORECASE),
            "문장 파손(제가 결과 ...)",
        ),
        (
            re.compile(r"선거까지\s+남은\s*[,，]", re.IGNORECASE),
            "문장 파손(선거까지 남은 ...)",
        ),
    )
    for pattern, label in critical_sentence_patterns:
        if pattern.search(plain):
            issues.append(label)

    if re.search(r"(?:\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?\s*){5,}", plain):
        issues.append("숫자/단위 토큰이 비정상적으로 연속됨")

    if re.search(r"(?:[가-힣]{2,8}\s*(?:의원|위원장|장관|후보)\s*){4,}", plain):
        issues.append("고유명사/직함 토큰이 비정상적으로 연속됨")
    if re.search(
        r"(?:\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?\s*){2,}(?:[가-힣]{2,8}\s*(?:의원|위원장|장관|후보|시장)\s*){2,}",
        plain,
    ):
        issues.append("숫자+인명/직함 토큰이 비정상적으로 결합됨")

    suspicious_tokens = ("이 사안", "관련 현안")
    suspicious_hits = sum(plain.count(token) for token in suspicious_tokens)
    if suspicious_hits >= 3:
        issues.append("비문 유발 토큰(이 사안/관련 현안) 반복 감지")

    deduped_issues: list[str] = []
    for issue in issues:
        if issue and issue not in deduped_issues:
            deduped_issues.append(issue)
    return deduped_issues


def _extract_blocking_integrity_issues(issues: list[str]) -> list[str]:
    blocking_markers = (
        "문장 파손(",
        "숫자/단위 토큰이 비정상적으로 연속됨",
        "고유명사/직함 토큰이 비정상적으로 연속됨",
        "숫자+인명/직함 토큰이 비정상적으로 결합됨",
        "비문 유발 토큰(이 사안/관련 현안) 반복 감지",
    )
    blocking: list[str] = []
    for issue in issues:
        normalized = str(issue or "").strip()
        if not normalized:
            continue
        if any(marker in normalized for marker in blocking_markers):
            blocking.append(normalized)
    return blocking


def _repair_integrity_noise_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    noise_pattern = re.compile(
        r"(?:\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?\s*){2,}(?:[가-힣]{2,8}\s*(?:의원|위원장|장관|후보|시장)\s*){2,}",
        re.IGNORECASE,
    )
    trailing_noise_pattern = re.compile(
        r"(?:\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?\s*){2,}[가-힣]{2,20}",
        re.IGNORECASE,
    )
    matchup_tail_pattern = re.compile(r"(?:후보군(?:\s*대결(?:에서도|에서)?)?|[가-힣]{1,4}\s*대결(?:에서도|에서))")

    repaired = base
    actions: list[str] = []
    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(base))
    for match in reversed(paragraph_matches):
        inner = str(match.group(1) or "")
        updated_inner = inner
        changed = False

        updated_inner, removed_noise = noise_pattern.subn(" ", updated_inner)
        if removed_noise > 0:
            actions.append(f"numeric_person_chain:{removed_noise}")
            changed = True

        updated_inner, removed_trailing = trailing_noise_pattern.subn(" ", updated_inner)
        if removed_trailing > 0:
            actions.append(f"numeric_tail_chain:{removed_trailing}")
            changed = True
        if changed:
            updated_inner, removed_matchup_tail = matchup_tail_pattern.subn(" ", updated_inner)
            if removed_matchup_tail > 0:
                actions.append(f"matchup_tail:{removed_matchup_tail}")

        if not changed:
            continue

        updated_inner = re.sub(r"\s{2,}", " ", updated_inner).strip()
        plain_after = re.sub(r"<[^>]*>", " ", updated_inner)
        plain_after = re.sub(r"\s+", " ", plain_after).strip()
        if len(plain_after) < 24:
            repaired = repaired[: match.start()] + repaired[match.end() :]
            actions.append("drop_short_noisy_paragraph")
            continue

        repaired = repaired[: match.start(1)] + updated_inner + repaired[match.end(1) :]

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _apply_final_sentence_polish_once(content: str) -> Dict[str, Any]:
    """최종 단계에서 문장 파손 가능성이 낮은 경량 윤문만 1회 적용한다."""
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = remove_grammatical_errors(base)
    actions: list[str] = []
    if repaired != base:
        actions.append("grammar_pattern_rewrite")

    safe_patterns: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r"선거까지\s+남은\s+결코\s+", re.IGNORECASE),
            "선거까지 남은 시간은 결코 ",
            "missing_subject_after_remaining",
        ),
        (
            re.compile(r"선거까지\s+남은\s+아직\s+", re.IGNORECASE),
            "선거까지 남은 시간은 아직 ",
            "missing_subject_after_remaining_alt",
        ),
        (
            re.compile(r"(\d)\.\s+(\d)"),
            r"\1.\2",
            "decimal_spacing",
        ),
        (
            re.compile(r"선거까지\s+아직\s*[,，]\s*", re.IGNORECASE),
            "선거까지 아직 시간이 남았지만, ",
            "dangling_clause_after_still",
        ),
        (
            re.compile(r"선거까지\s+남은\s*[,，]\s*", re.IGNORECASE),
            "선거까지 남은 시간 동안, ",
            "dangling_clause_after_remaining",
        ),
        (
            re.compile(r"에서\s+제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "에서 결과가 ",
            "broken_result_clause_after_i",
        ),
        (
            re.compile(r"제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "결과가 ",
            "broken_result_clause",
        ),
    ]
    for pattern, replacement, action_name in safe_patterns:
        repaired, changed = pattern.subn(replacement, repaired)
        if changed > 0:
            actions.append(f"{action_name}:{changed}")

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _extract_tag_text(text: str, tag: str) -> str:
    if not text:
        return ""
    source = str(text or "").strip()
    if not source:
        return ""

    # Remove markdown code fences first.
    source = re.sub(r"```(?:xml|html|json)?\s*([\s\S]*?)\s*```", r"\1", source, flags=re.IGNORECASE).strip()

    def _normalize_payload(payload: str) -> str:
        cleaned = str(payload or "").strip()
        if not cleaned:
            return ""

        # Remove optional XML declaration.
        cleaned = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", cleaned, flags=re.IGNORECASE)

        # Unwrap CDATA wrappers repeatedly.
        cdata_pattern = re.compile(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", re.DOTALL)
        while True:
            m = cdata_pattern.match(cleaned)
            if not m:
                break
            cleaned = str(m.group(1) or "").strip()

        # Guard against leaked CDATA delimiters from malformed outputs.
        cleaned = cleaned.replace("<![CDATA[", "").replace("]]>", "").strip()
        return cleaned

    def _extract_from(raw: str) -> str:
        pattern = re.compile(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", re.IGNORECASE)
        matches = list(pattern.finditer(raw))
        for match in reversed(matches):
            candidate = _normalize_payload(match.group(1) or "")
            if not candidate:
                continue
            # Skip obvious placeholder echoes from prompt examples.
            plain = re.sub(r"<[^>]*>", " ", candidate)
            plain = re.sub(r"\s+", " ", plain).strip().lower()
            if "html 본문" in plain and len(plain) < 40:
                continue
            if plain in {"...", "…"}:
                continue
            return candidate
        return ""

    extracted = _extract_from(source)
    if extracted:
        return extracted

    # Retry once with HTML-unescaped text (&lt;content&gt;...).
    unescaped = html.unescape(source)
    if unescaped != source:
        extracted = _extract_from(unescaped)
        if extracted:
            return extracted

    return ""


def _extract_content_payload(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    extracted = _extract_tag_text(source, "content")
    if extracted:
        return extracted

    # JSON fallback: {"content": "..."}
    stripped = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", source, flags=re.IGNORECASE).strip()
    json_candidate = ""
    if stripped.startswith("{") and stripped.endswith("}"):
        json_candidate = stripped
    else:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if match:
            json_candidate = match.group(0)
    if json_candidate:
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, dict):
                content_value = parsed.get("content")
                if isinstance(content_value, str):
                    return content_value.strip()
        except Exception:
            pass

    return ""


def _run_async_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


def _recover_short_content_once(
    *,
    content: str,
    title: str,
    topic: str,
    min_required_chars: int,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
) -> Dict[str, Any]:
    """분량 부족 시 1회 확장 보정."""
    base_content = str(content or "").strip()
    base_len = _count_chars_no_space(base_content)
    if not base_content or base_len >= min_required_chars:
        return {"content": base_content, "edited": False}

    max_chars = max(int(target_word_count * 1.2), min_required_chars + 220)
    prompt = f"""
<length_repair_prompt version="xml-v1">
  <role>당신은 한국어 정치 콘텐츠 편집자입니다. 본문 의미를 유지한 채 분량만 확장하세요.</role>
  <goal>
    <current_chars>{base_len}</current_chars>
    <min_chars>{min_required_chars}</min_chars>
    <max_chars>{max_chars}</max_chars>
  </goal>
  <rules>
    <rule order="1">핵심 주장/사실을 삭제하거나 왜곡하지 말 것.</rule>
    <rule order="2">허용 태그는 &lt;h2&gt;와 &lt;p&gt;만 사용.</rule>
    <rule order="3">같은 문장/같은 구문 반복으로 분량을 채우지 말 것.</rule>
    <rule order="4">행사 일시+장소 결합 문구는 2회를 넘기지 말 것.</rule>
    <rule order="5">키워드 과잉 삽입 금지.</rule>
  </rules>
  <topic>{topic}</topic>
  <title>{title}</title>
  <keywords>{', '.join(user_keywords)}</keywords>
  <draft><![CDATA[{base_content}]]></draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>content</allowed_tags>
    <example><![CDATA[<content>...HTML 본문...</content>]]></example>
  </output_contract>
</length_repair_prompt>
""".strip()

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

        response_text = _run_async_sync(
            generate_content_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.0,
                max_output_tokens=8192,
            )
        )
    except Exception as exc:
        logger.warning("분량 자동 보정 호출 실패: %s", exc)
        return {"content": base_content, "edited": False, "error": str(exc)}

    candidate = _extract_content_payload(response_text)
    if not candidate:
        logger.warning("Length auto-repair parse failed: no <content> payload extracted")
        return {"content": base_content, "edited": False}

    candidate_len = _count_chars_no_space(candidate)
    if candidate_len <= base_len:
        return {"content": base_content, "edited": False}

    keyword_repair = _repair_keyword_gate_once(
        content=candidate,
        title_text=title,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        body_min_overrides=body_min_overrides,
    )
    repaired_content = str(keyword_repair.get("content") or candidate)
    keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
    keyword_counts = keyword_repair.get("keywordCounts")
    if not isinstance(keyword_counts, dict):
        keyword_counts = {}

    return {
        "content": repaired_content,
        "edited": repaired_content != base_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "before": base_len,
        "after": _count_chars_no_space(repaired_content),
    }


def _repair_keyword_gate_once(
    *,
    content: str,
    title_text: str,
    user_keywords: list[str],
    auto_keywords: list[str],
    target_word_count: int,
    body_min_overrides: Dict[str, int],
) -> Dict[str, Any]:
    """키워드 게이트 실패(부족/과다)를 1회 자동 보정한다."""
    base_content = str(content or "")
    enforcement = enforce_keyword_requirements(
        base_content,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        title_text=title_text,
        body_min_overrides=body_min_overrides,
        max_iterations=2,
    )

    repaired_content = str(enforcement.get("content") or base_content)
    keyword_result = enforcement.get("keywordResult")
    if not isinstance(keyword_result, dict):
        keyword_result = validate_keyword_insertion(
            repaired_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
        )

    keyword_validation = build_keyword_validation(keyword_result)
    keyword_details = (keyword_result.get("details") or {}).get("keywords") or {}
    keyword_counts = {
        keyword: int((info or {}).get("coverage") or (info or {}).get("count") or 0)
        for keyword, info in keyword_details.items()
        if isinstance(info, dict)
    }
    reductions = enforcement.get("reductions") if isinstance(enforcement.get("reductions"), list) else []

    return {
        "content": repaired_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "edited": repaired_content != base_content,
        "reductions": reductions,
    }


def _extract_repetition_gate_issues(heuristic_result: Dict[str, Any]) -> list[str]:
    issues = heuristic_result.get("issues") if isinstance(heuristic_result, dict) else []
    if not isinstance(issues, list):
        return []
    repetition_keywords = ("문장 반복 감지", "구문 반복 감지", "유사 문장 감지")
    return [
        str(item).strip()
        for item in issues
        if isinstance(item, str) and any(keyword in item for keyword in repetition_keywords)
    ]


def _extract_legal_gate_issues(heuristic_result: Dict[str, Any]) -> list[str]:
    issues = heuristic_result.get("issues") if isinstance(heuristic_result, dict) else []
    if not isinstance(issues, list):
        return []
    legal_keywords = ("선거법 위반",)
    return [
        str(item).strip()
        for item in issues
        if isinstance(item, str) and any(keyword in item for keyword in legal_keywords)
    ]


def _append_quality_warning(warnings: list[str], message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    if text not in warnings:
        warnings.append(text)


def _detect_content_repair_corruption(before: str, after: str) -> tuple[bool, str]:
    before_text = str(before or "")
    after_text = str(after or "")
    if not after_text.strip():
        return True, "empty_output"

    before_len = _count_chars_no_space(before_text)
    after_len = _count_chars_no_space(after_text)
    if before_len >= 1200 and after_len < int(before_len * 0.78):
        return True, f"length_drop:{before_len}->{after_len}"

    suspicious_tokens = ("이 사안", "관련 현안")
    before_hits = sum(before_text.count(token) for token in suspicious_tokens)
    after_hits = sum(after_text.count(token) for token in suspicious_tokens)
    if after_hits >= max(3, before_hits + 2):
        return True, f"suspicious_token_spike:{before_hits}->{after_hits}"

    return False, ""


def _build_editor_keyword_feedback(
    keyword_validation: Dict[str, Any],
    user_keywords: list[str],
) -> Dict[str, Any]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords:
        return {"passed": True, "issues": [], "softIssues": []}

    hard_issues: list[str] = []
    soft_issues: list[str] = []
    for index, keyword in enumerate(normalized_user_keywords):
        info = keyword_validation.get(keyword) if isinstance(keyword_validation, dict) else None
        if not isinstance(info, dict):
            if index == 0:
                hard_issues.append(f"키워드 \"{keyword}\" 검증 정보가 없습니다.")
            else:
                soft_issues.append(f"보조 키워드 \"{keyword}\" 검증 정보가 없습니다.")
            continue

        status = str(info.get("status") or "").strip().lower()
        count = _to_int(info.get("count"), 0)
        expected = _to_int(info.get("expected"), 0)
        max_count = _to_int(info.get("max"), 0)
        if status == "insufficient":
            message = f"키워드 \"{keyword}\"가 부족합니다 ({count}/{expected})."
            if index == 0:
                hard_issues.append(message)
            else:
                soft_issues.append(f"보조 {message}")
        elif status == "spam_risk":
            message = f"키워드 \"{keyword}\"가 과다합니다 ({count}/{max_count})."
            if index == 0:
                hard_issues.append(message)
            else:
                soft_issues.append(f"보조 {message}")

    return {"passed": len(hard_issues) == 0, "issues": hard_issues, "softIssues": soft_issues}


def _score_title_compliance(
    *,
    title: str,
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    candidate = _normalize_title_surface_local(title)
    if not candidate:
        return {"passed": False, "score": 0, "reason": "empty", "title": ""}
    try:
        from agents.common.title_generation import calculate_title_quality_score

        result = calculate_title_quality_score(
            candidate,
            {
                "topic": str(topic or ""),
                "contentPreview": str(content or ""),
                "userKeywords": list(user_keywords or []),
                "fullName": str(full_name or ""),
                "category": str(category or ""),
                "status": str(status or ""),
                "contextAnalysis": context_analysis if isinstance(context_analysis, dict) else {},
            },
        )
        repaired_title = ""
        if isinstance(result, dict):
            repaired_title = str(result.get("repairedTitle") or "").strip()
        final_title = candidate
        if repaired_title:
            final_title = _normalize_title_surface_local(repaired_title) or repaired_title or candidate
        score = _to_int(result.get("score"), 0) if isinstance(result, dict) else 0
        strict_pass = bool(result.get("passed") is True) if isinstance(result, dict) else False
        # 최종 출력 가드는 하드 실패(score=0)만 차단한다.
        # 점수 70 미만의 소프트 이슈는 경고로 남기고 제목 생성은 계속 진행한다.
        passed = strict_pass or score > 0
        suggestions = result.get("suggestions") if isinstance(result, dict) else []
        reason = ""
        if isinstance(suggestions, list) and suggestions:
            reason = str(suggestions[0] or "").strip()
        if passed and not strict_pass:
            logger.info(
                "Title guard soft-pass applied (score=%s, reason=%s, title=%s)",
                score,
                reason,
                final_title,
            )
        return {
            "passed": passed,
            "score": score,
            "reason": reason,
            "title": final_title,
        }
    except Exception as exc:
        logger.warning("Title compliance scoring failed (non-fatal): %s", exc)
        return {"passed": True, "score": 0, "reason": "scoring_error", "title": candidate}


def _guard_title_after_editor(
    *,
    candidate_title: str,
    previous_title: str,
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
) -> tuple[str, Dict[str, Any]]:
    candidate = _normalize_title_surface_local(candidate_title)
    _ = _normalize_title_surface_local(previous_title)

    candidate_score = _score_title_compliance(
        title=candidate,
        topic=topic,
        content=content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=status,
        context_analysis=context_analysis,
    )
    scored_title = (
        _normalize_title_surface_local(str(candidate_score.get("title") or candidate))
        or candidate
    )
    if candidate_score.get("passed"):
        repaired = scored_title != candidate
        if repaired:
            logger.info(
                "Title guard auto-repaired candidate title: \"%s\" -> \"%s\"",
                candidate,
                scored_title,
            )
        return scored_title, {
            "accepted": True,
            "source": "candidate",
            "score": candidate_score.get("score"),
            "reason": candidate_score.get("reason"),
            "repaired": repaired,
        }

    reason = str(candidate_score.get("reason") or "candidate_failed")
    raise ApiError("internal", f"제목 검증 실패: {reason}")


def _extract_keyword_counts(keyword_result: Dict[str, Any] | None) -> Dict[str, int]:
    details = ((keyword_result or {}).get("details") or {}).get("keywords") or {}
    if not isinstance(details, dict):
        return {}

    counts: Dict[str, int] = {}
    for raw_keyword, raw_info in details.items():
        if not isinstance(raw_info, dict):
            continue

        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue

        keyword_type = str(raw_info.get("type") or "").strip().lower()
        exact_count = _to_int(raw_info.get("exactCount"), _to_int(raw_info.get("count"), 0))
        coverage_count = _to_int(raw_info.get("coverage"), exact_count)
        counts[keyword] = exact_count if keyword_type == "user" else coverage_count

    return counts


def _resolve_output_format_options(
    *,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    user_profile: Dict[str, Any],
    category: str,
) -> Dict[str, Any]:
    sub_category = str(
        pipeline_result.get("subCategory")
        or data.get("subCategory")
        or ""
    )
    allow_diagnostic_tail = (
        str(category or "").strip() == "current-affairs"
        and sub_category == "current_affairs_diagnosis"
    )

    slogan = str(
        pipeline_result.get("slogan")
        or data.get("slogan")
        or user_profile.get("slogan")
        or ""
    )
    slogan_enabled = bool(
        pipeline_result.get("sloganEnabled") is True
        or data.get("sloganEnabled") is True
        or user_profile.get("sloganEnabled") is True
    )
    donation_info = str(
        pipeline_result.get("donationInfo")
        or data.get("donationInfo")
        or user_profile.get("donationInfo")
        or ""
    )
    donation_enabled = bool(
        pipeline_result.get("donationEnabled") is True
        or data.get("donationEnabled") is True
        or user_profile.get("donationEnabled") is True
    )
    poll_citation = build_poll_citation_text(
        data.get("stanceText"),
        data.get("newsDataText"),
    )
    embed_poll_citation = _to_bool(
        data.get("embedPollCitation")
        if data.get("embedPollCitation") is not None
        else pipeline_result.get("embedPollCitation"),
        False,
    )

    return {
        "allowDiagnosticTail": allow_diagnostic_tail,
        "slogan": slogan,
        "sloganEnabled": slogan_enabled,
        "donationInfo": donation_info,
        "donationEnabled": donation_enabled,
        "pollCitation": poll_citation,
        "embedPollCitation": embed_poll_citation,
        "topic": str(pipeline_result.get("topic") or data.get("prompt") or data.get("topic") or ""),
        "bookTitleHint": str(
            (
                (_safe_dict(pipeline_result.get("contextAnalysis")).get("mustPreserve") or {})
                if isinstance(_safe_dict(pipeline_result.get("contextAnalysis")).get("mustPreserve"), dict)
                else {}
            ).get("bookTitle")
            or ""
        ),
        "contextAnalysis": _safe_dict(pipeline_result.get("contextAnalysis")),
        "fullName": str(
            pipeline_result.get("fullName")
            or data.get("fullName")
            or data.get("name")
            or user_profile.get("fullName")
            or user_profile.get("name")
            or ""
        ).strip(),
    }


def _apply_last_mile_postprocess(
    *,
    content: str,
    title_text: str,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
    output_options: Dict[str, Any],
    fallback_keyword_validation: Dict[str, Any],
    fallback_keyword_counts: Dict[str, Any],
) -> Dict[str, Any]:
    base_content = str(content or "").strip()
    fallback_counts = (
        fallback_keyword_counts
        if isinstance(fallback_keyword_counts, dict)
        else {}
    )
    if not base_content:
        return {
            "content": base_content,
            "wordCount": 0,
            "keywordValidation": fallback_keyword_validation if isinstance(fallback_keyword_validation, dict) else {},
            "keywordCounts": fallback_counts,
            "meta": {},
            "edited": False,
            "error": None,
        }

    try:
        cleaned = cleanup_post_content(base_content)
        interim_keyword_result = validate_keyword_insertion(
            cleaned,
            user_keywords,
            auto_keywords,
            target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
        )
        finalized = finalize_output(
            cleaned,
            slogan=str(output_options.get("slogan") or ""),
            slogan_enabled=bool(output_options.get("sloganEnabled") is True),
            donation_info=str(output_options.get("donationInfo") or ""),
            donation_enabled=bool(output_options.get("donationEnabled") is True),
            poll_citation=str(output_options.get("pollCitation") or ""),
            embed_poll_citation=bool(output_options.get("embedPollCitation") is True),
            allow_diagnostic_tail=bool(output_options.get("allowDiagnosticTail") is True),
            keyword_result=interim_keyword_result,
            topic=str(output_options.get("topic") or ""),
            book_title_hint=str(output_options.get("bookTitleHint") or ""),
            context_analysis=(
                output_options.get("contextAnalysis")
                if isinstance(output_options.get("contextAnalysis"), dict)
                else None
            ),
            full_name=str(output_options.get("fullName") or ""),
            target_word_count=target_word_count,
        )
        finalized_content = str(finalized.get("content") or cleaned).strip()

        final_keyword_result = validate_keyword_insertion(
            finalized_content,
            user_keywords,
            auto_keywords,
            target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
        )
        final_keyword_validation = build_keyword_validation(final_keyword_result)
        final_keyword_counts = _extract_keyword_counts(final_keyword_result)

        return {
            "content": finalized_content,
            "wordCount": _count_chars_no_space(finalized_content),
            "keywordValidation": final_keyword_validation,
            "keywordCounts": final_keyword_counts,
            "meta": _safe_dict(finalized.get("meta")),
            "edited": finalized_content != base_content,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Last-mile cleanup/finalize failed (non-fatal): %s", exc)
        return {
            "content": base_content,
            "wordCount": _count_chars_no_space(base_content),
            "keywordValidation": fallback_keyword_validation if isinstance(fallback_keyword_validation, dict) else {},
            "keywordCounts": fallback_counts,
            "meta": {},
            "edited": False,
            "error": str(exc),
        }


def _run_editor_repair_once(
    *,
    content: str,
    title: str,
    full_name: str,
    status: str,
    target_word_count: int,
    user_keywords: list[str],
    validation_result: Dict[str, Any],
    keyword_validation: Dict[str, Any],
    extra_issues: Optional[list[str]] = None,
    purpose: str = "repair",
) -> Dict[str, Any]:
    """기준 미충족 시 EditorAgent로 1회 교정 시도."""
    base_content = str(content or "")
    base_title = str(title or "")
    keyword_feedback = _build_editor_keyword_feedback(keyword_validation, user_keywords)
    if extra_issues:
        normalized_extra_issues = [str(item).strip() for item in extra_issues if str(item).strip()]
        if normalized_extra_issues:
            feedback_issues = list(keyword_feedback.get("issues") or [])
            for issue in normalized_extra_issues:
                tagged_issue = f"품질 무결성: {issue}"
                if tagged_issue not in feedback_issues:
                    feedback_issues.append(tagged_issue)
            keyword_feedback["issues"] = feedback_issues
            keyword_feedback["passed"] = False
    normalized_purpose = str(purpose or "repair").strip().lower()

    try:
        from agents.core.editor_agent import EditorAgent

        agent = EditorAgent()
        editor_input = {
            "content": base_content,
            "title": base_title,
            "fullName": str(full_name or "").strip(),
            "validationResult": validation_result if isinstance(validation_result, dict) else {},
            "keywordResult": keyword_feedback,
            "keywords": user_keywords,
            "status": status,
            "targetWordCount": int(target_word_count or 2000),
            "polishMode": normalized_purpose == "polish",
        }
        result = _run_async_sync(agent.run(editor_input))
        if not isinstance(result, dict):
            result = {}

        repaired_content = str(result.get("content") or base_content).strip()
        repaired_title = str(result.get("title") or base_title).strip() or base_title
        edit_summary = result.get("editSummary")
        if not isinstance(edit_summary, list):
            edit_summary = []

        return {
            "content": repaired_content,
            "title": repaired_title,
            "edited": (repaired_content != base_content) or (repaired_title != base_title),
            "editSummary": edit_summary,
            "error": None,
        }
    except Exception as exc:
        logger.warning("EditorAgent auto-repair failed (non-fatal): %s", exc)
        return {
            "content": base_content,
            "title": base_title,
            "edited": False,
            "editSummary": [],
            "error": str(exc),
        }


def _recover_repetition_issues_once(
    *,
    content: str,
    title: str,
    topic: str,
    repetition_issues: list[str],
    min_required_chars: int,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
) -> Dict[str, Any]:
    """반복 품질 실패 시 LLM 재작성으로 1회 자동 교정."""
    base_content = str(content or "").strip()
    base_len = _count_chars_no_space(base_content)
    if not base_content or not repetition_issues:
        return {"content": base_content, "edited": False}

    issue_lines = "\n".join(f"- {item}" for item in repetition_issues[:4])
    keyword_text = ", ".join(str(item).strip() for item in user_keywords if str(item).strip())
    prompt = f"""
<repetition_repair_prompt version="xml-v1">
  <role>당신은 한국어 정치 콘텐츠 교열자입니다. 반복 문제만 해결하고 의미/사실은 유지하세요.</role>
  <goal>
    <current_chars>{base_len}</current_chars>
    <min_chars>{min_required_chars}</min_chars>
    <target_chars>{int(target_word_count * 0.9)}~{int(target_word_count * 1.2)}</target_chars>
  </goal>
  <issues>
{issue_lines}
  </issues>
  <rules>
    <rule order="1">핵심 주장, 일정, 장소, 고유명사, 수치 사실을 삭제/왜곡하지 말 것.</rule>
    <rule order="2">문장/구문 반복 문제만 해결하고, 동일 어구 연쇄 반복을 피할 것.</rule>
    <rule order="3">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="4">검증 규칙 설명문(메타 문장)이나 템플릿 문장을 본문에 쓰지 말 것.</rule>
    <rule order="5">사용자 키워드가 있다면 문맥 안에서 자연스럽게 유지할 것.</rule>
  </rules>
  <topic>{topic}</topic>
  <title>{title}</title>
  <keywords>{keyword_text}</keywords>
  <draft><![CDATA[{base_content}]]></draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>content</allowed_tags>
    <example><![CDATA[<content>...HTML 본문...</content>]]></example>
  </output_contract>
</repetition_repair_prompt>
""".strip()

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

        response_text = _run_async_sync(
            generate_content_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.1,
                max_output_tokens=8192,
            )
        )
    except Exception as exc:
        logger.warning("반복 품질 자동 보정 호출 실패: %s", exc)
        return {"content": base_content, "edited": False, "error": str(exc)}

    candidate = _extract_content_payload(response_text)
    if not candidate:
        logger.warning("Repetition auto-repair parse failed: no <content> payload extracted")
        return {"content": base_content, "edited": False}

    candidate_len = _count_chars_no_space(candidate)
    if candidate_len < min_required_chars:
        logger.warning(
            "반복 품질 자동 보정 결과 분량 미달로 폐기: before=%s after=%s min=%s",
            base_len,
            candidate_len,
            min_required_chars,
        )
        return {"content": base_content, "edited": False}
    if base_len >= 1600 and candidate_len < int(base_len * 0.8):
        logger.warning(
            "반복 품질 자동 보정 결과 과축약으로 폐기: before=%s after=%s",
            base_len,
            candidate_len,
        )
        return {"content": base_content, "edited": False}

    keyword_repair = _repair_keyword_gate_once(
        content=candidate,
        title_text=title,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        body_min_overrides=body_min_overrides,
    )
    repaired_content = str(keyword_repair.get("content") or candidate)
    keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
    keyword_counts = keyword_repair.get("keywordCounts")
    if not isinstance(keyword_counts, dict):
        keyword_counts = {}

    return {
        "content": repaired_content,
        "edited": repaired_content != base_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "before": base_len,
        "after": _count_chars_no_space(repaired_content),
    }


def _choose_pipeline_route(raw_route: Any, *, is_admin: bool, is_tester: bool) -> str:
    return str(raw_route or "modular").strip() or "modular"


def handle_generate_posts_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    started_ms = int(time.time() * 1000)
    uid = req.auth.uid if req.auth else ""
    _ensure_user(uid)

    data = req.data if isinstance(req.data, dict) else {}
    if isinstance(data.get("data"), dict):
        data = data["data"]

    topic, category = _topic_and_category(data)
    target_word_count = _target_word_count(data, category)

    progress_session_id = str(data.get("progressSessionId") or f"{uid}_{int(time.time() * 1000)}")
    progress = ProgressTracker(progress_session_id)
    progress.step_preparing()

    # 프로필 로드 (권한/세션/경고/응답 메타데이터용)
    profile_bundle = load_user_profile(uid, category=category, topic=topic, options={"strictSourceOnly": True})
    user_profile = _safe_dict(profile_bundle.get("userProfile"))
    is_admin = bool(profile_bundle.get("isAdmin") is True)
    is_tester = bool(profile_bundle.get("isTester") is True)
    full_name = str(
        data.get("fullName")
        or user_profile.get("fullName")
        or user_profile.get("name")
        or ""
    ).strip()
    daily_limit_warning = _calc_daily_limit_warning(user_profile)
    editor_polish_enabled = _to_bool(data.get("editorPolish"), False)
    editor_second_pass_enabled = _to_bool(data.get("editorSecondPass"), False)

    requested_session_id = str(data.get("sessionId") or "").strip()
    if not requested_session_id:
        _clear_active_session(uid)

    session = get_or_create_session(uid, is_admin=is_admin, is_tester=is_tester, category=category, topic=topic)
    session = _safe_dict(session)
    attempts = _to_int(session.get("attempts"), 0)
    max_attempts = _to_int(session.get("maxAttempts"), 3)
    if attempts >= max_attempts:
        raise ApiError(
            "resource-exhausted",
            f"최대 {max_attempts}회까지만 재생성할 수 있습니다. 새로운 원고를 생성해주세요.",
        )

    progress.step_collecting()
    progress.step_generating()

    user_keywords = _normalize_keywords(data.get("keywords"))
    pipeline_route = _choose_pipeline_route(data.get("pipeline"), is_admin=is_admin, is_tester=is_tester)
    start_payload = _extract_start_payload(
        uid,
        data,
        topic=topic,
        category=category,
        target_word_count=target_word_count,
        user_keywords=user_keywords,
        pipeline_route=pipeline_route,
    )

    job_id = _call_pipeline_start(start_payload)
    pipeline_result = _poll_pipeline(job_id, progress)
    pipeline_user_keywords = _normalize_keywords(
        pipeline_result.get("userKeywords") or pipeline_result.get("keywords")
    )
    if not user_keywords and pipeline_user_keywords:
        user_keywords = pipeline_user_keywords
        logger.info(
            "요청 본문에서 추출된 userKeywords를 후처리 게이트에 반영: %s",
            user_keywords[:5],
        )
    output_format_options = _resolve_output_format_options(
        data=data,
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        user_profile=user_profile,
        category=category,
    )

    generated_content = str(pipeline_result.get("content") or "").strip()
    if not generated_content:
        raise ApiError("internal", "원고 생성 실패 - 콘텐츠가 생성되지 않았습니다.")

    full_name = _resolve_full_name(
        data=data,
        user_profile=user_profile,
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        provisional_name=full_name,
    )
    if not full_name:
        raise ApiError(
            "failed-precondition",
            "화자 이름을 확인할 수 없습니다. 프로필 이름 또는 fullName을 설정한 뒤 다시 시도해 주세요.",
        )
    output_format_options["fullName"] = full_name
    role_facts = _build_person_role_facts(
        data=data if isinstance(data, dict) else {},
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
    )
    poll_fact_table = build_poll_matchup_fact_table(
        [
            data.get("newsDataText"),
            pipeline_result.get("newsDataText"),
            data.get("stanceText"),
            data.get("sourceInput"),
            pipeline_result.get("sourceInput"),
        ],
        known_names=[*list(role_facts.keys()), full_name],
    )
    conflicting_role_keyword = _find_conflicting_role_keyword(user_keywords, role_facts)
    body_min_overrides: Dict[str, int] = {}
    if conflicting_role_keyword:
        body_min_overrides[conflicting_role_keyword] = 0

    quality_warnings: list[str] = []
    _raw_pipeline_title = str(pipeline_result.get("title") or "").strip()
    if not _raw_pipeline_title:
        raise ApiError("internal", "제목 생성에 실패했습니다. 다시 시도해 주세요.")
    generated_title = _normalize_title_surface_local(_raw_pipeline_title) or _raw_pipeline_title
    keyword_validation = _safe_dict(pipeline_result.get("keywordValidation"))
    seo_passed = pipeline_result.get("seoPassed")
    compliance_passed = pipeline_result.get("compliancePassed")
    writing_method = str(pipeline_result.get("writingMethod") or pipeline_route or "modular")
    context_analysis_for_title = _safe_dict(pipeline_result.get("contextAnalysis"))
    must_preserve_for_title = _safe_dict(context_analysis_for_title.get("mustPreserve"))
    event_date_hint_for_guard = str(must_preserve_for_title.get("eventDate") or "").strip()
    keyword_counts = pipeline_result.get("keywordCounts") if isinstance(pipeline_result.get("keywordCounts"), dict) else {}
    auto_keywords = _normalize_keywords(pipeline_result.get("autoKeywords"))
    word_count = _to_int(pipeline_result.get("wordCount"), _count_chars_no_space(generated_content))
    stance_count = _extract_stance_count(pipeline_result)
    min_required_chars = _calc_min_required_chars(target_word_count, stance_count)
    status_for_validation = str(data.get("status") or user_profile.get("status") or "")
    title_last_valid = generated_title
    title_guard_trace: list[Dict[str, Any]] = []
    speaker_gate: Dict[str, Any] = {
        "checked": False,
        "fullName": full_name,
        "initialIssues": [],
        "repairAttempted": False,
        "repairApplied": False,
        "repairPatterns": [],
        "finalIssues": [],
        "blocked": False,
    }
    role_gate: Dict[str, Any] = {
        "enabled": bool(role_facts),
        "facts": role_facts,
        "initialIssues": [],
        "repairAttempted": False,
        "repairApplied": False,
        "replacements": [],
        "honorificRepairApplied": False,
        "honorificReplacements": [],
        "finalIssues": [],
    }
    poll_fact_guard: Dict[str, Any] = {
        "enabled": bool((_safe_dict(poll_fact_table).get("pairs") or {})),
        "pairCount": len((_safe_dict(poll_fact_table).get("pairs") or {})),
        "title": {"checked": 0, "edited": False, "blockingIssues": [], "repairs": []},
        "content": {"checked": 0, "edited": False, "blockingIssues": [], "warnings": [], "repairs": []},
    }
    date_weekday_guard: Dict[str, Any] = {
        "applied": False,
        "yearHint": "",
        "title": {"edited": False, "changes": [], "issues": []},
        "content": {"edited": False, "changes": [], "issues": []},
    }
    length_repair_applied = False
    keyword_repair_applied = False
    repetition_rule_repair_applied = False
    repetition_llm_repair_applied = False
    editor_keyword_repair_applied = False
    max_content_repair_steps = 4
    content_repair_steps = 0
    content_repair_rollbacks: list[Dict[str, Any]] = []
    content_meta: Dict[str, Any] = {}
    final_sentence_polish: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "actions": [],
        "skippedReason": "",
    }
    subheading_entity_gate: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "replacements": [],
        "skippedReason": "",
    }
    integrity_editor_repair: Dict[str, Any] = {
        "attempted": 0,
        "applied": 0,
        "error": None,
        "summary": [],
    }

    def _apply_content_repair(stage: str, candidate_content: str) -> bool:
        nonlocal generated_content, word_count, content_repair_steps

        candidate = str(candidate_content or "").strip()
        if not candidate or candidate == generated_content:
            return False

        if content_repair_steps >= max_content_repair_steps:
            logger.info(
                "Content repair skipped(stage=%s): budget exhausted (%s/%s)",
                stage,
                content_repair_steps,
                max_content_repair_steps,
            )
            return False

        corrupted, reason = _detect_content_repair_corruption(generated_content, candidate)
        if corrupted:
            logger.warning("Content repair rollback(stage=%s): %s", stage, reason)
            content_repair_rollbacks.append({"stage": stage, "reason": reason})
            return False

        generated_content = candidate
        word_count = _count_chars_no_space(generated_content)
        content_repair_steps += 1
        return True

    heading_anchor = _ensure_user_keyword_in_subheading_once(
        generated_content,
        user_keywords,
        preferred_keyword=conflicting_role_keyword,
    )
    if heading_anchor.get("edited"):
        candidate_content = str(heading_anchor.get("content") or generated_content)
        if _apply_content_repair("keyword_heading_anchor", candidate_content):
            logger.info(
                "검색어 소제목 앵커링 적용: keyword=%s before=%s after=%s",
                heading_anchor.get("keyword"),
                heading_anchor.get("headingBefore"),
                heading_anchor.get("headingAfter"),
            )

    integrity_repair = _repair_integrity_noise_once(generated_content)
    if integrity_repair.get("edited"):
        integrity_candidate = str(integrity_repair.get("content") or generated_content)
        if _apply_content_repair("integrity_noise_repair", integrity_candidate):
            logger.info(
                "무결성 노이즈 자동 보정 적용: actions=%s",
                integrity_repair.get("actions"),
            )

    initial_keyword_gate_ok, initial_keyword_gate_msg = _validate_keyword_gate(keyword_validation, user_keywords)
    initial_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
    )
    initial_repetition_issues = _extract_repetition_gate_issues(initial_heuristic)
    initial_legal_issues = _extract_legal_gate_issues(initial_heuristic)
    initial_length_ok = word_count >= min_required_chars
    first_pass_failure_reasons: list[str] = []
    if not initial_length_ok:
        first_pass_failure_reasons.append("length")
    if not initial_keyword_gate_ok:
        first_pass_failure_reasons.append("keyword")
    if initial_repetition_issues:
        first_pass_failure_reasons.append("repetition")
    if initial_legal_issues:
        first_pass_failure_reasons.append("election_law")
    first_pass_passed = len(first_pass_failure_reasons) == 0

    logger.info(
        "분량 게이트 계산: target=%s, stance_count=%s, min_required=%s, actual=%s",
        target_word_count,
        stance_count,
        min_required_chars,
        word_count,
    )
    logger.info(
        "QUALITY_METRIC generate_posts first_pass=%s reason=%s length_ok=%s keyword_ok=%s repetition=%s legal=%s",
        int(first_pass_passed),
        ",".join(first_pass_failure_reasons) if first_pass_failure_reasons else "none",
        initial_length_ok,
        initial_keyword_gate_ok,
        len(initial_repetition_issues),
        len(initial_legal_issues),
    )
    if word_count < min_required_chars:
        length_repair = _recover_short_content_once(
            content=generated_content,
            title=generated_title,
            topic=topic,
            min_required_chars=min_required_chars,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            body_min_overrides=body_min_overrides,
        )
        if length_repair.get("edited"):
            candidate_content = str(length_repair.get("content") or generated_content)
            if _apply_content_repair("length_repair", candidate_content):
                length_repair_applied = True
                repaired_keyword_validation = length_repair.get("keywordValidation")
                if isinstance(repaired_keyword_validation, dict) and repaired_keyword_validation:
                    keyword_validation = repaired_keyword_validation
                repaired_keyword_counts = length_repair.get("keywordCounts")
                if isinstance(repaired_keyword_counts, dict) and repaired_keyword_counts:
                    keyword_counts = repaired_keyword_counts
                logger.info(
                    "분량 자동 보정 완료: %s자 -> %s자",
                    length_repair.get("before"),
                    length_repair.get("after"),
                )
            else:
                logger.info("분량 자동 보정 결과 미적용(stage=length_repair)")

    if word_count < min_required_chars:
        _append_quality_warning(
            quality_warnings,
            f"분량 권장치 미달 ({word_count}자 < {min_required_chars}자)",
        )
        logger.warning(
            "Soft gate - length below recommended threshold: actual=%s, min=%s",
            word_count,
            min_required_chars,
        )
    keyword_gate_ok, keyword_gate_msg = _validate_keyword_gate(keyword_validation, user_keywords)
    if not keyword_gate_ok:
        logger.info("키워드 자동 보정 시작: %s", keyword_gate_msg)
        repaired = _repair_keyword_gate_once(
            content=generated_content,
            title_text=generated_title,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            body_min_overrides=body_min_overrides,
        )
        candidate_content = str(repaired.get("content") or generated_content)
        applied = bool(repaired.get("edited")) and _apply_content_repair("keyword_repair", candidate_content)
        keyword_repair_applied = applied
        if applied:
            keyword_validation = _safe_dict(repaired.get("keywordValidation"))
            repaired_counts = repaired.get("keywordCounts")
            keyword_counts = repaired_counts if isinstance(repaired_counts, dict) else keyword_counts
            logger.info(
                "키워드 자동 보정 완료: edited=%s, reductions=%s, new_word_count=%s",
                bool(repaired.get("edited")),
                repaired.get("reductions"),
                word_count,
            )
        else:
            logger.info(
                "키워드 자동 보정 결과 미적용(stage=keyword_repair, edited=%s)",
                bool(repaired.get("edited")),
            )
        keyword_gate_ok, keyword_gate_msg = _validate_keyword_gate(keyword_validation, user_keywords)

    if not keyword_gate_ok:
        _append_quality_warning(
            quality_warnings,
            f"키워드 권장 기준 미충족: {keyword_gate_msg}",
        )
        logger.warning("Soft gate - keyword criteria not satisfied: %s", keyword_gate_msg)

    # 최종 반복 품질 게이트: 반복 이슈는 우선 자동 보정하고 경고로 남긴다.
    heuristic_result = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
    )
    repetition_issues = _extract_repetition_gate_issues(heuristic_result)
    if repetition_issues:
        repetition_fix = enforce_repetition_requirements(generated_content)
        if repetition_fix.get("edited"):
            candidate_content = str(repetition_fix.get("content") or generated_content)
            if _apply_content_repair("repetition_rule_repair", candidate_content):
                repetition_rule_repair_applied = True
                logger.info(
                    "반복 품질 자동 보정 적용: actions=%s, new_word_count=%s",
                    repetition_fix.get("actions"),
                    word_count,
                )

                post_fix_keyword_result = validate_keyword_insertion(
                    generated_content,
                    user_keywords,
                    auto_keywords,
                    target_word_count,
                    title_text=generated_title,
                    body_min_overrides=body_min_overrides,
                )
                keyword_validation = build_keyword_validation(post_fix_keyword_result)
                post_fix_keyword_gate_ok, post_fix_keyword_gate_msg = _validate_keyword_gate(
                    keyword_validation,
                    user_keywords,
                )
                if not post_fix_keyword_gate_ok:
                    keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                    )
                    keyword_candidate = str(keyword_repair.get("content") or generated_content)
                    keyword_applied = bool(keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_repetition",
                        keyword_candidate,
                    )
                    if keyword_applied:
                        keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
                        repaired_counts = keyword_repair.get("keywordCounts")
                        keyword_counts = repaired_counts if isinstance(repaired_counts, dict) else keyword_counts
                        post_fix_keyword_gate_ok, post_fix_keyword_gate_msg = _validate_keyword_gate(
                            keyword_validation,
                            user_keywords,
                        )
                    if not post_fix_keyword_gate_ok:
                        _append_quality_warning(
                            quality_warnings,
                            f"키워드 권장 기준 미충족: {post_fix_keyword_gate_msg}",
                        )
                        logger.warning(
                            "Soft gate - keyword criteria still not satisfied after repetition fix: %s",
                            post_fix_keyword_gate_msg,
                        )

                heuristic_result = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                )
                repetition_issues = _extract_repetition_gate_issues(heuristic_result)
            else:
                logger.info("반복 품질 자동 보정 결과 미적용(stage=repetition_rule_repair)")

        if repetition_issues:
            issue_text = "; ".join(repetition_issues[:2])
            logger.info("반복 품질 LLM 자동 보정 시작: %s", issue_text)
            repetition_llm_fix = _recover_repetition_issues_once(
                content=generated_content,
                title=generated_title,
                topic=topic,
                repetition_issues=repetition_issues,
                min_required_chars=min_required_chars,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                body_min_overrides=body_min_overrides,
            )
            if repetition_llm_fix.get("edited"):
                candidate_content = str(repetition_llm_fix.get("content") or generated_content)
                if _apply_content_repair("repetition_llm_repair", candidate_content):
                    repaired_keyword_validation = repetition_llm_fix.get("keywordValidation")
                    if isinstance(repaired_keyword_validation, dict) and repaired_keyword_validation:
                        keyword_validation = repaired_keyword_validation
                    repaired_keyword_counts = repetition_llm_fix.get("keywordCounts")
                    if isinstance(repaired_keyword_counts, dict) and repaired_keyword_counts:
                        keyword_counts = repaired_keyword_counts
                    repetition_llm_repair_applied = True
                    logger.info(
                        "반복 품질 LLM 자동 보정 완료: %s자 -> %s자",
                        repetition_llm_fix.get("before"),
                        repetition_llm_fix.get("after"),
                    )

                    heuristic_result = run_heuristic_validation_sync(
                        generated_content,
                        status_for_validation,
                        generated_title,
                    )
                    repetition_issues = _extract_repetition_gate_issues(heuristic_result)
                else:
                    logger.info("반복 품질 LLM 자동 보정 결과 미적용(stage=repetition_llm_repair)")

        if repetition_issues:
            issue_text = "; ".join(repetition_issues[:2])
            _append_quality_warning(
                quality_warnings,
                f"반복 품질 권장 기준 미충족: {issue_text}",
            )
            logger.warning("Soft gate - repetition criteria not satisfied: %s", issue_text)

    # 기준 미충족 시 EditorAgent가 1회 교정하도록 한다.
    speaker_gate["checked"] = True
    initial_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    speaker_gate["initialIssues"] = initial_speaker_issues
    initial_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
    role_gate["initialIssues"] = initial_role_issues

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    integrity_issues = _detect_integrity_gate_issues(generated_content)
    speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    role_issues = _extract_role_consistency_issues(generated_content, role_facts)
    pre_editor_extra_issues = [*integrity_issues, *speaker_issues, *role_issues]
    if pre_editor_extra_issues:
        heuristic_issues = list(final_heuristic.get("issues") or [])
        for issue in pre_editor_extra_issues:
            tagged = f"⚠️ 무결성 점검: {issue}"
            if tagged not in heuristic_issues:
                heuristic_issues.append(tagged)
        final_heuristic["issues"] = heuristic_issues

    editor_should_run = bool(legal_issues or pre_editor_extra_issues) or editor_polish_enabled
    editor_purpose = "repair" if (legal_issues or pre_editor_extra_issues) else "polish"
    editor_auto_repair = {
        "attempted": False,
        "applied": False,
        "purpose": editor_purpose,
        "summary": [],
        "error": None,
    }
    editor_second_pass = {
        "attempted": False,
        "applied": False,
        "summary": [],
        "error": None,
    }
    last_mile_postprocess_applied = False
    if editor_should_run:
        editor_auto_repair["attempted"] = True
        editor_fix = _run_editor_repair_once(
            content=generated_content,
            title=generated_title,
            full_name=full_name,
            status=status_for_validation,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            validation_result=final_heuristic,
            keyword_validation=keyword_validation,
            extra_issues=pre_editor_extra_issues,
            purpose=editor_purpose,
        )
        editor_auto_repair["error"] = editor_fix.get("error")
        summary = editor_fix.get("editSummary")
        if isinstance(summary, list):
            editor_auto_repair["summary"] = [str(item).strip() for item in summary if str(item).strip()]

        if editor_fix.get("edited"):
            editor_candidate_content = str(editor_fix.get("content") or generated_content)
            if _apply_content_repair("editor_auto_repair", editor_candidate_content):
                editor_candidate_title = str(editor_fix.get("title") or generated_title).strip() or generated_title
                guarded_title, guard_info = _guard_title_after_editor(
                    candidate_title=editor_candidate_title,
                    previous_title=title_last_valid,
                    topic=topic,
                    content=generated_content,
                    user_keywords=user_keywords,
                    full_name=full_name,
                    category=category,
                    status=status_for_validation,
                    context_analysis=context_analysis_for_title,
                )
                guard_info["phase"] = "editor_auto_repair"
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("source") == "candidate":
                    title_last_valid = generated_title
                elif guard_info.get("source") != "candidate":
                    logger.info(
                        "Title guard replaced editor title (phase=%s, source=%s, reason=%s)",
                        guard_info.get("phase"),
                        guard_info.get("source"),
                        guard_info.get("reason"),
                    )
                editor_auto_repair["applied"] = True
                logger.info("EditorAgent auto-repair applied before final blocker check")

                post_editor_keyword_result = validate_keyword_insertion(
                    generated_content,
                    user_keywords,
                    auto_keywords,
                    target_word_count,
                    title_text=generated_title,
                    body_min_overrides=body_min_overrides,
                )
                keyword_validation = build_keyword_validation(post_editor_keyword_result)
                post_editor_keyword_gate_ok, _ = _validate_keyword_gate(
                    keyword_validation,
                    user_keywords,
                )
                if not post_editor_keyword_gate_ok:
                    editor_keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                    )
                    keyword_candidate = str(editor_keyword_repair.get("content") or generated_content)
                    keyword_applied = bool(editor_keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_editor",
                        keyword_candidate,
                    )
                    if keyword_applied:
                        keyword_validation = _safe_dict(editor_keyword_repair.get("keywordValidation"))
                        repaired_counts = editor_keyword_repair.get("keywordCounts")
                        if isinstance(repaired_counts, dict):
                            keyword_counts = repaired_counts
                        editor_keyword_repair_applied = True
                        logger.info(
                            "Post-editor keyword auto-repair applied: edited=%s",
                            bool(editor_keyword_repair.get("edited")),
                        )

                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.info("EditorAgent 자동 보정 결과 미적용(stage=editor_auto_repair)")

    # Editor 이후에는 마지막 후처리(cleanup/finalize)를 다시 태운다.
    before_postprocess_word_count = word_count
    postprocess_result = _apply_last_mile_postprocess(
        content=generated_content,
        title_text=generated_title,
        target_word_count=target_word_count,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        body_min_overrides=body_min_overrides,
        output_options=output_format_options,
        fallback_keyword_validation=keyword_validation,
        fallback_keyword_counts=keyword_counts,
    )
    generated_content = str(postprocess_result.get("content") or generated_content)
    postprocess_meta = _safe_dict(postprocess_result.get("meta"))
    if postprocess_meta:
        content_meta = postprocess_meta
    keyword_validation = _safe_dict(postprocess_result.get("keywordValidation"))
    processed_keyword_counts = postprocess_result.get("keywordCounts")
    if isinstance(processed_keyword_counts, dict):
        keyword_counts = processed_keyword_counts
    word_count = _to_int(postprocess_result.get("wordCount"), _count_chars_no_space(generated_content))
    if postprocess_result.get("edited"):
        last_mile_postprocess_applied = True
        logger.info(
            "Post-editor cleanup/finalize reapplied: %s -> %s chars",
            before_postprocess_word_count,
            word_count,
        )

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    residual_repetition_issues = _extract_repetition_gate_issues(final_heuristic)
    residual_integrity_issues = _detect_integrity_gate_issues(generated_content)
    residual_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    residual_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
    residual_extra_issues = [*residual_integrity_issues, *residual_speaker_issues, *residual_role_issues]
    if editor_second_pass_enabled and (residual_repetition_issues or residual_extra_issues) and not legal_issues:
        editor_second_pass["attempted"] = True
        logger.info(
            "EditorAgent second-pass repair triggered: %s",
            "; ".join([*(residual_repetition_issues[:2]), *(residual_extra_issues[:2])]),
        )
        second_editor_fix = _run_editor_repair_once(
            content=generated_content,
            title=generated_title,
            full_name=full_name,
            status=status_for_validation,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            validation_result=final_heuristic,
            keyword_validation=keyword_validation,
            extra_issues=residual_extra_issues,
            purpose="repair",
        )
        editor_second_pass["error"] = second_editor_fix.get("error")
        second_summary = second_editor_fix.get("editSummary")
        if isinstance(second_summary, list):
            editor_second_pass["summary"] = [
                str(item).strip()
                for item in second_summary
                if str(item).strip()
            ]

        if second_editor_fix.get("edited"):
            second_editor_candidate_content = str(second_editor_fix.get("content") or generated_content)
            if _apply_content_repair("editor_second_pass", second_editor_candidate_content):
                second_editor_candidate_title = str(second_editor_fix.get("title") or generated_title).strip() or generated_title
                guarded_title, guard_info = _guard_title_after_editor(
                    candidate_title=second_editor_candidate_title,
                    previous_title=title_last_valid,
                    topic=topic,
                    content=generated_content,
                    user_keywords=user_keywords,
                    full_name=full_name,
                    category=category,
                    status=status_for_validation,
                    context_analysis=context_analysis_for_title,
                )
                guard_info["phase"] = "editor_second_pass"
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("source") == "candidate":
                    title_last_valid = generated_title
                elif guard_info.get("source") != "candidate":
                    logger.info(
                        "Title guard replaced second-pass editor title (source=%s, reason=%s)",
                        guard_info.get("source"),
                        guard_info.get("reason"),
                    )
                editor_second_pass["applied"] = True
                logger.info("EditorAgent second-pass repair applied")

                second_postprocess = _apply_last_mile_postprocess(
                    content=generated_content,
                    title_text=generated_title,
                    target_word_count=target_word_count,
                    user_keywords=user_keywords,
                    auto_keywords=auto_keywords,
                    body_min_overrides=body_min_overrides,
                    output_options=output_format_options,
                    fallback_keyword_validation=keyword_validation,
                    fallback_keyword_counts=keyword_counts,
                )
                generated_content = str(second_postprocess.get("content") or generated_content)
                second_post_meta = _safe_dict(second_postprocess.get("meta"))
                if second_post_meta:
                    content_meta = second_post_meta
                keyword_validation = _safe_dict(second_postprocess.get("keywordValidation"))
                second_keyword_counts = second_postprocess.get("keywordCounts")
                if isinstance(second_keyword_counts, dict):
                    keyword_counts = second_keyword_counts
                word_count = _to_int(second_postprocess.get("wordCount"), _count_chars_no_space(generated_content))
                if second_postprocess.get("edited"):
                    last_mile_postprocess_applied = True
                    logger.info("Post-second-pass cleanup/finalize reapplied")

                second_keyword_gate_ok, _ = _validate_keyword_gate(keyword_validation, user_keywords)
                if not second_keyword_gate_ok:
                    second_keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                    )
                    second_keyword_candidate = str(second_keyword_repair.get("content") or generated_content)
                    second_keyword_applied = bool(second_keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_second_editor",
                        second_keyword_candidate,
                    )
                    if second_keyword_applied:
                        keyword_validation = _safe_dict(second_keyword_repair.get("keywordValidation"))
                        second_repaired_counts = second_keyword_repair.get("keywordCounts")
                        if isinstance(second_repaired_counts, dict):
                            keyword_counts = second_repaired_counts
                        editor_keyword_repair_applied = True
                        logger.info(
                            "Post-second-pass keyword auto-repair applied: edited=%s",
                            bool(second_keyword_repair.get("edited")),
                        )

                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.info("EditorAgent second-pass 보정 결과 미적용(stage=editor_second_pass)")

    date_year_hint = " ".join(
        item.strip()
        for item in [event_date_hint_for_guard, topic]
        if str(item or "").strip()
    ).strip()
    title_date_repair = repair_date_weekday_pairs(
        generated_title,
        year_hint=(date_year_hint or None),
    )
    title_repaired_text = _normalize_title_surface_local(
        str(title_date_repair.get("text") or generated_title)
    )
    if title_repaired_text:
        generated_title = title_repaired_text

    content_date_repair = repair_date_weekday_pairs(
        generated_content,
        year_hint=(date_year_hint or None),
    )
    generated_content = str(content_date_repair.get("text") or generated_content)
    if content_date_repair.get("edited"):
        word_count = _count_chars_no_space(generated_content)

    title_validation = (
        title_date_repair.get("validation")
        if isinstance(title_date_repair.get("validation"), dict)
        else {}
    )
    content_validation = (
        content_date_repair.get("validation")
        if isinstance(content_date_repair.get("validation"), dict)
        else {}
    )
    date_weekday_guard = {
        "applied": bool(title_date_repair.get("edited") or content_date_repair.get("edited")),
        "yearHint": date_year_hint,
        "title": {
            "edited": bool(title_date_repair.get("edited")),
            "changes": title_date_repair.get("changes") if isinstance(title_date_repair.get("changes"), list) else [],
            "issues": title_validation.get("issues") if isinstance(title_validation.get("issues"), list) else [],
        },
        "content": {
            "edited": bool(content_date_repair.get("edited")),
            "changes": content_date_repair.get("changes") if isinstance(content_date_repair.get("changes"), list) else [],
            "issues": content_validation.get("issues") if isinstance(content_validation.get("issues"), list) else [],
        },
    }
    if date_weekday_guard.get("applied"):
        logger.info(
            "Date-weekday guard applied: title=%s content=%s",
            bool(date_weekday_guard.get("title", {}).get("edited")),
            bool(date_weekday_guard.get("content", {}).get("edited")),
        )

    title_date_repair = repair_date_weekday_pairs(
        title_last_valid,
        year_hint=(date_year_hint or None),
    )
    title_for_guard = _normalize_title_surface_local(
        str(title_date_repair.get("text") or title_last_valid)
    ) or title_last_valid

    final_guarded_title, final_title_guard = _guard_title_after_editor(
        candidate_title=generated_title,
        previous_title=title_for_guard,
        topic=topic,
        content=generated_content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=status_for_validation,
        context_analysis=context_analysis_for_title,
    )
    final_title_guard["phase"] = "final_output"
    title_guard_trace.append(final_title_guard)
    generated_title = final_guarded_title
    if final_title_guard.get("source") == "candidate":
        title_last_valid = generated_title
    elif final_title_guard.get("source") != "candidate":
        logger.info(
            "Title guard adjusted final output title (source=%s, reason=%s)",
            final_title_guard.get("source"),
            final_title_guard.get("reason"),
        )

    # 최종 반환 직전 따옴표 표면을 ASCII(U+0022)로 통일한다.
    generated_title = normalize_ascii_double_quotes(generated_title)
    generated_content = normalize_ascii_double_quotes(generated_content)
    generated_title = normalize_book_title_notation(
        generated_title,
        topic=topic,
        context_analysis=context_analysis_for_title,
        full_name=full_name,
    )
    generated_title = _normalize_title_surface_local(generated_title) or generated_title
    generated_content = normalize_book_title_notation(
        generated_content,
        topic=topic,
        context_analysis=context_analysis_for_title,
        full_name=full_name,
    )

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    if final_speaker_issues:
        speaker_gate["repairAttempted"] = True
        final_speaker_repair = _repair_speaker_consistency_once(generated_content, full_name)
        repair_candidate = str(final_speaker_repair.get("content") or generated_content).strip()
        if repair_candidate and repair_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(generated_content, repair_candidate)
            if not corrupted:
                generated_content = repair_candidate
                word_count = _count_chars_no_space(generated_content)
                speaker_gate["repairApplied"] = True
                repair_patterns = list(speaker_gate.get("repairPatterns") or [])
                for pattern in final_speaker_repair.get("appliedPatterns") or []:
                    if pattern not in repair_patterns:
                        repair_patterns.append(pattern)
                speaker_gate["repairPatterns"] = repair_patterns
                final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.warning("Final speaker repair skipped due to corruption risk: %s", reason)
    speaker_gate["finalIssues"] = final_speaker_issues

    final_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
    if final_role_issues:
        role_gate["repairAttempted"] = True
        final_role_repair = _repair_role_consistency_once(generated_content, role_facts)
        role_repair_candidate = str(final_role_repair.get("content") or generated_content).strip()
        if role_repair_candidate and role_repair_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(generated_content, role_repair_candidate)
            if not corrupted:
                generated_content = role_repair_candidate
                word_count = _count_chars_no_space(generated_content)
                role_gate["repairApplied"] = True
                role_gate["replacements"] = list(final_role_repair.get("replacements") or [])
                final_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.warning("Final role repair skipped due to corruption risk: %s", reason)
    role_gate["finalIssues"] = final_role_issues

    if poll_fact_guard.get("enabled"):
        title_poll_result = enforce_poll_fact_consistency(
            generated_title,
            poll_fact_table,
            full_name=full_name,
            field="title",
            allow_repair=True,
        )
        repaired_title = _normalize_title_surface_local(str(title_poll_result.get("text") or generated_title))
        if repaired_title:
            generated_title = repaired_title
        poll_fact_guard["title"] = {
            "checked": int(title_poll_result.get("checked") or 0),
            "edited": bool(title_poll_result.get("edited")),
            "blockingIssues": list(title_poll_result.get("blockingIssues") or []),
            "repairs": list(title_poll_result.get("repairs") or []),
        }
        title_poll_issues = list(title_poll_result.get("blockingIssues") or [])
        if title_poll_issues:
            raise ApiError("internal", f"제목 사실관계 불일치: {title_poll_issues[0]}")

        content_poll_result = enforce_poll_fact_consistency(
            generated_content,
            poll_fact_table,
            full_name=full_name,
            field="content",
            allow_repair=True,
        )
        content_poll_text = str(content_poll_result.get("text") or generated_content).strip()
        if content_poll_text and content_poll_text != generated_content:
            generated_content = content_poll_text
            word_count = _count_chars_no_space(generated_content)
        poll_fact_guard["content"] = {
            "checked": int(content_poll_result.get("checked") or 0),
            "edited": bool(content_poll_result.get("edited")),
            "blockingIssues": list(content_poll_result.get("blockingIssues") or []),
            "warnings": list(content_poll_result.get("warnings") or []),
            "repairs": list(content_poll_result.get("repairs") or []),
        }
        content_poll_issues = list(content_poll_result.get("blockingIssues") or [])
        if content_poll_issues:
            raise ApiError("internal", f"본문 사실관계 불일치: {content_poll_issues[0]}")

        final_heuristic = run_heuristic_validation_sync(
            generated_content,
            status_for_validation,
            generated_title,
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)

    honorific_repair = _normalize_lawmaker_honorifics_once(
        generated_content,
        role_facts,
        full_name,
    )
    honorific_candidate = str(honorific_repair.get("content") or generated_content).strip()
    if honorific_candidate and honorific_candidate != generated_content:
        generated_content = honorific_candidate
        word_count = _count_chars_no_space(generated_content)
        role_gate["honorificRepairApplied"] = True
        role_gate["honorificReplacements"] = list(honorific_repair.get("replacements") or [])
        final_heuristic = run_heuristic_validation_sync(
            generated_content,
            status_for_validation,
            generated_title,
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)

    final_sentence_polish["attempted"] = True
    sentence_polish_result = _apply_final_sentence_polish_once(generated_content)
    sentence_polish_candidate = str(sentence_polish_result.get("content") or generated_content).strip()
    final_sentence_polish["actions"] = list(sentence_polish_result.get("actions") or [])
    if sentence_polish_candidate and sentence_polish_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, sentence_polish_candidate)
        if not corrupted:
            generated_content = sentence_polish_candidate
            word_count = _count_chars_no_space(generated_content)
            final_sentence_polish["applied"] = True
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
        else:
            final_sentence_polish["skippedReason"] = str(reason or "corruption-risk")
            logger.warning("Final sentence polish skipped due to corruption risk: %s", reason)

    subheading_entity_gate["attempted"] = True
    known_person_names = _collect_known_person_names(
        full_name=full_name,
        role_facts=role_facts,
        user_keywords=user_keywords,
        poll_fact_table=poll_fact_table,
    )
    h2_entity_repair = _repair_subheading_entity_consistency_once(
        generated_content,
        known_person_names,
    )
    h2_entity_candidate = str(h2_entity_repair.get("content") or generated_content).strip()
    subheading_entity_gate["replacements"] = list(h2_entity_repair.get("replacements") or [])
    if h2_entity_candidate and h2_entity_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, h2_entity_candidate)
        if not corrupted:
            generated_content = h2_entity_candidate
            word_count = _count_chars_no_space(generated_content)
            subheading_entity_gate["applied"] = True
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
        else:
            subheading_entity_gate["skippedReason"] = str(reason or "corruption-risk")
            logger.warning("Subheading entity repair skipped due to corruption risk: %s", reason)

    final_integrity_issues = _detect_integrity_gate_issues(generated_content)
    final_blocking_integrity_issues = _extract_blocking_integrity_issues(final_integrity_issues)
    if final_blocking_integrity_issues and not legal_issues:
        max_integrity_editor_passes = 2
        for pass_no in range(1, max_integrity_editor_passes + 1):
            if not final_blocking_integrity_issues or legal_issues:
                break

            integrity_editor_repair["attempted"] = int(integrity_editor_repair.get("attempted") or 0) + 1
            logger.info(
                "Final integrity editor repair triggered(pass=%s): %s",
                pass_no,
                "; ".join(final_blocking_integrity_issues[:2]),
            )
            integrity_fix = _run_editor_repair_once(
                content=generated_content,
                title=generated_title,
                full_name=full_name,
                status=status_for_validation,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                validation_result=final_heuristic,
                keyword_validation=keyword_validation,
                extra_issues=final_blocking_integrity_issues,
                purpose="polish",
            )
            integrity_editor_repair["error"] = integrity_fix.get("error")
            summary_items = integrity_fix.get("editSummary")
            if isinstance(summary_items, list):
                merged_summary = list(integrity_editor_repair.get("summary") or [])
                for item in summary_items:
                    text_item = str(item).strip()
                    if text_item and text_item not in merged_summary:
                        merged_summary.append(text_item)
                integrity_editor_repair["summary"] = merged_summary

            if not integrity_fix.get("edited"):
                logger.info("Final integrity editor repair produced no changes(pass=%s)", pass_no)
                break

            integrity_candidate_content = str(integrity_fix.get("content") or generated_content)
            if not _apply_content_repair(f"integrity_editor_pass_{pass_no}", integrity_candidate_content):
                logger.info("Final integrity editor repair result skipped(pass=%s)", pass_no)
                break

            integrity_editor_repair["applied"] = int(integrity_editor_repair.get("applied") or 0) + 1
            integrity_candidate_title = str(integrity_fix.get("title") or generated_title).strip() or generated_title
            guarded_title, guard_info = _guard_title_after_editor(
                candidate_title=integrity_candidate_title,
                previous_title=title_last_valid,
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
            )
            guard_info["phase"] = f"integrity_editor_pass_{pass_no}"
            title_guard_trace.append(guard_info)
            generated_title = guarded_title
            if guard_info.get("source") == "candidate":
                title_last_valid = generated_title

            integrity_postprocess = _apply_last_mile_postprocess(
                content=generated_content,
                title_text=generated_title,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                body_min_overrides=body_min_overrides,
                output_options=output_format_options,
                fallback_keyword_validation=keyword_validation,
                fallback_keyword_counts=keyword_counts,
            )
            generated_content = str(integrity_postprocess.get("content") or generated_content).strip()
            integrity_post_meta = _safe_dict(integrity_postprocess.get("meta"))
            if integrity_post_meta:
                content_meta = integrity_post_meta
            keyword_validation = _safe_dict(integrity_postprocess.get("keywordValidation"))
            integrity_keyword_counts = integrity_postprocess.get("keywordCounts")
            if isinstance(integrity_keyword_counts, dict):
                keyword_counts = integrity_keyword_counts
            word_count = _to_int(integrity_postprocess.get("wordCount"), _count_chars_no_space(generated_content))

            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(generated_content, role_facts)
            final_integrity_issues = _detect_integrity_gate_issues(generated_content)
            final_blocking_integrity_issues = _extract_blocking_integrity_issues(final_integrity_issues)

    speaker_gate["finalIssues"] = final_speaker_issues
    role_gate["finalIssues"] = final_role_issues

    # 최종 경고는 최종 산출물 기준으로 다시 계산한다.
    quality_warnings = []
    if date_weekday_guard.get("applied"):
        _append_quality_warning(
            quality_warnings,
            "날짜-요일 불일치가 감지되어 자동 보정되었습니다.",
        )
    if final_title_guard.get("source") != "candidate":
        _append_quality_warning(
            quality_warnings,
            "제목 규칙 보정을 위해 자동 롤백이 적용되었습니다.",
        )
    poll_content_warnings = list((_safe_dict(poll_fact_guard.get("content")).get("warnings") or []))
    if poll_content_warnings:
        _append_quality_warning(
            quality_warnings,
            f"여론조사 사실관계 경고: {'; '.join(poll_content_warnings[:2])}",
        )
    if word_count < min_required_chars:
        _append_quality_warning(
            quality_warnings,
            f"분량 권장치 미달 ({word_count}자 < {min_required_chars}자)",
        )
    final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(keyword_validation, user_keywords)
    if not final_keyword_gate_ok:
        _append_quality_warning(
            quality_warnings,
            f"키워드 권장 기준 미충족: {final_keyword_gate_msg}",
        )
    final_secondary_keyword_issues = _collect_secondary_keyword_soft_issues(keyword_validation, user_keywords)
    if final_secondary_keyword_issues:
        _append_quality_warning(
            quality_warnings,
            f"보조 키워드 권장 기준 미충족: {'; '.join(final_secondary_keyword_issues[:2])}",
        )
    final_repetition_issues = _extract_repetition_gate_issues(final_heuristic)
    if final_repetition_issues:
        _append_quality_warning(
            quality_warnings,
            f"반복 품질 권장 기준 미충족: {'; '.join(final_repetition_issues[:2])}",
        )
    if final_integrity_issues:
        _append_quality_warning(
            quality_warnings,
            f"문장 무결성 점검 경고: {'; '.join(final_integrity_issues[:2])}",
        )
    if final_speaker_issues:
        _append_quality_warning(
            quality_warnings,
            f"화자 정체성 점검 경고: {'; '.join(final_speaker_issues[:2])}",
        )
    if final_role_issues:
        _append_quality_warning(
            quality_warnings,
            f"직함 정합성 점검 경고: {'; '.join(final_role_issues[:2])}",
        )
    if content_repair_rollbacks:
        _append_quality_warning(
            quality_warnings,
            "문장 파손 위험이 감지된 일부 자동 보정은 롤백되었습니다.",
        )
    if bool(content_meta.get("metaRemoved") is True):
        _append_quality_warning(
            quality_warnings,
            "본문에 섞인 메타 블록(조사개요/카테고리/검색어 집계 등)을 분리했습니다.",
        )
    if final_sentence_polish.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "최종 문장 윤문 안전망이 적용되었습니다.",
        )
    if subheading_entity_gate.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "소제목-본문 인물 불일치를 자동 보정했습니다.",
        )
    if speaker_gate.get("repairApplied") is True:
        _append_quality_warning(
            quality_warnings,
            "화자 정체성 불일치 문장을 자동 보정했습니다.",
        )
    if role_gate.get("repairApplied") is True:
        _append_quality_warning(
            quality_warnings,
            "인물 직함 불일치 문장을 입력 근거 기준으로 자동 보정했습니다.",
        )
    if int(integrity_editor_repair.get("applied") or 0) > 0:
        _append_quality_warning(
            quality_warnings,
            "최종 무결성 게이트에서 문장 윤문 재검사가 자동 적용되었습니다.",
        )

    # 하드 차단: 화자 정체성 불일치, 문장 무결성 치명 오류, 선거법 위반.
    if final_speaker_issues:
        speaker_gate["blocked"] = True
        issue_text = "; ".join(final_speaker_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked reason=speaker_identity warnings=%s repairs=%s",
            len(quality_warnings),
            int(speaker_gate.get("repairApplied") is True),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:SPEAKER_IDENTITY] {issue_text}",
        )

    if final_blocking_integrity_issues:
        issue_text = "; ".join(final_blocking_integrity_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked reason=integrity warnings=%s repairs=%s",
            len(quality_warnings),
            int(integrity_editor_repair.get("applied") or 0),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:INTEGRITY] {issue_text}",
        )

    if legal_issues:
        issue_text = "; ".join(legal_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked first_pass=%s blockers=%s warnings=%s repairs=%s",
            int(first_pass_passed),
            len(legal_issues),
            len(quality_warnings),
            int(
                any(
                    [
                        length_repair_applied,
                        keyword_repair_applied,
                        repetition_rule_repair_applied,
                        repetition_llm_repair_applied,
                        bool(editor_auto_repair.get("applied")),
                        bool(editor_second_pass.get("applied")),
                        int(integrity_editor_repair.get("applied") or 0) > 0,
                        editor_keyword_repair_applied,
                        last_mile_postprocess_applied,
                    ]
                )
            ),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:ELECTION_LAW] {issue_text}",
        )

    # 생성 성공 후 attempts / 사용량 업데이트
    session = increment_session_attempts(uid, session, is_admin=is_admin, is_tester=is_tester)
    session = _safe_dict(session)
    _apply_usage_updates_after_success(uid, is_admin=is_admin, is_tester=is_tester, session=session)

    progress.step_validating()
    progress.step_finalizing()
    progress.complete()

    generated_at = datetime.utcnow().isoformat() + "Z"
    now_ms = int(time.time() * 1000)
    source_input = str(
        data.get("sourceInput")
        or data.get("sourceContent")
        or data.get("originalContent")
        or data.get("inputContent")
        or data.get("rawContent")
        or data.get("prompt")
        or data.get("topic")
        or ""
    ).strip()
    source_type = str(
        data.get("sourceType")
        or data.get("inputType")
        or data.get("contentType")
        or data.get("writingSource")
        or "blog_draft"
    ).strip()
    draft_data = {
        "id": f"draft_{now_ms}",
        "title": generated_title,
        "content": generated_content,
        "wordCount": word_count,
        "category": category,
        "subCategory": str(data.get("subCategory") or ""),
        "keywords": data.get("keywords") or "",
        "sourceInput": source_input,
        "sourceType": source_type,
        "generatedAt": generated_at,
    }

    attempts_after = _to_int(session.get("attempts"), attempts + 1)
    can_regenerate = attempts_after < max_attempts

    message = "원고가 성공적으로 생성되었습니다"
    if daily_limit_warning:
        message += (
            "\n\n⚠️ 하루 3회 이상 원고를 생성하셨습니다. 네이버 블로그 정책상 과도한 발행은 스팸으로 "
            "분류될 수 있으므로, 반드시 마지막 포스팅으로부터 3시간 경과 후 발행해 주세요"
        )
    if quality_warnings:
        message += "\n\n⚠️ 자동 품질 보정 후에도 일부 권장 기준이 남아 있으니 발행 전 확인해 주세요."
    if can_regenerate:
        message += f"\n\n💡 마음에 들지 않으시면 재생성을 {max_attempts - attempts_after}회 더 하실 수 있습니다."

    logger.info(
        "QUALITY_METRIC generate_posts outcome=success first_pass=%s warnings=%s repairs=%s editor_applied=%s",
        int(first_pass_passed),
        len(quality_warnings),
        int(
            any(
                [
                    length_repair_applied,
                    keyword_repair_applied,
                    repetition_rule_repair_applied,
                    repetition_llm_repair_applied,
                    bool(editor_auto_repair.get("applied")),
                    bool(editor_second_pass.get("applied")),
                    editor_keyword_repair_applied,
                    last_mile_postprocess_applied,
                ]
            )
        ),
        bool(editor_auto_repair.get("applied")),
    )

    return {
        "success": True,
        "message": message,
        "dailyLimitWarning": daily_limit_warning,
        "drafts": draft_data,
        "sessionId": session.get("sessionId"),
        "attempts": attempts_after,
        "maxAttempts": max_attempts,
        "canRegenerate": can_regenerate,
        "metadata": {
            "generatedAt": generated_at,
            "userId": uid,
            "processingTime": started_ms,
            "multiAgent": {
                "enabled": True,
                "pipeline": "python-step-functions",
                "compliancePassed": compliance_passed,
                "complianceIssues": 0,
                "seoPassed": seo_passed,
                "keywords": pipeline_result.get("keywords") or user_keywords,
                "keywordValidation": keyword_validation or None,
                "duration": None,
                "partial": bool(pipeline_result.get("partial") is True),
                "partialReason": pipeline_result.get("partialReason"),
                "timeoutMs": None,
                "agentsCompleted": pipeline_result.get("agentsCompleted") or [],
                "lastAgent": pipeline_result.get("lastAgent"),
                "appliedStrategy": writing_method,
                "keywordCounts": keyword_counts,
                "wordCount": word_count,
                "qualityGate": {
                    "mode": "soft-first",
                    "hardBlockers": ["SPEAKER_IDENTITY", "INTEGRITY", "ELECTION_LAW"],
                    "warnings": quality_warnings,
                    "warningCount": len(quality_warnings),
                    "titleGuard": {
                        "applied": any(
                            str(item.get("source") or "") != "candidate"
                            for item in title_guard_trace
                            if isinstance(item, dict)
                        ),
                        "trace": title_guard_trace,
                    },
                    "dateWeekdayGuard": date_weekday_guard,
                    "editorPolishEnabled": editor_polish_enabled,
                    "firstPass": {
                        "passed": first_pass_passed,
                        "failureReasons": first_pass_failure_reasons,
                        "signals": {
                            "lengthOk": initial_length_ok,
                            "keywordOk": initial_keyword_gate_ok,
                            "repetitionIssueCount": len(initial_repetition_issues),
                            "legalIssueCount": len(initial_legal_issues),
                            "keywordMessage": initial_keyword_gate_msg if not initial_keyword_gate_ok else "",
                        },
                    },
                    "repairTrace": {
                        "lengthRepairApplied": length_repair_applied,
                        "keywordRepairApplied": keyword_repair_applied,
                        "repetitionRuleRepairApplied": repetition_rule_repair_applied,
                        "repetitionLlmRepairApplied": repetition_llm_repair_applied,
                        "editorKeywordRepairApplied": editor_keyword_repair_applied,
                        "editorSecondPassApplied": bool(editor_second_pass.get("applied")),
                        "finalSentencePolishApplied": bool(final_sentence_polish.get("applied")),
                        "finalSentencePolishActions": list(final_sentence_polish.get("actions") or []),
                        "finalSentencePolishSkippedReason": str(
                            final_sentence_polish.get("skippedReason") or ""
                        ),
                        "subheadingEntityRepairApplied": bool(subheading_entity_gate.get("applied")),
                        "subheadingEntityReplacements": list(subheading_entity_gate.get("replacements") or []),
                        "subheadingEntitySkippedReason": str(
                            subheading_entity_gate.get("skippedReason") or ""
                        ),
                        "integrityEditorRepairAttempted": int(integrity_editor_repair.get("attempted") or 0),
                        "integrityEditorRepairApplied": int(integrity_editor_repair.get("applied") or 0),
                        "integrityEditorRepairError": str(integrity_editor_repair.get("error") or ""),
                        "integrityEditorRepairSummary": list(integrity_editor_repair.get("summary") or []),
                        "lastMilePostprocessApplied": last_mile_postprocess_applied,
                        "contentRepairSteps": content_repair_steps,
                        "contentRepairMaxSteps": max_content_repair_steps,
                        "contentRepairRollbacks": content_repair_rollbacks,
                    },
                    "editorAutoRepair": editor_auto_repair,
                    "editorSecondPass": editor_second_pass,
                    "speakerGate": speaker_gate,
                    "roleGate": role_gate,
                    "pollFactGuard": poll_fact_guard,
                    "contentMeta": content_meta or None,
                },
            },
            "seo": {
                "passed": seo_passed,
                "keywordValidation": keyword_validation or None,
            },
        },
    }


def handle_generate_posts(req: https_fn.CallableRequest) -> Dict[str, Any]:
    progress: Optional[ProgressTracker] = None
    try:
        data = req.data if isinstance(req.data, dict) else {}
        if isinstance(data.get("data"), dict):
            data = data["data"]
        uid = req.auth.uid if req.auth else ""
        progress_session_id = str(data.get("progressSessionId") or f"{uid}_{int(time.time() * 1000)}")
        progress = ProgressTracker(progress_session_id)
        return handle_generate_posts_call(req)
    except ApiError as exc:
        logger.warning("generatePosts 처리 실패(ApiError): %s", exc)
        if progress:
            progress.error(str(exc))
        raise https_fn.HttpsError(exc.code, str(exc)) from exc
    except Exception as exc:
        logger.exception("generatePosts 처리 실패")
        if progress:
            progress.error(str(exc))
        raise https_fn.HttpsError("internal", f"원고 생성에 실패했습니다: {exc}") from exc
