"""H2 AEO 확장 단위 테스트 (PR 4 step 4).

대상:
- agents.common.h2_planning: classify_section_intent, detect_answer_type,
  build_target_keyword_canonical, build_descriptor_pool, assign_h2_entity_slots
- agents.common.h2_scoring: detect_emotion_appeal, count_entity_distribution,
  detect_sibling_suffix_overlap, score_h2_aeo (H2_HARD_FAIL_ISSUES 포함)

CLAUDE.md 범용성 원칙: 사용자/지역명은 placeholder(`홍길동`, `샘플구`)만 사용.
"""
from __future__ import annotations

import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.h2_planning import (
    AEO_ANSWER_TYPES,
    AEO_INTENT_KINDS,
    assign_h2_entity_slots,
    build_descriptor_pool,
    build_target_keyword_canonical,
    classify_section_intent,
    detect_answer_type,
)
from agents.common.h2_planning import extract_user_role, localize_user_role
from agents.common.h2_repair import enforce_anchor_cap, enforce_user_role_lock
from agents.common.h2_scoring import (
    H2_AEO_ADVISORIES,
    H2_HARD_FAIL_ISSUES,
    compute_anchor_cap,
    count_entity_distribution,
    detect_emotion_appeal,
    detect_sibling_suffix_overlap,
    score_h2,
    score_h2_aeo,
)


# ---------------------------------------------------------------------------
# classify_section_intent
# ---------------------------------------------------------------------------

class TestClassifySectionIntent:
    def test_default_is_info(self) -> None:
        assert classify_section_intent("어제 이런 일이 있었습니다.") == "info"

    def test_cmp_marker(self) -> None:
        text = "후보 A와 후보 B의 가상대결 결과는 박빙이었습니다."
        assert classify_section_intent(text) == "cmp"

    def test_cmp_numeric_pair(self) -> None:
        text = "지지율은 42.5% 대 38.1% 로 나타났습니다."
        assert classify_section_intent(text) == "cmp"

    def test_tx_marker(self) -> None:
        text = "신청 절차는 다음과 같습니다. 첫째, 서류를 준비합니다."
        assert classify_section_intent(text) == "tx"

    def test_nav_marker(self) -> None:
        text = "그의 이력과 활동 경력을 정리해 봅니다."
        assert classify_section_intent(text) == "nav"

    def test_returns_member_of_intent_kinds(self) -> None:
        for text in ("문단입니다", "신청 방법", "차이가 있다", "이력 소개"):
            assert classify_section_intent(text) in AEO_INTENT_KINDS


# ---------------------------------------------------------------------------
# detect_answer_type
# ---------------------------------------------------------------------------

class TestDetectAnswerType:
    def test_default_is_question_form(self) -> None:
        assert detect_answer_type("짧은 한 줄.") == "question-form"

    def test_list_marker(self) -> None:
        text = "방안은 다음과 같습니다. 첫째, A 입니다. 둘째, B 입니다. 셋째, C 입니다."
        assert detect_answer_type(text) == "declarative-list"

    def test_list_numeric_count(self) -> None:
        text = "3가지 핵심 원칙이 있습니다. 이를 단계별로 살펴봅니다."
        assert detect_answer_type(text) == "declarative-list"

    def test_fact_requires_three_sentences(self) -> None:
        text = "A 입니다. B 입니다. C 했습니다. D 됩니다."
        assert detect_answer_type(text) == "declarative-fact"

    def test_single_sentence_is_not_fact(self) -> None:
        text = "오늘은 뜻깊은 날을 맞아 다시 한번 다짐합니다."
        assert detect_answer_type(text) == "question-form"

    def test_returns_member_of_answer_types(self) -> None:
        for text in ("짧은 글", "첫째 둘째 셋째", "A 입니다 B 합니다 C 됩니다"):
            assert detect_answer_type(text) in AEO_ANSWER_TYPES


# ---------------------------------------------------------------------------
# build_target_keyword_canonical
# ---------------------------------------------------------------------------

class TestBuildTargetKeywordCanonical:
    def test_preferred_wins(self) -> None:
        result = build_target_keyword_canonical(
            preferred_keyword="청년 정책",
            full_name="홍길동",
            user_keywords=["일자리"],
        )
        assert result == "청년 정책"

    def test_falls_back_to_name(self) -> None:
        result = build_target_keyword_canonical(
            preferred_keyword="",
            full_name="홍길동",
            user_keywords=[],
        )
        assert result == "홍길동"

    def test_falls_back_to_user_keyword(self) -> None:
        result = build_target_keyword_canonical(
            preferred_keyword="",
            full_name="",
            user_keywords=["교통 해법"],
        )
        assert result == "교통 해법"

    def test_empty_inputs_return_empty(self) -> None:
        assert build_target_keyword_canonical() == ""


