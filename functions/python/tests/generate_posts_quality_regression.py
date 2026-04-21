from __future__ import annotations

import asyncio
import pathlib
import re
import sys
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common.poll_citation import build_poll_citation_text
from agents.common.role_keyword_policy import (
    build_role_keyword_policy,
    order_role_keyword_intent_anchor_candidates,
)
from agents.common.section_contract import (
    get_section_contract_sequence,
    infer_sentence_role,
    split_sentences,
    validate_cross_section_contracts,
    validate_section_contract,
)
from agents.common.title_generation import (
    _assess_initial_title_length_discipline,
    _compute_similarity_penalty,
    _repair_title_for_missing_keywords,
    build_title_prompt,
    calculate_title_quality_score,
    generate_and_validate_title,
    validate_theme_and_content,
)
from agents.common.xml_builder import build_context_analysis_section
from agents.core.structure_agent import StructureAgent
from agents.core.content_validator import ContentValidator
from agents.core.prompt_guards import _build_style_generation_guard
from agents.core.writer_agent import _should_keep_must_include_stance
from agents.core.prompt_builder import (
    build_retry_directive,
    build_structure_prompt,
    build_style_role_priority_summary,
)
from handlers.generate_posts import (
    ApiError,
    _apply_global_style_ai_alternative_rules_once,
    _apply_final_sentence_polish_once,
    _apply_targeted_sentence_rewrites,
    _build_display_keyword_validation,
    _build_independent_final_title_context,
    _contains_targeted_beyond_boilerplate,
    _detect_integrity_gate_issues,
    _collect_targeted_sentence_polish_candidates,
    _guard_draft_title_nonfatal,
    _guard_title_after_editor,
    _is_orphan_boilerplate_sentence,
    _is_unsupported_comparison_sentence,
    _remove_groundedness_violations_from_section,
    _remove_off_topic_poll_sentences_once,
    _repair_intent_only_role_keyword_mentions_once,
    _repair_competitor_policy_phrase_once,
    _normalize_lawmaker_honorifics_once,
    _repair_terminal_sentence_spacing_once,
    _prune_problematic_integrity_fragments,
    _repair_integrity_noise_once,
    _score_title_compliance,
    _scrub_suspicious_poll_residue_text,
    _sanitize_auto_keywords,
    _should_carry_recent_titles_from_prior_session,
)
from agents.common.h2_repair import repair_generic_surface as _repair_generic_subheading_surface_text
from handlers.generate_posts_pkg.pipeline import (
    _apply_speaker_name_keyword_max_override,
    _build_title_stance_summary,
    _repair_self_reference_placeholders_once,
    _repair_keyword_gate_once,
)
from services.posts.poll_focus_bundle import build_poll_focus_bundle
from services.posts.poll_fact_guard import (
    build_poll_matchup_fact_table,
    enforce_poll_fact_consistency,
)
from services.posts.content_processor import repair_duplicate_particles_and_tokens
from services.posts.output_formatter import finalize_output
from services.posts.personalization import generate_style_hints
from services.memory import _update_recent_titles
from services.posts.validation import (
    _build_keyword_replacement_pool,
    _count_user_keyword_exact_non_overlap,
    _inject_keyword_into_section,
    _remove_low_signal_keyword_sentence_once,
    _reduce_excess_user_keyword_mentions,
    _rewrite_sentence_to_reduce_keyword,
    _should_block_role_keyword_reference_sentence,
    enforce_keyword_requirements,
    force_insert_preferred_exact_keywords,
    force_insert_insufficient_keywords,
    validate_keyword_insertion,
)
from services.posts.validation.keyword_injection import _rewrite_sentence_with_keyword
from agents.common.h2_repair import (
    ensure_user_keyword_first_slot as _h2_ensure_user_keyword_first_slot,
    repair_entity_consistency as _h2_repair_entity_consistency_once,
)


def _ensure_user_keyword_in_subheading_once(content, user_keywords, *, preferred_keyword=""):
    return _h2_ensure_user_keyword_first_slot(
        content, user_keywords, preferred_keyword=preferred_keyword
    )


def _repair_subheading_entity_consistency_once(
    content, known_names, *, preferred_names=None, role_facts=None
):
    return _h2_repair_entity_consistency_once(
        content,
        known_names,
        preferred_names=preferred_names or (),
        role_facts=role_facts,
    )


def test_rewrite_excess_keyword_sentence() -> None:
    content = """
    <h2>'주진우 부산시장' 검색어가 거론되는 이유</h2>
    <p>온라인에서는 '주진우 부산시장' 검색어도 함께 거론되고 있습니다. 주진우 의원과의 가상대결은 치열합니다. 주진우 의원의 행보가 주목받고 있습니다. 주진우 의원과의 경쟁도 피할 수 없습니다.</p>
    <p>주진우 의원과의 경쟁에서도 저는 준비돼 있습니다. 주진우 의원의 비교 우위만 강조하는 문장은 줄여야 합니다. 부산 경제는 이재성입니다.</p>
    """
    user_keywords = ["주진우", "주진우 부산시장"]

    reduced = _reduce_excess_user_keyword_mentions(
        content,
        "주진우",
        user_keywords,
        target_max=4,
        shadowed_by=["주진우 부산시장"],
    )

    updated = str(reduced.get("content") or "")
    counts = _count_user_keyword_exact_non_overlap(updated, user_keywords)

    assert int(counts.get("주진우") or 0) == 4
    assert "비교 우위만 강조하는 문장은 줄여야 합니다." in updated
    assert int(reduced.get("rewrittenSentences") or 0) >= 1


def test_rewrite_sentence_to_reduce_role_keyword_avoids_related_issue_fragment() -> None:
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "주진우 부산시장이 아닌 제가 부산의 새로운 미래를 열겠습니다.",
        "주진우 부산시장",
    )

    assert rewritten == "제가 부산의 새로운 미래를 열겠습니다."
    assert "관련 사안" not in rewritten


def test_build_keyword_replacement_pool_avoids_issue_tokens() -> None:
    pool = _build_keyword_replacement_pool("부산 경제")

    assert pool
    assert "관련 사안" not in pool
    assert "이 사안" not in pool


def test_reduce_excess_place_keyword_does_not_leak_generic_person_reference() -> None:
    # Why: "샘플구 샘플단지" 같이 첫 토큰이 2글자 한글인 장소·사업명 키워드가
    #      이전에는 사람 이름("샘플구")으로 오인돼 뒷부분이 역할로 해석되면서
    #      최종 치환 결과가 bare "상대" 로 떨어지는 버그가 있었다.
    content = (
        "<p>샘플구 샘플단지 활성화에 매진해 온 저는 이 사업의 성공을 약속합니다. "
        "샘플구 샘플단지의 성공적인 조성은 지역 경제를 살립니다. "
        "샘플구 샘플단지는 미래 산업의 허브가 될 것입니다. "
        "샘플구 샘플단지를 세계적 단지로 만들겠습니다. "
        "샘플구 샘플단지에 대한 기대가 큽니다. "
        "샘플구 샘플단지의 완성을 향해 나아갑니다. "
        "샘플구 샘플단지 조성에는 협력이 필수입니다. "
        "샘플구 샘플단지 프로젝트가 본격 추진됩니다.</p>"
    )
    user_keywords = ["샘플구 샘플단지"]

    reduced = _reduce_excess_user_keyword_mentions(
        content,
        "샘플구 샘플단지",
        user_keywords,
        target_max=4,
    )

    updated = str(reduced.get("content") or "")
    assert "상대" not in updated
    assert "상대 의원" not in updated
    assert "상대의" not in updated


def test_should_keep_must_include_stance_filters_meta_and_branding_lines() -> None:
    assert _should_keep_must_include_stance("부산의 산업 전환 속도를 더 높여야 합니다.", "이재성") is True
    assert _should_keep_must_include_stance("이재성도 충분히 이깁니다.", "이재성") is False
    assert _should_keep_must_include_stance("부산 경제는 이재성입니다.", "이재성") is False
    assert _should_keep_must_include_stance("* KNN 뉴스 3월5일(목) 17시 방송분", "이재성") is False
    assert _should_keep_must_include_stance("#송영길 국회의원 보좌관", "문세종") is False


def test_build_context_analysis_section_omits_hashtag_bullet_stance_phrases() -> None:
    xml = build_context_analysis_section(
        {
            "mustIncludeFromStance": [
                "#profile_bullet",
                "#role_bullet",
                "{region} 주민 삶의 질을 높이겠습니다.",
            ]
        },
        "{user_name}",
    )

    assert "#profile_bullet" not in xml
    assert "#role_bullet" not in xml
    assert "{region} 주민 삶의 질을 높이겠습니다." in xml


# synthetic_fixture
def test_build_structure_prompt_skips_hashtag_bullet_stance_items() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "{region} 현안과 정책 방향",
            "category": "activity-report",
            "writingMethod": "direct_writing",
            "authorName": "{user_name}",
            "authorBio": "{user_title} {user_name}",
            "instructions": "{region} 주민 삶의 질을 높이겠습니다.",
            "newsContext": "",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {
                "mustIncludeFromStance": [
                    "#profile_bullet",
                    "{region} 주민 삶의 질을 높이겠습니다.",
                ]
            },
            "userProfile": {"name": "{user_name}", "status": "active"},
            "personalizationContext": "",
            "memoryContext": "",
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "bio",
            "userKeywords": ["{user_name}"],
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "paragraphs_per_section": 2,
                "per_section_min": 180,
                "per_section_max": 320,
            },
        }
    )

    assert "#profile_bullet" not in prompt
    assert "{region} 주민 삶의 질을 높이겠습니다." in prompt

# synthetic_fixture
def test_build_structure_prompt_guides_intro_as_three_paragraphs_by_default() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "{region} 현안과 정책 방향",
            "category": "activity-report",
            "writingMethod": "direct_writing",
            "authorName": "{user_name}",
            "authorBio": "{user_title} {user_name}",
            "instructions": "{region} 현안과 정책 방향을 설명합니다.",
            "newsContext": "",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "{user_name}", "status": "active"},
            "personalizationContext": "",
            "memoryContext": "",
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "bio",
            "userKeywords": ["{user_name}"],
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "paragraphs_per_section": 3,
                "per_section_min": 180,
                "per_section_max": 320,
            },
        }
    )

    assert '<intro paragraphs="3"' in prompt
    assert "서론은 반드시 3문단으로 쓰되" in prompt


# synthetic_fixture
def test_build_structure_prompt_adds_section_lane_rules_for_activity_report() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "{region} 정책 성과와 미래 과제",
            "category": "activity-report",
            "writingMethod": "direct_writing",
            "authorName": "{user_name}",
            "authorBio": "{user_title} {user_name}",
            "instructions": "{region} 주민 삶의 질을 높이기 위한 성과와 과제를 설명합니다.",
            "newsContext": "",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "{user_name}", "status": "active"},
            "personalizationContext": "",
            "memoryContext": "",
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "bio",
            "userKeywords": ["{user_name}"],
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "paragraphs_per_section": 3,
                "per_section_min": 180,
                "per_section_max": 320,
            },
        }
    )

    assert 'id="section_lane_achievement_only"' in prompt
    assert 'id="section_lane_future_only"' in prompt


def test_build_title_stance_summary_skips_hashtag_bullet_fragments() -> None:
    summary = _build_title_stance_summary(
        {
            "mustIncludeFromStance": [
                "#profile_bullet",
                "#role_bullet",
                "{region} 주민 삶의 질을 높이겠습니다.",
            ]
        },
        "#profile_bullet\n{region} 주민 삶의 질을 높이겠습니다.",
        full_name="{user_name}",
    )

    assert "#profile_bullet" not in summary
    assert "#role_bullet" not in summary
    assert "{region} 주민 삶의 질을 높이겠습니다." in summary


def test_style_generation_guard_includes_requested_static_forbidden_phrases() -> None:
    guard = _build_style_generation_guard()

    assert "오늘 이 자리에서" in guard
    assert "소홀히 하지 않았습니다" in guard
    assert "<phrase>소홀함이 없었습니다</phrase>" not in guard
    assert "<phrase>메커니즘을 완벽히 이해하고 있으며</phrase>" not in guard


def test_sanitize_auto_keywords_removes_fragments_and_name_particles() -> None:
    sanitized = _sanitize_auto_keywords(
        ["3월", "5일", "013명", "후보군", "대결에서도", "이틀동", "이재성도", "경남도", "주진우 부산시장"],
        user_keywords=["주진우 부산시장"],
    )

    assert sanitized == ["이재성", "경남도"]


def test_rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title() -> None:
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "주진우 의원과의 경쟁에서도 저는 준비돼 있습니다.",
        "주진우",
    )

    assert "주 의원과의 경쟁" in rewritten
    assert "주진우 의원" not in rewritten


def test_rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title_for_bare_name() -> None:
    policy = build_role_keyword_policy(
        ["주진우"],
        person_roles={"주진우": "국회의원"},
        source_texts=["주진우 의원은 부산시장 양자대결 조사에 포함됐다."],
    )
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "주진우를 비판하는 의견도 나옵니다.",
        "주진우",
        role_keyword_policy=policy,
    )

    assert rewritten == "주 의원을 비판하는 의견도 나옵니다."
    assert "상대 의원" not in rewritten
    assert "상대를 비판" not in rewritten


def test_rewrite_sentence_to_reduce_keyword_keeps_trailing_self_name_identity_sentence() -> None:
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "인천 계양구에서 당원과 시민을 위해 헌신해 온 문세종입니다.",
        "문세종",
    )

    assert rewritten == "인천 계양구에서 당원과 시민을 위해 헌신해 온 문세종입니다."
    assert "상대입니다" not in rewritten


def test_build_keyword_replacement_pool_avoids_opponent_fallback_for_bare_person_keyword() -> None:
    pool = _build_keyword_replacement_pool("문세종")

    assert pool == []


def test_rewrite_sentence_to_reduce_keyword_drops_first_person_competitor_comparison_clause() -> None:
    policy = build_role_keyword_policy(
        ["주진우"],
        person_roles={"주진우": "국회의원"},
        source_texts=["주진우 의원은 부산시장 양자대결 조사에 포함됐다."],
    )
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "주진우 의원과 비교했을 때, 저는 부산의 현안에 대한 더 깊은 이해와 해결책을 제시할 수 있습니다.",
        "주진우",
        role_keyword_policy=policy,
    )

    assert rewritten == "저는 부산의 현안에 대한 더 깊은 이해와 해결책을 제시할 수 있습니다."
    assert "주진우" not in rewritten


def test_rewrite_sentence_to_reduce_keyword_prefers_short_governor_title() -> None:
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "김동연 경기도지사의 해법도 다시 주목받고 있습니다.",
        "김동연",
    )

    assert "김 지사의 해법" in rewritten
    assert "김동연 경기도지사" not in rewritten


def test_rewrite_sentence_to_reduce_keyword_role_surface_keeps_full_name_first() -> None:
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "김동연 경기도지사가 해법을 제시했습니다.",
        "김동연 경기도지사",
    )

    assert "김동연 지사가 해법을 제시했습니다." in rewritten
    assert "김동연 경기도지사" not in rewritten


def test_role_keyword_policy_tracks_explicit_candidate_registration_per_person() -> None:
    policy = build_role_keyword_policy(
        ["나경원 서울시장", "이재성 부산시장"],
        person_roles={
            "나경원": "국회의원",
        },
        source_texts=[
            "서울시장 후보군으로 나경원 국회의원이 거론된다.",
            "부산시장 예비후보 이재성이 정책을 발표했다.",
        ],
    )
    reference_facts = policy.get("personReferenceFacts") or {}

    assert bool((reference_facts.get("나경원") or {}).get("candidateRegistered")) is False
    assert bool((reference_facts.get("이재성") or {}).get("candidateRegistered")) is True
    assert (reference_facts.get("이재성") or {}).get("explicitCandidateLabel") == "예비후보"


def test_rewrite_sentence_to_reduce_keyword_uses_source_role_without_candidate_promotion() -> None:
    policy = build_role_keyword_policy(
        ["나경원", "나경원 서울시장"],
        person_roles={"나경원": "국회의원"},
        source_texts=[
            "서울시장 후보군으로 나경원 국회의원이 거론된다.",
        ],
    )
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "나경원 국회의원의 해법도 다시 주목받고 있습니다.",
        "나경원",
        role_keyword_policy=policy,
    )

    assert "나 의원의 해법" in rewritten
    assert "나 후보" not in rewritten


def test_rewrite_sentence_to_reduce_keyword_allows_candidate_label_only_when_explicit() -> None:
    policy = build_role_keyword_policy(
        ["이재성"],
        source_texts=[
            "부산시장 예비후보 이재성이 정책을 발표했다.",
        ],
    )
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "이재성 예비후보의 정책도 다시 주목받고 있습니다.",
        "이재성",
        role_keyword_policy=policy,
    )

    assert "이 예비후보의 정책" in rewritten or "이 후보의 정책" in rewritten
    assert "이재성 예비후보" not in rewritten


def test_rewrite_sentence_to_reduce_conflicting_role_keyword_uses_source_role() -> None:
    policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원이 30.3%를 기록했다.",
        ],
    )
    rewritten = _rewrite_sentence_to_reduce_keyword(
        "주진우 부산시장이 다시 거론됩니다.",
        "주진우 부산시장",
        role_keyword_policy=policy,
    )

    assert "주진우 의원이 다시 거론됩니다." in rewritten
    assert "주진우 부산시장" not in rewritten


def test_reduce_excess_user_keyword_mentions_with_shadowed_keyword_still_hits_max() -> None:
    content = """
    <h2>주진우와 부산의 선택</h2>
    <p>온라인에서는 '주진우 부산시장' 검색어도 함께 거론되고 있습니다.</p>
    <p>주진우 의원과의 가상대결이 거론됩니다. 주진우 의원의 행보가 주목됩니다. 주진우 의원과의 경쟁도 이어집니다.</p>
    <p>부산 경제는 이재성입니다.</p>
    """
    user_keywords = ["주진우", "주진우 부산시장"]

    reduced = _reduce_excess_user_keyword_mentions(
        content,
        "주진우",
        user_keywords,
        target_max=1,
        shadowed_by=["주진우 부산시장"],
    )

    updated = str(reduced.get("content") or "")
    counts = _count_user_keyword_exact_non_overlap(updated, user_keywords)

    assert int(counts.get("주진우") or 0) <= 1
    assert "'주진우 부산시장' 검색어도 함께 거론되고 있습니다." in updated


def test_title_poll_fact_guard_repairs_margin_direction_phrase() -> None:
    fact_table = build_poll_matchup_fact_table(
        [
            "이재성 전 위원장과 주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
        ],
        known_names=["이재성", "주진우"],
    )
    repaired = enforce_poll_fact_consistency(
        "주진우 국회의원과 이재성, 부산시장 경쟁에서 왜 0.7% 밀렸을까",
        fact_table,
        full_name="이재성",
        field="title",
        allow_repair=True,
    )
    updated = str(repaired.get("text") or "")

    assert "1.4% 앞섰나" in updated
    assert repaired.get("edited") is True
    assert not list(repaired.get("blockingIssues") or [])


def test_title_poll_fact_guard_repairs_single_percent_binding_mismatch() -> None:
    fact_table = build_poll_matchup_fact_table(
        [
            "이재성 전 위원장과 주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
        ],
        known_names=["이재성", "주진우"],
    )
    repaired = enforce_poll_fact_consistency(
        "주진우 부산시장 출마? 이재성에게 왜 31.8%를 내줬나",
        fact_table,
        full_name="이재성",
        field="title",
        allow_repair=True,
    )
    updated = str(repaired.get("text") or "")

    assert "1.4% 앞섰나" in updated
    assert "31.8%" not in updated
    assert repaired.get("edited") is True
    assert not list(repaired.get("blockingIssues") or [])


def test_initial_title_length_discipline_marks_overlong_candidate_for_retry() -> None:
    title = "부산시장 경쟁에서 이재성이 앞으로 왜 앞서 나갈 수밖에 없는지를 길게 정리한 제목"
    assert len(title) > 35

    meta = _assess_initial_title_length_discipline(title)

    assert meta["status"] == "hard_violation"
    assert meta["requiresRetry"] is True
    assert int(meta["penalty"] or 0) >= 28


def test_generate_and_validate_title_retries_overlong_candidate_instead_of_fitting() -> None:
    long_title = "부산시장 경쟁에서 이재성이 앞으로 왜 앞서 나갈 수밖에 없는지를 길게 정리한 제목"
    short_title = "부산시장 경쟁, 이재성이 본 승부처"
    prompts: list[str] = []
    responses = iter([long_title, short_title])

    async def fake_generate_fn(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    result = asyncio.run(
        generate_and_validate_title(
            fake_generate_fn,
            {
                "topic": "부산시장 경쟁 판세",
                "contentPreview": (
                    "이재성은 부산시장 경쟁 판세에서 경제 회복과 변화 메시지로 시민 지지를 "
                    "넓히고 있으며, 부산의 미래 비전을 강조하고 있다."
                ),
                "userKeywords": [],
                "fullName": "이재성",
                "category": "current-affairs",
                "status": "campaign",
            },
            {
                "candidateCount": 1,
                "maxAttempts": 2,
                "minScore": 65,
            },
        )
    )

    assert result["title"] == short_title
    assert result["attempts"] == 2
    assert len(prompts) == 2


def test_generate_and_validate_title_repairs_direct_role_surface_before_scoring() -> None:
    role_keyword_policy = {
        "entries": {
            "주진우 부산시장": {
                "mode": "intent_only",
                "name": "주진우",
                "sourceRole": "국회의원",
            }
        }
    }

    async def fake_generate_fn(prompt: str) -> str:
        return "주진우 부산시장, 이재성 AI공약과 무엇이 다른가"

    result = asyncio.run(
        generate_and_validate_title(
            fake_generate_fn,
            {
                "topic": "부산시장 선거 양자대결에서 확인된 이재성의 경쟁력",
                "contentPreview": (
                    "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났고 "
                    "이재성 AI공약과 현장 40년 경험이 함께 부각됐다."
                ),
                "userKeywords": ["주진우 부산시장", "주진우"],
                "fullName": "이재성",
                "category": "current-affairs",
                "status": "campaign",
                "roleKeywordPolicy": role_keyword_policy,
            },
            {
                "candidateCount": 1,
                "maxAttempts": 1,
                "minScore": 1,
            },
        )
    )

    assert result["passed"] is True
    assert str(result.get("title") or "").startswith("주진우 부산시장 출마론,")
    assert "이재성 AI공약과 무엇이 다른가" in str(result.get("title") or "")


def test_order_role_keyword_intent_anchor_candidates_avoids_recent_variants() -> None:
    ordered = order_role_keyword_intent_anchor_candidates(
        "주진우 부산시장",
        [
            "주진우 부산시장 출마론, 이재성과 AI공약과 무엇이 다른가",
            "주진우 부산시장 거론, 이재성과의 정책 온도차는",
        ],
    )

    assert ordered[:3] == [
        "주진우 부산시장 출마 가능성",
        "주진우 부산시장 거론 속",
        "주진우 부산시장 구도",
    ]


def test_repair_title_for_missing_keywords_preserves_tail_with_intent_anchor() -> None:
    repaired = _repair_title_for_missing_keywords(
        "주진우 국회의원, 이재성 AI공약과 무엇이 다른가",
        {
            "missingType": "secondary_unique",
            "primaryKw": "주진우",
            "secondaryKw": "주진우 부산시장",
            "uniqueWords": ["부산시장"],
        },
        {
            "contentPreview": "이재성 AI공약과 현장 40년이 차별점으로 거론된다.",
            "userKeywords": ["주진우", "주진우 부산시장"],
            "keywords": ["이재성 AI공약"],
            "fullName": "이재성",
            "recentTitles": [
                "주진우 부산시장 출마론, 이재성과 AI공약과 무엇이 다른가",
                "주진우 부산시장 거론, 이재성과의 정책 온도차는",
            ],
        },
    )

    assert repaired == "주진우 부산시장 출마 가능성, 이재성 AI공약과 무엇이 다른가"


def test_repair_title_for_missing_keywords_replaces_generic_future_tail() -> None:
    repaired = _repair_title_for_missing_keywords(
        "주진우 국회의원, 이재성 도시의 미래",
        {
            "missingType": "secondary_unique",
            "primaryKw": "주진우",
            "secondaryKw": "주진우 부산시장",
            "uniqueWords": ["부산시장"],
        },
        {
            "contentPreview": "이재성 AI공약과 현장 40년이 차별점으로 거론된다.",
            "userKeywords": ["주진우", "주진우 부산시장"],
            "keywords": ["이재성 AI공약"],
            "fullName": "이재성",
        },
    )

    assert repaired is not None
    assert repaired.startswith("주진우 부산시장")
    assert "도시의 미래" not in repaired
    assert "AI공약" in repaired


def test_compute_similarity_penalty_penalizes_repeated_aggressive_question_frame() -> None:
    meta = _compute_similarity_penalty(
        "주진우 부산시장 출마? 왜 이재성에게 흔들리나",
        ["주진우 부산시장 출마? 왜 이재성이 약진했을까"],
        threshold=0.95,
        max_penalty=18,
    )

    assert int(meta.get("framePenalty") or 0) > 0
    assert int(meta.get("frameScore") or 0) >= 5
    assert str(meta.get("frameAgainst") or "") == "주진우 부산시장 출마? 왜 이재성이 약진했을까"


def test_validate_theme_and_content_uses_title_alignment_not_only_content_overlap() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    content = (
        "이재성은 부산시장 선거 양자대결에서 주진우보다 근소하게 앞서며 경쟁력을 보였다. "
        "부산 경제 비전과 변화 메시지가 시민들에게 설득력 있게 다가가고 있다."
    )

    weak = validate_theme_and_content(topic, content, "주진우 부산시장 왜 거론되나?")
    aggressive = validate_theme_and_content(topic, content, "주진우 부산시장 출마? 왜 이재성에게 흔들리나")
    strong = validate_theme_and_content(topic, content, "주진우와 양자대결, 이재성이 왜 앞섰나")

    assert int(weak["contentOverlapScore"] or 0) == 100
    assert int(weak.get("frameAlignmentScore") or 0) == 0
    assert int(aggressive.get("frameAlignmentScore") or 0) >= 70
    assert int(aggressive["effectiveTitleScore"] or 0) > int(weak["effectiveTitleScore"] or 0)
    assert int(weak["titleOverlapScore"] or 0) < int(strong["titleOverlapScore"] or 0)
    assert int(aggressive["effectiveTitleScore"] or 0) <= int(strong["effectiveTitleScore"] or 0)
    assert len(weak.get("titleMatchedKeywords") or []) < len(strong.get("titleMatchedKeywords") or [])
    assert all("제목에 주제 핵심어 부족" not in reason for reason in aggressive.get("mismatchReasons") or [])


def test_validate_theme_and_content_uses_surface_topic_fallback_for_sentence_like_topic() -> None:
    topic = "대통령님의 지역구를 지켜온 책임감으로, 계양구민에게 가장 충직한 인천광역시의원으로 역할을 해내겠습니다."
    content = (
        "인천 계양구에서 당원과 시민을 위해 뛰어온 인천광역시의원 문세종입니다. "
        "계양구을 지역위원회와 시의회 활동을 통해 지역구를 지켜왔고, 계양테크노밸리와 생활 조례 개정에도 힘써 왔습니다."
    )
    title = "문세종, 계양구민에게 가장 충직한 인천광역시의원"

    result = validate_theme_and_content(topic, content, title)

    assert int(result.get("titleOverlapScore") or 0) >= 50
    assert int(result.get("effectiveTitleScore") or 0) >= 65
    assert "인천광역시의원" in (result.get("titleMatchedKeywords") or [])


def test_validate_theme_and_content_penalizes_unsupported_reversal_frame() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    content = (
        "이재성은 부산시장 선거 양자대결에서 주진우보다 근소하게 앞서며 경쟁력을 보였다. "
        "부산 경제 비전과 변화 메시지가 시민들에게 설득력 있게 다가가고 있다."
    )

    aggressive = validate_theme_and_content(topic, content, "주진우 부산시장 출마? 왜 이재성에게 흔들리나")
    reversal = validate_theme_and_content(topic, content, "주진우 부산시장 출마? 90일 후 이재성이 뒤집나")

    assert int(reversal.get("effectiveTitleScore") or 0) < int(aggressive.get("effectiveTitleScore") or 0)
    assert any("역전 전제가 부족" in reason for reason in reversal.get("mismatchReasons") or [])


def test_validate_theme_and_content_penalizes_broken_numeric_subject_frame() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    content = (
        "이재성은 부산시장 선거 양자대결에서 주진우보다 근소하게 앞서며 경쟁력을 보였다. "
        "부산 경제 비전과 변화 메시지가 시민들에게 설득력 있게 다가가고 있다."
    )

    aggressive = validate_theme_and_content(topic, content, "주진우 부산시장 출마? 왜 이재성에게 흔들리나")
    broken = validate_theme_and_content(topic, content, "주진우 부산시장 출마? 왜 이재성에게 31.7%가 흔들렸나")

    assert int(broken.get("effectiveTitleScore") or 0) < int(aggressive.get("effectiveTitleScore") or 0)
    assert any("수치가 주어처럼" in reason for reason in broken.get("mismatchReasons") or [])


def test_validate_theme_and_content_penalizes_misbinding_poll_percent() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    content = (
        "이재성 전 위원장과 주진우 의원의 가상대결에서는 31.7% 대 30.3%로 나타났습니다. "
        "정당 지지율은 더불어민주당 31.8%, 국민의힘 25.4%, 지지정당 없음 35%였습니다."
    )

    broken = validate_theme_and_content(
        topic,
        content,
        "주진우 부산시장 출마? 이재성에게 왜 31.8%를 내줬나",
    )

    assert broken.get("isValid") is False
    assert int(broken.get("effectiveTitleScore") or 0) <= 40
    assert any("31.8%" in reason and "대결 수치" in reason for reason in broken.get("mismatchReasons") or [])


def test_validate_theme_and_content_penalizes_single_score_directional_title() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    content = (
        "이재성 전 위원장과 주진우 의원의 가상대결에서는 31.7% 대 30.3%로 나타났습니다. "
        "박형준 시장과의 양자대결에서는 30.9% 대 31.3%였습니다."
    )

    awkward = validate_theme_and_content(
        topic,
        content,
        "주진우 부산시장 출마? 이재성 31.7% 왜 앞섰나",
    )

    assert awkward.get("isValid") is False
    assert int(awkward.get("effectiveTitleScore") or 0) <= 45
    assert any("단일 득표율" in reason for reason in awkward.get("mismatchReasons") or [])


def test_guard_title_after_editor_rejects_aggressive_question_without_anchor_tail() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    try:
        _guard_title_after_editor(
            candidate_title="주진우 부산시장 출마? 왜 이재성에게 흔들리나",
            previous_title="이재성, 양자대결서 드러난 가능성",
            topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
            content=(
                "이재성은 부산시장 양자대결에서 주진우 의원보다 근소하게 앞서며 "
                "경쟁력과 가능성을 보여줬다."
            ),
            user_keywords=["주진우", "주진우 부산시장"],
            full_name="이재성",
            category="current-affairs",
            status="campaign",
            context_analysis={},
            role_keyword_policy=role_keyword_policy,
        )
    except ApiError as exc:
        assert "앞절 검색 앵커를 유지해야 합니다" in str(exc)
    else:
        raise AssertionError("검색 앵커 없는 공격형 경쟁자 intent 제목은 거부되어야 합니다.")


def test_guard_title_after_editor_falls_back_to_previous_topic_aligned_title() -> None:
    restored, info = _guard_title_after_editor(
        candidate_title="주진우 부산시장 왜 거론되나?",
        previous_title="주진우와 양자대결, 이재성이 왜 앞섰나",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        content=(
            "이재성은 부산시장 선거 양자대결에서 주진우보다 근소하게 앞서며 경쟁력을 보였다. "
            "부산 경제 비전과 변화 메시지가 시민들에게 설득력 있게 다가가고 있다."
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        category="일상 소통",
        status="campaign",
        context_analysis={},
    )

    assert restored.startswith("주진우 부산시장 출마론,")
    assert any(token in restored for token in ("왜 앞섰나", "경제 비전", "앞서는 이유"))
    assert info["source"] == "previous"


def test_guard_title_after_editor_accepts_direct_role_surface_candidate_when_anchor_is_kept() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    restored, info = _guard_title_after_editor(
        candidate_title="주진우 부산시장, 이재성 AI공약과 현장 40년",
        previous_title="",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        content=(
            "이재성은 부산시장 양자대결에서 주진우 의원보다 앞섰고 AI공약과 현장 40년 경험을 함께 강조했다."
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        category="current-affairs",
        status="campaign",
        context_analysis={},
        role_keyword_policy=role_keyword_policy,
    )

    assert restored.startswith("주진우 부산시장 출마론,")
    assert "이재성 AI공약과 현장 40년" in restored
    assert info["accepted"] is True
    assert info["repaired"] is True
    assert str(info["source"]).startswith("candidate")


def test_guard_draft_title_nonfatal_preserves_failed_candidate_without_fallback() -> None:
    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="부산 선거",
        previous_title="주진우와 양자대결서 드러난 이재성 가능성",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        content=(
            "이재성은 부산시장 선거 양자대결에서 경쟁력을 보였고 "
            "부산 경제와 변화 열망을 중심으로 가능성을 보여줬다."
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        category="일상 소통",
        status="campaign",
        context_analysis={},
    )

    assert restored
    assert restored == "부산 선거"
    assert info["accepted"] is True
    assert info["nonFatal"] is True
    assert info["phase"] == "draft_output"
    assert info["source"] == "candidate_failed_passthrough"
    assert info["validated"] is False


# synthetic_fixture
def test_guard_draft_title_nonfatal_repairs_mixed_duplicate_particles_in_title_surface() -> None:
    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="계양구의 밝은 미래를을 위한 약속과 비전",
        previous_title="",
        topic="계양구의 밝은 미래와 정책 방향",
        content="계양구의 미래와 정책 방향을 설명하는 의정활동 보고입니다.",
        user_keywords=["{user_name}"],
        full_name="{user_name}",
        category="activity-report",
        status="active",
        context_analysis={},
    )

    assert restored == "계양구의 밝은 미래를 위한 약속과 비전"
    assert info["accepted"] is True
    assert info["repaired"] is True


# synthetic_fixture
def test_guard_draft_title_nonfatal_repairs_third_person_possessive_title_surface() -> None:
    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="{user_name}, 그의 선택은?",
        previous_title="",
        topic="{region} 변화와 정책 방향",
        content="{region} 현안과 민생경제 해법을 설명하는 의정활동 보고입니다.",
        user_keywords=["{user_name}"],
        full_name="{user_name}",
        category="activity-report",
        status="active",
        context_analysis={},
    )

    assert restored
    assert "그의" not in restored
    assert "그녀의" not in restored
    assert "선택의 이유" in restored
    assert info["accepted"] is True
    assert info["repaired"] is True


def test_guard_draft_title_nonfatal_repairs_direct_role_surface_candidate_to_anchor_plus_argument() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났다.",
        ],
    )
    poll_fact_table = build_poll_matchup_fact_table(
        [
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났다.",
        ],
        known_names=["이재성", "주진우"],
    )

    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="주진우 부산시장, 이재성에게 왜 밀리고 있나?",
        previous_title="",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        content=(
            "이재성은 주진우 의원과의 가상대결에서 31.7% 대 30.3%를 기록하며 "
            "경쟁력과 가능성을 보여줬다."
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        category="current-affairs",
        status="campaign",
        context_analysis={},
        role_keyword_policy=role_keyword_policy,
        recent_titles=[
            "주진우 부산시장 출마? 왜 이재성에게 흔들리나",
            "주진우 부산시장 출마? 왜 이재성이 약진했을까",
        ],
        poll_fact_table=poll_fact_table,
    )

    assert restored
    assert restored.startswith("주진우 부산시장 출마론,")
    assert "31.7% 앞선 배경" in restored
    assert info["accepted"] is True
    assert info["nonFatal"] is True
    assert info["phase"] == "draft_output"
    assert info["source"] == "candidate"
    assert info["repaired"] is True


