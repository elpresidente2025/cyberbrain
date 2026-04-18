
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# API Call Timeout (seconds)
LLM_CALL_TIMEOUT = 120  # 2분 타임아웃
CONTEXT_ANALYZER_TIMEOUT = 60  # 1분 타임아웃

from ..common.editorial import STRUCTURE_SPEC
from ..common.section_contract import infer_sentence_role, validate_section_contract

logger = logging.getLogger(__name__)


from ..base_agent import Agent

from .structure_utils import (
    normalize_context_text,
    split_into_context_items,
    strip_html,
)
from .content_validator import ContentValidator
from .content_repair import ContentRepairAgent
from .context_analyzer import ContextAnalyzer
from .section_normalizer import SectionNormalizerMixin, _coerce_int_option
from .section_repair import SectionRepairMixin


class StructureAgent(SectionRepairMixin, SectionNormalizerMixin, Agent):
    _HEADING_ALIGNMENT_STOPWORDS = {
        "이유",
        "배경",
        "무엇",
        "무엇인가",
        "무엇을",
        "어떻게",
        "왜",
        "지금",
        "해야",
        "하나",
        "대한",
        "위한",
        "통한",
        "관련",
        "에서",
        "하는",
    }
    _HEADING_ALIGNMENT_SUFFIXES = (
        "에서는",
        "과의",
        "와의",
        "으로는",
        "에게는",
        "에서",
        "으로",
        "에게",
        "에는",
        "부터",
        "까지",
        "처럼",
        "보다",
        "과",
        "와",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "로",
        "도",
        "만",
    )
    _BANNED_FIRST_PERSON_HEADING_PATTERN = re.compile(r"(?:^|[\s,])(?:저는|제가|나는|내가)(?:[\s,]|$)")

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

        # 생성/복구 루프 예산 (성능 최적화)
        self.max_retries = _coerce_int_option(
            self.options.get("structureMaxRetries"),
            default=1,
            minimum=1,
            maximum=4,
        )
        self.length_recovery_rounds = _coerce_int_option(
            self.options.get("structureLengthRecoveryRounds"),
            default=0,
            minimum=0,
            maximum=3,
        )
        self.structural_recovery_rounds = _coerce_int_option(
            self.options.get("structureStructuralRecoveryRounds"),
            default=0,
            minimum=0,
            maximum=3,
        )
        self.late_recovery_cap = _coerce_int_option(
            self.options.get("structureLateRecoveryCap"),
            default=1,
            minimum=0,
            maximum=1,
        )
        self.late_recovery_start_attempt = _coerce_int_option(
            self.options.get("structureLateRecoveryStartAttempt"),
            default=3,
            minimum=2,
            maximum=self.max_retries + 1,
        )
        self.llm_retries_per_attempt = _coerce_int_option(
            self.options.get("structureLlmRetriesPerAttempt"),
            default=1,
            minimum=1,
            maximum=2,
        )

    def _sanitize_target_word_count(self, target_word_count: Any) -> int:
        try:
            parsed = int(float(target_word_count))
        except (TypeError, ValueError):
            return int(STRUCTURE_SPEC['idealTotalMin'])
        return max(1600, min(parsed, 3200))

    def _build_length_spec(self, target_word_count: Any, stance_count: int = 0, *, reference_text_len: int = 0) -> Dict[str, int]:
        target_chars = self._sanitize_target_word_count(target_word_count)
        section_char_target = int(STRUCTURE_SPEC['sectionCharTarget'])
        section_char_min = int(STRUCTURE_SPEC['sectionCharMin'])
        section_char_max = int(STRUCTURE_SPEC['sectionCharMax'])
        min_sections = int(STRUCTURE_SPEC['minSections'])
        max_sections = int(STRUCTURE_SPEC['maxSections'])
        ideal_total_min = int(STRUCTURE_SPEC['idealTotalMin'])
        ideal_total_max = int(STRUCTURE_SPEC['idealTotalMax'])
        paragraphs_per_section = int(STRUCTURE_SPEC['paragraphsPerSection'])

        # 섹션당 350자 내외를 기준으로 5~7섹션 계획
        total_sections = round(target_chars / section_char_target)
        total_sections = max(min_sections, min(max_sections, total_sections))
        if stance_count > 0:
            total_sections = max(total_sections, min(max_sections, stance_count + 2))
        # 참고자료가 풍부하면 섹션 수 상향
        if reference_text_len > 1200:
            total_sections = max(total_sections, min(max_sections, min_sections + 1))
        if reference_text_len > int(STRUCTURE_SPEC['idealTotalMin']):
            total_sections = min(max_sections, total_sections + 1)

        body_sections = total_sections - 2
        per_section_recommended = max(section_char_min, min(section_char_max, round(target_chars / total_sections)))
        per_section_min = max(section_char_min - 50, per_section_recommended - 50)
        per_section_max = min(section_char_max + 50, per_section_recommended + 50)

        min_chars = max(int(target_chars * 0.88), total_sections * per_section_min)
        # 상한은 기본 분량(2000자 기준)에서 3000자까지 허용하도록 고정 캡을 둔다.
        # - 기존: 2000자 기준 약 2250자
        # - 변경: 최대 3000자
        if target_chars >= ideal_total_min:
            max_chars = ideal_total_max + 200
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
            'paragraphs_per_section': paragraphs_per_section
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

    def _build_structure_json_schema(self, length_spec: Dict[str, int]) -> Dict[str, Any]:
        paragraph_schema: Dict[str, Any] = {"type": "string"}
        body_sections = max(1, int(length_spec.get('body_sections') or 1))

        return {
            "type": "object",
            "required": ["title", "intro", "body", "conclusion"],
            "properties": {
                "title": {"type": "string", "minLength": 12, "maxLength": 80},
                "intro": {
                    "type": "object",
                    "required": ["paragraphs"],
                    "properties": {
                        "paragraphs": {
                            "type": "array",
                            "minItems": 1,
                            "items": paragraph_schema,
                        }
                    },
                },
                "body": {
                    "type": "array",
                    "minItems": body_sections,
                    "maxItems": body_sections,
                    "items": {
                        "type": "object",
                        "required": ["heading", "paragraphs"],
                        "properties": {
                            "heading": {
                                "type": "string",
                            },
                            "paragraphs": {
                                "type": "array",
                                "minItems": 1,
                                "items": paragraph_schema,
                            },
                        },
                    },
                },
                "conclusion": {
                    "type": "object",
                    "required": ["heading", "paragraphs"],
                    "properties": {
                        "heading": {
                            "type": "string",
                        },
                        "paragraphs": {
                            "type": "array",
                            "minItems": 2,
                            "items": paragraph_schema,
                        },
                    },
                },
                "hashtags": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {"type": "string", "minLength": 2, "maxLength": 30},
                },
            },
        }

    def _build_outline_json_schema(self, length_spec: Dict[str, int]) -> Dict[str, Any]:
        """AEO 2단계 생성의 1단계: 아웃라인(제목+소제목+첫 문장)만 요청하는 스키마."""
        body_sections = max(1, int(length_spec.get('body_sections') or 1))
        return {
            "type": "object",
            "required": ["title", "intro_lead", "body", "conclusion_heading"],
            "properties": {
                "title": {"type": "string", "minLength": 12, "maxLength": 80},
                "intro_lead": {
                    "type": "string",
                    "description": "서론 첫 문단: 인사(1문장) + 핵심 결론(1~2문장). AI 답변 엔진이 이 문단만 추출해도 답이 되어야 한다.",
                    "minLength": 40,
                    "maxLength": 300,
                },
                "body": {
                    "type": "array",
                    "minItems": body_sections,
                    "maxItems": body_sections,
                    "items": {
                        "type": "object",
                        "required": ["heading", "lead_sentence"],
                        "properties": {
                            "heading": {"type": "string"},
                            "lead_sentence": {
                                "type": "string",
                                "description": "이 섹션의 핵심 주장·해법·결론을 첫 문장으로 직접 선언. 문제 진단·배경 설명·현황 묘사로 시작하지 말 것.",
                                "minLength": 20,
                                "maxLength": 200,
                            },
                        },
                    },
                },
                "conclusion_heading": {"type": "string"},
            },
        }

    def _build_structure_json_prompt(self, *, prompt: str, length_spec: Dict[str, int]) -> str:
        body_sections = max(1, int(length_spec.get('body_sections') or 1))
        total_sections = max(3, int(length_spec.get('total_sections') or (body_sections + 2)))
        section_paragraphs = _coerce_int_option(
            length_spec.get('paragraphs_per_section'),
            default=int(STRUCTURE_SPEC['paragraphsPerSection']),
            minimum=2,
            maximum=4,
        )
        per_section_min = int(length_spec.get('per_section_min') or STRUCTURE_SPEC['sectionCharMin'])
        per_section_max = int(length_spec.get('per_section_max') or STRUCTURE_SPEC['sectionCharMax'])
        min_chars = int(length_spec.get('min_chars') or STRUCTURE_SPEC['idealTotalMin'])
        max_chars = int(length_spec.get('max_chars') or STRUCTURE_SPEC['idealTotalMax'])

        return (
            f"{prompt}\n\n"
            "<json_output_contract priority=\"critical\">\n"
            "  <override>기존 XML output_format 지시는 무시하고, 최종 응답은 JSON 객체 1개만 출력하십시오.</override>\n"
            f"  <structure>총 섹션 {total_sections}개(서론 1 + 본론 {body_sections} + 결론 1), 섹션별 문단 {section_paragraphs}개 고정.</structure>\n"
            f"  <length>원고 전체 {min_chars}~{max_chars}자, 섹션당 {per_section_min}~{per_section_max}자 범위 준수.</length>\n"
            "  <rules>\n"
            "    <rule>코드블록(```) 금지, 설명문 금지, JSON 외 텍스트 금지.</rule>\n"
            "    <rule>intro에는 heading 필드를 넣지 말고 paragraphs만 작성.</rule>\n"
            "    <rule>body 각 항목은 heading 1개 + paragraphs 배열로 작성.</rule>\n"
            "    <rule>conclusion은 heading 1개 + paragraphs 배열로 작성하고 paragraphs는 최소 2개 이상 작성.</rule>\n"
            "    <rule>각 paragraphs 원소는 완결 문장 2~3개로 구성하고 최소 120자 이상 작성.</rule>\n"
            "    <rule>각 body/conclusion 항목은 paragraphs를 먼저 완성한 뒤 heading을 마지막에 작성.</rule>\n"
            "    <rule>heading은 바로 아래 paragraphs 첫 2문장이 실제로 말한 핵심을 선언형 또는 명사형으로 요약할 것. 본문 없이 heading을 먼저 확정하지 말 것.</rule>\n"
            "    <rule>heading을 확정하기 전에 조사나 단어가 중복되거나 의미가 덜 끝난 부분이 없는지 다시 읽고 고칠 것. 예: '도약을을', '민주당 민주당' 금지.</rule>\n"
            "    <rule>소제목에 '[인물명]의 [형용사형 어구]' 구조를 쓰지 말 것. 예: '[인물명]의 경제 대전환'처럼 이름 뒤 소유격만 앞세우지 말고, '경제 대전환 로드맵', '경제 대전환, [인물명]의 전략'처럼 의미가 완결되게 다시 쓸 것.</rule>\n"
            "    <rule>소제목이 '명사1과 명사2, 명사3 구도'처럼 서술어 없는 명사 나열로 끝나면 질문형('~은?', '~는?') 또는 서술형('~이다', '~해야')으로 바꿀 것.</rule>\n"
            "    <rule>소제목에 조사나 술어가 어색하게 잘린 경우('확신을 길', '진짜 승' 등) 반드시 고친 뒤 출력할 것.</rule>\n"
            "    <rule>소제목은 10~25자, \"위한/향한/만드는/통한/대한\" 수식어 금지.</rule>\n"
            "    <rule>소제목에 '저는/제가/나는/내가' 같은 1인칭 표현 금지.</rule>\n"
            "    <rule>어느 body/conclusion 섹션이 비어 보이거나 설명이 모자라면, 독자가 '그래서 구체적으로 어떻게 할 건데?'라고 물을 지점을 찾아 그 섹션에만 구체 문장 1개 이상을 더할 것. 어떤 후보나 어떤 선거에도 쓸 수 있는 일반 공약 문장은 추가하지 말 것.</rule>\n"
            "    <rule>새 섹션 첫 문장을 쓸 때는 직전 섹션 마지막 2문장의 흐름을 이어받을 것. '이는', '이러한', '이것은'으로 시작한다면 그 지시 대상이 직전 섹션에 실제로 있는지 스스로 확인하고, 없으면 명시적 주어로 다시 쓸 것.</rule>\n"
            "    <rule>JSON 문자열 안에 큰따옴표(\")를 직접 쓰지 말 것. 인용이 필요하면 작은따옴표(') 또는 괄호를 사용.</rule>\n"
            "    <rule>각 문자열 값은 한 줄로 작성하고 줄바꿈 문자를 넣지 말 것.</rule>\n"
            "    <rule>역슬래시(\\)를 임의로 출력하지 말 것.</rule>\n"
            "  </rules>\n"
            "  <json_shape><![CDATA[\n"
            "{\n"
            "  \"title\": \"...\",\n"
            "  \"intro\": {\"paragraphs\": [\"...\", \"...\", \"...\"]},\n"
            "  \"body\": [\n"
            "    {\"heading\": \"...\", \"paragraphs\": [\"...\", \"...\", \"...\"]}\n"
            "  ],\n"
            "  \"conclusion\": {\"heading\": \"...\", \"paragraphs\": [\"...\", \"...\", \"...\"]}\n"
            "}\n"
            "  ]]></json_shape>\n"
            "</json_output_contract>"
        )

    def _build_expansion_json_prompt(
        self,
        *,
        outline: Dict[str, Any],
        base_prompt: str,
        length_spec: Dict[str, int],
    ) -> str:
        """AEO 2단계 생성의 2단계: 아웃라인을 고정한 채 본문 확장을 요청하는 프롬프트."""
        body_lines = []
        for i, section in enumerate(outline.get('body', []), 1):
            body_lines.append(
                f'  <body_section order="{i}">\n'
                f'    <heading>{section["heading"]}</heading>\n'
                f'    <lead_sentence>{section["lead_sentence"]}</lead_sentence>\n'
                f'  </body_section>'
            )
        body_block = "\n".join(body_lines)

        lock_block = (
            '<locked_outline priority="absolute">\n'
            f'  <title>{outline["title"]}</title>\n'
            f'  <intro_lead>{outline["intro_lead"]}</intro_lead>\n'
            f'{body_block}\n'
            f'  <conclusion_heading>{outline["conclusion_heading"]}</conclusion_heading>\n'
            '</locked_outline>\n\n'
            '<expansion_instructions priority="critical">\n'
            '  위 locked_outline의 title, heading, lead_sentence, conclusion_heading은 그대로 사용하고 절대 수정하지 마십시오.\n'
            '  서론(intro) 첫 문단은 intro_lead 텍스트를 그대로 첫 문단으로 사용하십시오.\n'
            '  각 본론(body) 섹션의 heading을 소제목으로, lead_sentence를 첫 문단 첫 문장으로 사용하십시오.\n'
            '  각 섹션을 나머지 문단으로 확장하되, lead_sentence의 주장을 근거·맥락·효과로 뒷받침하십시오.\n'
            '  결론(conclusion)은 conclusion_heading을 소제목으로 사용하십시오.\n'
            '</expansion_instructions>\n\n'
        )

        modified_prompt = lock_block + base_prompt
        return self._build_structure_json_prompt(
            prompt=modified_prompt,
            length_spec=length_spec,
        )

    async def call_llm_json(self, prompt: str, *, length_spec: Dict[str, int]) -> Dict[str, Any]:
        response_schema = self._build_structure_json_schema(length_spec)
        return await self.call_llm_json_contract(
            prompt,
            response_schema=response_schema,
            required_keys=("title", "intro", "body", "conclusion"),
            stage="legacy-full",
            max_output_tokens=8192,
        )

    async def call_llm_json_contract(
        self,
        prompt: str,
        *,
        response_schema: Dict[str, Any],
        required_keys: Tuple[str, ...],
        stage: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:
        from ..common.gemini_client import StructuredOutputError, generate_json_async

        print(f"📤 [StructureAgent] LLM JSON 호출 시작 (stage={stage})")
        start_time = time.time()
        call_retries = max(1, int(self.llm_retries_per_attempt or 1))

        try:
            payload = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.0,
                max_output_tokens=max_output_tokens,
                retries=call_retries,
                response_schema=response_schema,
                required_keys=required_keys,
                options={"json_parse_retries": 2},
            )
            elapsed = time.time() - start_time
            print(f"✅ [StructureAgent] LLM JSON 응답 완료 (stage={stage}, {elapsed:.1f}초)")
            return payload
        except StructuredOutputError as e:
            elapsed = time.time() - start_time
            print(f"❌ [StructureAgent] LLM JSON 계약 실패 (stage={stage}, {elapsed:.1f}초): {e}")
            raise Exception(f"구조 JSON 계약 위반({stage}): {e}")
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"❌ [StructureAgent] LLM JSON 호출 실패 (stage={stage}, {elapsed:.1f}초): {error_msg}")
            if 'timeout' in error_msg.lower() or 'deadline' in error_msg.lower():
                raise Exception(f"LLM 호출 타임아웃 ({elapsed:.1f}초). Gemini API가 응답하지 않습니다.")
            raise

    async def call_llm(self, prompt: str) -> str:
        from ..common.gemini_client import generate_content_async

        print(f"📤 [StructureAgent] LLM 호출 시작")
        start_time = time.time()

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.1,  # 구조 준수율을 높이기 위해 변동성 축소
                max_output_tokens=4096,
                retries=self.llm_retries_per_attempt,
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
        current_title = user_profile.get('customTitle') or self._format_position_with_region(user_profile)
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

    @staticmethod
    def _format_position_with_region(user_profile: Dict) -> str:
        """position + regionMetro/regionLocal을 조합해 공식 직함을 생성한다.

        예: position="광역의원", regionMetro="인천광역시" → "인천광역시의원"
        """
        position = (user_profile.get('position') or '').strip()
        region_metro = (user_profile.get('regionMetro') or '').strip()
        region_local = (user_profile.get('regionLocal') or '').strip()

        if position == '광역의원' and region_metro:
            return f"{region_metro}의원"
        if position == '기초의원':
            if region_local:
                return f"{region_local}의원"
            if region_metro:
                return f"{region_metro}의원"
        if position == '광역자치단체장' and region_metro:
            return f"{region_metro}장"
        if position == '기초자치단체장' and region_local:
            return f"{region_local}장"

        return position

    def is_current_lawmaker(self, user_profile: Dict) -> bool:
        # position은 _canonical_position으로 국회의원/광역의원/기초의원/...으로
        # 정규화돼 저장되므로 완전 일치만 본다.
        if not user_profile or not isinstance(user_profile, dict):
            return False
        position = str(user_profile.get('position') or '').strip()
        return position == '국회의원'