# ---------------------------------------------------------------------------
# build_descriptor_pool
# ---------------------------------------------------------------------------

class TestBuildDescriptorPool:
    def test_profile_keys_extracted(self) -> None:
        pool = build_descriptor_pool(
            full_name="홍길동",
            full_region="샘플시 샘플구",
            profile={
                "currentRole": "청년정책연구원",
                "identity": "정책 실무자",
                "tagline": "지역 활동가",
            },
            role_facts={},
        )
        assert "청년정책연구원" in pool
        assert "정책 실무자" in pool
        assert "지역 활동가" in pool

    def test_role_facts_for_self(self) -> None:
        pool = build_descriptor_pool(
            full_name="홍길동",
            full_region="",
            profile={},
            role_facts={"홍길동": "독립운동가 후손"},
        )
        # 다단어 descriptor 도 분리되지 않아야 함
        assert "독립운동가 후손" in pool

    def test_excludes_full_name(self) -> None:
        pool = build_descriptor_pool(
            full_name="홍길동",
            profile={"currentRole": "홍길동"},
        )
        assert "홍길동" not in pool

    def test_region_based_positioning(self) -> None:
        pool = build_descriptor_pool(
            full_name="홍길동",
            full_region="샘플시 샘플구",
            profile={},
        )
        assert any("샘플구" in item for item in pool)

    def test_max_items_cap(self) -> None:
        pool = build_descriptor_pool(
            full_name="홍길동",
            profile={
                "currentRole": "역할1·역할2·역할3·역할4·역할5·역할6·역할7·역할8",
            },
            max_items=4,
        )
        assert len(pool) <= 4

    def test_excludes_other_person_role_facts(self) -> None:
        # Why: role_facts 는 소스 기사에서 추출된 다인물 역할 맵이다.
        #      본인("홍길동") 외의 역할이 descriptor 로 들어가면 H2 에
        #      엉뚱한 직책이 스탬핑된다. 본인 역할만 허용.
        pool = build_descriptor_pool(
            full_name="홍길동",
            full_region="샘플시 샘플구",
            profile={"currentRole": "시의원"},
            role_facts={
                "홍길동": "시의원",
                "아무개": "국회의원",
                "누군가": "위원장",
            },
        )
        assert "시의원" in pool
        assert "국회의원" not in pool
        assert "위원장" not in pool


# ---------------------------------------------------------------------------
# assign_h2_entity_slots
# ---------------------------------------------------------------------------

class TestAssignH2EntitySlots:
    def test_n3_one_anchor(self) -> None:
        slots = assign_h2_entity_slots(
            3, full_name="홍길동", descriptor_pool=["d1", "d2", "d3"]
        )
        assert slots == ["홍길동", "d1", "d2"]

    def test_n4_one_anchor(self) -> None:
        slots = assign_h2_entity_slots(
            4, full_name="홍길동", descriptor_pool=["d1", "d2", "d3"]
        )
        assert slots[0] == "홍길동"
        assert slots.count("홍길동") == 1
        assert all(s for s in slots)

    def test_n5_allows_second_anchor(self) -> None:
        slots = assign_h2_entity_slots(
            5, full_name="홍길동", descriptor_pool=["d1", "d2", "d3"]
        )
        assert slots[0] == "홍길동"
        assert slots.count("홍길동") == 2

    def test_anchor_ratio_floor(self) -> None:
        # N=4, ratio=0.5 → cap=2 이지만 N<5 라 second anchor 허용 안 함
        slots = assign_h2_entity_slots(
            4, full_name="홍길동", descriptor_pool=["d1", "d2", "d3"]
        )
        assert slots.count("홍길동") == 1

    def test_empty_pool_falls_back_to_name(self) -> None:
        slots = assign_h2_entity_slots(
            3, full_name="홍길동", descriptor_pool=[]
        )
        assert slots == ["홍길동", "홍길동", "홍길동"]

    def test_no_name_returns_descriptors(self) -> None:
        slots = assign_h2_entity_slots(
            3, full_name="", descriptor_pool=["d1", "d2"]
        )
        assert "" not in slots
        assert all(s in {"d1", "d2"} for s in slots)


