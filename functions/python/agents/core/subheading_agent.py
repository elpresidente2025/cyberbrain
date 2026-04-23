"""SubheadingAgent — H2 소제목 Plan → Gen → Score → Repair 오케스트레이터.

파이프라인:
    1. _plan_sections         — 결정론적 Plan 추출 (h2_planning)
    2. generate_aeo_subheadings (primary LLM #1)
    3. _score_headings        — h2_scoring rubric 게이트
    4. _deterministic_prerepair — 조사/길이/질문형 잘림 등 cheap 수리
    5. _repair_failed_headings (LLM #2, 실패 섹션만)
    6. 원본 H2 유지 (마지막 방어선)

LLM 호출 예산: 최대 2회 (primary + repair 1회). 전부 pass 시 LLM #2는 short-circuit.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..base_agent import Agent
from ..common.constants import detect_commemorative_topic
from ..common.gemini_client import StructuredOutputError, generate_json_async
from ..common.h2_guide import (
    H2_ARCHETYPE_DESCRIPTIONS,
    H2_BEST_RANGE,
    H2_MAX_LENGTH,
    H2_MIN_LENGTH,
    H2_OPTIMAL_MIN,
    build_category_tone_block,
    build_h2_rules,
    get_category_tone,
    has_incomplete_h2_ending,
    normalize_h2_style,
    resolve_category_archetypes,
    sanitize_h2_text,
)
from ..common.h2_quality import h2_semantic_family_key, is_h2_prefix_fragment
from ..common.h2_planning import (
    SectionPlan,
    StanceBrief,
    assign_h2_entity_slots,
    build_descriptor_pool,
    build_target_keyword_canonical,
    classify_section_intent,
    detect_answer_type,
    distribute_keyword_assignments,
    extract_section_plan,
    extract_stance_claims,
    extract_user_role,
    localize_user_role,
    strip_html,
)
from ..common.h2_repair import (
    enforce_anchor_cap,
    enforce_keyword_diversity,
    enforce_user_role_lock,
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

# 결정론적 fallback 템플릿에 키워드로 들어가서는 안 되는 조사/어미 suffix.
# "외에도", "약화시" 같은 조각이 must_include_keyword 로 잘못 전파됐을 때를 막는 2차 방어선.
_UNSAFE_KEYWORD_SUFFIXES = (
    "에도", "으로도", "으로", "부터", "까지", "에서", "에게",
    "도", "시", "를", "을", "은", "는", "이", "가", "에", "의", "과", "와", "만",
)
_FALLBACK_LOW_SIGNAL_KEYWORDS = frozenset({
    "다시",
    "정책",
    "사업",
    "문제",
    "방안",
    "시민",
    "주민",
    "여러분",
    "감사합니다",
    "지역",
    "경제",
    "활성화",
    "변화",
})


def _is_field_copy(heading: str, plan: Dict[str, Any]) -> bool:
    """repair 결과가 plan XML 필드값을 그대로 복사한 것인지 판정.

    repair LLM이 H2를 생성하지 않고 assigned_entity_surface 등
    입력 필드를 그대로 반환하는 실패 모드를 차단한다.
    """
    h = heading.strip()
    for key in ("assigned_entity_surface", "must_include_keyword", "key_claim"):
        val = str(plan.get(key) or "").strip()
        if val and h == val:
            return True
    return False


def _should_replace(new_score: Dict[str, Any], current_score: Dict[str, Any]) -> bool:
    """H2 교체 판정. passed 가 score 보다 우선한다.

    순수 score 비교는 hard-fail heading (passed=False, score 0.82) 이
    archetype-valid repair (passed=True, score 0.78) 를 거부하는 역설을 만든다.
    """
    new_passed = bool(new_score.get("passed", False))
    cur_passed = bool(current_score.get("passed", False))
    if new_passed and not cur_passed:
        return True
    if cur_passed and not new_passed:
        return False
    return new_score.get("score", 0.0) > current_score.get("score", 0.0)


def _keyword_is_template_safe(keyword: str, plan: Dict[str, Any]) -> bool:
    """deterministic fallback 템플릿에 넣어도 안전한 키워드인지 판정.

    allowlist 는 user_keywords + entity_hints (둘 다 깨끗한 소스):
      - user_keywords: 호출자가 명시한 키워드.
      - entity_hints: h2_planning 에서 stopstem 필터 거친 고유명사 + full_name/full_region.

    allowlist 에 없고 조사/어미 suffix 로 끝나면 "약화시", "외에도" 같은 조각이므로 탈락.
    """
    kw = str(keyword or "").strip()
    if len(kw) < 2:
        return False
    allowlist = set(plan.get("user_keywords") or []) | set(plan.get("entity_hints") or [])
    if kw in allowlist:
        return True
    if kw.endswith(_UNSAFE_KEYWORD_SUFFIXES):
        return False
    return True


def _issue_key(issue: Any) -> str:
    return str(issue or "").split(":", 1)[0]


def _hard_fail_issue_count(score: Dict[str, Any]) -> int:
    return sum(
        1
        for issue in score.get("issues") or []
        if _issue_key(issue) in H2_HARD_FAIL_ISSUES
    )


def _has_batchim(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    code = ord(normalized[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return False


def _subject_particle(text: str) -> str:
    return "이" if _has_batchim(text) else "가"


def _object_particle(text: str) -> str:
    return "을" if _has_batchim(text) else "를"


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for item in items or ():
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


class SubheadingAgent(Agent):
    def __init__(self, name: str = "SubheadingAgent", options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        self.model_name = (options or {}).get("modelName", "gemini-2.5-flash")

    def get_style_config(self, category: str) -> Dict[str, Any]:
        """h2_guide.get_category_tone 결과를 style_config 로 반환."""
        return dict(get_category_tone(category))

    # -------------------------------------------------------------------- main
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await self._process_inner(context)
        except Exception as error:
            import traceback
            print(
                f"❌ [{self.name}] process() 실패 — 원본 content 유지: {error}\n{traceback.format_exc()}"
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
            print(f"[{self.name}] 입장문 {len(stance_text)}자 활용하여 소제목 최적화")

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
        print(f"✅ [SubheadingAgent] 매치업 모드 완료. stats={stats}")
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

        # H2-title 유사도 체크용: content 에서 글 제목 추출
        _title_m = re.search(r"<(?:h1|title)>(.*?)</(?:h1|title)>", content)
        article_title = _title_m.group(1).strip() if _title_m else ""

        print(
            f"✨ [SubheadingAgent] 소제목 {len(matches)}개 최적화 시작 (Category: {category})"
        )

        style_config = self.get_style_config(category)
        is_commemorative = detect_commemorative_topic(topic, stance_text)
        if is_commemorative:
            style_config["commemorative"] = True
        h2_style = normalize_h2_style(style_config.get("style"))
        override_types = list(
            style_config.get("preferred_types") or style_config.get("preferredTypes") or []
        )
        if override_types:
            preferred_types = override_types
        else:
            pool = resolve_category_archetypes(
                category or "default",
                commemorative=is_commemorative,
                matchup=False,
            )
            preferred_types = list(pool["primary"]) + list(pool["auxiliary"])

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
        user_role = localize_user_role(
            extract_user_role(user_profile or {}),
            region_metro=(user_profile or {}).get("regionMetro", ""),
            region_local=(user_profile or {}).get("regionLocal", ""),
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
                user_role=user_role,
            )
        except Exception as error:  # pragma: no cover - defensive
            print(f"❌ [SubheadingAgent] Primary generation failed: {error}")
            first_attempt = []

        if not first_attempt or len(first_attempt) != len(plans):
            print(
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
            full_region=full_region,
            descriptor_pool=descriptor_pool,
            body_first_sentences=body_first_sentences,
            target_keyword_canonical=target_keyword_canonical,
            user_keywords=list(user_keywords or []),
            score_key="first",
            article_title=article_title,
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
                    full_region=full_region,
                    descriptor_pool=descriptor_pool,
                    body_first_sentences=body_first_sentences,
                    target_keyword_canonical=target_keyword_canonical,
                    user_keywords=list(user_keywords or []),
                    article_title=article_title,
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
            full_region=full_region,
            descriptor_pool=descriptor_pool,
            body_first_sentences=body_first_sentences,
            target_keyword_canonical=target_keyword_canonical,
            article_title=article_title,
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
                    user_role=user_role,
                )
                llm_repair_called = True
            except Exception as error:
                print(f"❌ [SubheadingAgent] LLM repair batch failed: {error}")
                repaired_map = {}

            for idx, new_heading in repaired_map.items():
                if 0 <= idx < len(working):
                    cleaned = self._safe_sanitize(new_heading)
                    # repair LLM이 XML 필드값을 그대로 복사하는 실패 모드 차단
                    if cleaned and _is_field_copy(cleaned, plans[idx]):
                        print(f"⚠️ [SubheadingAgent] repair[{idx}] 필드값 복사 거부: {cleaned!r}")
                        cleaned = ""
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
                            full_region=full_region,
                            descriptor_pool=descriptor_pool,
                            body_first_sentences=body_first_sentences,
                            target_keyword_canonical=target_keyword_canonical,
                            user_keywords=list(user_keywords or []),
                            article_title=article_title,
                        )
                        trace[idx]["llm_repair"] = cleaned
                        trace[idx]["llm_repair_score"] = new_score.get("score", 0.0)
                        trace[idx]["llm_repair_issues"] = list(new_score.get("issues", []))
                        if _should_replace(new_score, current_scores[idx]):
                            working[idx] = cleaned
                            current_scores[idx] = new_score

        # ---------- Phase 6: final hard-fail control (실패 H2는 출력 전 결정론 fallback으로 교체)
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
                final_headings.append(heading)
                continue

            fallback_result = self._select_deterministic_fallback_heading(
                plan=plans[i],
                index=i,
                current_score=current_scores[i],
                siblings=working,
                h2_style=h2_style,
                preferred_types=preferred_types,
                full_name=full_name,
                full_region=full_region,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
                user_keywords=list(user_keywords or []),
                article_title=article_title,
                is_conclusion=(i == len(working) - 1),
            )
            fallback_heading = str(fallback_result.get("heading") or "").strip()
            fallback_score = fallback_result.get("score")
            if fallback_heading and isinstance(fallback_score, dict):
                working[i] = fallback_heading
                current_scores[i] = fallback_score
                trace[i]["deterministic_fallback"] = fallback_heading
                trace[i]["deterministic_fallback_score"] = fallback_score.get("score", 0.0)
                trace[i]["deterministic_fallback_issues"] = list(fallback_score.get("issues", []))
                trace[i]["deterministic_fallback_candidates"] = list(
                    fallback_result.get("candidates") or []
                )
                trace[i]["action"] = (
                    "deterministic_fallback"
                    if fallback_score.get("passed")
                    else "deterministic_fallback_unpassed"
                )
                final_headings.append(fallback_heading)
                continue

            # fallback 후보도 없을 때만 최후의 best-effort. 이 경로는 구조 parity 보존용이다.
            trace[i]["action"] = "best_effort"
            trace[i]["best_effort_issues"] = list(current_scores[i].get("issues") or [])
            final_headings.append(heading)

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
            print(
                f"🔧 [SubheadingAgent] anchor cap enforced: cap={anchor_cap_value}, "
                f"edits={len(anchor_cap_result.get('actions') or [])}"
            )

        # ---------- Phase 6.6: 본인 직책 잠금 (타인 역할 스탬핑 방지)
        role_lock_result = enforce_user_role_lock(
            final_headings,
            full_name=full_name,
            allowed_role=user_role,
        )
        if role_lock_result.get("edited"):
            locked_headings = list(role_lock_result.get("headings") or final_headings)
            for action in role_lock_result.get("actions") or []:
                idx = action.get("index")
                if isinstance(idx, int) and 0 <= idx < len(trace):
                    trace[idx]["role_lock_before"] = action.get("before")
                    trace[idx]["role_lock_after"] = action.get("after")
                    trace[idx]["role_lock_removed"] = action.get("removed")
                    trace[idx]["role_lock_applied"] = True
            final_headings = locked_headings
            print(
                f"🔒 [SubheadingAgent] user role lock enforced: allowed={user_role!r} "
                f"edits={len(role_lock_result.get('actions') or [])}"
            )

        # ---------- Phase 6.7: user keyword / entity 반복 스탬핑 방지
        # plan.entity_hints (h2_planning 이 kiwi + stopstem 필터로 걸러낸 고유명사)
        # 와 full_name / full_region 을 합쳐 변이형 포함 카운팅으로 cap 규제.
        aggregated_entity_hints: List[str] = []
        seen_hint: set = set()
        for anchor in (full_name, full_region):
            token = str(anchor or "").strip()
            if token and token not in seen_hint:
                seen_hint.add(token)
                aggregated_entity_hints.append(token)
        for plan in plans:
            for hint in plan.get("entity_hints") or []:
                token = str(hint or "").strip()
                if token and token not in seen_hint:
                    seen_hint.add(token)
                    aggregated_entity_hints.append(token)

        kw_diversity_result = enforce_keyword_diversity(
            final_headings,
            user_keywords=list(user_keywords or []),
            entity_hints=aggregated_entity_hints,
        )
        if kw_diversity_result.get("edited"):
            div_headings = list(kw_diversity_result.get("headings") or final_headings)
            for action in kw_diversity_result.get("actions") or []:
                idx = action.get("index")
                if isinstance(idx, int) and 0 <= idx < len(trace):
                    trace[idx]["keyword_diversity_before"] = action.get("before")
                    trace[idx]["keyword_diversity_after"] = action.get("after")
            final_headings = div_headings
            print(
                f"🔑 [SubheadingAgent] keyword diversity enforced: "
                f"edits={len(kw_diversity_result.get('actions') or [])}"
            )

        # ---------- Phase 6.8: question-form 의문형 보충 (모든 H2 대상)
        #   _deterministic_prerepair 는 passed=True 인 H2를 건너뛰므로,
        #   scoring 통과한 question-form H2("확정될까", "가능할까" 등)에도
        #   보충되도록 최종 단계에서 일괄 적용한다.
        #   (a) 미완결 관형절("것인" → "것인가?") 완성
        #   (b) 단순 "?" 보충
        for i, heading in enumerate(final_headings):
            if (
                plans[i].get("answer_type") == "question-form"
                and h2_style != "assertive"
                and heading
                and not heading.endswith("?")
            ):
                # (a) 미완결 관형절 완성
                completed = False
                for suffix, completion in self._QUESTION_COMPLETION_MAP.items():
                    if heading.endswith(suffix) and len(heading) + len(completion) <= H2_MAX_LENGTH:
                        final_headings[i] = heading + completion
                        completed = True
                        break
                # (b) 단순 "?" 보충
                if (
                    not completed
                    and self._QUESTION_ENDING_RE.search(heading)
                    and len(heading) + 1 <= H2_MAX_LENGTH
                ):
                    final_headings[i] = heading + "?"

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
                    "deterministic_fallback_unpassed",
                    "fallback_original",
                    "best_effort",
                )
            },
        }
        print(f"✅ [SubheadingAgent] 완료. stats={stats}")
        for i, entry in enumerate(trace):
            print(f"[SubheadingAgent] trace[{i}] {entry}")
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
        plans = [
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
        return distribute_keyword_assignments(plans)

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
        user_role: str = "",
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
            resolved_plans = distribute_keyword_assignments([
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
            ])

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
            user_role=user_role,
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
                print(
                    f"⚠️ [SubheadingAgent] primary 응답 개수 불일치: "
                    f"expected={target_count} got={len(processed)}"
                )
            return processed
        except StructuredOutputError as error:
            print(f"❌ [SubheadingAgent] Structured output validation failed: {error}")
        except Exception as error:
            print(f"❌ [SubheadingAgent] Generation failed: {error}")
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
        user_role: str = "",
    ) -> str:
        entity_hints = ", ".join(filter(None, [full_name, full_region])) or "(없음)"
        target_count = len(plans)
        style_description = str(style_config.get("description") or "").strip() or "(없음)"
        archetype_pool = resolve_category_archetypes(
            category or "default",
            commemorative=bool(style_config.get("commemorative")),
            matchup=bool(style_config.get("matchup")),
        )
        primary_archetypes = archetype_pool.get("primary", [])
        auxiliary_archetypes = archetype_pool.get("auxiliary", [])
        primary_text = ", ".join(primary_archetypes) or "(없음)"
        auxiliary_text = ", ".join(auxiliary_archetypes) or "(없음)"
        archetype_desc_lines = [
            f"  - {name}: {H2_ARCHETYPE_DESCRIPTIONS[name]}"
            for name in (primary_archetypes + auxiliary_archetypes)
            if name in H2_ARCHETYPE_DESCRIPTIONS
        ]
        archetype_desc_text = "\n".join(archetype_desc_lines) or "  - (없음)"
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
            specific_anchors = ", ".join(plan.get("specific_anchors") or []) or "(없음)"
            section_xml_parts.append(
                f"""<section index="{int(plan.get("index", 0)) + 1}">
  <suggested_type>{plan.get("suggested_type") or "(없음)"}</suggested_type>
  <must_include_keyword>{plan.get("must_include_keyword") or "(없음)"}</must_include_keyword>
  <query_intent>{plan.get("query_intent") or "info"}</query_intent>
  <answer_type>{plan.get("answer_type") or "question-form"}</answer_type>
  <assigned_entity_surface>{plan.get("assigned_entity_surface") or "(없음)"}</assigned_entity_surface>
  <numerics>{numerics}</numerics>
  <specific_anchors>{specific_anchors}</specific_anchors>
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
- **주 아키타입 (이 중에서 선택)**: {primary_text}
- **보조 아키타입 (본문이 주 아키타입에 맞지 않을 때만 사용)**: {auxiliary_text}
- **아키타입 설명**:
{archetype_desc_text}
- **Topic**: {topic or "(없음)"}
- **User Keywords**: {keywords_text}
- **본인 직책 (고정·SSOT)**: {user_role or "(없음)"}
- **Descriptor Pool (본명 대체 호칭)**: {descriptor_text}
{stance_block}

