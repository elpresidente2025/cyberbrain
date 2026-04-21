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
- agents/core/structure_normalizer.py (_split_sentences Kiwi 우선 전환)
- agents/core/editor_agent.py (apply_hard_constraints 치환 후 문법 검증 + 문장 레벨 비문 스캔 + AI 수사 라벨링)
- agents/common/title_hook_quality.py (_is_body_exclusive — tokens_share_stem/extract_nouns)
- (확장 가능) stylometry/features/ 등
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


def _register_user_words(kiwi) -> None:
    """Kiwi 인스턴스에 프로젝트 커스텀 단어(지역화폐 브랜드명 등)를 등록한다."""
    try:
        from .local_currency_names import get_kiwi_user_words
        for word, tag, score in get_kiwi_user_words():
            kiwi.add_user_word(word, tag, score)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[korean_morph] 사용자 사전 등록 실패 (무시): {err}")


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
            _register_user_words(_KIWI_INSTANCE)
            return _KIWI_INSTANCE
        except Exception as err:  # pragma: no cover - defensive
            print(f"[korean_morph] kiwipiepy 초기화 실패 — regex fallback 사용: {err}")
            _KIWI_INIT_FAILED = True
            return None


_MAIN_PREDICATE_TAGS = frozenset({"VV", "VA", "VX", "VCP", "VCN"})
_NOUN_TAGS = frozenset({"NNG", "NNP", "NNB"})
_PARTICLE_TAGS = frozenset({"JKS", "JKO", "JKB", "JKG", "JKC", "JKV", "JKQ", "JX", "JC"})
_TRAILING_SKIP_TAGS = frozenset({"SF", "SP", "SS", "SW", "SO", "SE"})
_CONTENT_TOKEN_TAGS = _NOUN_TAGS | frozenset({"SL", "SN"})
_CONTENT_PREDICATE_TAGS = frozenset({"VV", "VA", "XR"})
_ADMIN_SUFFIXES = ("시", "군", "구")

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


def can_take_hada(noun_form: str) -> Optional[bool]:
    """명사가 '하다' 파생이 가능한 동작 명사인지 kiwi 로 판별.

    "이전하다" → XSV 토큰 존재 → True  (동작 명사)
    "주민하다" → XSV 토큰 없음  → False (개체 명사)
    kiwi 불가 시 None.
    """
    kiwi = get_kiwi()
    if kiwi is None:
        return None
    try:
        test_tokens = list(kiwi.tokenize(f"{noun_form}하다"))
        return any(t.tag == "XSV" for t in test_tokens)
    except Exception:  # pragma: no cover
        return None


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

    # 개체 명사 종결 — 동사/형용사/어미 없이 NNG 로 끝나는데
    # 그 NNG 가 '하다' 결합이 안 되는 개체 명사면 미완결.
    # "주민", "청년" → 미완결 / "이전", "분석" → 동작 명사 → 완결
    if last.tag == "NNG":
        has_verb = any(
            t.tag in _MAIN_PREDICATE_TAGS
            or t.tag in ("XSV", "XSA", "EF", "EC", "ETM")
            for t in tokens
        )
        if not has_verb:
            hada = can_take_hada(last.form)
            if hada is False:
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


# ──────────────────────────────────────────────────────────────────────
# 윤문(polish) 단계 지원 함수
# ──────────────────────────────────────────────────────────────────────

_DUPLICATE_CHECK_TAGS = _PARTICLE_TAGS | frozenset({"EF"})


def split_sentences(text: str) -> Optional[List[str]]:
    """Kiwi 의 split_into_sents 로 문장 분할. 실패 시 None (호출부 regex fallback)."""
    plain = str(text or "").strip()
    if not plain:
        return []
    kiwi = get_kiwi()
    if kiwi is None:
        return None
    try:
        results = kiwi.split_into_sents(plain)
        return [s.text.strip() for s in results if s.text.strip()]
    except Exception as err:  # pragma: no cover
        print(f"[korean_morph] split_into_sents 실패: {err}")
        return None


def find_duplicate_particles(text: str) -> Optional[List[Tuple[int, str, str]]]:
    """연속 동일 조사(JK*)/종결어미(EF) 중복을 탐지한다.

    반환:
      [(char_offset, form, tag), ...] — 중복인 두 번째 토큰 위치.
      빈 리스트 — 중복 없음.
      None — Kiwi 불가.
    """
    tokens = tokenize(text)
    if tokens is None:
        return None
    duplicates: List[Tuple[int, str, str]] = []
    prev = None
    for tok in tokens:
        if tok.tag in _TRAILING_SKIP_TAGS:
            continue
        if (
            prev is not None
            and tok.tag in _DUPLICATE_CHECK_TAGS
            and prev.tag == tok.tag
            and tok.form == prev.form
        ):
            duplicates.append((tok.start, tok.form, tok.tag))
        prev = tok
    return duplicates


def check_post_substitution_grammar(
    _original: str, substituted: str
) -> Optional[Dict[str, bool]]:
    """치환 전후 문장의 비문 가능성을 플래그한다.

    반환:
      {"has_duplicate_particle": bool, "is_incomplete": bool}
      None — Kiwi 불가.
    """
    dup = find_duplicate_particles(substituted)
    if dup is None:
        return None
    inc = is_incomplete_ending(substituted)
    if inc is None:
        return None
    return {
        "has_duplicate_particle": len(dup) > 0,
        "is_incomplete": bool(inc),
    }


# ──────────────────────────────────────────────────────────────────────
# 문장 구조 비문 탐지 (주술 불일치 / 속격 체인)
# ──────────────────────────────────────────────────────────────────────


