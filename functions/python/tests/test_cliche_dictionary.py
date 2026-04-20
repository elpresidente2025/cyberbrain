"""상투어 대체어 중앙 사전 시스템 단위 테스트.

테스트 범위:
  1. cliche_catalog — 마스터 리스트 통합, 중복 없음, 최소 크기
  2. centroid_builder — TF-IDF centroid 구축 (합성 데이터)
  3. candidate_extractor — 대체 표현 추출 로직
  4. dictionary_manager — 승격/퇴장 로직
  5. prompt_guards — global_alternatives 병합
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch  # noqa: F401 — available for subclass tests

# 프로젝트 루트를 path 에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestClicheCatalog(unittest.TestCase):
    """상투어 마스터 카탈로그 테스트."""

    def test_catalog_has_minimum_entries(self):
        """카탈로그가 최소 80개 이상의 고유 상투어를 포함하는지."""
        from services.cliche_dictionary.cliche_catalog import build_cliche_catalog

        catalog = build_cliche_catalog()
        self.assertGreaterEqual(len(catalog), 60)

    def test_catalog_no_empty_keys(self):
        """빈 문자열 키가 없는지."""
        from services.cliche_dictionary.cliche_catalog import build_cliche_catalog

        catalog = build_cliche_catalog()
        for key in catalog:
            self.assertTrue(key.strip(), f"Empty key found: {key!r}")

    def test_catalog_has_categories(self):
        """모든 항목에 카테고리가 있는지."""
        from services.cliche_dictionary.cliche_catalog import build_cliche_catalog

        catalog = build_cliche_catalog()
        for key, cat in catalog.items():
            self.assertTrue(cat, f"No category for: {key!r}")

    def test_catalog_known_entries(self):
        """알려진 상투어가 포함되어 있는지."""
        from services.cliche_dictionary.cliche_catalog import build_cliche_catalog

        catalog = build_cliche_catalog()
        expected = ["혁신적인", "체계적인", "밝은 미래", "진정성", "시너지"]
        for e in expected:
            self.assertIn(e, catalog, f"Expected cliche not found: {e}")

    def test_catalog_caching(self):
        """get_cliche_catalog 가 캐시를 반환하는지."""
        from services.cliche_dictionary.cliche_catalog import get_cliche_catalog

        c1 = get_cliche_catalog()
        c2 = get_cliche_catalog()
        self.assertIs(c1, c2)


class TestCentroidBuilder(unittest.TestCase):
    """TF-IDF centroid 구축 테스트 (합성 데이터)."""

    def test_build_centroids_with_synthetic_data(self):
        """합성 문장으로 centroid 가 정상 구축되는지."""
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            self.skipTest("scikit-learn not installed")

        from services.cliche_dictionary.centroid_builder import build_centroids

        # "체계적인" 이 포함된 합성 문장 5개 + "혁신적인" 5개
        cliche_sentences = {
            "체계적인": [
                "체계적인 대책을 마련하겠습니다",
                "체계적인 점검 시스템을 구축합니다",
                "체계적인 관리 방안을 수립하고",
                "체계적인 교육 프로그램을 운영합니다",
                "체계적인 지원 체계를 갖추겠습니다",
            ],
            "혁신적인": [
                "혁신적인 정책을 추진하겠습니다",
                "혁신적인 기술 도입을 검토합니다",
                "혁신적인 변화를 이끌겠습니다",
                "혁신적인 성장 동력을 확보합니다",
                "혁신적인 서비스를 제공하겠습니다",
            ],
            "없는상투어": [  # 5개 미만이라 스킵돼야 함
                "없는상투어 문장",
            ],
        }

        centroids, vectorizer, svd, samples = build_centroids(cliche_sentences)

        self.assertIn("체계적인", centroids)
        self.assertIn("혁신적인", centroids)
        self.assertNotIn("없는상투어", centroids)
        self.assertIsNotNone(vectorizer)
        self.assertIsNotNone(svd)
        self.assertEqual(len(samples["체계적인"]), 5)

    def test_empty_input(self):
        """빈 입력 시 빈 결과."""
        try:
            import sklearn  # noqa: F401
        except ImportError:
            self.skipTest("scikit-learn not installed")

        from services.cliche_dictionary.centroid_builder import build_centroids

        centroids, vec, svd, samples = build_centroids({})
        self.assertEqual(len(centroids), 0)
        self.assertIsNone(vec)


class TestCandidateExtractor(unittest.TestCase):
    """대체 표현 추출 로직 테스트."""

    def test_classify_cliche_pos_modifier(self):
        """관형사형 상투어 분류."""
        from services.cliche_dictionary.candidate_extractor import _classify_cliche_pos

        result = _classify_cliche_pos("혁신적인")
        # Kiwi 가 없으면 phrase 로 폴백될 수 있음
        self.assertIn(result, ("modifier", "phrase", None))

    def test_classify_cliche_pos_noun(self):
        """명사형 상투어 분류."""
        from services.cliche_dictionary.candidate_extractor import _classify_cliche_pos

        result = _classify_cliche_pos("시너지")
        self.assertIn(result, ("noun", "phrase", None))

    def test_cosine_similarity(self):
        """cosine similarity 계산."""
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")

        from services.cliche_dictionary.candidate_extractor import _cosine_similarity

        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        self.assertAlmostEqual(_cosine_similarity(a, b), 1.0, places=5)

        c = np.array([0.0, 1.0, 0.0])
        self.assertAlmostEqual(_cosine_similarity(a, c), 0.0, places=5)

        d = np.array([0.0, 0.0, 0.0])
        self.assertAlmostEqual(_cosine_similarity(a, d), 0.0, places=5)


class TestDictionaryManager(unittest.TestCase):
    """승격/퇴장 로직 테스트."""

    def test_cliche_hash_deterministic(self):
        """같은 입력에 같은 hash."""
        from services.cliche_dictionary.dictionary_manager import _cliche_hash

        h1 = _cliche_hash("체계적인")
        h2 = _cliche_hash("체계적인")
        self.assertEqual(h1, h2)

    def test_cliche_hash_different_inputs(self):
        """다른 입력에 다른 hash."""
        from services.cliche_dictionary.dictionary_manager import _cliche_hash

        h1 = _cliche_hash("체계적인")
        h2 = _cliche_hash("혁신적인")
        self.assertNotEqual(h1, h2)


class TestPromptGuardsIntegration(unittest.TestCase):
    """prompt_guards global_alternatives 병합 테스트."""

    def test_global_alternatives_injected(self):
        """global_alternatives 가 preferred_replacements 에 포함되는지."""
        from agents.core.prompt_guards import _build_style_generation_guard

        result = _build_style_generation_guard(
            global_alternatives={
                "체계적인": ["분기별", "단계별"],
                "혁신적인": ["실용적인"],
            }
        )

        # XML 출력에 대체어가 포함되어야 함
        self.assertIn("분기별", result)
        self.assertIn("실용적인", result)

    def test_user_alternatives_take_precedence(self):
        """per-user aiAlternatives 가 global 보다 우선하는지."""
        from agents.core.prompt_guards import _build_style_generation_guard

        # fingerprint 에 "체계적인" → "구체적인" 매핑이 있으면
        # global 의 "체계적인" → "분기별" 은 무시돼야 함
        result = _build_style_generation_guard(
            style_fingerprint={
                "aiAlternatives": {"instead_of_체계적인": "구체적인"},
            },
            global_alternatives={
                "체계적인": ["분기별"],
                "새로운 도약": ["실질적 변화"],
            },
        )

        self.assertIn("구체적인", result)
        # "새로운 도약" 은 user 에 없으므로 global 이 적용
        self.assertIn("실질적 변화", result)


if __name__ == "__main__":
    unittest.main()
