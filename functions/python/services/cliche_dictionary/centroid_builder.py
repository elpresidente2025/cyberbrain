"""TF-IDF centroid 구축 모듈.

기존 생성 원고(posts.variants.blog.content)에서 각 상투어가 등장하는 문장을
수집하고, TF-IDF → SVD 로 "전형적 문맥 벡터(centroid)"를 만든다.
이 centroid 는 candidate_extractor 에서 사용자 문장과 비교할 기준이 된다.
"""

from __future__ import annotations

import hashlib
import io
import logging
import pickle
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── 설정 ──
SVD_DIMS = 100
MAX_FEATURES = 5000
MIN_DF = 2
MIN_SENTENCES_PER_CLICHE = 5  # 이보다 적으면 centroid 구축 스킵
MAX_SAMPLE_SENTENCES = 10     # Firestore 에 저장할 샘플 문장 수
POSTS_PAGE_SIZE = 500

# HTML 태그 제거 (content_processor.strip_html 과 동일 로직)
_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _cliche_hash(phrase: str) -> str:
    return hashlib.md5(phrase.encode("utf-8")).hexdigest()[:12]


def _tokenize_to_content_words(text: str) -> str:
    """Kiwi 로 토크나이징 후 내용어(NNG, NNP, VV, VA) 의 form 만 공백 연결.

    TF-IDF vectorizer 의 입력으로 사용.
    Kiwi 불가 시 원문을 그대로 반환 (fallback).
    """
    from agents.common.korean_morph import tokenize

    tokens = tokenize(text)
    if tokens is None:
        return text

    content_tags = frozenset({"NNG", "NNP", "VV", "VA"})
    return " ".join(tok.form for tok in tokens if tok.tag in content_tags)


def _split_sentences(text: str) -> List[str]:
    """Kiwi split_sentences, fallback 은 마침표 분할."""
    from agents.common.korean_morph import split_sentences

    sents = split_sentences(text)
    if sents is not None:
        return sents
    # fallback
    return [s.strip() for s in re.split(r"[.!?]\s+", text) if s.strip()]


def collect_cliche_sentences_from_posts(
    catalog: Dict[str, str],
    db: Any,
) -> Dict[str, List[str]]:
    """Firestore posts 컬렉션에서 상투어별 포함 문장을 수집.

    Returns:
        {상투어: [문장, 문장, ...], ...}
    """
    cliche_sentences: Dict[str, List[str]] = {c: [] for c in catalog}
    processed = 0
    query = db.collection("posts").select(["variants.blog.content"])
    docs = query.stream()

    for doc in docs:
        data = doc.to_dict() or {}
        content = ""
        variants = data.get("variants")
        if isinstance(variants, dict):
            blog = variants.get("blog")
            if isinstance(blog, dict):
                content = blog.get("content", "")
        if not content:
            continue

        plain = _strip_html(content)
        if len(plain) < 50:
            continue

        sentences = _split_sentences(plain)
        for sent in sentences:
            if len(sent) < 10:
                continue
            for cliche in catalog:
                if cliche in sent:
                    cliche_sentences[cliche].append(sent)

        processed += 1
        if processed % 200 == 0:
            logger.info("[centroid_builder] %d posts processed", processed)

    logger.info(
        "[centroid_builder] Total %d posts processed, %d cliches with sentences",
        processed,
        sum(1 for v in cliche_sentences.values() if len(v) >= MIN_SENTENCES_PER_CLICHE),
    )
    return cliche_sentences


