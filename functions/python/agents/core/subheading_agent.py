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
    assign_h2_entity_slots,
    build_descriptor_pool,
    build_target_keyword_canonical,
    classify_section_intent,
    detect_answer_type,
    extract_section_plan,
    extract_stance_claims,
    strip_html,
)
from ..common.h2_repair import (
    enforce_anchor_cap,
    ensure_user_keyword_first_slot,
    repair_awkward_phrases,
    repair_branding_phrases,
    repair_entity_consistency,
)
from ..common.h2_templates import (
    MATCHUP_HEADING_CUES,
    MATCHUP_KIND_TEMPLATES,
    build_matchup_heading,
    select_matchup_kind_sequence,
)
from ..common.h2_scoring import (
    H2_HARD_FAIL_ISSUES,
    H2Score,
    compute_anchor_cap,
    detect_emotion_appeal,
    score_h2,
    score_h2_aeo,
)

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
        try:
            return await self._process_inner(context)
        except Exception as error:
            logger.error(
                f"❌ [{self.name}] process() 실패 — 원본 content 유지: {error}",
                exc_info=True,
            )
            return {
                "content": context.get("content") or "",
                "optimized": False,
                "h2Trace": [],
                "subheadingStats": {"error": str(error)[:200]},
            }

    async def _process_inner(self, context: Dict[str, Any]) -> Dict[str, Any]:
        content = context.get("content")
        if not content:
            return {"content": "", "optimized": False, "h2Trace": [], "subheadingStats": {}}

        poll_focus_bundle = context.get("pollFocusBundle")
        if (
            isinstance(poll_focus_bundle, dict)
            and str(poll_focus_bundle.get("scope") or "").strip().lower() == "matchup"
        ):
            return await self._process_matchup(context, poll_focus_bundle)

        full_name = (
            context.get("fullName")
            or (context.get("author") or {}).get("name", "")
            or context.get("authorName", "")
            or ""
        )
        user_profile = context.get("userProfile") or {}
        full_region = context.get("fullRegion") or (
            f"{user_profile.get('regionMetro', '')} {user_profile.get('regionDistrict', '')}".strip()
        )
        category = context.get("category", "") or "default"

        stance_text = context.get("stanceText", "") or ""
        user_keywords = list(context.get("userKeywords") or [])
        topic = context.get("topic", "") or ""

        known_person_names = list(context.get("knownPersonNames") or [])
        role_facts = context.get("roleFacts") or {}
        preferred_keyword = context.get("preferredKeyword", "") or ""

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
            known_person_names=known_person_names,
            role_facts=role_facts,
            preferred_keyword=preferred_keyword,
            user_profile=user_profile,
        )

        return {
            "content": optimized_content,
            "optimized": True,
            "h2Trace": trace,
            "subheadingStats": stats,
        }

    # ----------------------------------------------------------- matchup mode
    async def _process_matchup(
        self,
        context: Dict[str, Any],
        bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """매치업 모드 — h2_templates 기반 결정론 배정·생성 (LLM 0회).

        generic process() 와 반환 shape 호환. 실패 섹션은 원본 유지.
        """
        content = context.get("content") or ""
        if not content:
            return {"content": "", "optimized": False, "h2Trace": [], "subheadingStats": {}}

        matches = list(_H2_PATTERN.finditer(content))
        if not matches:
            return {
                "content": content,
                "optimized": False,
                "h2Trace": [],
                "subheadingStats": {"matches": 0, "mode": "matchup"},
            }

        primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
        secondary_pairs_raw = (
            bundle.get("secondaryPairs") if isinstance(bundle.get("secondaryPairs"), list) else []
        )
        speaker = str(primary_pair.get("speaker") or bundle.get("speaker") or "").strip()
        primary_opponent = str(primary_pair.get("opponent") or "").strip()
        speaker_percent = str(
            primary_pair.get("speakerPercent") or primary_pair.get("speakerScore") or ""
        ).strip()
        opponent_percent = str(
            primary_pair.get("opponentPercent") or primary_pair.get("opponentScore") or ""
        ).strip()

        if not speaker or not primary_opponent:
            return {
                "content": content,
                "optimized": False,
                "h2Trace": [],
                "subheadingStats": {
                    "matches": len(matches),
                    "mode": "matchup",
                    "skipped": "missing_speaker_or_opponent",
                },
            }

        secondary_opponents: List[str] = []
        secondary_templates_by_opp: Dict[str, Dict[str, str]] = {}
        for pair in secondary_pairs_raw[:3]:
            if not isinstance(pair, dict):
                continue
            opp = str(pair.get("opponent") or "").strip()
            if opp:
                secondary_opponents.append(opp)
                secondary_templates_by_opp[opp] = {
                    "speakerPercent": str(
                        pair.get("speakerPercent") or pair.get("speakerScore") or ""
                    ).strip(),
                    "opponentPercent": str(
                        pair.get("opponentPercent") or pair.get("opponentScore") or ""
                    ).strip(),
                }

        allowed_raw = bundle.get("allowedH2Kinds") if isinstance(bundle.get("allowedH2Kinds"), list) else []
        template_overrides: Dict[str, str] = {}
        allowed_kind_ids: List[str] = []
        for raw_kind in allowed_raw:
            if not isinstance(raw_kind, dict):
                continue
            kind_id = str(raw_kind.get("id") or "").strip()
            if not kind_id:
                continue
            allowed_kind_ids.append(kind_id)
            tmpl = str(raw_kind.get("template") or "").strip()
            if tmpl:
                template_overrides[kind_id] = tmpl
        if not allowed_kind_ids:
            allowed_kind_ids = list(MATCHUP_KIND_TEMPLATES.keys())

        section_texts: List[str] = []
        originals: List[str] = []
        for match in matches:
            start_pos = match.end()
            next_text = content[start_pos : start_pos + 600]
            section_texts.append(strip_html(next_text))
            originals.append(match.group(1).strip())

        kind_sequence = select_matchup_kind_sequence(
            section_texts,
            primary_opponent=primary_opponent,
            speaker_percent=speaker_percent,
            opponent_percent=opponent_percent,
            secondary_opponents=secondary_opponents,
            allowed_kind_ids=allowed_kind_ids,
        )

        trace: List[Dict[str, Any]] = []
        final_headings: List[str] = []
        for index, kind in enumerate(kind_sequence):
            item: Dict[str, Any] = {
                "index": index,
                "original": originals[index],
                "kind": kind,
                "action": "pending",
            }
            heading = ""
            if kind:
                opp_for_kind = primary_opponent
                sp_for_kind = speaker_percent
                op_for_kind = opponent_percent
                if kind == "secondary_matchup":
                    for cand in secondary_opponents:
                        if cand and cand in section_texts[index]:
                            opp_for_kind = cand
                            sp_for_kind = secondary_templates_by_opp.get(cand, {}).get(
                                "speakerPercent", ""
                            )
                            op_for_kind = secondary_templates_by_opp.get(cand, {}).get(
                                "opponentPercent", ""
                            )
                            break
                heading = build_matchup_heading(
                    kind,
                    speaker=speaker,
                    opponent=opp_for_kind,
                    speaker_percent=sp_for_kind,
                    opponent_percent=op_for_kind,
                    template_override=template_overrides.get(kind, ""),
                )

            item["template_heading"] = heading

            chosen = ""
            if heading and speaker in heading and not has_incomplete_h2_ending(heading):
                cues = MATCHUP_HEADING_CUES.get(kind, ())
                cue_ok = not cues or any(c in heading for c in cues)
                if cue_ok and H2_MIN_LENGTH <= len(heading) <= H2_MAX_LENGTH:
                    chosen = heading
                    item["action"] = "matchup_template"

            if not chosen:
                chosen = originals[index]
                item["action"] = "fallback_original"

            item["final"] = chosen
            trace.append(item)
            final_headings.append(chosen)

        rebuilt = self._replace_h2_headings(content, matches, final_headings)

        stats = {
            "matches": len(matches),
            "mode": "matchup",
            "llm_calls": 0,
            "kind_sequence": list(kind_sequence),
            "actions": {
                action: sum(1 for item in trace if item.get("action") == action)
                for action in ("matchup_template", "fallback_original")
            },
        }
        logger.info(f"✅ [SubheadingAgent] 매치업 모드 완료. stats={stats}")
        return {
            "content": rebuilt,
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
        known_person_names: Optional[Sequence[str]] = None,
        role_facts: Optional[Dict[str, Any]] = None,
        preferred_keyword: str = "",
        user_profile: Optional[Dict[str, Any]] = None,
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

        # ---------- AEO 결정론 산출: 글 전체 1회
        target_keyword_canonical = build_target_keyword_canonical(
            preferred_keyword=preferred_keyword,
            full_name=full_name,
            user_keywords=user_keywords or [],
        )
        descriptor_pool = build_descriptor_pool(
            full_name=full_name,
            full_region=full_region,
            role_facts=role_facts or {},
            profile=user_profile or {},
        )
        assigned_entity_surfaces = assign_h2_entity_slots(
            len(plans),
            full_name=full_name,
            descriptor_pool=descriptor_pool,
        )
        body_first_sentences: List[str] = []
        for text in section_texts:
            cleaned = (text or "").strip()
            first = re.split(r"(?<=[.!?。?!])\s+", cleaned, maxsplit=1)[0] if cleaned else ""
            body_first_sentences.append(first[:200])

        for i, plan in enumerate(plans):
            plan["query_intent"] = classify_section_intent(section_texts[i])
            plan["answer_type"] = detect_answer_type(section_texts[i])
            plan["target_keyword_canonical"] = target_keyword_canonical
            plan["assigned_entity_surface"] = (
                assigned_entity_surfaces[i] if i < len(assigned_entity_surfaces) else ""
            )

        trace: List[Dict[str, Any]] = [
            {
                "index": i,
                "original": originals[i],
                "suggested_type": plans[i].get("suggested_type", ""),
                "must_include_keyword": plans[i].get("must_include_keyword", ""),
                "query_intent": plans[i].get("query_intent", ""),
                "answer_type": plans[i].get("answer_type", ""),
                "assigned_entity_surface": plans[i].get("assigned_entity_surface", ""),
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

        # ---------- Phase 3: score (rubric + AEO advisory + emotion hard-fail)
        first_scores = [
            score_h2(
                heading,
                plans[i],
                style=h2_style,
                preferred_types=preferred_types,
            )
            for i, heading in enumerate(first_attempt)
        ]
        self._enrich_scores_with_aeo(
            scores=first_scores,
            headings=first_attempt,
            trace=trace,
            full_name=full_name,
            descriptor_pool=descriptor_pool,
            body_first_sentences=body_first_sentences,
            target_keyword_canonical=target_keyword_canonical,
            score_key="first",
        )

        # ---------- Phase 4a: per-heading deterministic pre-repair (cheap: josa/length/질문형)
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
                self._enrich_score_one(
                    new_score,
                    heading=repaired,
                    index=i,
                    siblings=working,
                    full_name=full_name,
                    descriptor_pool=descriptor_pool,
                    body_first_sentences=body_first_sentences,
                    target_keyword_canonical=target_keyword_canonical,
                )
                current_scores[i] = new_score
                trace[i]["pre_repair"] = repaired
                trace[i]["pre_repair_score"] = new_score.get("score", 0.0)
                trace[i]["pre_repair_issues"] = list(new_score.get("issues", []))

        # ---------- Phase 4b: content-level h2_repair chain (entity/phrase/user-keyword)
        chain_actions = self._apply_h2_repair_chain(
            content=content,
            matches=matches,
            working=working,
            originals=originals,
            trace=trace,
            plans=plans,
            current_scores=current_scores,
            h2_style=h2_style,
            preferred_types=preferred_types,
            known_person_names=known_person_names or [],
            role_facts=role_facts or {},
            user_keywords=list(user_keywords or []),
            preferred_keyword=preferred_keyword,
            full_name=full_name,
            descriptor_pool=descriptor_pool,
            body_first_sentences=body_first_sentences,
            target_keyword_canonical=target_keyword_canonical,
        )

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
                        self._enrich_score_one(
                            new_score,
                            heading=cleaned,
                            index=idx,
                            siblings=working,
                            full_name=full_name,
                            descriptor_pool=descriptor_pool,
                            body_first_sentences=body_first_sentences,
                            target_keyword_canonical=target_keyword_canonical,
                        )
                        trace[idx]["llm_repair"] = cleaned
                        trace[idx]["llm_repair_score"] = new_score.get("score", 0.0)
                        trace[idx]["llm_repair_issues"] = list(new_score.get("issues", []))
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
            self._enrich_score_one(
                fallback_score,
                heading=fallback,
                index=i,
                siblings=working,
                full_name=full_name,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
            )
            trace[i]["deterministic_fallback"] = fallback
            trace[i]["deterministic_fallback_score"] = fallback_score.get("score", 0.0)
            trace[i]["deterministic_fallback_issues"] = list(fallback_score.get("issues", []))

            if fallback_score.get("passed"):
                trace[i]["action"] = "deterministic_fallback"
                final_headings.append(fallback)
            else:
                trace[i]["action"] = "fallback_original"
                final_headings.append(originals[i])

        # ---------- Phase 6.5: fullName 앵커 cap 강제 (스탬핑 방지)
        anchor_cap_value = compute_anchor_cap(len(final_headings))
        anchor_cap_result = enforce_anchor_cap(
            final_headings,
            full_name=full_name,
            cap=anchor_cap_value,
        )
        if anchor_cap_result.get("edited"):
            capped_headings = list(anchor_cap_result.get("headings") or final_headings)
            for action in anchor_cap_result.get("actions") or []:
                idx = action.get("index")
                if isinstance(idx, int) and 0 <= idx < len(trace):
                    trace[idx]["anchor_cap_before"] = action.get("before")
                    trace[idx]["anchor_cap_after"] = action.get("after")
                    trace[idx]["anchor_cap_applied"] = True
            final_headings = capped_headings
            logger.info(
                "🔧 [SubheadingAgent] anchor cap enforced: cap=%s, edits=%s",
                anchor_cap_value,
                len(anchor_cap_result.get("actions") or []),
            )

        for i, final in enumerate(final_headings):
            trace[i]["final"] = final

        # ---------- Phase 7: reconstruct content
        rebuilt = self._replace_h2_headings(content, matches, final_headings)

        from ..common.h2_scoring import (
            count_entity_distribution,
            detect_sibling_suffix_overlap,
        )

        entity_distribution = count_entity_distribution(
            final_headings, full_name=full_name, descriptor_pool=descriptor_pool
        )
        sibling_overlap = detect_sibling_suffix_overlap(final_headings)

        stats = {
            "matches": len(matches),
            "llm_calls": 2 if llm_repair_called else 1,
            "passed_first": sum(1 for sc in first_scores if sc.get("passed")),
            "passed_after_pre_repair": sum(1 for sc in current_scores if sc.get("passed")),
            "h2_repair_chain": chain_actions,
            "aeo": {
                "target_keyword_canonical": target_keyword_canonical,
                "descriptor_pool": list(descriptor_pool),
                "assigned_entity_surfaces": list(assigned_entity_surfaces),
                "entity_distribution": entity_distribution,
                "sibling_suffix_overlap": [
                    {"token": token, "count": count} for token, count in sibling_overlap
                ],
                "intent_mix": {
                    intent: sum(
                        1 for plan in plans if plan.get("query_intent") == intent
                    )
                    for intent in ("info", "nav", "cmp", "tx")
                },
                "answer_type_mix": {
                    atype: sum(
                        1 for plan in plans if plan.get("answer_type") == atype
                    )
                    for atype in (
                        "question-form",
                        "declarative-fact",
                        "declarative-list",
                    )
                },
                "first_aeo_score_avg": (
                    round(
                        sum(sc.get("aeo_score", 0.0) for sc in first_scores)
                        / max(len(first_scores), 1),
                        4,
                    )
                ),
            },
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

        descriptor_pool_global: List[str] = []
        for plan in plans:
            surface = str(plan.get("assigned_entity_surface") or "").strip()
            if surface and surface != full_name and surface not in descriptor_pool_global:
                descriptor_pool_global.append(surface)
        descriptor_text = ", ".join(descriptor_pool_global) or "(없음)"

        section_xml_parts: List[str] = []
        for plan in plans:
            ctx_slice = str(plan.get("section_text") or "")[:400]
            numerics = ", ".join(plan.get("numerics") or []) or "(없음)"
            section_xml_parts.append(
                f"""<section index="{int(plan.get("index", 0)) + 1}">
  <suggested_type>{plan.get("suggested_type") or "(없음)"}</suggested_type>
  <must_include_keyword>{plan.get("must_include_keyword") or "(없음)"}</must_include_keyword>
  <query_intent>{plan.get("query_intent") or "info"}</query_intent>
  <answer_type>{plan.get("answer_type") or "question-form"}</answer_type>
  <assigned_entity_surface>{plan.get("assigned_entity_surface") or "(없음)"}</assigned_entity_surface>
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
- **Descriptor Pool (본명 대체 호칭)**: {descriptor_text}
{stance_block}

# [CRITICAL] H2 Rulebook (SSOT)
아래 XML 규칙 블록을 절대 우선으로 따르세요. 규칙, 금지어, few-shot 예시는 이 블록이 단일 원천입니다.
{build_h2_rules(h2_style)}
{tone_section}
# Section Plan Table
각 section 은 suggested_type / must_include_keyword / query_intent / answer_type / assigned_entity_surface / numerics / key_claim / context 로 구성되어 있습니다. must_include_keyword는 반드시 해당 소제목 앞 1/3 안에 등장시켜야 합니다.
{sections_xml}

# [AEO/SEO] Entity Surface 정책 (필수 준수)
- 각 section 의 `assigned_entity_surface` 가 곧 그 H2 에서 사용해야 할 인물 표면형입니다.
- 본명({full_name or "(없음)"})은 H2 세트 전체에서 1~2회만 등장해야 합니다 (키워드 스탬핑 방지).
- 본명이 아닌 슬롯에는 Descriptor Pool 의 호칭 중 의미가 가장 잘 맞는 것을 사용하되, 본문에 이미 등장한 표현이어야 합니다.
- `query_intent` 가 `cmp` 면 비교/대결 구조, `tx` 면 절차/방법 구조, `nav` 면 인물·이력 중심 구조, `info` 면 정보 정리형으로 작성하세요.
- `answer_type` 이 `question-form` 이면 의문형으로, `declarative-list` 면 숫자/항목 정리로, `declarative-fact` 면 단정형 주장으로 표현하세요.
- 감정 호소형 수사("함께 ~ 가자", "~을 위한 길", "~없었다면" 같은 반어, "약속드립니다/믿습니다" 단독 종결 등)는 H2 에서 금지입니다.

# Additional Constraints
- 단락마다 소제목 1개씩만 생성하세요.
- 입력 순서를 바꾸지 마세요.
- 소제목 텍스트만 생성하고 번호, 따옴표, 불릿은 넣지 마세요.
- {H2_MAX_LENGTH - 2}자를 넘기지 마세요. (네이버 최적 범위 {H2_BEST_RANGE}자 이내를 목표로 하세요.)
- 소제목은 반드시 완결된 어절로 끝나야 합니다. 조사("를", "을", "의", "에서", "과" 등)나 미완결 어미("겠", "하는", "있는" 등)로 끝나는 소제목은 금지입니다.
- 본문 구절을 그대로 잘라 붙여 소제목을 만들지 마세요.
- 같은 단어를 연속으로 반복하거나 조사 오타가 남은 소제목은 출력하지 마세요.

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
    def _enrich_score_one(
        self,
        score: H2Score,
        *,
        heading: str,
        index: int,
        siblings: Sequence[str],
        full_name: str,
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
    ) -> H2Score:
        """단일 heading 의 score_h2 결과에 AEO advisory + emotion hard-fail 을 병합.

        - `score_h2_aeo` 는 advisory 점수와 issues 를 반환 (hard-fail 아님)
        - `detect_emotion_appeal` 결과는 `H2_EMOTION_APPEAL` 로 기록되며
          `H2_HARD_FAIL_ISSUES` 멤버이므로 `passed=False` 로 강제 강등
        """
        text = str(heading or "").strip()
        if not text:
            return score

        body_first = (
            body_first_sentences[index] if 0 <= index < len(body_first_sentences) else ""
        )
        sibling_others = [
            str(item or "").strip()
            for j, item in enumerate(siblings)
            if j != index and str(item or "").strip()
        ]
        aeo = score_h2_aeo(
            text,
            siblings=sibling_others,
            full_name=full_name,
            descriptor_pool=list(descriptor_pool or []),
            body_first_sentence=body_first,
            target_keyword_canonical=target_keyword_canonical,
            section_index=index,
            section_count=len(list(siblings or [])),
        )
        merged_issues = list(score.get("issues") or [])
        for issue in aeo.get("issues") or []:
            if issue not in merged_issues:
                merged_issues.append(issue)

        emotion_label = detect_emotion_appeal(text)
        if emotion_label:
            tag = f"H2_EMOTION_APPEAL:{emotion_label}"
            if tag not in merged_issues:
                merged_issues.append(tag)

        score["issues"] = merged_issues
        score["aeo_score"] = aeo.get("score", 0.0)
        score["aeo_breakdown"] = aeo.get("breakdown", {})

        hard_fail = any(
            (issue.split(":", 1)[0] if isinstance(issue, str) else "")
            in H2_HARD_FAIL_ISSUES
            for issue in merged_issues
        )
        if hard_fail:
            score["passed"] = False
        return score

    def _enrich_scores_with_aeo(
        self,
        *,
        scores: List[H2Score],
        headings: Sequence[str],
        trace: List[Dict[str, Any]],
        full_name: str,
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
        score_key: str,
    ) -> None:
        """전체 score 리스트에 AEO 결과를 병합하고 trace 에 기록한다."""
        for i, sc in enumerate(scores):
            self._enrich_score_one(
                sc,
                heading=headings[i] if i < len(headings) else "",
                index=i,
                siblings=headings,
                full_name=full_name,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
            )
            trace[i][f"{score_key}_score"] = sc.get("score", 0.0)
            trace[i][f"{score_key}_aeo_score"] = sc.get("aeo_score", 0.0)
            trace[i][f"{score_key}_issues"] = list(sc.get("issues", []))

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

    # --------------------------------------------------- h2_repair content chain
    def _apply_h2_repair_chain(
        self,
        *,
        content: str,
        matches: Sequence[re.Match],
        working: List[str],
        originals: Sequence[str],
        trace: List[Dict[str, Any]],
        plans: Sequence[SectionPlan],
        current_scores: List[H2Score],
        h2_style: str,
        preferred_types: Sequence[str],
        known_person_names: Sequence[str],
        role_facts: Dict[str, Any],
        user_keywords: Sequence[str],
        preferred_keyword: str,
        full_name: str,
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
    ) -> List[Dict[str, Any]]:
        """결정론 h2_repair 모듈 체인을 한 번에 적용.

        `working` 헤딩을 콘텐츠로 재조립해 entity_consistency → awkward_phrases →
        branding_phrases → ensure_user_keyword_first_slot 순으로 호출한 뒤, 변경된
        헤딩만 추출해 `working`·`current_scores`·`trace`를 갱신한다. LLM 호출 없음.
        """
        actions: List[Dict[str, Any]] = []
        if not matches:
            return actions

        safe_working: List[str] = []
        for i in range(len(matches)):
            heading = working[i] if i < len(working) and working[i] else originals[i]
            safe_working.append(heading or "")
        assembled = self._replace_h2_headings(content, matches, safe_working)

        preferred_names: List[str] = []
        if full_name:
            preferred_names.append(full_name)
        for name in known_person_names:
            if name and name not in preferred_names:
                preferred_names.append(name)

        if known_person_names:
            entity_result = repair_entity_consistency(
                assembled,
                list(known_person_names),
                preferred_names=preferred_names,
                role_facts=role_facts,
            )
            if entity_result.get("edited"):
                assembled = entity_result.get("content") or assembled
                actions.append(
                    {
                        "step": "entity_consistency",
                        "replacements": entity_result.get("replacements", []),
                    }
                )

        awkward_result = repair_awkward_phrases(assembled)
        if awkward_result.get("edited"):
            assembled = awkward_result.get("content") or assembled
            actions.append(
                {"step": "awkward_phrases", "details": awkward_result.get("actions", [])}
            )

        branding_result = repair_branding_phrases(assembled)
        if branding_result.get("edited"):
            assembled = branding_result.get("content") or assembled
            actions.append(
                {"step": "branding_phrases", "details": branding_result.get("actions", [])}
            )

        if user_keywords:
            keyword_result = ensure_user_keyword_first_slot(
                assembled,
                user_keywords,
                preferred_keyword=preferred_keyword,
            )
            if keyword_result.get("edited"):
                assembled = keyword_result.get("content") or assembled
                actions.append({"step": "ensure_user_keyword_first_slot"})

        if not actions:
            return actions

        new_matches = list(_H2_PATTERN.finditer(assembled))
        if len(new_matches) != len(matches):
            logger.warning(
                "⚠️ [SubheadingAgent] h2_repair chain produced mismatched H2 count "
                "(expected=%s got=%s) — skipping extraction.",
                len(matches),
                len(new_matches),
            )
            return actions

        for i, new_match in enumerate(new_matches):
            new_inner = self._safe_sanitize(new_match.group(1))
            if not new_inner or new_inner == working[i]:
                continue
            trace[i]["h2_repair_chain"] = new_inner
            working[i] = new_inner
            new_score = score_h2(
                new_inner,
                plans[i],
                style=h2_style,
                preferred_types=preferred_types,
            )
            self._enrich_score_one(
                new_score,
                heading=new_inner,
                index=i,
                siblings=working,
                full_name=full_name,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
            )
            trace[i]["h2_repair_chain_score"] = new_score.get("score", 0.0)
            trace[i]["h2_repair_chain_issues"] = list(new_score.get("issues", []))
            current_scores[i] = new_score

        return actions

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
