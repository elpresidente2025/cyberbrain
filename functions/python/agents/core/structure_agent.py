
import re
import json
import logging
import time
import random
from html import escape as _xml_escape_raw
from typing import Dict, Any, Optional, List, Tuple

# API Call Timeout (seconds)
LLM_CALL_TIMEOUT = 120  # 2분 타임아웃
CONTEXT_ANALYZER_TIMEOUT = 60  # 1분 타임아웃

# Local imports
from ..common.classifier import classify_topic
from ..common.warnings import generate_non_lawmaker_warning, generate_family_status_warning
from ..common.theminjoo import get_party_stance
from ..common.election_rules import get_election_stage, get_prompt_instruction
from ..common.seo import build_seo_instruction
from ..common.constants import resolve_writing_method

# Template Builders
from ..templates.daily_communication import build_daily_communication_prompt
from ..templates.activity_report import build_activity_report_prompt
from ..templates.policy_proposal import build_policy_proposal_prompt
from ..templates.current_affairs import build_critical_writing_prompt, build_diagnosis_writing_prompt
from ..templates.local_issues import build_local_issues_prompt

# Template Builders Mapping
TEMPLATE_BUILDERS = {
    'emotional_writing': build_daily_communication_prompt,
    'logical_writing': build_policy_proposal_prompt, # Mapped buildLogicalWritingPrompt to policy proposal
    'direct_writing': build_activity_report_prompt,
    'critical_writing': build_critical_writing_prompt,
    'diagnostic_writing': build_diagnosis_writing_prompt,
    'analytical_writing': build_local_issues_prompt
}

logger = logging.getLogger(__name__)

def strip_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]*>', '', text)
    return re.sub(r'\s+', '', text).strip()