def test_guard_draft_title_nonfatal_does_not_return_blocked_candidate_title() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장", "주진우"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "최근 여론조사에서 주진우 의원과의 가상대결이 31.7% 대 30.3%로 나타났다.",
        ],
    )

    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="주진우 부산시장 출마론, 이재성과 가상대결서 드러난 접전",
        previous_title="",
        topic="부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        content="이재성 전 위원장과 주진우 의원의 가상대결은 31.7% 대 30.3%였다.",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        category="일상 소통",
        status="campaign",
        context_analysis={},
        role_keyword_policy=role_keyword_policy,
        recent_titles=[],
        poll_fact_table=build_poll_matchup_fact_table(
            ["이재성 전 위원장과 주진우 의원의 가상대결은 31.7% 대 30.3%였다."],
            known_names=["이재성", "주진우"],
        ),
    )

    assert restored != "주진우 부산시장 출마론, 이재성과 가상대결서 드러난 접전"
    assert restored.startswith("주진우 부산시장 출마론,")
    assert not any(token in restored for token in ("가상대결", "양자대결", "접전", "경쟁력"))
    assert info["source"] == "candidate"
    assert info["repaired"] is True


def test_guard_draft_title_nonfatal_avoids_raw_matchup_possessive_candidate() -> None:
    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="전재수, 이재성의 새로운 일자리",
        previous_title="",
        topic="전재수 의원과의 경선 확정 이후 부산 일자리 해법 경쟁",
        content="전재수와의 경선에서 부산 일자리와 경제 해법 경쟁이 본격화됐다.",
        user_keywords=["이재성", "전재수"],
        full_name="이재성",
        category="current-affairs",
        status="campaign",
        context_analysis={},
        poll_focus_bundle={
            "scope": "matchup",
            "speaker": "이재성",
            "focusNames": ["이재성", "전재수"],
            "titleNamePriority": ["이재성", "전재수"],
            "titleNameRepeatLimit": 1,
            "primaryPair": {
                "speaker": "이재성",
                "opponent": "전재수",
            },
            "allowedTitleLanes": [],
        },
    )

    assert restored
    assert restored != "전재수, 이재성의 새로운 일자리"
    assert "이재성의 새로운 일자리" not in restored
    assert info["source"] != "candidate_fallback"


def test_should_carry_recent_titles_from_prior_session_only_when_scope_matches() -> None:
    assert _should_carry_recent_titles_from_prior_session(
        {
            "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
            "category": "daily-communication",
            "recentTitles": ["주진우 부산시장 출마? 왜 이재성이 흔들리게 했나"],
        },
        topic="부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        category="daily-communication",
    ) is True

    assert _should_carry_recent_titles_from_prior_session(
        {
            "topic": "다른 주제",
            "category": "daily-communication",
            "recentTitles": ["주진우 부산시장 출마? 왜 이재성이 흔들리게 했나"],
        },
        topic="부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        category="daily-communication",
    ) is False


def test_update_recent_titles_keeps_latest_unique_titles() -> None:
    updated = _update_recent_titles(
        [
            "주진우 부산시장 출마론, 이재성과 AI공약과 무엇이 다른가",
            "주진우 부산시장 거론, 이재성과의 정책 온도차는",
        ],
        "주진우 부산시장 출마 가능성, 이재성이 내세우는 현장 40년",
        3,
    )

    assert updated == [
        "주진우 부산시장 출마 가능성, 이재성이 내세우는 현장 40년",
        "주진우 부산시장 출마론, 이재성과 AI공약과 무엇이 다른가",
        "주진우 부산시장 거론, 이재성과의 정책 온도차는",
    ]


def test_build_poll_focus_bundle_selects_primary_matchup_and_excludes_party_support() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
            "이재성 전 위원장과 박형준 현 부산시장의 양자대결은 30.9% 대 31.3%였습니다.",
            "정당 지지율은 더불어민주당 31.8%, 국민의힘 25.4%, 지지정당 없음 35%였습니다.",
        ],
    )

    assert bundle.get("scope") == "matchup"
    assert (bundle.get("primaryPair") or {}).get("opponent") == "주진우"
    assert "31.7% 대 30.3%" in str(bundle.get("focusedSourceText") or "")
    assert "정당 지지율" in str(bundle.get("focusedSourceText") or "")
    assert (bundle.get("primaryFactTemplate") or {}).get("sentence") == "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다."
    assert [item.get("id") for item in bundle.get("allowedTitleLanes") or []][:3] == [
        "intent_fact",
        "fact_direct",
        "contest_observation",
    ]
    h2_map = {item.get("id"): item for item in bundle.get("allowedH2Kinds") or []}
    assert h2_map["primary_matchup"]["template"] == "이재성이 주진우와의 가상대결에서 앞선 이유"
    assert h2_map["primary_matchup"]["answerLead"] == "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다."
    assert h2_map["primary_matchup"]["headingStyle"] == "declarative"
    assert h2_map["primary_matchup"]["firstSentenceRoles"] == ["matchup_fact"]
    assert "speaker_action" in h2_map["primary_matchup"]["experienceFollowupRoles"]
    assert h2_map["secondary_matchup"]["template"] == "박형준과의 접전에서 확인된 이재성 경쟁력"
    assert h2_map["policy"]["template"] == "부산 경제를 살릴 이재성의 해법"
    assert h2_map["policy"]["headingStyle"] == "declarative"
    assert "policy_detail" in h2_map["policy"]["experienceFollowupRoles"]
    assert "recognition" not in h2_map
    assert h2_map["closing"]["template"] == "지금 이재성에 주목해야 하는 이유"


def test_build_structure_prompt_includes_poll_focus_bundle_rules() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
            "이재성 전 위원장과 박형준 현 부산시장의 양자대결은 30.9% 대 31.3%였습니다.",
        ],
    )
    prompt = build_structure_prompt(
        {
            "topic": "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
            "category": "current-affairs",
            "writingMethod": "emotional_writing",
            "authorName": "이재성",
            "authorBio": "이재성 소개",
            "instructions": "이재성도 충분히 이깁니다.",
            "newsContext": str(bundle.get("focusedSourceText") or ""),
            "ragContext": "",
            "targetWordCount": 2000,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "이재성", "status": "campaign"},
            "personalizationContext": "",
            "memoryContext": "",
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["주진우 부산시장", "주진우"],
            "pollFocusBundle": bundle,
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1800,
                "max_chars": 2400,
                "per_section_min": 260,
                "per_section_max": 420,
                "per_section_recommended": 340,
            },
            "outputMode": "json",
        }
    )

    assert "<poll_focus_bundle" in prompt
    assert "A% 대 B%" in prompt
    assert "정당 지지율" in prompt
    assert "<allowed_h2_kinds>" in prompt
    assert "<answer_lead>" in prompt
    assert "<heading_style>declarative</heading_style>" in prompt
    assert "<first_sentence_roles>" in prompt
    assert "<allowed_sentence_roles>" in prompt
    assert "<body_writer_hint>" in prompt
    assert "타인 반응 해석형과 경험 → 역량 인증형은 어떤 자리에서도 허용 역할에 포함되지 않습니다." in prompt
    assert "경험 문장 다음에는 사실, 당시 행동, 구체 결과, 현재 해법 연결만 올 수 있습니다." in prompt
    assert "선언형 또는 명사형으로 요약합니다" in prompt
    assert "각 섹션은 첫 2문장을 먼저 완성한 뒤 H2를 작성합니다." in prompt


def test_build_structure_prompt_includes_style_generation_guard() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "부산 경제를 다시 세울 이재성의 가능성",
            "category": "current-affairs",
            "writingMethod": "emotional_writing",
            "authorName": "이재성",
            "authorBio": "이재성 소개",
            "instructions": "부산 경제는 이재성입니다.",
            "newsContext": "최근 여론조사 결과가 발표됐습니다.",
            "ragContext": "",
            "targetWordCount": 2000,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "이재성", "status": "campaign"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "직접적이고 자신감 있는 선언형으로 쓴다.",
            "styleFingerprint": {
                "analysisMetadata": {"confidence": 0.9},
                "aiAlternatives": {
                    "instead_of_더_나은_미래": "AI 3대 강국의 한 축",
                },
                "characteristicPhrases": {
                    "signatures": ["뼛속까지 부산사람"],
                    "avoidances": ["진정성"],
                },
                "toneProfile": {"directness": 0.8, "optimism": 0.7},
            },
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["주진우 부산시장", "주진우"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1800,
                "max_chars": 2400,
                "per_section_min": 260,
                "per_section_max": 420,
                "per_section_recommended": 340,
            },
            "outputMode": "json",
        }
    )

    assert "<style_generation_guard" in prompt
    assert "진정성" in prompt
    assert "획기적으로" in prompt
    assert "명실상부한" in prompt
    assert "주목할 만한" in prompt
    assert "혁신적이고 체계적인" in prompt
    assert "도모하" in prompt
    assert "기하겠" in prompt
    assert "제고하" in prompt
    assert "인사이트" in prompt
    assert "임팩트" in prompt
    assert "시너지" in prompt
    assert "라고 할 수 있습니다" in prompt
    assert "것은 사실입니다" in prompt
    assert "풍부한 경험을 바탕으로" in prompt
    assert "궁극적인 목표" in prompt
    assert "새로운 역사를 써 내려" in prompt
    assert "더 나은 미래" in prompt
    assert "더 나은 내일" in prompt
    assert "단순한 구호" in prompt
    assert "단순한 구호에 그치지 않고" in prompt
    assert "단순한 숫자" in prompt
    assert "단순한 X가 아니라" in prompt
    assert "단순히 X가 아닌" in prompt
    assert "단순한 X를 넘어" in prompt
    assert "단순히 X에 그치지 않고" in prompt
    assert "마음을 움직이고" in prompt
    assert "AI 3대 강국의 한 축" in prompt
    assert "자기 해설형 표현보다 단정형 선언" in prompt
    assert "<identity_signatures>" in prompt
    assert "도입·마감" in prompt
    assert "<forbidden_sentence_types>" in prompt
    assert "<sentence_type_examples>" not in prompt
    assert "경험·행동·정책 전망은 직접 서술할 수 있지만" in prompt
    assert "삶·경험·이력·경영 경력으로 자신의 정체성·역량을 증명하거나 보여준다고 결론내리지 말 것" in prompt
    assert "여론조사 수치나 결과를 쓴 뒤에는 그것이 시민의 주목·기대·열망을 뜻한다고 해석하지 말고" in prompt
    assert "의미 단정을 붙이지 말 것" in prompt
    assert "감탄형 해설이나 의미 단정을 붙이지 말 것" in prompt
    assert "부정-반전 프레임 자체를 쓰지 말 것" in prompt
    assert "명사를 바꿔도 같은 실패다" in prompt
    assert "더 나은 방향" in prompt
    assert "검증된 사실이 아닌 이상 기정사실로 쓰지 말 것" in prompt
    assert "믿음·추정형으로 완화해도 같은 금지다" in prompt
    assert "인지도 확장을 해설하지 말고" in prompt
    assert "인지도 자기서술을 반복하지 말고" in prompt
    assert "겸손 클리셰를 직설적 자신감 문장과 섞지 말 것" in prompt
    assert "경쟁자 이름을 기준점으로" in prompt
    assert "경쟁자 이름을 직접 비교 도입부로 쓰지 말 것." in prompt
    assert "타인의 판단을 대신 보고하지 말 것" in prompt
    assert "통찰력·전문성·실행력·자산을 제공했다" in prompt
    assert "자신의 비전 효과를 스스로 인증하지 말 것" in prompt
    assert "핵심 이력 나열은 원고당 한 번이면 충분하다." in prompt
    assert "동일 경력은 두 개 이상의 섹션에 반복하지 말 것." in prompt
    assert "긴 공약 목록은 본문에서 한 번만 펼치고" in prompt
    assert "등록된 시그니처가 있으면 정확형으로만 쓰고" in prompt
    assert "화자 이름 뒤에 비교 조사 도를 붙이지 말 것." in prompt
    assert "같은 의미를 다른 말로 반복하지 말 것" in prompt
    assert "같은 주제를 둘로 쪼개지 말고" in prompt
    assert "프로젝트 관리 보고서처럼" in prompt
    assert "같은 경력 나열은 원고 전체에서 한 번만 쓰고" in prompt
    assert "31.7% 대 30.3%" not in prompt
    assert "저 이재성의 가능성" not in prompt
    assert "단순한 숫자가 아니라" not in prompt
    assert "겸허히 받아들이며" not in prompt
    assert "강력한 열망을 보여주는 것입니다" not in prompt


def test_build_structure_prompt_excludes_user_specific_forbidden_phrases_without_custom_field() -> None:
    prompt = build_structure_prompt(
        {
            "instructions": "지역 경제를 살리겠습니다.",
            "newsContext": "최근 지역 현안이 논의되고 있습니다.",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "김민수", "status": "ready"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "직접적이고 간결한 선언형으로 쓴다.",
            "styleFingerprint": {
                "analysisMetadata": {"confidence": 0.9},
                "characteristicPhrases": {
                    "avoidances": ["진정성"],
                },
                "toneProfile": {"directness": 0.7, "optimism": 0.6},
            },
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["지역 현안"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1600,
                "max_chars": 2200,
                "per_section_min": 240,
                "per_section_max": 400,
                "per_section_recommended": 320,
            },
            "outputMode": "json",
        }
    )

    assert "통찰력을 길렀" not in prompt
    assert "통찰력과 실행력을 바탕으로" not in prompt
    assert "혁신적인 사고방식과 과감한 실행력" not in prompt
    assert "변화를 갈망하는 분명한 신호" not in prompt
    assert "시민 여러분의 기대를 반영" not in prompt
    assert "변화에 대한 강력한 열망을 보여줍니다" not in prompt
    assert "막내들" not in prompt


def test_build_structure_prompt_includes_user_specific_forbidden_phrases_from_profile_and_fingerprint() -> None:
    prompt = build_structure_prompt(
        {
            "instructions": "지역 경제를 살리겠습니다.",
            "newsContext": "최근 지역 현안이 논의되고 있습니다.",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {
                "name": "이재성",
                "status": "campaign",
                "forbidden_phrases": ["변화를 갈망하는 분명한 신호", "막내들"],
            },
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "직접적이고 간결한 선언형으로 쓴다.",
            "styleFingerprint": {
                "analysisMetadata": {"confidence": 0.9},
                "forbiddenPhrases": ["통찰력을 길렀", "시민 여러분의 기대를 반영"],
                "forbidden_phrases": ["통찰력과 실행력을 바탕으로", "변화에 대한 강력한 열망을 보여줍니다"],
                "toneProfile": {"directness": 0.7, "optimism": 0.6},
            },
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["지역 현안"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1600,
                "max_chars": 2200,
                "per_section_min": 240,
                "per_section_max": 400,
                "per_section_recommended": 320,
            },
            "outputMode": "json",
        }
    )

    assert "통찰력을 길렀" in prompt
    assert "통찰력과 실행력을 바탕으로" in prompt
    assert "변화를 갈망하는 분명한 신호" in prompt
    assert "시민 여러분의 기대를 반영" in prompt
    assert "변화에 대한 강력한 열망을 보여줍니다" in prompt
    assert "막내들" in prompt
    assert "<genre_contract name=\"정치인 블로그 글 기본 규칙\">" in prompt


def test_build_structure_prompt_keeps_examples_generic_across_users() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "지역 경제를 다시 세울 후보의 가능성",
            "category": "current-affairs",
            "writingMethod": "emotional_writing",
            "authorName": "김민수",
            "authorBio": "김민수 소개",
            "instructions": "지역 경제를 살리겠습니다.",
            "newsContext": "최근 여론조사 결과와 지역 현안이 함께 논의되고 있습니다.",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "김민수", "status": "ready"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "직접적이고 간결한 선언형으로 쓴다.",
            "styleFingerprint": {
                "analysisMetadata": {"confidence": 0.7},
                "toneProfile": {"directness": 0.6, "optimism": 0.6},
            },
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["지역 경제"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1600,
                "max_chars": 2200,
                "per_section_min": 240,
                "per_section_max": 400,
                "per_section_recommended": 320,
            },
            "outputMode": "json",
        }
    )

    assert "<sentence_type_examples>" not in prompt
    assert "같은 경력 나열은 원고 전체에서 한 번만 쓰고" in prompt
    assert "31.7% 대 30.3%" not in prompt
    assert "저 이재성의 가능성" not in prompt
    assert "이재성·주진우 의원 가상대결" not in prompt
    assert "단순한 숫자가 아니라" not in prompt
    assert "겸허히 받아들이며" not in prompt
    assert "정치인이 직접 쓰는 블로그 글이다" in prompt
    assert "경험과 사실을 말하고, 그 의미에 대한 최종 판단은 독자에게 맡길 것." in prompt


def test_structure_agent_heading_body_alignment_score_distinguishes_aligned_and_misaligned_sections() -> None:
    agent = StructureAgent(options={})

    aligned = agent._heading_body_alignment_score(
        "이재성이 주진우와의 가상대결에서 앞선 이유",
        [
            "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
            "저는 혁신기업 경영 현장에서 성과를 낸 경험으로 부산 경제 해법을 준비했습니다.",
        ],
    )
    misaligned = agent._heading_body_alignment_score(
        "이재성이 주진우와의 가상대결에서 앞선 이유",
        [
            "부산의 해양 관광과 문화 인프라를 어떻게 키울지 말씀드리겠습니다.",
            "북항 재개발과 관광 활성화 계획을 차례로 설명하겠습니다.",
        ],
    )

    assert aligned >= 0.24
    assert misaligned < 0.24


def test_structure_agent_conclusion_alignment_uses_full_paragraphs_for_closing_heading() -> None:
    agent = StructureAgent(options={})

    relaxed = agent._heading_body_alignment_score(
        "부산경제 대혁신, 반드시 이뤄내겠습니다!",
        [
            "시민과 함께 부산 경제를 다시 세우겠습니다.",
            "일자리와 산업 구조를 바꾸는 실행 계획을 끝까지 밀어붙이겠습니다.",
            "부산경제 대혁신, 반드시 이뤄내겠습니다.",
        ],
        use_all_paragraphs=True,
    )
    strict = agent._heading_body_alignment_score(
        "부산경제 대혁신, 반드시 이뤄내겠습니다!",
        [
            "시민과 함께 부산 경제를 다시 세우겠습니다.",
            "일자리와 산업 구조를 바꾸는 실행 계획을 끝까지 밀어붙이겠습니다.",
            "부산경제 대혁신, 반드시 이뤄내겠습니다.",
        ],
    )

    assert strict < 0.24
    assert relaxed >= 0.24


def test_shared_section_contract_blocks_experience_followed_by_self_certification() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    primary_contract = next(
        item for item in (bundle.get("allowedH2Kinds") or []) if item.get("id") == "primary_matchup"
    )

    violation = validate_section_contract(
        heading=primary_contract["template"],
        paragraphs=[
            primary_contract["answerLead"],
            (
                "저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. "
                "이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다."
            ),
        ],
        contract=primary_contract,
        speaker="이재성",
        opponent="주진우",
    )

    assert violation is not None
    assert violation.get("code") == "section_disallowed_role"

    age_asset_violation = validate_section_contract(
        heading=primary_contract["template"],
        paragraphs=[
            primary_contract["answerLead"],
            (
                "저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. "
                "33세라는 젊은 나이에 쌓은 경영 경험은 부산 경제를 풀 필수적인 자산입니다."
            ),
        ],
        contract=primary_contract,
        speaker="이재성",
        opponent="주진우",
    )

    assert age_asset_violation is not None
    assert age_asset_violation.get("code") == "section_disallowed_role"

    proven_capability_violation = validate_section_contract(
        heading=primary_contract["template"],
        paragraphs=[
            primary_contract["answerLead"],
            (
                "저는 산업 현장에서 결과를 만들며 일했습니다. "
                "이는 단순한 이론이나 추상적인 구상이 아닌, 실제 성과로 이미 증명된 저의 역량입니다."
            ),
        ],
        contract=primary_contract,
        speaker="이재성",
        opponent="주진우",
    )

    assert proven_capability_violation is not None
    assert proven_capability_violation.get("code") == "section_disallowed_role"


def test_shared_section_contract_excludes_audience_reaction_and_self_certification_anywhere_in_section() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    primary_contract = next(
        item for item in (bundle.get("allowedH2Kinds") or []) if item.get("id") == "primary_matchup"
    )

    assert "audience_reaction" not in (primary_contract.get("allowedSentenceRoles") or [])
    assert "self_certification" not in (primary_contract.get("allowedSentenceRoles") or [])

    audience_violation = validate_section_contract(
        heading=primary_contract["template"],
        paragraphs=[
            primary_contract["answerLead"],
            "시민 여러분께서는 저의 역량과 진정성을 알아봐 주셨습니다.",
        ],
        contract=primary_contract,
        speaker="이재성",
        opponent="주진우",
    )

    assert audience_violation is not None
    assert audience_violation.get("code") == "section_disallowed_role"
    assert audience_violation.get("role") == "audience_reaction"

    self_cert_violation = validate_section_contract(
        heading=primary_contract["template"],
        paragraphs=[
            primary_contract["answerLead"],
            "저의 비전이 부산의 새로운 도약을 이끌 것이라고 확신합니다.",
        ],
        contract=primary_contract,
        speaker="이재성",
        opponent="주진우",
    )

    assert self_cert_violation is not None
    assert self_cert_violation.get("code") == "section_disallowed_role"
    assert self_cert_violation.get("role") == "self_certification"


def test_shared_section_contract_classifies_showing_citizen_reaction_as_audience_reaction() -> None:
    sentence = "이러한 경험들이 부산 시민 여러분께 저의 진정성과 실력을 보여드리고 있습니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role == "audience_reaction"


def test_shared_section_contract_classifies_structural_audience_reaction_pattern() -> None:
    sentence = "저의 접근 방식이 시민 여러분의 지지로 이어진 것이라고 믿습니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role == "audience_reaction"


def test_shared_section_contract_classifies_citizen_subject_praise_result_as_audience_reaction() -> None:
    sentence = "부산 시민 여러분께서 저의 진심과 역량을 알아봐 주신 결과입니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role == "audience_reaction"


def test_shared_section_contract_classifies_citizen_subject_recognition_as_audience_reaction() -> None:
    sentence = "시민들이 이재성의 역량을 인정해 주셨습니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role == "audience_reaction"


def test_shared_section_contract_does_not_classify_speaker_commitment_as_audience_reaction() -> None:
    sentence = "저는 시민 여러분을 위해 최선을 다하겠습니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role != "audience_reaction"


def test_shared_section_contract_does_not_classify_civic_policy_process_as_audience_reaction() -> None:
    sentence = "시민 참여형 정책 수립 과정을 통해 해결하겠습니다."
    role = infer_sentence_role(sentence, speaker="이재성", opponent="주진우")

    assert role != "audience_reaction"


def test_shared_section_contract_classifies_dynamic_speaker_name_as_speaker_action() -> None:
    sentence = "민수는 현장을 직접 챙겼습니다."
    role = infer_sentence_role(sentence, speaker="민수", opponent="영희")

    assert role == "speaker_action"


def test_shared_section_contract_classifies_dynamic_speaker_name_as_audience_reaction() -> None:
    sentence = "민수는 부산에서 확실히 알려지고 있습니다."
    role = infer_sentence_role(sentence, speaker="민수", opponent="영희")

    assert role == "audience_reaction"


def test_shared_section_contract_split_sentences_preserves_decimal_poll_sentence() -> None:
    sentences = split_sentences(
        "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다. 다음 문장입니다."
    )

    assert sentences == [
        "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
        "다음 문장입니다.",
    ]


def test_shared_section_contract_blocks_duplicate_career_fact_across_sections() -> None:
    violation = validate_cross_section_contracts(
        sections=[
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
                    "저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다.",
                ],
            },
            {
                "heading": "지금 이재성에 주목해야 하는 이유",
                "paragraphs": [
                    "지금 이재성에 주목해야 하는 이유는 변화 요구가 함께 드러났기 때문입니다.",
                    "저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다.",
                ],
            },
        ],
        speaker="이재성",
        opponent="주진우",
    )

    assert violation is not None
    assert violation.get("code") == "duplicate_career_fact"
    assert violation.get("sectionIndex") == 2


