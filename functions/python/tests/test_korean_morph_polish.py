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


# ──────────────────────────────────────────────────────────────────────
# detect_subject_predicate_mismatch
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestDetectSubjectPredicateMismatch:
    def test_simple_first_person(self) -> None:
        """'저는' 만 주어 → 정상."""
        result = korean_morph.detect_subject_predicate_mismatch(
            "저는 최선을 다합니다."
        )
        assert result is False

    def test_mismatch_case(self) -> None:
        """'저는' + 제3자 주어 공존 → 의심 플래그."""
        result = korean_morph.detect_subject_predicate_mismatch(
            "저는 이러한 노력이 큰 효과를 낼 것입니다."
        )
        assert result is True

    def test_third_person_only(self) -> None:
        """'저는' 없음 → 정상."""
        result = korean_morph.detect_subject_predicate_mismatch(
            "이러한 노력이 큰 효과를 낼 것입니다."
        )
        assert result is False

    def test_empty(self) -> None:
        result = korean_morph.detect_subject_predicate_mismatch("")
        assert result is False


class TestDetectSubjectPredicateMismatchFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.detect_subject_predicate_mismatch(
            "저는 이러한 노력이 큰 효과를 낼 것입니다."
        )
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# detect_double_nominative
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestDetectDoubleNominative:
    def test_clean_single_subject(self) -> None:
        """JKS 1개 → 정상."""
        result = korean_morph.detect_double_nominative("시민이 참여합니다.")
        assert result is False

    def test_double_nominative_verb(self) -> None:
        """JKS 2개 + EC 없음 + 주동사 VV → 비문 의심."""
        result = korean_morph.detect_double_nominative(
            "샘플구가 기관장이 영업 사원을 자처하며 사례를 성사시켰다."
        )
        assert result is True

    def test_legal_double_subject_adjective(self) -> None:
        """이중주격 + 형용사 VA → 합법 예외."""
        result = korean_morph.detect_double_nominative("아이가 키가 크다")
        assert result is False

    def test_two_clauses_with_connector(self) -> None:
        """JKS 사이에 EC('-고/-며') 있으면 별개 절 → 정상."""
        result = korean_morph.detect_double_nominative(
            "시민이 참여하고 기업이 투자한다."
        )
        assert result is False

    def test_empty(self) -> None:
        result = korean_morph.detect_double_nominative("")
        assert result is False


class TestDetectDoubleNominativeFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.detect_double_nominative(
            "샘플구가 기관장이 성사시켰다."
        )
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# detect_purpose_pointer_inversion (Kiwi 무관 — 표면 regex)
# ──────────────────────────────────────────────────────────────────────


class TestDetectPurposePointerInversion:
    """직전 문장이 부정 상태 closer 로 닫혔는데 다음 문장이 "이를 위해" 로 시작하는 역전 탐지."""

    def test_negative_state_to_purpose_pointer(self) -> None:
        """오명 + 이를 위해 → 역전."""
        prev = "'뒤처진 산단'이라는 평가를 받고 있습니다."
        nxt = "이를 위해 2단계 지정을 신속히 완료하겠습니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is True

    def test_positive_state_to_purpose_pointer(self) -> None:
        """긍정 상태 + 이를 위해 → 정상."""
        prev = "계양구 발전이라는 목표가 분명합니다."
        nxt = "이를 위해 2단계 지정을 신속히 완료하겠습니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is False

    def test_no_pointer(self) -> None:
        """이를 위해 없음 → 정상."""
        prev = "발전 속도가 더딘 현실입니다."
        nxt = "하지만 이번 개정으로 바로잡을 것입니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is False

    def test_i_tonghae_variant(self) -> None:
        """'이를 통해' 변형도 포착."""
        prev = "조례가 없어 기업 유치 경쟁에서 불리한 위치에 있습니다."
        nxt = "이를 통해 앵커기업을 유치하고자 합니다."
        # "있습니다" 로 끝나지만 "없다" 의미 → _NEGATIVE_STATE_CLOSERS 목록은
        # "없습니다" 계열만 커버. 이 케이스는 False (과탐지 방지).
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is False

    def test_omyeong_middle_form(self) -> None:
        """'오명을 안고 있습니다' — closer 부분 매칭."""
        prev = "'뒤처진 산단' 오명을 안고 있습니다."
        nxt = "이를 위해 경쟁력 회복에 총력을 기울이겠습니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is True

    def test_criticism_continuing(self) -> None:
        """'지적이 이어져 왔습니다' — 비판·지적을 끌어안은 상태 closer."""
        prev = "경기 샘플구에 비해 발전 속도가 더디다는 지적이 이어져 왔습니다."
        nxt = "이를 위해 2단계 지정을 신속히 완료하겠습니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is True

    def test_criticism_many(self) -> None:
        """'지적이 많았습니다' — 과거형 closer."""
        prev = "기업 유치 경쟁에서 불리하다는 지적이 많았습니다."
        nxt = "이를 위해 취득세 감면 조례를 개정했습니다."
        assert korean_morph.detect_purpose_pointer_inversion(prev, nxt) is True

    def test_empty(self) -> None:
        assert korean_morph.detect_purpose_pointer_inversion("", "이를 위해 …") is False
        assert korean_morph.detect_purpose_pointer_inversion("현실입니다.", "") is False


