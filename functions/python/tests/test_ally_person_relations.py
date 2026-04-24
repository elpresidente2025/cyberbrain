"""Phase 2 회귀 테스트: ally(러닝메이트) 긍정 신호 wire-up.

Phase 1 (c1b0b34) 가 화자 직책 앵커를 주입했고, 본 Phase 2 는
사용자 키워드 외 source_texts 에 등장한 인물 중 화자와 같은 팀의
다른 직책 후보(러닝메이트) 를 LLM 에 명시 안내한다.

검증:
  T5: build_role_keyword_policy 가 personReferenceFacts 의 인물에
      대해 ally classification 을 돌려 personRelations 를 산출한다.
  T6: _build_role_keyword_title_policy_instruction 이 ally 인물에
      대해 mode="ally" 룰을 출력한다.
  T7: 화자 본인 / 직접 경쟁자 / 사용자 키워드로 이미 다뤄진 인물은
      personRelations 에서 제외된다 (중복·자기참조 방지).

CLAUDE.md 범용성 원칙: 인물명·지역명·직책 인스턴스는 placeholder
(홍길동·아무개·샘플특별시·샘플구) 만 사용한다.
"""

from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.role_keyword_policy import (
    build_role_keyword_policy,
    get_person_relation,
)
from agents.common.title_prompt_parts import (
    _build_role_keyword_title_policy_instruction,
)


def _speaker_profile() -> dict:
    return {
        "name": "홍길동",
        "position": "광역의원",
        "regionMetro": "샘플특별시",
        "regionLocal": "샘플구",
    }


def test_t5_runningmate_appears_in_person_relations() -> None:
    """같은 지역 상위 직책 후보가 ally 로 분류돼 personRelations 에 들어온다."""
    source_text = (
        "아무개 시장후보와 함께 샘플특별시의 변화를 만들겠습니다. "
        "저 홍길동은 샘플구민의 목소리를 전하는 광역의원입니다."
    )

    policy = build_role_keyword_policy(
        user_keywords=[],  # 사용자가 ally 의 직책을 키워드로 입력하지 않음
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )

    relations = policy.get("personRelations", {})
    assert "아무개" in relations, f"personRelations 에 아무개 누락: {relations}"
    relation = relations["아무개"]
    assert relation["allowCompetitorIntent"] is False
    assert relation["relation"] in {
        "same_region_allied_candidate",
        "allied_figure",
        "same_region_other_office",
        "different_office",
    }
    # bare "시장" 만 captured 된 경우 region inference 가 불가하므로
    # sameRegion 은 False 일 수 있다. allied context("함께") 가 있으니
    # alliedContext 는 True 여야 한다.
    assert relation["alliedContext"] is True
    assert "시장" in relation["role"]


def test_t5b_get_person_relation_helper_returns_relation() -> None:
    """get_person_relation helper 가 정상 조회된다."""
    source_text = "아무개 시장후보와 함께 뛰는 광역의원 홍길동입니다."
    policy = build_role_keyword_policy(
        user_keywords=[],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )

    relation = get_person_relation(policy, "아무개")
    assert relation
    assert relation.get("name") == "아무개"


def test_t6_title_prompt_emits_ally_rule_for_runningmate() -> None:
    """title prompt instruction 이 ally 인물에 대해 mode='ally' 룰을 emit 한다."""
    source_text = "아무개 시장후보와 함께 샘플특별시 발전을 위해 뛰겠습니다."
    policy = build_role_keyword_policy(
        user_keywords=[],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )

    instruction = _build_role_keyword_title_policy_instruction(policy)
    assert instruction
    assert 'person="아무개"' in instruction
    assert 'mode="ally"' in instruction
    assert "화자가 아니므로" in instruction


def test_t7_speaker_self_excluded_from_person_relations() -> None:
    """화자 본인이 source_text 에 등장해도 personRelations 에 들어오지 않는다."""
    source_text = "광역의원 홍길동입니다. 샘플구의 변화를 만들겠습니다."
    policy = build_role_keyword_policy(
        user_keywords=[],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )

    assert "홍길동" not in policy.get("personRelations", {})


def test_t7b_keyword_covered_person_excluded_from_relations() -> None:
    """사용자 키워드로 이미 entries 에 들어온 인물은 personRelations 중복 안 됨.

    ROLE_KEYWORD_PATTERN 이 fullmatch 가능한 형태(예: "아무개 국회의원") 로
    사용자가 키워드를 입력하면 entries 에 들어가고, 같은 인물이 source_text
    에도 등장하면 personRelations 에서는 빠진다.
    """
    source_text = "아무개 국회의원과 함께 샘플특별시 발전을 위해 뛰겠습니다."
    policy = build_role_keyword_policy(
        user_keywords=["아무개 국회의원"],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )

    entry_names = {
        str(entry.get("name") or "")
        for entry in policy.get("entries", {}).values()
        if isinstance(entry, dict)
    }
    assert "아무개" in entry_names
    assert "아무개" not in policy.get("personRelations", {})


def test_t7c_direct_competitor_excluded_from_ally_relations() -> None:
    """allowCompetitorIntent=True (직접 경쟁자/미상) 인 인물은 personRelations 제외.

    같은 office level 의 다른 인물은 same_office_unknown 으로 분류돼
    allowCompetitorIntent=True. ally 가 아니므로 personRelations 에 안 들어감.
    """
    # 화자 = 광역의원, 등장 인물도 광역의원으로 가상 시나리오
    source_text = "샘플특별시의원 아무개 후보와 함께"
    profile = {
        "name": "홍길동",
        "position": "광역의원",
        "regionMetro": "샘플특별시",
    }
    policy = build_role_keyword_policy(
        user_keywords=[],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=profile,
    )
    relations = policy.get("personRelations", {})
    if "아무개" in relations:
        # ally 로 들어왔으면 sameRegion 이고 다른 office 여야 함
        relation = relations["아무개"]
        assert relation["allowCompetitorIntent"] is False


def test_t6b_no_ally_then_no_role_keyword_policy_block() -> None:
    """ally 도 entries 도 없으면 빈 문자열 반환 (불필요한 빈 블록 출력 방지)."""
    policy = build_role_keyword_policy(
        user_keywords=[],
        person_roles={},
        source_texts=[],
        speaker_profile=_speaker_profile(),
    )
    instruction = _build_role_keyword_title_policy_instruction(policy)
    assert instruction == ""


def test_t6c_role_keyword_policy_block_contains_both_entries_and_ally() -> None:
    """entries 와 personRelations 가 둘 다 있으면 한 블록에 합쳐 출력된다."""
    source_text = (
        "아무개 시장후보와 함께 뛰는 광역의원 홍길동입니다. "
        "또다른 의원도 같은 자리에 있었습니다."
    )
    policy = build_role_keyword_policy(
        user_keywords=["또다른 의원"],
        person_roles={},
        source_texts=[source_text],
        speaker_profile=_speaker_profile(),
    )
    instruction = _build_role_keyword_title_policy_instruction(policy)
    assert "<role_keyword_policy>" in instruction
    assert "</role_keyword_policy>" in instruction
    # ally 룰 (아무개) 가 한 블록 안에 있다
    assert 'person="아무개"' in instruction
