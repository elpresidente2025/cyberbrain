"""지역화폐 명칭 Kiwi 사용자 사전 등록 테스트."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.local_currency_names import (
    LOCAL_CURRENCY_ENTRIES,
    LOCAL_CURRENCY_NAMES,
    LOCAL_CURRENCY_TO_REGION,
    get_kiwi_user_words,
)


def test_entries_not_empty():
    assert len(LOCAL_CURRENCY_ENTRIES) >= 50


def test_frozenset_matches_entries():
    assert len(LOCAL_CURRENCY_NAMES) == len(LOCAL_CURRENCY_ENTRIES)
    for name, _ in LOCAL_CURRENCY_ENTRIES:
        assert name in LOCAL_CURRENCY_NAMES


def test_region_mapping():
    assert LOCAL_CURRENCY_TO_REGION["동백전"] == "부산광역시"
    assert LOCAL_CURRENCY_TO_REGION["여민전"] == "세종특별자치시"
    assert LOCAL_CURRENCY_TO_REGION["인천e음"] == "인천광역시"


def test_kiwi_user_words_format():
    words = get_kiwi_user_words()
    assert len(words) >= 50
    for word, tag, score in words:
        assert tag == "NNP"
        assert score == 0.0
        assert len(word) >= 2


def test_kiwi_tokenize_recognizes_local_currency():
    """Kiwi 가 지역화폐 명칭을 단일 NNP 토큰으로 인식하는지 확인.

    Windows 환경(비ASCII 경로)에서는 Kiwi 가 초기화되지 않으므로 skip.
    """
    from agents.common import korean_morph

    tokens = korean_morph.tokenize("동백전으로 결제했다")
    if tokens is None:
        # Kiwi unavailable (Windows non-ASCII path) — skip
        return

    forms = [tok.form for tok in tokens]
    tags = {tok.form: tok.tag for tok in tokens}
    assert "동백전" in forms, f"'동백전' not found in tokens: {forms}"
    assert tags["동백전"] == "NNP"


def test_kiwi_tokenize_recognizes_yeminjeon():
    from agents.common import korean_morph

    tokens = korean_morph.tokenize("여민전은 세종시의 지역화폐다")
    if tokens is None:
        return

    forms = [tok.form for tok in tokens]
    assert "여민전" in forms, f"'여민전' not found in tokens: {forms}"


def test_is_local_currency_check():
    """LOCAL_CURRENCY_NAMES 집합으로 빠른 조회가 되는지."""
    assert "동백전" in LOCAL_CURRENCY_NAMES
    assert "여민전" in LOCAL_CURRENCY_NAMES
    assert "누비전" in LOCAL_CURRENCY_NAMES
    assert "탐나는전" in LOCAL_CURRENCY_NAMES
    assert "없는화폐" not in LOCAL_CURRENCY_NAMES
