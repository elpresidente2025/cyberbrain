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
- agents/core/editor_agent.py (apply_hard_constraints 치환 후 문법 검증 + 문장 레벨 비문 스캔)
- agents/common/title_hook_quality.py (_is_body_exclusive — tokens_share_stem/extract_nouns)
- (확장 가능) stylometry/features/ 등
"""

from __future__ import annotations

import os
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

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
