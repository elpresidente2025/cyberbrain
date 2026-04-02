
import logging
import re
from typing import Dict, Any, List, Optional

from ..base_agent import Agent
from ..common.role_keyword_policy import (
    build_role_keyword_policy,
    extract_person_role_facts_from_text,
)
from ..common.title_generation import (
    _detect_title_structural_defect,
    generate_and_validate_title,
    normalize_title_surface,
    resolve_title_purpose,
)
from ..common.title_common import (
    assess_malformed_title_surface,
    assess_title_focus_name_repetition,
    build_structured_title_candidates,
    repair_title_focus_name_repetition,
)
from ..common.title_scoring import calculate_title_quality_score

logger = logging.getLogger(__name__)

TITLE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
    },
    "required": ["title"],
}


def _is_title_compliance_failure(error: Exception) -> bool:
    message = str(error or "")
    if not message:
        return False
    markers = (
        "최소 점수",
        "말줄임표",
        "중간에 잘린",
        "비문",
        "동일 인물명",
        "제목 문장",
    )
    return any(marker in message for marker in markers)


def _normalize_topic_fallback_fragment(text: str) -> str:
    normalized = normalize_title_surface(text) or str(text or "").strip()
    if not normalized:
        return ""

    candidate = normalized
    candidate = re.sub(
        r"(?:해내겠습니다|하겠습니다|드리겠습니다|입니다|합니다|됩니다|되겠습니다)[.!?]*$",
        "",
        candidate,
    ).strip()
    candidate = re.sub(r"\s*역할을?\s+해내$", "", candidate).strip()
    candidate = re.sub(r"\s*역할을?\s*$", "", candidate).strip()
    candidate = re.sub(r"^\s*(?:앞으로도|끝까지|반드시)\s+", "", candidate).strip()
    candidate = re.sub(r"(?:으로|로|에게|에서|과|와|의|을|를|은|는|이|가)\s*$", "", candidate).strip()
    candidate = re.sub(r"\s{2,}", " ", candidate).strip(" ,.:;!?")
    return normalize_title_surface(candidate) or candidate


def _build_topic_sentence_fallback_candidates(params: Dict[str, Any]) -> List[str]:
    topic = str(params.get("topic") or "").strip()
    full_name = str(params.get("fullName") or "").strip()
    user_keywords = params.get("userKeywords") if isinstance(params.get("userKeywords"), list) else []
    primary_keyword = str(user_keywords[0] or "").strip() if user_keywords else ""

    base_topic = _normalize_topic_fallback_fragment(topic)
    if not base_topic:
        return []

    fragments: List[str] = []
    for raw_fragment in (base_topic,):
        normalized_fragment = _normalize_topic_fallback_fragment(raw_fragment)
        if normalized_fragment and normalized_fragment not in fragments:
            fragments.append(normalized_fragment)
        if "," in normalized_fragment:
            left, right = [part.strip() for part in normalized_fragment.split(",", 1)]
            for split_fragment in (right, left, f"{left} {right}".strip()):
                normalized_split = _normalize_topic_fallback_fragment(split_fragment)
                if normalized_split and normalized_split not in fragments:
                    fragments.append(normalized_split)

    prefixes: List[str] = []
    for prefix in (primary_keyword, full_name):
        normalized_prefix = str(prefix or "").strip()
        if normalized_prefix and normalized_prefix not in prefixes:
            prefixes.append(normalized_prefix)

    candidates: List[str] = []
    for fragment in fragments:
        if fragment and fragment not in candidates:
            candidates.append(fragment)
        for prefix in prefixes:
            if prefix and prefix not in fragment:
                prefixed = normalize_title_surface(f"{prefix}, {fragment}")
                if prefixed and prefixed not in candidates:
                    candidates.append(prefixed)

    return candidates[:8]


def _is_safe_fallback_candidate(title: str, params: Dict[str, Any]) -> bool:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    if not normalized_title:
        return False
    if _detect_title_structural_defect(normalized_title):
        return False
    malformed_surface = assess_malformed_title_surface(normalized_title, params)
    if not malformed_surface.get("passed", True):
        return False
    validation = assess_title_focus_name_repetition(normalized_title, params)
    return bool(validation.get("passed", True))


