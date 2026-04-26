from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import topic_classifier
from handlers.generate_posts_pkg import pipeline as generate_pipeline


def test_classify_topic_prefers_topic_for_primary_category() -> None:
    result = asyncio.run(topic_classifier.classify_topic("부산 교통 민원 해결 방안"))

    assert result["category"] == "local-issues"
    assert result["writingMethod"] == "analytical_writing"


def test_classify_topic_refines_policy_topic_with_stance_text() -> None:
    result = asyncio.run(
        topic_classifier.classify_topic(
            "기초연금 정책",
            stance_text="기초연금 신청 방법과 지원 대상을 쉽게 설명드리겠습니다.",
        )
    )

    assert result["category"] == "educational-content"
    assert result["subCategory"] == "policy_explanation"
    assert result["writingMethod"] == "logical_writing"


def test_resolve_request_intent_uses_only_first_instruction_as_secondary_signal() -> None:
    result = asyncio.run(
        topic_classifier.resolve_request_intent(
            "기초연금 정책",
            {
                "category": "",
                "instructions": [
                    "기초연금 신청 방법과 지원 대상을 쉽게 설명드리겠습니다.",
                    "오늘 간담회 결과와 예산 확보 성과를 보고드립니다.",
                ],
            },
        )
    )

    assert result["category"] == "educational-content"
    assert result["subCategory"] == "policy_explanation"


def test_resolve_request_category_uses_stance_text_when_category_missing() -> None:
    topic, category, sub_category = generate_pipeline._resolve_request_category(
        {
            "topic": "기초연금 정책",
            "instructions": [
                "기초연금 신청 방법과 지원 대상을 쉽게 설명드리겠습니다.",
                "오늘 간담회 결과와 예산 확보 성과를 보고드립니다.",
            ],
        }
    )

    assert topic == "기초연금 정책"
    assert category == "educational-content"
    assert sub_category == "policy_explanation"


def test_refine_with_stance_reclassifies_non_issue_policy_manifesto_out_of_current_affairs() -> None:
    primary = {
        "category": "current-affairs",
        "subCategory": "",
        "writingMethod": "critical_writing",
        "confidence": 0.78,
        "source": "llm_topic",
    }

    result = topic_classifier.refine_with_stance(
        primary,
        (
            "계양테크노밸리 완성과 지역화폐 부활, 이익공유형 기본소득 도입을 추진하겠습니다. "
            "예산 확보와 제도 개선으로 구체적인 정책 실행 계획을 보여드리겠습니다."
        ),
    )

    assert result["category"] == "policy-proposal"
    assert result["writingMethod"] == "logical_writing"
    assert result["source"] == "llm_topic+stance"


def test_resolve_request_intent_detects_support_appeal_from_topic_only() -> None:
    """topic에 '예비후보'+'약속드립'이 있고 stanceText가 짧아도 support_appeal 라우팅."""
    result = asyncio.run(
        topic_classifier.resolve_request_intent(
            "계양구의원 예비후보 홍길동, 주민 삶에 실질적 변화 약속드립니다",
            {
                "category": "daily-communication",
                "subCategory": "",
                "stanceText": "계산동과 작전동은 오랜 시간 활력을 잃어가고 있습니다.",
            },
        )
    )
    assert result["subCategory"] == "support_appeal"
    assert result["writingMethod"] == "support_appeal_writing"


def test_resolve_request_intent_detects_support_appeal_strong_pattern_in_topic() -> None:
    """topic에 강한 CTA('소중한 한 표')가 있으면 support_appeal 라우팅."""
    result = asyncio.run(
        topic_classifier.resolve_request_intent(
            "소중한 한 표 부탁드립니다 — 샘플구의원 예비후보 홍길동",
            {"category": "daily-communication", "subCategory": ""},
        )
    )
    assert result["subCategory"] == "support_appeal"


def test_resolve_request_intent_does_not_misroute_policy_heavy_topic() -> None:
    """topic이 '예비후보'를 포함해도 정책어가 3개 이상이면 support_appeal 아님."""
    result = asyncio.run(
        topic_classifier.resolve_request_intent(
            "샘플구의원 예비후보 홍길동의 조례·예산·공약 로드맵 발표",
            {
                "category": "daily-communication",
                "subCategory": "",
                "stanceText": "구청 예산 확보와 공약 추진 계획을 말씀드립니다.",
            },
        )
    )
    assert result["subCategory"] != "support_appeal"