# synthetic_fixture
def test_shared_section_contract_blocks_duplicate_political_career_fact_across_sections() -> None:
    violation = validate_cross_section_contracts(
        sections=[
            {
                "heading": "{region}를 위해 걸어온 길",
                "paragraphs": [
                    "정책보좌관, {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 역임하며 {region} 현안 해결에 앞장섰습니다.",
                ],
            },
            {
                "heading": "{user_name}의 지역 현안 이해",
                "paragraphs": [
                    "정책보좌관을 시작으로 {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 맡으며 {region} 발전에 힘썼습니다.",
                ],
            },
        ],
        speaker="{user_name}",
        opponent="",
    )

    assert violation is not None
    assert violation.get("code") == "duplicate_career_fact"
    assert violation.get("sectionIndex") == 2


# synthetic_fixture
def test_shared_section_contract_blocks_duplicate_policy_evidence_fact_across_sections() -> None:
    violation = validate_cross_section_contracts(
        sections=[
            {
                "heading": "{region} {policy_topic} 추진 방향과 실행 계획",
                "paragraphs": [
                    "지역화폐의 역할과 효과는 기준인물 시장께서 시장 재임 시절 이미 증명한 바 있습니다.",
                ],
            },
            {
                "heading": "{region} 민생 회복과 정책 실행 과제",
                "paragraphs": [
                    "저는 지역화폐의 역할과 효과가 기준인물 시장께서 시장 재임 시절 증명한 바와 같이 민생 회복에 도움이 된다고 봅니다.",
                ],
            },
        ],
        speaker="{user_name}",
        opponent="",
    )

    assert violation is not None
    assert violation.get("code") == "duplicate_policy_evidence_fact"
    assert violation.get("sectionIndex") == 2


def test_get_section_contract_sequence_keeps_single_closing_contract() -> None:
    bundle = {
        "scope": "matchup",
        "allowedH2Kinds": [
            {"id": "policy", "firstSentenceRoles": ["policy_answer"], "template": "정책", "answerLead": "정책 답"},
            {"id": "closing", "firstSentenceRoles": ["closing_commitment"], "template": "첫 결론", "answerLead": "첫 결론 문장"},
            {"id": "closing", "firstSentenceRoles": ["closing_commitment"], "template": "둘째 결론", "answerLead": "둘째 결론 문장"},
        ],
    }

    body_contracts, conclusion_contract = get_section_contract_sequence(bundle, body_sections=3)

    assert all(str(item.get("id") or "") != "closing" for item in body_contracts)
    assert conclusion_contract is not None
    assert conclusion_contract.get("template") == "첫 결론"


def test_structure_agent_build_html_soft_repairs_section_role_contract_violation() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "저는 부산 경제를 다시 세우겠습니다.",
                "최근 여론조사 결과가 나왔습니다.",
            ]
        },
        "body": [
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
                    (
                        "저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. "
                        "이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다."
                    ),
                ],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 살리겠습니다.",
            ],
        },
    }

    content, _ = agent._build_html_from_structure_json(
        payload,
        length_spec={
            "body_sections": 1,
            "paragraphs_per_section": 2,
        },
        topic="이재성의 가능성",
        poll_focus_bundle=bundle,
    )

    assert "전문성을 저에게 주었습니다" not in content
    assert "저는 33세에 CJ인터넷 이사" in content


def test_structure_agent_build_html_soft_repairs_multiple_section_role_contract_violations() -> None:
    bundle = {
        "scope": "matchup",
        "speaker": "이재성",
        "primaryPair": {"speaker": "이재성", "opponent": "주진우"},
        "allowedH2Kinds": [
            {
                "id": "primary_matchup",
                "template": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "answerLead": "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["matchup_fact"],
                "experienceFollowupRoles": [
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "allowedSentenceRoles": [
                    "matchup_fact",
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "첫 문장은 수치 사실로 시작합니다.",
                "minLeadOverlap": 0.0,
            },
            {
                "id": "closing",
                "template": "지금 이재성에 주목해야 하는 이유",
                "answerLead": "지금 이재성의 경쟁력은 확인됐습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
                "experienceFollowupRoles": [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "closing_commitment",
                    "concrete_result",
                ],
                "allowedSentenceRoles": [
                    "closing_commitment",
                    "policy_link",
                    "policy_answer",
                    "speaker_action",
                    "policy_detail",
                    "concrete_result",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "마지막은 짧게 마무리합니다.",
                "minLeadOverlap": 0.0,
            },
        ],
    }
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "저는 부산 경제를 다시 세우겠습니다.",
                "최근 여론조사 결과가 나왔습니다.",
            ]
        },
        "body": [
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                    "문장 하나. 문장 둘. 남는 문장입니다.",
                ],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 살리겠습니다.",
            ],
        },
    }

    with patch(
        "agents.core.structure_agent.validate_section_contract",
        side_effect=[
            {
                "code": "section_disallowed_role",
                "sentence": "문장 하나.",
                "message": "허용되지 않는 문장입니다.",
            },
            {
                "code": "section_disallowed_role",
                "sentence": "문장 둘.",
                "message": "허용되지 않는 문장입니다.",
            },
            None,
            None,
        ],
    ):
        content, _ = agent._build_html_from_structure_json(
            payload,
            length_spec={
                "body_sections": 1,
                "paragraphs_per_section": 2,
            },
            topic="이재성의 가능성",
            poll_focus_bundle=bundle,
        )

    assert "문장 하나." not in content
    assert "문장 둘." not in content
    assert "남는 문장입니다." in content


def test_structure_agent_build_html_cleans_intro_audience_reaction_sentences() -> None:
    bundle = {
        "scope": "matchup",
        "speaker": "이재성",
        "primaryPair": {"speaker": "이재성", "opponent": "주진우"},
        "allowedH2Kinds": [
            {
                "id": "primary_matchup",
                "template": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "answerLead": "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["matchup_fact"],
                "experienceFollowupRoles": [
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "allowedSentenceRoles": [
                    "matchup_fact",
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "첫 문장은 수치 사실로 시작합니다.",
                "minLeadOverlap": 0.0,
            },
            {
                "id": "closing",
                "template": "지금 이재성에 주목해야 하는 이유",
                "answerLead": "지금 이재성의 경쟁력은 확인됐습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
                "experienceFollowupRoles": [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "closing_commitment",
                    "concrete_result",
                ],
                "allowedSentenceRoles": [
                    "closing_commitment",
                    "policy_link",
                    "policy_answer",
                    "speaker_action",
                    "policy_detail",
                    "concrete_result",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "마지막은 짧게 마무리합니다.",
                "minLeadOverlap": 0.0,
            },
        ],
    }
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "제거할 문장입니다. 남길 문장입니다.",
                "다른 문단입니다.",
            ]
        },
        "body": [
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                    "저는 현장에서 문제를 확인하고 해법을 준비했습니다.",
                ],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 다시 세우겠습니다.",
            ],
        },
    }

    def _infer_role_for_intro_cleanup(sentence: str, **_: object) -> str:
        return "audience_reaction" if "제거할 문장입니다." in sentence else "other"

    with patch(
        "agents.core.structure_agent.infer_sentence_role",
        side_effect=_infer_role_for_intro_cleanup,
    ), patch("agents.core.structure_agent.validate_section_contract", return_value=None):
        content, _ = agent._build_html_from_structure_json(
            payload,
            length_spec={
                "body_sections": 1,
                "paragraphs_per_section": 2,
            },
            topic="이재성의 가능성",
            poll_focus_bundle=bundle,
        )

    assert "제거할 문장입니다." not in content
    assert "남길 문장입니다." in content
    assert "다른 문단입니다." in content


def test_structure_agent_build_html_precleans_section_wide_forbidden_before_first_sentence_mismatch() -> None:
    bundle = {
        "scope": "matchup",
        "speaker": "이재성",
        "primaryPair": {"speaker": "이재성", "opponent": "주진우"},
        "allowedH2Kinds": [
            {
                "id": "primary_matchup",
                "template": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "answerLead": "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["matchup_fact"],
                "experienceFollowupRoles": [
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "allowedSentenceRoles": [
                    "matchup_fact",
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "첫 문장은 수치 사실로 시작합니다.",
                "minLeadOverlap": 0.0,
            },
            {
                "id": "closing",
                "template": "지금 이재성에 주목해야 하는 이유",
                "answerLead": "지금 이재성의 경쟁력은 확인됐습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
                "experienceFollowupRoles": [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "closing_commitment",
                    "concrete_result",
                ],
                "allowedSentenceRoles": [
                    "closing_commitment",
                    "policy_link",
                    "policy_answer",
                    "speaker_action",
                    "policy_detail",
                    "concrete_result",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "마지막은 짧게 마무리합니다.",
                "minLeadOverlap": 0.0,
            },
        ],
    }
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "저는 부산 경제를 다시 세우겠습니다.",
                "최근 여론조사 결과가 나왔습니다.",
            ]
        },
        "body": [
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "저는 부산 경제를 다시 세우겠습니다.",
                    "부산 시민 여러분께서 저의 진심과 역량을 알아봐 주신 결과입니다.",
                ],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 다시 세우겠습니다.",
            ],
        },
    }

    content, _ = agent._build_html_from_structure_json(
        payload,
        length_spec={
            "body_sections": 1,
            "paragraphs_per_section": 2,
        },
        topic="이재성의 가능성",
        poll_focus_bundle=bundle,
    )

    assert "알아봐 주신 결과입니다" not in content
    assert "저는 부산 경제를 다시 세우겠습니다." in content


def test_structure_agent_build_html_filters_audience_reaction_when_contract_is_none() -> None:
    bundle = {
        "scope": "matchup",
        "speaker": "이재성",
        "primaryPair": {"speaker": "이재성", "opponent": "주진우"},
        "allowedH2Kinds": [
            {
                "id": "primary_matchup",
                "template": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "answerLead": "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["matchup_fact"],
                "experienceFollowupRoles": [
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "allowedSentenceRoles": [
                    "matchup_fact",
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "첫 문장은 수치 사실로 시작합니다.",
                "minLeadOverlap": 0.0,
            },
            {
                "id": "closing",
                "template": "지금 이재성에 주목해야 하는 이유",
                "answerLead": "지금 이재성의 경쟁력은 확인됐습니다.",
                "headingStyle": "declarative",
                "firstSentenceRoles": ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
                "experienceFollowupRoles": [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "closing_commitment",
                    "concrete_result",
                ],
                "allowedSentenceRoles": [
                    "closing_commitment",
                    "policy_link",
                    "policy_answer",
                    "speaker_action",
                    "policy_detail",
                    "concrete_result",
                ],
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": "마지막은 짧게 마무리합니다.",
                "minLeadOverlap": 0.0,
            },
        ],
    }
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "저는 부산 경제를 다시 세우겠습니다.",
                "최근 여론조사 결과가 나왔습니다.",
            ]
        },
        "body": [
            {
                "heading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 A% 대 B%로 나타났습니다.",
                    "저는 현장에서 문제를 확인하고 해법을 준비했습니다.",
                ],
            },
            {
                "heading": "추가 현장 기록과 판단",
                "paragraphs": [
                    "부산 시민 여러분께서 저의 진심과 역량을 알아봐 주신 결과입니다.",
                    "저는 현장에서 답을 찾겠습니다.",
                ],
            },
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 다시 세우겠습니다.",
            ],
        },
    }

    content, _ = agent._build_html_from_structure_json(
        payload,
        length_spec={
            "body_sections": 2,
            "paragraphs_per_section": 2,
        },
        topic="이재성의 가능성",
        poll_focus_bundle=bundle,
    )

    assert "알아봐 주신 결과입니다" not in content
    assert "저는 현장에서 답을 찾겠습니다." in content


def test_structure_agent_build_html_replaces_low_alignment_heading_with_contract_template() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    agent = StructureAgent(options={})
    payload = {
        "title": "이재성의 가능성",
        "intro": {
            "paragraphs": [
                "저는 부산 경제를 다시 일으키겠습니다.",
                "최근 여론조사 결과가 주목받고 있습니다.",
            ]
        },
        "body": [
            {
                "heading": "혁신과 실천으로 증명하는 이재성의 경쟁력",
                "paragraphs": [
                    "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
                    "저는 현장에서 문제를 확인하고 해법을 준비했습니다.",
                ],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "저는 부산 경제를 다시 일으키겠습니다.",
            ],
        },
    }

    content, _ = agent._build_html_from_structure_json(
        payload,
        length_spec={
            "body_sections": 1,
            "paragraphs_per_section": 2,
        },
        topic="이재성의 가능성",
        poll_focus_bundle=bundle,
    )

    assert "혁신과 실천으로 증명하는 이재성의 경쟁력" not in content
    assert "이재성이 주진우와의 가상대결에서 앞선 이유" in content

# synthetic_fixture
def test_structure_agent_build_html_merges_fragmented_intro_paragraphs() -> None:
    agent = StructureAgent(options={})
    payload = {
        "title": "{user_name}의 {issue_topic}",
        "intro": {
            "paragraphs": [
                "{user_title} {user_name}입니다.",
                "특히, {region} 현안과 주민들의 삶의 질 향상을 위해 더 치열하게 움직이겠습니다.",
                "앞으로도 저는 새로운 관점으로 {region}의 해법을 찾겠습니다.",
            ]
        },
        "body": [
            {
                "heading": "{region} 현안 해결 방향",
                "paragraphs": [
                    "{region}의 주요 현안을 다시 정리하고, 주민 불편을 줄이기 위한 대응 방안을 마련하겠습니다. 현장에서 확인한 문제를 빠르게 행정에 연결하겠습니다.",
                    "의정활동 과정에서 확인한 과제를 사업과 예산으로 연결해 실질적인 변화를 만들겠습니다. 주민이 체감하는 결과를 더 분명하게 보여드리겠습니다.",
                    "생활 밀착형 현안을 놓치지 않고 지역의 우선순위를 다시 세우겠습니다. 필요한 제도 개선과 예산 확보를 함께 추진하겠습니다.",
                ],
            }
        ],
        "conclusion": {
            "heading": "{region}의 더 나은 내일",
            "paragraphs": [
                "{region}의 더 나은 내일을 위해 지금 필요한 과제를 차분하게 풀어가겠습니다. 주민과의 약속을 실행으로 증명하겠습니다.",
                "현장의 목소리를 끝까지 듣고, 책임 있게 결과를 만들어내겠습니다. {region} 주민과 함께 다음 변화를 준비하겠습니다.",
                "주민이 체감하는 성과를 다시 확인할 수 있도록 마지막까지 챙기겠습니다. 더 나은 {region}를 위한 의정활동을 이어가겠습니다.",
            ],
        },
    }

    content, _ = agent._build_html_from_structure_json(
        payload,
        length_spec={
            "body_sections": 1,
            "paragraphs_per_section": 3,
        },
        topic="{region} 현안과 정책 방향",
    )

    intro_html = content.split("<h2>", 1)[0]

    assert intro_html.count("<p>") == 3
    assert "{user_title} {user_name}입니다." in intro_html
    assert "특히, {region} 현안과 주민들의 삶의 질 향상을 위해 더 치열하게 움직이겠습니다." in intro_html
    assert "앞으로도 저는 새로운 관점으로 {region}의 해법을 찾겠습니다." in intro_html


def test_content_validator_rejects_section_role_contract_violation() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    validator = ContentValidator()
    content = """
<p>저는 부산 경제를 다시 세우겠습니다.</p>
<p>최근 여론조사 결과가 나왔습니다.</p>
<p>부산 산업 전환의 핵심 쟁점과 해법을 차례로 말씀드리겠습니다.</p>
<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>
<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>
<p>저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. 이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다.</p>
<p>산업 전환의 방향은 현장 경험을 실행 계획으로 연결할 때 분명해집니다.</p>
<h2>지금 이재성에 주목해야 하는 이유</h2>
<p>지금 이재성의 경쟁력은 확인됐습니다.</p>
<p>저는 부산 경제를 살리겠습니다.</p>
<p>시민이 체감할 해법을 더 구체적으로 보여드리겠습니다.</p>
""".strip()

    validation = validator.validate(
        content,
        {
            "min_chars": 80,
            "max_chars": 2000,
            "expected_h2": 2,
            "per_section_recommended": 120,
            "per_section_min": 20,
            "per_section_max": 900,
            "total_sections": 3,
            "body_sections": 1,
        },
        poll_focus_bundle=bundle,
    )

    assert validation.get("passed") is False
    assert validation.get("code") == "SECTION_ROLE_CONTRACT"


def test_content_validator_rejects_duplicate_career_fact_across_sections() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    validator = ContentValidator()
    content = """
<p>저는 부산 경제를 다시 세우겠습니다.</p>
<p>최근 여론조사 결과가 나왔습니다.</p>
<p>부산 산업 전환의 핵심 쟁점과 해법을 차례로 말씀드리겠습니다.</p>
<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>
<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>
<p>저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다.</p>
<p>이 경험은 산업 정책을 설계하는 토대가 됐습니다.</p>
<h2>지금 이재성에 주목해야 하는 이유</h2>
<p>지금 이재성의 경쟁력은 확인됐습니다.</p>
<p>저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다.</p>
<p>시민이 체감할 변화는 실행력으로 입증하겠습니다.</p>
""".strip()

    validation = validator.validate(
        content,
        {
            "min_chars": 80,
            "max_chars": 2000,
            "expected_h2": 2,
            "per_section_recommended": 120,
            "per_section_min": 20,
            "per_section_max": 900,
            "total_sections": 3,
            "body_sections": 1,
        },
        poll_focus_bundle=bundle,
    )

    assert validation.get("passed") is False
    assert validation.get("code") == "SECTION_ROLE_CONTRACT"

# synthetic_fixture
def test_content_validator_rejects_fragmented_intro_paragraphs() -> None:
    validator = ContentValidator()
    content = """
<p>{user_title} {user_name}입니다.</p>
<p>특히, {region} 현안과 주민들의 삶의 질 향상에 집중하겠습니다.</p>
<p>앞으로도 저는 새로운 관점으로 {region}의 변화를 만들겠습니다.</p>
<h2>{region} 현안 해결 방향</h2>
<p>{region} 현안을 더 세밀하게 살피고 주민 불편을 줄이는 실질적 방안을 마련하겠습니다. 생활 현장에서 확인한 문제를 행정과 예산에 연결하겠습니다.</p>
<p>현장 의견을 꾸준히 수렴하고 우선순위를 분명히 정해 실행력을 높이겠습니다. 주민이 체감하는 개선 결과를 빠르게 보여드리겠습니다.</p>
<p>주민 설명과 집행 점검을 함께 챙겨 정책의 빈틈을 줄이겠습니다.</p>
<h2>{region}의 더 나은 내일</h2>
<p>{region}의 더 나은 내일을 위해 필요한 과제를 끝까지 책임 있게 챙기겠습니다. 주민과의 약속을 실행으로 증명하겠습니다.</p>
<p>지역의 문제를 끝까지 따라가며 해결책을 만들겠습니다. {region} 주민과 함께 다음 변화를 준비하겠습니다.</p>
<p>{region} 주민이 체감할 변화까지 연결되도록 마지막 과정도 놓치지 않겠습니다.</p>
""".strip()

    validation = validator.validate(
        content,
        {
            "min_chars": 80,
            "max_chars": 2000,
            "expected_h2": 2,
            "per_section_recommended": 120,
            "per_section_min": 20,
            "per_section_max": 900,
            "total_sections": 3,
            "body_sections": 1,
        },
    )

    assert validation.get("passed") is False
    assert validation.get("code") == "INTRO_FRAGMENTED"


# synthetic_fixture
def test_content_validator_rejects_orphan_intro_transition() -> None:
    validator = ContentValidator()
    content = """
<p>{user_name}입니다.</p>
<p>특히, {region} 현안 해결에 더 집중하겠습니다. 생활 불편을 줄이는 해법과 예산 우선순위를 더 분명히 말씀드리겠습니다.</p>
<p>{region} 주민이 체감할 변화까지 책임 있게 이어가겠습니다. 현장과 실행 점검도 함께 챙기겠습니다.</p>
<h2>{region} 현안 해결 방향</h2>
<p>{region} 현안을 더 세밀하게 살피고 주민 불편을 줄이는 실질적 방안을 마련하겠습니다. 생활 현장에서 확인한 문제를 행정과 예산에 연결하겠습니다.</p>
<p>현장 의견을 꾸준히 수렴하고 우선순위를 분명히 정해 실행력을 높이겠습니다. 주민이 체감하는 개선 결과를 빠르게 보여드리겠습니다.</p>
<p>주민 설명과 집행 점검을 함께 챙겨 정책의 빈틈을 줄이겠습니다.</p>
<h2>{region}의 더 나은 내일</h2>
<p>{region}의 더 나은 내일을 위해 필요한 과제를 끝까지 책임 있게 챙기겠습니다. 주민과의 약속을 실행으로 증명하겠습니다.</p>
<p>지역의 문제를 끝까지 따라가며 해결책을 만들겠습니다. {region} 주민과 함께 다음 변화를 준비하겠습니다.</p>
<p>{region} 주민이 체감할 변화까지 연결되도록 마지막 과정도 놓치지 않겠습니다.</p>
""".strip()

    validation = validator.validate(
        content,
        {
            "min_chars": 80,
            "max_chars": 2000,
            "expected_h2": 2,
            "per_section_recommended": 120,
            "per_section_min": 20,
            "per_section_max": 900,
            "total_sections": 3,
            "body_sections": 1,
        },
    )

    assert validation.get("passed") is False
    assert validation.get("code") == "INTRO_ORPHAN_TRANSITION"


# synthetic_fixture
def test_content_validator_rejects_section_topic_drift_for_activity_report() -> None:
    validator = ContentValidator()
    content = """
<p>{region}에서 주민과 함께한 {user_title} {user_name}입니다. 현장에서 확인한 문제를 정책과 예산에 연결해 왔습니다.</p>
<p>{issue_topic} 해결을 위해 지금까지의 성과와 앞으로의 과제를 차례로 말씀드리겠습니다. 무엇을 이미 해냈는지부터 분명히 짚겠습니다.</p>
<p>이미 만든 성과와 앞으로 풀 과제를 구분해 설명드리겠습니다. 주민이 체감한 변화와 남은 과제도 나눠 말씀드리겠습니다.</p>
<h2>{issue_topic} 입법 성과</h2>
<p>{issue_topic} 관련 조례를 발의하고 가결시키며 주민 불편을 줄였습니다. 현장에서 확인한 문제를 제도 개선으로 연결했습니다.</p>
<p>앞으로도 도시첨단산업단지 2단계 지정을 마무리하고 광역철도망 계획이 가시화될 수 있도록 힘쓰겠습니다.</p>
<p>조례 집행 점검과 후속 예산 확보도 함께 챙기며 성과를 이어가겠습니다.</p>
<h2>{region} 미래 비전</h2>
<p>{region}의 지속 가능한 발전을 위해 필요한 과제를 단계별로 추진하겠습니다. 주민이 체감하는 변화로 연결하겠습니다.</p>
<p>현장 의견을 반영해 실행 일정을 챙기고 필요한 기반을 마련하겠습니다.</p>
<p>추진 과정의 우선순위를 명확히 세워 실질적인 변화를 만들겠습니다.</p>
""".strip()

    validation = validator.validate(
        content,
        {
            "min_chars": 80,
            "max_chars": 2400,
            "expected_h2": 2,
            "per_section_recommended": 120,
            "per_section_min": 20,
            "per_section_max": 900,
            "total_sections": 3,
            "body_sections": 1,
        },
        category="activity-report",
    )

    assert validation.get("passed") is False
    assert validation.get("code") == "SECTION_TOPIC_DRIFT"


def test_build_retry_directive_raises_paragraph_floor_to_three_to_four() -> None:
    length_spec = {
        "total_sections": 5,
        "body_sections": 3,
        "min_chars": 2000,
        "max_chars": 2800,
        "per_section_recommended": 400,
        "expected_h2": 4,
    }

    total_directive = build_retry_directive({"code": "P_SHORT"}, length_spec)
    section_directive = build_retry_directive({"code": "SECTION_P_COUNT"}, length_spec)

    assert "3~4개씩" in total_directive
    assert "3~4개" in section_directive


def test_structure_agent_attempt_section_level_recovery_replaces_only_target_block() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    agent = StructureAgent(options={})

    async def _fake_recover_section_shortfall(**_: object) -> str:
        return (
            "<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>"
            "<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
            "<p>저는 현장에서 문제를 확인하고 해법을 준비했습니다.</p>"
        )

    agent.repairer.recover_section_shortfall = _fake_recover_section_shortfall  # type: ignore[method-assign]
    content = """
<p>저는 부산 경제를 다시 세우겠습니다.</p>
<p>최근 여론조사 결과가 나왔습니다.</p>
<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>
<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>
<p>저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. 이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다.</p>
<h2>지금 이재성에 주목해야 하는 이유</h2>
<p>지금 이재성의 경쟁력은 확인됐습니다.</p>
<p>저는 부산 경제를 살리겠습니다.</p>
""".strip()

    recovered = asyncio.run(
        agent._attempt_section_level_recovery(
            content=content,
            title="이재성의 가능성",
            topic="이재성의 가능성",
            length_spec={
                "body_sections": 1,
                "per_section_min": 20,
                "per_section_max": 900,
            },
            author_bio="이재성 소개",
            validation={
                "code": "SECTION_ROLE_CONTRACT",
                "reason": "본론 1 허용 문장 계약 위반",
                "feedback": "경험 문장 다음에는 사실·행동·구체 결과·해법 연결만 오도록 다시 작성하십시오.",
                "sectionIndex": 1,
                "sectionHeading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "violation": {
                    "sentence": "이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다.",
                },
            },
            poll_focus_bundle=bundle,
        )
    )

    assert recovered is not None
    updated_content, _, source = recovered
    assert source == "section-repair"
    assert "저는 현장에서 문제를 확인하고 해법을 준비했습니다." in updated_content
    assert "전문성을 저에게 주었습니다" not in updated_content
    assert "지금 이재성에 주목해야 하는 이유" in updated_content


def test_structure_agent_attempt_section_level_recovery_falls_back_to_degraded_block() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    agent = StructureAgent(options={})

    async def _none_recover_section_shortfall(**_: object) -> Optional[str]:
        return None

    agent.repairer.recover_section_shortfall = _none_recover_section_shortfall  # type: ignore[method-assign]
    content = """
<p>저는 부산 경제를 다시 세우겠습니다.</p>
<p>최근 여론조사 결과가 나왔습니다.</p>
<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>
<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>
<p>저는 33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로 활약했습니다. 이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다.</p>
<h2>지금 이재성에 주목해야 하는 이유</h2>
<p>지금 이재성의 경쟁력은 확인됐습니다.</p>
<p>저는 부산 경제를 살리겠습니다.</p>
""".strip()

    recovered = asyncio.run(
        agent._attempt_section_level_recovery(
            content=content,
            title="이재성의 가능성",
            topic="이재성의 가능성",
            length_spec={
                "body_sections": 1,
                "per_section_min": 20,
                "per_section_max": 900,
            },
            author_bio="이재성 소개",
            validation={
                "code": "SECTION_ROLE_CONTRACT",
                "reason": "본론 1 허용 문장 계약 위반",
                "feedback": "경험 문장 다음에는 사실·행동·구체 결과·해법 연결만 오도록 다시 작성하십시오.",
                "sectionIndex": 1,
                "sectionHeading": "이재성이 주진우와의 가상대결에서 앞선 이유",
                "violation": {
                    "sentence": "이러한 실질적인 경험은 산업 전환을 이끌 전문성을 저에게 주었습니다.",
                },
            },
            poll_focus_bundle=bundle,
        )
    )

    assert recovered is not None
    updated_content, _, source = recovered
    assert source == "section-degraded"
    assert "전문성을 저에게 주었습니다" not in updated_content
    assert "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다." in updated_content


def test_build_structure_prompt_prioritizes_style_role_examples() -> None:
    style_guide = """
1. 전환 패턴:
  - 실제 사용자 문장 예시: "[SELF_INTRODUCTION] 자기소개: 저는 부산항 부두 노동자의 2남 2녀 막내로 태어나 부산에서 초·중·고를 모두 다녔습니다.", "또한 부산 소년의집 초대 센터장 등 사회적 봉사 활동도 10년 이상 이어왔습니다."
  - 선언 뒤 연결: "또한", "그래서"
  - 실제 전개 예시: "부산을 AI 3대 강국의 한 축으로 세우겠습니다."
2. 구체화 패턴:
  - 실제 사용자 문장 예시: "33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다."
3. 리듬 패턴:
  - 단락/문장 마감: 했습니다., 있습니다., 됩니다.
5. 화자 포지셔닝 방식:
  - 실제 자기 선언 문장: "저는 AI 전문가, 성공한 기업인, 그리고 이재명 대통령이 직접 발탁한 민주당 영입인재 2호입니다."
6. 감정 표현 방식:
  - 실제 감정/선언 문장: "오늘 저는 시민 여러분께 분명한 부산 비전을 제시합니다.", "부산경제, 반드시 살려내겠습니다."
""".strip()

    prompt = build_structure_prompt(
        {
            "topic": "부산 경제를 다시 세울 이재성의 가능성",
            "category": "current-affairs",
            "writingMethod": "emotional_writing",
            "authorName": "이재성",
            "authorBio": "이재성 소개",
            "instructions": "부산 경제는 이재성입니다.",
            "newsContext": "최근 여론조사 결과가 발표됐습니다.",
            "ragContext": "",
            "targetWordCount": 2000,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "이재성", "status": "campaign"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": style_guide,
            "styleFingerprint": {
                "analysisMetadata": {"confidence": 0.9},
                "rhetoricalDevices": {
                    "examplePatterns": ["부산을 AI 3대 강국의 한 축으로 세우겠습니다."],
                },
                "toneProfile": {"directness": 0.8, "optimism": 0.7},
            },
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["주진우 부산시장", "주진우"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1800,
                "max_chars": 2400,
                "per_section_min": 260,
                "per_section_max": 420,
                "per_section_recommended": 340,
            },
            "outputMode": "json",
        }
    )

    assert "<style_role_guide" in prompt
    assert prompt.index("<style_role_guide") < prompt.index('<rule id="no_generic_political_boilerplate">')
    assert '<role name="narrative_to_policy">' in prompt
    assert "avoid_generic_second_sentence" in prompt
    role_block = prompt.split("<style_role_guide", 1)[1].split("</style_role_guide>", 1)[0]
    assert "[SELF_INTRODUCTION]" not in role_block
    assert "저는 부산항 부두 노동자의 2남 2녀 막내로 태어나 부산에서 초·중·고를 모두 다녔습니다." in prompt
    assert "부산을 AI 3대 강국의 한 축으로 세우겠습니다." in prompt