def detect_subject_predicate_mismatch(sentence: str) -> Optional[bool]:
    """한 문장에 1인칭 주어("저는")와 제3자 주격주어(NN*+JKS)가 공존하는지.

    비문 의심 패턴:
      "저는 X가 Y를 낼 것입니다." — '저는'이 고립돼 서술어는 'X'의 것.

    주의: 의심 신호일 뿐 확정 아님. "저는 X가 Y라고 생각합니다" 같은 인용절은
    합법이다. 호출부는 자동 교정하지 말고 LLM(_humanize_pass) 재검토 힌트로
    쓴다.

    반환:
      True  — 두 주어 공존 → 의심
      False — 공존 아님
      None  — Kiwi 불가
    """
    tokens = tokenize(sentence)
    if tokens is None:
        return None
    if not tokens:
        return False

    has_first_person = False
    has_third_person = False
    for i, tok in enumerate(tokens):
        # 1인칭 주어: "저"(NP) + "는"(JX)
        if tok.form == "저" and tok.tag == "NP":
            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                if nxt.tag == "JX" and nxt.form == "는":
                    has_first_person = True
        # 제3자 주어: 명사(NN*) + "이"/"가"(JKS)
        if tok.tag in _NOUN_TAGS and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.tag == "JKS" and nxt.form in ("이", "가"):
                has_third_person = True

    return has_first_person and has_third_person


def detect_double_nominative(sentence: str) -> Optional[bool]:
    """한 절(clause) 안에 주격조사 JKS("이"/"가")가 2회 이상 연이어 나오는 비문.

    예: "부천 대장지구가 기초단체장이 영업 사원을 자처하며 성사시킨 사례..."
        → "대장지구가" + "기초단체장이" 사이에 절 경계(EC) 없음
        → 뒤따르는 주동사가 VV("성사시키다") → 비문 의심.

    합법 예외 (이중주격 구문):
      "아이가 키가 크다"         — 술어 VA(형용사)
      "나는 그가 좋다"           — "나는"은 JX라 JKS 카운트에 포함 안 됨
      "커피가 맛이 좋다"         — 술어 VA
    주동사가 VA/VCP/VCN 이면 False 로 처리해 false positive 회피.

    알고리즘:
      1. tokenize → JKS(이/가) 위치 수집.
      2. 연속한 두 JKS 사이에 EC(연결어미)가 있으면 절이 분리된 것 → False.
      3. 두 번째 JKS 이후 첫 용언 태그를 본다.
         - VA/VCP/VCN → False (합법 이중주격)
         - VV/VX     → True  (비문 의심)
         - 용언 없음  → False

    반환:
      True  — 이중 주어 비문 의심
      False — 정상 또는 합법 이중주격
      None  — Kiwi 불가
    """
    tokens = tokenize(sentence)
    if tokens is None:
        return None
    if not tokens:
        return False

    jks_indices = [
        i for i, tok in enumerate(tokens)
        if tok.tag == "JKS" and tok.form in ("이", "가")
    ]
    if len(jks_indices) < 2:
        return False

    # 인접한 두 JKS 쌍을 훑어, 그 사이에 EC 가 없고 뒤이은 주동사가 VV 인 쌍이 있으면 True
    for idx_a, idx_b in zip(jks_indices, jks_indices[1:]):
        between = tokens[idx_a + 1 : idx_b]
        if any(t.tag == "EC" for t in between):
            continue  # 절 경계가 있으면 합법
        # 두 번째 JKS 이후 첫 용언 탐색
        predicate = None
        for tok in tokens[idx_b + 1 :]:
            if tok.tag in _MAIN_PREDICATE_TAGS:
                predicate = tok
                break
        if predicate is None:
            continue
        if predicate.tag in ("VA", "VCP", "VCN"):
            continue  # 이중주격 합법 구문
        if predicate.tag in ("VV", "VX"):
            return True

    return False


# 직전 문장이 "부정적 상태" 로 닫혔음을 암시하는 표면 형태
# (LLM 이 "~한 실정/현실/문제/오명/한계 + 입니다" 류로 찍는 경우가 대부분)
_NEGATIVE_STATE_CLOSERS: Tuple[str, ...] = (
    "실정입니다",
    "실정이다",
    "현실입니다",
    "현실이다",
    "문제입니다",
    "한계입니다",
    "한계를 안고 있습니다",
    "오명",  # "오명을 안고 있습니다", "오명을 쓰고 있습니다"
    "평가를 받고 있습니다",
    "평가를 받아왔습니다",
    "상황입니다",
    "없습니다",
    "없었습니다",
    "부족합니다",
    "부족했습니다",
    "못하고 있습니다",
    "못해 왔습니다",
    "못했습니다",
    "뒤처져 있습니다",
    "더딘",  # "발전 속도가 더딘"
    # 비판·지적을 끌어안은 상태 — 2026-04 생성 원고 관찰
    "지적이 이어져 왔습니다",
    "지적이 이어지고 있습니다",
    "지적이 계속돼 왔습니다",
    "지적이 계속되고 있습니다",
    "지적이 많았습니다",
    "지적이 제기돼 왔습니다",
    "지적이 제기되어 왔습니다",
    "지적을 받아 왔습니다",
    "지적받아 왔습니다",
)

# "이를 위해" 류 — 부정 문장을 목적으로 받으면 역전
_PURPOSE_POINTERS: Tuple[str, ...] = (
    "이를 위해",
    "이를 위하여",
    "이를 통해",
    "이를 통하여",
    "이에 따라",  # 때로 역전 (부정 상태를 "따라서 해결하겠다" 로 연결)
)