# ---------------------------------------------------------------------------
# detect_emotion_appeal — hard-fail trigger
# ---------------------------------------------------------------------------

class TestDetectEmotionAppeal:
    @pytest.mark.parametrize(
        "heading",
        [
            "함께 더 나은 미래로 나아가자",
            "청년 정책을 위한 길",
            "변화는 우리의 손에서 시작됩니다",
            "지금 이 순간 결단해야 합니다",
            "약속이 없었다면 시작도 없었다",
            "반드시 해내겠다고 약속드립니다",
        ],
    )
    def test_emotion_patterns_detected(self, heading: str) -> None:
        assert detect_emotion_appeal(heading) is not None

    def test_neutral_heading_passes(self) -> None:
        assert detect_emotion_appeal("청년 일자리 3대 핵심 정책 정리") is None

    def test_emotion_label_in_hard_fail_set(self) -> None:
        assert "H2_EMOTION_APPEAL" in H2_HARD_FAIL_ISSUES


# ---------------------------------------------------------------------------
# count_entity_distribution
# ---------------------------------------------------------------------------

class TestCountEntityDistribution:
    def test_distribution_split(self) -> None:
        headings = [
            "홍길동, 청년 정책의 첫 단추",
            "지역 활동가가 본 교통 문제",
            "정책 실무자 시각의 일자리 해법",
            "기타 일반 정리 글",
        ]
        result = count_entity_distribution(
            headings,
            full_name="홍길동",
            descriptor_pool=["지역 활동가", "정책 실무자"],
        )
        assert result == {"full_name": 1, "descriptor": 2, "neither": 1}

    def test_empty_inputs(self) -> None:
        result = count_entity_distribution([], full_name="홍길동")
        assert result == {"full_name": 0, "descriptor": 0, "neither": 0}


# ---------------------------------------------------------------------------
# detect_sibling_suffix_overlap
# ---------------------------------------------------------------------------

class TestDetectSiblingSuffixOverlap:
    def test_identical_tail_bigram(self) -> None:
        headings = [
            "청년 일자리 핵심 정리",
            "지역 교통 핵심 정리",
        ]
        overlaps = detect_sibling_suffix_overlap(headings)
        assert any("핵심 정리" in (token if isinstance(token, str) else "") for token, _ in overlaps)

    def test_penultimate_token_overlap(self) -> None:
        headings = [
            "지역 청년 정책 변화",
            "지역 청년 정책 실현",
        ]
        overlaps = detect_sibling_suffix_overlap(headings)
        assert any(token == "정책" for token, _ in overlaps)

    def test_no_overlap(self) -> None:
        headings = [
            "청년 일자리 첫 단추",
            "교통 혼잡 두 가지 해법",
        ]
        assert detect_sibling_suffix_overlap(headings) == []


# ---------------------------------------------------------------------------
# score_h2_aeo
# ---------------------------------------------------------------------------

