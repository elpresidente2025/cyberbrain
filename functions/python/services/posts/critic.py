"""Critic Agent - 원고 지침 준수 검토 모듈.

Node.js `functions/services/posts/critic.js` 포팅.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)


VIOLATION_TYPES: Dict[str, Dict[str, str]] = {
    "C1": {"id": "C1", "name": "선거법 위반", "severity": "HARD"},
    "C2_A": {"id": "C2-a", "name": "팩트 오류", "severity": "HARD"},
    "C2_B": {"id": "C2-b", "name": "해석 과잉", "severity": "SOFT"},
    "C3": {"id": "C3", "name": "심각한 반복", "severity": "HARD"},
    "C4": {"id": "C4", "name": "구조 미완", "severity": "SOFT"},
    "C5": {"id": "C5", "name": "톤 이탈", "severity": "SOFT"},
    "C6": {"id": "C6", "name": "유권자 관점", "severity": "POLITICAL"},
}


def build_critic_prompt(
    *,
    draft: str,
    rag_context: Optional[str],
    guidelines: Optional[str],
    status: Optional[str],
    topic: Optional[str],
    author_name: Optional[str],
) -> str:
    _ = topic
    return f"""당신은 두 가지 역할을 동시에 수행합니다:

【역할 1: 엄격한 편집장】
- 지침 위반 사항을 빠짐없이 찾아내는 검수관
- 팩트 오류에 무관용

【역할 2: 까다로운 유권자】
- "{author_name or '이 의원'}님을 지지할지 고민하는 중립적 시민"
- 진정성이 느껴지는지, 기계적 홍보는 아닌지 판단

═══════════════════════════════════════
[검토 대상 초안]
═══════════════════════════════════════
{draft}

═══════════════════════════════════════
[사실 확인용 참조 데이터 (RAG)]
이 데이터에 있는 내용만 '팩트'로 인정됩니다.
═══════════════════════════════════════
{rag_context or '(제공된 참조 데이터 없음 - 일반적 내용만 허용)'}

═══════════════════════════════════════
[적용된 핵심 지침]
═══════════════════════════════════════
{guidelines or '(기본 지침 적용)'}

═══════════════════════════════════════
[검토 체크리스트]
═══════════════════════════════════════

🔴 HARD FAIL (반드시 수정)
━━━━━━━━━━━━━━━━━━━━━━━━
C1. 선거법 위반 (현재 상태: {status or '미지정'})
    → 준비/현역이면 "~하겠습니다" 공약 표현 금지
    → 예: 추진하겠습니다, 만들겠습니다, 실현하겠습니다 등

C2-a. 팩트 오류
    → 수치, 날짜, 지역명, 사업명이 [참조 데이터]와 다르면 위반
    → 예: "100억 투자" → 참조에 "50억"만 있으면 위반
    → [참조 데이터]가 없으면 구체적 수치/사업명 사용 자체가 위반

C3. 심각한 반복
    → 같은 문장이 2회 이상 등장하면 위반
    → 같은 내용을 표현만 바꿔 반복해도 위반

🟡 SOFT FAIL (개선 권고)
━━━━━━━━━━━━━━━━━━━━━━━━
C2-b. 해석 과잉
    → [참조 데이터]에 없는 공약/계획을 과도하게 확대 해석
    → 단, 일반적 인사말/연결어는 허용

C4. 구조 미완
    → 글이 자연스럽게 끝나지 않음
    → 끝인사 후 본문이 다시 시작됨

C5. 톤 이탈
    → 격식체 말투에서 벗어남
    → 비서관다운 품위 부족

🟢 POLITICAL REVIEW (정무적 검토)
━━━━━━━━━━━━━━━━━━━━━━━━
C6. 유권자 관점
    → "이 글이 진정성 있게 느껴지는가?"
    → "너무 기계적인 홍보문 같지 않은가?"
    → "유권자로서 공감이 가는가?"

═══════════════════════════════════════
[출력 형식 - 반드시 JSON만 출력]
═══════════════════════════════════════
```json
{{
  "passed": true 또는 false,
  "score": 0-100 사이 정수,
  "violations": [
    {{
      "id": "C1, C2-a, C2-b, C3, C4, C5, C6 중 하나",
      "severity": "HARD" 또는 "SOFT" 또는 "POLITICAL",
      "type": "위반 유형 이름",
      "location": "위치 (n번째 문단, 또는 구체적 위치)",
      "problematic": "문제가 된 원문 발췌 (30자 이내)",
      "suggestion": "구체적인 수정 제안"
    }}
  ],
  "politicalReview": {{
    "authenticity": "진정성 평가 (1줄)",
    "voterAppeal": "유권자 호소력 평가 (1줄)"
  }},
  "summary": "종합 평가 (1줄)"
}}
```

