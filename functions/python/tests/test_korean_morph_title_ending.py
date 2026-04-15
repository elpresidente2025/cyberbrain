"""korean_morph.classify_title_ending 단위 테스트.

목적:
- 제목의 종결 어미를 수사적 반문 / 실질 질문 / 공약 / 선언 / 명사 / 기타
  6가지로 정확히 분류하는지 검증.
- kiwipiepy 가 로컬에서 초기화 실패 시(예: 비ASCII 홈 경로) classify_title_ending
  이 None 을 반환하는지 검증 — 소비처 regex fallback 경로의 전제.

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
    """Kiwi C++ 백엔드가 현재 환경에서 안전하게 뜰 수 있는지 추정.

    Windows 에서 홈 경로에 비ASCII 문자가 있으면 kiwipiepy 의 모델 로더가
    heap corruption(STATUS_HEAP_CORRUPTION) 으로 프로세스 자체를 터뜨린다.
    Python try/except 로는 잡을 수 없으므로, 호출 전에 환경을 선검사해
    불가 판정이 나면 get_kiwi() 자체를 호출하지 않는다.

    CI(Linux, ASCII 경로) 에서는 이 체크가 True 로 넘어가 실제 분류 테스트가
    실행된다.
    """
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


@kiwi_required
class TestClassifyTitleEndingRhetoricalQuestion:
    """수사적 반문: 의문사 없이 질문 어미로 끝남."""

    @pytest.mark.parametrize(
        "title",
        [
            "숙원 사업 완성할까?",
            "이번엔 이뤄낼 수 있을까",
            "해낼 수 있을까요",
            "가능할까?",
            "될까요",
            "되었을까",
            "이었을까",
            "정말 하겠습니까",
        ],
    )
    def test_rhetorical_question_detected(self, title: str) -> None:
        verdict = korean_morph.classify_title_ending(title)
        assert verdict is not None
        assert verdict["class"] == "rhetorical_question", (
            f"{title!r} → {verdict}"
        )


@kiwi_required
class TestClassifyTitleEndingRealQuestion:
    """실질 질문: 의문사(왜/무엇/어떻게/얼마 등) + 질문 어미."""

    @pytest.mark.parametrize(
        "title",
        [
            "왜 지금 개편이 필요한가",
            "무엇이 달라지는가",
            "어떻게 극복했나",
            "얼마까지 가능한가",
        ],
    )
    def test_real_question_detected(self, title: str) -> None:
        verdict = korean_morph.classify_title_ending(title)
        assert verdict is not None
        assert verdict["class"] == "real_question", (
            f"{title!r} → {verdict}"
        )


@kiwi_required
class TestClassifyTitleEndingCommitment:
    """다짐/공약형 종결."""

    @pytest.mark.parametrize(
        "title",
        [
            "끝까지 지키겠습니다",
            "약속드립니다",
            "앞장서겠습니다",
            "책임지고 만들겠습니다",
        ],
    )
    def test_commitment_detected(self, title: str) -> None:
        verdict = korean_morph.classify_title_ending(title)
        assert verdict is not None
        assert verdict["class"] == "commitment", (
            f"{title!r} → {verdict}"
        )


@kiwi_required
class TestClassifyTitleEndingNounEnd:
    """명사 종결 (AEO topic-label)."""

    @pytest.mark.parametrize(
        "title",
        [
            "선택의 이유",
            "개편의 전환점",
            "정책의 현주소",
        ],
    )
    def test_noun_end_detected(self, title: str) -> None:
        verdict = korean_morph.classify_title_ending(title)
        assert verdict is not None
        assert verdict["class"] == "noun_end", f"{title!r} → {verdict}"


@kiwi_required
class TestClassifyTitleEndingSeparation:
    """수사적 반문 vs 실질 질문이 한 판정 지점에서 구분되는지 교차 확인."""

    def test_rhetorical_and_real_are_distinguished(self) -> None:
        rhetorical = korean_morph.classify_title_ending("숙원 사업 완성할까?")
        real = korean_morph.classify_title_ending("왜 이 사업을 완성할까")
        assert rhetorical is not None and real is not None
        assert rhetorical["class"] == "rhetorical_question"
        assert real["class"] == "real_question"


class TestClassifyTitleEndingKiwiFailureFallback:
    """Kiwi 가 초기화에 실패하면 None 반환(호출부 fallback 경로 전제)."""

    def test_kiwi_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(korean_morph, "_KIWI_INSTANCE", None)
        monkeypatch.setattr(korean_morph, "_KIWI_INIT_FAILED", True)
        verdict = korean_morph.classify_title_ending("완성할까?")
        assert verdict is None

    def test_empty_title_returns_other_without_kiwi(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 빈 문자열은 tokenize 를 타지 않고 바로 'other' 로 반환되도록 설계했다.
        monkeypatch.setattr(korean_morph, "_KIWI_INSTANCE", None)
        monkeypatch.setattr(korean_morph, "_KIWI_INIT_FAILED", True)
        verdict = korean_morph.classify_title_ending("")
        assert verdict == {"class": "other", "form": "", "tag": ""}
