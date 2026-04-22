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
from agents.common.h2_quality import detect_dependent_section_opening


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
def test_structured_title_candidate_uses_solar_execution_items() -> None:
    candidates = build_structured_title_candidates(
        {
            "userKeywords": ["{policy_name}"],
            "contextAnalysis": {
                "source_contract": {
                    "answer_type": "implementation_plan",
                    "primary_keyword": "{policy_name}",
                    "execution_items": [
                        "햇빛지도 제작과 일조량 분석",
                        "개발이익 주민 공유",
                        "조례 제정 추진",
                        "입지·수익성 분석 용역 추진",
                    ],
                }
            },
        },
        limit=4,
    )

    assert candidates
    assert candidates[0] == "{policy_name}, 햇빛지도와 조례 제정이 첫 단계입니다"


# synthetic_fixture
def test_malformed_title_rejects_broken_basis_why_surface() -> None:
    result = assess_malformed_title_surface(
        "{policy_name} 지역화폐, {research_org} 바탕으로 민선8기 정책 외면 왜?"
    )

    assert result["passed"] is False
    assert result["issue"] == "broken_basis_why_surface"


# synthetic_fixture
def test_malformed_title_rejects_source_contract_forbidden_year() -> None:
    result = assess_malformed_title_surface(
        "{policy_name}, 2025년 조례 제정으로 시작합니다",
        {
            "contextAnalysis": {
                "source_contract": {
                    "answer_type": "implementation_plan",
                    "forbidden_inferred_actions": ["2025년"],
                }
            }
        },
    )

    assert result["passed"] is False
    assert result["issue"] == "source_contract_forbidden_title"


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


def _quality_paragraph(topic: str = "{policy_name}") -> str:
    return (
        f"{topic}은 원문에서 제시된 실행수단을 중심으로 설명해야 합니다. "
        "첫 문장은 핵심 주어를 분명히 세우고 독자가 바로 답을 알 수 있어야 합니다. "
        "마지막 문장은 실행 의미와 다음 행동을 연결해 문단을 완성합니다."
    )


def _quality_content(*, h2_1: str, h2_2: str, first_body_sentence: str | None = None) -> str:
    intro = "".join(f"<p>{_quality_paragraph('{policy_name}')}</p>" for _ in range(3))
    body1_first = first_body_sentence or _quality_paragraph("첫 번째 실행수단")
    body1 = (
        f"<h2>{h2_1}</h2>"
        f"<p>{body1_first}</p>"
        f"<p>{_quality_paragraph('두 번째 근거')}</p>"
        f"<p>{_quality_paragraph('세 번째 의미')}</p>"
    )
    body2 = (
        f"<h2>{h2_2}</h2>"
        f"<p>{_quality_paragraph('다른 실행수단')}</p>"
        f"<p>{_quality_paragraph('구체 근거')}</p>"
        f"<p>{_quality_paragraph('실행 효과')}</p>"
    )
    return intro + body1 + body2


def _length_spec() -> dict:
    return {
        "min_chars": 1,
        "max_chars": 4000,
        "expected_h2": 2,
        "total_sections": 3,
        "body_sections": 1,
        "per_section_min": 1,
        "per_section_max": 2000,
    }


# synthetic_fixture
def test_content_validator_rejects_repeated_generic_h2_family() -> None:
    validator = ContentValidator()
    result = validator.validate(
        _quality_content(
            h2_1="정책, 제도 기반 세웁니다",
            h2_2="사업, 제도 기반 세웁니다",
        ),
        _length_spec(),
    )

    assert result["passed"] is False
    assert result["code"] == "H2_GENERIC_FAMILY_REPEAT"


# synthetic_fixture
def test_content_validator_rejects_fragmented_h2_prefix() -> None:
    validator = ContentValidator()
    result = validator.validate(
        _quality_content(
            h2_1="형 정책, 시작 이유는?",
            h2_2="{policy_name} 실행 방안입니다",
        ),
        _length_spec(),
        user_keywords=["{policy_name}"],
    )

    assert result["passed"] is False
    assert result["code"] == "H2_TEXT_FRAGMENT"


