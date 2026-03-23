import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.core.structure_agent import StructureAgent


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
    assert schema["properties"]["conclusion"]["properties"]["paragraphs"]["minItems"] == 1


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
    ]
    passed = 0
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
        passed += 1
    print(f"OK {passed}")


if __name__ == "__main__":
    main()