# [CRITICAL] H2 Rulebook (SSOT)
아래 XML 규칙 블록을 절대 우선으로 따르세요. 규칙, 금지어, few-shot 예시는 이 블록이 단일 원천입니다.
{build_h2_rules(h2_style)}
{tone_section}
# Section Plan Table
각 section 은 suggested_type / must_include_keyword / query_intent / answer_type / assigned_entity_surface / numerics / specific_anchors / key_claim / context 로 구성되어 있습니다. must_include_keyword는 해당 소제목 앞 1/3 안에 등장시키되, **context 본문의 실제 주제와 must_include_keyword가 맞지 않으면 본문 주제를 우선하세요.** 소제목은 본문을 정답으로 가정한 질문·주장이어야 합니다.
`specific_anchors`가 있으면 H2에 최소 1개를 자연스럽게 포함하십시오. "실행 계획", "제도 기반", "제도로 뒷받침", "재정 우려" 같은 추상 틀은 specific_anchors 없이 쓰면 실패입니다.
{sections_xml}

# [AEO/SEO] Entity Surface 정책 (필수 준수)
- 각 section 의 `assigned_entity_surface` 가 곧 그 H2 에서 사용해야 할 인물 표면형입니다.
- 본명({full_name or "(없음)"})은 H2 세트 전체에서 1~2회만 등장해야 합니다 (키워드 스탬핑 방지).
- 본인({full_name or "(없음)"})의 직책은 **"{user_role or "(미지정)"}"** 단 하나입니다. 본문 맥락이나 타인 언급에서 본 다른 직책(예: 국회의원/위원장/시장/대표 등)을 본인 옆에 **절대** 붙이지 마세요. 본인에게는 이 직책 외의 라벨을 스탬핑하는 순간 hard-fail 입니다.
- 본명이 아닌 슬롯에는 Descriptor Pool 의 호칭 중 의미가 가장 잘 맞는 것을 사용하되, 본문에 이미 등장한 표현이어야 합니다.
- `query_intent` 가 `cmp` 면 비교/대결 구조, `tx` 면 절차/방법 구조, `nav` 면 인물·이력 중심 구조, `info` 면 정보 정리형으로 작성하세요.
- `answer_type` 이 `question-form` 이면 의문형으로, `declarative-list` 면 숫자/항목 정리로, `declarative-fact` 면 단정형 주장으로 표현하세요.
- 감정 호소형 수사("함께 ~ 가자", "~을 위한 길", "~없었다면" 같은 반어, "약속드립니다/믿습니다" 단독 종결 등)는 H2 에서 금지입니다.

