"""SubheadingAgent — H2 소제목 Plan → Gen → Score → Repair 오케스트레이터.

파이프라인:
    1. _plan_sections         — 결정론적 Plan 추출 (h2_planning)
    2. generate_aeo_subheadings (primary LLM #1)
    3. _score_headings        — h2_scoring rubric 게이트
    4. _deterministic_prerepair — 조사/길이/질문형 잘림 등 cheap 수리
    5. _repair_failed_headings (LLM #2, 실패 섹션만)
    6. _deterministic_fallback_heading — type별 템플릿
    7. 원본 H2 유지 (마지막 방어선)

LLM 호출 예산: 최대 2회 (primary + repair 1회). 전부 pass 시 LLM #2는 short-circuit.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..base_agent import Agent
from ..common.gemini_client import StructuredOutputError, generate_json_async
from ..common.h2_guide import (
    H2_BEST_RANGE,
    H2_MAX_LENGTH,
    H2_MIN_LENGTH,
    build_category_tone_block,
    build_h2_rules,
    get_category_tone,
    has_incomplete_h2_ending,
    normalize_h2_style,
    sanitize_h2_text,
)
from ..common.h2_planning import (
    SectionPlan,
    StanceBrief,
    extract_section_plan,
    extract_stance_claims,
    strip_html,
)
from ..common.h2_scoring import H2Score, score_h2

logger = logging.getLogger(__name__)

SUBHEADING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "headings": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        }
    },
    "required": ["headings"],
}

REPAIR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "repairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "heading": {"type": "string"},
                },
                "required": ["index", "heading"],
            },
            "minItems": 1,
        }
    },
    "required": ["repairs"],
}

_H2_PATTERN = re.compile(r"<h2>(.*?)</h2>", re.IGNORECASE)
_QUESTION_TAIL_RE = re.compile(r"(인가요|일까요|할까요|할까|는가|는지)\s*\?*$")
_BANNED_GENERIC_LEADS = ("정책", "방법", "소개", "논평", "입장", "안내")
_JOSA_TAIL_TOKENS = (
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "처럼",
    "보다",
    "과",
    "와",
    "의",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "도",
    "만",
    "로",
)


class SubheadingAgent(Agent):
    def __init__(self, name: str = "SubheadingAgent", options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        self.model_name = (options or {}).get("modelName", "gemini-2.0-flash")

    # ------------------------------------------------------------------ compat
    def get_style_config(self, category: str) -> Dict[str, Any]:
        """h2_guide.get_category_tone 결과를 레거시 키(preferredTypes)와 호환되도록 반환."""
        tone = dict(get_category_tone(category))
        tone.setdefault("preferredTypes", tone.get("preferred_types") or [])
        return tone

    # -------------------------------------------------------------------- main
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        content = context.get("content")
        if not content:
            return {"content": "", "optimized": False, "h2Trace": [], "subheadingStats": {}}

        full_name = (context.get("author") or {}).get("name", "") or context.get("authorName", "")
        user_profile = context.get("userProfile") or {}
        full_region = f"{user_profile.get('regionMetro', '')} {user_profile.get('regionDistrict', '')}".strip()
        category = context.get("category", "") or "default"

        stance_text = context.get("stanceText", "") or ""
        user_keywords = list(context.get("userKeywords") or [])
        topic = context.get("topic", "") or ""

        if stance_text:
            logger.info(f"[{self.name}] 입장문 {len(stance_text)}자 활용하여 소제목 최적화")

        optimized_content, trace, stats = await self.optimize_headings_in_content(
            content=content,
            category=category,
            full_name=full_name,
            full_region=full_region,
            stance_text=stance_text,
            user_keywords=user_keywords,
            topic=topic,
        )

        return {
            "content": optimized_content,
            "optimized": True,
            "h2Trace": trace,
            "subheadingStats": stats,
        }

    async def optimize_headings_in_content(
        self,
        *,
        content: str,
        category: str,
        full_name: str,
        full_region: str,
        stance_text: str = "",
        user_keywords: Optional[Sequence[str]] = None,
        topic: str = "",
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        matches = list(_H2_PATTERN.finditer(content))
        if not matches:
            return content, [], {"matches": 0}

        logger.info(
            f"✨ [SubheadingAgent] 소제목 {len(matches)}개 최적화 시작 (Category: {category})"
        )

        style_config = self.get_style_config(category)
        h2_style = normalize_h2_style(style_config.get("style"))
        preferred_types = list(
            style_config.get("preferred_types") or style_config.get("preferredTypes") or []
        )

        section_texts: List[str] = []
        originals: List[str] = []
        for match in matches:
            start_pos = match.end()
            next_text = content[start_pos : start_pos + 600]
            section_texts.append(strip_html(next_text))
            originals.append(match.group(1).strip())

        plans = self._plan_sections(
            section_texts=section_texts,
            category=category,
            style_config=style_config,
            full_name=full_name,
            full_region=full_region,
            user_keywords=user_keywords or [],
        )
        stance_brief = extract_stance_claims(stance_text) if stance_text else StanceBrief(
            top_claims=[], key_entities=[], dominant_type=""
        )

        trace: List[Dict[str, Any]] = [
            {
                "index": i,
                "original": originals[i],
                "suggested_type": plans[i].get("suggested_type", ""),
                "must_include_keyword": plans[i].get("must_include_keyword", ""),
                "action": "pending",
            }
            for i in range(len(plans))
        ]

        # ---------- Phase 2: primary LLM
        try:
            first_attempt = await self.generate_aeo_subheadings(
                sections=section_texts,
                style_config=style_config,
                full_name=full_name,
                full_region=full_region,
                stance_text=stance_text,
                plans=plans,
                stance_brief=stance_brief,
                topic=topic,
                user_keywords=user_keywords or [],
                category=category,
            )
        except Exception as error:  # pragma: no cover - defensive
            logger.error(f"❌ [SubheadingAgent] Primary generation failed: {error}")
            first_attempt = []

        if not first_attempt or len(first_attempt) != len(plans):
            logger.warning(
                "⚠️ [SubheadingAgent] 1차 생성 개수 불일치/실패. 결정론적 fallback으로 진행."
            )
            first_attempt = [""] * len(plans)

        for i, heading in enumerate(first_attempt):
            trace[i]["first_attempt"] = heading

        # ---------- Phase 3: score
        first_scores = [
            score_h2(
                heading,
                plans[i],
                style=h2_style,
                preferred_types=preferred_types,
            )
            for i, heading in enumerate(first_attempt)
        ]
        for i, sc in enumerate(first_scores):
            trace[i]["first_score"] = sc.get("score", 0.0)
            trace[i]["first_issues"] = list(sc.get("issues", []))

        # ---------- Phase 4: deterministic pre-repair
        working: List[str] = list(first_attempt)
        current_scores: List[H2Score] = list(first_scores)
        for i, sc in enumerate(first_scores):
            if sc.get("passed"):
                continue
            repaired = self._deterministic_prerepair(working[i], plans[i], style=h2_style)
            if repaired != working[i]:
                working[i] = repaired
                new_score = score_h2(
                    repaired,
                    plans[i],
                    style=h2_style,
                    preferred_types=preferred_types,
                )
                current_scores[i] = new_score
                trace[i]["pre_repair"] = repaired
                trace[i]["pre_repair_score"] = new_score.get("score", 0.0)

        # ---------- Phase 5: LLM repair (≤1 call, batched)
        failing_indices = [
            i for i, sc in enumerate(current_scores) if not sc.get("passed")
        ]
        llm_repair_called = False
        if failing_indices:
            try:
                repaired_map = await self._repair_failed_headings(
                    plans=plans,
                    failing_indices=failing_indices,
                    prev_headings=working,
                    issues_map={i: current_scores[i].get("issues", []) for i in failing_indices},
                    style_config=style_config,
                    full_name=full_name,
                    full_region=full_region,
                    stance_brief=stance_brief,
                    category=category,
                )
                llm_repair_called = True
            except Exception as error:
                logger.error(f"❌ [SubheadingAgent] LLM repair batch failed: {error}")
                repaired_map = {}

            for idx, new_heading in repaired_map.items():
                if 0 <= idx < len(working):
                    cleaned = self._safe_sanitize(new_heading)
                    if cleaned:
                        cleaned = self._deterministic_prerepair(cleaned, plans[idx], style=h2_style)
                        new_score = score_h2(
                            cleaned,
                            plans[idx],
                            style=h2_style,
                            preferred_types=preferred_types,
                        )
                        trace[idx]["llm_repair"] = cleaned
                        trace[idx]["llm_repair_score"] = new_score.get("score", 0.0)
                        if new_score.get("score", 0.0) > current_scores[idx].get("score", 0.0):
                            working[idx] = cleaned
                            current_scores[idx] = new_score

        # ---------- Phase 6: deterministic fallback + original preservation
        final_headings: List[str] = []
        for i, heading in enumerate(working):
            if current_scores[i].get("passed"):
                action = trace[i].get("action")
                if action == "pending":
                    if trace[i].get("llm_repair"):
                        trace[i]["action"] = "llm_repaired"
                    elif trace[i].get("pre_repair"):
                        trace[i]["action"] = "pre_repaired"
                    else:
                        trace[i]["action"] = "kept"
                final_headings.append(heading or originals[i])
                continue

            fallback = self._deterministic_fallback_heading(plans[i])
            fallback_score = score_h2(
                fallback,
                plans[i],
                style=h2_style,
                preferred_types=preferred_types,
            )
            trace[i]["deterministic_fallback"] = fallback
            trace[i]["deterministic_fallback_score"] = fallback_score.get("score", 0.0)

            if fallback_score.get("passed"):
                trace[i]["action"] = "deterministic_fallback"
                final_headings.append(fallback)
            else:
                trace[i]["action"] = "fallback_original"
                final_headings.append(originals[i])

        for i, final in enumerate(final_headings):
            trace[i]["final"] = final

        # ---------- Phase 7: reconstruct content
        rebuilt = self._replace_h2_headings(content, matches, final_headings)
        stats = {
            "matches": len(matches),
            "llm_calls": 2 if llm_repair_called else 1,
            "passed_first": sum(1 for sc in first_scores if sc.get("passed")),
            "passed_after_pre_repair": sum(1 for sc in current_scores if sc.get("passed")),
            "actions": {
                action: sum(1 for item in trace if item.get("action") == action)
                for action in (
                    "kept",
                    "pre_repaired",
                    "llm_repaired",
                    "deterministic_fallback",
                    "fallback_original",
                )
            },
        }
        logger.info(f"✅ [SubheadingAgent] 완료. stats={stats}")
        return rebuilt, trace, stats

    # ---------------------------------------------------------- Plan / prompt
    def _plan_sections(
        self,
        *,
        section_texts: Sequence[str],
        category: str,
        style_config: Dict[str, Any],
        full_name: str,
        full_region: str,
        user_keywords: Sequence[str],
    ) -> List[SectionPlan]:
        return [
            extract_section_plan(
                section_text=text,
                index=i,
                category=category,
                style_config=style_config,
                user_keywords=user_keywords,
                full_name=full_name,
                full_region=full_region,
            )
            for i, text in enumerate(section_texts)
        ]

    async def generate_aeo_subheadings(
        self,
        sections: Sequence[str],
        style_config: Dict[str, Any],
        full_name: str,
        full_region: str,
        stance_text: str = "",
        *,
        plans: Optional[Sequence[SectionPlan]] = None,
        stance_brief: Optional[StanceBrief] = None,
        topic: str = "",
        user_keywords: Optional[Sequence[str]] = None,
        category: str = "",
    ) -> List[str]:
        """Primary LLM 호출. 기존 시그니처 호환을 위해 sections/style_config/full_*/stance_text
        positional 파라미터를 유지하고, plans 등 신규 정보는 kwargs 로 받는다.
        """
        target_count = len(sections)
        if target_count == 0:
            return []

        h2_style = normalize_h2_style(style_config.get("style"))

        resolved_plans: List[SectionPlan]
        if plans and len(plans) == target_count:
            resolved_plans = list(plans)
        else:
            resolved_plans = [
                extract_section_plan(
                    section_text=sections[i],
                    index=i,
                    category=category or "default",
                    style_config=style_config,
                    user_keywords=user_keywords or [],
                    full_name=full_name,
                    full_region=full_region,
                )
                for i in range(target_count)
            ]

        resolved_brief = stance_brief or (
            extract_stance_claims(stance_text) if stance_text else StanceBrief(
                top_claims=[], key_entities=[], dominant_type=""
            )
        )

        prompt = self._build_primary_prompt(
            plans=resolved_plans,
            style_config=style_config,
            full_name=full_name,
            full_region=full_region,
            stance_brief=resolved_brief,
            topic=topic,
            user_keywords=user_keywords or [],
            category=category,
            h2_style=h2_style,
        )

        schema = {
            "type": "object",
            "properties": {
                "headings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": target_count,
                    "maxItems": target_count,
                }
            },
            "required": ["headings"],
        }

        try:
            payload = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.3,
                max_output_tokens=1200,
                retries=2,
                response_schema=schema,
                required_keys=("headings",),
            )
            headings = payload.get("headings")
            if not isinstance(headings, list):
                raise StructuredOutputError("headings must be an array.")

            processed: List[str] = []
            for heading in headings:
                cleaned = self._safe_sanitize(heading)
                processed.append(cleaned)
            if len(processed) != target_count:
                logger.warning(
                    "⚠️ [SubheadingAgent] primary 응답 개수 불일치: expected=%s got=%s",
                    target_count,
                    len(processed),
                )
            return processed
        except StructuredOutputError as error:
            logger.error(f"❌ [SubheadingAgent] Structured output validation failed: {error}")
        except Exception as error:
            logger.error(f"❌ [SubheadingAgent] Generation failed: {error}")
        return []

    def _build_primary_prompt(
        self,
        *,
        plans: Sequence[SectionPlan],
        style_config: Dict[str, Any],
        full_name: str,
        full_region: str,
        stance_brief: StanceBrief,
        topic: str,
        user_keywords: Sequence[str],
        category: str,
        h2_style: str,
    ) -> str:
        entity_hints = ", ".join(filter(None, [full_name, full_region])) or "(없음)"
        target_count = len(plans)
        style_description = str(style_config.get("description") or "").strip() or "(없음)"
        preferred_types_text = (
            ", ".join(
                str(item).strip()
                for item in (
                    style_config.get("preferred_types") or style_config.get("preferredTypes") or []
                )
                if str(item).strip()
            )
            or "(없음)"
        )
        is_assertive = h2_style == "assertive"
        role_name = (
            "정치 논평 전문 에디터"
            if is_assertive
            else "AEO(Answer Engine Optimization) & SEO 전문 카피라이터"
        )
        task_summary = (
            "주어진 논평/입장문 단락들을 분석하여, 날카롭고 주장이 담긴 소제목(H2)을 생성해야 합니다."
            if is_assertive
            else "주어진 본문 단락들을 분석하여, 검색 엔진과 사용자 모두에게 매력적인 최적의 소제목(H2)을 생성해야 합니다."
        )

        top_claims = [str(c).strip() for c in (stance_brief.get("top_claims") or []) if str(c).strip()]
        stance_block_lines = []
        if top_claims:
            stance_block_lines.append("**[입장문 핵심 주장]**:")
            for claim in top_claims:
                stance_block_lines.append(f"  - {claim}")
            entities = [str(e).strip() for e in (stance_brief.get("key_entities") or []) if str(e).strip()]
            if entities:
                stance_block_lines.append(f"**[주요 엔티티]**: {', '.join(entities)}")
        stance_block = "\n".join(stance_block_lines) if stance_block_lines else ""

        keywords_text = ", ".join([str(k).strip() for k in user_keywords if str(k).strip()]) or "(없음)"
        tone_block = build_category_tone_block(category or "default")

        section_xml_parts: List[str] = []
        for plan in plans:
            ctx_slice = str(plan.get("section_text") or "")[:400]
            numerics = ", ".join(plan.get("numerics") or []) or "(없음)"
            section_xml_parts.append(
                f"""<section index="{int(plan.get("index", 0)) + 1}">
  <suggested_type>{plan.get("suggested_type") or "(없음)"}</suggested_type>
  <must_include_keyword>{plan.get("must_include_keyword") or "(없음)"}</must_include_keyword>
  <numerics>{numerics}</numerics>
  <key_claim>{plan.get("key_claim") or "(없음)"}</key_claim>
  <context>{ctx_slice}</context>