# ──────────────────────────────────────────────────────────────────────
# find_duplicate_stems
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestFindDuplicateStems:
    def test_no_repeat(self) -> None:
        """동일 어간 반복 없음 → 빈 리스트."""
        result = korean_morph.find_duplicate_stems(
            "정주 여건과 광역교통망을 충분히 마련해야 합니다"
        )
        assert result == []

    def test_same_stem_twice(self) -> None:
        """'갖추' 어간 2회 (갖춰진 + 갖추기) → 플래그."""
        result = korean_morph.find_duplicate_stems(
            "광역교통망이 갖춰진 자족도시의 면모를 갖추기 위해서는"
        )
        assert result is not None
        # 어간 중 하나라도 >=2 나와야 함
        stems = [stem for stem, _count in result]
        assert "갖추" in stems

    def test_custom_min_count(self) -> None:
        """min_count=3 으로 올리면 2회는 빠져야 한다."""
        result = korean_morph.find_duplicate_stems(
            "광역교통망이 갖춰진 자족도시의 면모를 갖추기 위해서는",
            min_count=3,
        )
        assert result == []

    def test_empty(self) -> None:
        result = korean_morph.find_duplicate_stems("")
        assert result == []


class TestFindDuplicateStemsFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.find_duplicate_stems(
            "광역교통망이 갖춰진 자족도시의 면모를 갖추기 위해서는"
        )
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# find_genitive_chain
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestFindGenitiveChain:
    def test_no_chain(self) -> None:
        """'의' 1회만 → 임계 미만, 빈 리스트."""
        result = korean_morph.find_genitive_chain("청년 정책의 방향")
        assert result == []

    def test_three_chain(self) -> None:
        """'의' 3회 이상 → 플래그."""
        result = korean_morph.find_genitive_chain(
            "샘플구의 샘플 사업의 성공적인 조성의 필요성"
        )
        assert result is not None
        assert len(result) >= 3

    def test_custom_min_count(self) -> None:
        """min_count=2 로 완화하면 2회도 탐지."""
        result = korean_morph.find_genitive_chain("X의 Y의 Z", min_count=2)
        assert result is not None
        assert len(result) >= 2

    def test_empty(self) -> None:
        result = korean_morph.find_genitive_chain("")
        assert result == []


class TestFindGenitiveChainFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.find_genitive_chain("X의 Y의 Z의 W")
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# extract_nouns
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestExtractNouns:
    def test_basic(self) -> None:
        result = korean_morph.extract_nouns("청년 정책의 방향")
        assert result is not None
        # 명사만 — 조사/어미 제외
        assert "청년" in result
        assert "정책" in result
        assert "방향" in result
        # 조사 "의" 는 들어가면 안 됨
        assert "의" not in result

    def test_strips_particles(self) -> None:
        result = korean_morph.extract_nouns("사업을 추진한다")
        assert result is not None
        assert "사업" in result
        # 조사·동사 어간은 제외
        assert "을" not in result

    def test_empty(self) -> None:
        assert korean_morph.extract_nouns("") == []

    def test_none_string(self) -> None:
        assert korean_morph.extract_nouns(None) == []


class TestExtractNounsFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.extract_nouns("사업 추진")
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# tokens_share_stem
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestTokensShareStem:
    def test_extended_form(self) -> None:
        """확장형 ~ 기본형: 명사 집합이 superset ⇒ True."""
        result = korean_morph.tokens_share_stem("테크노밸리 사업", "테크노밸리")
        assert result is True

    def test_reversed_order(self) -> None:
        """방향성 대칭: 인자 순서 바꿔도 동일."""
        result = korean_morph.tokens_share_stem("테크노밸리", "테크노밸리 사업")
        assert result is True

    def test_compound_noun_overlap(self) -> None:
        """복합 명사구 ~ 부분 일치: 교집합이 있으면 True."""
        result = korean_morph.tokens_share_stem("취득세 감면 조례", "취득세 감면")
        assert result is True

    def test_no_overlap(self) -> None:
        """교집합 없음 ⇒ False."""
        result = korean_morph.tokens_share_stem("도시첨단산업단지", "특화지구")
        assert result is False

    def test_compatibility_case(self) -> None:
        """title_hook_quality 호환성 케이스 (body-exclusive False 여야 함)."""
        # 제목 세션의 _is_body_exclusive 내부 사용 패턴:
        # token="특화지구 사업", ref="특화지구" 의 명사 토큰 "특화지구"
        result = korean_morph.tokens_share_stem("특화지구 사업", "특화지구")
        assert result is True

    def test_empty(self) -> None:
        """어느 한 쪽이 비어 있으면 False."""
        assert korean_morph.tokens_share_stem("", "정책") is False
        assert korean_morph.tokens_share_stem("정책", "") is False


class TestTokensShareStemFallback:
    def test_returns_none_when_kiwi_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(korean_morph, "get_kiwi", lambda: None)
        result = korean_morph.tokens_share_stem("테크노밸리 사업", "테크노밸리")
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# AI 수사 패턴 라벨링 (label_ai_rhetoric_sentences)
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestLabelAiRhetoricSentences:
    """Kiwi 기반 AI 수사 패턴 탐지 검증."""

    # A1: 출처 없는 근거 호출
    def test_unsourced_evidence_flagged(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "객관적 지표에 따르면 경제가 성장합니다. 올해 성장률은 3.2%입니다."
        )
        assert result is not None
        assert len(result.get("unsourced_evidence", [])) == 1

    def test_unsourced_with_number_ok(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "2024년 통계에 따르면 인구가 5만 명 증가했습니다."
        )
        assert result is not None
        assert len(result.get("unsourced_evidence", [])) == 0

    # A2: 지시 관형사
    def test_demonstrative_overuse(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "이러한 정책입니다. 이러한 경험입니다. 이러한 협력입니다. 좋은 결과입니다."
        )
        assert result is not None
        assert len(result.get("demonstrative_overuse", [])) == 3

    def test_demonstrative_under_threshold(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "이러한 정책입니다. 좋은 결과입니다."
        )
        assert result is not None
        assert "demonstrative_overuse" not in result

    # A3: 추상 포용 수사
    def test_abstract_inclusive(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "모든 계층이 만족합니다. 다양한 계층을 포용합니다."
        )
        assert result is not None
        assert len(result.get("abstract_inclusive", [])) == 2

    # A4: ~적 접미사 남용
    def test_suffix_jeok(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "혁신적이고 체계적이며 효과적인 정책입니다."
        )
        assert result is not None
        assert len(result.get("suffix_jeok_overuse", [])) == 1

    # B1: 부정 병렬 과다
    def test_negative_parallel(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "경제뿐만 아니라 문화도 중요합니다. 이에 그치지 않고 환경도 챙깁니다."
        )
        assert result is not None
        assert len(result.get("negative_parallel", [])) == 2

    # B3: 번역체
    def test_translationese(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "이 기술이 유망하다는 것은 사실이다."
        )
        assert result is not None
        assert len(result.get("translationese", [])) == 1

    # 깨끗한 텍스트 → 빈 dict
    def test_clean_text_empty(self) -> None:
        result = korean_morph.label_ai_rhetoric_sentences(
            "샘플동 탄약고 이전 문제를 해결하겠습니다."
        )
        assert result is not None
        assert result == {}


