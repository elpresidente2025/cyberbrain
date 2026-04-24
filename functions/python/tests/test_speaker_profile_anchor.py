"""Phase 1 회귀 테스트: 화자 직책 앵커 주입.

배경: TitleAgent / ContextAnalyzer 의 프롬프트에 화자 직책이
구조화된 앵커로 들어가지 않아, stanceText 안에 더 큰 직책의
다른 정치인(예: 같은 팀 상위 직책 후보)이 등장하면 LLM 이
그 직책을 화자에게 잘못 귀속시키는 결함이 있었다.

본 테스트는 다음을 보장한다:
  T1: build_title_prompt 가 <speaker_profile> 블록을 출력한다.
  T2: 화자 분리 룰 문구가 프롬프트에 들어간다.
  T3: profile_label helper 가 region 을 결합한 라벨을 만든다.
  T4: ContextAnalyzer 헬퍼가 같은 형식의 블록을 만든다.

CLAUDE.md 범용성 원칙: 모든 인물명·지역명·직책 인스턴스는
placeholder (홍길동/샘플특별시/샘플구) 만 사용한다.
"""

from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.profile_label import (
    format_position_with_region,
    resolve_speaker_position_label,
)
from agents.common.title_generation import build_title_prompt
from agents.core.context_analyzer import ContextAnalyzer


def _base_title_params() -> dict:
    return {
        "topic": "샘플특별시 샘플구 활동 보고",
        "fullName": "홍길동",
        "speakerPositionLabel": "샘플특별시의원",
        "regionMetro": "샘플특별시",
        "regionLocal": "샘플구",
        "electoralDistrict": "샘플구 제1선거구",
        "contentPreview": "<p>샘플 본문입니다.</p>",
        "stanceText": "아무개 시장후보와 함께 샘플특별시 발전을 위해 뛰겠습니다.",
        "userKeywords": [],
        "keywords": [],
        "category": "activity-report",
        "status": "현역",
    }


def test_t1_title_prompt_includes_speaker_profile_block() -> None:
    """build_title_prompt 출력에 <speaker_profile> 블록과 화자 직책이 들어간다."""
    prompt = build_title_prompt(_base_title_params())

    assert "<speaker_profile" in prompt
    assert "<full_name>홍길동</full_name>" in prompt
    assert "<position>샘플특별시의원</position>" in prompt
    assert "<region_metro>샘플특별시</region_metro>" in prompt
    assert "<region_local>샘플구</region_local>" in prompt


def test_t2_title_prompt_includes_role_attribution_rule() -> None:
    """프롬프트에 화자/타인 분리 룰 문구가 포함된다."""
    prompt = build_title_prompt(_base_title_params())

    assert "다른 사람의 직책으로 본인을 묘사하지 말 것" in prompt


def test_t1b_title_prompt_omits_empty_speaker_fields() -> None:
    """프로필 일부 필드가 비어 있으면 출력에서도 생략된다 (LLM 추측 방지)."""
    params = _base_title_params()
    params["speakerPositionLabel"] = ""
    params["regionLocal"] = ""
    params["electoralDistrict"] = ""

    prompt = build_title_prompt(params)

    assert "<full_name>홍길동</full_name>" in prompt
    assert "<region_metro>샘플특별시</region_metro>" in prompt
    assert "<position>" not in prompt
    assert "<region_local>" not in prompt
    assert "<electoral_district>" not in prompt


def test_t1c_title_prompt_skips_block_when_profile_empty() -> None:
    """모든 화자 필드가 비어 있으면 블록 자체가 출력되지 않는다."""
    params = _base_title_params()
    params["fullName"] = ""
    params["speakerPositionLabel"] = ""
    params["regionMetro"] = ""
    params["regionLocal"] = ""
    params["electoralDistrict"] = ""

    prompt = build_title_prompt(params)

    assert "<speaker_profile" not in prompt


def test_t3_format_position_with_region_local_assembly() -> None:
    """광역의원 + regionMetro 결합."""
    label = format_position_with_region(
        {"position": "광역의원", "regionMetro": "샘플특별시"}
    )
    assert label == "샘플특별시의원"


def test_t3b_format_position_with_region_basic_assembly_prefers_local() -> None:
    """기초의원은 regionLocal 우선, 없으면 regionMetro fallback."""
    with_local = format_position_with_region(
        {
            "position": "기초의원",
            "regionMetro": "샘플특별시",
            "regionLocal": "샘플구",
        }
    )
    assert with_local == "샘플구의원"

    without_local = format_position_with_region(
        {"position": "기초의원", "regionMetro": "샘플특별시"}
    )
    assert without_local == "샘플특별시의원"


def test_t3c_format_position_with_region_executive() -> None:
    """광역/기초 단체장 라벨."""
    metro_head = format_position_with_region(
        {"position": "광역자치단체장", "regionMetro": "샘플특별시"}
    )
    assert metro_head == "샘플특별시장"

    basic_head = format_position_with_region(
        {"position": "기초자치단체장", "regionLocal": "샘플구"}
    )
    assert basic_head == "샘플구장"


def test_t3d_format_position_returns_raw_for_national_assembly() -> None:
    """국회의원은 region 결합 없이 원본 반환."""
    label = format_position_with_region(
        {"position": "국회의원", "regionMetro": "샘플특별시"}
    )
    assert label == "국회의원"


def test_t3e_resolve_speaker_position_label_prefers_custom_title() -> None:
    """customTitle 이 있으면 그것이 우선."""
    label = resolve_speaker_position_label(
        {
            "customTitle": "샘플 정책연구소장",
            "position": "광역의원",
            "regionMetro": "샘플특별시",
        }
    )
    assert label == "샘플 정책연구소장"


def test_t3f_resolve_speaker_position_label_falls_back_to_format() -> None:
    """customTitle 이 비어 있으면 format_position_with_region 으로 fallback."""
    label = resolve_speaker_position_label(
        {"position": "광역의원", "regionMetro": "샘플특별시"}
    )
    assert label == "샘플특별시의원"


def test_t4_context_analyzer_renders_speaker_profile_block() -> None:
    """ContextAnalyzer 헬퍼가 같은 형식의 블록을 만든다."""
    block = ContextAnalyzer._render_speaker_profile_xml(
        full_name="홍길동",
        position_label="샘플특별시의원",
        region_metro="샘플특별시",
        region_local="샘플구",
        electoral_district="샘플구 제1선거구",
    )

    assert '<speaker_profile priority="critical">' in block
    assert "<full_name>홍길동</full_name>" in block
    assert "<position>샘플특별시의원</position>" in block
    assert "<region_metro>샘플특별시</region_metro>" in block
    assert "다른 정치인이 등장해도 그 사람은 화자가 아니다" in block


def test_t4b_context_analyzer_speaker_block_empty_when_profile_absent() -> None:
    """화자 정보가 모두 비어 있으면 블록을 비우고 LLM 에 잡음 안 보낸다."""
    block = ContextAnalyzer._render_speaker_profile_xml(
        full_name="",
        position_label="",
        region_metro="",
        region_local="",
        electoral_district="",
    )
    assert block == ""