# Additional Constraints
- 단락마다 소제목 1개씩만 생성하세요.
- 입력 순서를 바꾸지 마세요.
- 소제목 텍스트만 생성하고 번호, 따옴표, 불릿은 넣지 마세요.
- {H2_MAX_LENGTH}자를 넘기지 마세요. (네이버 최적 범위 {H2_BEST_RANGE}자 이내를 목표로 하세요.)
- 소제목은 반드시 완결된 어절로 끝나야 합니다. 조사("를", "을", "의", "에서", "과" 등)나 미완결 어미("겠", "하는", "있는" 등)로 끝나는 소제목은 금지입니다.
- 본문 구절을 그대로 잘라 붙여 소제목을 만들지 마세요.
- 본문 고유 실행수단·대상·수치가 빠진 추상 소제목은 금지입니다. BAD: "기본소득, 제도 기반을 세우겠습니다" / GOOD: "기본소득은 태양광 배당에서 시작된다".
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
        full_region: str = "",
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
        user_keywords: Optional[Sequence[str]] = None,
        article_title: str = "",
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
            full_region=full_region,
            descriptor_pool=list(descriptor_pool or []),
            body_first_sentence=body_first,
            target_keyword_canonical=target_keyword_canonical,
            user_keywords=list(user_keywords or []),
            section_index=index,
            section_count=len(list(siblings or [])),
            article_title=article_title,
        )
        merged_issues = list(score.get("issues") or [])
        for issue in aeo.get("issues") or []:
            if issue not in merged_issues:
                merged_issues.append(issue)

        if is_h2_prefix_fragment(text) and "H2_TEXT_FRAGMENT" not in merged_issues:
            merged_issues.append("H2_TEXT_FRAGMENT")

        current_family = h2_semantic_family_key(text)
        if current_family:
            for sibling in sibling_others:
                if h2_semantic_family_key(sibling) == current_family:
                    if "H2_GENERIC_FAMILY_REPEAT" not in merged_issues:
                        merged_issues.append("H2_GENERIC_FAMILY_REPEAT")
                    break

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
        full_region: str = "",
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
        user_keywords: Optional[Sequence[str]] = None,
        score_key: str,
        article_title: str = "",
    ) -> None:
        """전체 score 리스트에 AEO 결과를 병합하고 trace 에 기록한다."""
        for i, sc in enumerate(scores):
            self._enrich_score_one(
                sc,
                heading=headings[i] if i < len(headings) else "",
                index=i,
                siblings=headings,
                full_name=full_name,
                full_region=full_region,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
                user_keywords=list(user_keywords or []),
                article_title=article_title,
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
    # question-form H2 에서 물음표 없는 질문형 종결 시 "?" 보충용
    # topic particle(은/는/을/를) + 의문형 EF(나요/까요/가요/까/나)
    _QUESTION_ENDING_RE = re.compile(r"(?:[가-힣](?:은|는|을|를)|나요|까요|가요|까|나)$")

    # 미완결 의문형 관형절 → 완성 매핑 (예: "것인" → "것인가?")
    # _QUESTION_ENDING_RE 보다 먼저 체크 — 2글자 이상 보충이 필요한 케이스.
    _QUESTION_COMPLETION_MAP: Dict[str, str] = {
        "것인": "가?",    # 관형형 "것인" → "것인가?"
        "것일": "까?",    # 관형형 "것일" → "것일까?"
    }

    def _deterministic_prerepair(self, heading: str, _plan: SectionPlan, *, style: str) -> str:
        text = self._safe_sanitize(heading)
        if not text:
            return ""

        # 0. question-form plan 인데 물음표 없는 질문형 종결이면 보충
        #    (a) 미완결 관형절("것인" → "것인가?") — 2글자 이상 보충
        #    (b) topic particle(은/는/을/를) + 의문형 EF(나요/까요/까/나) — "?" 1글자
        #    kiwi is_incomplete_ending 은 "?" 종결 시 즉시 완결 판정하므로,
        #    보충하면 while loop 미진입.
        added_question_mark = False
        if (
            _plan.get("answer_type") == "question-form"
            and style != "assertive"
            and not text.endswith("?")
        ):
            # (a) 미완결 관형절 완성
            completed = False
            for suffix, completion in self._QUESTION_COMPLETION_MAP.items():
                if text.endswith(suffix) and len(text) + len(completion) <= H2_MAX_LENGTH:
                    text = text + completion
                    added_question_mark = True
                    completed = True
                    break
            # (b) 단순 "?" 보충
            if (
                not completed
                and self._QUESTION_ENDING_RE.search(text)
                and len(text) + 1 <= H2_MAX_LENGTH
            ):
                text = text + "?"
                added_question_mark = True

        # 1. 길이 초과 → 마지막 어절 경계에서 절단
        if len(text) > H2_MAX_LENGTH:
            cut = text[:H2_MAX_LENGTH]
            last_space = cut.rfind(" ")
            if last_space >= H2_MIN_LENGTH:
                cut = cut[:last_space]
            text = cut.strip()

        # 2. trailing 조사/미완결 어미 제거 (H2_MIN_LENGTH 이하로는 줄이지 않음)
        #    skip_comma_tail=True: 반복 호출 시 쉼표 꼬리가 매 iteration 짧아지며
        #    연쇄 절단되는 문제 방지.
        while has_incomplete_h2_ending(text, skip_comma_tail=True):
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
        # step 0 에서 보충한 "?" 가 sanitize rstrip 에 의해 제거되었으면 복원
        if added_question_mark and not text.endswith("?"):
            text = text + "?"
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
        full_region: str = "",
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
        article_title: str = "",
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

        # preferred_names 는 repair_entity_consistency 의 "화자 보호" 가드로
        # 소비된다(h2_repair.py 1151). 여기 known_person_names 를 섞으면
        # 본인(full_name)과 타인이 동일 우선순위가 되어 본인 이름이 H2 에서
        # 타인 혹은 generic("지역/지방") 로 치환되는 Bug 1 경로가 열린다.
        # 반드시 본인 full_name 만 넣는다.
        preferred_names: List[str] = []
        if full_name:
            preferred_names.append(full_name)

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
            print(
                f"⚠️ [SubheadingAgent] h2_repair chain produced mismatched H2 count "
                f"(expected={len(matches)} got={len(new_matches)}) — skipping extraction."
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
                full_region=full_region,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
                user_keywords=list(user_keywords or []),
                article_title=article_title,
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
        user_role: str = "",
    ) -> Dict[int, str]:
        if not failing_indices:
            return {}

        entity_hints = ", ".join(filter(None, [full_name, full_region])) or "(없음)"
        tone_block = build_category_tone_block(category or "default")
        tone_section = f"\n{tone_block}\n" if tone_block else ""

        failed_xml_parts: List[str] = []
        for idx in failing_indices:
            plan = plans[idx]
            issues_text = ", ".join(issues_map.get(idx, [])) or "(없음)"
            ctx_slice = str(plan.get("section_text") or "")[:400]
            numerics = ", ".join(plan.get("numerics") or []) or "(없음)"
            specific_anchors = ", ".join(plan.get("specific_anchors") or []) or "(없음)"
            failed_xml_parts.append(
                f"""<failed_section index="{int(plan.get("index", idx))}">
  <previous_attempt>{prev_headings[idx] or "(비어 있음)"}</previous_attempt>
  <issues>{issues_text}</issues>
  <suggested_type>{plan.get("suggested_type") or "(없음)"}</suggested_type>
  <must_include_keyword>{plan.get("must_include_keyword") or "(없음)"}</must_include_keyword>
  <query_intent>{plan.get("query_intent") or "info"}</query_intent>
  <answer_type>{plan.get("answer_type") or "question-form"}</answer_type>
  <assigned_entity_surface>{plan.get("assigned_entity_surface") or "(없음)"}</assigned_entity_surface>
  <numerics>{numerics}</numerics>
  <specific_anchors>{specific_anchors}</specific_anchors>
  <key_claim>{plan.get("key_claim") or "(없음)"}</key_claim>
  <context>{ctx_slice}</context>
</failed_section>"""
            )
        failed_xml = "\n".join(failed_xml_parts)

        top_claims = [str(c).strip() for c in (stance_brief.get("top_claims") or []) if str(c).strip()]
        stance_line = ""
        if top_claims:
            stance_line = "**[입장문 핵심 주장]**: " + " / ".join(top_claims)

        # issue별 구체 교정 힌트 생성
        _ISSUE_HINTS = {
            "H2_GENERIC_CONTENT": (
                "소제목이 추상어만으로 구성됨. 본문의 구체적 사업명·지명·숫자·고유명사를 포함하세요. "
                "BAD: '혁신과 변화로 미래를 열겠습니다' → GOOD: '귤현동 탄약고 이전, 2027년까지 완료 목표'"
            ),
            "H2_LOW_INFORMATION_TEMPLATE": (
                "소제목이 저정보 템플릿에 머물렀음. specific_anchors 중 최소 1개를 넣어 본문 고유 실행수단을 드러내세요. "
                "BAD: '기본소득, 제도 기반을 세우겠습니다' → GOOD: '기본소득은 태양광 배당에서 시작된다'"
            ),
            "ARCHETYPE_MISMATCH": (
                "소제목이 7 아키타입(질문형/목표형/주장형/이유형/대조형/사례형/서술형) 중 어디에도 해당하지 않음. "
                "본문 내용에 맞는 아키타입을 선택하세요."
            ),
            "BODY_ALIGNMENT_LOW": (
                "소제목이 본문 내용과 무관함. context 본문을 읽고, 본문이 정답인 질문·주장을 만드세요."
            ),
            "KEYWORD_MISSING": (
                "must_include_keyword가 소제목에 없음. 본문 주제와 맞을 때만 keyword를 포함하세요."
            ),
            "H2_QUESTION_FORM_REQUIRED": (
                "질문형 아키타입인데 의문형이 아님. '~인가', '~할까', '~은?' 등 의문 종결로 바꾸세요."
            ),
            "TYPE_MISMATCH": (
                "suggested_type과 실제 아키타입이 다름. suggested_type에 맞게 수정하세요."
            ),
            "INCOMPLETE_ENDING": (
                "소제목이 조사/미완결 어미로 끝남. 완결된 어절로 마무리하세요."
            ),
        }
        all_issues: set = set()
        for idx in failing_indices:
            all_issues.update(issues_map.get(idx, []))
        all_issue_keys = {_issue_key(issue) for issue in all_issues}
        issue_hints = [
            f"- **{k}**: {v}" for k, v in _ISSUE_HINTS.items() if k in all_issue_keys
        ]
        issue_hint_block = "\n".join(issue_hints)
        issue_hint_section = f"\n# Issue-Specific Guidance\n{issue_hint_block}\n" if issue_hints else ""

        prompt = f"""
# Role Definition
당신은 소제목 교정 에디터입니다.
아래 소제목들이 규칙 위반으로 반려되었습니다. 각 항목의 issues 를 해소하는 **새 소제목**을 작성하세요.

# 핵심 원칙
1. **소제목은 본문(context)을 정답으로 가정한 질문·주장**이어야 합니다.
2. context 본문을 읽고, 본문 내용에서 H2를 역산하세요.
3. `specific_anchors`가 있으면 최소 1개를 소제목에 반영하세요.
4. {H2_OPTIMAL_MIN}~{H2_MAX_LENGTH}자 이내로 작성하세요.

# 금지
- `assigned_entity_surface` 값을 그대로 소제목으로 쓰지 마세요. 인물 표면형은 소제목의 **일부**로만 사용하세요.
- 추상어만으로 구성된 소제목 (혁신/미래/포용/도약/비전/발전)
- 감정 호소형 수사 ("함께 ~ 가자", "약속드립니다")

# Context
- **Entity**: {entity_hints}
- **본인 직책**: {user_role or "(없음)"}
{stance_line}
{tone_section}{issue_hint_section}
# Failed Sections
{failed_xml}

# Output Format (JSON Only)
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
            print(f"❌ [SubheadingAgent] Repair structured output failed: {error}")
            return {}
        except Exception as error:
            print(f"❌ [SubheadingAgent] Repair call failed: {error}")
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
    def _fallback_keyword_candidates(self, plan: SectionPlan) -> List[str]:
        raw_candidates: List[str] = []
        raw_candidates.append(str(plan.get("must_include_keyword") or "").strip())
        raw_candidates.extend(str(item or "").strip() for item in plan.get("candidate_keywords") or [])
        raw_candidates.extend(str(item or "").strip() for item in plan.get("entity_hints") or [])

        candidates: List[str] = []
        for keyword in _dedupe_preserve_order(raw_candidates):
            normalized = re.sub(r"\s+", " ", keyword).strip(" ,.:;!?\"'“”‘’")
            if len(normalized) < 2 or len(normalized) > 18:
                continue
            if normalized in _FALLBACK_LOW_SIGNAL_KEYWORDS:
                continue
            if not _keyword_is_template_safe(normalized, plan):
                continue
            candidates.append(normalized)
        return candidates

    def _normalize_fallback_heading_candidate(self, raw: str) -> str:
        candidate = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not candidate:
            return ""
        try:
            candidate = sanitize_h2_text(candidate)
        except ValueError:
            return ""
        if len(candidate) < H2_MIN_LENGTH or len(candidate) > H2_MAX_LENGTH:
            return ""
        if has_incomplete_h2_ending(candidate):
            return ""
        return candidate

    def _deterministic_fallback_candidates(
        self,
        plan: SectionPlan,
        *,
        is_conclusion: bool = False,
    ) -> List[str]:
        keywords = self._fallback_keyword_candidates(plan)
        if not keywords:
            return []

        keyword = keywords[0]
        specific_anchors = [
            str(anchor or "").strip()
            for anchor in (plan.get("specific_anchors") or [])
            if str(anchor or "").strip()
        ]
        suggested_type = str(plan.get("suggested_type") or "")
        numerics = list(plan.get("numerics") or [])
        key_claim = str(plan.get("key_claim") or "").strip()
        section_text = str(plan.get("section_text") or "")

        subject_particle = _subject_particle(keyword)
        object_particle = _object_particle(keyword)
        raw_candidates: List[str] = []

        def add(text: str) -> None:
            if text:
                raw_candidates.append(text)

        def _claim_declarative_ok() -> bool:
            return 12 <= len(key_claim) <= 22 and key_claim.endswith(("다", "다."))

        if specific_anchors:
            primary_anchor = specific_anchors[0]
            primary_anchor_subject = _subject_particle(primary_anchor)
            add(f"{keyword}은 {primary_anchor}에서 시작된다")
            add(f"{keyword}, {primary_anchor}부터 시작합니다")
            if len(specific_anchors) >= 2:
                secondary_anchor = specific_anchors[1]
                add(f"{keyword}은 {primary_anchor}와 {secondary_anchor}로 답한다")
        else:
            primary_anchor = ""
            primary_anchor_subject = ""

        if is_conclusion:
            if primary_anchor:
                add(f"{keyword}은 {primary_anchor}로 증명하겠습니다")
            else:
                add(f"{keyword}, 실행으로 증명하겠습니다")

        if re.search(r"(재정|건전성|부채|포퓰리즘|우려)", section_text):
            if primary_anchor:
                add(f"{keyword} 재원은 {primary_anchor}에서 시작된다")
            else:
                add(f"{keyword}{subject_particle} 낭비가 아닌 이유")
        if re.search(r"(조례|예산|제도|개정|근거|기반)", section_text):
            if primary_anchor:
                add(f"{keyword}은 {primary_anchor}로 제도화된다")
            else:
                add(f"{keyword}{object_particle} 조례로 뒷받침하겠습니다")
        if re.search(r"(자영업|소상공인|안전망|생존|골목상권)", section_text):
            if primary_anchor:
                add(f"{keyword}은 {primary_anchor}에서 효과를 낸다")
            else:
                add(f"{keyword}, 민생 안전망이 되다")
            add(f"{keyword}{subject_particle} 자영업자를 지킨다")
        if re.search(r"(소비|상권|경제|매출|역외|선순환)", section_text):
            if primary_anchor:
                add(f"{keyword}은 {primary_anchor}에서 효과를 낸다")

        templates = {
            "질문형": lambda: (
                f"{keyword}, {primary_anchor}{primary_anchor_subject} 왜 필요한가"
                if primary_anchor
                else f"{keyword}, 핵심 쟁점은 무엇인가요?"
            ),
            "목표형": lambda: (
                f"{keyword}은 {primary_anchor}에서 시작된다"
                if primary_anchor
                else f"{keyword}, 실행 계획을 세우겠습니다"
            ),
            "주장형": lambda: (
                key_claim if _claim_declarative_ok() else f"{keyword}{subject_particle} 필요하다"
            ),
            "이유형": lambda: (
                f"{keyword}에 {primary_anchor}{primary_anchor_subject} 필요한 이유"
                if primary_anchor
                else f"{keyword}{subject_particle} 필요한 이유"
            ),
            "대조형": lambda: (
                f"{keyword}은 {primary_anchor}에서 다르다"
                if primary_anchor
                else f"{keyword}, 기존 정책과 차이는?"
            ),
            "사례형": lambda: (
                f"{keyword} {numerics[0]}, 핵심 변화는?" if numerics else f"{keyword}, 현장에서 확인하다"
            ),
        }
        add(templates.get(suggested_type, lambda: f"{keyword}{subject_particle} 필요한 이유")())

        # 첫 키워드가 너무 길어 모든 템플릿이 탈락할 때를 대비해 다음 후보도 짧게 시도한다.
        for alt_keyword in keywords[1:3]:
            alt_subject = _subject_particle(alt_keyword)
            if primary_anchor:
                add(f"{alt_keyword}은 {primary_anchor}에서 시작된다")
                add(f"{alt_keyword}, {primary_anchor}{primary_anchor_subject} 왜 필요한가")
            else:
                add(f"{alt_keyword}{alt_subject} 필요한 이유")
                add(f"{alt_keyword}, 핵심 쟁점은 무엇인가요?")

        return _dedupe_preserve_order(
            [
                candidate
                for candidate in (
                    self._normalize_fallback_heading_candidate(item)
                    for item in raw_candidates
                )
                if candidate
            ]
        )

    def _deterministic_fallback_heading(self, plan: SectionPlan) -> str:
        candidates = self._deterministic_fallback_candidates(plan)
        return candidates[0] if candidates else ""

    def _select_deterministic_fallback_heading(
        self,
        *,
        plan: SectionPlan,
        index: int,
        current_score: H2Score,
        siblings: Sequence[str],
        h2_style: str,
        preferred_types: Sequence[str],
        full_name: str,
        full_region: str,
        descriptor_pool: Sequence[str],
        body_first_sentences: Sequence[str],
        target_keyword_canonical: str,
        user_keywords: Sequence[str],
        article_title: str = "",
        is_conclusion: bool = False,
    ) -> Dict[str, Any]:
        candidates = self._deterministic_fallback_candidates(
            plan,
            is_conclusion=is_conclusion,
        )
        if not candidates:
            return {"heading": "", "score": None, "candidates": []}

        current_hard_count = _hard_fail_issue_count(current_score)
        best_heading = ""
        best_score: Optional[H2Score] = None
        best_rank: tuple = (-999, -999, -999.0, -999.0, -999)

        for order, candidate in enumerate(candidates):
            score = score_h2(
                candidate,
                plan,
                style=h2_style,
                preferred_types=list(preferred_types or []),
            )
            self._enrich_score_one(
                score,
                heading=candidate,
                index=index,
                siblings=siblings,
                full_name=full_name,
                full_region=full_region,
                descriptor_pool=descriptor_pool,
                body_first_sentences=body_first_sentences,
                target_keyword_canonical=target_keyword_canonical,
                user_keywords=list(user_keywords or []),
                article_title=article_title,
            )
            hard_count = _hard_fail_issue_count(score)
            rank = (
                1 if score.get("passed") else 0,
                -hard_count,
                float(score.get("score") or 0.0),
                float(score.get("aeo_score") or 0.0),
                -order,
            )
            if rank > best_rank:
                best_rank = rank
                best_heading = candidate
                best_score = score

        if not best_heading or best_score is None:
            return {"heading": "", "score": None, "candidates": candidates}

        # fallback이 hard-fail 수를 줄이지 못하고 점수도 낮으면 기존 결과를 보존한다.
        if (
            not best_score.get("passed")
            and _hard_fail_issue_count(best_score) >= current_hard_count
            and float(best_score.get("score") or 0.0) <= float(current_score.get("score") or 0.0)
        ):
            return {"heading": "", "score": None, "candidates": candidates}

        return {"heading": best_heading, "score": best_score, "candidates": candidates}

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
