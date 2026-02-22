
import re
import logging
import time
import random
from typing import Dict, Any, Optional, List, Tuple

# API Call Timeout (seconds)
LLM_CALL_TIMEOUT = 120  # 2분 타임아웃
CONTEXT_ANALYZER_TIMEOUT = 60  # 1분 타임아웃

# Local imports
from ..common.classifier import classify_topic
from ..common.theminjoo import get_party_stance
from ..common.constants import resolve_writing_method

logger = logging.getLogger(__name__)


from ..base_agent import Agent

from .structure_utils import (
    strip_html, normalize_artifacts, normalize_html_structure_tags,
    normalize_context_text, split_into_context_items, parse_response
)
from .prompt_builder import build_structure_prompt, build_retry_directive
from .content_validator import ContentValidator
from .content_repair import ContentRepairAgent
from .context_analyzer import ContextAnalyzer
from .structure_normalizer import normalize_structure

class StructureAgent(Agent):
    def __init__(self, name: str = 'StructureAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)

        # 공통 Gemini 클라이언트 사용 (새 google-genai SDK)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = DEFAULT_MODEL

        # 클라이언트 초기화 확인
        client = get_client()
        if client:
            print(f"🤖 [StructureAgent] 모델: {self.model_name}")
        else:
            print(f"⚠️ [StructureAgent] Gemini 클라이언트 초기화 실패")

        self.validator = ContentValidator()
        self.repairer = ContentRepairAgent(model_name=self.model_name)
        self.context_analyzer = ContextAnalyzer(model_name=self.model_name)
    def _sanitize_target_word_count(self, target_word_count: Any) -> int:
        try:
            parsed = int(float(target_word_count))
        except (TypeError, ValueError):
            return 2000
        return max(1600, min(parsed, 3200))

    def _build_length_spec(self, target_word_count: Any, stance_count: int = 0, *, reference_text_len: int = 0) -> Dict[str, int]:
        target_chars = self._sanitize_target_word_count(target_word_count)

        # 섹션당 350자 내외를 기준으로 5~7섹션 계획
        total_sections = round(target_chars / 350)
        total_sections = max(5, min(7, total_sections))
        if stance_count > 0:
            total_sections = max(total_sections, min(7, stance_count + 2))
        # 참고자료가 풍부하면 섹션 수 상향
        if reference_text_len > 1200:
            total_sections = max(total_sections, 6)
        if reference_text_len > 2000:
            total_sections = min(7, total_sections + 1)

        body_sections = total_sections - 2
        per_section_recommended = max(330, min(380, round(target_chars / total_sections)))
        per_section_min = max(280, per_section_recommended - 50)
        per_section_max = min(430, per_section_recommended + 50)

        min_chars = max(int(target_chars * 0.88), total_sections * per_section_min)
        # 상한은 기본 분량(2000자 기준)에서 3000자까지 허용하도록 고정 캡을 둔다.
        # - 기존: 2000자 기준 약 2250자
        # - 변경: 최대 3000자
        if target_chars >= 2000:
            max_chars = 3000
        else:
            max_chars = min(int(target_chars * 1.18), total_sections * per_section_max)
        if max_chars <= min_chars:
            max_chars = min_chars + 180

        return {
            'target_chars': target_chars,
            'body_sections': body_sections,
            'total_sections': total_sections,
            'per_section_min': per_section_min,
            'per_section_max': per_section_max,
            'per_section_recommended': per_section_recommended,
            'min_chars': min_chars,
            'max_chars': max_chars,
            'expected_h2': total_sections - 1,
            'paragraphs_per_section': 3
        }

    def _is_low_context_input(
        self,
        *,
        stance_text: str,
        instructions: str,
        news_data_text: str,
        news_context: str,
    ) -> bool:
        stance_len = len(strip_html(stance_text or ""))
        instruction_len = len(strip_html(instructions or ""))
        news_data_len = len(strip_html(news_data_text or ""))
        news_ctx_len = len(strip_html(news_context or ""))
        primary_len = stance_len + instruction_len + max(news_data_len, news_ctx_len)
        source_count = sum(
            1
            for length in (stance_len, instruction_len, news_data_len, news_ctx_len)
            if length > 0
        )

        if primary_len < 550:
            return True
        if source_count <= 1 and primary_len < 900:
            return True
        if max(stance_len, instruction_len) < 320 and max(news_data_len, news_ctx_len) < 220:
            return True
        return False

    def _build_profile_support_context(self, user_profile: Dict[str, Any], *, max_chars: int = 1800) -> str:
        if not isinstance(user_profile, dict):
            return ""

        facts: List[str] = []
        seen: set[str] = set()

        def add_fact(raw: Any, *, prefix: str = "") -> None:
            text = normalize_context_text(raw, sep="\n")
            if not text:
                return

            chunks: List[str] = []
            for line in re.split(r'[\r\n]+', text):
                line = line.strip(" \t-•")
                if not line:
                    continue
                sentence_parts = re.split(r'[;·•]+|[.!?。]\s+|다\.\s+', line)
                for part in sentence_parts:
                    cleaned = re.sub(r'\s+', ' ', part).strip(" \t-•")
                    if len(cleaned) < 8:
                        continue
                    chunks.append(f"{prefix}{cleaned}" if prefix else cleaned)

            for chunk in chunks:
                key = re.sub(r'\s+', ' ', chunk).strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                facts.append(chunk)
                if len(facts) >= 14:
                    return

        name = str(user_profile.get('name') or '').strip()
        party_name = str(user_profile.get('partyName') or '').strip()
        title = str(user_profile.get('customTitle') or user_profile.get('position') or '').strip()
        identity = " ".join(part for part in (party_name, title, name) if part)
        if identity:
            add_fact(f"화자 정보: {identity}")

        add_fact(user_profile.get('careerSummary'))
        add_fact(user_profile.get('bio'))
        add_fact(user_profile.get('politicalExperience'), prefix='정치 이력: ')

        core_values = user_profile.get('coreValues')
        if isinstance(core_values, list):
            core_values_text = ", ".join(str(v).strip() for v in core_values if str(v).strip())
            if core_values_text:
                add_fact(core_values_text, prefix='핵심 가치: ')
        else:
            add_fact(core_values, prefix='핵심 가치: ')

        bio_entries = user_profile.get('bioEntries')
        if isinstance(bio_entries, list):
            for entry in bio_entries[:8]:
                if isinstance(entry, dict):
                    entry_parts = []
                    for key in ('title', 'summary', 'content', 'description', 'value', 'text'):
                        value = normalize_context_text(entry.get(key))
                        if value:
                            entry_parts.append(value)
                    if entry_parts:
                        add_fact(" - ".join(entry_parts))
                else:
                    add_fact(entry)

        region_metro = str(user_profile.get('regionMetro') or '').strip()
        region_district = str(user_profile.get('regionDistrict') or '').strip()
        if region_metro or region_district:
            add_fact(f"활동 지역: {' '.join(part for part in (region_metro, region_district) if part)}")

        if not facts:
            return ""

        lines: List[str] = []
        total_chars = 0
        for fact in facts:
            line = f"- {fact}"
            line_len = len(line) + 1
            if total_chars + line_len > max_chars:
                break
            lines.append(line)
            total_chars += line_len

        return "\n".join(lines).strip()

    def _normalize_context_analysis_materials(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        # Context 분석 결과 정규화 책임은 ContextAnalyzer 모듈로 분리했다.
        return self.context_analyzer.normalize_materials(analysis)

    def _extract_profile_additional_items(self, user_profile: Dict[str, Any], *, max_items: int = 24) -> List[str]:
        if not isinstance(user_profile, dict):
            return []

        items: List[str] = []
        seen: set[str] = set()

        def add_unique(text: str) -> None:
            cleaned = re.sub(r'\s+', ' ', normalize_context_text(text)).strip(" \t-•")
            if not cleaned:
                return
            if len(strip_html(cleaned)) < 12:
                return
            key = cleaned.lower()
            if key in seen:
                return
            seen.add(key)
            items.append(cleaned)

        def flatten_value(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, dict):
                parts: List[str] = []
                for k, v in value.items():
                    nested = flatten_value(v)
                    if not nested:
                        continue
                    if isinstance(v, (dict, list, tuple, set)):
                        parts.append(nested)
                    else:
                        parts.append(f"{k}: {nested}")
                return "\n".join(parts)
            if isinstance(value, (list, tuple, set)):
                parts = [flatten_value(v) for v in value]
                return "\n".join(p for p in parts if p)
            return str(value).strip()

        # 1) bioEntries 기반 추가정보 우선 추출 (정책/법안/성과 우선)
        type_priority = {
            'policy': 0,
            'legislation': 1,
            'achievement': 2,
            'vision': 3,
            'experience': 4,
            'reference': 5,
        }
        typed_candidates: List[Tuple[int, str]] = []
        bio_entries = user_profile.get('bioEntries')
        if isinstance(bio_entries, list):
            for entry in bio_entries:
                if not isinstance(entry, dict):
                    continue
                entry_type = str(entry.get('type') or '').strip().lower()
                priority = type_priority.get(entry_type, 9)
                if priority >= 9:
                    continue
                title = normalize_context_text(entry.get('title'))
                content = normalize_context_text(
                    entry.get('content') or entry.get('summary') or entry.get('description') or entry.get('text')
                )
                if not content:
                    continue
                label = entry_type or 'profile'
                if title:
                    typed_candidates.append((priority, f"[{label}] {title} - {content}"))
                else:
                    typed_candidates.append((priority, f"[{label}] {content}"))

        for _, text in sorted(typed_candidates, key=lambda x: x[0]):
            add_unique(text)
            if len(items) >= max_items:
                return items[:max_items]

        # 2) userProfile의 구조화 필드에서 공약/법안/성과성 키 추출
        interesting_key_pattern = re.compile(
            r'(policy|pledge|promise|manifesto|bill|legislation|ordinance|achievement|performance|track|'
            r'공약|정책|법안|조례|성과|실적|업적)',
            re.IGNORECASE,
        )
        skip_keys = {
            'name', 'partyName', 'customTitle', 'position', 'status', 'role',
            'regionMetro', 'regionDistrict', 'regionLocal', 'electoralDistrict',
            'bio', 'careerSummary', 'bioEntries', 'styleGuide', 'styleFingerprint',
            'slogan', 'sloganEnabled', 'donationInfo', 'donationEnabled',
            'targetElection', 'familyStatus', 'age', 'ageDecade', 'gender',
            'committees', 'customCommittees', 'localConnection', 'politicalExperience',
            'constituencyType', 'isAdmin', 'isTester',
        }
        for key, value in user_profile.items():
            key_text = str(key or '').strip()
            if not key_text or key_text in skip_keys:
                continue
            if not interesting_key_pattern.search(key_text):
                continue
            flattened = flatten_value(value)
            for snippet in split_into_context_items(flattened, min_len=14, max_items=8):
                add_unique(f"[{key_text}] {snippet}")
                if len(items) >= max_items:
                    return items[:max_items]

        return items[:max_items]

    def _build_profile_substitute_context(self, user_profile: Dict[str, Any], *, target_items: int = 3) -> Dict[str, Any]:
        target = max(1, int(target_items or 3))
        additional_pool = self._extract_profile_additional_items(user_profile, max_items=24)

        rng = random.SystemRandom()
        selected_additional: List[str] = []
        if additional_pool:
            selected_additional = rng.sample(additional_pool, min(target, len(additional_pool)))

        selected_items: List[str] = list(selected_additional)
        needed = max(0, target - len(selected_items))

        if needed > 0:
            bio_text = normalize_context_text(
                [user_profile.get('careerSummary'), user_profile.get('bio')],
                sep="\n",
            )
            bio_pool = [
                item for item in split_into_context_items(bio_text, min_len=12, max_items=24)
                if item not in selected_items
            ]
            if bio_pool:
                bio_selected = rng.sample(bio_pool, min(needed, len(bio_pool)))
                selected_items.extend(bio_selected)
                needed = max(0, target - len(selected_items))

        if needed > 0:
            support_text = self._build_profile_support_context(user_profile, max_chars=1800)
            support_pool = [
                item for item in split_into_context_items(support_text, min_len=10, max_items=24)
                if item not in selected_items
            ]
            if support_pool:
                support_selected = rng.sample(support_pool, min(needed, len(support_pool)))
                selected_items.extend(support_selected)

        if len(selected_items) > 1:
            rng.shuffle(selected_items)

        context_text = "\n".join(f"- {item}" for item in selected_items)
        return {
            'selectedItems': selected_items,
            'contextText': context_text,
            'additionalPoolCount': len(additional_pool),
            'usedAdditionalCount': len(selected_additional),
            'usedBioCount': max(0, len(selected_items) - len(selected_additional)),
        }

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        topic = context.get('topic', '')
        user_profile = context.get('userProfile', {})
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}
        category = context.get('category', '')
        sub_category = context.get('subCategory', '')
        instructions = normalize_context_text(context.get('instructions', ''))
        news_context = normalize_context_text(context.get('newsContext', ''))
        # 🔑 [NEW] 입장문과 뉴스/데이터 분리
        stance_text = normalize_context_text(context.get('stanceText', ''))
        news_data_text = normalize_context_text(context.get('newsDataText', ''))
        source_instructions = normalize_context_text(stance_text)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(instructions)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(topic)
        effective_news_context = news_data_text or news_context
        target_word_count = context.get('targetWordCount', 2000)
        user_keywords = context.get('userKeywords', [])
        personalized_hints = normalize_context_text(context.get('personalizedHints', ''), sep="\n")
        memory_context = normalize_context_text(context.get('memoryContext', ''), sep="\n")
        personalization_context = normalize_context_text([personalized_hints, memory_context], sep="\n")
        profile_support_context = self._build_profile_support_context(user_profile)
        has_news_source = bool(strip_html(effective_news_context))
        profile_substitute = self._build_profile_substitute_context(user_profile, target_items=3) if not has_news_source else {}
        analyzer_news_context = effective_news_context
        news_source_mode = 'news'
        if not has_news_source:
            news_source_mode = 'profile_fallback'
            substitute_text = normalize_context_text(profile_substitute.get('contextText'))
            if not substitute_text and profile_support_context:
                fallback_items = split_into_context_items(
                    profile_support_context,
                    min_len=12,
                    max_items=3,
                )
                if fallback_items:
                    substitute_text = "\n".join(f"- {item}" for item in fallback_items)
                    if isinstance(profile_substitute, dict):
                        profile_substitute["selectedItems"] = fallback_items
                        profile_substitute["contextText"] = substitute_text
                        profile_substitute["usedBioCount"] = max(
                            int(profile_substitute.get("usedBioCount") or 0),
                            len(fallback_items),
                        )
                    print(
                        "⚠️ [StructureAgent] 프로필 추가정보가 부족하여 Bio 보강 1차 문맥을 대체자료로 사용합니다."
                    )
            analyzer_news_context = f"[사용자 추가정보 대체자료]\n{substitute_text}" if substitute_text else ""

        print(f"🚀 [StructureAgent] 시작 - 카테고리: {category or '(자동)'}, 주제: {topic}")
        print(f"📊 [StructureAgent] 입장문: {len(stance_text)}자, 뉴스/데이터: {len(news_data_text)}자")
        if news_source_mode == 'news':
            print(f"🧭 [StructureAgent] ContextAnalyzer 소스: 뉴스/데이터 사용 ({len(strip_html(effective_news_context))}자)")
        else:
            print(
                "🧭 [StructureAgent] ContextAnalyzer 소스: 프로필 대체 "
                f"(추가정보 풀 {profile_substitute.get('additionalPoolCount', 0)}개, "
                f"사용 추가정보 {profile_substitute.get('usedAdditionalCount', 0)}개, "
                f"bio 보충 {profile_substitute.get('usedBioCount', 0)}개)"
            )

        # 1. Determine Writing Method
        writing_method = ''
        if category and category != 'auto':
            writing_method = resolve_writing_method(category, sub_category)
            print(f"✍️ [StructureAgent] 작법 선택 (카테고리 기반): {writing_method}")
        else:
            classification = await classify_topic(topic)
            writing_method = classification['writingMethod']
            print(f"🤖 [StructureAgent] 작법 자동 추론: {writing_method} (신뢰도: {classification.get('confidence')}, 소스: {classification.get('source')})")

        # 2. Build Author Bio
        author_bio, author_name = self.build_author_bio(user_profile)

        # 3. Get Party Stance
        party_stance_guide = None
        try:
             party_stance_guide = get_party_stance(topic)
        except Exception as e:
             print(f"⚠️ [StructureAgent] 당론 조회 실패: {str(e)}")

        # 4. ContextAnalyzer (입장문/뉴스 분리 처리)
        analyzer_stance_text = source_instructions
        if len(strip_html(analyzer_stance_text)) < 24:
            analyzer_stance_text = normalize_context_text([analyzer_stance_text, topic], sep="\n\n")
        analyzer_news_text = analyzer_news_context

        context_analysis = await self.run_context_analyzer(
            analyzer_stance_text,
            analyzer_news_text,
            author_name
        )
        if isinstance(context_analysis, dict):
            context_analysis = self._normalize_context_analysis_materials(context_analysis)
        # validate_output 호출에 사용하는 이벤트 컨텍스트 힌트는
        # process 스코프에서 항상 초기화되어야 한다.
        is_event_announcement = False
        event_date_hint = ''
        event_location_hint = ''
        if isinstance(context_analysis, dict):
            analysis_intent = str(context_analysis.get('intent') or '').strip().lower()
            must_preserve = context_analysis.get('mustPreserve')
            if analysis_intent == 'event_announcement':
                is_event_announcement = True
                if isinstance(must_preserve, dict):
                    event_date_hint = str(must_preserve.get('eventDate') or '').strip()
                    event_location_hint = str(must_preserve.get('eventLocation') or '').strip()

        reference_text_len = (
            len(strip_html(stance_text))
            + len(strip_html(news_data_text))
            + len(strip_html(instructions))
        )
        stance_count = len(context_analysis.get('mustIncludeFromStance', [])) if context_analysis else 0
        length_spec = self._build_length_spec(
            target_word_count,
            stance_count,
            reference_text_len=reference_text_len,
        )
        print(
            f"📏 [StructureAgent] 분량 계획: {length_spec['total_sections']}섹션, "
            f"{length_spec['min_chars']}~{length_spec['max_chars']}자 "
            f"(섹션당 {length_spec['per_section_recommended']}자)"
        )

        # 5. Build Prompt
        prompt = build_structure_prompt({
            'topic': topic,
            'category': category,
            'writingMethod': writing_method,
            'authorName': author_name,
            'authorBio': author_bio,
            'instructions': source_instructions,
            'newsContext': effective_news_context,
            'targetWordCount': target_word_count,
            'partyStanceGuide': party_stance_guide,
            'contextAnalysis': context_analysis,
            'userProfile': user_profile,
            'personalizationContext': personalization_context,
            'memoryContext': memory_context,
            'profileSupportContext': profile_support_context,
            'profileSubstituteContext': profile_substitute.get('contextText') if isinstance(profile_substitute, dict) else '',
            'newsSourceMode': news_source_mode,
            'userKeywords': user_keywords,
            'lengthSpec': length_spec
        })

        print(f"📝 [StructureAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

        # 6. Retry Loop
        max_retries = 3
        attempt = 0
        feedback = ''
        retry_directive = ''
        validation: Dict[str, Any] = {}
        last_error = None
        best_candidate: Dict[str, Any] = {}
        structural_recoverable_codes = {
            'H2_SHORT',
            'H2_LONG',
            'P_SHORT',
            'P_LONG',
            'H2_MALFORMED',
            'P_MALFORMED',
            'TAG_DISALLOWED',
            'PHRASE_REPEAT_CAP',
            'MATERIAL_REUSE',
            'LOCATION_ORPHAN_REPEAT',
            'META_PROMPT_LEAK',
            'EVENT_FACT_REPEAT',
            'EVENT_INVITE_REDUNDANT',
        }

        def _candidate_rank(candidate_validation: Dict[str, Any], candidate_content: str) -> tuple:
            plain_len = len(strip_html(candidate_content or ''))
            code = str(candidate_validation.get('code') or '')
            penalties = {
                'LENGTH_SHORT': 8,
                'LENGTH_LONG': 7,
                'H2_SHORT': 4,
                'H2_LONG': 4,
                'P_SHORT': 5,
                'P_LONG': 5,
                'H2_MALFORMED': 6,
                'P_MALFORMED': 6,
                'TAG_DISALLOWED': 6,
            }
            penalty = penalties.get(code, 5)
            return (
                1 if bool(candidate_validation.get('passed')) else 0,
                1 if plain_len >= int(length_spec.get('min_chars') or 0) else 0,
                1 if plain_len <= int(length_spec.get('max_chars') or 999999) else 0,
                -penalty,
                -abs(plain_len - int(length_spec.get('min_chars') or 0)),
                plain_len,
            )

        def _remember_best(
            candidate_content: str,
            candidate_title: str,
            candidate_validation: Dict[str, Any],
            source: str,
            source_attempt: int,
        ) -> None:
            nonlocal best_candidate
            if not candidate_content:
                return
            rank = _candidate_rank(candidate_validation, candidate_content)
            if (not best_candidate) or rank > tuple(best_candidate.get('rank') or ()):
                best_candidate = {
                    'content': candidate_content,
                    'title': candidate_title,
                    'validation': dict(candidate_validation or {}),
                    'rank': rank,
                    'plain_len': len(strip_html(candidate_content or '')),
                    'source': source,
                    'attempt': source_attempt,
                }

        while attempt <= max_retries:
            attempt += 1
            print(f"🔄 [StructureAgent] 생성 시도 {attempt}/{max_retries + 1}")

            current_prompt = prompt
            if feedback:
                retry_block = f"\n\n{retry_directive}" if retry_directive else ""
                current_prompt += (
                    f"\n\n🚨 [중요 - 재작성 지시] 이전 작성본이 다음 이유로 반려되었습니다:\n"
                    f"\"{feedback}\"{retry_block}"
                )

            try:
                response = await self.call_llm(current_prompt)
                print(f"📥 [StructureAgent] LLM 원본 응답 ({len(response)}자)")

                structured = parse_response(response)
                content = normalize_artifacts(structured['content'])
                content = normalize_html_structure_tags(content)
                content = normalize_structure(content, length_spec, user_keywords=user_keywords)
                title = normalize_artifacts(structured['title'])

                # 파싱/정리 과정에서 본문이 비정상적으로 축약된 경우 재시도 유도.
                plain_len = len(strip_html(content))
                response_text = str(response or "")
                response_plain_len = len(strip_html(response_text))
                print(
                    f"📐 [StructureAgent] 시도 {attempt} 길이: "
                    f"raw={len(response_text)}자, parsed={len(content)}자, plain={plain_len}자"
                )
                if plain_len < 400 and (
                    len(response_text) > 1000
                    or response_plain_len > max(700, plain_len * 4)
                ):
                    raise Exception(f"파싱 비정상 축약 감지 ({plain_len}자)")

                validation = self.validator.validate(
                    content,
                    length_spec,
                    context_analysis=context_analysis,
                    is_event_announcement=is_event_announcement,
                    event_date_hint=event_date_hint,
                    event_location_hint=event_location_hint,
                )
                _remember_best(content, title, validation, source='draft', source_attempt=attempt)

                if validation['passed']:
                    print(f"✅ [StructureAgent] 검증 통과: {len(strip_html(content))}자")
                    if not title.strip():
                        title = topic[:20] if topic else '새 원고'
                    return {
                        'content': content,
                        'title': title,
                        'writingMethod': writing_method,
                        'contextAnalysis': context_analysis
                    }

                print(
                    f"⚠️ [StructureAgent] 검증 실패: code={validation.get('code')} "
                    f"reason={validation['reason']}"
                )

                recovery_code = str(validation.get('code') or '')
                recovery_content = content
                recovery_title = title
                recovery_validation = dict(validation or {})
                max_recovery_rounds = 3 if (
                    recovery_code == 'LENGTH_SHORT' or recovery_code in structural_recoverable_codes
                ) else 1

                for recovery_round in range(1, max_recovery_rounds + 1):
                    current_code = str(recovery_validation.get('code') or '')
                    recovery_result: Optional[Tuple[str, str]] = None

                    if current_code == 'LENGTH_SHORT':
                        recovery_result = await self.repairer.recover_length_shortfall(
                            content=recovery_content,
                            title=recovery_title,
                            topic=topic,
                            length_spec=length_spec,
                            author_bio=author_bio,
                        )
                    elif current_code in structural_recoverable_codes:
                        recovery_result = await self.repairer.recover_structural_shortfall(
                            content=recovery_content,
                            title=recovery_title,
                            topic=topic,
                            length_spec=length_spec,
                            author_bio=author_bio,
                            failed_code=current_code,
                            failed_reason=str(recovery_validation.get('reason') or ''),
                            failed_feedback=str(recovery_validation.get('feedback') or ''),
                        )

                    if not recovery_result:
                        break

                    recovered_content, recovered_title = recovery_result
                    recovered_content = normalize_structure(
                        recovered_content, length_spec, user_keywords=user_keywords
                    )
                    recovered_validation = self.validator.validate(
                        recovered_content,
                        length_spec,
                        context_analysis=context_analysis,
                        is_event_announcement=is_event_announcement,
                        event_date_hint=event_date_hint,
                        event_location_hint=event_location_hint,
                    )
                    _remember_best(
                        recovered_content,
                        recovered_title,
                        recovered_validation,
                        source='repair',
                        source_attempt=attempt,
                    )
                    if recovered_validation.get('passed'):
                        print(
                            f"✅ [StructureAgent] 복구 검증 통과: "
                            f"{len(strip_html(recovered_content))}자"
                        )
                        if not recovered_title.strip():
                            recovered_title = topic[:20] if topic else '새 원고'
                        return {
                            'content': recovered_content,
                            'title': recovered_title,
                            'writingMethod': writing_method,
                            'contextAnalysis': context_analysis
                        }

                    next_code = str(recovered_validation.get('code') or '')
                    print(
                        f"⚠️ [StructureAgent] 복구 시도 {recovery_round}/{max_recovery_rounds} 실패: "
                        f"code={next_code} reason={recovered_validation.get('reason')}"
                    )

                    same_code = next_code == current_code
                    unchanged_text = strip_html(recovered_content) == strip_html(recovery_content)
                    recovery_content = recovered_content
                    recovery_title = recovered_title
                    recovery_validation = dict(recovered_validation or {})

                    if same_code and unchanged_text:
                        print(
                            "⚠️ [StructureAgent] 복구 결과가 동일해 추가 복구를 중단합니다."
                        )
                        break

                content = recovery_content
                title = recovery_title
                validation = recovery_validation

                feedback = str(validation.get('feedback') or validation.get('reason') or '')
                retry_directive = build_retry_directive(validation, length_spec)
                last_error = None

            except Exception as e:
                error_msg = str(e)
                print(f"❌ [StructureAgent] 에러 발생: {error_msg}")
                feedback = error_msg
                retry_directive = ''
                last_error = error_msg

            if attempt > max_retries:
                if best_candidate:
                    best_validation = best_candidate.get('validation') or {}
                    best_reason = str(best_validation.get('reason') or '').strip()
                    best_code = str(best_validation.get('code') or '').strip()
                    best_len = int(best_candidate.get('plain_len') or 0)
                    final_reason = best_reason or last_error or validation.get('reason', '알 수 없는 오류')
                    raise Exception(
                        f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason} "
                        f"[bestCode={best_code}, bestLen={best_len}, source={best_candidate.get('source')}]"
                    )
                final_reason = last_error or validation.get('reason', '알 수 없는 오류')
                raise Exception(f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason}")

    async def call_llm(self, prompt: str) -> str:
        from ..common.gemini_client import generate_content_async

        print(f"📤 [StructureAgent] LLM 호출 시작")
        start_time = time.time()

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.1,  # 구조 준수율을 높이기 위해 변동성 축소
                max_output_tokens=4096
            )

            elapsed = time.time() - start_time
            print(f"✅ [StructureAgent] LLM 응답 완료 ({elapsed:.1f}초)")

            return response_text

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"❌ [StructureAgent] LLM 호출 실패 ({elapsed:.1f}초): {error_msg}")

            # 타임아웃 관련 에러 메시지 개선
            if 'timeout' in error_msg.lower() or 'deadline' in error_msg.lower():
                raise Exception(f"LLM 호출 타임아웃 ({elapsed:.1f}초). Gemini API가 응답하지 않습니다.")
            raise


    async def run_context_analyzer(self, stance_text: str, news_data_text: str, author_name: str) -> Optional[Dict]:
        return await self.context_analyzer.analyze(
            stance_text=stance_text,
            news_data_text=news_data_text,
            author_name=author_name,
        )

    def build_author_bio(self, user_profile: Dict) -> tuple[str, str]:
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}

        name = user_profile.get('name', '사용자')
        party_name = user_profile.get('partyName', '')
        current_title = user_profile.get('customTitle') or user_profile.get('position', '')
        basic_bio = " ".join(filter(None, [party_name, current_title, name]))

        career = user_profile.get('careerSummary') or user_profile.get('bio', '')

        # 서론이 장문 자기소개로 쏠리지 않도록 경력 힌트는 1개만 압축한다.
        compact_career = ""
        if career:
            summary_parts = split_into_context_items(career, min_len=8, max_items=1)
            if summary_parts:
                compact_career = summary_parts[0][:120]

        compact_bio = basic_bio.strip()
        if compact_career:
            compact_bio = "\n".join(part for part in [compact_bio, compact_career] if part).strip()

        # 슬로건/후원 안내는 생성 단계에서 제외하고, 최종 출력 직전에만 부착한다.
        return (compact_bio or name), name

    def is_current_lawmaker(self, user_profile: Dict) -> bool:
        # 방어 코드 - list로 전달되거나 None인 경우 방어
        if not user_profile or not isinstance(user_profile, dict):
            return False
        status = user_profile.get('status', '')
        position = user_profile.get('position', '')
        title = user_profile.get('customTitle', '')

        elected_keywords = ['의원', '구청장', '군수', '시장', '도지사', '교육감']
        text_to_check = status + position + title
        return any(k in text_to_check for k in elected_keywords)


