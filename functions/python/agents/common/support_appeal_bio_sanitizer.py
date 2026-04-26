"""support_appeal 전용 authorBio 정화기.

지지 호소문에서 authorBio가 정책 카드 묶음으로 LLM에 그대로 주입되는 누수
경로를 차단한다. 라인 단위가 아닌 문장 단위로 처리해 정책 구절과 정체성
구절이 섞인 문장에서도 정체성을 보존한다.

원칙:
- 특정 정책 브랜드명을 코드에 박지 않는다 (범용성). 구조적 정책 패턴(~바우처,
  ~수당, ~사업, 조례, 예산 등)만 검사한다.
- 보존이 기본값. 정체성 마커(직책·활동 동사)가 있으면 정책 언급이 있어도 KEEP.
- 정체성 마커 0 + 구조적 정책 패턴 1+ 인 문장만 DROP.
"""

from __future__ import annotations

import re

_IDENTITY_MARKERS = re.compile(
    r"(위원장|부위원장|의원|예비후보|후보|의장|시장|도지사|구청장|군수|"
    r"단장|대표|회장|위원|사무국장|처장|이사장|간사|총무|"
    r"활동(?:하|했|함|중)|"
    r"역임|재직|근무|봉사|헌신|"
    r"태어나|자랐|살아|살아오|거주)"
)

_POLICY_STRUCTURAL = re.compile(
    r"(바우처|수당|지원금|보조금|"
    r"조례|예산\s*확보|국비|시범사업|법안\s*발의|"
    r"제도화|로드맵|공약\s*이행|"
    r"추진(?:한다|합니다|하겠|할|중)|"
    r"도입(?:한다|합니다|하겠|할|을)|"
    r"지급(?:한다|합니다|하겠|할|을|과)|"
    r"구축(?:한다|합니다|하겠|할)|"
    r"확대(?:한다|합니다|하겠|할))"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def sanitize_support_appeal_author_bio(text: str) -> str:
    """authorBio에서 정책 카드 문장만 골라 제거하고 정체성 문장은 보존한다.

    문장 단위로 분리해 다음 규칙을 적용:
    - 정체성 마커 1+ 있으면 KEEP (정책 언급이 섞여 있어도 보존)
    - 정체성 마커 0 + 정책 구조 마커 1+ → DROP
    - 둘 다 0인 중립 문장은 KEEP

    빈 입력은 빈 문자열 반환. 정화 후 너무 짧아져도 fallback을 만들지 않는다
    (정책 위주 bio는 그 자체가 신호이며, 프롬프트의 다른 소재가 메운다).
    """
    if not text or not text.strip():
        return ""

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    kept = []
    for sentence in sentences:
        has_identity = _IDENTITY_MARKERS.search(sentence) is not None
        has_policy = _POLICY_STRUCTURAL.search(sentence) is not None

        if has_identity:
            kept.append(sentence)
        elif has_policy:
            continue
        else:
            kept.append(sentence)

    return " ".join(kept).strip()