@kiwi_required
class TestFindProgressiveOveruseKiwi:
    """Kiwi 기반 '하고 있다' 진행형 초과 탐지 검증."""

    def test_no_progressive(self) -> None:
        """진행형 없으면 total=0, fixable 비어 있음."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "정책을 추진합니다. 예산을 확보합니다."
        )
        assert result is not None
        assert result["total"] == 0
        assert result["fixable"] == []

    def test_under_threshold_kept(self) -> None:
        """2개 이하면 전부 kept (threshold 기본값 2)."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "사업을 추진하고 있습니다. 예산을 확보하고 있습니다."
        )
        assert result is not None
        assert result["total"] == 2
        assert result["fixable"] == []
        assert len(result["kept"]) == 2

    def test_excess_becomes_fixable(self) -> None:
        """3개 이상이면 초과분이 fixable."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "사업을 추진하고 있습니다. 예산을 확보하고 있습니다. "
            "인력을 배치하고 있습니다. 시설을 점검하고 있습니다."
        )
        assert result is not None
        assert result["total"] == 4
        assert len(result["fixable"]) == 2  # 4 - keep_threshold(2) = 2
        for item in result["fixable"]:
            assert "ending_form" in item
            assert item["ending_form"] in korean_morph.HADA_PROGRESSIVE_MAP

    def test_temporal_guard(self) -> None:
        """시제부사 '현재'가 있는 문장은 kept (temporal)."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "현재 사업을 추진하고 있습니다. 예산을 확보하고 있습니다. "
            "인력을 배치하고 있습니다. 시설을 점검하고 있습니다."
        )
        assert result is not None
        temporal = [k for k in result["kept"] if k.get("reason") == "temporal"]
        assert len(temporal) >= 1  # "현재" 문장은 temporal로 보존

    def test_non_hada_verb_skipped(self) -> None:
        """비-하다 동사('달리고 있다')는 탐지 안 됨."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "선수가 달리고 있습니다. 바람이 불고 있습니다."
        )
        assert result is not None
        # 하다동사가 아니면 candidates에 안 잡힘
        assert result["total"] == 0

    def test_custom_threshold(self) -> None:
        """keep_threshold=0이면 전부 fixable."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "사업을 추진하고 있습니다. 예산을 확보하고 있습니다.",
            keep_threshold=0,
        )
        assert result is not None
        assert len(result["fixable"]) == 2
        assert len([k for k in result["kept"] if k.get("reason") == "threshold"]) == 0

    def test_ending_form_variety(self) -> None:
        """다양한 어미 매핑 확인."""
        result = korean_morph.find_progressive_overuse_kiwi(
            "사업을 추진하고 있다. 예산을 확보하고 있으며 인력도 배치하고 있는 상황이다.",
            keep_threshold=0,
        )
        assert result is not None
        if result["fixable"]:
            endings = {item["ending_form"] for item in result["fixable"]}
            # 최소 1개 이상의 어미가 잡혀야 함
            assert len(endings) >= 1


# ──────────────────────────────────────────────────────────────────────
# find_truncated_jeo_hanja_kiwi — 저-한자어 잘림 탐지
# ──────────────────────────────────────────────────────────────────────


@kiwi_required
class TestFindTruncatedJeoHanja:
    """Kiwi 기반 저-한��어(저해/저하 등) 잘림 탐지 테스트."""

    def test_detect_truncated_jeohae(self) -> None:
        """'저해하는' → '저' 잘림 탐지."""
        pre = "귤현역 인근 개발을 저해하는 핵심 요인이었습니다."
        post = "귤현역 인근 개발을 저 핵심 요인이었습니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        assert len(result) >= 1
        assert result[0]["original_word"] == "저해하는"

    def test_detect_truncated_jeoha(self) -> None:
        """'저하되는' → '저' 잘림 탐지."""
        pre = "수질이 저하되는 문제를 해결해야 합니다."
        post = "수질이 저 문제를 해결해야 합니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        assert len(result) >= 1
        assert result[0]["original_word"] == "저하되는"

    def test_no_false_positive_pronoun(self) -> None:
        """정상적인 1인칭 '저는'을 잘림으로 오탐하지 않아야 한다."""
        pre = "저는 이 문제를 해결하겠습니다. 저해 요인을 제거하겠습니다."
        post = "저는 이 문제를 해결하겠습니다. 저해 요인을 제거하겠습니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        assert len(result) == 0  # 잘린 것 없음

    def test_no_truncation_returns_empty(self) -> None:
        """저-한자어가 그대로 보존되면 빈 리스트."""
        pre = "경제를 저해하는 요소를 분석했습니다."
        post = "경제를 저해하는 요소를 분석했습니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        assert len(result) == 0

    def test_no_jeo_hanja_in_pre(self) -> None:
        """pre에 저-한자어가 없으면 빈 리스트."""
        pre = "시민들의 삶의 질을 높이겠습니다."
        post = "시민들의 삶의 질을 높이겠습니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        assert len(result) == 0

    def test_context_words_populated(self) -> None:
        """탐지 결과에 before_word/after_word가 채워져야 한다."""
        pre = "발전을 저해하는 핵심 요인입니다."
        post = "발전을 저 핵심 요인입니다."
        result = korean_morph.find_truncated_jeo_hanja_kiwi(pre, post)
        assert result is not None
        if result:
            assert result[0].get("before_word")
            assert result[0].get("after_word")