class TestScoreH2Aeo:
    def test_advisory_set_membership(self) -> None:
        for issue in (
            "H2_NO_SUBJECT_ENTITY",
            "H2_NO_QUESTION_FORM",
            "H2_SHORT_LENGTH",
            "H2_LONG_LENGTH",
            "H2_KEYWORD_STAMP_WARNING",
            "H2_ENTITY_ANCHOR_MISSING",
            "H2_SIBLING_SUFFIX_OVERLAP",
        ):
            assert issue in H2_AEO_ADVISORIES

    def test_perfect_question_with_entity(self) -> None:
        result = score_h2_aeo(
            "홍길동 청년 정책, 어떻게 시작될까요?",
            siblings=["지역 활동가가 본 교통 해법", "정책 실무자 5대 약속"],
            full_name="홍길동",
            descriptor_pool=["지역 활동가", "정책 실무자"],
            body_first_sentence="청년 정책의 시작점을 살펴봅니다.",
            target_keyword_canonical="청년 정책",
            section_index=0,
            section_count=3,
        )
        assert result["score"] >= 0.85
        assert "H2_NO_QUESTION_FORM" not in result["issues"]
        assert "H2_NO_SUBJECT_ENTITY" not in result["issues"]

    def test_no_entity_no_question(self) -> None:
        result = score_h2_aeo(
            "그저 평범한 정책 정리 모음",
            siblings=[],
            full_name="홍길동",
            descriptor_pool=["지역 활동가"],
            section_index=0,
            section_count=1,
        )
        assert "H2_NO_SUBJECT_ENTITY" in result["issues"]
        assert "H2_NO_QUESTION_FORM" in result["issues"]

    def test_keyword_stamping_warning(self) -> None:
        # 모든 H2 가 fullName 사용 → cap 초과
        siblings = [
            "홍길동 청년 정책 첫 단추",
            "홍길동 교통 정책 핵심",
            "홍길동 일자리 5대 약속",
        ]
        result = score_h2_aeo(
            "홍길동 지역 정책 약속",
            siblings=siblings,
            full_name="홍길동",
            descriptor_pool=["지역 활동가"],
            section_index=3,
            section_count=4,
        )
        assert "H2_KEYWORD_STAMP_WARNING" in result["issues"]

    def test_entity_anchor_missing(self) -> None:
        siblings = [
            "정책 정리 한눈에",
            "교통 해법 핵심",
            "일자리 해법 정리",
        ]
        result = score_h2_aeo(
            "기타 정책 모음",
            siblings=siblings,
            full_name="홍길동",
            descriptor_pool=["지역 활동가"],
            section_index=3,
            section_count=4,
        )
        assert "H2_ENTITY_ANCHOR_MISSING" in result["issues"]

    def test_body_echo_penalty(self) -> None:
        result = score_h2_aeo(
            "청년 일자리 핵심 정리",
            siblings=[],
            full_name="홍길동",
            descriptor_pool=[],
            body_first_sentence="청년 일자리 핵심 정리 입니다",
            section_index=0,
            section_count=1,
        )
        assert "H2_BODY_ECHO_FIRST_SENTENCE" in result["issues"]

    def test_length_bands(self) -> None:
        too_short = score_h2_aeo("짧은 제목", siblings=[], section_count=1)
        too_long = score_h2_aeo("이" * 60, siblings=[], section_count=1)
        assert "H2_SHORT_LENGTH" in too_short["issues"]
        assert "H2_LONG_LENGTH" in too_long["issues"]


# ---------------------------------------------------------------------------
# anchor cap enforcement
# ---------------------------------------------------------------------------

class TestAnchorCap:
    def test_compute_anchor_cap_small_sets(self) -> None:
        assert compute_anchor_cap(3) == 1
        assert compute_anchor_cap(4) == 1
        assert compute_anchor_cap(5) == 2
        assert compute_anchor_cap(6) == 2

    def test_enforce_anchor_cap_strips_prefix_comma(self) -> None:
        headings = [
            "샘플구를 변화시키는 홍길동의 책임",
            "청년위원장, 청년 정책 수행해야",
            "샘플시 청년 삶의 질 고민해야",
            "홍길동, 공동체를 위한 책임을 다하는 일꾼",
        ]
        result = enforce_anchor_cap(headings, full_name="홍길동", cap=1)
        assert result["edited"] is True
        out = result["headings"]
        assert out[0] == headings[0]
        assert out[3] == "공동체를 위한 책임을 다하는 일꾼"
        assert "홍길동" not in out[3]

    def test_enforce_anchor_cap_noop_when_within_cap(self) -> None:
        headings = [
            "샘플구 청년 정책 약속",
            "홍길동의 교통 해법 핵심",
            "일자리 5대 우선순위",
            "샘플동 교육 재도약",
        ]
        result = enforce_anchor_cap(headings, full_name="홍길동", cap=1)
        assert result["edited"] is False
        assert result["headings"] == headings

    def test_enforce_anchor_cap_preserves_when_strip_invalid(self) -> None:
        headings = [
            "홍길동 청년 정책 첫 단추",
            "홍길동",
        ]
        result = enforce_anchor_cap(headings, full_name="홍길동", cap=1)
        assert result["headings"][0] == headings[0]
        assert result["headings"][1] == headings[1]

    def test_enforce_anchor_cap_empty_fullname(self) -> None:
        headings = ["샘플 정책 약속", "샘플구 교통 해법"]
        result = enforce_anchor_cap(headings, full_name="", cap=1)
        assert result["edited"] is False
        assert result["headings"] == headings


# ---------------------------------------------------------------------------
# extract_user_role / enforce_user_role_lock
# ---------------------------------------------------------------------------


