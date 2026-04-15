"""한국어 형태소 분석 공용 유틸 (kiwipiepy 기반).

목적:
- 정규식 나열로는 잡기 힘든 "미완결 종결 / 질문형 판정 / 명사구 파일업" 을
  형태소 태그 단위로 정확히 판정한다.
- kiwipiepy 초기화 실패 시에는 None 을 반환해 호출부가 regex fallback 으로
  우회할 수 있도록 한다 (배포 환경 문제로 라이브러리가 동작하지 않아도
  기존 regex 경로가 살아있어 시스템 전체가 멈추지 않게 한다).

소비처:
- agents/common/h2_guide.py (has_incomplete_h2_ending)
- agents/common/h2_scoring.py (_has_question_form, 명사구 hard-fail)
- (확장 가능) agents/common/title_hook_quality.py, stylometry/features/ 등
"""

from __future__ import annotations

import os
import re
import threading
from typing import Dict, Optional, Sequence, Tuple

_KIWI_LOCK = threading.Lock()
_KIWI_INSTANCE = None
_KIWI_INIT_FAILED = False


def _environment_is_kiwi_hostile() -> bool:
    """Kiwi C++ 백엔드가 현재 환경에서 안전하게 뜰 수 있는지 사전 판별.

    Windows 에서 홈 경로에 비ASCII 문자(한글 사용자명 등)가 포함되면 kiwipiepy
    의 모델 로더가 힙 손상(STATUS_HEAP_CORRUPTION) 으로 프로세스 전체를 터뜨린다.
    Python try/except 로는 잡히지 않으므로, 실제 Kiwi() 호출 전에 환경 변수로
    이 조건을 사전 검사해 해당 환경에서는 아예 생성하지 않고 None 을 반환한다.

    Cloud Functions(Linux, ASCII 경로) 프로덕션에는 영향 없음.
    """
    if os.name != "nt":
        return False
    for key in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        value = os.environ.get(key, "")
        if not value:
            continue
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            return True
    return False


def get_kiwi():
    """Kiwi 싱글톤을 lazy 초기화한다. 실패 시 None.

    Cloud Functions cold start 시 약 0.5~1초 소요. 첫 호출 이후에는 캐시됨.
    """
    global _KIWI_INSTANCE, _KIWI_INIT_FAILED
    if _KIWI_INSTANCE is not None:
        return _KIWI_INSTANCE
    if _KIWI_INIT_FAILED:
        return None
    if _environment_is_kiwi_hostile():
        _KIWI_INIT_FAILED = True
        return None
    with _KIWI_LOCK:
        if _KIWI_INSTANCE is not None:
            return _KIWI_INSTANCE
        if _KIWI_INIT_FAILED:
            return None
        try:
            from kiwipiepy import Kiwi  # type: ignore
            _KIWI_INSTANCE = Kiwi()
            return _KIWI_INSTANCE
        except Exception as err:  # pragma: no cover - defensive
            print(f"[korean_morph] kiwipiepy 초기화 실패 — regex fallback 사용: {err}")
            _KIWI_INIT_FAILED = True
            return None


_MAIN_PREDICATE_TAGS = frozenset({"VV", "VA", "VX", "VCP", "VCN"})
_NOUN_TAGS = frozenset({"NNG", "NNP", "NNB"})
_PARTICLE_TAGS = frozenset({"JKS", "JKO", "JKB", "JKG", "JKC", "JKV", "JKQ", "JX", "JC"})
_TRAILING_SKIP_TAGS = frozenset({"SF", "SP", "SS", "SW", "SO", "SE"})

# 질문 종결어미 form 화이트리스트 (EF 태그와 결합)
_QUESTION_EF_FORMS = frozenset(
    {
        "까", "까요", "ᆯ까", "ᆯ까요", "을까", "을까요",
        "나", "나요", "ᆫ가", "ᆫ가요", "은가", "은가요",
        "는가", "는가요", "는지", "ᆯ지", "을지",
        "니", "디", "소",
    }
)

# 의문 부사/대명사 — EC 종결이지만 의문 문맥 단서
_INTERROGATIVE_CUES = (
    "왜", "무엇", "무슨", "어떻게", "어떤", "어디",
    "언제", "누가", "누구", "얼마", "몇",
)

