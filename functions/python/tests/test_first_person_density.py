"""1인칭 주어 밀도 분석 단위 테스트.

analyze_first_person_density() 와 pipeline.py의 전역 게이트 상수 검증.

CLAUDE.md 범용성 원칙: 실제 사용자/지역/정당명을 fixture에 하드코드하지 않는다.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common import korean_morph
from agents.common.korean_morph import analyze_first_person_density
from handlers.generate_posts_pkg.pipeline import (
    FIRST_PERSON_PROTECTED_RE,
    _first_person_subject_limit,
)


def _kiwi_can_run() -> bool:
    for key in ("USERPROFILE", "HOME", "TEMP"):
        value = os.environ.get(key, "")
        if not value:
            continue
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            return False
    try:
        return korean_morph.get_kiwi() is not None
    except Exception:
        return False


_KIWI_OK = _kiwi_can_run()

kiwi_required = pytest.mark.skipif(
    not _KIWI_OK,
    reason="kiwipiepy 초기화 불가 환경(비ASCII 경로 등) — 로컬에서만 스킵",
)


# ── analyze_first_person_density (Kiwi 필요) ──────────────────────────

@kiwi_required
def test_counts_jeoneun():
    text = "저는 샘플 정책을 추진하겠습니다. 저는 지역경제를 살리겠습니다."
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["counts"]["subject_total"] == 2
    assert result["counts"]["subject_start"] == 2


@kiwi_required
def test_counts_jega():
    text = "제가 책임지겠습니다. 제가 직접 확인하겠습니다."
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["counts"]["subject_total"] == 2


@kiwi_required
def test_counts_mixed():
    text = (
        "저는 샘플 자립을 돕겠습니다. "
        "저는 경제를 살리겠습니다. "
        "제가 책임지겠습니다."
    )
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["counts"]["subject_total"] == 3


@kiwi_required
def test_excludes_jeoui():
    """저의는 소유격 — 주어 카운트에서 제외."""
    text = "저의 비전은 샘플구를 바꾸는 것입니다."
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["counts"]["subject_total"] == 0


@kiwi_required
def test_excludes_jeoreul():
    """저를(목적어)·저에게(부사어)도 카운트 제외."""
    text = "저를 믿어주십시오. 저에게 기회를 주십시오."
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["counts"]["subject_total"] == 0


@kiwi_required
def test_sentence_count():
    text = "저는 하겠습니다. 저는 만들겠습니다. 저는 지원하겠습니다."
    result = analyze_first_person_density(text)
    assert result is not None
    assert result["sentence_count"] == 3


def test_empty_text():
    """빈 문자열 — Kiwi 없어도 동작."""
    result = analyze_first_person_density("")
    # Kiwi 불가 환경에서는 None, 가능하면 빈 결과
    if result is not None:
        assert result["counts"]["subject_total"] == 0
        assert result["sentence_count"] == 0


# ── _first_person_subject_limit (Kiwi 불필요) ─────────────────────────

def test_limit_short():
    assert _first_person_subject_limit(20) == 4


def test_limit_medium():
    # round(33 * 0.15) = round(4.95) = 5
    assert _first_person_subject_limit(33) == 5


def test_limit_long():
    # round(40 * 0.15) = round(6.0) = 6
    assert _first_person_subject_limit(40) == 6


def test_limit_clamp_max():
    assert _first_person_subject_limit(100) == 6


# ── FIRST_PERSON_PROTECTED_RE (Kiwi 불필요) ──────────────────────────

def test_protected_career_sentence():
    """경력 서술 문장 — 보호 매칭."""
    assert FIRST_PERSON_PROTECTED_RE.search(
        "저는 샘플단체에서 활동하며 현장의 목소리를 들어왔습니다."
    )


def test_protected_responsibility():
    """책임 선언 문장 — 보호 매칭."""
    assert FIRST_PERSON_PROTECTED_RE.search("저는 이 일을 책임지겠습니다.")


def test_protected_promise():
    """약속 선언 문장 — 보호 매칭."""
    assert FIRST_PERSON_PROTECTED_RE.search("저는 약속드립니다.")


def test_not_protected_policy_sentence():
    """정책 공약 문장 — 보호 미매칭 (rewrite 후보 가능)."""
    assert not FIRST_PERSON_PROTECTED_RE.search("저는 샘플 정책을 추진하겠습니다.")


def test_not_protected_position_word_alone():
    """'의원/대표/위원장' 단독 포함 공약 문장 — 보호 미매칭."""
    assert not FIRST_PERSON_PROTECTED_RE.search(
        "저는 구의원이 되면 청년 정책을 추진하겠습니다."
    )
    assert not FIRST_PERSON_PROTECTED_RE.search(
        "저는 주민 대표로서 지역경제를 살리겠습니다."
    )
