from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.core.context_analyzer import ContextAnalyzer
from agents.core.content_validator import ContentValidator
from agents.core.prompt_builder import build_structure_prompt
from agents.core.structure_agent import StructureAgent
from agents.common.title_common import (
    assess_malformed_title_surface,
    build_structured_title_candidates,
)


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
def test_augment_execution_plan_builds_source_contract_from_stance() -> None:
    analyzer = ContextAnalyzer(model_name="test-model")
    stance = (
        "지역화폐 '{policy_name}'은 캐시백 요율을 줄이고 각종 지원책을 줄이면서 위축됐습니다. "
        "담당 부서를 말석에 배치하고 명칭도 사용하지 않아 이용자 수와 결제액이 급감했습니다. "
        "의원 연구단체를 구성해 영향을 분석하고 관련 조례 개정에도 만전을 기하겠습니다."
    )

    analysis = analyzer._augment_execution_plan({}, stance_text=stance)
    contract = analysis["source_contract"]

    assert analysis["answer_type"] == "implementation_plan"
    assert contract["primary_keyword"] == "{policy_name}"
    assert "캐시백 요율 축소" in contract["required_source_facts"]
    assert "지원책 축소" in contract["required_source_facts"]
    assert "담당 부서 위상 약화" in contract["required_source_facts"]
    assert "캐시백 요율 회복" in contract["execution_items"]
    assert "지원책 복원" in contract["execution_items"]
    assert "담당 부서 재정비" in contract["execution_items"]
    assert "관련 조례 개정" in contract["execution_items"]
    assert "10%" in contract["forbidden_inferred_actions"]


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


# synthetic_fixture
def test_build_structure_prompt_injects_source_contract_rules() -> None:
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
                "source_contract": {
                    "answer_type": "implementation_plan",
                    "primary_keyword": "{policy_name}",
                    "central_claim": "{policy_name} 부활 방안을 마련하겠다",
                    "required_source_facts": ["캐시백 요율 축소", "지원책 축소"],
                    "execution_items": ["캐시백 요율 회복", "지원책 복원", "관련 조례 개정"],
                    "forbidden_inferred_actions": ["10%", "전담 TF"],
                },
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

    assert "<primary_keyword>{policy_name}</primary_keyword>" in prompt
    assert "<fact priority=\"1\">캐시백 요율 축소</fact>" in prompt
    assert "<item>10%</item>" in prompt
    assert "사용자 입력 텍스트의 재료입니다" in prompt
    assert "새 공약처럼 쓰지 마십시오" in prompt


# synthetic_fixture
def test_content_validator_rejects_source_contract_hallucinated_action() -> None:
    validator = ContentValidator()
    content = (
        "<p>{policy_name}은 캐시백 요율과 지원책을 회복해야 합니다.</p>"
        "<h2>{policy_name} 실행 방안</h2>"
        "<p>캐시백 요율 회복과 지원책 복원을 추진하겠습니다.</p>"
        "<p>관련 조례 개정도 함께 준비하겠습니다.</p>"
        "<p>다만 캐시백 최소 10% 이상을 새로 보장하겠습니다.</p>"
    )
    issue = validator._validate_source_contract(
        content,
        {
            "source_contract": {
                "answer_type": "implementation_plan",
                "required_source_facts": ["캐시백 요율 축소", "지원책 축소"],
                "execution_items": ["캐시백 요율 회복", "지원책 복원", "관련 조례 개정"],
                "forbidden_inferred_actions": ["10%"],
            }
        },
    )

    assert issue is not None
    assert issue["code"] == "UNSUPPORTED_INFERRED_ACTION"


# synthetic_fixture
def test_structured_title_candidate_uses_keyword_and_execution_items() -> None:
    candidates = build_structured_title_candidates(
        {
            "userKeywords": ["{policy_name}"],
            "contextAnalysis": {
                "source_contract": {
                    "answer_type": "implementation_plan",
                    "primary_keyword": "{policy_name}",
                    "execution_items": [
                        "캐시백 요율 회복",
                        "지원책 복원",
                        "담당 부서 재정비",
                        "관련 조례 개정",
                    ],
                }
            },
        },
        limit=4,
    )

    assert candidates
    assert candidates[0] == "{policy_name} 부활 방안, 캐시백·지원책·관련 조례 개정으로 풉니다"


# synthetic_fixture
def test_malformed_title_rejects_broken_basis_why_surface() -> None:
    result = assess_malformed_title_surface(
        "{policy_name} 지역화폐, {research_org} 바탕으로 민선8기 정책 외면 왜?"
    )

    assert result["passed"] is False
    assert result["issue"] == "broken_basis_why_surface"


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
