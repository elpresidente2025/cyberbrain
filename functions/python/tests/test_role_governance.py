"""회귀 테스트: role_governance + generate_role_warning_bundle

검증 항목:
- 직책별 XML이 올바르게 생성되는지
- 박스 문자가 제거되는지
- familyStatus가 string으로 처리되는지
- warning bundle이 두 블록을 포함하는지
- prompt_builder 경로에서 role_warning_bundle이 reference_materials보다 앞에 오는지
"""
import pytest


# ──────────────────────────────────────────────
# 1. build_role_governance_xml
# ──────────────────────────────────────────────

def test_role_governance_basic_lawmaker_xml():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "기초의원"})
    assert '<role_governance priority="critical" role="기초의원">' in xml
    assert "조례 제정·개정 제안" in xml
    assert "예산 심의와 우선순위 조정" in xml
    assert "기본소득, 기본소득제, BI" in xml
    assert '<rewrite_rules semantic="true">' in xml
    assert "유사어, 축약어, 조사 변화, 동사 변화가 있어도" in xml
    assert "<final_check>" in xml


def test_role_governance_national_lawmaker_xml():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "국회의원"})
    assert 'role="국회의원"' in xml
    assert "법률 제정·개정" in xml
    assert "국정감사" in xml
    assert "국가 예산 심의" in xml
    assert "지방정부 사업을 제가 직접 집행하겠습니다" in xml


def test_role_governance_metro_assembly_xml():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "광역의원"})
    assert 'role="광역의원"' in xml
    assert "광역 조례 제정·개정" in xml
    assert "시·도 예산 심의" in xml


def test_role_governance_basic_executive_xml():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "기초자치단체장"})
    assert 'role="기초자치단체장"' in xml
    assert "행정 집행" in xml
    assert "예산에 반영하겠습니다" in xml
    assert "조례를 제가 발의하겠습니다" in xml


def test_role_governance_metro_executive_xml():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "광역자치단체장"})
    assert 'role="광역자치단체장"' in xml
    assert "광역 행정 운영" in xml
    assert "광역 차원에서 추진하겠습니다" in xml


def test_role_governance_unknown_position_returns_empty():
    from agents.common.role_governance import build_role_governance_xml

    assert build_role_governance_xml({"position": "알수없음"}) == ""
    assert build_role_governance_xml(None) == ""
    assert build_role_governance_xml({}) == ""


def test_role_governance_only_current_role_injected():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "기초의원"})
    assert 'role="국회의원"' not in xml
    assert 'role="광역자치단체장"' not in xml
    assert 'role="기초자치단체장"' not in xml


# ──────────────────────────────────────────────
# 2. _strip_warning_box_artifacts
# ──────────────────────────────────────────────

def test_strip_removes_box_lines():
    from agents.common.warnings import _strip_warning_box_artifacts

    raw = (
        "╔═══════════════════╗\n"
        "║  작성자 신분 설정  ║\n"
        "╚═══════════════════╝\n"
        "\n"
        "본문 내용입니다."
    )
    result = _strip_warning_box_artifacts(raw)
    assert "╔" not in result
    assert "╚" not in result
    assert "═" not in result
    assert "작성자 신분 설정" in result
    assert "본문 내용입니다." in result


def test_strip_preserves_non_box_content():
    from agents.common.warnings import _strip_warning_box_artifacts

    text = "[절대 금지]\n❌ 국회의원 표현\n✅ 기초의원 표현"
    result = _strip_warning_box_artifacts(text)
    assert "절대 금지" in result
    assert "❌" in result
    assert "✅" in result


# ──────────────────────────────────────────────
# 3. generate_role_warning_bundle
# ──────────────────────────────────────────────