</section>"""
            )
        sections_xml = "\n".join(section_xml_parts)

        tone_section = f"\n# [TONE ANCHOR] 카테고리별 톤 앵커 (few-shot)\n{tone_block}\n" if tone_block else ""

        return f"""
# Role Definition
당신은 대한민국 최고의 **{role_name}**입니다.
{task_summary}

# Input Data
- **Context**: {entity_hints}
- **Target Count**: {target_count} Headings
- **Style Summary**: {style_description}
- **Preferred Types**: {preferred_types_text}
- **Topic**: {topic or "(없음)"}
- **User Keywords**: {keywords_text}
{stance_block}

# [CRITICAL] H2 Rulebook (SSOT)
아래 XML 규칙 블록을 절대 우선으로 따르세요. 규칙, 금지어, few-shot 예시는 이 블록이 단일 원천입니다.
{build_h2_rules(h2_style)}
{tone_section}
# Section Plan Table
각 section 은 suggested_type / must_include_keyword / numerics / key_claim / context 로 구성되어 있습니다. must_include_keyword는 반드시 해당 소제목 앞 1/3 안에 등장시켜야 합니다.
{sections_xml}

# Additional Constraints
- 단락마다 소제목 1개씩만 생성하세요.
- 입력 순서를 바꾸지 마세요.
- 소제목 텍스트만 생성하고 번호, 따옴표, 불릿은 넣지 마세요.
- {H2_MAX_LENGTH - 2}자를 넘기지 마세요. (네이버 최적 범위 {H2_BEST_RANGE}자 이내를 목표로 하세요.)
- 소제목은 반드시 완결된 어절로 끝나야 합니다. 조사("를", "을", "의", "에서", "과" 등)나 미완결 어미("겠", "하는", "있는" 등)로 끝나는 소제목은 금지입니다.
- 본문 구절("미래에 대한 확신을", "이뤄내겠습니다" 등)을 잘라 붙여 소제목을 만들지 마세요.
- 같은 단어를 연속으로 반복하거나 "도약을을"처럼 조사 오타가 남은 소제목은 출력하지 마세요.

