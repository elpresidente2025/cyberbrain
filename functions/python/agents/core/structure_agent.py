
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
from ..common.editorial import STRUCTURE_SPEC
from ..common.h2_guide import H2_MIN_LENGTH, H2_MAX_LENGTH
from ..templates.intelligent_selector import select_prompt_parameters

logger = logging.getLogger(__name__)


from ..base_agent import Agent

from .structure_utils import (
    strip_html, normalize_artifacts, normalize_html_structure_tags,
    normalize_context_text, split_into_context_items
)
from .prompt_builder import build_structure_prompt, build_retry_directive
from .content_validator import ContentValidator
from .content_repair import ContentRepairAgent
from .context_analyzer import ContextAnalyzer
from .structure_normalizer import normalize_structure


def _coerce_int_option(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


class StructureAgent(Agent):
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
                            "items": paragraph_schema,
                        }
                    },
                },
                "body": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["heading", "paragraphs"],
                        "properties": {
                            "heading": {
                                "type": "string",
                            },
                            "paragraphs": {
                                "type": "array",
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
            "    <rule>conclusion은 heading 1개 + paragraphs 배열로 작성.</rule>\n"
            "    <rule>각 paragraphs 원소는 완결 문장 2~3개로 구성하고 최소 120자 이상 작성.</rule>\n"
            "    <rule>소제목은 10~25자, \"위한/향한/만드는/통한/대한\" 수식어 금지.</rule>\n"
            "    <rule>소제목에 '저는/제가/나는/내가' 같은 1인칭 표현 금지.</rule>\n"
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

    def _clean_plain_text(self, value: Any) -> str:
        text = normalize_context_text(value, sep=' ')
        text = re.sub(r'<[^>]*>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _sanitize_heading_text(self, heading: Any) -> str:
        text = self._clean_plain_text(heading)
        if not text:
            raise ValueError("구조 JSON 계약 위반: 소제목이 비어 있습니다.")
        if self._BANNED_FIRST_PERSON_HEADING_PATTERN.search(text):
            raise ValueError(f"구조 JSON 계약 위반: 소제목 1인칭 표현 금지('{text}')")
        text = re.sub(r'(위한|향한|만드는|통한|대한)(\s|$)', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip(' -_.,')
        if len(text) > H2_MAX_LENGTH:
            text = text[:H2_MAX_LENGTH].rstrip(' -_.,')
        if len(text) < H2_MIN_LENGTH:
            raise ValueError(f"구조 JSON 계약 위반: 소제목 길이 부족({len(text)}자)")
        return text

    def _normalize_section_paragraphs(
        self,
        paragraphs: Any,
        *,
        target_count: int,
    ) -> List[str]:
        candidates = paragraphs if isinstance(paragraphs, list) else [paragraphs]
        cleaned_list: List[str] = []
        for item in candidates:
            cleaned = self._clean_plain_text(item)
            if cleaned:
                cleaned_list.append(cleaned)

        if len(cleaned_list) > target_count:
            keep = cleaned_list[: target_count - 1]
            tail = " ".join(cleaned_list[target_count - 1 :]).strip()
            if tail:
                keep.append(tail)
            cleaned_list = keep

        if len(cleaned_list) < target_count:
            print(
                f"⚠️ [StructureAgent] 문단 수 부족({len(cleaned_list)}개, "
                f"요구 {target_count}개) — 있는 만큼 사용, normalize_section_p_count가 보정"
            )

        return cleaned_list[:target_count]

    def _build_html_from_structure_json(
        self,
        payload: Dict[str, Any],
        *,
        length_spec: Dict[str, int],
        topic: str,
    ) -> Tuple[str, str]:
        section_paragraphs = _coerce_int_option(
            length_spec.get('paragraphs_per_section'),
            default=int(STRUCTURE_SPEC['paragraphsPerSection']),
            minimum=2,
            maximum=4,
        )
        body_sections = max(1, int(length_spec.get('body_sections') or 1))

        title = self._clean_plain_text(payload.get('title'))
        if not title:
            title = (topic or "새 원고").strip()[:40]

        intro_payload = payload.get('intro')
        if not isinstance(intro_payload, dict):
            raise ValueError("구조 JSON 계약 위반: intro 객체가 누락되었습니다.")
        intro_paragraphs = self._normalize_section_paragraphs(
            intro_payload.get('paragraphs'),
            target_count=section_paragraphs,
        )

        body_payload = payload.get('body')
        if not isinstance(body_payload, list):
            raise ValueError("구조 JSON 계약 위반: body 배열이 누락되었습니다.")
        conclusion_payload = payload.get('conclusion')
        if not isinstance(conclusion_payload, dict):
            raise ValueError("구조 JSON 계약 위반: conclusion 객체가 누락되었습니다.")

        html_parts: List[str] = []
        for paragraph in intro_paragraphs:
            html_parts.append(f"<p>{paragraph}</p>")

        for index in range(body_sections):
            if index >= len(body_payload) or not isinstance(body_payload[index], dict):
                raise ValueError(
                    f"구조 JSON 계약 위반: 본론 섹션 누락({index + 1}/{body_sections})"
                )
            section = body_payload[index]
            heading = self._sanitize_heading_text(section.get('heading'))
            html_parts.append(f"<h2>{heading}</h2>")
            section_paragraph_list = self._normalize_section_paragraphs(
                section.get('paragraphs'),
                target_count=section_paragraphs,
            )
            for paragraph in section_paragraph_list:
                html_parts.append(f"<p>{paragraph}</p>")

        conclusion_heading = self._sanitize_heading_text(conclusion_payload.get('heading'))
        html_parts.append(f"<h2>{conclusion_heading}</h2>")
        conclusion_paragraphs = self._normalize_section_paragraphs(
            conclusion_payload.get('paragraphs'),
            target_count=section_paragraphs,
        )
        for paragraph in conclusion_paragraphs:
            html_parts.append(f"<p>{paragraph}</p>")

        content = "\n".join(html_parts).strip()
        return content, title

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
        poll_focus_bundle = context.get('pollFocusBundle') if isinstance(context.get('pollFocusBundle'), dict) else {}
        focused_news_context = normalize_context_text(poll_focus_bundle.get('focusedSourceText'), sep="\n")
        source_instructions = normalize_context_text(stance_text)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(instructions)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(topic)
        effective_news_context = focused_news_context or news_data_text or news_context
        target_word_count = context.get('targetWordCount', int(STRUCTURE_SPEC['idealTotalMin']))
        user_keywords = context.get('userKeywords', [])
        personalized_hints = normalize_context_text(context.get('personalizedHints', ''), sep="\n")
        memory_context = normalize_context_text(context.get('memoryContext', ''), sep="\n")
        personalization_context = normalize_context_text([personalized_hints, memory_context], sep="\n")
        style_guide = normalize_context_text(context.get('styleGuide', ''), sep="\n")
        style_fingerprint = context.get('styleFingerprint') if isinstance(context.get('styleFingerprint'), dict) else {}
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

        prompt_variation_params: Dict[str, Any] = {}
        if category == 'educational-content':
            try:
                selected = select_prompt_parameters(
                    category='educational-content',
                    topic=topic,
                    instructions=source_instructions,
                )
                if isinstance(selected, dict):
                    prompt_variation_params = selected
                if prompt_variation_params:
                    print(f"🎛️ [StructureAgent] 교육 카테고리 배리에이션 적용: {prompt_variation_params}")
            except Exception as e:
                print(f"⚠️ [StructureAgent] 교육 카테고리 배리에이션 선택 실패: {str(e)}")

        # 5. Build Prompt
        rag_context = normalize_context_text(context.get('ragContext', ''))
        prompt_params: Dict[str, Any] = {
            'topic': topic,
            'category': category,
            'writingMethod': writing_method,
            'authorName': author_name,
            'authorBio': author_bio,
            'instructions': source_instructions,
            'newsContext': effective_news_context,
            'ragContext': rag_context,
            'targetWordCount': target_word_count,
            'partyStanceGuide': party_stance_guide,
            'contextAnalysis': context_analysis,
            'userProfile': user_profile,
            'personalizationContext': personalization_context,
            'memoryContext': memory_context,
            'styleGuide': style_guide,
            'styleFingerprint': style_fingerprint,
            'profileSupportContext': profile_support_context,
            'profileSubstituteContext': profile_substitute.get('contextText') if isinstance(profile_substitute, dict) else '',
            'newsSourceMode': news_source_mode,
            'userKeywords': user_keywords,
            'pollFocusBundle': poll_focus_bundle,
            'lengthSpec': length_spec,
            'outputMode': 'json',
        }
        if prompt_variation_params:
            prompt_params.update(prompt_variation_params)
        prompt = build_structure_prompt(prompt_params)

        print(f"📝 [StructureAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

        # 6. Retry Loop
        max_retries = self.max_retries
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
            'SECTION_P_COUNT',
            'H2_MALFORMED',
            'P_MALFORMED',
            'TAG_DISALLOWED',
            'DUPLICATE_SENTENCE',
            'PHRASE_REPEAT',
            'VERB_REPEAT',
            'PHRASE_REPEAT_CAP',
            'MATERIAL_REUSE',
            'INTRO_STANCE_MISSING',
            'INTRO_CONCLUSION_ECHO',
            'LOCATION_ORPHAN_REPEAT',
            'META_PROMPT_LEAK',
            'EVENT_FACT_REPEAT',
            'EVENT_INVITE_REDUNDANT',
            'SECTION_LENGTH',
            'H2_TEXT_LONG',
            'H2_TEXT_MODIFIER',
            'H2_TEXT_FIRST_PERSON',
            'H2_TEXT_SHORT',
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

        def _evaluate_candidate_with_normalizer(
            candidate_content: str,
            candidate_title: str,
            *,
            source: str,
            source_attempt: int,
        ) -> Tuple[str, Dict[str, Any], str]:
            structural_gate_codes = {
                'LENGTH_SHORT',
                'LENGTH_LONG',
                'H2_SHORT',
                'H2_LONG',
                'SECTION_P_COUNT',
                'P_SHORT',
                'P_LONG',
                'SECTION_LENGTH',
                'H2_MALFORMED',
                'P_MALFORMED',
                'TAG_DISALLOWED',
                'H2_TEXT_SHORT',
                'H2_TEXT_LONG',
                'H2_TEXT_MODIFIER',
                'H2_TEXT_FIRST_PERSON',
            }

            def _failure_stage(validation_result: Dict[str, Any]) -> int:
                if validation_result.get('passed'):
                    return 3
                code = str(validation_result.get('code') or '')
                if code in structural_gate_codes:
                    return 0
                return 1

            base_content = normalize_artifacts(candidate_content)
            base_content = normalize_html_structure_tags(base_content)
            raw_validation = self.validator.validate(
                base_content,
                length_spec,
                context_analysis=context_analysis,
                is_event_announcement=is_event_announcement,
                event_date_hint=event_date_hint,
                event_location_hint=event_location_hint,
            )
            raw_rank = _candidate_rank(raw_validation, base_content)
            raw_source = f"{source}-raw"
            _remember_best(base_content, candidate_title, raw_validation, source=raw_source, source_attempt=source_attempt)

            normalized_content = normalize_structure(
                base_content,
                length_spec,
                user_keywords=user_keywords,
                context_analysis=context_analysis,
            )
            normalized_validation = self.validator.validate(
                normalized_content,
                length_spec,
                context_analysis=context_analysis,
                is_event_announcement=is_event_announcement,
                event_date_hint=event_date_hint,
                event_location_hint=event_location_hint,
            )
            normalized_rank = _candidate_rank(normalized_validation, normalized_content)
            _remember_best(normalized_content, candidate_title, normalized_validation, source=source, source_attempt=source_attempt)

            if raw_validation.get('passed') and not normalized_validation.get('passed'):
                print(
                    f"⚠️ [StructureAgent] 정규화 후 품질 퇴행 감지: "
                    f"raw=PASS, normalized=FAIL({normalized_validation.get('code')})"
                )
                return base_content, raw_validation, raw_source

            if normalized_validation.get('passed') and not raw_validation.get('passed'):
                print(
                    f"✅ [StructureAgent] 정규화 교정 성공: "
                    f"raw=FAIL({raw_validation.get('code')}), normalized=PASS"
                )
                return normalized_content, normalized_validation, source

            raw_stage = _failure_stage(raw_validation)
            normalized_stage = _failure_stage(normalized_validation)
            if normalized_stage > raw_stage:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧭 [StructureAgent] 단계 우선 선택(normalized): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return normalized_content, normalized_validation, source
            if raw_stage > normalized_stage:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧭 [StructureAgent] 단계 우선 선택(raw): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return base_content, raw_validation, raw_source

            if raw_rank >= normalized_rank:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧪 [StructureAgent] 후보 선택(raw 우선): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return base_content, raw_validation, raw_source

            if raw_validation.get('code') != normalized_validation.get('code'):
                print(
                    f"🧪 [StructureAgent] 후보 선택(normalized 우선): "
                    f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                )
            return normalized_content, normalized_validation, source

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
                json_prompt = self._build_structure_json_prompt(
                    prompt=current_prompt,
                    length_spec=length_spec,
                )
                response_schema = self._build_structure_json_schema(length_spec)
                payload = await self.call_llm_json_contract(
                    json_prompt,
                    response_schema=response_schema,
                    required_keys=("title", "intro", "body", "conclusion"),
                    stage="structure",
                    max_output_tokens=8192,
                )
                raw_content, title = self._build_html_from_structure_json(
                    payload,
                    length_spec=length_spec,
                    topic=topic,
                )
                raw_content = normalize_artifacts(raw_content)
                raw_content = normalize_html_structure_tags(raw_content)
                title = normalize_artifacts(title)

                plain_len = len(strip_html(raw_content))
                body_sections = len(payload.get('body') or []) if isinstance(payload, dict) else 0
                print(
                    f"📐 [StructureAgent] 시도 {attempt} 길이: "
                    f"json_body_sections={body_sections}, parsed={len(raw_content)}자, plain={plain_len}자"
                )
                if plain_len < 400:
                    raise Exception(f"JSON 구조 결과가 비정상적으로 짧습니다 ({plain_len}자)")

                content, validation, selected_source = _evaluate_candidate_with_normalizer(
                    raw_content,
                    title,
                    source='draft',
                    source_attempt=attempt,
                )

                if validation['passed']:
                    print(f"✅ [StructureAgent] 검증 통과({selected_source}): {len(strip_html(content))}자")
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
                if str(validation.get('code') or '') == 'DUPLICATE_SENTENCE':
                    dup_samples = validation.get('duplicateSamples') or []
                    dup_count = validation.get('duplicateCount')
                    print(
                        f"🔎 [StructureAgent] DUPLICATE_SENTENCE details: "
                        f"count={dup_count}, samples={dup_samples}"
                    )
                if str(validation.get('code') or '') == 'INTRO_CONCLUSION_ECHO':
                    dup_samples = validation.get('duplicatePhrases') or []
                    dup_count = validation.get('duplicateCount')
                    print(
                        f"🔎 [StructureAgent] INTRO_CONCLUSION_ECHO details: "
                        f"count={dup_count}, samples={dup_samples}"
                    )

                recovery_code = str(validation.get('code') or '')
                recovery_content = content
                recovery_title = title
                recovery_validation = dict(validation or {})
                if recovery_code == 'LENGTH_SHORT':
                    max_recovery_rounds = self.length_recovery_rounds
                elif recovery_code in structural_recoverable_codes:
                    max_recovery_rounds = self.structural_recovery_rounds
                else:
                    max_recovery_rounds = 0

                # 후반 시도에서는 복구 루프를 1회로 제한해 꼬리 지연을 줄인다.
                if attempt >= self.late_recovery_start_attempt:
                    max_recovery_rounds = min(max_recovery_rounds, self.late_recovery_cap)

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
                            failed_meta=dict(recovery_validation or {}),
                        )

                    if not recovery_result:
                        break

                    recovered_content, recovered_title = recovery_result
                    recovered_content, recovered_validation, recovered_source = _evaluate_candidate_with_normalizer(
                        recovered_content,
                        recovered_title,
                        source='repair',
                        source_attempt=attempt,
                    )
                    if recovered_validation.get('passed'):
                        print(
                            f"✅ [StructureAgent] 복구 검증 통과({recovered_source}): "
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
                    best_content = best_candidate.get('content', '')
                    best_title = best_candidate.get('title') or topic[:20] or '새 원고'
                    best_validation = best_candidate.get('validation') or {}
                    best_code = str(best_validation.get('code') or '').strip()
                    best_len = int(best_candidate.get('plain_len') or 0)
                    print(
                        f"⚠️ [StructureAgent] 검증 미통과 — best-effort 반환: "
                        f"code={best_code}, len={best_len}, "
                        f"source={best_candidate.get('source')}"
                    )
                    return {
                        'content': best_content,
                        'title': best_title,
                        'writingMethod': writing_method,
                        'contextAnalysis': context_analysis,
                    }
                final_reason = last_error or validation.get('reason', '알 수 없는 오류')
                raise Exception(f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason}")

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