def test_bundle_contains_role_governance_and_non_lawmaker():
    from agents.common.warnings import generate_role_warning_bundle

    bundle = generate_role_warning_bundle(
        user_profile={
            "position": "기초의원",
            "status": "예비",
            "politicalExperience": "정치 신인",
        },
        author_bio="샘플구의원 예비후보 홍길동",
    )
    assert "<role_warning_bundle>" in bundle
    assert "<role_governance" in bundle
    assert "<non_lawmaker_warning>" in bundle
    assert "기본소득" in bundle
    assert "제가 발의한 조례" in bundle


def test_bundle_no_box_chars_in_non_lawmaker_section():
    from agents.common.warnings import generate_role_warning_bundle

    bundle = generate_role_warning_bundle(
        user_profile={
            "position": "기초의원",
            "status": "예비",
            "politicalExperience": "정치 신인",
        },
        author_bio="홍길동",
    )
    assert "╔" not in bundle
    assert "╚" not in bundle
    assert "═" not in bundle


def test_bundle_national_lawmaker_has_role_governance_but_no_non_lawmaker():
    from agents.common.warnings import generate_role_warning_bundle

    bundle = generate_role_warning_bundle(
        user_profile={"position": "국회의원"},
        author_bio="홍길동",
    )
    assert "<role_governance" in bundle
    assert "<non_lawmaker_warning>" not in bundle


def test_bundle_empty_for_unknown_position_and_lawmaker():
    from agents.common.warnings import generate_role_warning_bundle

    # 알 수 없는 직책 + 국회의원급 → role_governance 없음, non_lawmaker 없음
    result = generate_role_warning_bundle(
        user_profile={"position": "알수없음", "status": "현역", "politicalExperience": "초선"},
        author_bio="",
    )
    # role_governance 없고 non_lawmaker도 없으면 빈 문자열
    assert result == ""


# ──────────────────────────────────────────────
# 4. familyStatus string 처리
# ──────────────────────────────────────────────

def test_family_status_warning_fires_with_string():
    from agents.common.warnings import generate_family_status_warning

    result = generate_family_status_warning("미혼")
    assert "자녀" in result

    result2 = generate_family_status_warning("기혼(자녀 없음)")
    assert "자녀" in result2


def test_family_status_warning_silent_for_other_values():
    from agents.common.warnings import generate_family_status_warning

    assert generate_family_status_warning("기혼(자녀 있음)") == ""
    assert generate_family_status_warning("") == ""


# ──────────────────────────────────────────────
# 5. prompt_builder 경로 순서 검증
# ──────────────────────────────────────────────

def test_build_structure_prompt_role_warning_before_reference_materials():
    from agents.core.prompt_builder import build_structure_prompt

    prompt = build_structure_prompt({
        "topic": "샘플구 생활 복지 정책",
        "category": "policy-proposal",
        "writingMethod": "logical_writing",
        "authorName": "홍길동",
        "authorBio": "샘플구의원 예비후보 홍길동",
        "instructions": "주민 생활 개선",
        "newsContext": "지역 복지 논의",
        "ragContext": "",
        "targetWordCount": 1800,
        "contextAnalysis": {},
        "userProfile": {
            "name": "홍길동",
            "position": "기초의원",
            "status": "예비",
            "politicalExperience": "정치 신인",
            "regionMetro": "샘플특별시",
            "regionLocal": "샘플구",
        },
        "userKeywords": ["홍길동", "샘플구"],
        "lengthSpec": {
            "body_sections": 3,
            "total_sections": 5,
            "paragraphs_per_section": 3,
            "per_section_min": 180,
            "per_section_max": 320,
        },
    })

    role_idx = prompt.find("<role_warning_bundle>")
    ref_idx = prompt.find("<reference_materials")

    assert role_idx != -1, "role_warning_bundle이 프롬프트에 없음"
    assert ref_idx != -1, "reference_materials가 프롬프트에 없음"
    assert role_idx < ref_idx, (
        f"role_warning_bundle({role_idx})이 reference_materials({ref_idx})보다 뒤에 위치함"
    )


