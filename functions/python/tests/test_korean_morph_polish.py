"""korean_morph 윤문 지원 함수 단위 테스트.

목적:
- split_sentences: Kiwi 문장 분할이 regex 보다 정확한지 검증
- find_duplicate_particles: 연속 동일 조사/어미 탐지
- check_post_substitution_grammar: 치환 후 비문 플래그

CLAUDE.md 범용성 원칙: 실제 사용자/지역/인물명을 하드코드하지 않는다.
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


def _kiwi_can_run() -> bool:
    """Kiwi C++ 백엔드가 현재 환경에서 안전하게 뜰 수 있는지 추정."""
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


# ──────────────────────────────────────────────────────────────────────
# split_sentences
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestSplitSentences:
    def test_basic_two_sentences(self) -> None:
        result = korean_morph.split_sentences("첫째 문장입니다. 둘째 문장입니다.")
        assert result is not None
        assert len(result) == 2

    def test_decimal_not_split(self) -> None:
        """소수점(3.14)에서 잘리지 않아야 한다."""
        result = korean_morph.split_sentences("3.14% 상승했다. 다음 문장.")
        assert result is not None
        assert len(result) == 2

    def test_empty_string(self) -> None:
        result = korean_morph.split_sentences("")
        assert result == []

    def test_none_string(self) -> None:
        result = korean_morph.split_sentences(None)
        assert result == []

    def test_single_sentence(self) -> None:
        result = korean_morph.split_sentences("단일 문장입니다.")
        assert result is not None
        assert len(result) == 1


class TestSplitSentencesFallback:
    """Kiwi 불가 환경에서 None 반환 검증."""

    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.split_sentences("아무 문장입니다.")
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# find_duplicate_particles
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestFindDuplicateParticles:
    def test_no_duplicates(self) -> None:
        result = korean_morph.find_duplicate_particles("정책을 추진합니다.")
        assert result is not None
        assert len(result) == 0

    def test_normal_sentence(self) -> None:
        result = korean_morph.find_duplicate_particles("샘플구의 발전을 위해 노력합니다.")
        assert result is not None
        assert len(result) == 0

    def test_empty(self) -> None:
        result = korean_morph.find_duplicate_particles("")
        assert result is not None
        assert len(result) == 0


class TestFindDuplicateParticlesFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.find_duplicate_particles("아무 문장입니다.")
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# check_post_substitution_grammar
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestCheckPostSubstitutionGrammar:
    def test_clean_substitution(self) -> None:
        result = korean_morph.check_post_substitution_grammar(
            "약속드립니다", "필요성을 말씀드립니다"
        )
        assert result is not None
        assert result["has_duplicate_particle"] is False

    def test_incomplete_ending(self) -> None:
        result = korean_morph.check_post_substitution_grammar(
            "비교하면", "비교하면"
        )
        assert result is not None
        assert result["is_incomplete"] is True


class TestCheckPostSubstitutionGrammarFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.check_post_substitution_grammar("원문", "치환문")
        assert result is None