def test_build_style_role_priority_summary_uses_actual_examples() -> None:
    style_guide = """
1. 전환 패턴:
  - 실제 사용자 문장 예시: "[SELF_INTRODUCTION] 자기소개: 저는 부산항 부두 노동자의 2남 2녀 막내로 태어나 부산에서 초·중·고를 모두 다녔습니다.", "또한 부산 소년의집 초대 센터장 등 사회적 봉사 활동도 10년 이상 이어왔습니다."
  - 선언 뒤 연결: "또한", "그래서"
  - 실제 전개 예시: "부산을 AI 3대 강국의 한 축으로 세우겠습니다."
2. 구체화 패턴:
  - 실제 사용자 문장 예시: "33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다."
6. 감정 표현 방식:
  - 실제 감정/선언 문장: "오늘 저는 시민 여러분께 분명한 부산 비전을 제시합니다.", "부산경제, 반드시 살려내겠습니다."
""".strip()

    summary = build_style_role_priority_summary(
        style_guide,
        {
            "rhetoricalDevices": {
                "examplePatterns": ["부산을 AI 3대 강국의 한 축으로 세우겠습니다."],
            }
        },
    )

    assert summary.startswith("[style-role-priority]")
    assert "[SELF_INTRODUCTION]" not in summary
    assert '선언 뒤 연결: "저는 부산항 부두 노동자의 2남 2녀 막내로 태어나 부산에서 초·중·고를 모두 다녔습니다."' in summary
    assert '수치/증거->의미: 근거 "33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다."' in summary
    assert '문단 마감: "오늘 저는 시민 여러분께 분명한 부산 비전을 제시합니다."' in summary or '문단 마감: "부산경제, 반드시 살려내겠습니다."' in summary


def test_generate_style_hints_includes_transition_and_example_patterns() -> None:
    style_guide = generate_style_hints(
        {
            "analysisMetadata": {
                "confidence": 0.9,
                "dominantStyle": "비전 제시형",
                "uniqueFeatures": ["지역 경험에서 정책으로 바로 넘어감"],
            },
            "characteristicPhrases": {
                "transitions": ["여기서 멈추지 않겠습니다", "이제는 결과로 보여드리겠습니다"],
                "signatures": ["뼛속까지 부산사람"],
                "emphatics": ["반드시"],
                "conclusions": ["끝까지 책임지겠습니다"],
            },
            "sentencePatterns": {
                "avgLength": 42,
                "preferredStarters": ["저는", "이제"],
                "clauseComplexity": "medium",
                "endingPatterns": ["합니다", "겠습니다"],
            },
            "vocabularyProfile": {
                "frequentWords": ["부두", "골목", "월급봉투"],
                "preferredVerbs": ["지키다", "만들다"],
                "preferredAdjectives": ["단단한"],
                "technicalLevel": "accessible",
                "localTerms": ["부산항"],
            },
            "toneProfile": {
                "formality": 0.7,
                "emotionality": 0.4,
                "directness": 0.8,
                "optimism": 0.7,
                "toneDescription": "직접적이고 자신감 있는 선언형",
            },
            "rhetoricalDevices": {
                "usesRepetition": True,
                "usesEnumeration": False,
                "examplePatterns": [
                    "짧게 선언한 뒤 바로 현장 경험을 붙인다",
                    "문제 제기 뒤 즉시 해법을 제시한다",
                ],
            },
            "aiAlternatives": {
                "instead_of_더_나은_미래": "부산경제 대혁신",
            },
        }
    )

    assert "1. 전환 패턴" in style_guide
    assert "여기서 멈추지 않겠습니다" in style_guide
    assert "짧게 선언한 뒤 바로 현장 경험을 붙인다" in style_guide
    assert "2. 구체화 패턴" in style_guide
    assert "3. 리듬 패턴" in style_guide
    assert "4. 선호 어휘 클러스터" in style_guide
    assert "5. 화자 포지셔닝 방식" in style_guide
    assert "6. 감정 표현 방식" in style_guide


def test_build_title_prompt_includes_poll_focus_title_rules() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
            "정당 지지율은 더불어민주당 31.8%, 국민의힘 25.4%였습니다.",
        ],
    )
    prompt = build_title_prompt(
        {
            "topic": "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
            "contentPreview": "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였습니다.",
            "userKeywords": ["주진우 부산시장", "주진우"],
            "keywords": ["이재성", "주진우"],
            "fullName": "이재성",
            "category": "current-affairs",
            "status": "campaign",
            "titleScope": {},
            "backgroundText": "",
            "stanceText": "이재성도 충분히 이깁니다.",
            "contextAnalysis": {},
            "pollFocusBundle": bundle,
            "roleKeywordPolicy": build_role_keyword_policy(
                ["주진우 부산시장", "주진우"],
                person_roles={"주진우": "국회의원"},
                source_texts=["이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였습니다."],
            ),
            "titlePromptLite": True,
        }
    )

    assert "<poll_focus_title" in prompt
    assert "31.7% 대 30.3%" in prompt
    assert "<allowed_lanes>" in prompt
    assert "intent+fact" in prompt


def test_build_title_prompt_includes_competitor_intent_structure_rules() -> None:
    prompt = build_title_prompt(
        {
            "topic": "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
            "contentPreview": "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였고 이재성 AI공약이 부각됐다.",
            "userKeywords": ["주진우 부산시장", "주진우"],
            "keywords": ["이재성 AI공약"],
            "fullName": "이재성",
            "category": "current-affairs",
            "status": "campaign",
            "titleScope": {},
            "backgroundText": "",
            "stanceText": "이재성 AI공약과 현장 40년을 강조합니다.",
            "contextAnalysis": {},
            "roleKeywordPolicy": {
                "entries": {
                    "주진우 부산시장": {
                        "mode": "intent_only",
                        "name": "주진우",
                        "sourceRole": "국회의원",
                    }
                }
            },
            "recentTitles": ["주진우 부산시장 출마론, 이재성과 AI공약과 무엇이 다른가"],
            "titlePromptLite": True,
        }
    )

    assert "<competitor_intent_title" in prompt
    assert "[경쟁자 출마/거론 표현], [본문 핵심 논지]" in prompt
    assert "주진우 부산시장 거론" in prompt
    assert "AI공약" in prompt
    assert "인명을 쉼표로 나열하는 구조는 금지" in prompt
    assert "1인칭 표현을 넣지 않습니다" in prompt
    assert "<tail_selection_order>" in prompt
    assert "수치가 있으면 수치+해석을 우선합니다" in prompt
    assert "비전, 가능성, 가상대결, 접전, 경쟁력" in prompt


def test_validate_theme_and_content_rejects_reversal_lane_with_poll_focus_bundle() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성"
    content = "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였습니다."
    bundle = build_poll_focus_bundle(
        topic=topic,
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[content],
    )

    result = validate_theme_and_content(
        topic,
        content,
        "주진우 부산시장 출마? 왜 이재성에게 역전당했나?",
        params={"pollFocusBundle": bundle},
    )

    assert result["isValid"] is False
    assert any("poll focus" in reason or "역전" in reason for reason in result["mismatchReasons"])