def build_centroids(
    cliche_sentences: Dict[str, List[str]],
) -> Tuple[Dict[str, np.ndarray], Any, Any, Dict[str, List[str]]]:
    """TF-IDF + SVD centroid 를 구축한다.

    Returns:
        (centroids, vectorizer, svd, sample_sentences)
        - centroids: {상투어: ndarray(SVD_DIMS,)}
        - vectorizer: fitted TfidfVectorizer
        - svd: fitted TruncatedSVD
        - sample_sentences: {상투어: [최대 10개 샘플]}
    """
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    # 모든 문장을 하나의 코퍼스로 합치되, 상투어별 인덱스를 기록
    all_docs: List[str] = []
    cliche_ranges: Dict[str, Tuple[int, int]] = {}
    sample_sentences: Dict[str, List[str]] = {}

    for cliche, sents in cliche_sentences.items():
        if len(sents) < MIN_SENTENCES_PER_CLICHE:
            continue
        start = len(all_docs)
        tokenized = [_tokenize_to_content_words(s) for s in sents]
        all_docs.extend(tokenized)
        end = len(all_docs)
        cliche_ranges[cliche] = (start, end)
        sample_sentences[cliche] = sents[:MAX_SAMPLE_SENTENCES]

    if not all_docs:
        logger.warning("[centroid_builder] No documents to build centroids from")
        return {}, None, None, {}

    logger.info(
        "[centroid_builder] Building TF-IDF from %d docs, %d cliches",
        len(all_docs),
        len(cliche_ranges),
    )

    vectorizer = TfidfVectorizer(
        max_features=MAX_FEATURES,
        min_df=min(MIN_DF, len(all_docs)),
        token_pattern=r"(?u)\b\w+\b",
    )
    tfidf_matrix = vectorizer.fit_transform(all_docs)

    n_components = min(SVD_DIMS, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
    if n_components < 1:
        n_components = 1
    svd = TruncatedSVD(n_components=n_components, random_state=42)
    reduced = svd.fit_transform(tfidf_matrix)

    centroids: Dict[str, np.ndarray] = {}
    for cliche, (start, end) in cliche_ranges.items():
        centroid = reduced[start:end].mean(axis=0)
        centroids[cliche] = centroid

    logger.info("[centroid_builder] Built %d centroids (SVD dims=%d)", len(centroids), n_components)
    return centroids, vectorizer, svd, sample_sentences


def save_centroids_to_firestore(
    centroids: Dict[str, np.ndarray],
    sample_sentences: Dict[str, List[str]],
    catalog: Dict[str, str],
    db: Any,
) -> int:
    """centroid 메타데이터를 Firestore cliche_centroids 컬렉션에 저장.

    벡터 자체는 pickle 로 GCS 에 저장하므로 여기선 메타만.
    """
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    count = 0
    batch = db.batch()
    batch_size = 0

    for cliche, centroid in centroids.items():
        doc_id = _cliche_hash(cliche)
        ref = db.collection("cliche_centroids").document(doc_id)
        batch.set(ref, {
            "cliche": cliche,
            "category": catalog.get(cliche, "unknown"),
            "sentence_count": len(sample_sentences.get(cliche, [])),
            "sample_sentences": sample_sentences.get(cliche, [])[:MAX_SAMPLE_SENTENCES],
            "updatedAt": SERVER_TIMESTAMP,
        })
        batch_size += 1
        count += 1

        if batch_size >= 400:
            batch.commit()
            batch = db.batch()
            batch_size = 0

    if batch_size > 0:
        batch.commit()

    logger.info("[centroid_builder] Saved %d centroid docs to Firestore", count)
    return count


def save_model_to_gcs(
    centroids: Dict[str, np.ndarray],
    vectorizer: Any,
    svd: Any,
    bucket_name: str,
) -> str:
    """vectorizer + SVD + centroids 를 pickle 로 GCS 에 업로드.

    Returns:
        GCS blob path
    """
    from firebase_admin import storage

    model_data = {
        "centroids": centroids,
        "vectorizer": vectorizer,
        "svd": svd,
        "built_at": time.time(),
    }

    buf = io.BytesIO()
    pickle.dump(model_data, buf)
    buf.seek(0)

    blob_path = "cliche_dictionary/centroid_model.pkl"
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_file(buf, content_type="application/octet-stream")

    logger.info("[centroid_builder] Uploaded model to gs://%s/%s", bucket_name, blob_path)
    return blob_path


def load_model_from_gcs(
    bucket_name: str,
) -> Optional[Dict[str, Any]]:
    """GCS 에서 centroid 모델을 로드.

    Returns:
        {"centroids": {...}, "vectorizer": ..., "svd": ..., "built_at": float}
        또는 없으면 None
    """
    from firebase_admin import storage

    blob_path = "cliche_dictionary/centroid_model.pkl"
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        logger.info("[centroid_builder] No model found at gs://%s/%s", bucket_name, blob_path)
        return None

    buf = io.BytesIO()
    blob.download_to_file(buf)
    buf.seek(0)

    model_data = pickle.load(buf)
    logger.info("[centroid_builder] Loaded model from gs://%s/%s", bucket_name, blob_path)
    return model_data


def run_centroid_build(db: Any, bucket_name: str) -> Dict[str, Any]:
    """centroid 구축 전체 파이프라인.

    Returns:
        {"cliche_count": int, "centroid_count": int, "blob_path": str}
    """
    from .cliche_catalog import get_cliche_catalog

    catalog = get_cliche_catalog()
    logger.info("[centroid_builder] Catalog size: %d cliches", len(catalog))

    cliche_sentences = collect_cliche_sentences_from_posts(catalog, db)
    centroids, vectorizer, svd, sample_sentences = build_centroids(cliche_sentences)

    if not centroids:
        return {"cliche_count": len(catalog), "centroid_count": 0, "blob_path": ""}

    save_centroids_to_firestore(centroids, sample_sentences, catalog, db)
    blob_path = save_model_to_gcs(centroids, vectorizer, svd, bucket_name)

    return {
        "cliche_count": len(catalog),
        "centroid_count": len(centroids),
        "blob_path": blob_path,
    }