# EC 태그로 잡히지만 의문 종결 역할 가능한 form
_QUESTION_EC_FORMS = frozenset({"나", "니", "지", "까"})


def tokenize(text: str) -> Optional[list]:
    """Kiwi 로 tokenize. 실패 시 None."""
    kiwi = get_kiwi()
    if kiwi is None:
        return None
    try:
        return list(kiwi.tokenize(str(text or "")))
    except Exception as err:  # pragma: no cover
        print(f"[korean_morph] tokenize 실패: {err}")
        return None


def _last_content_token(tokens: Sequence) -> Optional[object]:
    """끝에서 구두점 등 공백성 태그를 건너뛰고 실제 내용 토큰을 반환."""
    for tok in reversed(tokens):
        if tok.tag in _TRAILING_SKIP_TAGS:
            continue
        return tok
    return None


def has_main_predicate(tokens: Sequence) -> bool:
    """문장에 진짜 용언(VV/VA/VX/VCP/VCN) 이 있는지.

    XSV/XSA(파생 접미사) 는 제외 — 이것만 있으면 여전히 종결이 필요하다.
    """
    return any(tok.tag in _MAIN_PREDICATE_TAGS for tok in tokens)


def has_final_ending(tokens: Sequence) -> bool:
    """EF(종결어미) 가 문장에 있는지."""
    return any(tok.tag == "EF" for tok in tokens)


def is_question_form(text: str) -> Optional[bool]:
    """H2 가 의문형인지.

    반환:
      True  — 의문형 확정
      False — 의문형 아님
      None  — Kiwi 불가, 호출부는 regex fallback 으로 가라
    """
    plain = str(text or "").strip()
    if not plain:
        return False
    if plain.rstrip().endswith("?"):
        return True

    tokens = tokenize(plain)
    if tokens is None:
        return None

    last = _last_content_token(tokens)
    if last is None:
        return False

    if last.tag == "EF" and last.form in _QUESTION_EF_FORMS:
        return True

    # EC 로 잡혔지만 의문 단서가 있으면 질문
    if last.tag == "EC" and last.form in _QUESTION_EC_FORMS:
        if any(cue in plain for cue in _INTERROGATIVE_CUES):
            return True

    return False


def is_incomplete_ending(text: str) -> Optional[bool]:
    """H2 가 한국어로 미완결인지.

    검출 케이스:
      1. 조사 단독 종결 (JKS/JKO/JKB/JKG/JKC/JKV/JX/JC) — "목소리가", "정치의"
      2. 관형형 전성어미 ETM 종결 — "더딘", "느린", "가는", "다할" (수식 대상 누락)
      3. 연결어미 EC 종결 — "비교하면", "달리고" (단, 의문 단서가 있으면 제외)

    NOTE: 순수 명사구 종결("책임", "절차", "현황")은 AEO 스타일의 합법적
    topic-label 패턴이므로 여기서 미완결로 치지 않는다. 원래의 regex fallback
    (`_H2_TRAILING_INCOMPLETE_ENDING_RE` 등) 이 남아 있으므로 그쪽이 계속 담당한다.

    반환:
      True  — 미완결
      False — 완결
      None  — Kiwi 불가, 호출부 fallback 필요
    """
    plain = str(text or "").strip()
    if not plain:
        return True

    # 의문부호로 끝나는 헤딩은 종결 구조 — 조사/어미 단독이어도 완결로 본다.
    if plain.rstrip().endswith("?"):
        return False

    tokens = tokenize(plain)
    if tokens is None:
        return None

    last = _last_content_token(tokens)
    if last is None:
        return True

    # 조사 단독 종결
    if last.tag in _PARTICLE_TAGS:
        return True

    # 관형형 전성어미 (수식 대상 누락)
    if last.tag == "ETM":
        return True

    # 연결어미 종결
    if last.tag == "EC":
        # 의문 단서 있으면 의문 보조 역할 — 미완결 아님
        if last.form in _QUESTION_EC_FORMS and any(
            cue in plain for cue in _INTERROGATIVE_CUES
        ):
            return False
        return True

    return False


_DECLARATIVE_EF_FORMS = frozenset({"다", "네", "지", "어", "야", "요", "죠"})