# Output Format (JSON Only)
반드시 아래 JSON 포맷으로 출력하세요. 순서는 section index 와 일치해야 합니다.
{{
  "headings": [
    "생성된 소제목1",
    "생성된 소제목2"
  ]
}}
"""

    # ------------------------------------------------------------------- score
    def _safe_sanitize(self, raw: Any) -> str:
        try:
            return sanitize_h2_text(str(raw))
        except ValueError:
            return ""

    # -------------------------------------------------------- pre-repair cheap
    def _deterministic_prerepair(self, heading: str, _plan: SectionPlan, *, style: str) -> str:
        text = self._safe_sanitize(heading)
        if not text:
            return ""

        # 1. 길이 초과 → 마지막 어절 경계에서 절단
        if len(text) > H2_MAX_LENGTH:
            cut = text[:H2_MAX_LENGTH]
            last_space = cut.rfind(" ")
            if last_space >= H2_MIN_LENGTH:
                cut = cut[:last_space]
            text = cut.strip()

        # 2. trailing 조사/미완결 어미 제거 (H2_MIN_LENGTH 이하로는 줄이지 않음)
        while has_incomplete_h2_ending(text):
            tokens = text.split(" ")
            if len(tokens) <= 1:
                break
            truncated = " ".join(tokens[:-1]).strip()
            if len(truncated) < H2_MIN_LENGTH:
                break
            text = truncated

        stripped_last = text
        changed = True
        while changed:
            changed = False
            for josa in _JOSA_TAIL_TOKENS:
                if stripped_last.endswith(josa) and len(stripped_last) - len(josa) >= H2_MIN_LENGTH:
                    stripped_last = stripped_last[: -len(josa)].rstrip()
                    changed = True
        text = stripped_last

        # 3. assertive 에서 질문형 어미/물음표 제거
        if style == "assertive":
            while text.endswith("?"):
                text = text[:-1].rstrip()
            text = _QUESTION_TAIL_RE.sub("", text).rstrip()

        # 4. 서두 banned generic 제거
        for lead in _BANNED_GENERIC_LEADS:
            prefix = f"{lead} "
            if text.startswith(prefix) and len(text) - len(prefix) >= H2_MIN_LENGTH:
                text = text[len(prefix):].lstrip()
                break

        text = self._safe_sanitize(text)
        return text

    # -------------------------------------------------------------- repair LLM
    async def _repair_failed_headings(
        self,
        *,
        plans: Sequence[SectionPlan],
        failing_indices: Sequence[int],
        prev_headings: Sequence[str],
        issues_map: Dict[int, List[str]],
        style_config: Dict[str, Any],
        full_name: str,
        full_region: str,
        stance_brief: StanceBrief,
        category: str,
    ) -> Dict[int, str]:
        if not failing_indices:
            return {}

        h2_style = normalize_h2_style(style_config.get("style"))
        entity_hints = ", ".join(filter(None, [full_name, full_region])) or "(없음)"
        tone_block = build_category_tone_block(category or "default")
        tone_section = f"\n{tone_block}\n" if tone_block else ""

        failed_xml_parts: List[str] = []
        for idx in failing_indices:
            plan = plans[idx]
            issues_text = ", ".join(issues_map.get(idx, [])) or "(없음)"
            ctx_slice = str(plan.get("section_text") or "")[:400]
            numerics = ", ".join(plan.get("numerics") or []) or "(없음)"
            failed_xml_parts.append(
                f"""<failed_section index="{int(plan.get("index", idx))}">
  <previous_attempt>{prev_headings[idx] or "(비어 있음)"}</previous_attempt>
  <issues>{issues_text}</issues>
  <suggested_type>{plan.get("suggested_type") or "(없음)"}</suggested_type>
  <must_include_keyword>{plan.get("must_include_keyword") or "(없음)"}</must_include_keyword>
  <numerics>{numerics}</numerics>
  <key_claim>{plan.get("key_claim") or "(없음)"}</key_claim>
  <context>{ctx_slice}</context>