class TestUserRoleLock:
    def test_extract_user_role_prefers_position(self) -> None:
        # Why: Firestore 정식 스키마는 `position`. profile 저장 핸들러가
        #      canonicalize 한 값(국회의원/광역의원/기초의원/광역자치단체장/
        #      기초자치단체장) 이 여기로 들어온다.
        profile = {
            "position": "기초의원",
            "currentRole": "시의원",
            "identity": "정책 실무자",
        }
        assert extract_user_role(profile) == "기초의원"

    def test_extract_user_role_falls_back_when_position_missing(self) -> None:
        profile = {
            "currentRole": "",
            "current_role": "시의원",
            "identity": "정책 실무자",
        }
        assert extract_user_role(profile) == "시의원"

    def test_extract_user_role_empty_profile(self) -> None:
        assert extract_user_role({}) == ""
        assert extract_user_role(None) == ""

    def test_enforce_user_role_lock_strips_conflicting_role_after_name(self) -> None:
        # Why: 본인("홍길동")은 시의원인데 LLM 이 본문 맥락의 "국회의원"/"위원장"
        #      을 본인 옆에 스탬핑하는 사고가 있었다. allowed_role 과 비호환인
        #      토큰은 본인 앵커 주변에서만 제거한다.
        headings = [
            "홍길동 국회의원의 청년 정책 약속",
            "샘플구 교통 혼잡, 해법은 무엇일까?",
            "홍길동 위원장이 본 지역 경제",
        ]
        result = enforce_user_role_lock(
            headings,
            full_name="홍길동",
            allowed_role="시의원",
        )
        assert result["edited"] is True
        out = result["headings"]
        assert "국회의원" not in out[0]
        assert "위원장" not in out[2]
        assert out[1] == headings[1]

    def test_enforce_user_role_lock_preserves_compatible_role(self) -> None:
        headings = ["홍길동 시의원의 약속은 무엇인가?"]
        result = enforce_user_role_lock(
            headings,
            full_name="홍길동",
            allowed_role="시의원",
        )
        assert result["edited"] is False
        assert result["headings"] == headings

    def test_enforce_user_role_lock_does_not_touch_other_persons(self) -> None:
        # 본인 앵커와 무관한 "이재명 국회의원" 언급은 건드리지 않아야 한다.
        headings = ["이재명 국회의원과의 토론에서 드러난 쟁점"]
        result = enforce_user_role_lock(
            headings,
            full_name="홍길동",
            allowed_role="시의원",
        )
        assert result["edited"] is False
        assert result["headings"] == headings

    def test_enforce_user_role_lock_noop_when_allowed_role_empty(self) -> None:
        headings = ["홍길동 국회의원의 약속"]
        result = enforce_user_role_lock(
            headings,
            full_name="홍길동",
            allowed_role="",
        )
        assert result["edited"] is False
        assert result["headings"] == headings


# ---------------------------------------------------------------------------
# localize_user_role
# ---------------------------------------------------------------------------


class TestLocalizeUserRole:
    # Why: Firestore canonical `position` 값("기초의원"/"광역의원"/"광역자치단체장"
    #      등)은 일반 계층 라벨이지 본인을 칭할 표면은 아니다. 지역과 결합해
    #      "계양구의원", "서울시장" 같은 실제 직함으로 변환되어야 프롬프트에서
    #      본인 호칭 고정이 뜻을 갖는다.

    def test_wide_metro_head_becomes_si_jang(self) -> None:
        assert (
            localize_user_role(
                "광역자치단체장",
                region_metro="서울특별시",
                region_local="",
            )
            == "서울시장"
        )

    def test_province_head_becomes_do_jisa(self) -> None:
        assert (
            localize_user_role(
                "광역자치단체장",
                region_metro="경기도",
                region_local="",
            )
            == "경기도지사"
        )

    def test_sejong_special_city_head(self) -> None:
        assert (
            localize_user_role(
                "광역자치단체장",
                region_metro="세종특별자치시",
                region_local="",
            )
            == "세종시장"
        )

    def test_local_head_si(self) -> None:
        assert (
            localize_user_role(
                "기초자치단체장",
                region_metro="경기도",
                region_local="수원시",
            )
            == "수원시장"
        )

    def test_local_head_gu(self) -> None:
        assert (
            localize_user_role(
                "기초자치단체장",
                region_metro="인천광역시",
                region_local="계양구",
            )
            == "계양구청장"
        )

    def test_local_head_gun(self) -> None:
        assert (
            localize_user_role(
                "기초자치단체장",
                region_metro="경기도",
                region_local="양평군",
            )
            == "양평군수"
        )

    def test_metro_council_member_wide(self) -> None:
        assert (
            localize_user_role(
                "광역의원",
                region_metro="서울특별시",
                region_local="",
            )
            == "서울시의원"
        )

    def test_metro_council_member_province(self) -> None:
        assert (
            localize_user_role(
                "광역의원",
                region_metro="경기도",
                region_local="",
            )
            == "경기도의원"
        )

    def test_local_council_member_gu(self) -> None:
        assert (
            localize_user_role(
                "기초의원",
                region_metro="인천광역시",
                region_local="계양구",
            )
            == "계양구의원"
        )

    def test_local_council_member_si(self) -> None:
        assert (
            localize_user_role(
                "기초의원",
                region_metro="경기도",
                region_local="수원시",
            )
            == "수원시의원"
        )

    def test_preserves_national_role(self) -> None:
        # 국회의원은 지역에 관계없이 그대로 통과.
        assert (
            localize_user_role(
                "국회의원",
                region_metro="서울특별시",
                region_local="강남구",
            )
            == "국회의원"
        )

    def test_preserves_already_localized_title(self) -> None:
        # 이미 지역이 박힌 표면("계양구의원") 은 그대로 유지.
        assert (
            localize_user_role(
                "계양구의원",
                region_metro="인천광역시",
                region_local="계양구",
            )
            == "계양구의원"
        )

    def test_empty_role_returns_empty(self) -> None:
        assert localize_user_role("", region_metro="서울특별시", region_local="") == ""
        assert localize_user_role(None, region_metro="", region_local="") == ""