def _select_compliance_safe_fallback(
    params: Dict[str, Any],
    *,
    min_score: int,
    title_purpose: str,
) -> Optional[Dict[str, Any]]:
    candidate_pool: List[tuple[str, str]] = []
    seen_candidates: set[str] = set()

    def _append_candidate(raw_title: str, source: str) -> None:
        normalized_title = normalize_title_surface(raw_title) or str(raw_title or "").strip()
        if not normalized_title or normalized_title in seen_candidates:
            return
        seen_candidates.add(normalized_title)
        candidate_pool.append((normalized_title, source))

    for structured_title in build_structured_title_candidates(
        params,
        title_purpose=title_purpose,
        limit=6,
    ):
        _append_candidate(str(structured_title or ""), "structured_fallback")

    for fallback_title in _build_topic_sentence_fallback_candidates(params):
        _append_candidate(fallback_title, "topic_sentence_fallback")

    best_match: Optional[Dict[str, Any]] = None
    best_score = -1
    fallback_min_score = max(60, min_score - 10)
    for candidate_title, source in candidate_pool:
        normalized_candidate = normalize_title_surface(candidate_title) or candidate_title
        if not _is_safe_fallback_candidate(normalized_candidate, params):
            continue
        validation = assess_title_focus_name_repetition(normalized_candidate, params)
        if not validation.get("passed", True):
            repaired_candidate = repair_title_focus_name_repetition(normalized_candidate, params)
            normalized_candidate = normalize_title_surface(repaired_candidate) or normalized_candidate
            validation = assess_title_focus_name_repetition(normalized_candidate, params)
            if not validation.get("passed", True):
                continue

        score_result = calculate_title_quality_score(normalized_candidate, params)
        scored_title = normalize_title_surface(
            str(score_result.get("repairedTitle") or normalized_candidate)
        ) or normalized_candidate
        if scored_title != normalized_candidate:
            rescored_result = calculate_title_quality_score(scored_title, params)
            if int(rescored_result.get("score") or 0) >= int(score_result.get("score") or 0):
                score_result = rescored_result
                normalized_candidate = scored_title

        score = int(score_result.get("score") or 0)
        if score <= 0:
            continue

        if score > best_score:
            best_score = score
            best_match = {
                "title": normalized_candidate,
                "score": score,
                "source": source,
                "passed": bool(score_result.get("passed")),
                "suggestions": list(score_result.get("suggestions") or []),
                "breakdown": dict(score_result.get("breakdown") or {}),
            }

        if bool(score_result.get("passed")) and score >= fallback_min_score:
            return {
                "title": normalized_candidate,
                "score": score,
                "source": source,
                "passed": bool(score_result.get("passed")),
                "suggestions": list(score_result.get("suggestions") or []),
                "breakdown": dict(score_result.get("breakdown") or {}),
            }

    return (
        best_match
        if best_match
        and bool(best_match.get("passed"))
        and int(best_match.get("score") or 0) >= fallback_min_score
        else None
    )