def normalize_artifacts(text: str) -> str:
    if not text:
        return ''
    cleaned = text.strip()
    # 코드펜스가 감싸져 온 경우 본문을 보존한 채 펜스만 제거
    cleaned = re.sub(
        r'```(?:[\w.+-]+)?\s*([\s\S]*?)\s*```',
        lambda m: m.group(1).strip(),
        cleaned,
    ).strip()
    cleaned = re.sub(r'^\s*\\"', '', cleaned)
    cleaned = re.sub(r'\\"?\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*["“]', '', cleaned)
    cleaned = re.sub(r'["”]\s*$', '', cleaned)
    
    # Remove trailing metadata block only when marker appears near the tail as a standalone line.
    # (Do not truncate normal body text that happens to include "카테고리:" in a sentence.)
    lines = cleaned.splitlines()
    metadata_line_re = re.compile(
        r'^\s*\*{0,2}(카테고리|검색어 삽입 횟수|생성 시간)\*{0,2}\s*:\s*',
        re.IGNORECASE,
    )
    tail_cut_index = None
    if lines:
        tail_window_start = max(0, len(lines) - 8)
        for i in range(tail_window_start, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            # HTML line은 본문일 가능성이 높으므로 metadata 시작점으로 보지 않음
            if '<' in line and '>' in line:
                continue
            if metadata_line_re.match(line):
                tail_cut_index = i
                break
    if tail_cut_index is not None:
        cleaned = "\n".join(lines[:tail_cut_index]).strip()
    
    cleaned = re.sub(r'"content"\s*:\s*', '', cleaned)
    
    return cleaned.strip()


def normalize_html_structure_tags(text: str) -> str:
    """기본 구조 태그를 표준 형태로 정규화한다.

    엄격 기준은 유지하되, 모델이 생성한 부가 속성/대소문자 차이로
    구조 검증이 오탐으로 실패하는 상황을 줄인다.
    """
    if not text:
        return ''
    normalized = text
    normalized = re.sub(r'<\s*h2\b[^>]*>', '<h2>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*/\s*h2\s*>', '</h2>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*p\b[^>]*>', '<p>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*/\s*p\s*>', '</p>', normalized, flags=re.IGNORECASE)
    return normalized


def is_example_like_block(text: str) -> bool:
    """예시/템플릿 블록 여부를 판정한다.

    규칙 완화가 아니라, 모델이 프롬프트 예시를 그대로 재출력한 블록을
    본문 후보에서 제외하기 위한 방어 로직이다.
    """
    if not text:
        return True
    lowered = text.lower()
    placeholder_count = len(re.findall(r'\[[^\]\n]{1,40}\]', text))
    marker_count = sum(
        1
        for marker in (
            'sample_output',
            'reference_example',
            'placeholder',
            '예시',
            '샘플',
            '여기에',
            '작성',
        )
        if marker in lowered
    )
    plain_len = len(strip_html(text))
    return (
        placeholder_count >= 2
        or ('<![cdata[' in lowered and plain_len < 900)
        or (marker_count >= 1 and plain_len < 900)
    )


def normalize_context_text(value: Any, *, sep: str = "\n\n") -> str:
    """list/tuple 중첩 입력까지 안전하게 문자열로 정규화."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        parts: List[str] = []
        for item in value:
            normalized = normalize_context_text(item, sep=sep)
            if normalized:
                parts.append(normalized)
        return sep.join(parts)
    return str(value).strip()


def _xml_text(value: Any) -> str:
    return _xml_escape_raw(str(value or ""), quote=True)


def _xml_cdata(value: Any) -> str:
    text = str(value or "")
    safe = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe}]]>"

from ..base_agent import Agent

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

    def _sanitize_target_word_count(self, target_word_count: Any) -> int:
        try:
            parsed = int(float(target_word_count))
        except (TypeError, ValueError):
            return 2000
        return max(1600, min(parsed, 3200))

    def _build_length_spec(self, target_word_count: Any, stance_count: int = 0) -> Dict[str, int]:
        target_chars = self._sanitize_target_word_count(target_word_count)

        # 섹션당 400자 내외를 기준으로 5~7섹션 계획
        total_sections = round(target_chars / 400)
        total_sections = max(5, min(7, total_sections))
        if stance_count > 0:
            total_sections = max(total_sections, min(7, stance_count + 2))

        body_sections = total_sections - 2
        per_section_recommended = max(360, min(420, round(target_chars / total_sections)))
        per_section_min = max(320, per_section_recommended - 50)
        per_section_max = min(460, per_section_recommended + 50)

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
            'expected_h2': total_sections - 1
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

    def _split_into_context_items(self, text: str, *, min_len: int = 14, max_items: int = 40) -> List[str]:
        if not text:
            return []

        normalized = normalize_context_text(text, sep="\n")
        if not normalized:
            return []

        raw_parts = re.split(r'[\r\n]+|[;·•]+|(?<=[.!?。])\s+|다\.\s+', normalized)
        items: List[str] = []
        seen: set[str] = set()

        for part in raw_parts:
            cleaned = re.sub(r'\s+', ' ', str(part or "")).strip(" \t-•")
            if not cleaned:
                continue
            if len(strip_html(cleaned)) < min_len:
                continue
            if len(cleaned) > 220:
                cleaned = cleaned[:220].rstrip() + "..."
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(cleaned)
            if len(items) >= max_items:
                break

        return items

    def _material_key(self, value: Any) -> str:
        text = normalize_context_text(value)
        if not text:
            return ""
        text = strip_html(text).lower()
        text = re.sub(r'["\'`“”‘’\[\]\(\)<>]', '', text)
        text = re.sub(r'[\s\.,!?;:·~\-_\\/]+', '', text)
        return text

    def _normalize_context_analysis_materials(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(analysis, dict):
            return {}

        normalized_analysis = dict(analysis)

        stance_items: List[Dict[str, str]] = []
        stance_seen: set[str] = set()
        raw_stance = normalized_analysis.get('mustIncludeFromStance')
        if isinstance(raw_stance, list):
            for item in raw_stance:
                if isinstance(item, dict):
                    topic = normalize_context_text(item.get('topic'))
                    why_txt = normalize_context_text(item.get('expansion_why'))
                    how_txt = normalize_context_text(item.get('expansion_how'))
                    effect_txt = normalize_context_text(item.get('expansion_effect'))
                else:
                    topic = normalize_context_text(item)
                    why_txt = ""
                    how_txt = ""
                    effect_txt = ""

                if len(strip_html(topic)) < 5:
                    continue

                key = self._material_key(topic)
                if not key or key in stance_seen:
                    continue

                stance_seen.add(key)
                stance_items.append(
                    {
                        'topic': topic,
                        'expansion_why': why_txt,
                        'expansion_how': how_txt,
                        'expansion_effect': effect_txt,
                    }
                )
                if len(stance_items) >= 6:
                    break

        normalized_analysis['mustIncludeFromStance'] = stance_items

        def dedupe_text_list(
            raw_values: Any,
            *,
            blocked_keys: Optional[set[str]] = None,
            max_items: int = 8,
        ) -> Tuple[List[str], set[str]]:
            blocked = blocked_keys or set()
            results: List[str] = []
            keys: set[str] = set()
            if not isinstance(raw_values, list):
                return results, keys

            for raw in raw_values:
                text = normalize_context_text(raw)
                if len(strip_html(text)) < 8:
                    continue
                key = self._material_key(text)
                if not key or key in blocked or key in keys:
                    continue
                keys.add(key)
                results.append(text)
                if len(results) >= max_items:
                    break
            return results, keys

        stance_keys = {self._material_key(item.get('topic')) for item in stance_items if isinstance(item, dict)}
        stance_keys.discard("")

        facts, fact_keys = dedupe_text_list(
            normalized_analysis.get('mustIncludeFacts'),
            blocked_keys=stance_keys,
            max_items=8,
        )
        normalized_analysis['mustIncludeFacts'] = facts

        quotes, _quote_keys = dedupe_text_list(
            normalized_analysis.get('newsQuotes'),
            blocked_keys=stance_keys.union(fact_keys),
            max_items=8,
        )
        normalized_analysis['newsQuotes'] = quotes

        return normalized_analysis

    def _build_material_uniqueness_guard(
        self,
        context_analysis: Optional[Dict[str, Any]],
        *,
        body_sections: int,
    ) -> str:
        if not isinstance(context_analysis, dict):
            return ""

        cards: List[Dict[str, str]] = []
        seen: set[str] = set()

        def add_card(card_type: str, raw_text: Any) -> None:
            text = normalize_context_text(raw_text)
            if len(strip_html(text)) < 8:
                return
            key = self._material_key(text)
            if not key or key in seen:
                return
            seen.add(key)
            cards.append({"type": card_type, "text": text})

        for item in context_analysis.get('mustIncludeFromStance') or []:
            if isinstance(item, dict):
                add_card("stance", item.get('topic'))
            else:
                add_card("stance", item)
        for item in context_analysis.get('mustIncludeFacts') or []:
            add_card("fact", item)
        for item in context_analysis.get('newsQuotes') or []:
            add_card("quote", item)

        if not cards:
            return ""

        body_count = max(1, int(body_sections or 1))
        max_cards = max(4, min(len(cards), body_count + 3))
        selected = cards[:max_cards]
        lines: List[str] = []
        for idx, card in enumerate(selected):
            section_slot = (idx % body_count) + 1
            lines.append(
                f'    <material id="M{idx + 1}" type="{card["type"]}" '
                f'section_hint="body_{section_slot}">{_xml_text(card["text"])}</material>'
            )

        allocated_count = min(body_count, len(selected))
        allocation_lines: List[str] = []
        for idx in range(allocated_count):
            allocation_lines.append(
                f'    <section index="{idx + 1}" use="M{idx + 1}" mode="exclusive_once"/>'
            )

        if body_count > allocated_count:
            banned_ids = ",".join(f"M{idx + 1}" for idx in range(allocated_count))
            for idx in range(allocated_count, body_count):
                allocation_lines.append(
                    f'    <section index="{idx + 1}" use="DERIVED" mode="new_evidence_only" '
                    f'ban_ids="{banned_ids}"/>'
                )

        lines_text = "\n".join(lines)
        allocation_text = "\n".join(allocation_lines)
        return f"""
<material_uniqueness_guard priority="critical">
  <rule id="one_material_one_use">소재 카드는 본문 전체에서 1회만 사용합니다.</rule>
  <rule id="follow_section_allocation">section_allocation 지시를 그대로 따르고, 이미 사용한 material id는 재사용 금지합니다.</rule>
  <rule id="no_recycled_quote">동일 인용/일화/근거 문장을 다른 섹션에서 다시 쓰지 않습니다.</rule>
  <rule id="body_diversity">각 본론 섹션은 서로 다른 근거를 사용해 논지를 전개합니다.</rule>
  <materials>
{lines_text}
  </materials>
  <section_allocation>
{allocation_text}
  </section_allocation>
</material_uniqueness_guard>
""".strip()

    def _detect_material_reuse_issues(
        self,
        content: str,
        context_analysis: Optional[Dict[str, Any]],
        *,
        max_mentions: int = 1,
    ) -> List[Dict[str, Any]]:
        if not content or not isinstance(context_analysis, dict):
            return []

        normalized_body = self._material_key(strip_html(content))
        if not normalized_body:
            return []

        candidates: List[Tuple[str, str]] = []
        for item in context_analysis.get('mustIncludeFromStance') or []:
            if isinstance(item, dict):
                candidates.append(("stance", normalize_context_text(item.get('topic'))))
            else:
                candidates.append(("stance", normalize_context_text(item)))
        for item in context_analysis.get('mustIncludeFacts') or []:
            candidates.append(("fact", normalize_context_text(item)))
        for item in context_analysis.get('newsQuotes') or []:
            candidates.append(("quote", normalize_context_text(item)))

        issues: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        for material_type, text in candidates:
            key = self._material_key(text)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            if len(key) < 16:
                continue
            count = normalized_body.count(key)
            if count > max_mentions:
                issues.append(
                    {
                        "type": material_type,
                        "text": text,
                        "count": count,
                    }
                )
        return issues

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
            for snippet in self._split_into_context_items(flattened, min_len=14, max_items=8):
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
                item for item in self._split_into_context_items(bio_text, min_len=12, max_items=24)
                if item not in selected_items
            ]
            if bio_pool:
                bio_selected = rng.sample(bio_pool, min(needed, len(bio_pool)))
                selected_items.extend(bio_selected)
                needed = max(0, target - len(selected_items))

        if needed > 0:
            support_text = self._build_profile_support_context(user_profile, max_chars=1800)
            support_pool = [
                item for item in self._split_into_context_items(support_text, min_len=10, max_items=24)
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

    def _build_retry_directive(self, validation: Dict[str, Any], length_spec: Dict[str, int]) -> str:
        code = validation.get('code')
        total_sections = length_spec['total_sections']
        body_sections = length_spec['body_sections']
        min_chars = length_spec['min_chars']
        max_chars = length_spec['max_chars']
        per_section_recommended = length_spec['per_section_recommended']
        expected_h2 = length_spec['expected_h2']

        if code == 'LENGTH_SHORT':
            return (
                f"재작성 시 총 분량을 {min_chars}~{max_chars}자로 맞추십시오. "
                f"총 섹션은 도입 1 + 본론 {body_sections} + 결론 1(총 {total_sections})로 유지하고, "
                f"섹션당 {per_section_recommended}자 내외로 보강하십시오."
            )

        if code == 'LENGTH_LONG':
            return (
                f"재작성 시 총 분량을 {max_chars}자 이하로 압축하십시오(절대 초과 금지). "
                f"중복 문장, 수식어, 유사 사례를 제거하고 섹션당 {per_section_recommended}자 내외로 간결하게 작성하십시오."
            )

        if code in {'H2_SHORT', 'H2_LONG'}:
            return (
                f"섹션 구조를 정확히 맞추십시오: 도입 1 + 본론 {body_sections} + 결론 1. "
                f"<h2>는 본론과 결론에만 사용하여 총 {expected_h2}개로 작성하십시오. "
                f"소제목 태그는 속성 없이 반드시 <h2>텍스트</h2> 형식만 허용됩니다."
            )

        if code in {'P_SHORT', 'P_LONG'}:
            return (
                f"문단 수를 조정하십시오. 총 {total_sections}개 섹션 기준으로 문단은 2~3개씩 유지하고, "
                f"군더더기 없는 문장으로 길이 범위({min_chars}~{max_chars}자)를 지키십시오."
            )

        if code == 'EVENT_INVITE_REDUNDANT':
            return (
                "행사 안내 문구 반복을 줄이십시오. \"직접 만나\", \"진솔한 소통\", \"기다리겠습니다\" 류 표현은 "
                "각 2회 이하로 제한하고, 중복된 문장은 행사 핵심 정보(일시/장소/참여 방법)나 새로운 근거로 치환하십시오."
            )

        if code == 'EVENT_FACT_REPEAT':
            return (
                "행사 일시+장소가 결합된 안내 문장은 도입 1회, 결론 1회까지만 허용됩니다. "
                "3회째부터는 \"이번 행사 현장\"처럼 변형하여 반복 구문을 해소하십시오."
            )

        if code == 'META_PROMPT_LEAK':
            return (
                "프롬프트 규칙 설명 문장을 본문에 쓰지 마십시오. "
                "\"문제는~점검\"류 메타 문장을 제거하고 실제 사실/근거 문장으로 바꿔 작성하십시오."
            )

        if code == 'PHRASE_REPEAT_CAP':
            return (
                "상투 구문 반복이 과다합니다. 동일 어구는 최대 2회로 제한하고, "
                "초과 구간은 새로운 근거·수치·사례 중심 문장으로 재작성하십시오."
            )

        if code == 'MATERIAL_REUSE':
            return (
                "같은 소재(인용/일화/근거)를 여러 번 재사용했습니다. "
                "본론 섹션마다 서로 다른 소재 카드를 배정하고, 각 카드는 1회만 사용하십시오."
            )

        return (
            f"총 {total_sections}개 섹션 구조와 분량 범위({min_chars}~{max_chars}자)를 정확히 준수하여 재작성하십시오."
        )

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
        source_instructions = normalize_context_text([stance_text, instructions], sep="\n\n")
        # stanceText가 비어도 최소 앵커를 잃지 않도록 topic을 분석 시드로 보강한다.
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text([topic, instructions], sep="\n\n")
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
                fallback_items = self._split_into_context_items(
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

        stance_count = len(context_analysis.get('mustIncludeFromStance', [])) if context_analysis else 0
        length_spec = self._build_length_spec(target_word_count, stance_count)
        print(
            f"📏 [StructureAgent] 분량 계획: {length_spec['total_sections']}섹션, "
            f"{length_spec['min_chars']}~{length_spec['max_chars']}자 "
            f"(섹션당 {length_spec['per_section_recommended']}자)"
        )

        # 5. Build Prompt
        prompt = self.build_prompt({
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

                structured = self.parse_response(response)
                content = normalize_artifacts(structured['content'])
                content = normalize_html_structure_tags(content)
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

                validation = self.validate_output(
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
                        recovery_result = await self.recover_length_shortfall(
                            content=recovery_content,
                            title=recovery_title,
                            topic=topic,
                            length_spec=length_spec,
                            author_bio=author_bio,
                        )
                    elif current_code in structural_recoverable_codes:
                        recovery_result = await self.recover_structural_shortfall(
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
                    recovered_validation = self.validate_output(
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
                retry_directive = self._build_retry_directive(validation, length_spec)
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

    async def recover_length_shortfall(
        self,
        *,
        content: str,
        title: str,
        topic: str,
        length_spec: Dict[str, int],
        author_bio: str = '',
    ) -> Optional[Tuple[str, str]]:
        current_len = len(strip_html(content))
        min_len = int(length_spec.get('min_chars', 0))
        max_len = int(length_spec.get('max_chars', 0))
        expected_h2 = int(length_spec.get('expected_h2', 0))

        if min_len <= 0:
            return None

        from ..common.gemini_client import generate_content_async

        best_content = content
        best_title = title
        best_len = current_len
        max_recovery_attempts = 3

        for recovery_attempt in range(1, max_recovery_attempts + 1):
            gap = max(0, min_len - best_len)
            rewrite_mode = best_len < int(min_len * 0.6)

            if rewrite_mode:
                prompt = f"""
<length_recovery_prompt version="xml-v1" mode="full_rewrite">
  <role>당신은 엄격한 한국어 정치 에디터입니다. 현재 초안이 지나치게 짧으므로 완전 재작성합니다.</role>
  <goal>
    <current_chars>{best_len}</current_chars>
    <min_chars>{min_len}</min_chars>
    <max_chars>{max_len}</max_chars>
    <expected_h2>{expected_h2}</expected_h2>
  </goal>
  <rules>
    <rule order="1">최종 결과는 완성형 본문이어야 하며, 개요/요약/예시 금지.</rule>
    <rule order="2">태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="3">도입 1 + 본론/결론 구조를 유지하고 분량을 충족.</rule>
    <rule order="4">출력에는 title/content XML 외 설명문 금지.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(best_title)}</draft_title>
    <draft_content>{_xml_cdata(best_content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\n<content>...</content>')}</example>
  </output_contract>
</length_recovery_prompt>
""".strip()
            else:
                prompt = f"""
<length_recovery_prompt version="xml-v1" mode="expand_only">
  <role>당신은 엄격한 한국어 정치 에디터입니다. 기존 흐름을 유지하며 분량만 보강합니다.</role>
  <goal>
    <current_chars>{best_len}</current_chars>
    <min_chars>{min_len}</min_chars>
    <max_chars>{max_len}</max_chars>
    <required_additional_chars>{gap}</required_additional_chars>
    <expected_h2>{expected_h2}</expected_h2>
  </goal>
  <rules>
    <rule order="1">기존 &lt;h2&gt; 제목 삭제/변경 금지.</rule>
    <rule order="2">&lt;h2&gt; 개수는 정확히 {expected_h2}개 유지.</rule>
    <rule order="3">문단은 &lt;p&gt;...&lt;/p&gt;만 사용하고 태그를 정확히 닫을 것.</rule>
    <rule order="4">기존 사실/주장을 삭제하거나 왜곡하지 말 것.</rule>
    <rule order="5">중복/반복 금지. 각 단락은 새로운 근거/설명으로 보강.</rule>
    <rule order="6">최종 분량은 {min_len}~{max_len}자 범위를 반드시 충족.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(best_title)}</draft_title>
    <draft_content>{_xml_cdata(best_content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\n<content>...</content>')}</example>
  </output_contract>
</length_recovery_prompt>
""".strip()

            try:
                response_text = await generate_content_async(
                    prompt,
                    model_name=self.model_name,
                    temperature=0.0,
                    max_output_tokens=8192,
                )
                parsed = self.parse_response(response_text)
                recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
                recovered_title = normalize_artifacts(parsed.get('title', '')) or best_title
                if not recovered_content:
                    continue

                recovered_len = len(strip_html(recovered_content))
                print(
                    f"🔧 [StructureAgent] 분량 보강 시도 {recovery_attempt}/{max_recovery_attempts}: "
                    f"{best_len}자 -> {recovered_len}자"
                )
                if recovered_len > best_len:
                    best_content = recovered_content
                    best_title = recovered_title
                    best_len = recovered_len

                if recovered_len >= min_len:
                    return recovered_content, recovered_title
            except Exception as e:
                print(f"⚠️ [StructureAgent] 분량 보강 복구 실패: {str(e)}")

        if best_len > current_len:
            print(
                f"⚠️ [StructureAgent] 분량 기준 미달이지만 보강 개선: "
                f"{current_len}자 -> {best_len}자"
            )
            return best_content, best_title
        return None

    async def recover_structural_shortfall(
        self,
        *,
        content: str,
        title: str,
        topic: str,
        length_spec: Dict[str, int],
        author_bio: str = '',
        failed_code: str,
        failed_reason: str,
        failed_feedback: str,
    ) -> Optional[Tuple[str, str]]:
        from ..common.gemini_client import generate_content_async

        current_len = len(strip_html(content))
        min_len = int(length_spec.get('min_chars', 0))
        max_len = int(length_spec.get('max_chars', 0))
        expected_h2 = int(length_spec.get('expected_h2', 0))
        total_sections = int(length_spec.get('total_sections', 5))
        min_p = total_sections * 2
        max_p = total_sections * 4

        prompt = f"""
<structural_recovery_prompt version="xml-v1">
  <role>당신은 엄격한 편집자입니다. 아래 원고는 구조/형식 검증에 실패했으므로 완전 교정합니다.</role>
  <failure>
    <code>{_xml_text(failed_code)}</code>
    <reason>{_xml_cdata(failed_reason)}</reason>
    <feedback>{_xml_cdata(failed_feedback)}</feedback>
  </failure>
  <goal>
    <current_chars>{current_len}</current_chars>
    <target_chars>{min_len}~{max_len}</target_chars>
    <expected_h2>{expected_h2}</expected_h2>
    <expected_p>{min_p}~{max_p}</expected_p>
  </goal>
  <rules>
    <rule order="1">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="2">모든 &lt;h2&gt;, &lt;p&gt; 태그를 정확히 열고 닫을 것.</rule>
    <rule order="3">본문에 예시 플레이스홀더([제목], [내용], [구체적 대안] 등)를 남기지 말 것.</rule>
    <rule order="4">기존 핵심 의미/사실은 유지하되 형식과 구조를 완전 교정할 것.</rule>
    <rule order="5">분량 부족이면 구체 근거를 보강하고, 분량 초과면 중복을 압축할 것.</rule>
    <rule order="6">최종 응답은 title/content XML 태그만 출력할 것.</rule>
    <rule order="7">실패 코드({ _xml_text(failed_code) })를 최우선으로 해결하고, 동일 실패 코드가 재발하지 않게 재작성할 것.</rule>
    <rule order="8">반복 관련 실패 코드라면 동일 어구 반복을 줄이고, 초과 부분은 새로운 사실/근거/행동 문장으로 치환할 것(의미 보존).</rule>
    <rule order="9">검증 규칙 설명문이나 메타 문장을 본문으로 출력하지 말 것.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(title)}</draft_title>
    <draft_content>{_xml_cdata(content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\n<content>...</content>')}</example>
  </output_contract>
</structural_recovery_prompt>
""".strip()

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.1,
                max_output_tokens=8192,
            )
            parsed = self.parse_response(response_text)
            recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
            recovered_title = normalize_artifacts(parsed.get('title', '')) or title
            if not recovered_content:
                return None
            return recovered_content, recovered_title
        except Exception as e:
            print(f"⚠️ [StructureAgent] 구조/분량 보강 복구 실패: {str(e)}")
            return None

    async def run_context_analyzer(self, stance_text: str, news_data_text: str, author_name: str) -> Optional[Dict]:
        from ..common.gemini_client import generate_content_async

        stance_len = len(strip_html(stance_text or ""))
        news_len = len(strip_html(news_data_text or ""))
        # 입장문이 짧아도 뉴스/대체자료가 충분하면 분석 진행
        if stance_len < 50:
            if news_len >= 80:
                print(
                    f"⚠️ [StructureAgent] 입장문이 짧음 ({stance_len}자) - "
                    f"뉴스/대체자료({news_len}자) 중심으로 분석 진행"
                )
                stance_text = normalize_context_text([stance_text, news_data_text], sep="\n\n")
            else:
                print(
                    f"⚠️ [StructureAgent] 입장문/뉴스 모두 짧음 "
                    f"(stance={stance_len}자, news={news_len}자) - ContextAnalyzer 스킵"
                )
                return None

        print(f'🔍 [StructureAgent] ContextAnalyzer 실행... (입장문: {len(stance_text)}자, 뉴스: {len(news_data_text)}자)')
        start_time = time.time()

        if not news_data_text:
            # 뉴스 데이터가 없으면 입장문 중심으로 분석
            print(f"⚠️ [StructureAgent] 뉴스 데이터 없음 - 입장문만으로 분석 진행")

        news_preview = news_data_text[:2000] if news_data_text else '(없음)'
        context_json_example = """{
  "intent": "donation_request",
  "contentStrategy": {
    "tone": "감성 호소",
    "structure": "스토리텔링 → 비전 → CTA",
    "emphasis": ["후원 동참 유도", "진정성 전달"]
  },
  "mustIncludeFromStance": [
    {
      "topic": "핵심 주장 1",
      "expansion_why": "배경...",
      "expansion_how": "방안...",
      "expansion_effect": "효과..."
    }
  ],
  "mustIncludeFacts": [],
  "mustPreserve": {
    "bankName": "신한은행",
    "accountNumber": "140016005619",
    "accountHolder": "이재성 후원회",
    "contactNumber": "01097262663",
    "instruction": "입금 후 성함 문자 → 영수증 발급",
    "eventDate": null,
    "eventLocation": null,
    "ctaPhrase": "지금 바로 함께할 수 있습니다"
  }
}"""

        context_prompt = f"""
<context_analyzer_prompt version="xml-v1">
  <role>당신은 정치 콘텐츠 전략가입니다. 입력 텍스트를 분석해 블로그 콘텐츠 전략을 수립하세요.</role>
  <inputs>
    <stance_text>{_xml_cdata(stance_text[:2500])}</stance_text>
    <news_or_data>{_xml_cdata(news_preview)}</news_or_data>
    <author_name>{_xml_text(author_name)}</author_name>
  </inputs>
  <analysis_tasks>
    <intent_selection>
      <description>아래 중 가장 적합한 의도 하나만 선택</description>
      <option key="donation_request">후원 요청 (계좌/연락처 포함)</option>
      <option key="policy_promotion">정책/비전 홍보</option>
      <option key="event_announcement">일정/행사 안내</option>
      <option key="activity_report">활동 보고</option>
      <option key="personal_message">개인 소통/인사</option>
    </intent_selection>
    <content_strategy>
      <field name="tone">톤앤매너 (예: 감성 호소, 논리적 설득, 정보 전달, 친근한 소통)</field>
      <field name="structure">전개 구조 (예: 스토리텔링→비전→CTA / 문제→해법→효과 / 일정→내용→참여방법)</field>
      <field name="emphasis">강조 포인트 리스트</field>
    </content_strategy>
    <must_include_from_stance max_items="3">
      <description>글쓴이({_xml_text(author_name)})의 핵심 주장 추출</description>
      <field name="topic">핵심 주장 (간결한 문장)</field>
      <field name="expansion_why">이 주장이 필요한 배경</field>
      <field name="expansion_how">구체적 실현 방안</field>
      <field name="expansion_effect">기대되는 효과</field>
    </must_include_from_stance>
    <must_preserve critical="true">
      <description>원문에서 절대 누락되면 안 되는 구체 정보만 추출</description>
      <field name="bankName">은행명 (없으면 null)</field>
      <field name="accountNumber">계좌번호 (없으면 null)</field>
      <field name="accountHolder">예금주 (없으면 null)</field>
      <field name="contactNumber">연락처 (없으면 null)</field>
      <field name="instruction">안내 문구 (없으면 null)</field>
      <field name="eventDate">일시 (없으면 null)</field>
      <field name="eventLocation">장소 (없으면 null)</field>
      <field name="ctaPhrase">CTA 문구 (없으면 null)</field>
    </must_preserve>
  </analysis_tasks>
  <output_contract>
    <format>JSON only</format>
    <rules>
      <rule order="1">반드시 JSON 객체 하나만 출력</rule>
      <rule order="2">코드블록, XML, 부가 설명문 출력 금지</rule>
      <rule order="3">키 누락 시 null 또는 빈 배열을 사용</rule>
    </rules>
    <json_example>{_xml_cdata(context_json_example)}</json_example>
  </output_contract>
</context_analyzer_prompt>
""".strip()

        try:
            response_text = await generate_content_async(
                context_prompt,
                model_name=self.model_name,
                temperature=0.0,  # 분석은 정확도 우선
                response_mime_type='application/json'
            )

            analysis = json.loads(response_text)

            elapsed = time.time() - start_time
            print(f"✅ [StructureAgent] ContextAnalyzer 완료 ({elapsed:.1f}초)")

            # Filter phrases
            if 'mustIncludeFromStance' in analysis and isinstance(analysis['mustIncludeFromStance'], list):
                filtered_list = []
                for item in analysis['mustIncludeFromStance']:
                    # 기존 문자열 호환성 (string이면 그대로 사용)
                    if isinstance(item, str) and len(item.strip()) >= 5:
                         filtered_list.append({'topic': item, 'expansion_why': '', 'expansion_how': '', 'expansion_effect': ''})
                    # 딕셔너리 구조 필터링
                    elif isinstance(item, dict) and item.get('topic'):
                        topic = item.get('topic', '').strip()
                        if len(topic) >= 2 and not topic.startswith('⚠️'):
                            filtered_list.append(item)
                analysis['mustIncludeFromStance'] = filtered_list

            analysis = self._normalize_context_analysis_materials(analysis)
            return analysis
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"⚠️ [StructureAgent] ContextAnalyzer 실패 ({elapsed:.1f}초): {error_msg} - 건너뜀")
            return None

    def build_prompt(self, params: Dict[str, Any]) -> str:
        # Extract params
        writing_method = params.get('writingMethod')
        template_builder = TEMPLATE_BUILDERS.get(writing_method, build_daily_communication_prompt)

        # userProfile 방어 코드 - list로 전달되는 경우 방어
        user_profile = params.get('userProfile', {})
        if not isinstance(user_profile, dict):
            user_profile = {}
        news_source_mode = str(params.get('newsSourceMode') or 'news').strip().lower()
        profile_support_context = normalize_context_text(params.get('profileSupportContext'))
        profile_substitute_context = normalize_context_text(params.get('profileSubstituteContext'))
        personalization_context = normalize_context_text(
            params.get('personalizationContext') or params.get('memoryContext'),
            sep="\n",
        )

        # Build base template prompt
        template_prompt = template_builder({
            'topic': params.get('topic'),
            'authorBio': params.get('authorBio'),
            'authorName': params.get('authorName'),
            'instructions': params.get('instructions'),
            'keywords': params.get('userKeywords'),
            'targetWordCount': params.get('targetWordCount'),
            'personalizedHints': personalization_context,
            'newsContext': params.get('newsContext'),
            'isCurrentLawmaker': self.is_current_lawmaker(user_profile),
            'politicalExperience': user_profile.get('politicalExperience', '정치 신인'),
            'familyStatus': user_profile.get('familyStatus', '')
        })

        # Reference Materials Section
        instructions_text = normalize_context_text(params.get('instructions'))
        news_context_text = normalize_context_text(params.get('newsContext'))
        source_blocks = [instructions_text]
        if news_context_text:
            source_blocks.append(news_context_text)
        bio_source_line = ""
        bio_source_rule = "보조 자료: 사용자 프로필(Bio)은 화자 정체성과 어조 참고용이며, 분량이 부족할 때만 활용하세요."
        if news_source_mode == 'profile_fallback' and profile_substitute_context:
            source_blocks.append(f"[뉴스/데이터 대체자료]\n{profile_substitute_context}")
            bio_source_line = "- 대체 자료: 사용자 추가정보(공약/법안/성과) 무작위 3개 + Bio 보강"
            bio_source_rule = (
                "대체자료 활용: 뉴스/데이터가 비어 있으므로 사용자 추가정보(공약/법안/성과)와 "
                "Bio 보강 맥락에서 팩트를 추출해 사용하세요. 대체자료 3개는 매 요청마다 무작위 선정됩니다."
            )
        elif not news_context_text and profile_support_context:
            source_blocks.append(f"[작성자 BIO 보강 맥락]\n{profile_support_context}")
            bio_source_line = "- 보강 자료: 사용자 Bio (경력/이력/가치)"
            bio_source_rule = (
                "Bio 보강 활용: 뉴스/데이터와 구조화 추가정보가 모두 부족하므로 "
                "사용자 Bio에서 확인 가능한 경력/성과/핵심가치를 사실 근거로 활용하세요."
            )

        source_text = "\n\n---\n\n".join(block for block in source_blocks if block)
        ref_section = ""
        if source_text.strip():
            ref_section = f"""
<reference_materials priority="critical">
  <overview>아래 참고자료가 이 원고의 1차 자료(Primary Source)입니다.</overview>
  <source_order>
    <item order="1">첫 번째 자료: 작성자의 입장문/페이스북 글 (핵심 논조와 주장)</item>
    <item order="2">이후 자료: 뉴스/데이터 (근거, 팩트, 배경 정보)</item>
    {'<item order="3">' + _xml_text(bio_source_line) + '</item>' if bio_source_line else ''}
  </source_order>
  <source_body>{_xml_cdata(source_text[:6000])}</source_body>
  <processing_rules>
    <rule order="1">정보 추출: 핵심 팩트, 수치, 논점만 사용</rule>
    <rule order="2">재작성 필수: 참고자료 문장을 그대로 복사하지 않음</rule>
    <rule order="3">구어체를 문어체로 변환</rule>
    <rule order="4">창작 금지: 참고자료에 없는 팩트/수치 생성 금지</rule>
    <rule order="5">주제 유지: 참고자료 핵심 주제 이탈 금지</rule>
    <rule order="6">{_xml_text(bio_source_rule)}</rule>
  </processing_rules>
  <forbidden_examples>
    <example type="source">{_xml_cdata('정확하게 얘기를 하면 그래서 창의적이고 정말 압도적인...')}</example>
    <example type="bad">{_xml_cdata('정확하게 얘기를 하면 그래서 창의적이고...')}</example>
    <example type="good">{_xml_cdata('창의적이고 압도적인 콘텐츠 기반 전략이 핵심입니다.')}</example>
  </forbidden_examples>
</reference_materials>
"""
            print(f"📚 [StructureAgent] 참고자료 주입 완료: {len(source_text)}자")
        else:
            print("⚠️ [StructureAgent] 참고자료 없음 - 사용자 프로필만으로 생성")

        # Context Injection
        context_injection = ""
        is_event_announcement = False
        event_date_hint = ""
        event_location_hint = ""
        event_contact_hint = ""
        event_cta_hint = ""
        intro_anchor_topic = ""
        intro_anchor_why = ""
        intro_anchor_effect = ""
        intro_seed = ""

        intro_seed_candidates = self._split_into_context_items(instructions_text, min_len=10, max_items=6)
        if not intro_seed_candidates and profile_substitute_context:
            intro_seed_candidates = self._split_into_context_items(profile_substitute_context, min_len=10, max_items=6)
        if not intro_seed_candidates and news_context_text:
            intro_seed_candidates = self._split_into_context_items(news_context_text, min_len=10, max_items=6)
        if not intro_seed_candidates:
            intro_seed_candidates = self._split_into_context_items(
                normalize_context_text(params.get('topic')),
                min_len=6,
                max_items=2,
            )
        if intro_seed_candidates:
            intro_seed = intro_seed_candidates[0]

        raw_context_analysis = params.get('contextAnalysis')
        context_analysis = (
            self._normalize_context_analysis_materials(raw_context_analysis)
            if isinstance(raw_context_analysis, dict)
            else {}
        )
        if context_analysis:
            stance_list = context_analysis.get('mustIncludeFromStance', [])
            
            # 구조화된 stance 처리
            formatted_stances = []
            for i, p in enumerate(stance_list):
                if isinstance(p, dict):
                    topic = p.get('topic', '')
                    why_txt = p.get('expansion_why', '')
                    how_txt = p.get('expansion_how', '')
                    eff_txt = p.get('expansion_effect', '')
                    
                    block = f"""
<stance index="{i+1}" section_hint="본론 {i+1}">
  <topic>{_xml_text(topic)}</topic>
  <why>{_xml_text(why_txt)}</why>
  <how>{_xml_text(how_txt)}</how>
  <effect>{_xml_text(eff_txt)}</effect>
</stance>"""
                    formatted_stances.append(block.strip())
                else:
                    # Fallback for string (legacy)
                    formatted_stances.append(
                        f"<stance index=\"{i+1}\" section_hint=\"본론 {i+1}\"><topic>{_xml_text(p)}</topic></stance>"
                    )

            stance_phrases = "\n\n".join(formatted_stances)
            stance_count = len(stance_list)
            if stance_list:
                first = stance_list[0]
                if isinstance(first, dict):
                    intro_anchor_topic = normalize_context_text(first.get('topic'))
                    intro_anchor_why = normalize_context_text(first.get('expansion_why'))
                    intro_anchor_effect = normalize_context_text(first.get('expansion_effect'))
                else:
                    intro_anchor_topic = normalize_context_text(first)
             
            if stance_count > 0:
                context_injection = f"""
<body_expansion mandatory="true">
  <description>아래 {stance_count}개 설계도에 따라 본론 섹션을 확장합니다.</description>
  <stance_count>{stance_count}</stance_count>
  <stance_blueprints>
{stance_phrases}
  </stance_blueprints>
  <instructions>
    <instruction order="1">각 주제를 별도의 본론 섹션(H2)으로 구성</instruction>
    <instruction order="2">각 섹션에 Why/How/Effect 논리를 핵심 위주로 반영</instruction>
    <instruction order="3">How 단계에서 Bio(경력)를 근거로 전문성을 제시</instruction>
  </instructions>
</body_expansion>
"""

                intro_anchor_summary = " / ".join(
                    part for part in [intro_anchor_topic, intro_anchor_why, intro_anchor_effect] if part
                ).strip()
                if intro_anchor_summary:
                    context_injection += f"""
<intro_anchor mandatory="true">
  <description>서론 1~2문단은 입장문 핵심 요지를 재진술하고 본론으로 연결합니다.</description>
  <anchor>{_xml_text(intro_anchor_summary)}</anchor>
</intro_anchor>
"""

            # 🔴 [NEW] contentStrategy 주입
            content_strategy = context_analysis.get('contentStrategy', {})
            if content_strategy:
                tone = content_strategy.get('tone', '')
                structure = content_strategy.get('structure', '')
                emphasis = content_strategy.get('emphasis', [])
                
                if tone or structure:
                    emphasis_str = ", ".join(emphasis) if emphasis else "없음"
                    context_injection += f"""
<content_strategy>
  <tone>{_xml_text(tone)}</tone>
  <structure>{_xml_text(structure)}</structure>
  <emphasis>{_xml_text(emphasis_str)}</emphasis>
</content_strategy>
"""
                    print(f"🎯 [StructureAgent] 콘텐츠 전략 주입: {tone} / {structure}")

            # 🔴 [NEW] mustPreserve 기반 CTA 정보 주입
            must_preserve = context_analysis.get('mustPreserve', {})
            intent = context_analysis.get('intent', '')
            
            if must_preserve and intent == 'donation_request':
                # 슬로건/후원 안내는 최종 출력 직전에만 부착한다.
                # 본문 생성 단계에서는 계좌/연락처/영수증 문구를 주입하지 않는다.
                print("💡 [StructureAgent] 후원 정보 본문 주입 생략 (최종 출력 단계에서만 부착)")

            # 🔴 [NEW] 행사 안내 정보 주입
            elif must_preserve and intent == 'event_announcement':
                is_event_announcement = True
                event_date = must_preserve.get('eventDate')
                event_location = must_preserve.get('eventLocation')
                contact_number = must_preserve.get('contactNumber')
                cta_phrase = must_preserve.get('ctaPhrase')

                event_date_hint = str(event_date or '').strip()
                event_location_hint = str(event_location or '').strip()
                event_contact_hint = str(contact_number or '').strip()
                event_cta_hint = str(cta_phrase or '').strip()
                
                if event_date or event_location:
                    event_parts = []
                    if event_date:
                        event_parts.append(f"- 일시: {event_date}")
                    if event_location:
                        event_parts.append(f"- 장소: {event_location}")
                    if contact_number:
                        event_parts.append(f"- 문의: {contact_number}")
                    
                    event_text = "\n".join(event_parts)
                    
                    context_injection += f"""
<event_context mandatory="true">
  <facts>{_xml_cdata(event_text)}</facts>
  <instructions>
    <instruction order="1">행사 정보(일시/장소/참여방법)를 도입에서 명확히 제시</instruction>
    <instruction order="2">동일한 일시+장소 결합 문장을 본문에서 반복하지 않음</instruction>
    <instruction order="3">결론 CTA는 행동 동사+구체 장소로 1회만 제시</instruction>
  </instructions>
</event_context>
"""
                    print(f"📅 [StructureAgent] 행사 정보 주입: {event_date} / {event_location}")

        if not intro_anchor_topic:
            intro_anchor_topic = intro_seed or normalize_context_text(params.get('topic'))

        # Warning Generation (XML)
        warning_blocks: List[str] = []
        non_lawmaker_warn = generate_non_lawmaker_warning(
            self.is_current_lawmaker(user_profile),
            user_profile.get('politicalExperience'),
            params.get('authorBio')
        )
        if non_lawmaker_warn:
            warning_blocks.append(
                f"<non_lawmaker_warning>{_xml_cdata(non_lawmaker_warn)}</non_lawmaker_warning>"
            )
        
        if params.get('authorBio') and '"' in params.get('authorBio', ''):
            warning_blocks.append(
                """
<bio_quote_rules priority="critical">
  <rule order="1">Bio의 큰따옴표(" ")로 묶인 문장은 원문 그대로 인용</rule>
  <rule order="2">따옴표 문장의 단어/조사/어미를 임의 수정하지 않음</rule>
  <rule order="3">사람 이름으로 단어를 대체하지 않음</rule>
  <examples>
    <bad><![CDATA["벌써 국회의원 했을 텐데" -> "벌써 홍길동 했을 텐데"]]></bad>
    <good><![CDATA["벌써 국회의원 했을 텐데" (원문 그대로)]]></good>
  </examples>
</bio_quote_rules>
""".strip()
            )

        bio_warning = ""
        if warning_blocks:
            bio_warning = "<warning_bundle>\n" + "\n".join(warning_blocks) + "\n</warning_bundle>"

        # Modified Structure Enforcement: Dynamic based on stance_count
        stance_count = 0
        if context_analysis:
            stance_count = len(context_analysis.get('mustIncludeFromStance', []))

        length_spec = params.get('lengthSpec') or self._build_length_spec(
            params.get('targetWordCount', 2000),
            stance_count
        )
        body_section_count = length_spec['body_sections']
        total_section_count = length_spec['total_sections']
        min_total_chars = length_spec['min_chars']
        max_total_chars = length_spec['max_chars']
        per_section_min = length_spec['per_section_min']
        per_section_max = length_spec['per_section_max']
        per_section_recommended = length_spec['per_section_recommended']
        material_uniqueness_guard = self._build_material_uniqueness_guard(
            context_analysis,
            body_sections=body_section_count,
        )

        intro_line_1 = '<p>1문단: 화자 소개 + 입장문에서 드러난 문제의식 1가지를 재진술</p>'
        intro_line_2 = '<p>2문단: 입장문 핵심 주장(원문 요지)을 재작성하여 글의 목적을 명확히 제시</p>'
        intro_line_3 = '<p>3문단: 본론에서 다룰 해결 방향/행동 제안을 예고</p>'
        intro_stance_rules = f"""
  <intro_stance_binding priority="critical">
    <rule id="intro_must_anchor_stance">서론 2문단 이내에 입장문 핵심 주장 또는 문제의식을 반드시 재진술할 것.</rule>
    <rule id="intro_no_generic_opening">맥락 없는 일반 인삿말/상투적 도입으로 시작하지 말 것.</rule>
    <rule id="intro_paraphrase_required">입장문 문장을 그대로 복붙하지 말고 의미는 유지한 채 재작성할 것.</rule>
    <rule id="intro_to_body_bridge">서론 마지막 문장에서 본론 주제로 자연스럽게 연결할 것.</rule>
    <stance_seed>{intro_seed or '(입장문 요지 없음)'}</stance_seed>
    <stance_anchor_topic>{intro_anchor_topic or '(미지정)'}</stance_anchor_topic>
  </intro_stance_binding>
"""
        event_mode_rules = ''
        if is_event_announcement:
            intro_line_1 = '<p>1문단: 화자 실명 + 행사 목적을 2문장 이내로 명확히 제시</p>'
            intro_line_2 = '<p>2문단: 행사 핵심정보(일시/장소/참여방법/문의)를 한 문단으로 압축 제시</p>'
            intro_line_3 = '<p>3문단: 입장문의 문제의식/핵심 메시지가 행사에서 어떻게 다뤄지는지 제시</p>'
            event_mode_rules = f"""
  <event_mode intent="event_announcement" priority="critical">
    <facts>
      <event_date>{event_date_hint or '(미상)'}</event_date>
      <event_location>{event_location_hint or '(미상)'}</event_location>
      <event_contact>{event_contact_hint or '(미상)'}</event_contact>
      <event_cta>{event_cta_hint or '(없음)'}</event_cta>
    </facts>
    <rule id="event_info_first">도입부 2문단 이내에 행사 일시/장소/참여 방법을 모두 제시할 것.</rule>
    <rule id="speaker_name_required">첫 문단 첫 2문장 안에 화자 실명을 반드시 포함할 것.</rule>
    <rule id="bio_limit_before_event">행사 핵심정보 제시 전, 화자 경력/서사 서술은 최대 2문장으로 제한할 것.</rule>
    <rule id="no_invite_redundancy">"직접 만나", "진솔한 소통" 류 문구 반복 금지. 원고 전체 최대 2회.</rule>
    <rule id="event_fact_repeat_limit">행사 일시/장소/참여 안내 문구는 도입 1회 + 결론 1회까지만 허용할 것.</rule>
    <rule id="event_fact_variation">동일한 일시+장소 결합 구문을 본문 섹션마다 반복하지 말 것. 중간 섹션에서는 "이번 행사 현장", "행사 자리"처럼 변형해 연결할 것.</rule>
    <rule id="event_datetime_ngram_cap">"3월 1일(일) 오후 2시, 서면..."처럼 일시+장소 결합 5단어 이상 구문은 원고 전체 최대 2회. 3회째부터는 "행사 당일", "당일 현장" 등 변형 표현으로만 작성할 것.</rule>
    <rule id="event_seed_priority">서론 1~2문단에서 입장문 핵심 시드(stance_seed)의 의미를 반드시 재진술할 것.</rule>
    <rule id="no_orphan_location_line">장소 키워드("서면 영광도서/부산 영광도서")는 단순 안내 단문으로 분리하지 말고, 해당 단락의 행사 맥락(참여 정보/대화 주제/독자 효익)과 결합한 문장으로 작성할 것.</rule>
    <rule id="no_recap_echo">각 섹션 끝의 요약 단문 반복 금지. 특히 "이 만남은 ~", "이 자리는 ~", "이 뜻깊은 자리는 ~", "이번 만남은 ~" 패턴은 원고 전체 1회만 허용.</rule>
    <rule id="cta_once">결론부 CTA는 1회만 작성하고, 행동 동사+구체 장소를 함께 제시할 것. 예: "주저 말고 서면 영광도서를 찾아 주십시오."</rule>
    <rule id="audience_intent">행사 안내문 독자가 즉시 행동할 수 있도록 정보 우선, 자기서사 과잉 금지.</rule>
    <rule id="event_intro_with_stance">행사 정보 제시 후, 입장문 핵심 메시지를 서론에서 바로 연결할 것.</rule>
  </event_mode>
"""
        
        # 동적 본론 구조 문자열 생성
        body_structure_lines = []
        for i in range(1, body_section_count + 1):
            body_structure_lines.append(
                f"<body_section order=\"{i+1}\" name=\"본론 {i}\" paragraphs=\"2~3\" chars=\"{per_section_min}~{per_section_max}\" heading=\"h2 필수\"/>"
            )
        body_structure_str = "\n    ".join(body_structure_lines)
        
        # 지역 정보 추출 - 범용성 확보 및 동적 변수
        region_metro = user_profile.get('regionMetro', '')
        region_district = user_profile.get('regionDistrict', '')
        user_region = f"{region_metro} {region_district}".strip()
        if not user_region:
            user_region = "지역 사회"
            
        structure_enforcement = f"""
<structure_guide mode="strict">
  <strategy>E-A-T (전문성-권위-신뢰) 전략으로 작성</strategy>

  <volume warning="위반 시 시스템 오류">
    <per_section min="{per_section_min}" max="{per_section_max}" recommended="{per_section_recommended}"/>
    <paragraphs_per_section>2~3개 문단, 문단당 2~4문장으로 핵심 위주 서술</paragraphs_per_section>
    <total sections="{total_section_count}" min="{min_total_chars}" max="{max_total_chars}"/>
    <caution>총 분량 상한을 넘기지 않도록 중복 문장과 장황한 수식어를 제거하고, 근거 중심으로 간결하게 작성하십시오.</caution>
  </volume>

  <expansion_guide name="섹션별 작성 4단계">
    각 본론 섹션을 아래 흐름으로 밀도 있게 전개하십시오.
    <step name="Why" sentences="1~2">시민들이 겪는 실제 불편함과 현장의 고충을 구체적으로 진단</step>
    <step name="How+Expertise" sentences="2">실현 가능한 해결책 제시 및 본인의 Bio(경력)를 인용하여 전문성 강조</step>
    <step name="Authority" sentences="1">과거 성과나 네트워크를 바탕으로 실행 능력을 증명</step>
    <step name="Effect+Trust" sentences="1~2">변화될 {user_region}의 미래 청사진을 명확히 제시</step>
  </expansion_guide>

  <sections total="{total_section_count}">
    <intro paragraphs="2~3" chars="{per_section_recommended}" heading="없음">
      {intro_line_1}
      {intro_line_2}
      {intro_line_3}
    </intro>
    {body_structure_str}
    <conclusion order="{total_section_count}" paragraphs="2~3" chars="{per_section_recommended}" heading="h2 필수"/>
  </sections>

  <h2_strategy name="소제목 작성 전략 (AEO+SEO)">
    <type name="질문형" strength="AEO 최강">청년 기본소득, 신청 방법은?</type>
    <type name="명사형" strength="SEO 기본">분당구 정자동 주차장 신설 위치</type>
    <type name="데이터" strength="신뢰성">2025년 상반기 5대 주요 성과</type>
    <type name="절차" strength="실용성">청년 기본소득 신청 3단계 절차</type>
    <type name="비교" strength="차별화">기존 정책 대비 개선된 3가지</type>
    <banned>추상적 표현("노력", "열전", "마음"), 모호한 제목("정책 안내", "소개"), 서술어 포함("~에 대한 설명")</banned>
  </h2_strategy>

  <mandatory_rules>
    <rule id="html_tags">소제목은 &lt;h2&gt;, 문단은 &lt;p&gt; 태그만 사용 (마크다운 문법 금지)</rule>
    <rule id="defer_output_addons" severity="critical">슬로건/후원 안내(계좌·예금주·연락처·영수증 안내)는 본문에 쓰지 말 것. 해당 정보는 최종 출력 직전에 시스템이 자동 부착.</rule>
    <rule id="no_slogan_repeat" severity="critical">입장문의 맺음말/슬로건을 각 섹션 끝마다 반복 금지. 모든 호소와 다짐은 맨 마지막 결론부에만.</rule>
    <rule id="sentence_completion">문장은 올바른 종결 어미(~입니다, ~합니다, ~시오)로 끝내야 함. 고의적 오타/잘린 문장 금지.</rule>
    <rule id="keyword_per_section">각 섹션마다 키워드 1개 이상 포함</rule>
    <rule id="separate_pledges">각 본론 섹션은 서로 다른 주제/공약을 다룰 것</rule>
    <rule id="verb_diversity" severity="critical">같은 동사(예: "던지면서")를 원고 전체에서 3회 이상 사용 금지. 동의어 교체: 제시하며, 약속하며, 열며, 보여드리며 등.</rule>
    <rule id="slogan_once">캐치프레이즈("청년이 돌아오는 부산")나 비유("아시아의 싱가포르")는 결론부 1회만. 다른 섹션에서는 변형 사용.</rule>
    <rule id="natural_keyword">키워드는 정보 문장이 아니라 맥락 문장으로 삽입. 키워드 문장에는 최소 1개 이상 포함: 행사 정보(일시/장소/참여 방법), 대화 주제, 시민 행동 제안. 해당 문단의 주장/근거와 결합해 쓰고, 키워드만으로 된 장식/단독 문장 금지.</rule>
    <rule id="no_single_sentence_echo">같은 구조의 단문 문장을 섹션 말미마다 반복 금지. 특히 "이 만남은 ~", "이 자리는 ~", "이 뜻깊은 자리는 ~", "이번 만남은 ~" 패턴은 한 번만 사용.</rule>
    <rule id="no_datetime_location_ngram_repeat">일시+장소가 함께 들어간 구문(예: "3월 1일(일) 오후 2시, 서면...")은 같은 어순으로 3회 이상 반복 금지. 2회를 넘으면 어순/표현을 반드시 변형할 것.</rule>
    <rule id="no_meta_prompt_leak">프롬프트/규칙 설명 문장을 본문에 복사하지 말 것. "문제는~점검" 같은 규칙성 메타 문장 생성 금지.</rule>
    <rule id="paragraph_min_sentences">원칙적으로 각 <p>는 최소 2문장으로 구성. 예외는 결론의 마지막 CTA 문단 1개만 허용.</rule>
    <rule id="causal_clarity">성과 언급 시 본인의 구체적 역할/직책 명시. "40% 득표율을 이끌어냈다" → "시당위원장으로서 지역 조직을 총괄하며 40% 득표율 달성에 기여했습니다"</rule>
  </mandatory_rules>
{material_uniqueness_guard}
{event_mode_rules}
{intro_stance_rules}

  <constraints warning="위반 시 자동 반려">
    <max_chars>{max_total_chars}</max_chars>
    <min_chars>{min_total_chars}</min_chars>
    <no_repeat>같은 문장, 같은 표현 반복 금지 (특히 "~바랍니다" 반복 금지)</no_repeat>
    <html>문단은 &lt;p&gt;...&lt;/p&gt;, 소제목은 &lt;h2&gt;...&lt;/h2&gt;만 사용</html>
    <separate_pledges>서로 다른 공약/정책은 하나의 본론에 합치지 말 것</separate_pledges>
  </constraints>

  <output_format>템플릿에서 지시한 XML 태그(title, content, hashtags)만 출력. output 래퍼나 마크다운 코드블록 금지.</output_format>
</structure_guide>
"""

        # SEO 지침 생성
        seo_instruction = build_seo_instruction({
            'keywords': params.get('userKeywords', []),
            'targetWordCount': params.get('targetWordCount', 2000)
        })

        # 선거법 준수 지침 생성
        user_status = user_profile.get('status', '준비')
        election_instruction = get_prompt_instruction(user_status)

        party_stance_guide = params.get('partyStanceGuide') or ''
        context_injection_xml = ""
        if context_injection.strip():
            context_injection_xml = f"<context_injection>\n{context_injection.strip()}\n</context_injection>"

        return f"""
<structure_agent_prompt version="xml-v1">
  <template_prompt>{_xml_cdata(template_prompt)}</template_prompt>
  <party_stance_guide>{_xml_cdata(party_stance_guide)}</party_stance_guide>
  <seo_instruction>{_xml_cdata(seo_instruction)}</seo_instruction>
  <election_instruction>{_xml_cdata(election_instruction)}</election_instruction>
  {ref_section}
  {context_injection_xml}
  {bio_warning}
  {structure_enforcement}
</structure_agent_prompt>
""".strip()

    def build_author_bio(self, user_profile: Dict) -> tuple[str, str]:
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}

        name = user_profile.get('name', '사용자')
        party_name = user_profile.get('partyName', '')
        current_title = user_profile.get('customTitle') or user_profile.get('position', '')
        basic_bio = " ".join(filter(None, [party_name, current_title, name]))

        career = user_profile.get('careerSummary') or user_profile.get('bio', '')

        # 슬로건/후원 안내는 생성 단계에서 제외하고, 최종 출력 직전에만 부착한다.
        return f"{basic_bio}\n{career}".strip(), name

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

    def parse_response(self, response: str) -> Dict[str, str]:
        if not response:
            return {'content': '', 'title': ''}
        
        # XML Tag Extraction
        try:
            def extract_html_fallback(text: str) -> str:
                html_blocks = re.findall(
                    r'<(?:p|h[23])\b[^>]*>[\s\S]*?</(?:p|h[23])>',
                    text or '',
                    re.IGNORECASE,
                )
                return "\n".join(html_blocks).strip() if html_blocks else ''

            # Title extraction (여러 블록이 있을 때는 마지막 유효 블록 우선)
            title_blocks = [
                (m.group(1) or "").strip()
                for m in re.finditer(r'<title>(.*?)</title>', response, re.DOTALL | re.IGNORECASE)
            ]
            title = next((t for t in reversed(title_blocks) if t), '')

            # Content extraction
            content_blocks = [
                (m.group(1) or "").strip()
                for m in re.finditer(r'<content>(.*?)</content>', response, re.DOTALL | re.IGNORECASE)
            ]
            content = ''
            if content_blocks:
                # 1) 예시/템플릿 블록 제거 2) 구조 밀도 + 길이로 본문 블록 선택
                candidates = []
                for idx, block in enumerate(content_blocks):
                    normalized = normalize_html_structure_tags(normalize_artifacts(block))
                    tag_density = len(re.findall(r'<(?:h2|p)\b', normalized, re.IGNORECASE))
                    plain_len = len(strip_html(normalized))
                    candidates.append(
                        {
                            'index': idx,
                            'content': normalized,
                            'tag_density': tag_density,
                            'plain_len': plain_len,
                            'is_example': is_example_like_block(normalized),
                        }
                    )

                real_candidates = [c for c in candidates if not c['is_example']]
                pool = real_candidates if real_candidates else candidates

                # Prefer substantial body text first, then structure density.
                # This prevents short outline/sample blocks from being selected
                # over the actual long-form draft.
                max_plain_len = max((c['plain_len'] for c in pool), default=0)
                min_plain_threshold = max(300, int(max_plain_len * 0.45))
                length_filtered_pool = [
                    c for c in pool
                    if c['plain_len'] >= min_plain_threshold
                ]
                selection_pool = length_filtered_pool if length_filtered_pool else pool
                selected = max(
                    selection_pool,
                    key=lambda c: (c['plain_len'], c['tag_density'], c['index']),
                )
                content = selected['content'].strip()
                selected_plain_len = selected['plain_len']

                # 선택된 content 인덱스와 같은 title이 있으면 우선 사용
                selected_idx = selected['index']
                if selected_idx < len(title_blocks):
                    aligned_title = (title_blocks[selected_idx] or '').strip()
                    if aligned_title:
                        title = aligned_title

                # 짧은 XML content 블록이 잡혔는데 본문 HTML이 응답에 따로 존재하면 폴백으로 교체
                fallback_content = extract_html_fallback(response)
                fallback_plain_len = len(strip_html(fallback_content))
                fallback_is_example = is_example_like_block(fallback_content)
                if (
                    not fallback_is_example
                    and
                    selected_plain_len < 180
                    and fallback_plain_len >= max(260, selected_plain_len + 120)
                ):
                    print(
                        f"⚠️ [StructureAgent] 짧은 XML content({selected_plain_len}자) 감지, "
                        f"HTML 폴백({fallback_plain_len}자)로 교체"
                    )
                    content = fallback_content
            
            if not content:
                # Fallback: try to find just HTML tags if XML tags are missing
                print('⚠️ [StructureAgent] XML 태그 누락, HTML 직접 추출 시도')
                fallback_content = extract_html_fallback(response)
                if fallback_content:
                    content = fallback_content
                else:
                    content = response # 최후단: 전체 텍스트
            
            print(f"✅ [StructureAgent] 파싱 성공: content={len(content)}자")
            return {'content': content, 'title': title}
            
        except Exception as e:
            print(f"⚠️ [StructureAgent] 파싱 에러: {str(e)}")
            return {'content': response, 'title': ''}

    def _split_plain_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        chunks = re.findall(r'[^.!?。]+[.!?。]?', text)
        sentences = []
        for chunk in chunks:
            sentence = re.sub(r'\s+', ' ', chunk).strip()
            if sentence:
                sentences.append(sentence)
        return sentences

    def _find_meta_prompt_leak_sentences(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []

        patterns = [
            re.compile(r'문제는 .*현장 .*데이터.*점검해야', re.IGNORECASE),
            re.compile(r'관련 .*쟁점.*함께 .*봐야', re.IGNORECASE),
            re.compile(r'그래도 .*문제는 .*점검해야', re.IGNORECASE),
            re.compile(r'현장 .*데이터.*함께 .*점검', re.IGNORECASE),
        ]

        leaks: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            if any(pattern.search(sentence) for pattern in patterns):
                leaks.append(sentence)
        return leaks

    def _count_event_fact_sentence_mentions(
        self,
        content: str,
        *,
        event_date_hint: str = '',
        event_location_hint: str = '',
    ) -> int:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return 0

        location_tokens: List[str] = []
        for token in ('서면 영광도서', '부산 영광도서'):
            if token in plain_text:
                location_tokens.append(token)
        if event_location_hint:
            normalized_location_hint = re.sub(r'\s+', ' ', event_location_hint).strip()
            if normalized_location_hint and normalized_location_hint not in location_tokens:
                location_tokens.append(normalized_location_hint)

        date_tokens: List[str] = []
        if event_date_hint:
            for pattern in (
                r'\d{1,2}\s*월\s*\d{1,2}\s*일(?:\s*\([^)]+\))?',
                r'(?:오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?',
            ):
                match = re.search(pattern, event_date_hint)
                if match:
                    date_tokens.append(re.sub(r'\s+', ' ', match.group(0)).strip())

        if not date_tokens:
            date_tokens = [r'\d{1,2}\s*월\s*\d{1,2}\s*일', r'(?:오전|오후)\s*\d{1,2}\s*시']

        count = 0
        for sentence in self._split_plain_sentences(plain_text):
            has_location = any(token and token in sentence for token in location_tokens)
            has_date = any(re.search(token, sentence) for token in date_tokens)
            if has_location and has_date:
                count += 1
        return count

    def _find_overused_anchor_phrases(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []

        phrase_limits = {
            '부산항 부두 노동자의 막내로': 2,
            '시민 여러분과 함께': 2,
        }
        overused: List[str] = []
        for phrase, limit in phrase_limits.items():
            count = len(re.findall(re.escape(phrase), plain_text))
            if count > limit:
                overused.append(f'"{phrase}" {count}회')
        return overused

    def _repair_anchor_phrase_overuse(self, content: str) -> Tuple[str, List[Dict[str, Any]]]:
        working = str(content or '')
        if not working:
            return working, []

        rules: List[Dict[str, Any]] = [
            {
                'phrase': '시민 여러분과 함께',
                'limit': 2,
                'replacements': ['시민과 함께', '여러분과 함께', '지역사회와 함께'],
            },
            {
                'phrase': '부산항 부두 노동자의 막내로',
                'limit': 2,
                'replacements': ['부산항 노동자 가정의 막내로', '부산항 현장 노동자 집안의 막내로'],
            },
        ]

        actions: List[Dict[str, Any]] = []
        for rule in rules:
            phrase = str(rule.get('phrase') or '').strip()
            limit = int(rule.get('limit') or 2)
            replacements = [str(item).strip() for item in (rule.get('replacements') or []) if str(item).strip()]
            if not phrase or not replacements:
                continue

            pattern = re.compile(re.escape(phrase))
            matches = list(pattern.finditer(working))
            if len(matches) <= limit:
                continue

            replaced = 0
            to_replace = list(reversed(matches[limit:]))
            for idx, match in enumerate(to_replace):
                replacement = replacements[idx % len(replacements)]
                start, end = match.span()
                working = working[:start] + replacement + working[end:]
                replaced += 1

            if replaced > 0:
                actions.append(
                    {
                        'type': 'anchor_phrase_overuse_repair',
                        'phrase': phrase,
                        'replaced': replaced,
                        'limit': limit,
                    }
                )

        return working, actions

    def validate_output(
        self,
        content: str,
        target_word_count: Any,
        stance_count: int = 0,
        *,
        context_analysis: Optional[Dict[str, Any]] = None,
        is_event_announcement: bool = False,
        event_date_hint: str = '',
        event_location_hint: str = '',
    ) -> Dict:
        if not content:
            return {
                'passed': False,
                'code': 'EMPTY_CONTENT',
                'reason': '내용 없음',
                'feedback': '내용이 비어있습니다.'
            }
        
        plain_length = len(strip_html(content))

        if isinstance(target_word_count, dict):
            length_spec = target_word_count
        else:
            length_spec = self._build_length_spec(target_word_count, stance_count)

        min_length = length_spec['min_chars']
        max_length = length_spec['max_chars']
        expected_h2 = length_spec['expected_h2']
        per_section_recommended = length_spec['per_section_recommended']
        per_section_max = length_spec['per_section_max']
        total_sections = length_spec['total_sections']

        placeholder_count = len(re.findall(r'\[[^\]\n]{1,40}\]', content))
        if placeholder_count >= 2:
            return {
                'passed': False,
                'code': 'TEMPLATE_ECHO',
                'reason': f"예시/플레이스홀더 잔존 ({placeholder_count}개)",
                'feedback': '예시 문구([제목], [구체적 내용] 등)를 모두 제거하고 실제 본문으로 작성하십시오.'
            }

        if plain_length < min_length:
            deficit = min_length - plain_length
            return {
                'passed': False,
                'code': 'LENGTH_SHORT',
                'reason': f"분량 부족 ({plain_length}자 < {min_length}자)",
                'feedback': (
                    f"현재 분량({plain_length}자)이 최소 기준({min_length}자)보다 {deficit}자 부족합니다. "
                    f"섹션당 {per_section_recommended}자 안팎으로 구체 사례를 보강하되, 총 분량은 {max_length}자를 넘기지 마십시오."
                )
            }
        
        if plain_length > max_length:
            excess = plain_length - max_length
            return {
                'passed': False,
                'code': 'LENGTH_LONG',
                'reason': f"분량 초과 ({plain_length}자 > {max_length}자)",
                'feedback': (
                    f"현재 분량({plain_length}자)이 최대 기준({max_length}자)을 {excess}자 초과했습니다. "
                    f"각 섹션을 {per_section_recommended}자 안팎(최대 {per_section_max}자)으로 압축하고, "
                    f"중복 문장과 장황한 수식어를 제거하십시오."
                )
            }

        # 허용 태그는 h2/p만 사용해야 하므로, 기타 heading 태그는 즉시 반려.
        disallowed_heading_count = len(re.findall(r'<h(?!2\b)[1-6]\b[^>]*>', content, re.IGNORECASE))
        if disallowed_heading_count > 0:
            return {
                'passed': False,
                'code': 'TAG_DISALLOWED',
                'reason': f"허용되지 않은 heading 태그 사용 (h2 외 {disallowed_heading_count}개)",
                'feedback': '소제목은 <h2>만 사용하고, <h1>/<h3> 등 다른 heading 태그는 제거하십시오.'
            }

        h2_open_tags = re.findall(r'<h2\b[^>]*>', content, re.IGNORECASE)
        h2_close_tags = re.findall(r'</h2\s*>', content, re.IGNORECASE)
        h2_count = len(h2_open_tags)
        if h2_count != len(h2_close_tags):
            return {
                'passed': False,
                'code': 'H2_MALFORMED',
                'reason': f"h2 태그 짝 불일치 (열림 {h2_count}개, 닫힘 {len(h2_close_tags)}개)",
                'feedback': '모든 소제목은 <h2>...</h2> 형태로 정확히 닫아 주십시오.'
            }

        if h2_count < expected_h2:
            return {
                'passed': False,
                'code': 'H2_SHORT',
                'reason': f"소제목 부족 (현재 {h2_count}개, 목표 {expected_h2}개)",
                'feedback': (
                    f"소제목(<h2>)이 부족합니다. 도입을 제외한 본론+결론 기준으로 정확히 {expected_h2}개의 "
                    f"<h2>를 작성하십시오."
                )
            }
        
        if h2_count > expected_h2:
            return {
                'passed': False,
                'code': 'H2_LONG',
                'reason': f"소제목 과다 (현재 {h2_count}개, 목표 {expected_h2}개)",
                'feedback': (
                    f"소제목(<h2>)이 너무 많습니다. 도입을 제외한 본론+결론 소제목 수를 정확히 {expected_h2}개로 "
                    f"맞추십시오."
                )
            }

        p_open_tags = re.findall(r'<p\b[^>]*>', content, re.IGNORECASE)
        p_close_tags = re.findall(r'</p\s*>', content, re.IGNORECASE)
        p_count = len(p_open_tags)
        if p_count != len(p_close_tags):
            return {
                'passed': False,
                'code': 'P_MALFORMED',
                'reason': f"p 태그 짝 불일치 (열림 {p_count}개, 닫힘 {len(p_close_tags)}개)",
                'feedback': '모든 문단은 <p>...</p> 형태로 정확히 닫아 주십시오.'
            }

        expected_min_p = total_sections * 2
        expected_max_p = total_sections * 4
        
        if p_count < expected_min_p:
             return {
                'passed': False,
                'code': 'P_SHORT',
                'reason': f"문단 수 부족 (현재 {p_count}개, 필요 {expected_min_p}개 이상)",
                'feedback': (
                    f"문단 수가 너무 적습니다. 총 {total_sections}개 섹션 기준으로 최소 {expected_min_p}개 "
                    f"문단(섹션당 2개 이상)이 필요합니다."
                )
            }

        if p_count > expected_max_p:
            return {
                'passed': False,
                'code': 'P_LONG',
                'reason': f"문단 수 과다 (현재 {p_count}개, 최대 {expected_max_p}개)",
                'feedback': (
                    f"문단 수가 너무 많습니다. 총 {total_sections}개 섹션 기준으로 {expected_max_p}개 이하로 줄이고, "
                    f"문단을 합쳐 중복 설명을 압축하십시오."
                )
            }

        # 장소 키워드가 단독 1문장 문단으로 반복되는 패턴을 하드 차단한다.
        # (한 번의 안내성 단문은 허용하되, 2회 이상 반복되면 반려)
        location_orphan_paragraphs: List[str] = []
        paragraph_blocks = re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', content, re.IGNORECASE)
        location_pattern = re.compile(r'(서면\s*영광도서|부산\s*영광도서)', re.IGNORECASE)
        for block in paragraph_blocks:
            paragraph_text = re.sub(r'<[^>]*>', ' ', block)
            paragraph_text = re.sub(r'\s+', ' ', paragraph_text).strip()
            if not paragraph_text:
                continue
            if not location_pattern.search(paragraph_text):
                continue

            sentence_tokens = [
                token.strip()
                for token in re.split(r'(?<=[.!?。])\s+', paragraph_text)
                if token and token.strip()
            ]
            sentence_count = len(sentence_tokens) if sentence_tokens else (1 if paragraph_text else 0)
            if sentence_count <= 1:
                location_orphan_paragraphs.append(paragraph_text)

        if len(location_orphan_paragraphs) >= 2:
            samples = '; '.join(f'"{text[:40]}{"..." if len(text) > 40 else ""}"' for text in location_orphan_paragraphs[:2])
            return {
                'passed': False,
                'code': 'LOCATION_ORPHAN_REPEAT',
                'reason': f"장소 단문 반복 ({len(location_orphan_paragraphs)}회)",
                'feedback': (
                    "서면/부산 영광도서가 들어간 단독 1문장 문단이 반복되었습니다. "
                    "장소 표현은 기존 문단의 주장/근거/행동 제안과 결합해 서술하고, "
                    "단독 안내 문단은 최대 1회만 허용됩니다. "
                    f"반복 예시: {samples}"
                )
            }

        plain_text = re.sub(r'<[^>]*>', ' ', content)
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()

        meta_leaks = self._find_meta_prompt_leak_sentences(content)
        if meta_leaks:
            sample = "; ".join(f'"{item[:45]}{"..." if len(item) > 45 else ""}"' for item in meta_leaks[:2])
            return {
                'passed': False,
                'code': 'META_PROMPT_LEAK',
                'reason': f"메타 문구 누수 ({len(meta_leaks)}문장)",
                'feedback': (
                    "프롬프트 규칙 설명 문장이 본문으로 출력되었습니다. "
                    "해당 문장을 삭제하고 실제 행사·정책 내용으로 대체하십시오. "
                    f"누수 예시: {sample}"
                )
            }

        overused_anchor_phrases = self._find_overused_anchor_phrases(content)
        if overused_anchor_phrases:
            detail = ", ".join(overused_anchor_phrases[:2])
            return {
                'passed': False,
                'code': 'PHRASE_REPEAT_CAP',
                'reason': f"상투 구문 반복 과다 ({detail})",
                'feedback': (
                    "대표 문구 반복이 과다합니다. 동일 어구는 원고 전체 최대 2회로 제한하고, "
                    "초과 구간은 새로운 사실/근거 문장으로 교체하십시오."
                )
            }

        material_reuse_issues = self._detect_material_reuse_issues(
            content,
            context_analysis,
            max_mentions=1,
        )
        if material_reuse_issues:
            samples = "; ".join(
                f"[{item.get('type')}] {str(item.get('text') or '')[:36]}"
                for item in material_reuse_issues[:2]
            )
            return {
                'passed': False,
                'code': 'MATERIAL_REUSE',
                'reason': f"동일 소재 재사용 감지 ({len(material_reuse_issues)}개)",
                'feedback': (
                    "같은 인용/일화/근거가 여러 섹션에서 반복되었습니다. "
                    "본론 섹션마다 서로 다른 소재를 1회씩만 사용하도록 재작성하십시오. "
                    f"중복 예시: {samples}"
                ),
            }

        event_signal_patterns = [
            r'\d{1,2}\s*월\s*\d{1,2}\s*일',
            r'출판기념회',
            r'행사',
            r'오후\s*\d{1,2}\s*시',
            r'서면\s*영광도서',
            r'부산\s*영광도서',
        ]
        event_signal_hits = sum(
            1 for pattern in event_signal_patterns if re.search(pattern, plain_text, re.IGNORECASE)
        )
        if is_event_announcement or event_signal_hits >= 2:
            event_fact_mentions = self._count_event_fact_sentence_mentions(
                content,
                event_date_hint=event_date_hint,
                event_location_hint=event_location_hint,
            )
            if event_fact_mentions > 2:
                return {
                    'passed': False,
                    'code': 'EVENT_FACT_REPEAT',
                    'reason': f"행사 일시/장소 문장 반복 과다 ({event_fact_mentions}회)",
                    'feedback': (
                        "행사 일시+장소가 결합된 안내 문장은 도입 1회, 결론 1회까지만 허용됩니다. "
                        "중간 본론에서는 '이번 행사 현장'처럼 변형해 반복을 줄이십시오."
                    )
                }

            invite_patterns = {
                '직접 만나': r'직접\s*만나',
                '진솔한 소통': r'진솔한\s*소통',
                '기다리겠습니다': r'기다리겠습니다',
            }
            overused_phrases = []
            for label, pattern in invite_patterns.items():
                count = len(re.findall(pattern, plain_text, re.IGNORECASE))
                if count > 2:
                    overused_phrases.append(f"{label} {count}회")

            if overused_phrases:
                detail = ", ".join(overused_phrases)
                return {
                    'passed': False,
                    'code': 'EVENT_INVITE_REDUNDANT',
                    'reason': f"행사 초대 문구 반복 과다 ({detail})",
                    'feedback': (
                        "행사 안내문은 정보 중심으로 간결하게 작성해야 합니다. "
                        "\"직접 만나\", \"진솔한 소통\", \"기다리겠습니다\" 류 문구는 각 2회 이하로 줄이고, "
                        "반복 구간은 행사 핵심 정보(일시/장소/참여 방법) 또는 새로운 근거 설명으로 대체하십시오."
                    )
                }

        return {'passed': True}