</failed_section>"""
            )
        failed_xml = "\n".join(failed_xml_parts)

        top_claims = [str(c).strip() for c in (stance_brief.get("top_claims") or []) if str(c).strip()]
        stance_line = ""
        if top_claims:
            stance_line = "**[입장문 핵심 주장]**: " + " / ".join(top_claims)

        prompt = f"""
# Role Definition
당신은 대한민국 최고의 소제목 교정 에디터입니다.
아래 소제목들이 규칙 위반으로 반려되었습니다. 각 항목의 issues 배열을 모두 해소하는 **새 소제목**을 작성하세요.

# Context
- **Entity**: {entity_hints}
{stance_line}

# [CRITICAL] H2 Rulebook (SSOT)
{build_h2_rules(h2_style)}
{tone_section}
# Failed Sections
{failed_xml}

# Output Format (JSON Only)
반드시 아래 JSON 포맷으로, 원래 section index 를 유지해 출력하세요.
{{
  "repairs": [
    {{"index": 0, "heading": "교정된 소제목"}},
    {{"index": 1, "heading": "교정된 소제목"}}
  ]
}}
"""

        try:
            payload = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.25,
                max_output_tokens=900,
                retries=2,
                response_schema=REPAIR_RESPONSE_SCHEMA,
                required_keys=("repairs",),
            )
        except StructuredOutputError as error:
            logger.error(f"❌ [SubheadingAgent] Repair structured output failed: {error}")
            return {}
        except Exception as error:
            logger.error(f"❌ [SubheadingAgent] Repair call failed: {error}")
            return {}

        repairs = payload.get("repairs") or []
        result: Dict[int, str] = {}
        for item in repairs:
            try:
                idx = int(item.get("index"))
                heading = str(item.get("heading") or "").strip()
            except (TypeError, ValueError):
                continue
            if heading:
                result[idx] = heading
        return result

    # --------------------------------------------------------- fallback heading
    def _deterministic_fallback_heading(self, plan: SectionPlan) -> str:

        keyword = str(plan.get("must_include_keyword") or "").strip()
        suggested_type = str(plan.get("suggested_type") or "")
        numerics = list(plan.get("numerics") or [])
        key_claim = str(plan.get("key_claim") or "").strip()

        templates = {
            "질문형": lambda: f"{keyword}, 어떻게 신청하나요?" if keyword else "",
            "명사형": lambda: f"{keyword} 핵심 정리" if keyword else "",
            "데이터형": lambda: (
                f"{keyword} {numerics[0]} 현황" if keyword and numerics else (f"{keyword} 핵심 정리" if keyword else "")
            ),
            "절차형": lambda: f"{keyword} 신청 3단계 절차" if keyword else "",
            "비교형": lambda: f"{keyword} 비교 핵심 정리" if keyword else "",
            "단정형": lambda: (
                key_claim if 12 <= len(key_claim) <= 22 and key_claim.endswith(("다", "다.")) else (f"{keyword}은 바로잡아야 한다" if keyword else "")
            ),
            "주장형": lambda: (
                key_claim if 12 <= len(key_claim) <= 22 and key_claim.endswith(("다", "다.")) else (f"{keyword}은 바로잡아야 한다" if keyword else "")
            ),
            "비판형": lambda: (
                (key_claim[:20].rstrip() + " 태도") if key_claim else (f"{keyword}의 구조적 한계" if keyword else "")
            ),
        }

        raw = templates.get(suggested_type, lambda: (f"{keyword} 핵심 정리" if keyword else key_claim))()
        raw = raw.strip()
        if not raw:
            return ""
        try:
            return sanitize_h2_text(raw)
        except ValueError:
            return raw[:H2_MAX_LENGTH]

    # -------------------------------------------------------- content rewrite
    def _replace_h2_headings(
        self,
        content: str,
        matches: Sequence[re.Match],
        headings: Sequence[str],
    ) -> str:
        if not matches or len(matches) != len(headings):
            return content
        parts: List[str] = []
        last_index = 0
        for match, heading in zip(matches, headings):
            parts.append(content[last_index : match.start()])
            parts.append(f"<h2>{heading}</h2>")
            last_index = match.end()
        parts.append(content[last_index:])
        return "".join(parts)