class TitleAgent(Agent):
    def __init__(self, name: str = 'TitleAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = (options or {}).get('modelName', DEFAULT_MODEL)
        self._client = get_client()
        if not self._client:
            logger.warning("GEMINI_API_KEY not set for TitleAgent")

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        TitleAgent main process
        """
        from ..common.gemini_client import StructuredOutputError, generate_json_async

        # Extract inputs
        topic = context.get('topic', '')
        # Prefer optimized content from previous agents, otherwise use original content
        content_preview = context.get('optimizedContent') or context.get('content') or ''

        # Strip HTML for preview
        content_preview_text = re.sub(r'<[^>]*>', ' ', content_preview)
        content_preview_text = re.sub(r'\s+', ' ', content_preview_text).strip()

        user_keywords = context.get('userKeywords') or context.get('keywords') or []  # User provided keywords
        if not isinstance(user_keywords, list):
            user_keywords = []
        generated_keywords = (context.get('analysis') or {}).get('keywords', []) # SEO extracts
        context_analysis = context.get('contextAnalysis')
        if not isinstance(context_analysis, dict):
            context_analysis = {}

        author = context.get('author')
        if not isinstance(author, dict):
            author = {}
        user_profile = context.get('userProfile')
        if not isinstance(user_profile, dict):
            user_profile = {}

        full_name = str(
            author.get('name')
            or user_profile.get('name')
            or user_profile.get('displayName')
            or ''
        ).strip()
        source_texts = [
            context.get('newsDataText'),
            context.get('sourceInput'),
            context.get('sourceContent'),
            context.get('originalContent'),
        ]
        person_roles: Dict[str, str] = {}
        for text in source_texts:
            extracted = extract_person_role_facts_from_text(text)
            for name, role in extracted.items():
                if name not in person_roles:
                    person_roles[name] = role
        category = context.get('category', 'activity-report')
        status = context.get('status', 'active') # Election status
        title_scope = (context.get('config') or {}).get('titleScope', {})
        background_text = context.get('background', '')
        poll_focus_bundle = context.get('pollFocusBundle')
        if not isinstance(poll_focus_bundle, dict):
            poll_focus_bundle = {}
        
        # 🔑 [NEW] 입장문(심층 주제) 추출 - 제목에 핵심 주장 반영
        stance_text = context.get('stanceText', '')
        if stance_text:
            logger.info(f"[{self.name}] 입장문 {len(stance_text)}자 활용하여 제목 생성")

        params = {
            'topic': topic,
            'contentPreview': content_preview_text,
            'userKeywords': user_keywords, # User intent keywords
            'keywords': generated_keywords, # SEO extracts
            'fullName': full_name,
            'category': category,
            'status': status,
            'titleScope': title_scope,
            'backgroundText': background_text,
            'stanceText': stance_text,  # 🔑 [NEW] 입장문 전달
            'contextAnalysis': context_analysis,
            'pollFocusBundle': poll_focus_bundle,
            'roleKeywordPolicy': build_role_keyword_policy(
                user_keywords,
                person_roles=person_roles,
                source_texts=source_texts,
            ),
            'titleConstraintText': '동일 인물 이름은 제목 전체에서 1회만 사용할 것.',
            # 빈 응답 예방: 제목 프롬프트를 경량화해 모델 부담을 낮춘다.
            'titlePromptLite': bool((self.options or {}).get('titlePromptLite', True)),
        }

        # 최근 제목을 전달해 동일 패턴 재생산을 줄인다.
        recent_titles = []
        for key in ('recentTitles', 'previousTitles'):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        recent_titles.append(item.strip())
        title_history_ctx = context.get('titleHistory')
        if isinstance(title_history_ctx, list):
            for item in title_history_ctx:
                title_text = ''
                if isinstance(item, dict):
                    title_text = str(item.get('title') or '').strip()
                elif isinstance(item, str):
                    title_text = item.strip()
                if title_text:
                    recent_titles.append(title_text)
        dedup_recent_titles = []
        seen_recent_titles = set()
        for title in recent_titles:
            if title in seen_recent_titles:
                continue
            seen_recent_titles.add(title)
            dedup_recent_titles.append(title)
        if dedup_recent_titles:
            params['recentTitles'] = dedup_recent_titles[:10]
        logger.info(
            "[%s] recentTitles (count=%s): %s",
            self.name,
            len(params.get('recentTitles', [])),
            params.get('recentTitles', []),
        )

        # Override type if debug/forced
        if (self.options or {}).get('forceType'):
            params['_forcedType'] = self.options['forceType']

        logger.info(f"[{self.name}] Generating title for topic: {topic}")
        title_purpose = resolve_title_purpose(topic, params)
        is_matchup_title = str((poll_focus_bundle or {}).get('scope') or '').strip().lower() == 'matchup'
        # 행사 안내형은 규칙 준수 우선으로 샘플링 강도를 낮춰 안정적으로 생성한다.
        if title_purpose == 'event_announcement':
            generation_temperature = 0.25
            generation_top_p = 0.90
            generation_top_k = 32
        elif is_matchup_title:
            generation_temperature = 0.25
            generation_top_p = 0.80
            generation_top_k = 24
        else:
            generation_temperature = 0.7
            generation_top_p = 0.95
            generation_top_k = 40
        min_score = 70

        structured_candidates = []
        if not bool((self.options or {}).get("skipStructuredCandidates")):
            structured_candidates = build_structured_title_candidates(
                params,
                title_purpose=title_purpose,
                limit=8,
            )
        if structured_candidates:
            best_structured_title = ""
            best_structured_score = -1
            best_structured_result: Dict[str, Any] = {}
            for candidate in structured_candidates:
                validation = assess_title_focus_name_repetition(candidate, params)
                if not validation.get("passed", True):
                    continue
                score_result = calculate_title_quality_score(
                    candidate,
                    params,
                    {"autoFitLength": False},
                )
                score = int(score_result.get("score", 0) or 0)
                if score > best_structured_score:
                    best_structured_score = score
                    best_structured_title = candidate
                    best_structured_result = score_result

            if best_structured_title and best_structured_score >= min_score:
                logger.info(
                    "[%s] Structured title selected before LLM: %s (score=%s)",
                    self.name,
                    best_structured_title,
                    best_structured_score,
                )
                return {
                    "title": best_structured_title,
                    "titleScore": best_structured_score,
                    "titleHistory": [
                        {
                            "attempt": 0,
                            "title": best_structured_title,
                            "score": best_structured_score,
                            "source": "structured_plan",
                            "suggestions": list(best_structured_result.get("suggestions") or []),
                            "breakdown": dict(best_structured_result.get("breakdown") or {}),
                        }
                    ],
                    "titleType": "STRUCTURED_PLAN",
                }

        # 단계별로 올리는 클로저 변수 (프리앰블 재시도 기회 확보를 위해 최소 2)
        _json_parse_retries = 2

        async def generate_fn(prompt: str) -> str:
            if not self._client:
                raise ValueError("Model not initialized")
            payload = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=generation_temperature,
                max_output_tokens=220,
                retries=2,
                response_schema=TITLE_RESPONSE_SCHEMA,
                required_keys=("title",),
                options={
                    'top_p': generation_top_p,
                    'top_k': generation_top_k,
                    'json_parse_retries': _json_parse_retries,
                },
            )
            title = str(payload.get('title') or '').strip()
            if not title:
                raise StructuredOutputError("title is empty")
            return title

        primary_options = {
            'minScore': min_score,
            'maxAttempts': 2,
            'candidateCount': int((self.options or {}).get('candidateCount', 2)),
            'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
            'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
            'recentTitles': params.get('recentTitles', []),
            'allowAutoRepair': False,
            'temperature': generation_temperature,
            'onProgress': lambda p: logger.debug(f"[{self.name}] Attempt {p['attempt']} finished. Score: {p.get('score', 0)}")
        }

        try:
            result = await generate_and_validate_title(generate_fn, params, options=primary_options)
        except Exception as primary_error:
            logger.warning(
                "[%s] Primary title generation failed. Retry with strict single-candidate mode: %s",
                self.name,
                primary_error,
            )
            # strict retry: 파싱 재시도 강화, 후보 1개, 낮은 temperature
            generation_temperature = 0.2
            generation_top_p = 0.75
            generation_top_k = 20
            _json_parse_retries = 3
            strict_retry_options = {
                'minScore': min_score,
                'maxAttempts': 2,
                'candidateCount': 1,
                'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
                'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
                'recentTitles': params.get('recentTitles', []),
                'allowAutoRepair': False,
                'temperature': generation_temperature,
                'onProgress': lambda p: logger.debug(
                    f"[{self.name}] Strict retry attempt {p['attempt']} finished. Score: {p.get('score', 0)}"
                ),
            }
            try:
                result = await generate_and_validate_title(generate_fn, params, options=strict_retry_options)
            except Exception as strict_error:
                compliance_failure = (
                    _is_title_compliance_failure(primary_error)
                    or _is_title_compliance_failure(strict_error)
                )
                if compliance_failure:
                    logger.warning(
                        "[%s] Strict retry failed on compliance rules. Run full-context compliance retry: %s",
                        self.name,
                        strict_error,
                    )
                    _json_parse_retries = 3
                    generation_temperature = 0.1
                    generation_top_p = 0.65
                    generation_top_k = 12
                    compliance_params = {
                        **params,
                        'titlePromptLite': False,
                    }
                    compliance_options = {
                        'minScore': min_score,
                        'maxAttempts': 2,
                        'candidateCount': 1,
                        'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
                        'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
                        'recentTitles': params.get('recentTitles', []),
                        'allowAutoRepair': False,
                    }
                    try:
                        result = await generate_and_validate_title(
                            generate_fn, compliance_params, options=compliance_options,
                        )
                    except Exception as compliance_error:
                        fallback_result = _select_compliance_safe_fallback(
                            compliance_params,
                            min_score=min_score,
                            title_purpose=title_purpose,
                        )
                        if fallback_result:
                            fallback_title = str(fallback_result.get("title") or "").strip()
                            fallback_score = int(fallback_result.get("score") or 0)
                            fallback_source = str(fallback_result.get("source") or "compliance_fallback")
                            logger.warning(
                                "[%s] Compliance retry exhausted. Use safe fallback title: %s (score=%s, source=%s)",
                                self.name,
                                fallback_title,
                                fallback_score,
                                fallback_source,
                            )
                            return {
                                "title": fallback_title,
                                "titleScore": fallback_score,
                                "titleHistory": [
                                    {
                                        "attempt": -1,
                                        "title": fallback_title,
                                        "score": fallback_score,
                                        "source": fallback_source,
                                        "suggestions": list(fallback_result.get("suggestions") or []),
                                        "breakdown": dict(fallback_result.get("breakdown") or {}),
                                        "fallbackUsed": True,
                                        "softAccepted": not bool(fallback_result.get("passed")),
                                    }
                                ],
                                "titleType": (
                                    "COMPLIANCE_FALLBACK"
                                    if bool(fallback_result.get("passed"))
                                    else "COMPLIANCE_FALLBACK_SOFT"
                                ),
                            }
                        logger.error(
                            "[%s] All title generation attempts exhausted. "
                            "primary=%s | strict=%s | compliance=%s",
                            self.name, primary_error, strict_error, compliance_error,
                        )
                        raise compliance_error
                else:
                    # minimal retry: 경량 프롬프트로 generate_and_validate_title 경유 (A 하드페일 보장)
                    logger.warning(
                        "[%s] Strict retry failed. Minimal prompt retry via validate: %s",
                        self.name,
                        strict_error,
                    )
                    _json_parse_retries = 3
                    generation_temperature = 0.3
                    generation_top_p = 0.80
                    generation_top_k = 20
                    minimal_params = {
                        **params,
                        'contentPreview': '',
                        'backgroundText': '',
                        'stanceText': '',
                    }
                    minimal_options = {
                        'minScore': 1,
                        'maxAttempts': 1,
                        'candidateCount': 1,
                        'recentTitles': params.get('recentTitles', []),
                        'allowAutoRepair': False,
                    }
                    try:
                        result = await generate_and_validate_title(
                            generate_fn, minimal_params, options=minimal_options,
                        )
                    except Exception as minimal_error:
                        logger.error(
                            "[%s] All title generation attempts exhausted. "
                            "primary=%s | strict=%s | minimal=%s",
                            self.name, primary_error, strict_error, minimal_error,
                        )
                        raise minimal_error

        raw_title = str(result.get('title') or '')
        normalized_title = normalize_title_surface(raw_title) or raw_title
        focus_name_validation = assess_title_focus_name_repetition(normalized_title, params)
        if not focus_name_validation.get('passed', True):
            logger.warning(
                "[%s] Duplicate focus names detected. Trigger strict retry: %s | title=%s",
                self.name,
                focus_name_validation.get('reason'),
                normalized_title,
            )
            generation_temperature = 0.2
            generation_top_p = 0.75
            generation_top_k = 20
            _json_parse_retries = max(_json_parse_retries, 3)
            retry_params = {
                **params,
                'recentTitles': [*params.get('recentTitles', []), normalized_title],
            }
            retry_options = {
                'minScore': min_score,
                'maxAttempts': 1,
                'candidateCount': 1,
                'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
                'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
                'recentTitles': retry_params.get('recentTitles', []),
                'allowAutoRepair': False,
                'temperature': generation_temperature,
            }
            try:
                retry_result = await generate_and_validate_title(generate_fn, retry_params, options=retry_options)
                retry_title = normalize_title_surface(str(retry_result.get('title') or '').strip())
                retry_validation = assess_title_focus_name_repetition(retry_title, retry_params)
                if retry_title and retry_validation.get('passed', True):
                    result = retry_result
                    normalized_title = retry_title
                else:
                    raise StructuredOutputError(
                        str(
                            retry_validation.get('reason')
                            or '중복 이름 후처리 재시도에서 유효한 제목을 만들지 못했습니다.'
                        )
                    )
            except Exception as retry_error:
                raise StructuredOutputError(
                    str(
                        focus_name_validation.get('reason')
                        or f'제목 이름 중복 후처리 검증에 실패했습니다: {retry_error}'
                    )
                ) from retry_error
        logger.info(f"[{self.name}] Selected Title: {normalized_title} (Score: {result['score']})")

        return {
            'title': normalized_title,
            'titleScore': result['score'],
            'titleHistory': result['history'],
            'titleType': result.get('analysis', {}).get('type', 'UNKNOWN')
        }
