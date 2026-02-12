"""
Evaluation Service - LLM-as-Judge 기반 콘텐츠 품질 평가.

Node.js `services/evaluation/index.js`의 Python 포팅 버전이다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from agents.common.gemini_client import generate_content

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """당신은 정치인 블로그 콘텐츠 품질 평가 전문가입니다.
다음 콘텐츠를 평가하고 JSON 형식으로 점수를 매겨주세요.

## 평가 기준 (각 1-10점)

1. **relevance** (주제 적합성): 주어진 주제를 잘 다루고 있는가?
2. **readability** (가독성): 문장이 자연스럽고 읽기 쉬운가?
3. **structure** (구조): 서론-본론-결론 구조가 명확한가?
4. **authenticity** (진정성): 정치인의 진솔한 목소리가 느껴지는가?
5. **engagement** (참여 유도): 독자의 공감과 반응을 이끌어낼 수 있는가?

## 콘텐츠 정보
- 카테고리: {category}
- 주제: {topic}
- 작성자: {author}

## 콘텐츠
{content}

## 응답 형식 (JSON만 출력)
{
  "scores": {
    "relevance": 8,
    "readability": 7,
    "structure": 8,
    "authenticity": 6,
    "engagement": 7
  },
  "overallScore": 7.2,
  "strengths": ["강점1", "강점2"],
  "improvements": ["개선점1", "개선점2"],
  "summary": "한 줄 평가"
}"""


def _extract_first_balanced_json(text: str) -> str | None:
    if not text:
        return None

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _normalize_score(score: Any) -> float:
    try:
        value = float(score)
    except Exception:
        value = 5.0
    return min(10.0, max(1.0, value))


def get_default_evaluation() -> Dict[str, Any]:
    return {
        "scores": {
            "relevance": 5,
            "readability": 5,
            "structure": 5,
            "authenticity": 5,
            "engagement": 5,
        },
        "overallScore": 5,
        "strengths": [],
        "improvements": [],
        "summary": "자동 평가 미수행",
        "evaluated": False,
    }


def parse_evaluation_response(response_text: str) -> Dict[str, Any]:
    try:
        json_text = _extract_first_balanced_json(response_text)
        if not json_text:
            # 마지막 fallback: 정규식
            match = re.search(r"\{[\s\S]*\}", response_text or "")
            json_text = match.group(0) if match else None
        if not json_text:
            raise ValueError("JSON not found in response")

        parsed = json.loads(json_text)
        scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
        overall_score = parsed.get("overallScore")
        if overall_score is None:
            raise ValueError("Invalid evaluation format")

        return {
            "scores": {
                "relevance": _normalize_score(scores.get("relevance")),
                "readability": _normalize_score(scores.get("readability")),
                "structure": _normalize_score(scores.get("structure")),
                "authenticity": _normalize_score(scores.get("authenticity")),
                "engagement": _normalize_score(scores.get("engagement")),
            },
            "overallScore": _normalize_score(overall_score),
            "strengths": (
                parsed.get("strengths", [])[:3]
                if isinstance(parsed.get("strengths"), list)
                else []
            ),
            "improvements": (
                parsed.get("improvements", [])[:3]
                if isinstance(parsed.get("improvements"), list)
                else []
            ),
            "summary": parsed.get("summary") or "평가 완료",
            "evaluated": True,
        }
    except Exception as exc:
        logger.warning("[Evaluation] 응답 파싱 실패: %s", exc)
        return get_default_evaluation()


def evaluate_content(params: Dict[str, Any]) -> Dict[str, Any]:
    content = str((params or {}).get("content", "") or "")
    category = str((params or {}).get("category", "") or "일반")
    topic = str((params or {}).get("topic", "") or "미지정")
    author = str((params or {}).get("author", "") or "작성자")

    if len(content) < 100:
        logger.warning("[Evaluation] 콘텐츠가 너무 짧아 평가 스킵")
        return get_default_evaluation()

    try:
        truncated_content = content[:3000] + ("...(이하 생략)" if len(content) > 3000 else "")
        prompt = (
            EVALUATION_PROMPT.replace("{category}", category)
            .replace("{topic}", topic)
            .replace("{author}", author)
            .replace("{content}", truncated_content)
        )

        response_text = generate_content(
            prompt,
            model_name="gemini-2.5-flash",
            temperature=0.3,
            max_output_tokens=500,
            response_mime_type="application/json",
            retries=2,
        )
        evaluation = parse_evaluation_response(response_text)
        logger.info(
            "[Evaluation] 평가 완료: overallScore=%s summary=%s",
            evaluation.get("overallScore"),
            evaluation.get("summary"),
        )
        return evaluation
    except Exception as exc:
        logger.warning("[Evaluation] 평가 실패: %s", exc)
        return get_default_evaluation()


def meets_quality_threshold(evaluation: Dict[str, Any] | None, threshold: float = 7.0) -> bool:
    if not evaluation or not evaluation.get("evaluated"):
        return False
    try:
        return float(evaluation.get("overallScore", 0)) >= float(threshold)
    except Exception:
        return False