# synthetic_fixture
def test_content_validator_rejects_thin_one_sentence_paragraph() -> None:
    validator = ContentValidator()
    thin = "{policy_name}은 원문 실행수단을 중심으로 설명해야 합니다."
    result = validator.validate(
        _quality_content(
            h2_1="{policy_name} 실행 방안입니다",
            h2_2="{policy_name} 추진 근거입니다",
            first_body_sentence=thin,
        ),
        _length_spec(),
        user_keywords=["{policy_name}"],
    )

    assert result["passed"] is False
    assert result["code"] == "P_THIN"


# synthetic_fixture
def test_section_opening_dependency_uses_morphological_detector() -> None:
    issue = detect_dependent_section_opening(
        "이는 원문 실행수단을 앞 문맥에 기대어 설명하는 문장입니다."
    )

    assert issue["detected"] is True
    assert issue["reason"] in {
        "deictic_reference_opening",
        "contextual_reference_opening",
    }


# synthetic_fixture
def test_content_validator_rejects_dependent_section_opening() -> None:
    validator = ContentValidator()
    dependent = (
        "이는 원문 실행수단을 앞 문맥에 기대어 설명하는 문장입니다. "
        "첫 문장이 독립 주어 없이 시작하면 검색 답변성이 약해집니다. "
        "따라서 정책명이나 실행수단을 주어로 다시 세워야 합니다."
    )
    result = validator.validate(
        _quality_content(
            h2_1="{policy_name} 실행 방안입니다",
            h2_2="{policy_name} 추진 근거입니다",
            first_body_sentence=dependent,
        ),
        _length_spec(),
        user_keywords=["{policy_name}"],
    )

    assert result["passed"] is False
    assert result["code"] == "SECTION_OPENING_DEPENDENT_REFERENCE"


# synthetic_fixture
def test_context_analyzer_extracts_solar_profit_source_contract() -> None:
    analyzer = ContextAnalyzer(model_name="test-model")
    stance = (
        "신재생에너지 개발이익 공유 정책은 공약이기도 합니다. "
        "'{policy_name}'의 지역 버전을 추진할 근거를 마련하겠습니다. "
        "관내 일조량을 분석해 '햇빛지도'를 만들고 공영주차장이나 공공기관 옥상 등 "
        "태양광 발전시설 설치에 적합한 지역과 수익성을 분석하는 용역 예산을 확보하겠습니다. "
        "이익을 지역 주민과 함께 나눌 이익공유형 기본소득 모델을 설계하고 {region}부터 점진 추진하겠습니다."
    )

    analysis = analyzer._augment_execution_plan({}, stance_text=stance)
    contract = analysis["source_contract"]

    assert contract["primary_keyword"] == "{policy_name}"
    assert "햇빛지도 제작" in contract["required_source_facts"]
    assert "관내 일조량 분석" in contract["required_source_facts"]
    assert "입지·수익성 분석 용역 추진" in contract["execution_items"]
    assert "개발이익 주민 공유" in contract["execution_items"]
    assert "{region}부터 점진 추진" in contract["source_sequence_items"]
    assert "AI" in contract["forbidden_inferred_actions"]


# synthetic_fixture
def test_content_validator_rejects_detached_leadership_generalization() -> None:
    validator = ContentValidator()
    content = (
        "<p>{policy_name}은 햇빛지도와 조례 제정을 중심으로 추진해야 합니다. "
        "원문 실행수단을 먼저 배치해야 글의 초점이 살아납니다. "
        "지역 주민에게 돌아가는 이익 공유가 핵심입니다.</p>"
        "<h2>{policy_name} 실행 방안입니다</h2>"
        f"<p>{_quality_paragraph('햇빛지도')}</p>"
        "<p>AI와 로봇 기술 발전은 노동의 종말을 앞당기는 시대 변화입니다. "
        "기본소득은 구매력 상실을 막는 거시경제 해법입니다. "
        "이 문단은 원문 실행수단과 직접 연결되지 않았습니다.</p>"
        f"<p>{_quality_paragraph('조례 제정')}</p>"
    )
    issue = validator._validate_source_contract(
        content,
        {
            "source_contract": {
                "answer_type": "implementation_plan",
                "primary_keyword": "{policy_name}",
                "required_source_facts": ["햇빛지도 제작", "조례 제정"],
                "execution_items": ["이익공유형 기본소득 모델 설계"],
                "source_sequence_items": ["햇빛지도 제작", "조례 제정"],
                "forbidden_inferred_actions": [],
            }
        },
    )

    assert issue is not None
    assert issue["code"] == "LEADERSHIP_DETACHED"
