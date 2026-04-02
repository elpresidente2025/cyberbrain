import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.core.structure_agent import StructureAgent
from agents.core.structure_normalizer import (
    normalize_section_length,
    normalize_section_p_count,
    normalize_structure,
)


def test_structure_agent_build_structure_json_schema_requires_nonempty_section_paragraphs() -> None:
    agent = StructureAgent(options={})

    schema = agent._build_structure_json_schema(
        {
            "body_sections": 2,
            "paragraphs_per_section": 2,
        }
    )

    assert schema["properties"]["intro"]["properties"]["paragraphs"]["minItems"] == 1
    assert schema["properties"]["body"]["minItems"] == 2
    assert schema["properties"]["body"]["maxItems"] == 2
    assert schema["properties"]["body"]["items"]["properties"]["paragraphs"]["minItems"] == 1
    assert schema["properties"]["conclusion"]["properties"]["paragraphs"]["minItems"] == 2


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


def test_structure_agent_build_html_drops_heading_only_section_after_empty_body() -> None:
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
    assert "지금 이재성에 주목해야 하는 이유" in content


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
            "structure_agent_build_structure_json_schema_requires_nonempty_section_paragraphs",
            test_structure_agent_build_structure_json_schema_requires_nonempty_section_paragraphs,
        ),
        (
            "structure_agent_build_html_drops_heading_only_section_after_empty_body",
            test_structure_agent_build_html_drops_heading_only_section_after_empty_body,
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