위반 사항이 없으면 "passed": true, "violations": [], "score": 100으로 응답하세요.
JSON 외의 다른 텍스트는 출력하지 마세요."""


def _extract_json_payload(response: str) -> Optional[Dict[str, Any]]:
    text = (response or "").strip()
    if not text:
        return None

    code_block = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    candidate = code_block.group(1).strip() if code_block else text

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    brace_match = re.search(r"\{[\s\S]*\}", candidate)
    if not brace_match:
        return None
    try:
        parsed = json.loads(brace_match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def parse_critic_report(response: str) -> Dict[str, Any]:
    try:
        report = _extract_json_payload(response) or {}
        if not isinstance(report.get("passed"), bool):
            report["passed"] = False
        if not isinstance(report.get("violations"), list):
            report["violations"] = []
        if not isinstance(report.get("score"), (int, float)):
            report["score"] = calculate_score(report)
        return report
    except Exception as exc:
        logger.error("Critic 응답 파싱 실패: %s", exc)
        logger.debug("Critic 원본 응답: %s", (response or "")[:500])
        return {
            "passed": False,
            "score": 50,
            "violations": [
                {
                    "id": "PARSE_ERROR",
                    "severity": "SOFT",
                    "type": "검토 오류",
                    "location": "전체",
                    "problematic": "파싱 실패",
                    "suggestion": "재검토 필요",
                }
            ],
            "politicalReview": {
                "authenticity": "평가 불가",
                "voterAppeal": "평가 불가",
            },
            "summary": "Critic 응답 파싱 실패",
        }


def calculate_score(critic_report: Dict[str, Any]) -> int:
    score = 100
    violations = critic_report.get("violations")
    if not isinstance(violations, list):
        return score

    for violation in violations:
        severity = str((violation or {}).get("severity") or "")
        if severity == "HARD":
            score -= 30
        elif severity == "SOFT":
            score -= 10
        elif severity == "POLITICAL":
            score -= 5
        else:
            score -= 5

    return max(0, min(100, score))


def has_hard_violations(critic_report: Dict[str, Any]) -> bool:
    violations = critic_report.get("violations")
    if not isinstance(violations, list):
        return False
    return any((item or {}).get("severity") == "HARD" for item in violations)


def should_retry(critic_report: Dict[str, Any]) -> bool:
    score = critic_report.get("score")
    score_value = int(score) if isinstance(score, (int, float)) else 0
    return has_hard_violations(critic_report) or score_value < 70


async def run_critic_review(
    *,
    draft: str,
    rag_context: Optional[str],
    guidelines: Optional[str],
    status: Optional[str],
    topic: Optional[str],
    author_name: Optional[str],
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    logger.info("Critic Agent 검토 시작")

    try:
        prompt = build_critic_prompt(
            draft=draft,
            rag_context=rag_context,
            guidelines=guidelines,
            status=status,
            topic=topic,
            author_name=author_name,
        )
        response = await generate_content_async(prompt, model_name=model_name, temperature=1.0)
        if not response:
            raise RuntimeError("Critic Agent 응답 없음")

        report = parse_critic_report(response)
        report["score"] = calculate_score(report)
        report["needsRetry"] = should_retry(report)

        logger.info(
            "Critic 검토 완료: %s (점수: %s)",
            "통과" if report.get("passed") else "위반 발견",
            report.get("score"),
        )
        return report

    except Exception as exc:
        logger.exception("Critic Agent 실행 실패: %s", exc)
        return {
            "passed": True,
            "score": 70,
            "violations": [],
            "politicalReview": {
                "authenticity": "검토 실패로 평가 불가",
                "voterAppeal": "검토 실패로 평가 불가",
            },
            "summary": "Critic 검토 중 오류 발생 - 기본 통과 처리",
            "needsRetry": False,
            "error": str(exc),
        }


def summarize_guidelines(status: Optional[str], topic: Optional[str]) -> str:
    _ = topic
    guidelines: List[str] = []
    if status in {"준비", "현역"}:
        guidelines.append('⚠️ 선거법: "~하겠습니다" 공약 표현 절대 금지')
    guidelines.append("📝 반복 금지: 같은 내용/문장 반복 불가")
    guidelines.append("✅ 완결성: 글은 자연스럽게 끝맺을 것")
    guidelines.append("🎯 팩트 준수: RAG 데이터에 없는 수치/사업명 사용 금지")
    return "\n".join(guidelines)


# JS 호환 별칭
buildCriticPrompt = build_critic_prompt
parseCriticReport = parse_critic_report
calculateScore = calculate_score
hasHardViolations = has_hard_violations
shouldRetry = should_retry
runCriticReview = run_critic_review
summarizeGuidelines = summarize_guidelines


__all__ = [
    "VIOLATION_TYPES",
    "build_critic_prompt",
    "parse_critic_report",
    "calculate_score",
    "has_hard_violations",
    "should_retry",
    "run_critic_review",
    "summarize_guidelines",
    "buildCriticPrompt",
    "parseCriticReport",
    "calculateScore",
    "hasHardViolations",
    "shouldRetry",
    "runCriticReview",
    "summarizeGuidelines",
]