def test_validate_theme_and_content_rejects_competitor_intent_cliche_tail() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성"
    content = "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였고 이재성 AI공약이 부각됐다."
    params = {
        "topic": topic,
        "contentPreview": content,
        "userKeywords": ["주진우 부산시장", "주진우"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "roleKeywordPolicy": {
            "entries": {
                "주진우 부산시장": {
                    "mode": "intent_only",
                    "name": "주진우",
                    "sourceRole": "국회의원",
                }
            }
        },
    }

    result = validate_theme_and_content(
        topic,
        content,
        "주진우 부산시장 출마론, 이재성과 가상대결서 드러난 접전",
        params=params,
    )

    assert result["isValid"] is False
    assert any("쉼표 뒤" in reason and "가상대결" in reason for reason in result["mismatchReasons"])


def test_validate_theme_and_content_rejects_competitor_intent_generic_future_tail() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성"
    content = "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였고 이재성 AI공약이 부각됐다."
    params = {
        "topic": topic,
        "contentPreview": content,
        "userKeywords": ["주진우 부산시장", "주진우"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "roleKeywordPolicy": {
            "entries": {
                "주진우 부산시장": {
                    "mode": "intent_only",
                    "name": "주진우",
                    "sourceRole": "국회의원",
                }
            }
        },
    }

    result = validate_theme_and_content(
        topic,
        content,
        "주진우 부산시장 출마 가능성, 이재성 도시의 미래",
        params=params,
    )

    assert result["isValid"] is False
    assert any("범용 문구" in reason or "도시의 미래" in reason for reason in result["mismatchReasons"])


def test_validate_theme_and_content_rejects_competitor_intent_name_list_structure() -> None:
    topic = "부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성"
    content = "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%였고 이재성 AI공약이 부각됐다."
    params = {
        "topic": topic,
        "contentPreview": content,
        "userKeywords": ["주진우 부산시장", "주진우"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "roleKeywordPolicy": {
            "entries": {
                "주진우 부산시장": {
                    "mode": "intent_only",
                    "name": "주진우",
                    "sourceRole": "국회의원",
                }
            }
        },
    }

    result = validate_theme_and_content(
        topic,
        content,
        "주진우, 이재성 변화와 혁신",
        params=params,
    )

    assert result["isValid"] is False
    assert any("인명을 쉼표로 나열" in reason or "앞절 검색 앵커" in reason for reason in result["mismatchReasons"])


def test_role_keyword_policy_uses_source_fact_per_person() -> None:
    policy = build_role_keyword_policy(
        ["주진우 부산시장", "나경원 서울시장", "조국 부산시장"],
        person_roles={
            "주진우": "국회의원",
            "나경원": "국회의원",
            "조국": "대표",
        },
        source_texts=[
            "부산시장 양자대결에서 주진우 의원은 30.3%를 기록했다.",
            "서울시장 선거 후보군으로 나경원 국회의원이 거론된다.",
            "조국 대표는 당 개혁 방향을 설명했다.",
        ],
    )
    entries = policy.get("entries") or {}

    assert (entries.get("주진우 부산시장") or {}).get("mode") == "intent_only"
    assert (entries.get("나경원 서울시장") or {}).get("mode") == "intent_only"
    assert (entries.get("조국 부산시장") or {}).get("mode") == "blocked"


def test_calculate_title_quality_score_blocks_direct_role_surface_but_allows_intent_surface() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    params = {
        "topic": "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        "contentPreview": (
            "이재성은 부산시장 양자대결에서 주진우 의원보다 근소하게 앞서며 "
            "경쟁력과 가능성을 보여줬다."
        ),
        "userKeywords": ["주진우", "주진우 부산시장"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
        "roleKeywordPolicy": role_keyword_policy,
    }

    invalid = calculate_title_quality_score("주진우 부산시장, 이재성에게 왜 밀리나?", params)
    cliche_tail = calculate_title_quality_score("주진우 부산시장 출마론, 이재성과 가상대결서 드러난 접전", params)
    valid = calculate_title_quality_score("주진우 부산시장 출마론, 이재성 AI공약과 무엇이 다른가", params)
    aggressive = calculate_title_quality_score("주진우 부산시장 출마? 왜 이재성에게 흔들리나", params)

    assert invalid["passed"] is False
    assert int(invalid["score"] or 0) == 0
    assert "출마" in str((invalid.get("suggestions") or [""])[0] or "")
    assert cliche_tail["passed"] is False
    assert any("쉼표 뒤" in suggestion for suggestion in cliche_tail.get("suggestions") or [])
    assert int(valid["score"] or 0) > 0
    assert aggressive["passed"] is False
    assert "앞절 검색 앵커" in " ".join(aggressive.get("suggestions") or [])
    repaired_aggressive = str(aggressive.get("repairedTitle") or "")
    assert (not repaired_aggressive) or repaired_aggressive.startswith("주진우 부산시장 출마론,")


def test_calculate_title_quality_score_repairs_competitor_name_list_to_anchor_plus_argument() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났고 이재성 AI공약이 부각됐다.",
        ],
    )
    params = {
        "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        "contentPreview": "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났고 이재성 AI공약이 부각됐다.",
        "userKeywords": ["주진우 부산시장", "주진우"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
        "roleKeywordPolicy": role_keyword_policy,
    }

    result = calculate_title_quality_score("주진우, 이재성 변화와 혁신", params)

    assert result["passed"] is False
    repaired = str(result.get("repairedTitle") or "")
    assert repaired.startswith("주진우 부산시장 출마론,")
    assert "," in repaired
    assert len(repaired) > len("주진우 부산시장 출마론,")


def test_calculate_title_quality_score_rejects_first_person_competitor_title_and_repairs_anchor() -> None:
    params = {
        "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        "contentPreview": "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났고 이재성 AI공약이 부각됐다.",
        "userKeywords": ["주진우", "주진우 부산시장"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
    }

    result = calculate_title_quality_score("주진우, 이재성 저의 정책", params)

    assert result["passed"] is False
    assert any("1인칭" in suggestion for suggestion in result.get("suggestions") or [])
    repaired = str(result.get("repairedTitle") or "")
    assert repaired.startswith("주진우 부산시장 출마론,")
    assert "저의" not in repaired
    assert any(token in repaired for token in ("31.7%", "AI공약", "앞선 배경"))


def test_calculate_title_quality_score_rejects_generic_vision_tail_for_competitor_intent() -> None:
    params = {
        "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        "contentPreview": "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났고 이재성 AI공약이 부각됐다.",
        "userKeywords": ["주진우", "주진우 부산시장"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
    }

    result = calculate_title_quality_score("주진우 부산시장 출마론, 이재성 부산 비전", params)

    assert result["passed"] is False
    assert any("비전" in suggestion for suggestion in result.get("suggestions") or [])
    repaired = str(result.get("repairedTitle") or "")
    assert repaired.startswith("주진우 부산시장 출마론,")
    assert "비전" not in repaired


def test_calculate_title_quality_score_inferrs_competitor_intent_from_role_keyword_without_policy() -> None:
    params = {
        "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        "contentPreview": "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났고 이재성 AI공약이 부각됐다.",
        "userKeywords": ["주진우", "주진우 부산시장"],
        "keywords": ["이재성 AI공약"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
    }

    result = calculate_title_quality_score("주진우, 이재성 변화와 혁신", params)

    assert result["passed"] is False
    repaired = str(result.get("repairedTitle") or "")
    assert repaired.startswith("주진우 부산시장 출마론,")
    assert any(token in repaired for token in ("31.7%", "AI공약", "앞선 배경"))


def test_blocked_role_keyword_is_not_required_in_title_gate_or_prompt() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["조국 대표", "조국 부산시장"],
        person_roles={"조국": "대표"},
        source_texts=[
            "조국 대표는 당 개혁 방향과 부산 현안에 대한 입장을 설명했다.",
        ],
    )
    params = {
        "topic": "조국 대표의 부산 현안 입장",
        "contentPreview": "조국 대표는 부산 현안에 대한 입장을 밝혔다.",
        "userKeywords": ["조국 대표", "조국 부산시장"],
        "keywords": [],
        "fullName": "조국",
        "category": "current-affairs",
        "status": "campaign",
        "roleKeywordPolicy": role_keyword_policy,
    }

    result = calculate_title_quality_score("부산 현안 답한 조국 대표, 개혁 구상은?", params)
    prompt = build_title_prompt(params)

    assert result["passed"] is False
    assert int(result["score"] or 0) == 0
    assert str(result.get("repairedTitle") or "").startswith("조국 부산시장 출마론,")
    assert 'priority="2" value="조국 부산시장"' not in prompt
    assert '두 검색어("조국 대표", "조국 부산시장")' not in prompt
    assert 'keyword="조국 부산시장" mode="blocked_intent_title"' in prompt
    assert "<competitor_intent_title" in prompt


def test_blocked_role_keyword_can_use_intent_anchor_in_title() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "이재성 전 위원장과 주진우 의원의 가상대결은 31.7% 대 30.3%로 나타났다.",
        ],
    )
    params = {
        "topic": "부산시장 선거 양자대결에서 확인된 이재성의 가능성",
        "contentPreview": "이재성 전 위원장과 주진우 의원의 가상대결은 31.7% 대 30.3%였고 부산 해법이 부각됐다.",
        "userKeywords": ["주진우 부산시장", "주진우"],
        "keywords": ["부산 해법"],
        "fullName": "이재성",
        "category": "current-affairs",
        "status": "campaign",
        "roleKeywordPolicy": role_keyword_policy,
    }

    result = calculate_title_quality_score("주진우 부산시장 출마론, 이재성 부산 해법은?", params)

    assert result["passed"] is True
    assert int(result["score"] or 0) >= 70


def test_ensure_user_keyword_in_subheading_once_skips_role_keyword_anchor() -> None:
    content = "<h2>이재성의 승리 가능성, 어떻게 보시나요?</h2><p>부산의 변화를 위해 뛰겠습니다.</p>"

    result = _ensure_user_keyword_in_subheading_once(
        content,
        ["주진우 부산시장"],
    )

    assert result["edited"] is False
    assert result["content"] == content


def test_repair_competitor_policy_phrase_once_removes_first_person_name_chain_residue() -> None:
    content = (
        "<p>부산 시민 여러분께 저의 진심과 주진우 의원 전재수 비전이 조금씩, "
        "그러나 확실하게 알려지고 있기 때문입니다.</p>"
    )

    repaired = _repair_competitor_policy_phrase_once(
        content,
        full_name="이재성",
        person_roles={"주진우": "국회의원", "전재수": "국회의원"},
    )
    updated = str(repaired.get("content") or "")

    assert "저의 비전이 조금씩" in updated
    assert "주진우 의원 전재수 비전" not in updated
    assert repaired.get("edited") is True


def test_scrub_matchup_residue() -> None:
    source = "저는 전재수 의원 경남도 후보군 주진우 의원 주진우 의원 비전을 더욱 명확히 전달하겠습니다."
    scrubbed = _scrub_suspicious_poll_residue_text(source)
    content = str(scrubbed.get("content") or "")

    assert "후보군" not in content
    assert "주진우 의원 주진우 의원 비전" not in content
    assert "비전" in content
    assert scrubbed.get("edited") is True


def test_poll_citation_detects_source_input_and_compacts() -> None:
    citation = build_poll_citation_text(
        "",
        "",
        """
        본문
        조사개요
        조사기관: 부산MBC 의뢰·한국사회여론연구소(KSOI)
        조사기간: 2026년 2월 20일~21일
        조사대상: 부산 부산에 거주하고 있는 만 18세 이상 남녀 유권자
        표본수: 1,001명
        조사방법: 무선 ARS 자동응답 방식
        표본오차: 95% 신뢰수준 ±3.1%p
        응답률: 5.9%
        기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조
        """,
    )

    expected = (
        "부산MBC 의뢰·한국사회여론연구소(KSOI) 조사("
        "2026년 2월 20일~21일, 부산 부산에 거주하고 있는 만 18세 이상 남녀 유권자, "
        "1001명, 무선 ARS 자동응답 방식, 95% 신뢰수준 ±3.1%p, 응답률 5.9%)\n"
        "기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조"
    )
    assert citation == expected


def test_poll_citation_compacts_narrative_source_and_ignores_weaker_summary() -> None:
    citation = build_poll_citation_text(
        """
        조사개요
        여야의 공천 작업이 속도를 내고 있는 가운데 저희 KNN이 부산시장과 경남도지사 선거 여론조사를 실시했습니다.
        표본오차는 각각 95% 신뢰수준에 최대허용 표본오차 ±3.1 포인트이며 응답률은 3.4%입니다.
        """,
        """
        이번 여론 조사는 KNN이 서던포스트에 의뢰해 지난 3일과 4일 이틀 동안 만 18세 이상 부산 시민 1,013명을 대상으로 실시되었습니다.
        표본오차는 각각 95% 신뢰수준에 최대허용 표본오차 ±3.1 포인트이며 응답률은 3.4%입니다.
        기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조
        KNN 주우진입니다.
        """,
    )

    expected = (
        "KNN 의뢰·서던포스트 조사(3일~4일, 만 18세 이상 부산 시민, 1013명, "
        "95% 신뢰수준 ±3.1%p, 응답률 3.4%)\n"
        "기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조"
    )
    assert citation == expected


def test_poll_citation_infers_year_month_from_article_timestamp() -> None:
    citation = build_poll_citation_text(
        """
        <KNN 여론조사> '전이박주' 각각 양자대결 결과는?
        Play Video
        주우진 입력 : 2026.03.05 17:33
        조회수 : 390

        <앵커>
        여야의 공천 작업이 속도를 내고 있는 가운데 저희 KNN이 부산시장과 경남도지사 선거 여론조사를 실시했습니다.

        <기자>
        이번 여론 조사는 KNN이 서던포스트에 의뢰해 지난 3일과 4일 이틀동안 만 18세 이상 부산시민 1,013명을 대상으로 실시했습니다.
        표본오차는 각각 95% 신뢰수준에 최대허용 표본오차 ±3.1 포인트이며 응답률은 3.4%입니다.
        KNN 주우진입니다.
        """,
    )

    expected = (
        "KNN 의뢰·서던포스트 조사(2026년 3월 3일~4일, 만 18세 이상 부산시민, "
        "1013명, 95% 신뢰수준 ±3.1%p, 응답률 3.4%)\n"
        "기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조"
    )
    assert citation == expected


def test_poll_citation_uses_plain_event_date_hint_without_header_label() -> None:
    citation = build_poll_citation_text(
        """
        이번 여론 조사는 KNN이 서던포스트에 의뢰해 지난 3일과 4일 이틀동안 만 18세 이상 부산시민 1,013명을 대상으로 실시했습니다.
        표본오차는 각각 95% 신뢰수준에 최대허용 표본오차 ±3.1 포인트이며 응답률은 3.4%입니다.
        """,
        "2026-03-05",
    )

    expected = (
        "KNN 의뢰·서던포스트 조사(2026년 3월 3일~4일, 만 18세 이상 부산시민, "
        "1013명, 95% 신뢰수준 ±3.1%p, 응답률 3.4%)\n"
        "기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조"
    )
    assert citation == expected


def test_poll_citation_drops_reporter_signoff() -> None:
    citation = build_poll_citation_text(
        """
        조사개요
        조사기관: KNN·서던포스트
        조사기간: 3월 3일~4일
        표본수: 부산 시민 1,013명
        KNN 주우진입니다.
        """
    )

    assert "KNN 주우진입니다." not in citation
    assert "중앙선거여론조사심의위원회 홈페이지 참조" in citation


def test_finalize_output_forces_poll_citation() -> None:
    content = "<p>부산 경제는 이재성입니다.</p>"
    result = finalize_output(
        content,
        poll_citation="""
        조사기관: 부산MBC 의뢰·한국사회여론연구소(KSOI)
        조사기간: 2026년 2월 20일~21일
        조사대상: 부산 부산에 거주하고 있는 만 18세 이상 남녀 유권자
        표본수: 1,001명
        조사방법: 무선 ARS 자동응답 방식
        표본오차: 95% 신뢰수준 ±3.1%p
        응답률: 5.9%
        """,
        embed_poll_citation=False,
    )
    updated = str(result.get("content") or "")
    meta = result.get("meta") or {}

    assert updated.count("<strong>조사개요</strong>") == 1
    assert "부산MBC 의뢰·한국사회여론연구소(KSOI) 조사(" in updated
    assert "중앙선거여론조사심의위원회 홈페이지 참조" in updated
    assert meta.get("pollCitationForced") is True


def test_finalize_output_reuses_embedded_poll_summary() -> None:
    content = """
    <p>부산 경제는 이재성입니다.</p>
    <p>조사개요<br>조사기관: 부산MBC 의뢰·한국사회여론연구소(KSOI)<br>조사기간: 2026년 2월 20일~21일<br>조사대상: 부산 부산에 거주하고 있는 만 18세 이상 남녀 유권자<br>표본수: 1,001명<br>조사방법: 무선 ARS 자동응답 방식<br>표본오차: 95% 신뢰수준 ±3.1%p<br>응답률: 5.9%</p>
    """
    result = finalize_output(
        content,
        poll_citation="",
        embed_poll_citation=False,
    )
    updated = str(result.get("content") or "")
    meta = result.get("meta") or {}

    assert updated.count("<strong>조사개요</strong>") == 1
    assert "부산MBC 의뢰·한국사회여론연구소(KSOI) 조사(" in updated
    assert "중앙선거여론조사심의위원회 홈페이지 참조" in updated
    assert meta.get("pollCitation")
    assert meta.get("pollCitationForced") is True


# synthetic_fixture
def test_finalize_output_can_defer_terminal_addons() -> None:
    content = "<p>{region} 민생 회복을 위해 뛰겠습니다.</p>"
    result = finalize_output(
        content,
        slogan="일하는 시의원",
        slogan_enabled=True,
        donation_info="후원계좌 : 신한 000-000",
        donation_enabled=True,
        poll_citation="조사기관: {organization}\n표본수: 1,000명",
        embed_poll_citation=True,
        append_terminal_addons=False,
    )
    updated = str(result.get("content") or "")
    meta = result.get("meta") or {}

    assert "후원계좌" not in updated
    assert "일하는 시의원" not in updated
    assert "<strong>조사개요</strong>" not in updated
    assert meta.get("pollCitation")
    assert meta.get("pollCitationForced") is True


# synthetic_fixture
def test_finalize_output_strips_keyword_reflection_meta_tail_and_repairs_duplicate_particles() -> None:
    content = """
    <p>{user_name}은 계양구민 삶의 질 향상을을 위해 끝까지 뛰겠습니다.</p>
    <h2>계양구의 밝은 미래를을 위한 약속과 비전</h2>
    <p>{user_name}은 약속이 아닌 실천으로 변화를 만들겠습니다.</p>
    카테고리: 논평, 진단 및 이슈 대응
    검색어 반영 횟수:
    "{user_name}": 6회
    생성 시간: 2026. 4. 2. 오후 8:12:30
    """

    result = finalize_output(content, embed_poll_citation=False)
    updated = str(result.get("content") or "")

    assert "카테고리:" not in updated
    assert "검색어 반영 횟수" not in updated
    assert "생성 시간:" not in updated
    assert '"{user_name}": 6회' not in updated
    assert "향상을을" not in updated
    assert "미래를을" not in updated
    assert "계양구민 삶의 질 향상을 위해" in updated
    assert "계양구의 밝은 미래를 위한 약속과 비전" in updated


# synthetic_fixture
def test_finalize_output_compresses_near_duplicate_event_sentences() -> None:
    content = """
    <p>불법 비상계엄과 탄핵 정국 속에서도 국회 결집과 거리 집회에 참여하며 민주주의와 당을 수호하는 데 최선을 다했습니다.</p>
    <p>특히 불법 비상계엄과 탄핵 정국이라는 엄중한 시기에도 저는 국회 결집과 거리 집회에 참여하며 민주주의와 당을 수호하는 데 앞장섰습니다.</p>
    <p>{region} 현안과 지역화폐 정책도 함께 추진하겠습니다.</p>
    """

    result = finalize_output(content, embed_poll_citation=False)
    updated = str(result.get("content") or "")

    assert updated.count("비상계엄") == 1
    assert "{region} 현안과 지역화폐 정책도 함께 추진하겠습니다." in updated


# synthetic_fixture
def test_finalize_output_does_not_reduce_final_section_below_three_paragraphs() -> None:
    content = """
    <p>{region} 현안은 더 미룰 수 없습니다.</p>
    <p>{organization}과 함께 실행 순서를 세우겠습니다.</p>
    <p>주민이 체감하는 변화를 만들겠습니다.</p>
    <h2>{region} 민생 회복 전략</h2>
    <p>{region} 소상공인 지원은 소비 흐름을 살리는 출발점입니다.</p>
    <p>{region} 소상공인 지원은 소비 흐름을 살리는 출발점입니다.</p>
    <p>예산과 현장 점검을 함께 묶어 실효성을 높이겠습니다.</p>
    """

    result = finalize_output(content, embed_poll_citation=False)
    updated = str(result.get("content") or "")
    final_section = updated.split("<h2>{region} 민생 회복 전략</h2>", 1)[-1]

    assert final_section.count("<p>") == 3
    assert final_section.count("소상공인 지원은 소비 흐름을 살리는 출발점입니다.") == 2


def test_enforce_keyword_requirements_keeps_speaker_name_without_generic_opponent_fallback() -> None:
    content = """
    <p>문세종은 계양구를 위해 뛰어왔습니다.</p>
    <p>문세종은 시민과 함께 현장을 지켜왔습니다.</p>
    <p>문세종은 조례 개정과 예산 확보에 힘써왔습니다.</p>
    <p>문세종은 앞으로도 책임 있게 일하겠습니다.</p>
    <p>문세종은 약속보다 실천으로 보여드리겠습니다.</p>
    <p>문세종은 계양구민 곁에서 끝까지 뛰겠습니다.</p>
    """
    overrides: dict[str, int] = {}
    _apply_speaker_name_keyword_max_override(["문세종"], "문세종", overrides)

    result = enforce_keyword_requirements(
        content,
        user_keywords=["문세종"],
        auto_keywords=[],
        target_word_count=1800,
        user_keyword_max_overrides=overrides,
    )
    updated = str(result.get("content") or "")

    assert updated == content
    assert "상대" not in updated
    assert overrides["문세종"] >= 999


def test_repair_self_reference_placeholders_once_restores_generic_opponent_placeholder_to_speaker_name() -> None:
    content = (
        "<p>인천 계양구에서 당원과 시민을 위해 헌신해 온 상대입니다.</p>"
        "<p>앞으로도 인천광역시의원 상대으로서 역할을 다하겠습니다.</p>"
    )

    repaired = _repair_self_reference_placeholders_once(content, full_name="문세종")
    updated = str(repaired.get("content") or "")

    assert repaired.get("edited") is True
    assert "상대입니다" not in updated
    assert "상대으로서" not in updated
    assert "문세종입니다" in updated
    assert "문세종으로서" in updated


def test_repair_competitor_policy_phrase_chain() -> None:
    content = "<p>선거까지 90일이라는 시간이 남아있지만, 저는 충분히 승리할 수 있다고 확신합니다. 부산 시민 여러분께 저의 진심과 주진우 의원 전재수 비전이 조금씩 알려지고 있기 때문입니다.</p>"
    repaired = _repair_competitor_policy_phrase_once(
        content,
        full_name="이재성",
        person_roles={
            "이재성": "전 부산시당위원장",
            "주진우": "국회의원",
            "전재수": "국회의원",
        },
    )
    updated = str(repaired.get("content") or "")

    assert "주진우 의원 전재수 비전" not in updated
    assert "비전이" in updated
    assert repaired.get("edited") is True


def test_final_sentence_polish_repairs_common_broken_phrases() -> None:
    content = """
    <h2>부산 경제, 제가 비전은?</h2>
    <p>상대 후보와의 가상대결에서 결과가 부산 시민 여러분의 변화에 대한 열망을 반영합니다.</p>
    """
    polished = _apply_final_sentence_polish_once(content)
    updated = str(polished.get("content") or "")
    actions = list(polished.get("actions") or [])

    assert "<h2>부산 경제, 제 비전은?</h2>" in updated
    assert "상대 후보와의 가상대결 결과는 부산 시민 여러분의 변화에 대한 열망을 반영합니다." in updated
    assert any("broken_heading_first_person_topic" in action for action in actions)
    assert any("broken_matchup_result_clause" in action for action in actions)


def test_collect_targeted_sentence_polish_candidates() -> None:
    content = """
    <h2>부산 경제, 제가 비전은?</h2>
    <p>상대 후보와의 가상대결에서 결과가 부산 시민 여러분의 변화에 대한 열망을 반영합니다.</p>
    """
    candidates = _collect_targeted_sentence_polish_candidates(content)

    assert any(
        candidate.get("tag") == "h2" and candidate.get("reason") == "heading_first_person_topic"
        for candidate in candidates
    )
    assert any(
        candidate.get("tag") == "p" and str(candidate.get("reason") or "").startswith("matchup_result_clause")
        for candidate in candidates
    )


def test_apply_targeted_sentence_rewrites() -> None:
    content = """
    <h2>부산 경제, 제가 비전은?</h2>
    <p>상대 후보와의 가상대결에서 결과가 부산 시민 여러분의 변화에 대한 열망을 반영합니다.</p>
    """
    candidates = _collect_targeted_sentence_polish_candidates(content)
    rewrite_map = {}
    for candidate in candidates:
        if candidate.get("tag") == "h2":
            rewrite_map[str(candidate.get("id") or "")] = "부산 경제, 제 비전은?"
        else:
            rewrite_map[str(candidate.get("id") or "")] = (
                "상대 후보와의 가상대결 결과는 부산 시민 여러분의 변화에 대한 열망을 반영합니다."
            )

    repaired = _apply_targeted_sentence_rewrites(
        content,
        candidates,
        rewrite_map,
        user_keywords=[],
        known_names=[],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>부산 경제, 제 비전은?</h2>" in updated
    assert "상대 후보와의 가상대결 결과는 부산 시민 여러분의 변화에 대한 열망을 반영합니다." in updated
    assert repaired.get("edited") is True


def test_collect_targeted_sentence_polish_candidates_marks_ai_alternative_overlay() -> None:
    content = "<p>더 나은 내일을 위해 나아가겠습니다.</p>"
    style_fingerprint = {
        "aiAlternatives": {"instead_of_더_나은_내일": "부산경제 대혁신"},
        "analysisMetadata": {"confidence": 0.9},
    }

    candidates = _collect_targeted_sentence_polish_candidates(
        content,
        style_instruction="enabled",
        style_polish_mode="light",
        style_fingerprint=style_fingerprint,
    )

    assert any(
        str(candidate.get("reason") or "") == "ai_alternative_voice_overlay"
        for candidate in candidates
    )


def test_apply_targeted_sentence_rewrites_applies_ai_alternative_rule_and_caps_style_count() -> None:
    sentence = "더 나은 내일을 위해 나아가겠습니다."
    content = (
        f"<p>{sentence}</p>\n"
        f"<p>{sentence}</p>\n"
        f"<p>{sentence}</p>\n"
        f"<p>{sentence}</p>"
    )
    style_fingerprint = {
        "aiAlternatives": {"instead_of_더_나은_내일": "부산경제 대혁신"},
        "analysisMetadata": {"confidence": 0.9},
    }
    candidates = []
    for block_index, match in enumerate(re.finditer(r"<p>(.*?)</p>", content, re.DOTALL)):
        inner = str(match.group(1) or "")
        candidates.append(
            {
                "id": f"p-{block_index}-s0",
                "tag": "p",
                "reason": "ai_alternative_voice_overlay",
                "hint": "",
                "priority": 90,
                "text": inner,
                "blockIndex": block_index,
                "sentenceIndex": 0,
                "blockKey": f"p-{block_index}",
                "blockInner": inner,
                "innerStart": match.start(1),
                "innerEnd": match.end(1),
                "styleRulePairs": [{"source": "더 나은 내일", "target": "부산경제 대혁신"}],
            }
        )

    repaired = _apply_targeted_sentence_rewrites(
        content,
        candidates,
        {},
        user_keywords=[],
        known_names=[],
        style_fingerprint=style_fingerprint,
        style_polish_mode="light",
    )
    updated = str(repaired.get("content") or "")
    actions = repaired.get("actions") or []

    assert updated.count("부산경제 대혁신을 위해 나아가겠습니다.") == 4
    assert updated.count("더 나은 내일을 위해 나아가겠습니다.") == 0
    assert any(str(action).startswith("targeted_sentence_rule_apply:") for action in actions)
    assert not any(str(action).startswith("targeted_sentence_style_skip_cap:") for action in actions)


def test_apply_global_style_ai_alternative_rules_once_rewrites_all_blocks() -> None:
    content = (
        "<h2>부산의 더 나은 미래</h2>"
        "<p>더 나은 미래를 시민 여러분과 함께 열겠습니다.</p>"
        "<p>더 나은 내일을 위해 나아가겠습니다.</p>"
    )
    result = _apply_global_style_ai_alternative_rules_once(
        content,
        {
            "aiAlternatives": {
                "instead_of_더_나은_미래": "AI 3대 강국의 한 축",
            }
        },
    )
    updated = str(result.get("content") or "")

    assert "더 나은 미래" not in updated
    assert "더 나은 내일" not in updated
    assert updated.count("AI 3대 강국의 한 축") == 3
    assert result.get("edited") is True


def test_collect_targeted_sentence_polish_candidates_preserves_jeonim_overlay_slot() -> None:
    noisy_h2 = "".join(
        f"<h2>저는 비전은?</h2><p>본문 설명 {idx}입니다.</p>"
        for idx in range(8)
    )
    content = (
        noisy_h2
        + "<p>도입 문장입니다.</p>"
        + "<p>저는 시민 곁에 있었습니다. 그 시간을 잊지 않습니다. "
        + "저는 현장의 무게를 압니다. 그 목소리를 기억합니다. 저는 그 책임을 압니다.</p>"
        + "<p>또 다른 설명입니다.</p>"
        + "<p>마무리 설명입니다.</p>"
    )

    candidates = _collect_targeted_sentence_polish_candidates(
        content,
        style_instruction="on",
        style_polish_mode="light",
        style_fingerprint={"analysisMetadata": {"confidence": 0.9}},
    )

    reasons = [str(candidate.get("reason") or "") for candidate in candidates]
    assert "jeonim_voice_overlay" in reasons


def test_collect_targeted_sentence_polish_candidates_detects_beyond_boilerplate_pattern() -> None:
    assert _contains_targeted_beyond_boilerplate(
        "이는 단순히 숫자를 넘어, 부산 시민들의 변화 요구를 보여줍니다."
    )


def test_repair_subheading_entity_consistency_prefers_speaker_over_low_signal_noise() -> None:
    content = """
    <h2>전재수, 부산의 미래를 말하다</h2>
    <p>온라인에서는 '주진우 부산시장' 검색어도 함께 거론되고 있습니다.</p>
    <p>주진우 의원과의 양자대결도 거론되지만, 저는 부산 경제를 다시 세울 실천안을 말씀드리겠습니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "전재수", "주진우"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>이재성, 부산의 미래를 말하다</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_third_personizes_first_person_heading() -> None:
    content = """
    <h2>부산 경제, 제 비전은?</h2>
    <p>저는 부산 경제를 다시 세울 실천안을 말씀드리겠습니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>부산 경제, 이재성의 비전은?</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_repairs_possessive_heading_after_third_personization() -> None:
    content = """
    <h2>부산 경제, 제가 혁신 방향은?</h2>
    <p>저는 부산 경제를 다시 세울 실천안을 말씀드리겠습니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>부산 경제, 이재성의 혁신 방향은?</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_repairs_malformed_matchup_heading() -> None:
    content = """
    <h2>박형준 현 이재성의 양자대결, 오차 범위</h2>
    <p>이재성 더불어민주당 전 부산시당위원장과 박형준 현 부산시장의 양자대결에서는 30.9% 대 31.3%로 접전이 이어졌습니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "박형준"],
        preferred_names=["이재성"],
        role_facts={"박형준": "부산시장"},
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>박형준 시장과의 양자대결, 오차 범위</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_repairs_speaker_role_mismatch_matchup_heading() -> None:
    content = """
    <h2>이재성 시장과의 양자대결, 오차 범위</h2>
    <p>이재성 더불어민주당 전 부산시당위원장과 박형준 현 부산시장의 양자대결에서는 30.9% 대 31.3%로 접전이 이어졌습니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "박형준"],
        preferred_names=["이재성"],
        role_facts={"박형준": "부산시장", "이재성": "예비후보"},
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>박형준 시장과의 양자대결, 오차 범위</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_dedupes_duplicate_heading_token() -> None:
    content = """
    <h2>민주당 민주당, 혁신과 정치적 무게감의 대결 구도</h2>
    <p>이번 경선은 혁신성과 정치 경험이 어떤 차이를 만드는지 비교하게 합니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "전재수"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>민주당, 혁신과 정치적 무게감의 대결 구도</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_dedupes_prefixed_duplicate_heading_token() -> None:
    content = """
    <h2>부산 민주당 민주당, 컨벤션 효과 극대화 전략</h2>
    <p>민주당 경선은 부산 유권자에게 선택지를 제공합니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "전재수"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>부산 민주당, 컨벤션 효과 극대화 전략</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_subheading_entity_consistency_drops_low_signal_matchup_prefix() -> None:
    content = """
    <h2>상대 후보, 혁신성과 정치적 무게감의 양자 대결 구도</h2>
    <p>이번 경선은 두 후보의 경험과 정책 역량을 비교하는 과정입니다.</p>
    """
    repaired = _repair_subheading_entity_consistency_once(
        content,
        ["이재성", "전재수"],
        preferred_names=["이재성"],
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>혁신성과 정치적 무게감의 양자 대결 구도</h2>" in updated
    assert repaired.get("edited") is True


def test_repair_generic_subheading_surface_text_keeps_existing_object_particle() -> None:
    heading = "계양테크노밸리 성공적 완성을 위한 노력과 과제"

    repaired, replacements = _repair_generic_subheading_surface_text(heading)

    assert repaired == heading
    assert replacements == []


def test_repair_generic_subheading_surface_text_repairs_missing_object_particle() -> None:
    heading = "계양테크노밸리 성공적 완성 위한 노력과 과제"

    repaired, replacements = _repair_generic_subheading_surface_text(heading)

    assert repaired == "계양테크노밸리 성공적 완성을 위한 노력과 과제"
    assert any(
        str(replacement.get("type") or "") == "heading_missing_object_particle"
        for replacement in replacements
    )


def test_detect_integrity_gate_issues_allows_valid_matchup_heading_and_sentence() -> None:
    content = (
        "<h2>박형준 시장과의 양자대결, 오차 범위</h2>"
        "<p>이재성 더불어민주당 전 부산시당위원장과 박형준 현 부산시장의 양자대결에서는 "
        "30.9% 대 31.3%로 접전이 이어졌습니다.</p>"
    )
    issues = _detect_integrity_gate_issues(content)

    assert "문장 파손(인명 결합 소제목/문장)" not in issues
    assert "문장 파손(화자-직함 혼합 대결 소제목/문장)" not in issues


def test_repair_intent_only_role_keyword_mentions_rewrites_safe_body_sentence() -> None:
    content = """
    <p>정가에서는 주진우 부산시장이 다시 거론됩니다.</p>
    <p>부산 경제를 살릴 대안을 설명드리겠습니다.</p>
    """
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    repaired = _repair_intent_only_role_keyword_mentions_once(
        content,
        role_keyword_policy=role_keyword_policy,
    )
    updated = str(repaired.get("content") or "")

    assert "주진우 부산시장 출마론이 다시 거론됩니다." in updated
    assert repaired.get("edited") is True


def test_repair_intent_only_role_keyword_mentions_restores_matchup_fact_role() -> None:
    content = "<p>주진우 부산시장 후보와의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    repaired = _repair_intent_only_role_keyword_mentions_once(
        content,
        role_keyword_policy=role_keyword_policy,
    )
    updated = str(repaired.get("content") or "")

    assert repaired.get("edited") is True
    assert "주진우 의원과의 가상대결" in updated
    assert "주진우 부산시장 후보와의 가상대결" not in updated


def test_inject_keyword_into_section_does_not_use_reference_template_by_default() -> None:
    section = "<p>부산 경제를 살리기 위한 실천 방안을 말씀드리겠습니다.</p>"
    updated, edited, sentence = _inject_keyword_into_section(
        section,
        "주진우 부산시장",
        "body",
        0,
    )

    assert updated == section
    assert edited is False
    assert sentence == ""


def test_force_insert_insufficient_keywords_limits_reference_sentence_to_primary_role_keyword() -> None:
    content = "<p>부산 경제를 살리기 위한 실천 방안을 말씀드리겠습니다.</p>"
    keyword_validation = {
        "주진우 부산시장": {"status": "insufficient", "expected": 1},
        "전재수 국회의원": {"status": "insufficient", "expected": 1},
    }
    updated = force_insert_insufficient_keywords(
        content,
        ["주진우 부산시장", "전재수 국회의원"],
        keyword_validation,
    )

    assert updated == content
    assert "전재수 국회의원" not in updated


def test_role_keyword_reference_sentence_guard_blocks_meta_surface_and_duplicate_georon() -> None:
    assert _should_block_role_keyword_reference_sentence(
        "온라인에서는 '주진우 부산시장' 검색어도 함께 거론되고 있습니다.",
        context_html="",
        keyword="주진우 부산시장",
    )
    assert _should_block_role_keyword_reference_sentence(
        "이 흐름 속에서 주진우 부산시장 후보론도 함께 거론됩니다.",
        context_html="<p>정가에서는 주진우 의원 전략공천설이 다시 거론됩니다.</p>",
        keyword="주진우 부산시장",
    )
    assert _should_block_role_keyword_reference_sentence(
        "온라인에서는 주진우 의원 출마 가능성도 함께 언급됩니다.",
        context_html="<p>부산 경제를 살릴 실천 방안을 설명합니다.</p>",
        keyword="주진우 의원",
    )


def test_inject_keyword_into_section_skips_broken_poll_residue_paragraph() -> None:
    section = (
        "<h2>?댁옱???몄? ??μ긽, ?쒕???湲곕?'</h2>"
        "<p>?щ줎議곗궗?먯꽌 ?댁옱?깆씠 議곌툑???뺤떎???뚮젮吏怨??덉뒿?덈떎. "
        "鍮꾨줈 ???섎??쇱＜??遺?곗떆??후보 ?묒빀?꾨뿉?꽌?? ?꾩옱??援?쉶?섏썝??37. 4%瑜??湲곕줉?덈떎. "
        "?댁옱?? ?꾩옱 ? 遺?곗떆??10. 6%蹂대떎 ?ш쾶 ?욌??덊땲?? ?쒕뒗 ?대? ?섏튂 ?띿뿉?? "
        "?댁옱?깆쓽 媛?μ꽦??蹂댁븯?듬땲?? 寃쎈궓?꾩뿉?꽌???쇰ぉ?섎뒗 ?댁옱?깆쓽 ?낅땲?? "
        "?쒕? ???꾩쓽 二쇱쭊?? 遺?곗떆?? 鍮꾩쟾怨??뺤콉?? ?붽렇?쟻쑝濡??뚮┛ 湲고쉶?낅땲??</p>"
    )

    updated, edited, sentence = _inject_keyword_into_section(
        section,
        "二쇱쭊???섏썝",
        "body",
        0,
    )

    assert updated == section
    assert edited is False
    assert sentence == ""


def test_force_insert_insufficient_keywords_skips_visible_intent_surface_for_conflicting_role_keyword() -> None:
    content = "<p>부산 경제를 살리기 위한 실천 방안을 말씀드리겠습니다.</p>"
    keyword_validation = {
        "주진우 부산시장": {"status": "insufficient", "expected": 1},
    }
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원이 30.3%, 이재성 전 위원장이 31.7%를 기록했다.",
        ],
    )

    updated = force_insert_insufficient_keywords(
        content,
        ["주진우 부산시장"],
        keyword_validation,
        role_keyword_policy=role_keyword_policy,
    )

    assert updated == content


def test_inject_keyword_into_section_skips_intent_reference_fallback_in_body_paragraph() -> None:
    section = (
        "<p>첫 문단은 이번 글의 도입입니다.</p>"
        "<p>둘째 문단에서는 부산 경제와 일자리 해법을 설명합니다.</p>"
    )
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원이 30.3%, 이재성 전 위원장이 31.7%를 기록했다.",
        ],
    )

    updated, edited, sentence = _inject_keyword_into_section(
        section,
        "주진우 부산시장",
        "body",
        0,
        allow_reference_fallback=True,
        role_keyword_policy=role_keyword_policy,
    )

    assert updated == section
    assert edited is False
    assert sentence == ""


def test_inject_keyword_into_section_does_not_splice_role_keyword_into_noun_phrase() -> None:
    section = "<p>시민들의 삶과 직결된 문제들을 해결하기 위해 실천 방안을 설명합니다.</p>"
    updated, edited, sentence = _inject_keyword_into_section(
        section,
        "주진우 의원",
        "body",
        0,
    )

    assert updated == section
    assert edited is False
    assert sentence == ""


def test_rewrite_sentence_with_keyword_does_not_match_inside_word() -> None:
    sentence = "부산의 잠재력을 극대화하겠습니다."

    rewritten = _rewrite_sentence_with_keyword(
        sentence,
        "이재성 전재수",
    )

    assert rewritten == sentence


def test_inject_keyword_into_section_emits_before_after_logs_for_safe_rewrite() -> None:
    section = "<p>부산 경제 문제를 풀 구체적인 계획을 설명합니다.</p>"
    with patch("services.posts.validation.keyword_injection.logger.info") as mock_logger:
        updated, edited, sentence = _inject_keyword_into_section(
            section,
            "이재성 전재수",
            "body",
            0,
            section_index=1,
        )

    assert edited is True
    assert "이재성 전재수 문제" in updated
    assert sentence == "부산 경제 이재성 전재수 문제를 풀 구체적인 계획을 설명합니다."
    messages = [str(call.args[0]) for call in mock_logger.call_args_list]
    assert any("Keyword sentence rewrite applied" in message for message in messages)
    assert any("Keyword section rewrite applied" in message for message in messages)


def test_force_insert_insufficient_keywords_does_not_append_intent_reference_sentence() -> None:
    content = (
        "<p>첫 문단은 이번 글의 도입입니다.</p>"
        "<p>둘째 문단에서는 부산 경제와 일자리 해법을 설명합니다.</p>"
        "<p>셋째 문단에서는 산업 전환 방향을 정리합니다.</p>"
    )
    keyword_validation = {
        "주진우 부산시장": {"status": "insufficient", "expected": 2},
    }
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원이 30.3%, 이재성 전 위원장이 31.7%를 기록했다.",
        ],
    )

    updated = force_insert_insufficient_keywords(
        content,
        ["주진우 부산시장"],
        keyword_validation,
        role_keyword_policy=role_keyword_policy,
    )

    assert updated == content


def test_validate_keyword_insertion_counts_intent_title_toward_role_keyword_requirement() -> None:
    result = validate_keyword_insertion(
        "<p>부산 경제는 이재성입니다.</p>",
        user_keywords=["주진우 부산시장"],
        auto_keywords=[],
        title_text="주진우 부산시장 출마? 양자대결서 드러난 이재성 가능성",
        body_min_overrides={"주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우 부산시장": 2},
    )
    info = ((result.get("details") or {}).get("keywords") or {}).get("주진우 부산시장") or {}

    assert result.get("valid") is True
    assert int(info.get("count") or 0) == 1
    assert int(info.get("titleCount") or 0) == 1
    assert int(info.get("bodyCount") or 0) == 0


def test_validate_keyword_insertion_accepts_same_sentence_reflection_but_tracks_exact_shortfall() -> None:
    result = validate_keyword_insertion(
        "<p>부산시장 선거에서 주진우 의원이 다시 거론되고 있습니다.</p>",
        user_keywords=["주진우 부산시장"],
        auto_keywords=[],
        body_min_overrides={"주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우 부산시장": 2},
    )
    info = ((result.get("details") or {}).get("keywords") or {}).get("주진우 부산시장") or {}

    assert result.get("valid") is True
    assert int(info.get("gateCount") or 0) == 1
    assert int(info.get("exclusiveCount") or 0) == 0
    assert int(info.get("sentenceCoverageCount") or 0) == 1
    assert int(info.get("exactShortfall") or 0) == 1


def test_enforce_keyword_requirements_keeps_sentence_coverage_for_intent_role_keyword() -> None:
    content = (
        "<p>부산시장 선거에서 주진우 의원이 다시 거론되고 있습니다.</p>"
        "<p>이재성의 가능성이 조금씩 커지고 있습니다.</p>"
    )
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원이 30.3%, 이재성 전 위원장이 31.7%를 기록했다.",
        ],
    )

    repaired = enforce_keyword_requirements(
        content,
        user_keywords=["주진우 부산시장"],
        auto_keywords=[],
        title_text="",
        body_min_overrides={"주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우 부산시장": 2},
        role_keyword_policy=role_keyword_policy,
        max_iterations=1,
    )
    updated = str(repaired.get("content") or "")
    info = (((repaired.get("keywordResult") or {}).get("details") or {}).get("keywords") or {}).get("주진우 부산시장") or {}

    assert updated == content
    assert int(info.get("sentenceCoverageCount") or 0) >= 1
    assert int(info.get("exclusiveCount") or 0) == 0
    assert int(info.get("exactShortfall") or 0) == 1


def test_enforce_keyword_requirements_skips_broken_poll_residue_section() -> None:
    content = (
        "<h2>?댁옱???몄? ??μ긽, ?쒕???湲곕?'</h2>"
        "<p>?щ줎議곗궗?먯꽌 ?댁옱?깆씠 議곌툑???뺤떎???뚮젮吏怨??덉뒿?덈떎. "
        "鍮꾨줈 ???섎??쇱＜??遺?곗떆??후보 ?묒빀?꾨뿉?꽌?? ?꾩옱??援?쉶?섏썝??37. 4%瑜??湲곕줉?덈떎. "
        "?댁옱?? ?꾩옱 ? 遺?곗떆??10. 6%蹂대떎 ?ш쾶 ?욌??덊땲?? ?쒕뒗 ?대? ?섏튂 ?띿뿉?? "
        "?댁옱?깆쓽 媛?μ꽦??蹂댁븯?듬땲?? 寃쎈궓?꾩뿉?꽌???쇰ぉ?섎뒗 ?댁옱?깆쓽 ?낅땲?? "
        "?쒕? ???꾩쓽 二쇱쭊?? 遺?곗떆?? 鍮꾩쟾怨??뺤콉?? ?붽렇?쟻쑝濡??뚮┛ 湲고쉶?낅땲??</p>"
    )

    repaired = enforce_keyword_requirements(
        content,
        user_keywords=[
            "주진우 부산시장",
            "주진우",
            "3일",
            "4일",
            "013명",
            "전재수 국회의원",
            "주진우 국회의원",
        ],
        auto_keywords=[],
        title_text="",
        max_iterations=1,
    )
    updated = str(repaired.get("content") or "")
    issues = _detect_integrity_gate_issues(updated)

    assert "고유명사/직함 토큰이 비정상적으로 연속됨" not in issues
    assert "숫자+인명/직함 토큰이 비정상적으로 결합됨" not in issues
    assert "3일 4일 013명" not in updated


def test_enforce_keyword_requirements_does_not_force_auto_keywords_without_user_keywords() -> None:
    content = "<p>부산 경제를 살릴 실행 계획을 차분히 설명드리겠습니다.</p>"

    repaired = enforce_keyword_requirements(
        content,
        user_keywords=[],
        auto_keywords=["경남도"],
        title_text="",
        max_iterations=1,
    )

    assert repaired.get("edited") is False
    assert str(repaired.get("content") or "") == content


def test_enforce_keyword_requirements_reduces_shadowed_short_keyword_even_when_skipped_for_under_min() -> None:
    content = (
        "<p>주진우 부산시장 출마 가능성도 함께 거론됩니다.</p>"
        "<p>주진우 의원과의 경쟁에서도 저는 준비돼 있습니다.</p>"
        "<p>주진우 의원이 제시하지 못한 비전을 제가 보여드리겠습니다.</p>"
        "<p>주진우 의원과 비교했을 때, 저는 부산 경제의 해법을 더 잘 알고 있습니다.</p>"
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
    )
    repaired = enforce_keyword_requirements(
        content,
        user_keywords=["주진우", "주진우 부산시장"],
        auto_keywords=[],
        title_text="주진우 부산시장 출마? 양자대결서 드러난 이재성 가능성",
        body_min_overrides={"주진우": 0, "주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우": 0, "주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우": 4, "주진우 부산시장": 2},
        skip_user_keywords=["주진우"],
        role_keyword_policy=build_role_keyword_policy(
            ["주진우", "주진우 부산시장"],
            person_roles={"주진우": "국회의원"},
            source_texts=[
                "부산시장 양자대결에서 주진우 의원이 30.3%, 이재성 전 위원장이 31.7%를 기록했다.",
            ],
        ),
        max_iterations=1,
    )
    updated = str(repaired.get("content") or "")
    counts = _count_user_keyword_exact_non_overlap(updated, ["주진우", "주진우 부산시장"])

    assert int(counts.get("주진우") or 0) <= 4
    assert "주진우 부산시장" in updated


def test_enforce_keyword_requirements_does_not_retarget_already_hit_section_for_same_keyword() -> None:
    keyword = "이재성 전재수"
    content = (
        f"<h2>첫 번째 섹션</h2><p>{keyword} 비전과 계획을 설명합니다.</p>"
        "<h2>두 번째 섹션</h2><p>부산 경제의 계획을 설명합니다.</p>"
    )

    repaired = enforce_keyword_requirements(
        content,
        user_keywords=[keyword],
        auto_keywords=[],
        title_text="",
        body_min_overrides={keyword: 0},
        user_keyword_expected_overrides={keyword: 3},
        user_keyword_max_overrides={keyword: 4},
        max_iterations=1,
    )
    updated = str(repaired.get("content") or "")
    rewrite_requests = list(repaired.get("rewriteRequests") or [])

    assert f"<p>{keyword} 비전과 계획을 설명합니다.</p>" in updated
    assert f"<p>부산 경제의 {keyword} 계획을 설명합니다.</p>" in updated
    assert updated.count(keyword) == 2
    assert any(
        str(item.get("reason") or "") == "no_safe_target_section"
        for item in rewrite_requests
        if isinstance(item, dict)
    )


def test_repair_keyword_gate_once_logs_snapshot_and_result() -> None:
    keyword = "이재성 전재수"
    content = "<p>부산 경제의 계획을 설명합니다.</p>"

    with patch("handlers.generate_posts_pkg.pipeline.logger.info") as mock_logger:
        repaired = _repair_keyword_gate_once(
            content=content,
            title_text="",
            user_keywords=[keyword],
            auto_keywords=[],
            target_word_count=2000,
            body_min_overrides={keyword: 0},
            user_keyword_expected_overrides={keyword: 1},
            user_keyword_max_overrides={keyword: 2},
        )

    assert bool(repaired.get("edited")) is True
    messages = [str(call.args[0]) for call in mock_logger.call_args_list]
    assert any("Keyword gate repair snapshot" in message for message in messages)
    assert any("Keyword gate repair result" in message for message in messages)


def test_build_display_keyword_validation_keeps_soft_keyword_spam_risk_visible() -> None:
    display = _build_display_keyword_validation(
        {
            "주진우": {
                "count": 8,
                "expected": 3,
                "max": 4,
                "status": "spam_risk",
                "type": "user",
                "exclusiveCount": 8,
            }
        },
        soft_keywords=["주진우"],
        shadowed_map={"주진우": ["주진우 부산시장"]},
    )
    info = display.get("주진우") or {}

    assert info.get("soft") is True
    assert info.get("status") == "spam_risk"
    assert int(info.get("max") or 0) == 4


def test_calculate_title_quality_score_rejects_truncated_numeric_title() -> None:
    params = {
        "topic": "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        "contentPreview": "이재성이 주진우 의원과의 양자대결에서 앞서는 흐름을 보였습니다.",
        "userKeywords": ["주진우"],
        "fullName": "이재성",
    }

    result = calculate_title_quality_score(
        "이재성, 주진우 국회의원과 가상대결서 우위… 부산시장 선거 90",
        params,
        {"autoFitLength": False},
    )

    assert result.get("passed") is False
    assert int(result.get("score") or 0) == 0


def test_score_title_compliance_fails_closed_on_scoring_exception() -> None:
    import agents.common.title_generation as title_generation_module

    original = title_generation_module.calculate_title_quality_score

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    title_generation_module.calculate_title_quality_score = _boom
    try:
        result = _score_title_compliance(
            title="주진우, 이재성의 가능성",
            topic="부산시장 선거 양자대결에서 확인된 이재성의 가능성",
            content="이재성 전 위원장과 주진우 의원의 가상대결은 31.7% 대 30.3%였다.",
            user_keywords=["주진우"],
            full_name="이재성",
            category="current-affairs",
            status="campaign",
            context_analysis={},
            role_keyword_policy={},
            poll_focus_bundle={},
        )
    finally:
        title_generation_module.calculate_title_quality_score = original

    assert result["passed"] is False
    assert result["reason"] == "scoring_error"


def test_prune_problematic_integrity_fragments_drops_low_signal_name_noun_residue() -> None:
    repaired = _prune_problematic_integrity_fragments("전재수 소통")
    updated = str(repaired.get("content") or "")

    assert repaired.get("edited") is True
    assert "전재수 소통" not in updated


def test_repair_competitor_policy_phrase_once_removes_extended_candidate_residue_chain() -> None:
    content = (
        "<p>많은 분들이 부산시장 선거 판세와 저의 가능성에 대해 궁금해하십니다. "
        "부산 시민 여러분께 저의 전재수 국회의원 전재수 의원 이재성도 경남도 후보군 비전을 충분히 전달하겠습니다.</p>"
    )

    repaired = _repair_competitor_policy_phrase_once(
        content,
        full_name="이재성",
        person_roles={"이재성": "전 부산시당위원장", "전재수": "국회의원", "주진우": "국회의원"},
    )
    updated = str(repaired.get("content") or "")

    assert "전재수 국회의원 전재수 의원" not in updated
    assert "후보군 비전" not in updated
    assert "저의 비전을 충분히 전달하겠습니다." in updated


def test_repair_competitor_policy_phrase_once_removes_matchup_tail_residue_chain() -> None:
    content = (
        "<p>선거까지 남은 90일은 결코 짧은 시간이 아닙니다."
        "이 기간 동안 저는 부산 시민들께 저의 전재수 국회의원 이재성도 경남도 후보군 대결에서도 "
        "비전을 더욱 확실히 알리겠습니다.</p>"
    )

    repaired = _repair_competitor_policy_phrase_once(
        content,
        full_name="이재성",
        person_roles={"이재성": "전 부산시당위원장", "전재수": "국회의원", "주진우": "국회의원"},
    )
    updated = str(repaired.get("content") or "")

    assert "후보군 대결" not in updated
    assert "전재수 국회의원 이재성도 경남도" not in updated
    assert "저의 비전을 더욱 확실히 알리겠습니다." in updated


def test_remove_off_topic_poll_sentences_once_drops_internal_primary_poll_sentence() -> None:
    content = (
        "<p>선거까지 남은 90일은 결코 짧지 않습니다.</p>"
        "<p>최근 여론조사에서 더불어민주당 내 경쟁에서 전재수 의원이 37.4%를 기록하며 "
        "저 이재성 전 부산시당위원장보다 앞섰지만, 이는 저에게 더 큰 동기 부여가 됩니다.</p>"
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
        "<p>박형준 현 부산시장과의 양자대결에서는 30.9% 대 31.3%로 접전입니다.</p>"
    )
    poll_fact_table = build_poll_matchup_fact_table(
        [
            "이재성 전 위원장과 주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
            "이재성 전 위원장과 박형준 현 부산시장의 양자대결에서는 30.9% 대 31.3%로 나타났습니다.",
            "더불어민주당 내 경쟁에서 전재수 의원이 37.4%를 기록했다.",
        ],
        known_names=["이재성", "주진우", "박형준", "전재수"],
    )
    repaired = _remove_off_topic_poll_sentences_once(
        content,
        full_name="이재성",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        title_text="주진우 부산시장 출마? 90일 남은 선거 왜 이재성인가",
        user_keywords=["주진우", "주진우 부산시장"],
        role_facts={
            "이재성": "전 부산시당위원장",
            "주진우": "국회의원",
            "박형준": "부산시장",
            "전재수": "국회의원",
        },
        poll_fact_table=poll_fact_table,
    )
    updated = str(repaired.get("content") or "")

    assert "전재수 의원이 37.4%" not in updated
    assert "주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다." in updated
    assert "박형준 현 부산시장과의 양자대결에서는 30.9% 대 31.3%로 접전입니다." in updated
    assert repaired.get("edited") is True


def test_remove_off_topic_poll_sentences_once_drops_party_support_and_internal_scope_drift() -> None:
    content = (
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
        "<p>하지만 저는 이러한 당내 경선 수치에 연연하지 않고 시민만 바라보겠습니다.</p>"
        "<p>최근 여론조사에서 정당 지지율은 더불어민주당 31.8%, 국민의힘 25.4%, 지지정당 없음 35%였습니다.</p>"
        "<p>박형준 현 부산시장과의 양자대결에서는 30.9% 대 31.3%로 접전입니다.</p>"
    )
    poll_fact_table = build_poll_matchup_fact_table(
        [
            "이재성 전 위원장과 주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.",
            "이재성 전 위원장과 박형준 현 부산시장의 양자대결에서는 30.9% 대 31.3%로 나타났습니다.",
        ],
        known_names=["이재성", "주진우", "박형준"],
    )
    repaired = _remove_off_topic_poll_sentences_once(
        content,
        full_name="이재성",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        title_text="주진우 부산시장 출마? 왜 이재성이 약진했을까",
        user_keywords=["주진우", "주진우 부산시장"],
        role_facts={
            "이재성": "전 부산시당위원장",
            "주진우": "국회의원",
            "박형준": "부산시장",
        },
        poll_fact_table=poll_fact_table,
    )
    updated = str(repaired.get("content") or "")

    assert "당내 경선 수치" not in updated
    assert "정당 지지율은 더불어민주당" not in updated
    assert "주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다." in updated
    assert "박형준 현 부산시장과의 양자대결에서는 30.9% 대 31.3%로 접전입니다." in updated
    assert repaired.get("edited") is True


def test_final_sentence_polish_restores_missing_sentence_spacing() -> None:
    content = "<p>많은 분들이 궁금해하십니다.선거까지 남은 시간은 충분합니다.</p>"
    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "궁금해하십니다. 선거까지" in updated


def test_repair_terminal_sentence_spacing_once_restores_missing_spacing() -> None:
    content = "<p>선거까지 남은 90일은 결코 짧은 시간이 아닙니다.이 기간 동안 더 알리겠습니다.</p>"
    repaired = _repair_terminal_sentence_spacing_once(content)
    updated = str(repaired.get("content") or "")

    assert repaired.get("edited") is True
    assert "아닙니다. 이 기간" in updated


def test_normalize_lawmaker_honorifics_once_removes_lawmaker_candidate_chain() -> None:
    content = (
        "<p>주진우 의원 후보와는 차별화된 비전을 제시하겠습니다.</p>"
        "<p>주 의원 후보와의 경쟁에서도 흔들리지 않겠습니다.</p>"
    )
    repaired = _normalize_lawmaker_honorifics_once(
        content,
        {"주진우": "국회의원"},
        "이재성",
    )
    updated = str(repaired.get("content") or "")

    assert "주진우 의원 후보" not in updated
    assert "주 의원 후보" not in updated
    assert "주진우 의원과는" in updated
    assert "주 의원과의" in updated


def test_final_sentence_polish_dedupes_duplicate_poll_explanation_sentence() -> None:
    content = (
        "<p>최근 KNN이 서던포스트에 의뢰해 지난 3일과 4일 이틀 동안 만 18세 이상 부산 시민 1,013명을 대상으로 실시한 여론조사 결과는 변화를 보여줍니다.</p>"
        "<p>이번 여론 조사는 KNN이 서던포스트에 의뢰해 지난 3일과 4일 이틀 동안 만 18세 이상 부산 시민 1,013명을 대상으로 실시되었으며, 저는 이 결과를 겸허히 받아들이겠습니다.</p>"
    )
    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert updated.count("KNN이 서던포스트에 의뢰해") == 1
    assert repaired.get("edited") is True


def test_final_sentence_polish_repairs_duplicate_particles_in_heading_and_body() -> None:
    content = (
        "<h2>계양구의 밝은 미래를을 위한 약속과 비전</h2>"
        "<p>계양구민 삶의 질 향상을을 위해 끝까지 뛰겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content)
    updated = str(repaired.get("content") or "")

    assert "미래를을" not in updated
    assert "향상을을" not in updated
    assert "<h2>계양구의 밝은 미래를 위한 약속과 비전</h2>" in updated
    assert "계양구민 삶의 질 향상을 위해 끝까지 뛰겠습니다." in updated
    assert repaired.get("edited") is True
    assert "repair_duplicate_particles_and_tokens" in list(repaired.get("actions") or [])


def test_repair_duplicate_particles_preserves_normal_surfaces_and_repairs_true_duplicates() -> None:
    content = (
        "이러한 예산 확보 성과를 바탕으로 성과는 이어졌고, "
        "귀 기울이는 소중한 자세와 만들어 나가는 실행력, "
        "판교테크노밸리에 버금가는 비전을 함께 강조했습니다. "
        "마을을 지키겠다는 약속과 가을을 떠올리게 하는 이야기 역시 남겼습니다. "
        "계양구의 밝은 미래를을 위한 약속과 삶의 질 향상을을 위한 과제도 남았습니다."
    )

    repaired = repair_duplicate_particles_and_tokens(content)

    assert "성과를 바탕으로" in repaired
    assert "성과는 이어졌고" in repaired
    assert "귀 기울이는 소중한 자세" in repaired
    assert "만들어 나가는 실행력" in repaired
    assert "버금가는 비전" in repaired
    assert "마을을 지키겠다는 약속" in repaired
    assert "가을을 떠올리게 하는 이야기" in repaired
    assert "성를" not in repaired
    assert "성는" not in repaired
    assert "기울는" not in repaired
    assert "만들어 나는" not in repaired
    assert "버금는" not in repaired
    assert "마을 지키겠다는" not in repaired
    assert "가을 떠올리게" not in repaired
    assert "미래를을" not in repaired
    assert "미래를 위한" in repaired
    assert "향상을을" not in repaired
    assert "향상을 위한" in repaired


def test_final_sentence_polish_drops_broken_poll_fragment_sentence() -> None:
    content = (
        "<p>최근 여론조사에서 주진우 의원이 37.6%보다 크게 앞섰지만, 저의 인지도는 꾸준히 상승하고 있습니다.</p>"
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
    )
    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        role_facts={"주진우": "국회의원"},
        poll_fact_table={"knownNames": ["이재성", "주진우"]},
    )
    updated = str(repaired.get("content") or "")

    assert "37.6%보다 크게 앞섰지만" not in updated
    assert "31.7% 대 30.3%로 나타났습니다." in updated
    assert repaired.get("edited") is True


def test_final_sentence_polish_drops_leading_numeric_percent_fragment() -> None:
    content = (
        "<p>6%보다 크게 앞섰습니다.</p>"
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
    )
    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        role_facts={"주진우": "국회의원"},
        poll_fact_table={"knownNames": ["이재성", "주진우"]},
    )
    updated = str(repaired.get("content") or "")

    assert "6%보다 크게 앞섰습니다." not in updated
    assert "31.7% 대 30.3%로 나타났습니다." in updated
    assert repaired.get("edited") is True


def test_final_sentence_polish_repairs_matchup_result_and_future_role_fragments() -> None:
    content = (
        "<p>주진우 의원과의 가상대결에서 제가 여론조사 결과는 이러한 가능성을 보여줍니다.</p>"
        "<p>이러한 노력은 미래 주 의원과의 경쟁에서도 저의 강점으로 작용할 것입니다.</p>"
    )
    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "가상대결의 여론조사 결과는 이러한 가능성을 보여줍니다." in updated
    assert "향후 주 의원과의 경쟁에서도" in updated
    assert "가상대결에서 제가 여론조사 결과는" not in updated
    assert "미래 주 의원과의 경쟁에서도" not in updated
    assert repaired.get("edited") is True


def test_repair_integrity_noise_once_repairs_broken_result_clause_before_blocker() -> None:
    content = "<p>주진우 의원과의 가상대결에서 제가 결과는 이러한 가능성을 보여줍니다.</p>"

    before_issues = _detect_integrity_gate_issues(content)
    assert any("문장 파손(제가 결과 ...)" in issue for issue in before_issues)

    repaired = _repair_integrity_noise_once(content)
    updated = str(repaired.get("content") or "")
    after_issues = _detect_integrity_gate_issues(updated)

    assert "주진우 의원과의 가상대결 결과는 이러한 가능성을 보여줍니다." in updated
    assert not any("문장 파손(제가 결과 ...)" in issue for issue in after_issues)
    assert repaired.get("edited") is True


def test_final_sentence_polish_preserves_aligned_body_first_heading() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    content = (
        "<h2>이재성이 앞선 이유: 검증된 경영 경험</h2>"
        "<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
        "<p>저는 혁신기업 경영 일선에서 성과를 낸 경험으로 부산 경제 해법을 준비했습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        poll_focus_bundle=bundle,
    )
    updated = str(repaired.get("content") or "")

    assert "<h2>이재성이 앞선 이유: 검증된 경영 경험</h2>" in updated
    assert "<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>" not in updated


# synthetic_fixture
def test_final_sentence_polish_dedupes_intro_body_overlap_sentences() -> None:
    content = (
        "<p>지역에서 당원과 시민을 위해 헌신해 온 {user_title} {user_name}입니다. "
        "불법 비상계엄과 탄핵 정국 속에서도 민주주의와 공동체를 지키는 데 앞장섰습니다.</p>"
        "<h2>{region} 현안 해결 방향</h2>"
        "<p>저는 지역에서 당원과 시민을 위해 헌신하며 {user_title}으로서의 소임을 다하고 있습니다. "
        "불법 비상계엄과 탄핵 정국이라는 어려운 시기에도 국회 결집과 거리 집회에 참여하며 민주주의와 공동체를 지키는 데 앞장섰습니다.</p>"
        "<p>{region} 교통과 생활 현안을 끝까지 챙기겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="{user_name}")
    updated = str(repaired.get("content") or "")

    assert updated.count("당원과 시민을 위해") == 1
    assert updated.count("비상계엄") == 1
    assert "{region} 교통과 생활 현안을 끝까지 챙기겠습니다." in updated
    assert repaired.get("edited") is True
    assert any(str(action).startswith("intro_body_sentence_dedupe:") for action in list(repaired.get("actions") or []))


# synthetic_fixture
def test_final_sentence_polish_rewrites_speech_stage_framing() -> None:
    content = "<p>오늘 이 자리에서 제가 걸어온 길과 앞으로 나아갈 방향을 상세히 보고드리며 말씀드리겠습니다.</p>"

    repaired = _apply_final_sentence_polish_once(content, full_name="{user_name}")
    updated = str(repaired.get("content") or "")

    assert "오늘 이 자리에서" not in updated
    assert "상세히 보고드리며" not in updated
    assert "이 글에서" in updated
    assert "함께 말씀드리며" in updated


def test_final_sentence_polish_dedupes_duplicate_sections_before_style_overlay() -> None:
    content = (
        "<h2>지금 이재성에 주목해야 하는 이유</h2>"
        "<p>지금 이재성의 경쟁력은 확인됐습니다.</p>"
        "<h2>지금 이재성에 주목해야 하는 이유</h2>"
        "<p>지금 이재성의 경쟁력은 확인됐습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert updated.count("지금 이재성에 주목해야 하는 이유") == 1
    assert updated.count("지금 이재성의 경쟁력은 확인됐습니다.") == 1


def test_final_sentence_polish_dedupes_semantically_overlapping_focus_sections() -> None:
    content = (
        "<h2>지금 이재성에 주목해야 하는 이유</h2>"
        "<p>지금 이재성의 경쟁력은 확인됐습니다.</p>"
        "<h2>이재성의 가능성에 주목해야 하는 결정적인 이유</h2>"
        "<p>이재성의 가능성에 주목해야 하는 결정적인 이유는 여론조사 수치와 변화 요구가 동시에 확인됐기 때문입니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert updated.count("지금 이재성에 주목해야 하는 이유") == 1
    assert "이재성의 가능성에 주목해야 하는 결정적인 이유" not in updated
    assert updated.count("<h2>") == 1


def test_final_sentence_polish_scrubs_beyond_sincerity_and_duplicate_appeals() -> None:
    content = (
        "<p>이는 단순한 숫자가 아니라, 부산 시민의 변화 요구를 보여줍니다.</p>"
        "<p>이 수치는 단순한 숫자가 아니라, 부산 시민 여러분께서 변화를 갈망하고 계시다는 분명한 증거입니다.</p>"
        "<p>이는 단순한 수치를 넘어, 부산 시민의 변화 요구를 보여줍니다.</p>"
        "<p>저의 이러한 진정성이 부산 시민들에게 전달되고 있습니다.</p>"
        "<p>저의 진정성과 전문성에 공감하기 시작했습니다.</p>"
        "<p>이러한 직접적인 접근이 시민들의 마음을 움직이고 있습니다.</p>"
        "<p>그것은 단순히 숫자로만 볼 수 없습니다.</p>"
        "<p>이것은 단순한 구호가 아니라, 부산의 부산경제 대혁신을 향한 약속입니다.</p>"
        "<p>이러한 진정성이 시민들의 공감을 얻으며 인지도를 확장하는 핵심 동력이 되고 있습니다.</p>"
        "<p>저의 진심이 시민 여러분께 닿아 인지도가 확장되고 있다고 믿습니다.</p>"
        "<p>저의 삶의 궤적은 제가 부산의 정체성을 깊이 이해하고 있음을 증명합니다.</p>"
        "<p>이러한 경영 경험은 산업 전환을 이끌 저의 역량을 증명합니다.</p>"
        "<p>부산 시민들은 저의 삶의 경험과 봉사 정신을 통해 저의 진심을 알아보고 있습니다.</p>"
        "<p>이 흐름은 이재성의 이름과 메시지가 부산 시민 사이에서 조금씩 더 알려지고 있음을 보여줍니다.</p>"
        "<p>부산 시민 여러분께서는 저의 이러한 역량과 진정성을 알아봐 주셨습니다.</p>"
        "<p>시민 여러분께서는 저의 이러한 실질적인 경험과 비전을 높이 평가해 주셨습니다.</p>"
        "<p>시민 여러분께서는 저의 직접적인 행보와 실질적인 문제 해결 능력을 믿어주셨습니다.</p>"
        "<p>이러한 경험은 산업 전환을 이끌 전문성을 저에게 부여했습니다.</p>"
        "<p>이러한 실질적인 경험은 산업 전환 전문성을 저에게 주었습니다.</p>"
        "<p>이러한 경험은 현장에서 필요한 리더십을 길러주었습니다.</p>"
        "<p>이러한 노력들이 시민 여러분께 닿아 긍정적인 변화를 만들어내고 있다고 확신합니다.</p>"
        "<p>조금씩 확실히 알려지고 있으며, 이는 시민 여러분의 지지와 성원 덕분입니다.</p>"
        "<p>우리 아이들이 더 나은 미래를 꿈꿀 수 있는 부산 비전을 제시합니다.</p>"
        "<p>부산 시민의 삶을 더 나은 방향으로 이끌겠다는 약속입니다.</p>"
        "<p>저는 이 결과를 겸허히 받아들이며, 더욱 낮은 자세로 시민 여러분의 목소리에 귀 기울이겠습니다.</p>"
        "<p>이는 제가 우리 사회의 약한 이웃들과 함께하며 공동체의 가치를 실현해 온 증거입니다.</p>"
        "<p>최근 여론조사 결과는 저 이재성의 가능성을 분명히 보여주고 있습니다.</p>"
        "<p>저는 단순히 정치적 구호를 외치는 것이 아니라, 부산 산업 구조를 바꾸겠습니다.</p>"
        "<p>이러한 정책들이 단순한 구호에 그치지 않고 부산 경제 대혁신으로 이어져야 합니다.</p>"
        "<p>더 나은 미래, 더 이상 미룰 수 없습니다.</p>"
        "<p>부산의 더 나은 미래를 향한 약속입니다.</p>"
        "<p>더 나은 내일을 위해 나아갈 수 있는 원동력이 됩니다.</p>"
        "<p>단순한 지지율의 차이를 넘어섭니다.</p>"
        "<p>단순한 행정 경험을 넘어, 실질적 해법을 준비했습니다.</p>"
        "<p>단순히 추상적인 선언이 아니라, 바로 실행하겠습니다.</p>"
        "<p>단순한 고향이 아니라, 부산을 바꿀 실천의 출발점입니다.</p>"
        "<p>단순한 약속을 넘어 실제 성과로 보여드리겠습니다.</p>"
        "<p>단순히 기업 경영에만 머문 것이 아니라, 도시 구조를 봤습니다.</p>"
        "<p>단순히 경제 지표에만 머물지 않고 현장을 보겠습니다.</p>"
        "<p>저는 단순히 보여주기식 행정이 아니라, 현장에서 해법을 준비했습니다.</p>"
        "<p>이 결과는 단순한 출발점이 아니라, 31.7% 대 30.3%입니다.</p>"
        "<p>이 땅의 부산항 부두 노동자의 막내들과 함께 성장했습니다.</p>"
        "<p>저의 발걸음에 많은 관심과 응원 부탁드립니다.</p>"
        "<p>저의 진심을 담은 이 약속에 많은 지지와 성원을 부탁드립니다.</p>"
        "<p>주진우 의원과 비교했을 때, 저는 실질적인 경제 해법을 제시합니다.</p>"
        "<p>급변하는 IT 산업과 첨단 기술 분야에서 쌓은 경험은 저에게 미래를 예측하고 선도하는 통찰력을 제공했습니다.</p>"
        "<p>혁신적인 사고방식과 과감한 실행력은 부산 경제 문제를 해결하는 데 필수적인 자산이 될 것입니다.</p>"
        "<p>혁신적인 사고방식과 과감한 실행력은 부산 경제를 다시 세우는 큰 자산이 됩니다.</p>"
        "<p>저의 비전이 부산의 새로운 도약을 이끌 것이라고 확신합니다.</p>"
        "<p>저는 단순히 이론적인 정책이 아닌, 실제 기업 경영을 통해 검증된 접근을 제시합니다.</p>"
        "<p>저의 경험은 단순한 이론이 아닌, 실제 성과로 증명된 것입니다.</p>"
        "<p>저의 리더십과 실질적인 경험이 부산의 변화를 이끌어낼 것이라 확신합니다.</p>"
        "<p>이러한 실질적인 경험은 부산 산업 전환의 큰 자산이 됩니다.</p>"
        "<p>이러한 경험은 제가 현장에서 필요한 리더십을 갖추게 했습니다.</p>"
        "<p>명확한 우선순위를 설정하고, 필요한 자원과 일정을 현실적으로 맞추어 추진하겠습니다.</p>"
        "<p>33세라는 젊은 나이에 쌓은 경영 경험은 부산 경제를 풀 필수적인 자산입니다.</p>"
        "<p>이러한 혁신적인 경영 경험은 급변하는 산업 현장의 흐름을 정확히 예측하고, 미래를 선도하는 통찰력을 저에게 길러주었습니다.</p>"
        "<p>이 경험은 통찰력과 문제 해결 능력을 길러주었습니다.</p>"
        "<p>이 경험은 문제 해결 능력을 길러주었습니다.</p>"
        "<p>이 경험은 미래를 예측하고 선제적으로 대응하는 힘을 길렀습니다.</p>"
        "<p>이는 단순한 이론이나 추상적인 구상이 아닌, 실제 성과로 이미 증명된 저의 역량입니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        style_fingerprint={
            "aiAlternatives": {"instead_of_더_나은_미래": "부산경제 대혁신"},
        },
    )
    updated = str(repaired.get("content") or "")

    assert "단순한 수치를 넘어" not in updated
    assert "단순한 숫자가 아니라" not in updated
    assert "부산 시민의 변화 요구를 보여줍니다." not in updated
    assert "변화를 갈망하고 계시다는 분명한 증거" not in updated
    assert "저의 이러한 진정성이 부산 시민들에게 전달되고 있습니다." not in updated
    assert "공감하기 시작했습니다" not in updated
    assert "마음을 움직이고 있습니다" not in updated
    assert "현장의 반응이 달라지고 있습니다" not in updated
    assert "단순히 숫자로만" not in updated
    assert "숫자로만 볼 수 없습니다" not in updated
    assert "단순한 구호가 아니라" not in updated
    assert "공감을 얻으며 인지도를 확장하는 핵심 동력" not in updated
    assert "인지도가 확장되고 있다고 믿습니다" not in updated
    assert "정체성을 깊이 이해하고 있음을 증명합니다" not in updated
    assert "저의 역량을 증명합니다" not in updated
    assert "저의 진심을 알아보고 있습니다" not in updated
    assert "알려지고 있음을 보여줍니다" not in updated
    assert "알아봐 주셨습니다" not in updated
    assert "높이 평가해 주셨습니다" not in updated
    assert "믿어주셨습니다" not in updated
    assert "전문성을 저에게 부여했습니다" not in updated
    assert "전문성을 저에게 주었습니다" not in updated
    assert "리더십을 길러주었습니다" not in updated
    assert "긍정적인 변화를 만들어내고 있다고 확신합니다" not in updated
    assert "조금씩 확실히 알려지고 있으며" not in updated
    assert "더 나은 방향" not in updated
    assert "겸허히 받아들이며" not in updated
    assert "낮은 자세로" not in updated
    assert "공동체의 가치를 실현해 온 증거입니다" not in updated
    assert "가능성을 분명히 보여주고 있습니다" not in updated
    assert "단순히 정치적 구호를 외치는 것이 아니라" not in updated
    assert "단순한 구호에 그치지 않고" not in updated
    assert "저는 부산 산업 구조를 바꾸겠습니다." not in updated
    assert "더 나은 미래" not in updated
    assert "더 나은 내일" not in updated
    assert "단순한 지지율의 차이를 넘어섭니다" not in updated
    assert "단순한 행정 경험을 넘어" not in updated
    assert "단순히 추상적인 선언이 아니라" not in updated
    assert "단순한 고향이 아니라" not in updated
    assert "단순한 약속을 넘어" not in updated
    assert "단순히 기업 경영에만" not in updated
    assert "단순히 경제 지표에만" not in updated
    assert "단순히 보여주기식 행정이 아니라" not in updated
    assert "단순한 출발점이 아니라" not in updated
    assert "부산경제 대혁신를" not in updated
    assert "부산경제 대혁신" in updated
    assert "부산의 부산경제" not in updated
    assert "저는 현장에서 해법을 준비했습니다." not in updated
    assert "이 결과는 31.7% 대 30.3%입니다." not in updated
    assert "부산항 부두 노동자의 막내들" not in updated
    assert "부산항 부두 노동자의 자녀들" in updated
    assert updated.count("부탁드립니다") == 1
    assert "비교했을 때" not in updated
    assert "저는 실질적인 경제 해법을 제시합니다." in updated
    assert "통찰력을 제공했습니다" not in updated
    assert "필수적인 자산이 될 것입니다" not in updated
    assert "큰 자산이 됩니다" not in updated
    assert "새로운 도약을 이끌 것이라고 확신합니다" not in updated
    assert "단순히 이론적인 정책이 아닌" not in updated
    assert "단순한 이론이 아닌" not in updated
    assert "실제 성과로 증명된 것입니다" not in updated
    assert "이끌어낼 것이라 확신합니다" not in updated
    assert "리더십을 갖추게 했습니다" not in updated
    assert "명확한 우선순위를 설정하고" not in updated
    assert "필수적인 자산입니다" not in updated
    assert "통찰력을 저에게 길러주었습니다" not in updated
    assert "통찰력과 문제 해결 능력을 길러주었습니다" not in updated
    assert "문제 해결 능력을 길러주었습니다" not in updated
    assert "미래를 예측하고 선제적으로 대응하는" not in updated
    assert "실제 성과로 이미 증명된 저의 역량입니다" not in updated
    assert "저는 실제 기업 경영을 통해 검증된 접근을 제시합니다." not in updated


def test_final_sentence_polish_trims_gehumility_clause_but_keeps_main_claim() -> None:
    content = "<p>저는 이 결과를 겸허히 받아들이며, 더욱 낮은 자세로 시민 여러분의 목소리에 귀 기울이겠습니다.</p>"

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "겸허히 받아들이며" not in updated
    assert "낮은 자세로" not in updated
    assert "시민 여러분의 목소리에 귀 기울이겠습니다." in updated


def test_final_sentence_polish_softens_certainty_phrase_without_dropping_sentence() -> None:
    content = "<p>저의 비전이 도시의 새로운 도약을 이끌 것이라고 확신합니다.</p>"

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "것이라고 확신합니다" not in updated
    assert "저의 비전이 도시의 새로운 도약을 이끌 것입니다." in updated


def test_final_sentence_polish_drops_simple_negation_frames_from_latest_reference_draft() -> None:
    content = (
        "<p>부산은 저 이재성에게 단순한 고향을 넘어선 운명과도 같은 도시입니다.</p>"
        "<p>이는 단순한 수치상의 우위를 넘어, 새로운 리더십과 구체적인 해법을 기대하는 시민들의 목소리가 반영된 결과라고 확신합니다.</p>"
        "<p>단순히 추상적인 선언에 그치지 않고, 시민 여러분이 일상에서 직접 체감할 수 있는 실질적인 변화를 만들어내는 데 집중할 것입니다.</p>"
        "<p>부산 경제를 살릴 해법은 단순한 단기적인 부양책이 아닌, 지역 산업의 구조적 혁신에 있습니다.</p>"
        "<p>이러한 정책들은 단순히 경제 지표를 개선하는 것을 넘어, 시민 여러분의 월급봉투를 두둑하게 하는 데 기여할 것입니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "단순한" not in updated
    assert "단순히" not in updated


def test_final_sentence_polish_drops_extended_simple_negation_frames() -> None:
    content = (
        "<p>이러한 정책들은 단순히 이론적인 구상에 그치지 않고 시민 삶을 바꾸겠습니다.</p>"
        "<p>이 해법은 이론에만 머무르지 않고 현장에 바로 적용됩니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "단순히 이론적인 구상에 그치지 않고" not in updated
    assert "에만 머무르지 않고" not in updated


def test_final_sentence_polish_removes_hoekijeok_phrase_without_dropping_sentence() -> None:
    content = (
        "<p>시민의 삶의 질을 획기적으로 향상시키겠습니다.</p>"
        "<p>부산을 명실상부한 해양수도로 만들겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "획기적으로" not in updated
    assert "시민의 삶의 질을 향상시키겠습니다." in updated
    assert "명실상부한 해양수도" in updated


def test_final_sentence_polish_removes_jeokgeukjeok_phrase_without_dropping_sentence() -> None:
    content = (
        "<p>신산업을 적극적으로 유치하겠습니다.</p>"
        "<p>주민 의견을 적극적으로 수렴하겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "적극적으로" not in updated
    assert "신산업을 유치하겠습니다." in updated
    assert "주민 의견을 수렴하겠습니다." in updated


def test_final_sentence_polish_drops_negation_frame_extensions() -> None:
    content = (
        "<p>시민 참여에 그치지 않고 실행까지 연결하겠습니다.</p>"
        "<p>뿐만 아니라 지역 산업도 함께 살리겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "에 그치지 않고" not in updated
    assert "뿐만 아니라" not in updated


def test_final_sentence_polish_removes_verbose_postpositions_and_link_prefixes() -> None:
    content = (
        "<p>정책 추진에 있어서 속도를 높이겠습니다.</p>"
        "<p>점검함에 있어 기준을 분명히 하겠습니다.</p>"
        "<p>이를 통해, 시민의 삶을 바꾸겠습니다.</p>"
        "<p>이러한 점에서, 해법은 분명합니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "에 있어서" not in updated
    assert "함에 있어" not in updated
    assert "이를 통해" not in updated
    assert "이러한 점에서" not in updated
    assert "정책 추진 속도를 높이겠습니다." in updated
    assert "점검 기준을 분명히 하겠습니다." in updated
    assert "시민의 삶을 바꾸겠습니다." in updated
    assert "해법은 분명합니다." in updated


def test_final_sentence_polish_drops_translationese_sentences() -> None:
    content = (
        "<p>이 변화는 꼭 필요하다고 할 수 있습니다.</p>"
        "<p>이 흐름은 분명한 전환점인 것은 사실입니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "라고 할 수 있습니다" not in updated
    assert "것은 사실입니다" not in updated


def test_final_sentence_polish_rewrites_double_passive_surface() -> None:
    content = "<p>성과가 현장에서 되어지며 시민 삶에 반영됩니다.</p>"

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "되어지" not in updated
    assert "되며" in updated


def test_final_sentence_polish_trims_self_analytical_story_tail_and_repairs_signature_misuse() -> None:
    content = (
        "<p>부산에서 나고 자라 지역의 아픔과 기쁨을 함께 해온 저의 이야기는 시민들의 마음을 움직이는 강력한 힘이 됩니다.</p>"
        "<p>뼛속까지 부산사람들과 함께 성장했습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "마음을 움직이는 강력한 힘이 됩니다" not in updated
    assert "공감과 희망" not in updated
    assert "부산에서 나고 자라 지역의 아픔과 기쁨을 함께 해왔습니다." in updated
    assert "뼛속까지 부산사람들과" not in updated
    assert "부산 사람들과 함께 성장했습니다." in updated


def test_final_sentence_polish_repairs_signature_variant_to_exact_form() -> None:
    content = (
        "<p>뼛속까지 부산 사람, 이재성입니다.</p>"
        "<p>뼛속까지 부산 사람으로서 부산을 바꾸겠습니다.</p>"
        "<p>뼛속까지 부산사람, 이재성입니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "뼛속까지 부산 사람으로서" not in updated
    assert "뼛속까지 부산 사람, 이재성입니다." not in updated
    assert updated.count("뼛속까지 부산사람, 이재성입니다.") == 1


def test_final_sentence_polish_drops_role_keyword_intent_sentence_surface() -> None:
    content = (
        "<p>온라인에서는 주진우 의원 출마 가능성도 함께 언급됩니다.</p>"
        "<p>부산 경제를 살릴 실질적 해법을 설명하겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "온라인에서는 주진우 의원 출마 가능성도 함께 언급됩니다." not in updated
    assert "부산 경제를 살릴 실질적 해법을 설명하겠습니다." in updated


def test_final_sentence_polish_inserts_identity_signature_when_fingerprint_requires_it() -> None:
    content = (
        "<h2>결론</h2>"
        "<p>부산경제 대혁신, 반드시 이뤄내겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        style_fingerprint={
            "characteristicPhrases": {
                "signatures": ["뼛속까지 부산사람, 이재성입니다."],
            }
        },
    )
    updated = str(repaired.get("content") or "")

    assert "뼛속까지 부산사람, 이재성입니다. 부산경제 대혁신, 반드시 이뤄내겠습니다." in updated
    assert updated.count("뼛속까지 부산사람, 이재성입니다.") == 1


def test_final_sentence_polish_restores_empty_closing_section_paragraph() -> None:
    bundle = build_poll_focus_bundle(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        user_keywords=["주진우 부산시장", "주진우"],
        full_name="이재성",
        text_sources=[
            "이재성 전 위원장과 주진우 국회의원의 가상대결은 31.7% 대 30.3%로 나타났습니다.",
        ],
    )
    content = (
        "<h2>이재성이 주진우와의 가상대결에서 앞선 이유</h2>"
        "<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
        "<h2>부산 경제를 살릴 이재성의 해법</h2>"
        "<p>부산 경제를 살릴 해법은 지역 산업과 일자리 문제를 함께 풀 수 있는 실질적 정책에 있습니다.</p>"
        "<h2>지금 이재성에 주목해야 하는 이유</h2>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        full_name="이재성",
        poll_focus_bundle=bundle,
    )
    updated = str(repaired.get("content") or "")

    assert re.search(r"<h2\b[^>]*>[\s\S]*?</h2>\s*<p>[^<]{8,}</p>\s*$", updated)


def test_final_sentence_polish_drops_soft_self_analysis_and_project_management_sentences() -> None:
    content = (
        "<p>저의 비전과 실천 의지가 시민 여러분께 깊이 닿아, 앞서는 결과로 나타났습니다.</p>"
        "<p>저의 이러한 역량과 진정성을 높이 평가하고 적극적으로 인정해주신 것입니다.</p>"
        "<p>우선순위를 명확히 하고 필요한 자원과 일정을 현실적으로 맞추겠습니다.</p>"
        "<p>실행 과정에서 드러나는 한계는 즉시 보완해 완성도를 높이겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "저의 비전과 실천 의지" not in updated
    assert "앞서는 결과로 나타났습니다." in updated
    assert "역량과 진정성을 높이 평가" not in updated
    assert "우선순위를 명확히 하고" not in updated
    assert "완성도를 높이겠습니다" not in updated


def test_final_sentence_polish_removes_incomplete_trailing_sentence_and_numeric_beyond_variant() -> None:
    content = (
        "<p>이는 단순한 수치를 넘어, 부산 시민의 변화 요구를 보여줍니다.</p>"
        "<p>이러한 시민 여러분의 뜨거운 지지와 성원에 진심으로 깊이</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "단순한 수치를 넘어" not in updated
    assert "부산 시민의 변화 요구를 보여줍니다." not in updated
    assert "진심으로 깊이" not in updated


def test_final_sentence_polish_drops_predicateless_fragment_sentence() -> None:
    content = (
        "<p>부산 경제를 살리겠습니다.</p>"
        "<p>시민 여러분의 기대와 성원에 진심으로</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "부산 경제를 살리겠습니다." in updated
    assert "시민 여러분의 기대와 성원에 진심으로" not in updated


def test_remove_groundedness_violations_removes_unsupported_comparison_sentence() -> None:
    section_html = (
        "<p>이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다. "
        "주진우 의원은 부산 경제 비전을 제시했지만, 저는 그보다 더 구체적이고 실현 가능한 방안을 가지고 있습니다.</p>"
    )
    result = _remove_groundedness_violations_from_section(
        section_html,
        opponent_names=["주진우"],
        poll_number_tokens=("31.7%", "30.3%"),
    )
    updated = str(result.get("content") or "")

    assert result.get("edited") is True
    assert "그보다 더 구체적이고 실현 가능한 방안" not in updated
    assert "이재성·주진우 가상대결에서는 31.7% 대 30.3%로 나타났습니다." in updated


def test_remove_groundedness_violations_removes_direct_opponent_comparison_clause() -> None:
    section_html = (
        "<p>주진우 의원과는 달리, 저는 실질적인 경영 경험을 바탕으로 부산경제 대혁신 해법을 제시합니다.</p>"
        "<p>주진우 의원과는 차별화된 저 이재성만의 비전으로 부산을 바꾸겠습니다.</p>"
    )
    result = _remove_groundedness_violations_from_section(
        section_html,
        opponent_names=["주진우"],
        poll_number_tokens=(),
    )
    updated = str(result.get("content") or "")

    assert result.get("edited") is True
    assert "주진우 의원과는 달리" not in updated
    assert "주진우 의원과는 차별화된" not in updated


def test_remove_groundedness_violations_removes_competitor_mid_sentence_role_discussion() -> None:
    section_html = (
        "<p>이러한 변화의 중심에서 주진우 의원과 같은 인물들의 역할 또한 중요하게 논의되고 있지만, "
        "저는 부산 경제 해법을 현장에서 준비했습니다.</p>"
    )
    result = _remove_groundedness_violations_from_section(
        section_html,
        opponent_names=["주진우"],
        poll_number_tokens=(),
    )
    updated = str(result.get("content") or "")

    assert result.get("edited") is True
    assert "주진우 의원과 같은 인물들의 역할" not in updated


def test_remove_groundedness_violations_removes_orphan_boilerplate_sentence() -> None:
    section_html = (
        "<p>이 흐름은 이재성의 이름과 메시지가 부산 시민 사이에서 조금씩 더 알려지고 있음을 보여줍니다. "
        "이는 특정 정당에 얽매이지 않고 오직 부산의 발전만을 생각하는 저에게 큰 기회가 될 수 있습니다.</p>"
    )
    result = _remove_groundedness_violations_from_section(
        section_html,
        opponent_names=[],
        poll_number_tokens=(),
    )
    updated = str(result.get("content") or "")

    assert result.get("edited") is True
    assert "저에게 큰 기회가 될 수 있습니다" not in updated
    assert "이 흐름은 이재성의 이름과 메시지가 부산 시민 사이에서 조금씩 더 알려지고 있음을 보여줍니다." not in updated


def test_final_sentence_polish_drops_poll_reaction_interpretation_and_recognition_self_narration() -> None:
    content = (
        "<p>최근 여론조사에서 주 의원의 전략공천설이 화제라길래 봤더니, 제가 앞서는 결과가 나왔습니다.</p>"
        "<p>이 수치는 단순한 숫자가 아니라, 부산 시민 여러분께서 변화를 갈망하고 계시다는 분명한 증거입니다.</p>"
        "<p>이는 부산 시민 여러분께서 저의 비전에 주목하고 계시다는 분명한 신호입니다.</p>"
        "<p>저의 경쟁력은 부산 시민 여러분의 변화에 대한 강력한 열망을 보여주는 것입니다.</p>"
        "<p>제가 조금씩 확실히 알려지고 있습니다.</p>"
        "<p>저는 확실히 알려지고 있습니다.</p>"
        "<p>최근 양자대결 수치는 31.7% 대 30.3%로 나타났습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert "봤더니, 제가 앞서는 결과가 나왔습니다." in updated
    assert "단순한 숫자가 아니라" not in updated
    assert "분명한 증거" not in updated
    assert "주목하고 계시다는 분명한 신호" not in updated
    assert "강력한 열망을 보여주는 것입니다" not in updated
    assert "조금씩 확실히 알려지고 있습니다" not in updated
    assert "저는 확실히 알려지고 있습니다" not in updated
    assert "31.7% 대 30.3%" in updated


def test_final_sentence_polish_dedupes_repeated_career_fact_sentence() -> None:
    content = (
        "<p>33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다.</p>"
        "<p>부산 경제는 다시 일어서야 합니다.</p>"
        "<p>33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert updated.count("33세에 CJ인터넷 이사, 엔씨소프트 전무, 자율주행 스타트업 CEO로서 혁신기업 경영 일선에서 활약했습니다.") == 1
    assert "부산 경제는 다시 일어서야 합니다." in updated


# synthetic_fixture
def test_final_sentence_polish_dedupes_repeated_political_career_fact_sentence() -> None:
    content = (
        "<p>정책보좌관, {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 역임하며 {region} 현안 해결에 앞장섰습니다.</p>"
        "<p>{issue_topic}의 성공적 완성을 위해 교통망과 기업 유치를 함께 챙기겠습니다.</p>"
        "<p>정책보좌관을 시작으로 {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 맡으며 {region} 발전에 힘썼습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="{user_name}")
    updated = str(repaired.get("content") or "")

    assert updated.count("정책보좌관") == 1
    assert "{issue_topic}의 성공적 완성을 위해 교통망과 기업 유치를 함께 챙기겠습니다." in updated
    assert repaired.get("edited") is True
    assert any(str(action).startswith("career_fact_dedupe:") for action in list(repaired.get("actions") or []))


# synthetic_fixture
def test_final_sentence_polish_dedupes_repeated_policy_evidence_sentence() -> None:
    content = (
        "<p>지역화폐의 역할과 효과는 기준인물 시장께서 "
        "시장 재임 시절 이미 증명한 바 있습니다.</p>"
        "<p>{region}에서는 이 정책을 생활 현장에 맞게 조정해 실행하겠습니다.</p>"
        "<p>저는 지역화폐의 역할과 효과가 기준인물 시장께서 "
        "시장 재임 시절 증명한 바와 같이 민생 회복에 도움이 된다고 봅니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="{user_name}")
    updated = str(repaired.get("content") or "")

    assert updated.count("지역화폐의 역할과 효과") == 1
    assert "{region}에서는 이 정책을 생활 현장에 맞게 조정해 실행하겠습니다." in updated
    assert repaired.get("edited") is True
    assert any(str(action).startswith("policy_evidence_dedupe:") for action in list(repaired.get("actions") or []))


# synthetic_fixture
def test_final_sentence_polish_applies_cross_section_contract_to_activity_report() -> None:
    content = (
        "<p>{region} 현장에서 주민 의견을 듣고 정책 과제를 정리해 왔습니다.</p>"
        "<h2>{region} 현안 해결 방향</h2>"
        "<p>{career_role}, {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 맡으며 "
        "{region} 현안을 챙겨왔습니다.</p>"
        "<p>{issue_topic} 해결을 위해 예산과 행정 절차를 함께 점검하겠습니다.</p>"
        "<h2>{region} 실행 계획</h2>"
        "<p>{career_role}을 시작으로 {user_title}, 지역조직 사무국장, 지역위원장 직무대행을 역임하며 "
        "{region} 현장 경험을 쌓았습니다.</p>"
        "<p>{issue_topic} 해결 순서와 일정은 주민과 공유하겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        category="activity-report",
        full_name="{user_name}",
    )
    updated = str(repaired.get("content") or "")

    assert "{issue_topic} 해결을 위해 예산과 행정 절차를 함께 점검하겠습니다." in updated
    assert "{issue_topic} 해결 순서와 일정은 주민과 공유하겠습니다." in updated
    assert repaired.get("edited") is True
    assert any(
        str(action).startswith("cross_section_contract:duplicate_career_fact:")
        for action in list(repaired.get("actions") or [])
    )


# synthetic_fixture
def test_final_sentence_polish_applies_cross_section_contract_to_policy_proposal() -> None:
    content = (
        "<p>{region} 민생 회복을 위한 실행 근거를 먼저 설명합니다.</p>"
        "<h2>{policy_topic} 추진 근거</h2>"
        "<p>지역화폐의 역할과 효과는 기준인물 도지사 재임 시절 이미 증명한 바 있습니다.</p>"
        "<p>{region} 여건에 맞는 실행 모델을 구체화하겠습니다.</p>"
        "<h2>{policy_topic} 실행 계획</h2>"
        "<p>저는 지역화폐의 역할과 효과가 기준인물 도지사 재임 시절 증명한 바와 같이 "
        "{region} 민생 회복에도 도움이 된다고 봅니다.</p>"
        "<p>예산 규모와 우선 대상부터 차례로 확정하겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        category="policy-proposal",
        full_name="{user_name}",
    )
    updated = str(repaired.get("content") or "")

    assert "{region} 여건에 맞는 실행 모델을 구체화하겠습니다." in updated
    assert "예산 규모와 우선 대상부터 차례로 확정하겠습니다." in updated
    assert repaired.get("edited") is True
    assert any(
        str(action).startswith("cross_section_contract:duplicate_policy_evidence_fact:")
        for action in list(repaired.get("actions") or [])
    )


# synthetic_fixture
def test_final_sentence_polish_moves_future_agenda_sentence_to_future_section() -> None:
    content = (
        "<p>{region} 주민과 함께 현안을 점검해 온 {user_title} {user_name}입니다.</p>"
        "<h2>{issue_topic} 입법 성과</h2>"
        "<p>{issue_topic} 관련 조례를 발의하고 가결시키며 생활 현장의 불편을 줄였습니다. 주민 의견을 제도 개선으로 연결했습니다.</p>"
        "<p>앞으로도 도시첨단산업단지 2단계 지정을 마무리하고 광역철도망 계획이 가시화될 수 있도록 힘쓰겠습니다.</p>"
        "<h2>{region} 미래 비전</h2>"
        "<p>{region}의 지속 가능한 발전을 위해 필요한 과제를 단계별로 추진하겠습니다. 주민이 체감하는 변화로 연결하겠습니다.</p>"
        "<p>현장 의견을 반영해 실행 일정을 챙기고 필요한 기반을 마련하겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(
        content,
        category="activity-report",
        full_name="{user_name}",
    )
    updated = str(repaired.get("content") or "")

    achievement_index = updated.index("<h2>{issue_topic} 입법 성과</h2>")
    future_index = updated.index("<h2>{region} 미래 비전</h2>")
    moved_sentence = "앞으로도 도시첨단산업단지 2단계 지정을 마무리하고 광역철도망 계획이 가시화될 수 있도록 힘쓰겠습니다."

    assert moved_sentence not in updated[achievement_index:future_index]
    assert moved_sentence in updated[future_index:]
    assert repaired.get("edited") is True
    assert any(
        str(action).startswith("section_lane_move:")
        for action in list(repaired.get("actions") or [])
    )


def test_final_sentence_polish_dedupes_repeated_policy_bundle_sentence() -> None:
    content = (
        "<p>북항 재개발과 제조업 혁신, 스타트업 육성, 첨단금융, 관광 인프라를 함께 밀어 부산 경제를 다시 세우겠습니다.</p>"
        "<p>결론에서도 북항 재개발과 제조업 혁신, 스타트업 육성, 첨단금융, 관광 인프라를 함께 밀어 부산 경제를 다시 세우겠습니다.</p>"
        "<p>결론에서는 북항 재개발과 제조업 혁신에 더 속도를 내겠습니다.</p>"
    )

    repaired = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(repaired.get("content") or "")

    assert updated.count("북항 재개발과 제조업 혁신, 스타트업 육성, 첨단금융, 관광 인프라를 함께 밀어 부산 경제를 다시 세우겠습니다.") == 1
    assert "결론에서는 북항 재개발과 제조업 혁신에 더 속도를 내겠습니다." in updated


def test_remove_low_signal_keyword_sentence_once_keeps_poll_fact_sentence_body() -> None:
    content = "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
    repaired = _remove_low_signal_keyword_sentence_once(
        content,
        "주진우",
        ["주진우"],
    )
    updated = str(repaired.get("content") or "")

    assert "<p>" in updated
    assert "31.7% 대 30.3%" in updated
    assert "주 의원과의 가상대결" in updated or updated == content


def test_force_insert_preferred_exact_keywords_skips_visible_intent_exact_backfill() -> None:
    content = (
        "<p>부산시장 선거에서 주진우 의원이 다시 거론되고 있습니다.</p>"
        "<p>이재성의 가능성이 조금씩 커지고 있습니다.</p>"
    )
    role_keyword_policy = build_role_keyword_policy(
        ["주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=["부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었습니다."],
    )
    initial = validate_keyword_insertion(
        content,
        user_keywords=["주진우 부산시장"],
        auto_keywords=[],
        body_min_overrides={"주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우 부산시장": 2},
    )
    keyword_validation = (initial.get("details") or {}).get("keywords") or {}

    updated = force_insert_preferred_exact_keywords(
        content,
        user_keywords=["주진우 부산시장"],
        keyword_validation=keyword_validation,
        role_keyword_policy=role_keyword_policy,
    )
    final = validate_keyword_insertion(
        updated,
        user_keywords=["주진우 부산시장"],
        auto_keywords=[],
        body_min_overrides={"주진우 부산시장": 0},
        user_keyword_expected_overrides={"주진우 부산시장": 1},
        user_keyword_max_overrides={"주진우 부산시장": 2},
    )
    info = ((final.get("details") or {}).get("keywords") or {}).get("주진우 부산시장") or {}

    assert updated == content
    assert int(info.get("sentenceCoverageCount") or 0) >= 1
    assert int(info.get("exactShortfall") or 0) == 1


def test_reduce_excess_user_keyword_mentions_preserves_poll_fact_sentence_first() -> None:
    content = (
        "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
        "<p>주진우 의원과의 경쟁에서 차별화된 비전을 보여드리겠습니다.</p>"
        "<p>주진우 의원의 가능성보다 저의 경쟁력을 말씀드리겠습니다.</p>"
    )
    reduced = _reduce_excess_user_keyword_mentions(
        content,
        "주진우",
        ["주진우"],
        target_max=1,
    )
    updated = str(reduced.get("content") or "")
    counts = _count_user_keyword_exact_non_overlap(updated, ["주진우"])

    assert "31.7% 대 30.3%" in updated
    assert int(counts.get("주진우") or 0) <= 1


def test_build_independent_final_title_context_excludes_draft_title_history() -> None:
    context = _build_independent_final_title_context(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        category="daily-communication",
        content="<p>최종 원고 본문입니다.</p>",
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        user_profile={"name": "이재성"},
        status="active",
        data={
            "background": "배경",
            "instructions": ["지시"],
            "config": {"titleScope": {"mode": "default"}},
            "newsDataText": "뉴스 본문",
            "stanceText": "이재성의 가능성",
            "sourceInput": "소스 입력",
            "sourceContent": "소스 콘텐츠",
            "originalContent": "원문",
            "title": "가제",
            "titleHistory": [{"title": "가제"}],
            "recentTitles": ["가제"],
        },
        pipeline_result={
            "title": "파이프라인 가제",
            "titleHistory": [{"title": "파이프라인 가제"}],
            "recentTitles": ["파이프라인 가제"],
        },
        context_analysis={"mustPreserve": {"eventDate": "2026년 3월 3일"}},
        auto_keywords=["부산시장 선거"],
    )

    assert context.get("topic") == "부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성"
    assert context.get("content") == "<p>최종 원고 본문입니다.</p>"
    assert context.get("optimizedContent") == "<p>최종 원고 본문입니다.</p>"
    assert context.get("newsDataText") == "뉴스 본문"
    assert context.get("stanceText") == "이재성의 가능성"
    assert context.get("sourceInput") == "소스 입력"
    assert "title" not in context
    assert "titleHistory" not in context
    assert "recentTitles" not in context


def test_build_independent_final_title_context_includes_recent_title_memory_when_provided() -> None:
    context = _build_independent_final_title_context(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 보인 이재성의 가능성",
        category="daily-communication",
        content="<p>최종 원고 본문입니다.</p>",
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        user_profile={"name": "이재성"},
        status="active",
        data={},
        pipeline_result={},
        context_analysis={},
        auto_keywords=["부산시장 선거"],
        recent_titles=[
            "주진우 부산시장 출마? 왜 이재성에게 흔들리나",
            "주진우 부산시장 출마? 왜 이재성이 약진했을까",
            "주진우 부산시장 출마? 왜 이재성에게 흔들리나",
        ],
    )

    assert context.get("recentTitles") == [
        "주진우 부산시장 출마? 왜 이재성에게 흔들리나",
        "주진우 부산시장 출마? 왜 이재성이 약진했을까",
    ]
    assert "titleHistory" not in context


def test_build_independent_final_title_context_focuses_matchup_content_and_filters_stance_noise() -> None:
    context = _build_independent_final_title_context(
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        category="daily-communication",
        content=(
            "<p>주진우 의원과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
            "<p>정당 지지율은 더불어민주당 31.8%, 국민의힘 25.4%, 지지정당 없음 35%였습니다.</p>"
            "<p>부산 경제는 이재성입니다.</p>"
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        user_profile={"name": "이재성"},
        status="active",
        data={
            "background": "배경",
            "instructions": ["지시"],
            "config": {"titleScope": {"mode": "default"}},
            "newsDataText": "뉴스 본문",
            "stanceText": "이재성도 충분히 이깁니다.\n* KNN 뉴스\n3월5일(목) 17시 방송분\n부산의 변화를 만들겠습니다.",
            "sourceInput": "소스 입력",
            "sourceContent": "소스 콘텐츠",
            "originalContent": "원문",
        },
        pipeline_result={},
        context_analysis={
            "mustIncludeFromStance": [
                "이재성도 충분히 이깁니다.",
                "부산의 변화를 만들겠습니다.",
                "KNN 뉴스 3월5일(목) 17시 방송분",
            ]
        },
        auto_keywords=["부산시장 선거"],
    )

    assert "31.7% 대 30.3%" in str(context.get("content") or "")
    assert "정당 지지율" not in str(context.get("content") or "")
    assert "부산 경제는 이재성입니다" not in str(context.get("content") or "")
    assert context.get("stanceText") == "부산의 변화를 만들겠습니다."


def main() -> None:
    tests = [
        ("rewrite_excess_keyword_sentence", test_rewrite_excess_keyword_sentence),
        (
            "rewrite_sentence_to_reduce_role_keyword_avoids_related_issue_fragment",
            test_rewrite_sentence_to_reduce_role_keyword_avoids_related_issue_fragment,
        ),
        (
            "build_keyword_replacement_pool_avoids_issue_tokens",
            test_build_keyword_replacement_pool_avoids_issue_tokens,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title",
            test_rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title_for_bare_name",
            test_rewrite_sentence_to_reduce_keyword_prefers_short_lawmaker_title_for_bare_name,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_drops_first_person_competitor_comparison_clause",
            test_rewrite_sentence_to_reduce_keyword_drops_first_person_competitor_comparison_clause,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_prefers_short_governor_title",
            test_rewrite_sentence_to_reduce_keyword_prefers_short_governor_title,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_role_surface_keeps_full_name_first",
            test_rewrite_sentence_to_reduce_keyword_role_surface_keeps_full_name_first,
        ),
        (
            "role_keyword_policy_tracks_explicit_candidate_registration_per_person",
            test_role_keyword_policy_tracks_explicit_candidate_registration_per_person,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_uses_source_role_without_candidate_promotion",
            test_rewrite_sentence_to_reduce_keyword_uses_source_role_without_candidate_promotion,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_allows_candidate_label_only_when_explicit",
            test_rewrite_sentence_to_reduce_keyword_allows_candidate_label_only_when_explicit,
        ),
        (
            "rewrite_sentence_to_reduce_conflicting_role_keyword_uses_source_role",
            test_rewrite_sentence_to_reduce_conflicting_role_keyword_uses_source_role,
        ),
        (
            "reduce_excess_user_keyword_mentions_with_shadowed_keyword_still_hits_max",
            test_reduce_excess_user_keyword_mentions_with_shadowed_keyword_still_hits_max,
        ),
        (
            "title_poll_fact_guard_repairs_margin_direction_phrase",
            test_title_poll_fact_guard_repairs_margin_direction_phrase,
        ),
        (
            "title_poll_fact_guard_repairs_single_percent_binding_mismatch",
            test_title_poll_fact_guard_repairs_single_percent_binding_mismatch,
        ),
        (
            "initial_title_length_discipline_marks_overlong_candidate_for_retry",
            test_initial_title_length_discipline_marks_overlong_candidate_for_retry,
        ),
        (
            "generate_and_validate_title_retries_overlong_candidate_instead_of_fitting",
            test_generate_and_validate_title_retries_overlong_candidate_instead_of_fitting,
        ),
        (
            "generate_and_validate_title_repairs_direct_role_surface_before_scoring",
            test_generate_and_validate_title_repairs_direct_role_surface_before_scoring,
        ),
        (
            "order_role_keyword_intent_anchor_candidates_avoids_recent_variants",
            test_order_role_keyword_intent_anchor_candidates_avoids_recent_variants,
        ),
        (
            "repair_title_for_missing_keywords_preserves_tail_with_intent_anchor",
            test_repair_title_for_missing_keywords_preserves_tail_with_intent_anchor,
        ),
        (
            "repair_title_for_missing_keywords_replaces_generic_future_tail",
            test_repair_title_for_missing_keywords_replaces_generic_future_tail,
        ),
        (
            "compute_similarity_penalty_penalizes_repeated_aggressive_question_frame",
            test_compute_similarity_penalty_penalizes_repeated_aggressive_question_frame,
        ),
        (
            "validate_theme_and_content_uses_title_alignment_not_only_content_overlap",
            test_validate_theme_and_content_uses_title_alignment_not_only_content_overlap,
        ),
        (
            "validate_theme_and_content_uses_surface_topic_fallback_for_sentence_like_topic",
            test_validate_theme_and_content_uses_surface_topic_fallback_for_sentence_like_topic,
        ),
        (
            "validate_theme_and_content_penalizes_unsupported_reversal_frame",
            test_validate_theme_and_content_penalizes_unsupported_reversal_frame,
        ),
        (
            "validate_theme_and_content_penalizes_broken_numeric_subject_frame",
            test_validate_theme_and_content_penalizes_broken_numeric_subject_frame,
        ),
        (
            "validate_theme_and_content_penalizes_misbinding_poll_percent",
            test_validate_theme_and_content_penalizes_misbinding_poll_percent,
        ),
        (
            "validate_theme_and_content_penalizes_single_score_directional_title",
            test_validate_theme_and_content_penalizes_single_score_directional_title,
        ),
        (
            "guard_title_after_editor_rejects_aggressive_question_without_anchor_tail",
            test_guard_title_after_editor_rejects_aggressive_question_without_anchor_tail,
        ),
        (
            "guard_title_after_editor_falls_back_to_previous_topic_aligned_title",
            test_guard_title_after_editor_falls_back_to_previous_topic_aligned_title,
        ),
        (
            "guard_title_after_editor_accepts_direct_role_surface_candidate_when_anchor_is_kept",
            test_guard_title_after_editor_accepts_direct_role_surface_candidate_when_anchor_is_kept,
        ),
        (
            "guard_draft_title_nonfatal_preserves_failed_candidate_without_fallback",
            test_guard_draft_title_nonfatal_preserves_failed_candidate_without_fallback,
        ),
        (
            "guard_draft_title_nonfatal_repairs_mixed_duplicate_particles_in_title_surface",
            test_guard_draft_title_nonfatal_repairs_mixed_duplicate_particles_in_title_surface,
        ),
        (
            "guard_draft_title_nonfatal_repairs_direct_role_surface_candidate_to_anchor_plus_argument",
            test_guard_draft_title_nonfatal_repairs_direct_role_surface_candidate_to_anchor_plus_argument,
        ),
        (
            "guard_draft_title_nonfatal_does_not_return_blocked_candidate_title",
            test_guard_draft_title_nonfatal_does_not_return_blocked_candidate_title,
        ),
        (
            "guard_draft_title_nonfatal_avoids_raw_matchup_possessive_candidate",
            test_guard_draft_title_nonfatal_avoids_raw_matchup_possessive_candidate,
        ),
        (
            "should_carry_recent_titles_from_prior_session_only_when_scope_matches",
            test_should_carry_recent_titles_from_prior_session_only_when_scope_matches,
        ),
        (
            "build_poll_focus_bundle_selects_primary_matchup_and_excludes_party_support",
            test_build_poll_focus_bundle_selects_primary_matchup_and_excludes_party_support,
        ),
        (
            "build_structure_prompt_includes_poll_focus_bundle_rules",
            test_build_structure_prompt_includes_poll_focus_bundle_rules,
        ),
        (
            "build_structure_prompt_includes_style_generation_guard",
            test_build_structure_prompt_includes_style_generation_guard,
        ),
        (
            "build_structure_prompt_excludes_user_specific_forbidden_phrases_without_custom_field",
            test_build_structure_prompt_excludes_user_specific_forbidden_phrases_without_custom_field,
        ),
        (
            "build_structure_prompt_includes_user_specific_forbidden_phrases_from_profile_and_fingerprint",
            test_build_structure_prompt_includes_user_specific_forbidden_phrases_from_profile_and_fingerprint,
        ),
        (
            "build_structure_prompt_keeps_examples_generic_across_users",
            test_build_structure_prompt_keeps_examples_generic_across_users,
        ),
        (
            "structure_agent_heading_body_alignment_score_distinguishes_aligned_and_misaligned_sections",
            test_structure_agent_heading_body_alignment_score_distinguishes_aligned_and_misaligned_sections,
        ),
        (
            "structure_agent_conclusion_alignment_uses_full_paragraphs_for_closing_heading",
            test_structure_agent_conclusion_alignment_uses_full_paragraphs_for_closing_heading,
        ),
        (
            "shared_section_contract_blocks_experience_followed_by_self_certification",
            test_shared_section_contract_blocks_experience_followed_by_self_certification,
        ),
        (
            "shared_section_contract_classifies_showing_citizen_reaction_as_audience_reaction",
            test_shared_section_contract_classifies_showing_citizen_reaction_as_audience_reaction,
        ),
        (
            "shared_section_contract_classifies_structural_audience_reaction_pattern",
            test_shared_section_contract_classifies_structural_audience_reaction_pattern,
        ),
        (
            "shared_section_contract_classifies_citizen_subject_praise_result_as_audience_reaction",
            test_shared_section_contract_classifies_citizen_subject_praise_result_as_audience_reaction,
        ),
        (
            "shared_section_contract_classifies_citizen_subject_recognition_as_audience_reaction",
            test_shared_section_contract_classifies_citizen_subject_recognition_as_audience_reaction,
        ),
        (
            "shared_section_contract_does_not_classify_speaker_commitment_as_audience_reaction",
            test_shared_section_contract_does_not_classify_speaker_commitment_as_audience_reaction,
        ),
        (
            "shared_section_contract_does_not_classify_civic_policy_process_as_audience_reaction",
            test_shared_section_contract_does_not_classify_civic_policy_process_as_audience_reaction,
        ),
        (
            "shared_section_contract_classifies_dynamic_speaker_name_as_speaker_action",
            test_shared_section_contract_classifies_dynamic_speaker_name_as_speaker_action,
        ),
        (
            "shared_section_contract_classifies_dynamic_speaker_name_as_audience_reaction",
            test_shared_section_contract_classifies_dynamic_speaker_name_as_audience_reaction,
        ),
        (
            "shared_section_contract_split_sentences_preserves_decimal_poll_sentence",
            test_shared_section_contract_split_sentences_preserves_decimal_poll_sentence,
        ),
        (
            "shared_section_contract_blocks_duplicate_career_fact_across_sections",
            test_shared_section_contract_blocks_duplicate_career_fact_across_sections,
        ),
        (
            "shared_section_contract_blocks_duplicate_political_career_fact_across_sections",
            test_shared_section_contract_blocks_duplicate_political_career_fact_across_sections,
        ),
        (
            "get_section_contract_sequence_keeps_single_closing_contract",
            test_get_section_contract_sequence_keeps_single_closing_contract,
        ),
        (
            "structure_agent_build_html_soft_repairs_section_role_contract_violation",
            test_structure_agent_build_html_soft_repairs_section_role_contract_violation,
        ),
        (
            "structure_agent_build_html_soft_repairs_multiple_section_role_contract_violations",
            test_structure_agent_build_html_soft_repairs_multiple_section_role_contract_violations,
        ),
        (
            "structure_agent_build_html_cleans_intro_audience_reaction_sentences",
            test_structure_agent_build_html_cleans_intro_audience_reaction_sentences,
        ),
        (
            "structure_agent_build_html_precleans_section_wide_forbidden_before_first_sentence_mismatch",
            test_structure_agent_build_html_precleans_section_wide_forbidden_before_first_sentence_mismatch,
        ),
        (
            "structure_agent_build_html_filters_audience_reaction_when_contract_is_none",
            test_structure_agent_build_html_filters_audience_reaction_when_contract_is_none,
        ),
        (
            "structure_agent_build_html_replaces_low_alignment_heading_with_contract_template",
            test_structure_agent_build_html_replaces_low_alignment_heading_with_contract_template,
        ),
        (
            "content_validator_rejects_section_role_contract_violation",
            test_content_validator_rejects_section_role_contract_violation,
        ),
        (
            "content_validator_rejects_duplicate_career_fact_across_sections",
            test_content_validator_rejects_duplicate_career_fact_across_sections,
        ),
        (
            "structure_agent_attempt_section_level_recovery_replaces_only_target_block",
            test_structure_agent_attempt_section_level_recovery_replaces_only_target_block,
        ),
        (
            "structure_agent_attempt_section_level_recovery_falls_back_to_degraded_block",
            test_structure_agent_attempt_section_level_recovery_falls_back_to_degraded_block,
        ),
        (
            "build_structure_prompt_prioritizes_style_role_examples",
            test_build_structure_prompt_prioritizes_style_role_examples,
        ),
        (
            "build_style_role_priority_summary_uses_actual_examples",
            test_build_style_role_priority_summary_uses_actual_examples,
        ),
        (
            "build_title_prompt_includes_poll_focus_title_rules",
            test_build_title_prompt_includes_poll_focus_title_rules,
        ),
        (
            "validate_theme_and_content_rejects_reversal_lane_with_poll_focus_bundle",
            test_validate_theme_and_content_rejects_reversal_lane_with_poll_focus_bundle,
        ),
        (
            "validate_theme_and_content_rejects_competitor_intent_cliche_tail",
            test_validate_theme_and_content_rejects_competitor_intent_cliche_tail,
        ),
        (
            "validate_theme_and_content_rejects_competitor_intent_generic_future_tail",
            test_validate_theme_and_content_rejects_competitor_intent_generic_future_tail,
        ),
        (
            "validate_theme_and_content_rejects_competitor_intent_name_list_structure",
            test_validate_theme_and_content_rejects_competitor_intent_name_list_structure,
        ),
        (
            "role_keyword_policy_uses_source_fact_per_person",
            test_role_keyword_policy_uses_source_fact_per_person,
        ),
        (
            "calculate_title_quality_score_blocks_direct_role_surface_but_allows_intent_surface",
            test_calculate_title_quality_score_blocks_direct_role_surface_but_allows_intent_surface,
        ),
        (
            "calculate_title_quality_score_repairs_competitor_name_list_to_anchor_plus_argument",
            test_calculate_title_quality_score_repairs_competitor_name_list_to_anchor_plus_argument,
        ),
        (
            "calculate_title_quality_score_rejects_first_person_competitor_title_and_repairs_anchor",
            test_calculate_title_quality_score_rejects_first_person_competitor_title_and_repairs_anchor,
        ),
        (
            "calculate_title_quality_score_rejects_generic_vision_tail_for_competitor_intent",
            test_calculate_title_quality_score_rejects_generic_vision_tail_for_competitor_intent,
        ),
        (
            "calculate_title_quality_score_inferrs_competitor_intent_from_role_keyword_without_policy",
            test_calculate_title_quality_score_inferrs_competitor_intent_from_role_keyword_without_policy,
        ),
        (
            "blocked_role_keyword_is_not_required_in_title_gate_or_prompt",
            test_blocked_role_keyword_is_not_required_in_title_gate_or_prompt,
        ),
        (
            "blocked_role_keyword_can_use_intent_anchor_in_title",
            test_blocked_role_keyword_can_use_intent_anchor_in_title,
        ),
        (
            "ensure_user_keyword_in_subheading_once_skips_role_keyword_anchor",
            test_ensure_user_keyword_in_subheading_once_skips_role_keyword_anchor,
        ),
        (
            "repair_competitor_policy_phrase_once_removes_first_person_name_chain_residue",
            test_repair_competitor_policy_phrase_once_removes_first_person_name_chain_residue,
        ),
        ("scrub_matchup_residue", test_scrub_matchup_residue),
        ("poll_citation_detects_source_input_and_compacts", test_poll_citation_detects_source_input_and_compacts),
        ("poll_citation_compacts_narrative_source_and_ignores_weaker_summary", test_poll_citation_compacts_narrative_source_and_ignores_weaker_summary),
        ("poll_citation_infers_year_month_from_article_timestamp", test_poll_citation_infers_year_month_from_article_timestamp),
        ("poll_citation_uses_plain_event_date_hint_without_header_label", test_poll_citation_uses_plain_event_date_hint_without_header_label),
        ("poll_citation_drops_reporter_signoff", test_poll_citation_drops_reporter_signoff),
        ("finalize_output_forces_poll_citation", test_finalize_output_forces_poll_citation),
        ("finalize_output_reuses_embedded_poll_summary", test_finalize_output_reuses_embedded_poll_summary),
        ("finalize_output_can_defer_terminal_addons", test_finalize_output_can_defer_terminal_addons),
        (
            "finalize_output_strips_keyword_reflection_meta_tail_and_repairs_duplicate_particles",
            test_finalize_output_strips_keyword_reflection_meta_tail_and_repairs_duplicate_particles,
        ),
        (
            "finalize_output_compresses_near_duplicate_event_sentences",
            test_finalize_output_compresses_near_duplicate_event_sentences,
        ),
        (
            "finalize_output_does_not_reduce_final_section_below_three_paragraphs",
            test_finalize_output_does_not_reduce_final_section_below_three_paragraphs,
        ),
        (
            "enforce_keyword_requirements_keeps_speaker_name_without_generic_opponent_fallback",
            test_enforce_keyword_requirements_keeps_speaker_name_without_generic_opponent_fallback,
        ),
        (
            "repair_self_reference_placeholders_once_restores_generic_opponent_placeholder_to_speaker_name",
            test_repair_self_reference_placeholders_once_restores_generic_opponent_placeholder_to_speaker_name,
        ),
        ("repair_competitor_policy_phrase_chain", test_repair_competitor_policy_phrase_chain),
        ("final_sentence_polish_repairs_common_broken_phrases", test_final_sentence_polish_repairs_common_broken_phrases),
        (
            "final_sentence_polish_repairs_duplicate_particles_in_heading_and_body",
            test_final_sentence_polish_repairs_duplicate_particles_in_heading_and_body,
        ),
        ("collect_targeted_sentence_polish_candidates", test_collect_targeted_sentence_polish_candidates),
        ("apply_targeted_sentence_rewrites", test_apply_targeted_sentence_rewrites),
        (
            "collect_targeted_sentence_polish_candidates_marks_ai_alternative_overlay",
            test_collect_targeted_sentence_polish_candidates_marks_ai_alternative_overlay,
        ),
        (
            "apply_targeted_sentence_rewrites_applies_ai_alternative_rule_and_caps_style_count",
            test_apply_targeted_sentence_rewrites_applies_ai_alternative_rule_and_caps_style_count,
        ),
        (
            "apply_global_style_ai_alternative_rules_once_rewrites_all_blocks",
            test_apply_global_style_ai_alternative_rules_once_rewrites_all_blocks,
        ),
        (
            "collect_targeted_sentence_polish_candidates_preserves_jeonim_overlay_slot",
            test_collect_targeted_sentence_polish_candidates_preserves_jeonim_overlay_slot,
        ),
        (
            "collect_targeted_sentence_polish_candidates_detects_beyond_boilerplate_pattern",
            test_collect_targeted_sentence_polish_candidates_detects_beyond_boilerplate_pattern,
        ),
        (
            "repair_subheading_entity_consistency_prefers_speaker_over_low_signal_noise",
            test_repair_subheading_entity_consistency_prefers_speaker_over_low_signal_noise,
        ),
        (
            "repair_subheading_entity_consistency_third_personizes_first_person_heading",
            test_repair_subheading_entity_consistency_third_personizes_first_person_heading,
        ),
        (
            "repair_subheading_entity_consistency_repairs_possessive_heading_after_third_personization",
            test_repair_subheading_entity_consistency_repairs_possessive_heading_after_third_personization,
        ),
        (
            "repair_subheading_entity_consistency_repairs_malformed_matchup_heading",
            test_repair_subheading_entity_consistency_repairs_malformed_matchup_heading,
        ),
        (
            "repair_subheading_entity_consistency_repairs_speaker_role_mismatch_matchup_heading",
            test_repair_subheading_entity_consistency_repairs_speaker_role_mismatch_matchup_heading,
        ),
        (
            "repair_subheading_entity_consistency_dedupes_duplicate_heading_token",
            test_repair_subheading_entity_consistency_dedupes_duplicate_heading_token,
        ),
        (
            "repair_subheading_entity_consistency_dedupes_prefixed_duplicate_heading_token",
            test_repair_subheading_entity_consistency_dedupes_prefixed_duplicate_heading_token,
        ),
        (
            "repair_subheading_entity_consistency_drops_low_signal_matchup_prefix",
            test_repair_subheading_entity_consistency_drops_low_signal_matchup_prefix,
        ),
        (
            "repair_generic_subheading_surface_text_keeps_existing_object_particle",
            test_repair_generic_subheading_surface_text_keeps_existing_object_particle,
        ),
        (
            "repair_generic_subheading_surface_text_repairs_missing_object_particle",
            test_repair_generic_subheading_surface_text_repairs_missing_object_particle,
        ),
        (
            "detect_integrity_gate_issues_allows_valid_matchup_heading_and_sentence",
            test_detect_integrity_gate_issues_allows_valid_matchup_heading_and_sentence,
        ),
        (
            "should_keep_must_include_stance_filters_meta_and_branding_lines",
            test_should_keep_must_include_stance_filters_meta_and_branding_lines,
        ),
        (
            "sanitize_auto_keywords_removes_fragments_and_name_particles",
            test_sanitize_auto_keywords_removes_fragments_and_name_particles,
        ),
        (
            "style_generation_guard_includes_requested_static_forbidden_phrases",
            test_style_generation_guard_includes_requested_static_forbidden_phrases,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_keeps_trailing_self_name_identity_sentence",
            test_rewrite_sentence_to_reduce_keyword_keeps_trailing_self_name_identity_sentence,
        ),
        (
            "build_keyword_replacement_pool_avoids_opponent_fallback_for_bare_person_keyword",
            test_build_keyword_replacement_pool_avoids_opponent_fallback_for_bare_person_keyword,
        ),
        (
            "repair_intent_only_role_keyword_mentions_rewrites_safe_body_sentence",
            test_repair_intent_only_role_keyword_mentions_rewrites_safe_body_sentence,
        ),
        (
            "repair_intent_only_role_keyword_mentions_restores_matchup_fact_role",
            test_repair_intent_only_role_keyword_mentions_restores_matchup_fact_role,
        ),
        (
            "inject_keyword_into_section_does_not_use_reference_template_by_default",
            test_inject_keyword_into_section_does_not_use_reference_template_by_default,
        ),
        (
            "inject_keyword_into_section_skips_broken_poll_residue_paragraph",
            test_inject_keyword_into_section_skips_broken_poll_residue_paragraph,
        ),
        (
            "force_insert_insufficient_keywords_limits_reference_sentence_to_primary_role_keyword",
            test_force_insert_insufficient_keywords_limits_reference_sentence_to_primary_role_keyword,
        ),
        (
            "force_insert_insufficient_keywords_skips_visible_intent_surface_for_conflicting_role_keyword",
            test_force_insert_insufficient_keywords_skips_visible_intent_surface_for_conflicting_role_keyword,
        ),
        (
            "inject_keyword_into_section_skips_intent_reference_fallback_in_body_paragraph",
            test_inject_keyword_into_section_skips_intent_reference_fallback_in_body_paragraph,
        ),
        (
            "inject_keyword_into_section_does_not_splice_role_keyword_into_noun_phrase",
            test_inject_keyword_into_section_does_not_splice_role_keyword_into_noun_phrase,
        ),
        (
            "rewrite_sentence_with_keyword_does_not_match_inside_word",
            test_rewrite_sentence_with_keyword_does_not_match_inside_word,
        ),
        (
            "inject_keyword_into_section_emits_before_after_logs_for_safe_rewrite",
            test_inject_keyword_into_section_emits_before_after_logs_for_safe_rewrite,
        ),
        (
            "force_insert_insufficient_keywords_does_not_append_intent_reference_sentence",
            test_force_insert_insufficient_keywords_does_not_append_intent_reference_sentence,
        ),
        (
            "validate_keyword_insertion_counts_intent_title_toward_role_keyword_requirement",
            test_validate_keyword_insertion_counts_intent_title_toward_role_keyword_requirement,
        ),
        (
            "validate_keyword_insertion_accepts_same_sentence_reflection_but_tracks_exact_shortfall",
            test_validate_keyword_insertion_accepts_same_sentence_reflection_but_tracks_exact_shortfall,
        ),
        (
            "enforce_keyword_requirements_keeps_sentence_coverage_for_intent_role_keyword",
            test_enforce_keyword_requirements_keeps_sentence_coverage_for_intent_role_keyword,
        ),
        (
            "enforce_keyword_requirements_skips_broken_poll_residue_section",
            test_enforce_keyword_requirements_skips_broken_poll_residue_section,
        ),
        (
            "enforce_keyword_requirements_does_not_force_auto_keywords_without_user_keywords",
            test_enforce_keyword_requirements_does_not_force_auto_keywords_without_user_keywords,
        ),
        (
            "enforce_keyword_requirements_reduces_shadowed_short_keyword_even_when_skipped_for_under_min",
            test_enforce_keyword_requirements_reduces_shadowed_short_keyword_even_when_skipped_for_under_min,
        ),
        (
            "enforce_keyword_requirements_does_not_retarget_already_hit_section_for_same_keyword",
            test_enforce_keyword_requirements_does_not_retarget_already_hit_section_for_same_keyword,
        ),
        (
            "repair_keyword_gate_once_logs_snapshot_and_result",
            test_repair_keyword_gate_once_logs_snapshot_and_result,
        ),
        (
            "build_display_keyword_validation_keeps_soft_keyword_spam_risk_visible",
            test_build_display_keyword_validation_keeps_soft_keyword_spam_risk_visible,
        ),
        (
            "calculate_title_quality_score_rejects_truncated_numeric_title",
            test_calculate_title_quality_score_rejects_truncated_numeric_title,
        ),
        (
            "score_title_compliance_fails_closed_on_scoring_exception",
            test_score_title_compliance_fails_closed_on_scoring_exception,
        ),
        (
            "prune_problematic_integrity_fragments_drops_low_signal_name_noun_residue",
            test_prune_problematic_integrity_fragments_drops_low_signal_name_noun_residue,
        ),
        (
            "repair_competitor_policy_phrase_once_removes_extended_candidate_residue_chain",
            test_repair_competitor_policy_phrase_once_removes_extended_candidate_residue_chain,
        ),
        (
            "repair_competitor_policy_phrase_once_removes_matchup_tail_residue_chain",
            test_repair_competitor_policy_phrase_once_removes_matchup_tail_residue_chain,
        ),
        (
            "remove_off_topic_poll_sentences_once_drops_internal_primary_poll_sentence",
            test_remove_off_topic_poll_sentences_once_drops_internal_primary_poll_sentence,
        ),
        (
            "remove_off_topic_poll_sentences_once_drops_party_support_and_internal_scope_drift",
            test_remove_off_topic_poll_sentences_once_drops_party_support_and_internal_scope_drift,
        ),
        (
            "final_sentence_polish_restores_missing_sentence_spacing",
            test_final_sentence_polish_restores_missing_sentence_spacing,
        ),
        (
            "repair_terminal_sentence_spacing_once_restores_missing_spacing",
            test_repair_terminal_sentence_spacing_once_restores_missing_spacing,
        ),
        (
            "normalize_lawmaker_honorifics_once_removes_lawmaker_candidate_chain",
            test_normalize_lawmaker_honorifics_once_removes_lawmaker_candidate_chain,
        ),
        (
            "final_sentence_polish_dedupes_duplicate_poll_explanation_sentence",
            test_final_sentence_polish_dedupes_duplicate_poll_explanation_sentence,
        ),
        (
            "final_sentence_polish_drops_broken_poll_fragment_sentence",
            test_final_sentence_polish_drops_broken_poll_fragment_sentence,
        ),
        (
            "final_sentence_polish_drops_leading_numeric_percent_fragment",
            test_final_sentence_polish_drops_leading_numeric_percent_fragment,
        ),
        (
            "final_sentence_polish_repairs_matchup_result_and_future_role_fragments",
            test_final_sentence_polish_repairs_matchup_result_and_future_role_fragments,
        ),
        (
            "repair_integrity_noise_once_repairs_broken_result_clause_before_blocker",
            test_repair_integrity_noise_once_repairs_broken_result_clause_before_blocker,
        ),
        (
            "final_sentence_polish_dedupes_duplicate_sections_before_style_overlay",
            test_final_sentence_polish_dedupes_duplicate_sections_before_style_overlay,
        ),
        (
            "final_sentence_polish_dedupes_semantically_overlapping_focus_sections",
            test_final_sentence_polish_dedupes_semantically_overlapping_focus_sections,
        ),
        (
            "final_sentence_polish_scrubs_beyond_sincerity_and_duplicate_appeals",
            test_final_sentence_polish_scrubs_beyond_sincerity_and_duplicate_appeals,
        ),
        (
            "final_sentence_polish_drops_simple_negation_frames_from_latest_reference_draft",
            test_final_sentence_polish_drops_simple_negation_frames_from_latest_reference_draft,
        ),
        (
            "final_sentence_polish_drops_extended_simple_negation_frames",
            test_final_sentence_polish_drops_extended_simple_negation_frames,
        ),
        (
            "final_sentence_polish_removes_hoekijeok_phrase_without_dropping_sentence",
            test_final_sentence_polish_removes_hoekijeok_phrase_without_dropping_sentence,
        ),
        (
            "final_sentence_polish_removes_jeokgeukjeok_phrase_without_dropping_sentence",
            test_final_sentence_polish_removes_jeokgeukjeok_phrase_without_dropping_sentence,
        ),
        (
            "final_sentence_polish_drops_negation_frame_extensions",
            test_final_sentence_polish_drops_negation_frame_extensions,
        ),
        (
            "final_sentence_polish_removes_verbose_postpositions_and_link_prefixes",
            test_final_sentence_polish_removes_verbose_postpositions_and_link_prefixes,
        ),
        (
            "final_sentence_polish_drops_translationese_sentences",
            test_final_sentence_polish_drops_translationese_sentences,
        ),
        (
            "final_sentence_polish_rewrites_double_passive_surface",
            test_final_sentence_polish_rewrites_double_passive_surface,
        ),
        (
            "final_sentence_polish_repairs_signature_variant_to_exact_form",
            test_final_sentence_polish_repairs_signature_variant_to_exact_form,
        ),
        (
            "final_sentence_polish_drops_role_keyword_intent_sentence_surface",
            test_final_sentence_polish_drops_role_keyword_intent_sentence_surface,
        ),
        (
            "final_sentence_polish_inserts_identity_signature_when_fingerprint_requires_it",
            test_final_sentence_polish_inserts_identity_signature_when_fingerprint_requires_it,
        ),
        (
            "final_sentence_polish_restores_empty_closing_section_paragraph",
            test_final_sentence_polish_restores_empty_closing_section_paragraph,
        ),
        (
            "final_sentence_polish_drops_soft_self_analysis_and_project_management_sentences",
            test_final_sentence_polish_drops_soft_self_analysis_and_project_management_sentences,
        ),
        (
            "final_sentence_polish_trims_gehumility_clause_but_keeps_main_claim",
            test_final_sentence_polish_trims_gehumility_clause_but_keeps_main_claim,
        ),
        (
            "final_sentence_polish_softens_certainty_phrase_without_dropping_sentence",
            test_final_sentence_polish_softens_certainty_phrase_without_dropping_sentence,
        ),
        (
            "final_sentence_polish_removes_incomplete_trailing_sentence_and_numeric_beyond_variant",
            test_final_sentence_polish_removes_incomplete_trailing_sentence_and_numeric_beyond_variant,
        ),
        (
            "final_sentence_polish_drops_predicateless_fragment_sentence",
            test_final_sentence_polish_drops_predicateless_fragment_sentence,
        ),
        (
            "remove_groundedness_violations_removes_unsupported_comparison_sentence",
            test_remove_groundedness_violations_removes_unsupported_comparison_sentence,
        ),
        (
            "remove_groundedness_violations_removes_direct_opponent_comparison_clause",
            test_remove_groundedness_violations_removes_direct_opponent_comparison_clause,
        ),
        (
            "remove_groundedness_violations_removes_competitor_mid_sentence_role_discussion",
            test_remove_groundedness_violations_removes_competitor_mid_sentence_role_discussion,
        ),
        (
            "remove_groundedness_violations_removes_orphan_boilerplate_sentence",
            test_remove_groundedness_violations_removes_orphan_boilerplate_sentence,
        ),
        (
            "final_sentence_polish_drops_poll_reaction_interpretation_and_recognition_self_narration",
            test_final_sentence_polish_drops_poll_reaction_interpretation_and_recognition_self_narration,
        ),
        (
            "final_sentence_polish_dedupes_repeated_career_fact_sentence",
            test_final_sentence_polish_dedupes_repeated_career_fact_sentence,
        ),
        (
            "final_sentence_polish_dedupes_repeated_political_career_fact_sentence",
            test_final_sentence_polish_dedupes_repeated_political_career_fact_sentence,
        ),
        (
            "final_sentence_polish_applies_cross_section_contract_to_activity_report",
            test_final_sentence_polish_applies_cross_section_contract_to_activity_report,
        ),
        (
            "final_sentence_polish_applies_cross_section_contract_to_policy_proposal",
            test_final_sentence_polish_applies_cross_section_contract_to_policy_proposal,
        ),
        (
            "final_sentence_polish_dedupes_repeated_policy_bundle_sentence",
            test_final_sentence_polish_dedupes_repeated_policy_bundle_sentence,
        ),
        (
            "remove_low_signal_keyword_sentence_once_keeps_poll_fact_sentence_body",
            test_remove_low_signal_keyword_sentence_once_keeps_poll_fact_sentence_body,
        ),
        (
            "force_insert_preferred_exact_keywords_skips_visible_intent_exact_backfill",
            test_force_insert_preferred_exact_keywords_skips_visible_intent_exact_backfill,
        ),
        (
            "reduce_excess_user_keyword_mentions_preserves_poll_fact_sentence_first",
            test_reduce_excess_user_keyword_mentions_preserves_poll_fact_sentence_first,
        ),
        (
            "build_independent_final_title_context_excludes_draft_title_history",
            test_build_independent_final_title_context_excludes_draft_title_history,
        ),
        (
            "build_independent_final_title_context_includes_recent_title_memory_when_provided",
            test_build_independent_final_title_context_includes_recent_title_memory_when_provided,
        ),
        (
            "build_independent_final_title_context_focuses_matchup_content_and_filters_stance_noise",
            test_build_independent_final_title_context_focuses_matchup_content_and_filters_stance_noise,
        ),
    ]
    passed = 0
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
        passed += 1
    print(f"OK {passed}")


if __name__ == "__main__":
    main()
