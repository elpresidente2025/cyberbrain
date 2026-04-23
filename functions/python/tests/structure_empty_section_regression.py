import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.core.structure_agent import StructureAgent
from agents.common.leadership import build_argument_role_material_block
from agents.core.structure_normalizer import (
    normalize_section_length,
    normalize_section_p_count,
    normalize_structure,
)
from services.posts.output_formatter import compress_redundant_sentences


def test_structure_agent_build_structure_json_schema_requires_three_paragraphs_per_section() -> None:
    agent = StructureAgent(options={})

    schema = agent._build_structure_json_schema(
        {
            "body_sections": 2,
            "paragraphs_per_section": 2,
        }
    )

    assert schema["properties"]["intro"]["properties"]["paragraphs"]["minItems"] == 3
    assert schema["properties"]["intro"]["properties"]["paragraphs"]["maxItems"] == 3
    assert schema["properties"]["body"]["minItems"] == 2
    assert schema["properties"]["body"]["maxItems"] == 2
    assert schema["properties"]["body"]["items"]["properties"]["paragraphs"]["minItems"] == 3
    assert schema["properties"]["body"]["items"]["properties"]["paragraphs"]["maxItems"] == 3
    assert schema["properties"]["conclusion"]["properties"]["paragraphs"]["minItems"] == 3
    assert schema["properties"]["conclusion"]["properties"]["paragraphs"]["maxItems"] == 3


def test_structure_agent_repair_low_alignment_heading_ignores_name_only_overlap() -> None:
    agent = StructureAgent(options={})

    repaired = agent._repair_low_alignment_heading(
        heading="부산시장 이재성, 혁신과 미래를 선택",
        paragraphs=[
            "소년의집에서 10년 동안 아이들과 생활하며 현장의 어려움을 함께 겪었습니다.",
            "그 시간은 사람을 먼저 보는 태도와 공동체 감각을 제게 남겼습니다.",
        ],
        contract={"template": "사람 곁에서 쌓은 현장 경험"},
        section_label="본론 1",
        ignore_tokens=["이재성", "부산시장"],
        minimum_score=0.34,
    )

    assert repaired == "사람 곁에서 쌓은 현장 경험"


