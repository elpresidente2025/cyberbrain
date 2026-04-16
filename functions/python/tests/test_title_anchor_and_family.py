"""제목 파이프라인 복합 패널티 수정 회귀 테스트.

대상 변경:
- title_hook_quality._slot_token_used_in_title: compact + stem stripping 으로
  "테크노밸리 사업" → stem "테크노밸리" 가 제목 substring 에 매칭.
- title_scoring._assess_body_anchor_coverage: _slot_token_used_in_title 사용.
- title_keywords._topic_keyword_matches_text: stem fallback 추가.
- title_common.detect_content_type / select_title_family: 질문 톤이 법률 어휘보다 우선.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common.title_common import select_title_family, detect_content_type
from agents.common.title_scoring import _assess_body_anchor_coverage
from agents.common.title_hook_quality import _slot_token_used_in_title
from agents.common.title_keywords import _topic_keyword_matches_text


# ---------------------------------------------------------------------------
# _slot_token_used_in_title — stem stripping
# ---------------------------------------------------------------------------

def test_slot_stem_strips_policy_suffix():
    """'테크노밸리 사업' stem '테크노밸리' 가 제목에 매칭."""
    assert _slot_token_used_in_title(
        "계양 테크노밸리, 2단계 지정 왜 늦어지나?",
        "테크노밸리 사업",
    )


def test_slot_stem_strips_institution_suffix():
    """'주민참여예산시민위원회' stem '주민참여예산시민' 이 제목에 매칭."""
    assert _slot_token_used_in_title(
        "주민참여예산시민 제도 안내",
        "주민참여예산시민위원회",
    )


def test_slot_exact_match_still_works():
    """접미사 없는 토큰은 그대로 exact substring 매칭."""
    assert _slot_token_used_in_title("서울시의회 의정보고", "서울시의회")


def test_slot_no_false_positive_on_short_stem():
    """stem 이 2자 미만이면 매칭하지 않음."""
    assert not _slot_token_used_in_title("아무 제목", "가사업")


def test_slot_compact_ignores_whitespace():
    """토큰과 제목 모두 공백 제거 후 비교."""
    assert _slot_token_used_in_title(
        "취득세 감면 조례 개정",
        "취득세감면조례",
    )


# ---------------------------------------------------------------------------
# _topic_keyword_matches_text — stem fallback
# ---------------------------------------------------------------------------

def test_topic_keyword_stem_fallback():
    """compact match 실패해도 stem fallback 이 잡아준다."""
    assert _topic_keyword_matches_text(
        "테크노밸리사업",
        "계양 테크노밸리, 2단계 지정",
    )


def test_topic_keyword_exact_match_still_works():
    assert _topic_keyword_matches_text("계양", "계양 테크노밸리")


# ---------------------------------------------------------------------------
# _assess_body_anchor_coverage — _slot_token_used_in_title 사용
# ---------------------------------------------------------------------------

def test_body_anchor_stem_matching_passes():
    """policy 토큰 '테크노밸리 사업' 이 stem 으로 제목에 매칭 성공."""
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": [],
            "policy": ["테크노밸리 사업"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {
            "topic": "계양 테크노밸리 2단계",
            "contentPreview": "...",
        }
        result = _assess_body_anchor_coverage(
            "계양 테크노밸리, 2단계 지정 왜 늦어지나?", params
        )
        assert result.get("passed") is True, f"결과: {result}"
        assert "policy" in (result.get("hitBuckets") or [])
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_exact_token_still_works():
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": ["서울시의회"],
            "policy": [],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {"topic": "지역 현안", "contentPreview": "..."}
        result = _assess_body_anchor_coverage(
            "서울시의회 의정보고, 주민과의 약속", params
        )
        assert result.get("passed") is True
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_fails_when_no_match():
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": [],
            "policy": ["기본소득 확대"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {"topic": "다른 주제", "contentPreview": "..."}
        result = _assess_body_anchor_coverage("아주 일반적인 제목입니다", params)
        assert result.get("passed") is False
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


# ---------------------------------------------------------------------------
# Family classifier — 질문 톤이 법률 어휘보다 우선
# ---------------------------------------------------------------------------

def test_question_tone_prevents_expert_knowledge_prior():
    """질문 + 법률 어휘 → detect_content_type 이 EXPERT_KNOWLEDGE 안 돼야."""
    content = "조례 개정이 필요하다. 왜 지금 추진해야 하는가?"
    result = detect_content_type(content, "daily-communication")
    assert result != "EXPERT_KNOWLEDGE", f"질문 톤인데 EXPERT_KNOWLEDGE 반환: {result}"


def test_question_tone_demotes_legal_boost():
    """질문형 source 에 법률 어휘 있어도 EXPERT_KNOWLEDGE 가 낮게 부스트."""
    params = {
        "topic": "테크노밸리 2단계 지정, 왜 늦어지나?",
        "stanceText": (
            "시의회와 함께 조례 개정도 뒷받침해야 합니다. "
            "이 제도를 왜 미루는 것인가? 어떻게 해결할 것인가?"
        ),
        "contentPreview": "",
        "category": "daily-communication",
    }
    result = select_title_family(params)
    expert_score = result["scores"].get("EXPERT_KNOWLEDGE", 0)
    question_score = result["scores"].get("QUESTION_ANSWER", 0)
    assert question_score > expert_score, (
        f"QUESTION_ANSWER={question_score} > EXPERT_KNOWLEDGE={expert_score} 여야 함. "
        f"scores={result['scores']}"
    )


def test_dominant_legal_no_question_still_expert():
    """질문 없이 법률 용어 3회+ → 여전히 EXPERT_KNOWLEDGE +6."""
    params = {
        "topic": "조례 개정안 발의",
        "stanceText": "이번 조례 개정안은 제도 개선을 위한 법률 정비다. 법안 통과를 목표로 한다.",
        "category": "policy-proposal",
    }
    result = select_title_family(params)
    expert_reasons = result["reasons"].get("EXPERT_KNOWLEDGE", [])
    assert any("주요" in r for r in expert_reasons), (
        f"기대: 주요 배지. reasons={expert_reasons}"
    )
    assert result["scores"].get("EXPERT_KNOWLEDGE", 0) >= 6


def test_incidental_legal_no_question_gets_minor_boost():
    """질문 없고 법률 1회 + 다짐형 다수 → 부수 +2."""
    params = {
        "topic": "숙원 사업 완성",
        "stanceText": (
            "저는 앞장서서 추진하겠습니다. 조례도 뒷받침하고, "
            "약속을 지키며 완성해 나가겠습니다."
        ),
        "contentPreview": "",
        "category": "daily-communication",
    }
    result = select_title_family(params)
    expert_reasons = result["reasons"].get("EXPERT_KNOWLEDGE", [])
    assert any("부수" in r for r in expert_reasons), (
        f"기대: 부수 배지. reasons={expert_reasons}"
    )