def test_build_structure_prompt_role_warning_before_execution_plan():
    from agents.core.prompt_builder import build_structure_prompt

    prompt = build_structure_prompt({
        "topic": "샘플구 생활 복지 정책",
        "category": "policy-proposal",
        "writingMethod": "logical_writing",
        "authorName": "홍길동",
        "authorBio": "샘플구의원 예비후보 홍길동",
        "instructions": "주민 생활 개선",
        "newsContext": "지역 복지 논의",
        "ragContext": "",
        "targetWordCount": 1800,
        "contextAnalysis": {},
        "userProfile": {
            "name": "홍길동",
            "position": "기초의원",
            "status": "예비",
            "politicalExperience": "정치 신인",
            "regionMetro": "샘플특별시",
            "regionLocal": "샘플구",
        },
        "userKeywords": ["홍길동", "샘플구"],
        "lengthSpec": {
            "body_sections": 3,
            "total_sections": 5,
            "paragraphs_per_section": 3,
            "per_section_min": 180,
            "per_section_max": 320,
        },
    })

    role_idx = prompt.find("<role_warning_bundle>")
    plan_idx = prompt.find("<execution_plan")

    assert role_idx != -1, "role_warning_bundle이 프롬프트에 없음"
    if plan_idx != -1:
        assert role_idx < plan_idx, (
            f"role_warning_bundle({role_idx})이 execution_plan({plan_idx})보다 뒤에 위치함"
        )


def test_build_structure_prompt_basic_lawmaker_contains_scale_guard():
    """기초의원 프롬프트에 국가급 정책 스케일 금지 텍스트가 포함되어야 한다."""
    from agents.core.prompt_builder import build_structure_prompt

    prompt = build_structure_prompt({
        "topic": "샘플구 기본소득 정책",
        "category": "policy-proposal",
        "writingMethod": "logical_writing",
        "authorName": "홍길동",
        "authorBio": "샘플구의원 예비후보 홍길동",
        "instructions": "기본소득 도입과 증세 합의 필요성",
        "newsContext": "",
        "ragContext": "",
        "targetWordCount": 1800,
        "contextAnalysis": {},
        "userProfile": {
            "name": "홍길동",
            "position": "기초의원",
            "status": "예비",
            "politicalExperience": "정치 신인",
            "regionMetro": "샘플특별시",
            "regionLocal": "샘플구",
        },
        "userKeywords": ["홍길동", "샘플구"],
        "lengthSpec": {
            "body_sections": 3,
            "total_sections": 5,
            "paragraphs_per_section": 3,
            "per_section_min": 180,
            "per_section_max": 320,
        },
    })

    # forbidden_direct_claims 항목이 프롬프트에 있어야 함
    assert "전국 단위 기본소득을 시행하겠습니다" in prompt
    assert "증세 합의를 이끌겠습니다" in prompt

    # rewrite_rules의 source_pattern과 target_frame이 들어가야 함
    assert "기본소득, 기본소득제, BI" in prompt
    assert "생활비 부담을 줄이는 지역형 지원 조례 검토" in prompt

    # role_warning_bundle이 reference_materials보다 앞에 있어야 함
    role_idx = prompt.find("<role_warning_bundle>")
    ref_idx = prompt.find("<reference_materials")
    assert role_idx != -1
    assert role_idx < ref_idx or ref_idx == -1


# ──────────────────────────────────────────────
# 6. final_check 완료형 사실 금지 규칙
# ──────────────────────────────────────────────

def test_role_governance_final_check_blocks_unverified_completed_facts():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "기초의원"})

    assert "근거 없는 완료형 사실 표현 금지" in xml
    assert "확보했습니다" in xml
    assert "합의했습니다" in xml
    assert "확정됐습니다" in xml
    assert "공식 문서·예산안·의결·협약·회의록·보도자료 등" in xml


def test_role_governance_final_check_suggests_procedural_rewrites():
    from agents.common.role_governance import build_role_governance_xml

    xml = build_role_governance_xml({"position": "국회의원"})

    assert "확보를 추진하겠습니다" in xml
    assert "협의하겠습니다" in xml
    assert "반영되도록 요구하겠습니다" in xml
