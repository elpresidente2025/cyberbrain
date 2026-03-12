from __future__ import annotations

import asyncio
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common.poll_citation import build_poll_citation_text
from agents.common.role_keyword_policy import build_role_keyword_policy
from agents.common.title_generation import (
    _assess_initial_title_length_discipline,
    build_title_prompt,
    calculate_title_quality_score,
    generate_and_validate_title,
    validate_theme_and_content,
)
from handlers.generate_posts import (
    _apply_final_sentence_polish_once,
    _apply_targeted_sentence_rewrites,
    _build_independent_final_title_context,
    _collect_targeted_sentence_polish_candidates,
    _ensure_user_keyword_in_subheading_once,
    _guard_draft_title_nonfatal,
    _guard_title_after_editor,
    _repair_intent_only_role_keyword_mentions_once,
    _repair_competitor_policy_phrase_once,
    _repair_terminal_sentence_spacing_once,
    _prune_problematic_integrity_fragments,
    _repair_subheading_entity_consistency_once,
    _scrub_suspicious_poll_residue_text,
)
from services.posts.poll_fact_guard import (
    build_poll_matchup_fact_table,
    enforce_poll_fact_consistency,
)
from services.posts.output_formatter import finalize_output
from services.posts.validation import (
    _count_user_keyword_exact_non_overlap,
    _inject_keyword_into_section,
    _reduce_excess_user_keyword_mentions,
    _rewrite_sentence_to_reduce_keyword,
    enforce_keyword_requirements,
    force_insert_preferred_exact_keywords,
    force_insert_insufficient_keywords,
    validate_keyword_insertion,
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
    assert int(result["history"][0]["score"] or 0) == 0
    assert int(result["history"][0]["initialLengthPenalty"] or 0) >= 28


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


def test_guard_title_after_editor_keeps_allowed_aggressive_question_frame() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    restored, info = _guard_title_after_editor(
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

    assert restored == "주진우 부산시장 출마? 왜 이재성에게 흔들리나"
    assert info["accepted"] is True
    assert info["source"] == "candidate"


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

    assert "양자대결" in restored
    assert "이재성이" in restored
    assert info["source"] == "previous"


def test_guard_title_after_editor_repairs_direct_role_surface_to_intent() -> None:
    role_keyword_policy = build_role_keyword_policy(
        ["주진우", "주진우 부산시장"],
        person_roles={"주진우": "국회의원"},
        source_texts=[
            "부산시장 양자대결에서 주진우 의원과 이재성 전 위원장이 맞붙었다.",
        ],
    )
    restored, info = _guard_title_after_editor(
        candidate_title="주진우 부산시장, 양자대결서 드러난 이재성 가능성",
        previous_title="",
        topic="부산시장 선거 양자대결에서 주진우보다 우세를 점한 이재성의 가능성",
        content=(
            "이재성은 부산시장 양자대결에서 주진우 의원보다 앞서며 경쟁력과 가능성을 보였다."
        ),
        user_keywords=["주진우", "주진우 부산시장"],
        full_name="이재성",
        category="current-affairs",
        status="campaign",
        context_analysis={},
        role_keyword_policy=role_keyword_policy,
    )

    assert "주진우 부산시장 출마?" in restored
    assert "이재성 가능성" in restored
    assert info["accepted"] is True
    assert str(info["source"]).startswith("candidate_role_policy_repair")


def test_guard_draft_title_nonfatal_downgrades_failure_to_previous_fallback() -> None:
    restored, info = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title="부산 선거",
        previous_title="이재성, 양자대결서 드러난 가능성",
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

    assert restored == "이재성, 양자대결서 드러난 가능성"
    assert info["accepted"] is True
    assert info["nonFatal"] is True
    assert info["source"] == "previous_fallback"
    assert info["phase"] == "draft_output"


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
    valid = calculate_title_quality_score("주진우 부산시장 출마? 양자대결서 이재성 가능성", params)
    aggressive = calculate_title_quality_score("주진우 부산시장 출마? 왜 이재성에게 흔들리나", params)

    assert invalid["passed"] is False
    assert int(invalid["score"] or 0) == 0
    assert "출마" in str((invalid.get("suggestions") or [""])[0] or "")
    assert int(valid["score"] or 0) > 0
    assert aggressive["passed"] is True
    assert int(((aggressive.get("breakdown") or {}).get("topicMatch") or {}).get("score") or 0) >= 15


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

    assert result["passed"] is True
    assert int(result["score"] or 0) > 0
    assert 'priority="2" value="조국 부산시장"' not in prompt
    assert '두 검색어("조국 대표", "조국 부산시장")' not in prompt
    assert 'keyword="조국 부산시장" mode="blocked"' in prompt


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


def test_repair_intent_only_role_keyword_mentions_skips_matchup_sentence() -> None:
    content = "<p>주진우 부산시장과의 가상대결에서는 31.7% 대 30.3%로 나타났습니다.</p>"
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

    assert repaired.get("edited") is False
    assert str(repaired.get("content") or "") == content


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

    assert "온라인에서는 '주진우 부산시장' 검색어도 함께 거론되고 있습니다." in updated
    assert "전재수 국회의원" not in updated
    assert updated.count("검색어도 함께 거론되고 있습니다.") == 1


def test_force_insert_insufficient_keywords_uses_intent_surface_for_conflicting_role_keyword() -> None:
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

    assert "온라인에서는 주진우 부산시장 출마 가능성도 함께 거론됩니다." in updated


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


def test_enforce_keyword_requirements_prefers_one_exact_match_for_multi_token_keyword() -> None:
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

    assert "주진우 부산시장" in updated
    assert int(info.get("exclusiveCount") or 0) >= 1
    assert int(info.get("exactShortfall") or 0) == 0


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


def test_force_insert_preferred_exact_keywords_backfills_one_exact_match() -> None:
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

    assert "주진우 부산시장" in updated
    assert int(info.get("exactShortfall") or 0) == 0


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


def main() -> None:
    tests = [
        ("rewrite_excess_keyword_sentence", test_rewrite_excess_keyword_sentence),
        (
            "rewrite_sentence_to_reduce_role_keyword_avoids_related_issue_fragment",
            test_rewrite_sentence_to_reduce_role_keyword_avoids_related_issue_fragment,
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
            "initial_title_length_discipline_marks_overlong_candidate_for_retry",
            test_initial_title_length_discipline_marks_overlong_candidate_for_retry,
        ),
        (
            "generate_and_validate_title_retries_overlong_candidate_instead_of_fitting",
            test_generate_and_validate_title_retries_overlong_candidate_instead_of_fitting,
        ),
        (
            "validate_theme_and_content_uses_title_alignment_not_only_content_overlap",
            test_validate_theme_and_content_uses_title_alignment_not_only_content_overlap,
        ),
        (
            "guard_title_after_editor_keeps_allowed_aggressive_question_frame",
            test_guard_title_after_editor_keeps_allowed_aggressive_question_frame,
        ),
        (
            "guard_title_after_editor_falls_back_to_previous_topic_aligned_title",
            test_guard_title_after_editor_falls_back_to_previous_topic_aligned_title,
        ),
        (
            "guard_title_after_editor_repairs_direct_role_surface_to_intent",
            test_guard_title_after_editor_repairs_direct_role_surface_to_intent,
        ),
        (
            "guard_draft_title_nonfatal_downgrades_failure_to_previous_fallback",
            test_guard_draft_title_nonfatal_downgrades_failure_to_previous_fallback,
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
            "blocked_role_keyword_is_not_required_in_title_gate_or_prompt",
            test_blocked_role_keyword_is_not_required_in_title_gate_or_prompt,
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
        ("poll_citation_drops_reporter_signoff", test_poll_citation_drops_reporter_signoff),
        ("finalize_output_forces_poll_citation", test_finalize_output_forces_poll_citation),
        ("finalize_output_reuses_embedded_poll_summary", test_finalize_output_reuses_embedded_poll_summary),
        ("repair_competitor_policy_phrase_chain", test_repair_competitor_policy_phrase_chain),
        ("final_sentence_polish_repairs_common_broken_phrases", test_final_sentence_polish_repairs_common_broken_phrases),
        ("collect_targeted_sentence_polish_candidates", test_collect_targeted_sentence_polish_candidates),
        ("apply_targeted_sentence_rewrites", test_apply_targeted_sentence_rewrites),
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
            "repair_intent_only_role_keyword_mentions_rewrites_safe_body_sentence",
            test_repair_intent_only_role_keyword_mentions_rewrites_safe_body_sentence,
        ),
        (
            "repair_intent_only_role_keyword_mentions_skips_matchup_sentence",
            test_repair_intent_only_role_keyword_mentions_skips_matchup_sentence,
        ),
        (
            "inject_keyword_into_section_does_not_use_reference_template_by_default",
            test_inject_keyword_into_section_does_not_use_reference_template_by_default,
        ),
        (
            "force_insert_insufficient_keywords_limits_reference_sentence_to_primary_role_keyword",
            test_force_insert_insufficient_keywords_limits_reference_sentence_to_primary_role_keyword,
        ),
        (
            "force_insert_insufficient_keywords_uses_intent_surface_for_conflicting_role_keyword",
            test_force_insert_insufficient_keywords_uses_intent_surface_for_conflicting_role_keyword,
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
            "enforce_keyword_requirements_prefers_one_exact_match_for_multi_token_keyword",
            test_enforce_keyword_requirements_prefers_one_exact_match_for_multi_token_keyword,
        ),
        (
            "calculate_title_quality_score_rejects_truncated_numeric_title",
            test_calculate_title_quality_score_rejects_truncated_numeric_title,
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
            "final_sentence_polish_restores_missing_sentence_spacing",
            test_final_sentence_polish_restores_missing_sentence_spacing,
        ),
        (
            "repair_terminal_sentence_spacing_once_restores_missing_spacing",
            test_repair_terminal_sentence_spacing_once_restores_missing_spacing,
        ),
        (
            "force_insert_preferred_exact_keywords_backfills_one_exact_match",
            test_force_insert_preferred_exact_keywords_backfills_one_exact_match,
        ),
        (
            "reduce_excess_user_keyword_mentions_preserves_poll_fact_sentence_first",
            test_reduce_excess_user_keyword_mentions_preserves_poll_fact_sentence_first,
        ),
        (
            "build_independent_final_title_context_excludes_draft_title_history",
            test_build_independent_final_title_context_excludes_draft_title_history,
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
