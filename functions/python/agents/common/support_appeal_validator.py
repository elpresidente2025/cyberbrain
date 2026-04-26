"""support_appeal_writing 전용 post-generation validator.

AEO_ANSWER_FIRST_METHODS에서 제외된 자리에 들어가는 장르 전용 rubric.
4개 검사: CTA 존재 / 질문형 H2 0 / 독립 정책 H2 0 / 정책 수치 ≤ 2.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_H2_RE = re.compile(r"<h2>(.*?)</h2>", re.DOTALL)
_QUESTION_TAIL_RE = re.compile(r"(?:\?|까\??|나요\??|는가\??)$")

_POLICY_KEYWORD_RE = re.compile(
    r"(조례|예산|국비|시범사업|로드맵|법안|발의|시스템|플랫폼|"
    r"구축|도입|확대|지원|공약|정책|사업)"
)
_NUMERIC_RE = re.compile(r"\d+\s*(?:억|만|천|건|개|명|대|곳|%|퍼센트)")

_CTA_RE = re.compile(
    r"(지지해\s*주|한\s*표\s*(?:부탁|주십시오|주세요)|기회를\s*주|투표\s*부탁|"
    r"성원\s*부탁|함께해\s*주|선택해\s*주|소중한\s*한\s*표|"
    r"맡겨\s*주|힘을\s*실어\s*주|도와\s*주|밀어\s*주)"
)

_DONATION_FOOTER_PATTERNS = [
    re.compile(r"\n\s*(?:[가-힣]+(?:은행|금고|뱅크|저축은행))\s+[\d\-]+.*$", re.DOTALL),
    re.compile(r"\n\s*\*\s*본인의\s*실명.*$", re.DOTALL),
    re.compile(r"\n\s*\*\s*연간\s*\d+\s*만원.*$", re.DOTALL),
    re.compile(r"\n\s*\*\s*\d+인당\s*연간.*$", re.DOTALL),
]


def _strip_donation_footer(content: str) -> str:
    """후원 안내 블록(은행·계좌, 실명·세액공제 안내)을 제거.

    후원 안내는 generation 단계 이후 고정 블록으로 붙는 경우가 많아
    validator의 NUMERIC 검사에서 false positive를 일으킨다."""
    cleaned = content
    for pattern in _DONATION_FOOTER_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


def validate_support_appeal_writing(content: str) -> Dict[str, Any]:
    """support_appeal 본문 4개 게이트 검증. 각 게이트는 issue 코드 발급."""
    issues: List[str] = []
    content = _strip_donation_footer(content)

    headings = [h.strip() for h in _H2_RE.findall(content)]

    # 1. 질문형 H2 0개
    question_h2 = [h for h in headings if h.endswith("?") or _QUESTION_TAIL_RE.search(h)]
    if question_h2:
        issues.append(f"SUPPORT_APPEAL_QUESTION_H2:{len(question_h2)}")

    # 2. 독립 정책 H2 0개
    policy_h2 = [h for h in headings if _POLICY_KEYWORD_RE.search(h)]
    if policy_h2:
        issues.append(f"SUPPORT_APPEAL_POLICY_H2:{len(policy_h2)}")

    # 3. 정책 수치 ≤ 2 (본문 전체)
    numerics = _NUMERIC_RE.findall(content)
    if len(numerics) > 2:
        issues.append(f"SUPPORT_APPEAL_NUMERIC_OVERLOAD:{len(numerics)}")

    # 4. CTA 존재 — 마지막 </h2> 닫힌 이후 본문에 CTA 어휘 1+
    last_h2_close = content.rfind("</h2>")
    tail = content[last_h2_close + 5:] if last_h2_close >= 0 else content
    if not _CTA_RE.search(tail):
        issues.append("SUPPORT_APPEAL_CTA_MISSING")

    return {
        "passed": not issues,
        "issues": issues,
        "h2_count": len(headings),
        "question_h2_count": len(question_h2),
        "policy_h2_count": len(policy_h2),
        "numeric_count": len(numerics),
    }
