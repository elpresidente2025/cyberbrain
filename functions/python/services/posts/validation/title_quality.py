"""?? ?? ??."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

from agents.common.editorial import TITLE_SPEC
from agents.common.fact_guard import extract_numeric_tokens

def validate_title_quality(
    title: str,
    user_keywords: Optional[Sequence[str]] = None,
    content: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    strict_facts = options.get("strictFacts") is True
    user_keywords = list(user_keywords or [])

    if not title:
        return {"passed": True, "issues": [], "details": {}}

    issues: list[Dict[str, Any]] = []
    title_min_length = int(TITLE_SPEC['hardMin'])
    title_max_length = int(TITLE_SPEC['hardMax'])
    details: Dict[str, Any] = {
        "length": len(title),
        "maxLength": title_max_length,
        "keywordPosition": None,
        "abstractExpressions": [],
        "hasNumbers": False,
    }

    if len(title) < title_min_length:
        issues.append(
            {
                "type": "title_too_short",
                "severity": "critical",
                "description": f"제목이 너무 짧음 ({len(title)}자)",
                "instruction": f"{title_min_length}자 이상으로 구체적인 내용을 포함하여 작성하세요. 단순 키워드 나열 금지.",
            }
        )

    if len(title) > title_max_length:
        issues.append(
            {
                "type": "title_length",
                "severity": "critical",
                "description": f"제목 {len(title)}자 → {title_max_length}자 초과",
                "instruction": f"{title_max_length}자 이내로 줄이세요. 불필요한 조사, 부제목(:, -) 제거.",
            }
        )

    if user_keywords:
        primary_kw = user_keywords[0]
        kw_index = title.find(primary_kw)
        details["keywordPosition"] = kw_index

        if kw_index == -1:
            issues.append(
                {
                    "type": "keyword_missing",
                    "severity": "high",
                    "description": f"핵심 키워드 \"{primary_kw}\" 제목에 없음",
                    "instruction": f"\"{primary_kw}\"를 제목 앞부분에 포함하세요.",
                }
            )
        elif kw_index > 10:
            issues.append(
                {
                    "type": "keyword_position",
                    "severity": "medium",
                    "description": f"키워드 \"{primary_kw}\" 위치 {kw_index}자 → 너무 뒤쪽",
                    "instruction": "핵심 키워드는 제목 앞쪽 8자 이내에 배치하세요 (앞쪽 1/3 법칙).",
                }
            )

        clean_title = re.sub(r"\s+", "", title)
        clean_kw = re.sub(r"\s+", "", primary_kw)
        if clean_kw and clean_kw in clean_title and len(clean_title) <= len(clean_kw) + 4:
            issues.append(
                {
                    "type": "title_too_generic",
                    "severity": "critical",
                    "description": "제목이 키워드와 너무 유사함 (단순 명사형)",
                    "instruction": "서술어인 \"현안 진단\", \"핵심 분석\", \"이슈 점검\" 등을 반드시 포함하여 구체화하세요.",
                }
            )

    if content:
        title_numeric_tokens = extract_numeric_tokens(title)
        content_numeric_tokens = extract_numeric_tokens(content)
        if title_numeric_tokens:
            if not content_numeric_tokens:
                issues.append(
                    {
                        "type": "title_number_mismatch",
                        "severity": "high",
                        "description": "제목에 수치가 있으나 본문에 근거 수치 없음",
                        "instruction": "본문에 실제로 있는 수치/단위를 제목에 사용하세요.",
                    }
                )
            else:
                missing_tokens = [token for token in title_numeric_tokens if token not in content_numeric_tokens]
                if missing_tokens:
                    issues.append(
                        {
                            "type": "title_number_mismatch",
                            "severity": "high",
                            "description": f"제목 수치/단위가 본문과 불일치: {', '.join(missing_tokens)}",
                            "instruction": "본문에 실제로 등장하는 수치/단위를 제목에 그대로 사용하세요.",
                        }
                    )

    abstract_patterns = [
        ("비전", r"비전"),
        ("혁신", r"혁신"),
        ("발전", r"발전"),
        ("노력", r"노력"),
        ("최선", r"최선"),
        ("약속", r"약속"),
        ("다짐", r"다짐"),
        ("함께", r"함께"),
        ("확충", r"확충"),
        ("개선", r"개선"),
        ("추진", r"추진"),
        ("시급", r"시급"),
        ("강화", r"강화"),
        ("증진", r"증진"),
        ("도모", r"도모"),
        ("향상", r"향상"),
        ("활성화", r"활성화"),
        ("선도", r"선도"),
        ("선진", r"선진"),
        ("미래", r"미래"),
    ]
    found_abstract = [word for word, pattern in abstract_patterns if re.search(pattern, title)]
    if found_abstract:
        details["abstractExpressions"] = found_abstract
        issues.append(
            {
                "type": "abstract_expression",
                "severity": "medium",
                "description": f"추상적 표현 사용: {', '.join(found_abstract)}",
                "instruction": "구체적 수치나 사실로 대체하세요. 예: \"발전\" → \"40% 증가\", \"비전\" → \"3대 핵심 정책\"",
            }
        )

    details["hasNumbers"] = bool(re.search(r"\d", title))
    if (not details["hasNumbers"]) and issues and (not strict_facts):
        issues.append(
            {
                "type": "no_numbers",
                "severity": "low",
                "description": "숫자/구체적 데이터 없음",
                "instruction": "가능하면 숫자를 포함하세요. 예: \"3대 정책\", \"120억 확보\", \"40% 개선\"",
            }
        )

    has_blocking_issue = any(issue.get("severity") in {"critical", "high"} for issue in issues)
    return {"passed": not has_blocking_issue, "issues": issues, "details": details}