def test_structure_agent_build_html_keeps_conclusion_content_when_empty_body_section_is_dropped() -> None:
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
                "heading": "혁신과 연대로 부산의 새로운 도약",
                "paragraphs": ["", "   "],
            }
        ],
        "conclusion": {
            "heading": "지금 이재성에 주목해야 하는 이유",
            "paragraphs": [
                "지금 이재성의 경쟁력은 확인됐습니다.",
                "부산 경제를 다시 세우는 실행력이 중요합니다.",
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
        poll_focus_bundle=None,
    )

    assert "혁신과 연대로 부산의 새로운 도약" not in content
    assert "지금 이재성의 경쟁력은 확인됐습니다." in content
    assert "부산 경제를 다시 세우는 실행력이 중요합니다." in content
    assert "<h2></h2>" in content


# synthetic_fixture
def test_structure_agent_build_expansion_json_prompt_inlines_role_material_inside_target_body_sections() -> None:
    agent = StructureAgent(options={})
    outline = {
        "title": "{region} 지역화폐를 다시 살릴 시간",
        "intro_lead": "{region} 민생경제를 살리기 위해 지역화폐 활성화가 필요합니다.",
        "body": [
            {
                "heading": "지역화폐 축소가 남긴 공백",
                "lead_sentence": "지역화폐 축소 이후 소비 흐름이 약해졌습니다.",
                "role": "evidence",
            },
            {
                "heading": "소상공인 매출과 지역 순환",
                "lead_sentence": "지역 안에서 돈이 돌 때 골목상권이 버팁니다.",
                "role": "evidence",
            },
            {
                "heading": "예상되는 우려와 다시 답해야 할 이유",
                "lead_sentence": "일부에서는 지역화폐가 재정 부담만 키운다고 말합니다.",
                "role": "counterargument_rebuttal",
            },
            {
                "heading": "기본생활을 지키는 지역경제 원칙",
                "lead_sentence": "지역화폐는 소비 지원을 넘어 공동체 안전망과도 연결됩니다.",
                "role": "higher_principle",
            },
        ],
        "conclusion_heading": "{region} 경제를 다시 움직일 실천",
    }

    prompt = agent._build_expansion_json_prompt(
        outline=outline,
        base_prompt="BASE_PROMPT",
        length_spec={
            "body_sections": 4,
            "paragraphs_per_section": 3,
        },
        writing_method="logical_writing",
    )

    section3 = prompt.split('<body_section order="3">', 1)[1].split('</body_section>', 1)[0]
    section4 = prompt.split('<body_section order="4">', 1)[1].split('</body_section>', 1)[0]

    assert '<role_material role="counterargument_rebuttal"' in section3
    assert '<role_material role="higher_principle"' in section4
    assert section3.index('<expansion_role') < section3.index('<role_material role="counterargument_rebuttal"')
    assert section4.index('<expansion_role') < section4.index('<role_material role="higher_principle"')
    assert '<argument_layer for=' not in prompt
    # counterargument_rebuttal: 문단별 ���할 명시 + 금지 규칙
    assert '<paragraph_roles>' in section3
    assert '반론 수용' in section3
    assert '재반론' in section3
    assert '<ban>' in section3
    # higher_principle: 문단별 역할 명시
    assert '<paragraph_roles>' in section4
    assert '가치 선언' in section4
    assert '실증 근거' in section4
    assert '한국 맥락 착지' in section4


# real_fixture_ok: 지역화폐 브랜드명 기반 소재 매칭 회귀 검증에는 실제 명칭이 필요함
def test_leadership_material_prioritizes_local_currency_for_registered_brand_names() -> None:
    for brand in ("인천e음", "동백전", "여민전", "탐나는전", "경기지역화폐"):
        evidence = build_argument_role_material_block(
            "evidence",
            topic=f"{brand} 활성화 방안",
            keywords=[brand],
        )
        higher = build_argument_role_material_block(
            "higher_principle",
            topic=f"{brand} 활성화 방안",
            keywords=[brand],
        )
        rebuttal = build_argument_role_material_block(
            "counterargument_rebuttal",
            topic=f"{brand} 활성화 방안",
            keywords=[brand],
        )

        assert '<role_material role="evidence"' in evidence
        assert "지역화폐 지급" in evidence or "지역화폐 → 골목상권 강제 순환" in evidence
        assert "지역화폐 → 골목상권 강제 순환" in higher
        assert "모세혈관 경제" in higher
        assert "지역화폐 지급이 민생구제와 골목상권 매출 증대의 이중 효과" in rebuttal


# real_fixture_ok: 지역화폐 브랜드명 기반 프롬프트 연결 회귀 검증에는 실제 명칭이 필요함
def test_expansion_prompt_injects_local_currency_material_into_evidence_sections() -> None:
    agent = StructureAgent(options={})
    outline = {
        "title": "동백전 활성화 방안",
        "intro_lead": "지역화폐를 다시 민생경제의 실질적 도구로 세우겠습니다.",
        "body": [
            {
                "heading": "소상공인 매출과 지역 순환",
                "lead_sentence": "지역 안에서 돈이 돌 때 골목상권이 버팁니다.",
                "role": "evidence",
            },
            {
                "heading": "예상되는 우려와 재정의 답",
                "lead_sentence": "일부에서는 지역화폐가 재정 부담만 키운다고 말합니다.",
                "role": "counterargument_rebuttal",
            },
            {
                "heading": "기본생활을 지키는 지역경제 원칙",
                "lead_sentence": "지역화폐는 소비 지원을 넘어 공동체 안전망과도 연결됩니다.",
                "role": "higher_principle",
            },
        ],
        "conclusion_heading": "지역경제를 다시 움직일 실천",
    }

    prompt = agent._build_expansion_json_prompt(
        outline=outline,
        base_prompt="BASE_PROMPT",
        length_spec={"body_sections": 3, "paragraphs_per_section": 3},
        writing_method="logical_writing",
        topic="동백전 활성화 방안",
        user_keywords=["동백전"],
    )
    section1 = prompt.split('<body_section order="1">', 1)[1].split('</body_section>', 1)[0]

    assert '<role_material role="evidence"' in section1
    assert "지역화폐" in section1
    assert "골목상권" in section1


# real_fixture_ok: leadership.py의 실제 정책 재료 선택 회귀 검증에는 실제 정책명·사례명이 필요함
def test_leadership_material_prioritizes_multiple_policy_domains() -> None:
    cases = [
        (
            "공공병원 의료공백 해소 방안",
            "evidence",
            ("성남시의료원", "의료공백"),
        ),
        (
            "공공배달앱 수수료 부담 완화",
            "counterargument_rebuttal",
            ("공공배달앱은 민간 혁신", "플랫폼 사업자"),
        ),
        (
            "저신용자 불법 사금융 대책",
            "evidence",
            ("극저신용대출", "불법사금융"),
        ),
        (
            "공공건설 원가 공개 확대",
            "counterargument_rebuttal",
            ("원가 공개·표준시장단가", "4.4% 절감"),
        ),
        (
            "공공버스 준공영제와 이동권",
            "evidence",
            ("공공버스", "이동권"),
        ),
    ]

    for topic, role, expected_fragments in cases:
        material = build_argument_role_material_block(role, topic=topic, keywords=[topic])
        assert material, topic
        assert any(fragment in material for fragment in expected_fragments), material


def test_normalize_structure_padding_avoids_deprecated_boilerplate_sentences() -> None:
    content = "<h2>부산의 변화</h2><p>부산 경제를 다시 세우겠습니다.</p>"

    normalized = normalize_structure(
        content,
        length_spec={
            "body_sections": 1,
            "paragraphs_per_section": 2,
        },
    )

    assert "핵심 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다." not in normalized
    assert "추상적 선언이 아니라 시민이 체감할 수 있는 변화를 만들겠습니다." not in normalized
    assert "실행 과정에서 드러나는 한계는 즉시 보완해 완성도를 높이겠습니다." not in normalized


def test_normalize_section_p_count_does_not_fill_last_section_with_generic_padding() -> None:
    content = (
        "<p>부산의 변화는 더 미룰 수 없습니다.</p>"
        "<h2>부산 경제 체질 개선</h2>"
        "<p>스마트 항만과 자율운항 산업을 연결해 새로운 성장축을 만들겠습니다. "
        "지역 제조업의 전환 속도도 함께 높이겠습니다.</p>"
        "<p>AI와 블록체인 스타트업이 부산에 자리잡을 수 있도록 투자와 실증 기회를 넓히겠습니다. "
        "청년 일자리와 산업 생태계를 동시에 키우겠습니다.</p>"
        "<h2>부산 경제 대혁신</h2>"
        "<p>반드시 생활의 변화로 이어지게 하겠습니다.</p>"
    )

    normalized = normalize_section_p_count(content)
    tail = normalized.split("<h2>부산 경제 대혁신</h2>", 1)[-1]

    assert "현장 목소리를 꾸준히 듣고 미흡한 지점은 빠르게 손보겠습니다." not in tail
    assert "부산의 산업과 생활 문제를 함께 보며 해법을 더 구체화하겠습니다." not in tail
    assert "사업 추진 현황을 투명하게 공개하고 결과로 증명하겠습니다." not in tail
    assert "지역 현안에 대한 전문가 자문과 주민 토론을 병행하겠습니다." not in tail


# synthetic_fixture
def test_normalize_section_p_count_splits_last_section_when_content_allows() -> None:
    content = (
        "<p>{region} 변화는 더 미룰 수 없습니다.</p>"
        "<p>현장에서 확인한 과제를 정책으로 연결하겠습니다.</p>"
        "<p>주민이 체감하는 결과를 만들겠습니다.</p>"
        "<h2>{region} 민생 회복 전략</h2>"
        "<p>{region} 지역화폐는 골목상권 소비를 다시 묶는 수단입니다. "
        "소상공인 매출 흐름을 살리고 주민 구매 부담을 낮추는 효과도 있습니다. "
        "예산과 집행 기준을 함께 설계해야 지속 가능한 정책으로 자리 잡을 수 있습니다. "
        "상권별 소비 데이터를 확인해 필요한 지원 대상을 더 정확히 잡겠습니다. "
        "공공 배달과 전통시장 결제망을 연계해 사용처도 넓히겠습니다. "
        "정산 속도와 가맹점 안내를 개선해 소상공인의 불편을 줄이겠습니다. "
        "주민 설명과 집행 점검을 병행해 정책 신뢰를 높이겠습니다. "
        "분기별 성과를 공개해 보완 과제까지 책임 있게 챙기겠습니다.</p>"
    )

    normalized = normalize_section_p_count(content)
    tail = normalized.split("<h2>{region} 민생 회복 전략</h2>", 1)[-1]

    assert tail.count("<p>") == 3
    paragraphs = re.findall(r"<p\b[^>]*>([\s\S]*?)</p\s*>", tail, re.IGNORECASE)
    assert all(len(re.findall(r"[.!?。！？]", paragraph)) >= 2 for paragraph in paragraphs)


# synthetic_fixture
def test_normalize_section_p_count_does_not_split_single_sentence_mid_phrase() -> None:
    content = (
        "<h2>{region} 실행 계획</h2>"
        "<p>{region} 관내 일조량을 정밀하게 분석하여 햇빛지도를 제작하고, "
        "햇빛지도를 기반으로 태양광 발전시설 설치에 적합한 공영주차장과 "
        "공공기관 옥상 등의 지역과 수익성을 분석하는 용역을 추진하겠습니다.</p>"
    )

    normalized = normalize_section_p_count(content)

    assert "태양광 발전시설</p>\n<p>설치에 적합한" not in normalized
    assert normalized.count("<p>") == 1


# synthetic_fixture
def test_normalize_section_p_count_merges_broken_mid_sentence_paragraphs() -> None:
    content = (
        "<h2>{region} 실행 계획</h2>"
        "<p>{region} 관내 일조량을 정밀하게 분석하여 햇빛지도를 제작하고, "
        "햇빛지도를 기반으로 태양광 발전시설</p>"
        "<p>설치에 적합한 공영주차장과 공공기관 옥상 등의 지역과 수익성을 분석하는 용역을 추진하겠습니다.</p>"
        "<p>사업성 검토는 주민 공유 모델을 설계하는 첫 단계입니다.</p>"
    )

    normalized = normalize_section_p_count(content)

    assert "태양광 발전시설 설치에 적합한" in normalized
    assert "태양광 발전시설</p>\n<p>설치에 적합한" not in normalized
    assert "<p>사업성 검토는 주민 공유 모델을 설계하는 첫 단계입니다.</p>" not in normalized


# synthetic_fixture
def test_compress_redundant_sentences_keeps_two_sentence_minimum() -> None:
    content = (
        "<h2>{region} 정책 점검</h2>"
        "<p>현장 점검을 이어가겠습니다. 현장 점검을 이어가겠습니다.</p>"
        "<p>예산 흐름을 확인하겠습니다. 주민 설명도 병행하겠습니다.</p>"
    )

    compressed, meta = compress_redundant_sentences(content)

    assert int(meta.get("removedSentences") or 0) == 0
    assert "현장 점검을 이어가겠습니다. 현장 점검을 이어가겠습니다." in compressed


def test_normalize_section_length_does_not_pad_underfilled_body_section_with_generic_text() -> None:
    content = (
        "<p>부산의 변화는 더 미룰 수 없습니다.</p>"
        "<h2>민주당 경선 구도</h2>"
        "<p>이번 경선은 정책과 경력의 대비를 보여줍니다.</p>"
        "<h2>부산 경제 대혁신</h2>"
        "<p>스마트 항만과 자율운항 산업을 연결해 새로운 성장축을 만들겠습니다.</p>"
        "<p>AI와 블록체인 스타트업이 부산에 자리잡을 수 있도록 투자와 실증 기회를 넓히겠습니다.</p>"
    )

    normalized = normalize_section_length(content, min_chars=320, max_chars=470)
    middle = normalized.split("<h2>민주당 경선 구도</h2>", 1)[-1].split("<h2>부산 경제 대혁신</h2>", 1)[0]

    assert "행정 절차와 예산 흐름까지 살펴 실현 가능한 해법으로 다듬겠습니다." not in middle
    assert "현장 목소리를 꾸준히 듣고 미흡한 지점은 빠르게 손보겠습니다." not in middle
    assert "부산의 산업과 생활 문제를 함께 보며 해법을 더 구체화하겠습니다." not in middle


def main() -> None:
    tests = [
        (
            "structure_agent_build_structure_json_schema_requires_three_paragraphs_per_section",
            test_structure_agent_build_structure_json_schema_requires_three_paragraphs_per_section,
        ),
        (
            "structure_agent_build_html_keeps_conclusion_content_when_empty_body_section_is_dropped",
            test_structure_agent_build_html_keeps_conclusion_content_when_empty_body_section_is_dropped,
        ),
        (
            "structure_agent_build_expansion_json_prompt_inlines_role_material_inside_target_body_sections",
            test_structure_agent_build_expansion_json_prompt_inlines_role_material_inside_target_body_sections,
        ),
        (
            "leadership_material_prioritizes_local_currency_for_registered_brand_names",
            test_leadership_material_prioritizes_local_currency_for_registered_brand_names,
        ),
        (
            "expansion_prompt_injects_local_currency_material_into_evidence_sections",
            test_expansion_prompt_injects_local_currency_material_into_evidence_sections,
        ),
        (
            "leadership_material_prioritizes_multiple_policy_domains",
            test_leadership_material_prioritizes_multiple_policy_domains,
        ),
        (
            "structure_agent_repair_low_alignment_heading_ignores_name_only_overlap",
            test_structure_agent_repair_low_alignment_heading_ignores_name_only_overlap,
        ),
        (
            "normalize_structure_padding_avoids_deprecated_boilerplate_sentences",
            test_normalize_structure_padding_avoids_deprecated_boilerplate_sentences,
        ),
        (
            "normalize_section_p_count_does_not_fill_last_section_with_generic_padding",
            test_normalize_section_p_count_does_not_fill_last_section_with_generic_padding,
        ),
        (
            "normalize_section_p_count_splits_last_section_when_content_allows",
            test_normalize_section_p_count_splits_last_section_when_content_allows,
        ),
        (
            "normalize_section_p_count_does_not_split_single_sentence_mid_phrase",
            test_normalize_section_p_count_does_not_split_single_sentence_mid_phrase,
        ),
        (
            "normalize_section_p_count_merges_broken_mid_sentence_paragraphs",
            test_normalize_section_p_count_merges_broken_mid_sentence_paragraphs,
        ),
        (
            "compress_redundant_sentences_keeps_two_sentence_minimum",
            test_compress_redundant_sentences_keeps_two_sentence_minimum,
        ),
        (
            "normalize_section_length_does_not_pad_underfilled_body_section_with_generic_text",
            test_normalize_section_length_does_not_pad_underfilled_body_section_with_generic_text,
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
