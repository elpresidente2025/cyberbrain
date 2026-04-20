"""Kiwi 기반 키워드/SEO/stylometry 확장 회귀 테스트."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_seo_agent_keyword_validation_uses_morph_sentence_matches(monkeypatch) -> None:
    from agents.common import korean_morph
    from agents.core.seo_agent import SEOAgent

    agent = SEOAgent()

    def _fake_count_sentence_keyword_matches(text: str, keyword: str) -> int:
        if keyword == "청년정책":
            return 1 if "청년을 위한 정책" in text else 0
        if keyword == "교통":
            return 1 if "교통" in text else 0
        return 0

    monkeypatch.setattr(
        korean_morph,
        "count_sentence_keyword_matches",
        _fake_count_sentence_keyword_matches,
    )

    result = agent.validate_user_keywords(
        "<p>청년을 위한 정책과 교통 개선이 필요합니다.</p>",
        ["청년정책", "교통"],
    )
    assert result["passed"] is True
    assert result["stats"]["keywords"]["청년정책"]["effectiveCount"] == 1


def test_seo_agent_reports_duplicate_stems(monkeypatch) -> None:
    from agents.common import korean_morph
    from agents.core.seo_agent import SEOAgent

    agent = SEOAgent()

    monkeypatch.setattr(
        korean_morph,
        "find_duplicate_stems",
        lambda sentence: [("추진", 3)] if "추진" in sentence else [],
    )

    result = agent.check_anti_repetition(
        "<p>사업을 추진하고 예산을 추진하며 계획을 추진합니다. 이어서 후속 점검도 진행합니다.</p>"
    )
    assert any("서술어 어간 반복" in issue for issue in result["issues"])


def test_fingerprint_native_words_use_morph_match(monkeypatch) -> None:
    from agents.common import korean_morph
    from services.stylometry.fingerprint import _extract_user_native_words

    monkeypatch.setattr(
        korean_morph,
        "matches_content_keyword",
        lambda keyword, text: keyword == "체계적" and "체계적으로" in text,
    )

    result = _extract_user_native_words("체계적으로 접근하겠습니다.")
    assert "체계적" in result
