"""Phase 3: 부수 법률 신호 step-down + body anchor 장형 별칭 매칭 회귀 테스트.

대상 변경:
- title_common.select_title_family: 법률 용어가 부수적으로만 등장할 때
  EXPERT_KNOWLEDGE 부스트를 +6 → +2 로 낮춘다.
- title_scoring._assess_body_anchor_coverage: '계양TV' 같이 한글 어간 +
  라틴 축약 토큰이 본문 앵커로 잡히고 제목엔 장형('계양 테크노밸리') 만
  등장하는 경우, topic/userKeywords 에서 장형을 찾아 substring 매칭을
  성공시킨다.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common.title_common import select_title_family
from agents.common.title_scoring import (
    _assess_body_anchor_coverage,
    _collect_long_form_candidates,
    _token_alias_variants,
)


def test_incidental_legal_term_does_not_dominate_family():
    """법률 용어 1개 + 다짐형 용어 다수 → EXPERT_KNOWLEDGE 보너스 2점만."""
    params = {
        "topic": "테크노밸리 2단계, 숙원 사업 완성",
        "stanceText": (
            "저는 앞장서서 이 숙원 사업을 끝까지 추진하겠습니다. "
            "시의회와 함께 조례 개정도 뒷받침하고, 주민 약속을 지키며 "
            "끝까지 완성해 나가겠습니다."
        ),
        "contentPreview": "",
        "category": "daily-communication",
    }
    result = select_title_family(params)
    expert_reasons = result["reasons"].get("EXPERT_KNOWLEDGE", [])
    assert any("부수" in r for r in expert_reasons), (
        f"기대: 부수 배지가 reason 에 찍혀야 함. 실제 reasons={expert_reasons}"
    )
    # SLOGAN_COMMITMENT 가 EXPERT_KNOWLEDGE 보다 높은 점수여야 한다 — 다짐형이 주 톤.
    expert_score = result["scores"].get("EXPERT_KNOWLEDGE", 0)
    slogan_score = result["scores"].get("SLOGAN_COMMITMENT", 0)
    assert slogan_score > expert_score, (
        f"SLOGAN_COMMITMENT={slogan_score} 가 EXPERT_KNOWLEDGE={expert_score} "
        f"보다 커야 함. scores={result['scores']}"
    )


def test_dominant_legal_terms_still_boost_expert_knowledge():
    """법률 용어 3회 이상이면 기존과 같이 +6 점."""
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


def test_token_alias_variants_extracts_long_form_from_topic():
    """한글+라틴 축약 토큰이 topic 장형과 연결된다."""
    variants = _token_alias_variants(
        "계양TV",
        ["계양 테크노밸리 2단계", "기타 키워드"],
    )
    assert "계양TV" in variants
    assert "계양 테크노밸리 2단계" in variants


def test_token_alias_variants_plain_token_unchanged():
    """일반 토큰은 변형 없이 원본만 반환."""
    variants = _token_alias_variants("기본소득", ["민생 기본소득"])
    assert variants == ["기본소득"]


def test_body_anchor_alias_resolves_abbreviation_to_title_long_form():
    """body anchor 가 'XTV' 이고 제목이 'X 테크노밸리' 여도 매칭 성공."""
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": ["계양TV"],
            "policy": [],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {
            "topic": "계양 테크노밸리 2단계, 숙원 사업 완성",
            "contentPreview": "...",
            "userKeywords": [],
        }
        result = _assess_body_anchor_coverage(
            "계양 테크노밸리 2단계, 숙원 사업 완성", params
        )
        assert result.get("passed") is True, f"결과: {result}"
        assert "institution" in (result.get("hitBuckets") or [])
        hit_tokens = result.get("hitTokens") or []
        assert any("계양TV" in t and "→" in t for t in hit_tokens), (
            f"별칭 해석이 hitTokens 에 기록돼야 함. hitTokens={hit_tokens}"
        )
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_original_token_match_still_works():
    """장형 변형이 없어도 원본 토큰이 제목에 있으면 매칭된다."""
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
        assert "institution" in (result.get("hitBuckets") or [])
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_fails_when_no_variant_matches():
    """장형 후보가 있어도 제목에 없으면 여전히 실패."""
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


def test_collect_long_form_candidates_splits_topic():
    """topic 을 구분자 기준으로 잘라 장형 후보로 만든다."""
    params = {
        "topic": "계양 테크노밸리 2단계, 숙원 사업 완성",
        "userKeywords": ["계양 테크노밸리"],
    }
    candidates = _collect_long_form_candidates(params)
    joined = " | ".join(candidates)
    assert "계양 테크노밸리 2단계" in joined
    assert "계양 테크노밸리" in candidates
