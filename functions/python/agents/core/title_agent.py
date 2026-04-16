
import logging
import re
from typing import Dict, Any, Optional

from ..base_agent import Agent
from ..common.role_keyword_policy import (
    build_role_keyword_policy,
    extract_person_role_facts_from_text,
)
from ..common.title_generation import (
    generate_and_validate_title,
    normalize_title_surface,
    resolve_title_purpose,
)
from ..common.title_common import (
    assess_title_focus_name_repetition,
    build_structured_title_candidates,
)
from ..common.title_scoring import calculate_title_quality_score

logger = logging.getLogger(__name__)

TITLE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        # Phase 1 (source-tone self-judgment) — LLM 이 원문을 읽고 먼저 판정한
        # 톤을 함께 반환. regex/Kiwi family classifier 를 점진적으로 대체하기
        # 위한 관측 필드. 허용값은 프롬프트에서 명시. schema 는 required 에서
        # 제외해 기존 응답 호환성 유지(구버전 프롬프트 / 미기입 시 payload 에
        # 안 실려도 파싱 성공).
        "sourceTone": {"type": "string"},
        "sourceToneReason": {"type": "string"},
    },
    "required": ["title"],
}


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
            # 🔑 프로필 지역/직책 필드 — extract_slot_opportunities 가
            # 본문 표면추출보다 먼저 읽어 "자족도시/천광역시" 같은 오탐을
            # 원천 차단한다. 필드명은 Firestore 스키마(handlers/profile.py)
            # 의 canonical name 을 그대로 사용한다.
            'regionMetro': str(user_profile.get('regionMetro') or '').strip(),
            'regionLocal': str(user_profile.get('regionLocal') or '').strip(),
            'electoralDistrict': str(user_profile.get('electoralDistrict') or '').strip(),
            'position': str(user_profile.get('position') or '').strip(),
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
                max_output_tokens=260,
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
            # Phase 1 관측 — LLM 자기판정 source tone 을 로그로 남겨 기존
            # select_title_family regex 판정과 대조 가능하게 한다. 아직 파이프라인
            # 동작에는 반영하지 않는다(순수 로깅).
            tone = str(payload.get('sourceTone') or '').strip().lower()
            tone_reason = str(payload.get('sourceToneReason') or '').strip()
            if tone:
                logger.info(
                    "[TitleAgent] source_tone_self_judgment tone=%s reason=%s title=%r",
                    tone,
                    tone_reason[:120],
                    title,
                )
            return title

        # allowDegradedPass: 호출 측(예: 파이프라인 최종 제목 단계) 이 설정하면,
        # 모든 재시도가 min_score 미달이어도 하드 게이트(length/role/anchor) 통과한
        # best_result 를 예외 대신 반환하도록 generate_and_validate_title 에 위임.
        # 설정 안 되면 기존 엄격 동작(예외) 유지.
        allow_degraded_pass = bool((self.options or {}).get('allowDegradedPass', False))

        primary_options = {
            'minScore': min_score,
            'maxAttempts': 2,
            'candidateCount': int((self.options or {}).get('candidateCount', 2)),
            'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
            'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
            'recentTitles': params.get('recentTitles', []),
            'allowAutoRepair': False,
            'allowDegradedPass': allow_degraded_pass,
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
                'allowDegradedPass': allow_degraded_pass,
                'temperature': generation_temperature,
                'onProgress': lambda p: logger.debug(
                    f"[{self.name}] Strict retry attempt {p['attempt']} finished. Score: {p.get('score', 0)}"
                ),
            }
            try:
                result = await generate_and_validate_title(generate_fn, params, options=strict_retry_options)
            except Exception as strict_error:
                logger.error(
                    "[%s] All title generation attempts exhausted. primary=%s | strict=%s",
                    self.name, primary_error, strict_error,
                )
                raise strict_error

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
                'allowDegradedPass': allow_degraded_pass,
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