def detect_purpose_pointer_inversion(
    prev_sentence: str, next_sentence: str
) -> Optional[bool]:
    """인접 두 문장 쌍에서 "이를 위해/이를 통해" 역전 구조 탐지.

    패턴:
      prev: "… 평가를 받고 있습니다." (부정적 상태 closer)
      next: "이를 위해 ~을 완료하겠습니다."
      → "이를" 이 부정적 상태 자체를 목적으로 가리켜 논리가 뒤집힘.

    반환:
      True  — 역전 의심
      False — 정상
      None  — Kiwi 의존 없음, 항상 None 반환은 없음 (표면 regex 기반이라 안전)
    """
    prev = str(prev_sentence or "").strip()
    nxt = str(next_sentence or "").strip()
    if not prev or not nxt:
        return False

    # next 가 목적 지시어로 시작하는지
    starts_with_pointer = False
    for pointer in _PURPOSE_POINTERS:
        if nxt.startswith(pointer):
            starts_with_pointer = True
            break
    if not starts_with_pointer:
        return False

    # prev 가 부정적 상태로 닫혔는지
    # (문장 끝 구두점·공백 제거 후 tail 검사)
    tail = prev.rstrip(" .!?。")
    for closer in _NEGATIVE_STATE_CLOSERS:
        if tail.endswith(closer):
            return True
        # "오명을 안고 있습니다" 처럼 closer 가 중간형인 경우 부분 매칭도 허용
        if closer == "오명" and "오명" in tail[-30:]:
            return True

    return False


def find_duplicate_stems(
    sentence: str, min_count: int = 2
) -> Optional[List[Tuple[str, int]]]:
    """한 문장 내에서 동일 용언 어간(VV/VA)이 `min_count` 회 이상 반복되는지 탐지.

    예:
      "정주 여건과 광역교통망이 충분히 갖춰진 자족도시의 면모를 갖추기 위해서는"
        → 어간 "갖추" 가 VV 로 2회 → [("갖추", 2)]

    합법 반복(무방):
      - 단어 자체가 달라도 같은 어간이 반복되면 플래그 — 윤문 단계에서 상위 문맥으로 판단.
      - 보조용언(VX)·지정사(VCP/VCN)는 빈번히 반복되므로 카운트하지 않는다.

    반환:
      [(stem_form, count), ...] — 기준 충족 어간 목록 (빈 리스트면 반복 없음)
      None                      — Kiwi 불가
    """
    tokens = tokenize(sentence)
    if tokens is None:
        return None
    if not tokens:
        return []
    counts: Dict[str, int] = {}
    for tok in tokens:
        if tok.tag in ("VV", "VA"):
            counts[tok.form] = counts.get(tok.form, 0) + 1
    return [(stem, n) for stem, n in counts.items() if n >= min_count]


def find_genitive_chain(
    sentence: str, min_count: int = 3
) -> Optional[List[int]]:
    """한 문장에서 속격조사 "의"(JKG) 가 min_count 회 이상이면 offset 리스트 반환.

    반환:
      [offset, ...] — min_count 충족 시 등장 위치 전부
      []            — min_count 미만
      None          — Kiwi 불가
    """
    tokens = tokenize(sentence)
    if tokens is None:
        return None
    offsets = [
        tok.start
        for tok in tokens
        if tok.tag == "JKG" and tok.form == "의"
    ]
    if len(offsets) >= min_count:
        return offsets
    return []


# ──────────────────────────────────────────────────────────────────────
# 토큰 어근 비교 (제목 hook 품질 등 타 파이프라인과 공유)
# ──────────────────────────────────────────────────────────────────────


def extract_nouns(text: str) -> Optional[List[str]]:
    """text 에서 명사 형태소(NNG/NNP/NNB) 의 form 리스트 반환.

    중복 제거하지 않고 등장 순서 보존. 조사·어미·용언·관형사 등은 제외.

    반환:
      List[str] — 명사 form 리스트 (빈 텍스트는 빈 리스트)
      None      — Kiwi 불가
    """
    plain = str(text or "").strip()
    if not plain:
        return []
    tokens = tokenize(plain)
    if tokens is None:
        return None
    return [tok.form for tok in tokens if tok.tag in _NOUN_TAGS]


