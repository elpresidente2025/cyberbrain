"""배경지시문에서 필수 키워드를 추출하는 유틸리티.

Node.js `functions/services/posts/keyword-extractor.js` 포팅.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence


def _normalize_instructions(instructions: str | Sequence[str] | None) -> str:
    if not instructions:
        return ""
    if isinstance(instructions, str):
        return instructions
    if isinstance(instructions, Iterable):
        return " ".join(str(item) for item in instructions if item)
    return str(instructions)


def extract_keywords_from_instructions(instructions: str | Sequence[str] | None) -> List[str]:
    """배경정보에서 검색/검증에 필요한 키워드를 추출한다.

    Args:
        instructions: 문자열 또는 문자열 배열.

    Returns:
        중복 제거된 키워드 리스트.
    """
    text = _normalize_instructions(instructions)
    if not text:
        return []

    keywords: list[str] = []

    patterns = [
        # 1) 숫자 + 단위
        r"[0-9]+여?[명개회건차명월일년원]",
        # 2) 인명 + 직책
        r"[가-힣]{2,4}\s+(?:경기도당위원장|국회의원|위원장|의원|시장|도지사|장관|총리|대통령)",
        # 3) 조직명
        r"[가-힣]{2,}(?:도당|시당|구당|위원회|재단|협회|연합|위원회)",
        # 4) 이벤트명
        r"[가-힣]{2,}(?:대회|행사|토론회|간담회|설명회|세미나|워크숍|회의|집회|축제)",
        # 5) 지명
        r"[가-힣]{2,}(?:특별시|광역시|도|시|군|구|읍|면|동)",
        # 6) 연도
        r"20[0-9]{2}년",
        # 7) 정책/법안명
        r"[가-힣]{2,}(?:법|조례|정책|사업|계획|방안)",
    ]

    # 1~7번 순서 유지
    for idx, pattern in enumerate(patterns, start=1):
        matches = re.findall(pattern, text)
        if matches:
            keywords.extend(matches)

        # 2번 패턴은 "이름만"도 별도 추가
        if idx == 2 and matches:
            for match in matches:
                name_only = re.match(r"([가-힣]{2,4})\s+", match)
                if name_only and name_only.group(1):
                    keywords.append(name_only.group(1))

    # 순서를 보존하면서 중복 제거
    seen: set[str] = set()
    deduped: list[str] = []
    for keyword in keywords:
        if keyword in seen:
            continue
        seen.add(keyword)
        deduped.append(keyword)
    return deduped


# JS 호환 별칭
extractKeywordsFromInstructions = extract_keywords_from_instructions


__all__ = [
    "extract_keywords_from_instructions",
    "extractKeywordsFromInstructions",
]