# 다짐/공약 종결 — EF 단독으로는 잘 안 잡히므로 surface regex 보조
_COMMITMENT_SURFACE_RE = re.compile(
    r"(겠습니다|하겠다|드리겠|드립니다|하겠습니다|올리겠|올립니다|약속드립|앞장서겠)\s*[.!?？!]*\s*$"
)
_COMMITMENT_EF_FORMS = frozenset({"겠", "ᆸ니다", "습니다"})


def classify_title_ending(title: str) -> Optional[Dict[str, str]]:
    """제목의 종결 형태를 형태소 분석으로 분류한다.

    반환:
      {
        'class': 'rhetorical_question' | 'real_question' | 'declarative'
               | 'commitment' | 'noun_end' | 'other',
        'form':  마지막 내용 토큰의 form (없으면 ""),
        'tag':   마지막 내용 토큰의 POS 태그 (없으면 ""),
      }
      None — Kiwi 초기화 실패. 호출부는 regex fallback 으로 내려가야 함.

    분류 규칙:
      1. commitment surface regex 매칭              → 'commitment'
      2. EF ∈ _QUESTION_EF_FORMS + 의문사 없음       → 'rhetorical_question'
      3. EF ∈ _QUESTION_EF_FORMS + 의문사 있음       → 'real_question'
      4. '?' 로 끝나는데 EF 가 위에 안 걸린 경우     → 'real_question' (보수)
      5. EF ∈ _COMMITMENT_EF_FORMS                   → 'commitment'
      6. EF ∈ _DECLARATIVE_EF_FORMS                  → 'declarative'
      7. 마지막 토큰 tag ∈ _NOUN_TAGS                → 'noun_end'
      8. 그 외                                       → 'other'
    """
    plain = str(title or "").strip()
    if not plain:
        return {"class": "other", "form": "", "tag": ""}

    tokens = tokenize(plain)
    if tokens is None:
        return None

    last = _last_content_token(tokens)
    last_form = last.form if last is not None else ""
    last_tag = last.tag if last is not None else ""

    # Commitment surface 매칭이 가장 강력 — EF 가 "ᆸ니다" 로 잡혀도 공약 톤이면 우선
    if _COMMITMENT_SURFACE_RE.search(plain):
        return {"class": "commitment", "form": last_form, "tag": last_tag}

    if last is not None and last.tag == "EF":
        if last.form in _QUESTION_EF_FORMS:
            if any(cue in plain for cue in _INTERROGATIVE_CUES):
                return {"class": "real_question", "form": last_form, "tag": last_tag}
            return {"class": "rhetorical_question", "form": last_form, "tag": last_tag}
        if last.form in _COMMITMENT_EF_FORMS:
            return {"class": "commitment", "form": last_form, "tag": last_tag}
        if last.form in _DECLARATIVE_EF_FORMS:
            return {"class": "declarative", "form": last_form, "tag": last_tag}

    # EC 로 잡혔지만 의문 단서가 있으면 real_question 으로 승격
    if last is not None and last.tag == "EC" and last.form in _QUESTION_EC_FORMS:
        if any(cue in plain for cue in _INTERROGATIVE_CUES):
            return {"class": "real_question", "form": last_form, "tag": last_tag}

    # 물음표로 끝나지만 EF 가 위 분기를 못 탄 경우 — 의문사 유무로 분류
    if plain.rstrip().endswith("?"):
        if any(cue in plain for cue in _INTERROGATIVE_CUES):
            return {"class": "real_question", "form": last_form, "tag": last_tag}
        return {"class": "rhetorical_question", "form": last_form, "tag": last_tag}

    if last is not None and last.tag in _NOUN_TAGS:
        return {"class": "noun_end", "form": last_form, "tag": last_tag}

    return {"class": "other", "form": last_form, "tag": last_tag}


def last_token_info(text: str) -> Optional[Tuple[str, str]]:
    """디버깅용: 마지막 내용 토큰의 (form, tag) 반환. 실패 시 None."""
    tokens = tokenize(text)
    if tokens is None:
        return None
    last = _last_content_token(tokens)
    if last is None:
        return None
    return (last.form, last.tag)
