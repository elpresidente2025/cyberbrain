from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.core.context_analyzer import ContextAnalyzer
from agents.core.prompt_builder import build_structure_prompt
from agents.core.structure_agent import StructureAgent


# synthetic_fixture
def test_augment_execution_plan_normalizes_llm_output() -> None:
    """LLM이 추출한 answer_type/central_claim/execution_items가 정규화·보강되어 통과한다."""
    analyzer = ContextAnalyzer(model_name="test-model")

    analysis = analyzer._augment_execution_plan(
        {
            # alias → canonical 정규화 검증
            "answer_type": "policy_revival_plan",
            "central_claim": "{policy_name} 부활 방안을 마련하겠다",
            "execution_items": [
                "캐시백 요율 회복",
                "캐시백 요율 회복",  # 중복 제거 확인
                "지원책 복원",
                "전담 추진체계 재정비",
                "관련 조례 개정",
            ],
        }
    )

    assert analysis["answer_type"] == "implementation_plan"
    assert analysis["central_claim"] == "{policy_name} 부활 방안을 마련하겠다"
    assert analysis["execution_items"] == [
        "캐시백 요율 회복",
        "지원책 복원",
        "전담 추진체계 재정비",
        "관련 조례 개정",
    ]
    emphasis = analysis["contentStrategy"]["emphasis"]
    assert "구체 실행 항목" in emphasis
    assert "제도화" in emphasis
    assert "효과 확인" in emphasis


def test_augment_execution_plan_leaves_empty_when_llm_did_not_extract() -> None:
    """LLM이 비워서 보낸 경우 휴리스틱으로 도메인을 박지 않고 빈 값을 유지한다."""
    analyzer = ContextAnalyzer(model_name="test-model")

    analysis = analyzer._augment_execution_plan({})

    assert analysis["answer_type"] == ""
    assert analysis["central_claim"] == ""
    assert analysis["execution_items"] == []
    assert "contentStrategy" not in analysis


# synthetic_fixture
def test_build_structure_prompt_injects_execution_plan_lock() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "{policy_name} 부활 방안",
            "category": "policy-proposal",
            "writingMethod": "logical_writing",
            "authorName": "{user_name}",
            "authorBio": "{user_name} 의원",
            "instructions": "{policy_name} 부활 방안을 모색하겠습니다.",
            "userKeywords": ["{policy_name}"],
            "targetWordCount": 1200,
            "contextAnalysis": {
                "answer_type": "implementation_plan",
                "central_claim": "{policy_name} 부활 방안을 마련하겠다",
                "execution_items": [
                    "캐시백 요율 회복",
                    "지원책 복원",
                    "전담 추진체계 재정비",
                    "관련 조례 개정",
                ],
            },
            "lengthSpec": {
                "min_chars": 1000,
                "max_chars": 1500,
                "body_sections": 3,
                "total_sections": 5,
                "paragraphs_per_section": 3,
            },
            "outputMode": "json",
            "userProfile": {},
        }
    )

    assert "<execution_plan mandatory=\"true\">" in prompt
    assert "<central_claim>{policy_name} 부활 방안을 마련하겠다</central_claim>" in prompt
    assert "캐시백 요율 회복" in prompt
    assert "정책 일반론이 아니라 위 실행 항목을 답하는 실행안" in prompt


def test_outline_prompt_prioritizes_execution_structure_over_dialectic() -> None:
    agent = StructureAgent(options={"structureMaxRetries": 1})
    base_prompt = (
        "<structure_agent_prompt>"
        "<context_injection>"
        "<execution_plan mandatory=\"true\">"
        "<execution_items><item>캐시백 요율 회복</item><item>관련 조례 개정</item></execution_items>"
        "</execution_plan>"
        "</context_injection>"
        "</structure_agent_prompt>"
    )

    prompt = agent._build_outline_json_prompt(
        prompt=base_prompt,
        length_spec={"body_sections": 3},
        writing_method="logical_writing",
    )

    assert "<implementation_structure priority=\"critical\">" in prompt
    assert "execution_items의 실행 항목" in prompt
    assert "<argument_structure priority=\"high\">" not in prompt