def _compact_surface(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _append_unique(items: List[str], seen: set[str], token: str) -> None:
    cleaned = _compact_surface(token)
    if not cleaned:
        return
    if cleaned in seen:
        return
    seen.add(cleaned)
    items.append(cleaned)


def _iter_compound_forms(buffer: Sequence[str], *, max_size: int = 3) -> List[str]:
    if len(buffer) < 2:
        return []
    compounds: List[str] = []
    upper = min(len(buffer), max_size)
    for size in range(2, upper + 1):
        for start in range(0, len(buffer) - size + 1):
            compounds.append("".join(buffer[start:start + size]))
    return compounds


def _append_surface_variants(items: List[str], seen: set[str], token: str) -> None:
    _append_unique(items, seen, token)
    compact = _compact_surface(token)
    if len(compact) >= 3 and compact.endswith(_ADMIN_SUFFIXES):
        _append_unique(items, seen, compact[:-1])


def extract_content_tokens(
    text: str,
    *,
    include_predicates: bool = True,
    include_compounds: bool = True,
    max_compound_size: int = 3,
) -> Optional[List[str]]:
    """본문/키워드 비교용 핵심 형태소 토큰을 추출한다.

    반환 규칙:
      - 명사/고유명사/숫자/영문 토큰은 그대로 포함
      - 연속 명사구는 결합형("청년정책", "테크노밸리사업")도 함께 포함
      - VV/VA/XR 은 어간 기준으로 포함(옵션)
      - 중복은 제거하되 등장 순서는 보존
    """
    plain = str(text or "").strip()
    if not plain:
        return []

    tokens = tokenize(plain)
    if tokens is None:
        return None

    result: List[str] = []
    seen: set[str] = set()
    noun_buffer: List[str] = []

    def _flush_noun_buffer() -> None:
        nonlocal noun_buffer
        if not noun_buffer:
            return
        if include_compounds:
            for compound in _iter_compound_forms(
                noun_buffer,
                max_size=max_compound_size,
            ):
                _append_surface_variants(result, seen, compound)
        noun_buffer = []

    for tok in tokens:
        if tok.tag in _TRAILING_SKIP_TAGS:
            _flush_noun_buffer()
            continue
        if tok.tag in _CONTENT_TOKEN_TAGS:
            _append_surface_variants(result, seen, tok.form)
            noun_buffer.append(tok.form)
            continue
        _flush_noun_buffer()
        if include_predicates and tok.tag in _CONTENT_PREDICATE_TAGS:
            _append_surface_variants(result, seen, tok.form)

    _flush_noun_buffer()
    return result


def matches_content_keyword(keyword: str, text: str) -> Optional[bool]:
    """키워드가 텍스트에 형태소 단위로 반영됐는지 판정한다.

    exact compact 매칭이 우선이며, 실패하면 내용어 토큰 교집합으로 보완한다.
    """
    keyword_compact = _compact_surface(keyword).lower()
    text_compact = _compact_surface(text).lower()
    if not keyword_compact or not text_compact:
        return False
    if keyword_compact in text_compact:
        return True

    if len(keyword_compact) >= 3 and keyword_compact.endswith(_ADMIN_SUFFIXES):
        admin_stem = keyword_compact[:-1]
        if len(admin_stem) >= 2 and admin_stem in text_compact:
            return True

    keyword_tokens = extract_content_tokens(keyword)
    text_tokens = extract_content_tokens(text)
    if keyword_tokens is None or text_tokens is None:
        return None
    if not keyword_tokens or not text_tokens:
        return False

    keyword_set = set(keyword_tokens)
    text_set = set(text_tokens)
    overlap = keyword_set & text_set
    if not overlap:
        return False
    if len(keyword_set) == 1:
        return True
    if len(overlap) >= 2:
        return True
    return any(len(token) >= 4 for token in overlap)


def count_sentence_keyword_matches(text: str, keyword: str) -> Optional[int]:
    """문장 단위로 키워드 반영 횟수를 센다.

    표면 exact count 가 아니라 "형태소 기준으로 이 문장이 키워드를 다뤘는가"를
    세는 용도다. SEO 후검수의 자연 삽입 판정에 사용한다.
    """
    plain = str(text or "").strip()
    if not plain or not str(keyword or "").strip():
        return 0

    sentences = split_sentences(plain)
    if sentences is None:
        return None

    count = 0
    for sentence in sentences:
        matched = matches_content_keyword(keyword, sentence)
        if matched is None:
            return None
        if matched:
            count += 1
    return count


def tokens_share_stem(token_a: str, token_b: str) -> Optional[bool]:
    """두 한국어 토큰이 같은 명사 어근을 공유하는지 판정.

    조사/어미/용언을 제거한 뒤 양쪽의 명사 형태소 집합을 구하고, 교집합이
    비어 있지 않으면 True. 방향성 대칭.

    예:
      "테크노밸리 사업"  ~ "테크노밸리"      → True  ({테크노밸리} 공유)
      "취득세 감면 조례" ~ "취득세 감면"     → True  ({취득세, 감면} 공유)
      "특화지구 사업"    ~ "특화지구"        → True  ({특화, 지구} 공유)
      "도시첨단산업단지" ~ "특화지구"        → False (교집합 없음)

    반환:
      True  — 명사 어근 공유
      False — 공유 없음 또는 한 쪽에 명사 없음
      None  — Kiwi 불가 (호출부 fallback 필요)
    """
    nouns_a = extract_nouns(token_a)
    nouns_b = extract_nouns(token_b)
    if nouns_a is None or nouns_b is None:
        return None
    if not nouns_a or not nouns_b:
        return False
    return bool(set(nouns_a) & set(nouns_b))


# ──────────────────────────────────────────────────────────────────────
# "저는" pro-drop 라벨링 (humanize 프롬프트 힌트 생성)
# ──────────────────────────────────────────────────────────────────────


def label_first_person_sentences(
    plain_text: str,
) -> Optional[List[Dict[str, str]]]:
    """각 문장에 대해 "저는" 삭제/유지 라벨을 생성한다.

    Kiwi 형태소 분석으로 문장별 주어·서술어를 파악해 언어학적 판단을 내린다.

    반환:
      [{"text": "저는 ...", "label": "삭제 권장", "reason": "..."}, ...]
      "저는"으로 시작하지 않는 문장은 포함하지 않는다.
      None — Kiwi 불가 (호출부 regex fallback).
    """
    sents = split_sentences(plain_text)
    if sents is None:
        return None
    if not sents:
        return []

    results: List[Dict[str, str]] = []
    first_person_seen = False

    for i, sent in enumerate(sents):
        tokens = tokenize(sent)
        if tokens is None:
            return None

        # "저는" 으로 시작하는 문장인지 확인 (NP "저" + JX "는")
        is_fp = False
        if len(tokens) >= 2:
            if (tokens[0].form == "저" and tokens[0].tag == "NP"
                    and tokens[1].form in ("는", "는") and tokens[1].tag == "JX"):
                is_fp = True

        if not is_fp:
            continue

        # 직전 문장 분석
        prev_is_fp = False
        prev_has_other_subj = False
        if i > 0:
            prev_tokens = tokenize(sents[i - 1])
            if prev_tokens:
                # 직전 문장이 "저는"으로 시작?
                if (len(prev_tokens) >= 2
                        and prev_tokens[0].form == "저" and prev_tokens[0].tag == "NP"
                        and prev_tokens[1].form in ("는", "는") and prev_tokens[1].tag == "JX"):
                    prev_is_fp = True
                else:
                    # 직전 문장에 다른 주격/보조사 주어가 있는지
                    for j, tok in enumerate(prev_tokens[:6]):  # 문두 6토큰만
                        if tok.tag.startswith("NN") and j + 1 < len(prev_tokens):
                            nxt = prev_tokens[j + 1]
                            if nxt.tag in ("JKS", "JX") and nxt.form in ("이", "가", "는", "은", "에서", "께서"):
                                prev_has_other_subj = True
                                break

        # 현재 문장 서술어 분석: 의지/다짐 어미인지
        has_volition = False
        for tok in reversed(tokens):
            if tok.tag in ("SF", "SP", "SS", "SE", "SW"):
                continue
            # EF(종결어미) 에 "겠" 선어말어미가 앞에 있으면 의지/다짐
            if tok.tag == "EF":
                # "겠" 은 EP(선어말어미) 태그
                ef_idx = tokens.index(tok)
                if ef_idx > 0 and tokens[ef_idx - 1].tag == "EP" and tokens[ef_idx - 1].form == "겠":
                    has_volition = True
            break

        # 라벨 결정
        if not first_person_seen:
            label = "유지"
            reason = "첫 등장"
            first_person_seen = True
        elif prev_has_other_subj:
            label = "유지"
            reason = "대조/전환"
        elif prev_is_fp:
            label = "삭제 권장"
            reason = "동일 주어 연속"
        elif has_volition:
            label = "삭제 권장"
            reason = "의지/다짐 서술어"
        else:
            # 직전 문장에 주어가 없는(생략 상태) 경우 → 같은 화자 맥락
            label = "삭제 권장"
            reason = "주어 생략 맥락"

        results.append({
            "text": sent.strip(),
            "label": label,
            "reason": reason,
        })

    return results


# ──────────────────────────────────────────────────────────────────────
# AI 수사 패턴 라벨링 (humanize 프롬프트 힌트 생성)
# ──────────────────────────────────────────────────────────────────────

# --- A 그룹: Kiwi 품사 태그 정밀 탐지 ---

_EVIDENCE_NOUNS = frozenset({
    "지표", "데이터", "수치", "통계", "분석", "자료", "연구",
})

_DEMONSTRATIVE_MM_FORMS = frozenset({
    "이러한", "그러한", "이와", "이같은", "이런", "그런",
})

_DEMONSTRATIVE_ABSTRACT_NOUNS = frozenset({
    "가치", "결과", "과제", "가능성", "노력", "논의", "대응",
    "모델", "문제", "방안", "방향", "변화", "비전", "사례",
    "상황", "선택", "성과", "소홀", "시도", "역할", "우려",
    "의미", "이유", "접근", "정책", "점", "조건", "흐름",
    "해법", "효과",
})
_DEMONSTRATIVE_ABSTRACT_PATTERN = re.compile(
    r"(?P<modifier>이러한|이런|그러한|그런)\s+"
    r"(?P<body>[0-9A-Za-z가-힣·\s]{0,28}?)"
    r"(?P<noun>정책적\s+소홀함|성공\s+사례|"
    r"가치|결과|과제|가능성|노력|논의|대응|모델|문제|방안|방향|변화|비전|"
    r"사례|상황|선택|성과|소홀함|소홀|시도|역할|우려|의미|이유|접근|정책|점|조건|흐름|해법|효과)"
    r"(?P<particle>은|는|이|가|을|를|으로|로|에서|에도|에게|께|도|만|까지|에|의|과|와)?",
    re.IGNORECASE,
)

_ABSTRACT_MM = frozenset({"모든", "다양한", "각종", "전체"})
_ABSTRACT_NNG = frozenset({
    "계층", "분야", "시민", "주민", "세대", "구성원",
})

_AI_ADJ_MM_FORMS = frozenset({
    "혁신적인", "체계적인", "효과적인", "적극적인", "지속적인",
    "종합적인", "선도적인", "심층적인", "유기적인", "활발한", "주목할",
})

_VAGUE_SOURCE_NOUNS = frozenset({
    "전문가", "관계자", "학계", "일각",
})

_HYPERBOLE_NOUNS = frozenset({
    "전환점", "이정표", "지평", "패러다임", "토대",
})


def _detect_demonstrative_abstract_phrases_regex(text: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for match in _DEMONSTRATIVE_ABSTRACT_PATTERN.finditer(str(text or "")):
        phrase = re.sub(r"\s+", " ", str(match.group(0) or "")).strip()
        if not phrase:
            continue
        noun = re.sub(r"\s+", " ", str(match.group("noun") or "")).strip()
        results.append({
            "phrase": phrase,
            "modifier": str(match.group("modifier") or ""),
            "noun": noun,
            "start": str(match.start()),
            "end": str(match.end()),
            "source": "regex",
        })
    return results


def detect_demonstrative_abstract_phrases(text: str) -> List[Dict[str, str]]:
    """지시 관형사가 추상 명사를 수식하는 문구를 찾는다.

    예: "이러한 정책", "이러한 성공 사례", "이러한 정책적 소홀함".
    Kiwi 가 가능하면 MM/NNG 품사 기준으로 잡고, Kiwi 불가 환경에서는 regex
    fallback 으로 같은 계열의 표면 패턴을 잡는다.
    """
    plain = str(text or "")
    if not plain.strip():
        return []

    tokens = tokenize(plain)
    if tokens is None:
        return _detect_demonstrative_abstract_phrases_regex(plain)

    results: List[Dict[str, str]] = []
    for index, token in enumerate(tokens):
        if token.tag != "MM" or token.form not in _DEMONSTRATIVE_MM_FORMS:
            continue

        start = int(getattr(token, "start", 0) or 0)
        end = start + int(getattr(token, "len", len(str(token.form))) or len(str(token.form)))
        hit_noun = ""

        for next_index in range(index + 1, min(len(tokens), index + 8)):
            next_token = tokens[next_index]
            next_tag = str(getattr(next_token, "tag", "") or "")
            next_form = str(getattr(next_token, "form", "") or "")
            next_start = int(getattr(next_token, "start", end) or end)
            next_end = next_start + int(getattr(next_token, "len", len(next_form)) or len(next_form))

            if next_tag in _TRAILING_SKIP_TAGS:
                break
            if next_start - end > 12:
                break

            if next_tag.startswith("J"):
                if hit_noun:
                    end = max(end, next_end)
                break

            if next_tag in _NOUN_TAGS:
                end = max(end, next_end)
                if next_form in _DEMONSTRATIVE_ABSTRACT_NOUNS:
                    hit_noun = next_form
                    if next_index + 1 < len(tokens):
                        follower = tokens[next_index + 1]
                        follower_tag = str(getattr(follower, "tag", "") or "")
                        if follower_tag.startswith("J"):
                            follower_start = int(getattr(follower, "start", end) or end)
                            follower_len = int(
                                getattr(
                                    follower,
                                    "len",
                                    len(str(getattr(follower, "form", ""))),
                                )
                                or 0
                            )
                            end = max(end, follower_start + follower_len)
                    break
                continue

            if next_tag in {"XSN", "XR", "VA", "VV", "XSA", "XSV", "ETM"}:
                end = max(end, next_end)
                continue

            if hit_noun:
                break

        if not hit_noun:
            continue

        phrase = re.sub(r"\s+", " ", plain[start:end]).strip()
        if not phrase:
            continue
        results.append({
            "phrase": phrase,
            "modifier": str(token.form),
            "noun": hit_noun,
            "start": str(start),
            "end": str(end),
            "source": "kiwi",
        })

    return results

# --- B 그룹: 표면 매칭 ---

_NEGATIVE_PARALLEL_PHRASES = (
    "뿐만 아니라", "에 그치지 않고", "비단", "을 넘어",
)

_VERBOSE_PARTICLE_PHRASES = (
    "에 있어서", "에 있어", "함에 있어", "의 관점에서", "라는 점에서",
)

_TRANSLATIONESE_PHRASES = (
    "것은 사실이다", "것이 가능하다", "에 의해", "경향이 있다",
    "것으로 보인다",
)

_CLICHE_PROSPECT_PHRASES = (
    "여전히 많은 과제", "밝은 전망", "4차 산업혁명", "새로운 도약",
)


def label_ai_rhetoric_sentences(
    plain_text: str,
) -> Optional[Dict[str, List[Dict[str, str]]]]:
    """본문 전체에서 AI 수사 패턴을 문장별로 라벨링한다.

    Kiwi 형태소 분석(A1~A8) + 표면 매칭(B1~B5) 으로 13개 패턴을 탐지.
    탐지된 것만 dict 에 포함 → humanize 프롬프트에 해당 항목만 주입.

    반환:
      {패턴키: [{"text": 문장, "reason": 설명}, ...], ...}
      ���지 안 된 카테고리는 키 자체를 생략.
      빈 dict — 아무것도 탐지 안 됨.
      None    — Kiwi 불가.
    """
    sents = split_sentences(plain_text)
    if sents is None:
        return None
    if not sents:
        return {}

    # --- 문장별 수집 버퍼 (임계치 적용 전) ---
    buf_unsourced: List[Dict[str, str]] = []
    buf_demonstrative: List[Dict[str, str]] = []
    buf_abstract: List[Dict[str, str]] = []
    buf_suffix_jeok: List[Dict[str, str]] = []
    buf_ai_adj: List[Dict[str, str]] = []
    buf_progressive: List[Dict[str, str]] = []
    buf_vague_source: List[Dict[str, str]] = []
    buf_hyperbole: List[Dict[str, str]] = []
    buf_neg_parallel: List[Dict[str, str]] = []
    buf_verbose: List[Dict[str, str]] = []
    buf_translationese: List[Dict[str, str]] = []
    buf_chain: List[Dict[str, str]] = []
    buf_cliche: List[Dict[str, str]] = []

    for sent in sents:
        tokens = tokenize(sent)
        if tokens is None:
            return None  # Kiwi 실패 → 전체 None

        # 사전 계산
        has_sn = any(t.tag == "SN" for t in tokens)
        has_nnp = any(t.tag == "NNP" for t in tokens)

        # ── A1: 출처 없는 근거 호출 ──
        has_evidence = any(
            t.tag == "NNG" and t.form in _EVIDENCE_NOUNS for t in tokens
        )
        if has_evidence and not has_sn:
            buf_unsourced.append({
                "text": sent, "reason": "출처/수치 없는 근거 호출",
            })

        # ── A2: 지시 관형사 ──
        for t in tokens:
            if t.tag == "MM" and t.form in _DEMONSTRATIVE_MM_FORMS:
                buf_demonstrative.append({
                    "text": sent,
                    "reason": f'지시 관형사 "{t.form}"',
                })
                break  # 한 문장 1회만

        # ── A3: 추상 포용 수사 ──
        for i, t in enumerate(tokens):
            if t.tag == "MM" and t.form in _ABSTRACT_MM:
                if i + 1 < len(tokens):
                    nxt = tokens[i + 1]
                    if nxt.tag == "NNG" and nxt.form in _ABSTRACT_NNG:
                        buf_abstract.append({
                            "text": sent,
                            "reason": f'추상 포용 "{t.form} {nxt.form}"',
                        })
                        break

        # ── A4: ~적 접미사 남용 (문장당 3개+) ──
        jeok_count = sum(1 for t in tokens if t.tag == "XSN" and t.form == "적")
        if jeok_count >= 3:
            buf_suffix_jeok.append({
                "text": sent,
                "reason": f'"~적" 접미사 {jeok_count}회',
            })

        # ── A5: AI 고빈도 관형사 ──
        for t in tokens:
            if t.tag == "MM" and t.form in _AI_ADJ_MM_FORMS:
                buf_ai_adj.append({
                    "text": sent,
                    "reason": f'AI 고빈도 "{t.form}"',
                })
                break

        # ── A6: 진행형 남용 (~하고 있다) ──
        for i, t in enumerate(tokens):
            if t.tag == "EC" and t.form == "고":
                if i + 1 < len(tokens) and tokens[i + 1].tag == "VX" and tokens[i + 1].form == "있":
                    buf_progressive.append({
                        "text": sent, "reason": '"~하고 있다" 진행형',
                    })
                    break

        # ── A7: 모호 출처 표현 ──
        has_vague = any(
            t.tag == "NNG" and t.form in _VAGUE_SOURCE_NOUNS for t in tokens
        )
        if has_vague and not has_nnp:
            buf_vague_source.append({
                "text": sent, "reason": "모호 출처 (구체 고유명사 없음)",
            })

        # ── A8: 과장 수사 ──
        for t in tokens:
            if t.tag == "NNG" and t.form in _HYPERBOLE_NOUNS:
                buf_hyperbole.append({
                    "text": sent,
                    "reason": f'과장 수사 "{t.form}"',
                })
                break

        # ── B1~B5: 표면 매칭 ──
        for phrase in _NEGATIVE_PARALLEL_PHRASES:
            if phrase in sent:
                buf_neg_parallel.append({
                    "text": sent, "reason": f'부정 병렬 "{phrase}"',
                })
                break

        for phrase in _VERBOSE_PARTICLE_PHRASES:
            if phrase in sent:
                buf_verbose.append({
                    "text": sent, "reason": f'장황 조사 "{phrase}"',
                })
                break

        for phrase in _TRANSLATIONESE_PHRASES:
            if phrase in sent:
                buf_translationese.append({
                    "text": sent, "reason": f'번역체 "{phrase}"',
                })
                break

        # B4: ~하며 피상 체인 (한 문장 3회+)
        chain_count = sent.count("하며") + sent.count("하고")
        if chain_count >= 3:
            buf_chain.append({
                "text": sent,
                "reason": f'"~하며/~하고" 체인 {chain_count}회',
            })

        for phrase in _CLICHE_PROSPECT_PHRASES:
            if phrase in sent:
                buf_cliche.append({
                    "text": sent, "reason": f'클리셰 "{phrase}"',
                })
                break

    # --- 임계치 적용 → 결과 dict 구성 ---
    result: Dict[str, List[Dict[str, str]]] = {}

    # 1건부터 포함
    if buf_unsourced:
        result["unsourced_evidence"] = buf_unsourced
    if buf_suffix_jeok:
        result["suffix_jeok_overuse"] = buf_suffix_jeok
    if buf_vague_source:
        result["vague_source"] = buf_vague_source
    if buf_translationese:
        result["translationese"] = buf_translationese
    if buf_chain:
        result["superficial_chain"] = buf_chain
    if buf_cliche:
        result["cliche_prospect"] = buf_cliche

    # 전체 카운트 임계치
    if len(buf_demonstrative) >= 3:
        result["demonstrative_overuse"] = buf_demonstrative
    if len(buf_abstract) >= 2:
        result["abstract_inclusive"] = buf_abstract
    if len(buf_ai_adj) >= 3:
        result["ai_adjective_overuse"] = buf_ai_adj
    if len(buf_progressive) >= 4:
        result["progressive_overuse"] = buf_progressive
    if len(buf_hyperbole) >= 2:
        result["hyperbole"] = buf_hyperbole
    if len(buf_neg_parallel) >= 2:
        result["negative_parallel"] = buf_neg_parallel
    if len(buf_verbose) >= 2:
        result["verbose_particle"] = buf_verbose

    return result


# ──────────────────────────────────────────────────────────────────────
# Deterministic rhetoric fix helpers
# ──────────────────────────────────────────────────────────────────────

_TEMPORAL_ADVERBS = frozenset({
    "현재", "지금", "올해", "이번", "최근", "당장",
})

# "하고 있{ending}" → 축약형 매핑
HADA_PROGRESSIVE_MAP: Dict[str, str] = {
    "습니다": "합니다",
    "다": "한다",
    "으며": "하며",
    "며": "하며",
    "는": "하는",
}


def find_progressive_overuse_kiwi(
    plain_text: str,
    *,
    keep_threshold: int = 2,
) -> Optional[Dict[str, Any]]:
    """'하고 있다' 진행형의 Kiwi 기반 분류.

    하다동사(VV form이 '하'로 끝남)의 '~하고 있{어미}' 패턴만 대상.
    시제부사가 있는 문장은 실제 진행 중일 수 있어 보존.
    전체에서 *keep_threshold* 개까지 유지, 초과분을 fixable로 반환.

    Returns
    -------
    None  — Kiwi 불가
    dict  — {
        "total": int,          # 전체 하다-진행형 수
        "fixable": [           # 기계적 치환 대상 (뒤쪽부터)
            {"sentence": str, "ending_form": str},
        ],
        "kept": [              # 유지 대상
            {"sentence": str, "reason": str},
        ],
    }
    """
    sents = split_sentences(plain_text)
    if sents is None:
        return None
    if not sents:
        return {"total": 0, "fixable": [], "kept": []}

    candidates: List[Dict[str, str]] = []  # {"sentence", "ending_form"}
    temporal_kept: List[Dict[str, str]] = []

    for sent in sents:
        tokens = tokenize(sent)
        if tokens is None:
            return None

        # 시제부사 존재 여부
        has_temporal = any(
            t.form in _TEMPORAL_ADVERBS for t in tokens
            if t.tag in ("MAG", "NNG", "MM")
        )

        # VV(하) → EC(고) → VX(있) → EF/EC 시퀀스 탐색
        found = False
        for i, t in enumerate(tokens):
            if found:
                break
            if t.tag == "VV" and t.form.endswith("하"):
                # 다음 토큰이 EC("고")인지
                if i + 1 < len(tokens):
                    t1 = tokens[i + 1]
                    if t1.tag == "EC" and t1.form == "고":
                        # 그 다음이 VX("있")인지
                        if i + 2 < len(tokens):
                            t2 = tokens[i + 2]
                            if t2.tag == "VX" and t2.form == "있":
                                # 그 다음 어미 수집
                                ending_form = ""
                                if i + 3 < len(tokens):
                                    t3 = tokens[i + 3]
                                    if t3.tag in ("EF", "EC", "ETM"):
                                        ending_form = t3.form
                                # HADA_PROGRESSIVE_MAP에 매핑 가능한지
                                if ending_form and ending_form in HADA_PROGRESSIVE_MAP:
                                    if has_temporal:
                                        temporal_kept.append({
                                            "sentence": sent,
                                            "reason": "temporal",
                                        })
                                    else:
                                        candidates.append({
                                            "sentence": sent,
                                            "ending_form": ending_form,
                                        })
                                    found = True

    total = len(candidates) + len(temporal_kept)

    # keep_threshold 적용: 앞에서부터 유지, 뒤에서부터 fixable
    threshold_kept: List[Dict[str, str]] = []
    fixable: List[Dict[str, str]] = []
    for idx, c in enumerate(candidates):
        if idx < keep_threshold:
            threshold_kept.append({"sentence": c["sentence"], "reason": "threshold"})
        else:
            fixable.append(c)

    kept = temporal_kept + threshold_kept

    return {
        "total": total,
        "fixable": fixable,
        "kept": kept,
    }


# ── 저-한자어 잘림 탐지/복원 (Kiwi 기반) ─────────────────────

_JEO_HANJA_STEMS = ("저해", "저하", "저지", "저감", "저축", "저장", "저항", "저변", "저력", "저조")
_JEO_HANJA_WORD_RE = re.compile(
    r"(?:" + "|".join(re.escape(s) for s in _JEO_HANJA_STEMS) + r")[가-힣]*"
)


def find_truncated_jeo_hanja_kiwi(
    pre_plain: str,
    post_plain: str,
) -> Optional[List[Dict[str, Any]]]:
    """pre→post에서 저-한자어(저해/저하 등)가 '저'로 잘렸는지 Kiwi 기반 탐지.

    알고리즘:
      1. pre에서 저-한자어 수집 (regex)
      2. post에서 해당 단어 소실 확인
      3. Kiwi로 post 문장 분석 → 문법상 비정상 '저' 토큰 탐지
      4. pre 문장과 매칭하여 원본 단어 특정

    Returns:
      [{"original_word": "저해하는", "post_sentence": "...", "before_word": "을", "after_word": "핵심"}, ...]
      빈 리스트 → 잘림 없음.
      None → Kiwi 불가.
    """
    pre_words = list(set(_JEO_HANJA_WORD_RE.findall(pre_plain)))
    if not pre_words:
        return []

    missing = [w for w in pre_words if w not in post_plain]
    if not missing:
        return []

    post_sents = split_sentences(post_plain)
    if post_sents is None:
        return None

    pre_sents = split_sentences(pre_plain)
    if pre_sents is None:
        return None

    results: List[Dict[str, Any]] = []

    for post_sent in post_sents:
        toks = tokenize(post_sent)
        if not toks:
            continue

        for i, tok in enumerate(toks):
            if tok.form != "저":
                continue

            # ── 정상적인 1인칭 대명사 위치 → skip ──
            # "저는/저도/저의/저에게/저를/저가" 등 조사 결합
            if (tok.tag == "NP"
                    and i + 1 < len(toks)
                    and toks[i + 1].tag.startswith("J")
                    and toks[i + 1].form in ("는", "도", "의", "에게", "를", "가", "에게서")):
                continue
            # 관형사 "저 사람/저 건물" 등
            if tok.tag == "MM":
                continue

            # ── 비정상 위치 판별 ──
            suspicious = False

            # (a) 격조사·보조사 바로 뒤의 "저" — 대명사 불가
            if i > 0 and toks[i - 1].tag.startswith("J"):
                suspicious = True

            # (b) "저" 바로 뒤에 체언(명사) — 조사 없이 직접 연결은 비문
            if (not suspicious
                    and i + 1 < len(toks)
                    and toks[i + 1].tag.startswith("NN")):
                suspicious = True

            # (c) Kiwi가 비정상 태그 부여 (XR, XSV 등)
            if not suspicious and tok.tag not in ("NP", "IC", "VV"):
                suspicious = True

            if not suspicious:
                continue

            # ── pre 문장 매칭으로 원본 단어 특정 ──
            best_pre = _find_best_sentence_match(post_sent, pre_sents)
            if not best_pre:
                continue

            for w in missing:
                if w not in best_pre:
                    continue
                # 주변 context 추출 (HTML 치환용)
                before_w = ""
                after_w = ""
                if i > 0:
                    before_w = toks[i - 1].form
                if i + 1 < len(toks) and toks[i + 1].tag not in ("SF", "SP"):
                    after_w = toks[i + 1].form
                results.append({
                    "original_word": w,
                    "post_sentence": post_sent,
                    "before_word": before_w,
                    "after_word": after_w,
                })
                break

    return results


def _find_best_sentence_match(target: str, candidates: List[str]) -> Optional[str]:
    """word overlap이 가장 큰 후보 문장 반환 (최소 2단어 필요)."""
    tw = set(target.split())
    best, best_score = None, 1
    for c in candidates:
        score = len(tw & set(c.split()))
        if score > best_score:
            best_score = score
            best = c
    return best