# ---------------------------------------------------------------------------
# body_alignment 배경 어휘 오탐 차단
# ---------------------------------------------------------------------------

class TestBodyAlignmentBackgroundFP:
    def test_discounts_background_token_false_positive(self) -> None:
        """배경 어휘 오탐: full coverage 높지만 첫 문장과 무관 → BODY_ALIGNMENT_LOW.

        H2를 조사 없는 순수 명사형으로 구성해 regex/kiwi 양쪽에서 substring 매칭이
        일어나도록 한다. 첫 문장은 H2 토큰과 무관한 내용으로, 후반 본문에만 H2 토큰이
        등장하는 배경 어휘 오탐 패턴을 재현한다.
        """
        plan = {
            "must_include_keyword": "청년",
            "suggested_type": "이유형",
            "section_text": (
                "지역 경제 현황을 먼저 살펴봐야 합니다. "
                "청년 창업 지원이 필요한 이유는 일자리 문제와 직결되기 때문입니다."
            ),
        }
        result = score_h2(
            "청년 창업 지원 필요한 이유",
            plan,
            style="aeo",
            preferred_types=["이유형"],
        )
        assert "BODY_ALIGNMENT_LOW" in result["issues"]
        assert result["passed"] is False
        assert result["breakdown"]["body_alignment"]["first_sentence_coverage"] == 0.0
        assert result["breakdown"]["body_alignment"]["background_fp_discounted"] == 1.0

    def test_no_penalty_when_first_sentence_matches(self) -> None:
        """정상 H2: 첫 문장과 토큰 겹침 → 할인 없음."""
        plan = {
            "must_include_keyword": "청년 주거",
            "suggested_type": "질문형",
            "section_text": (
                "청년 주거 문제 해결은 월세 부담 완화와 공공임대 확대에서 출발합니다. "
                "창업 지원과 일자리 정책도 함께 추진합니다."
            ),
        }
        result = score_h2(
            "청년 주거 문제는 어떻게 풀 수 있을까?",
            plan,
            style="aeo",
            preferred_types=["질문형"],
        )
        assert result["breakdown"]["body_alignment"]["background_fp_discounted"] == 0.0
        assert "BODY_ALIGNMENT_LOW" not in result["issues"]

    def test_existing_low_coverage_still_fails(self) -> None:
        """기존 동작 회귀: full coverage 자체가 낮으면 여전히 BODY_ALIGNMENT_LOW."""
        plan = {
            "must_include_keyword": "청년 주거",
            "suggested_type": "주장형",
            "section_text": "교통 혼잡 완화와 버스 노선 조정이 이 지역의 핵심 과제입니다.",
        }
        result = score_h2(
            "청년 주거 공약은 반드시 실현된다",
            plan,
            style="aeo",
            preferred_types=["주장형"],
        )
        assert "BODY_ALIGNMENT_LOW" in result["issues"]
        assert result["passed"] is False
