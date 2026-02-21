"""
Keyword scoring service migrated from `functions/services/keyword-scorer.js`.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def calculate_serp_score(serp_data: Dict[str, Any]) -> float:
    if not isinstance(serp_data, dict):
        return 5

    results = _safe_list(serp_data.get("results"))
    if len(results) == 0:
        return 5

    score = 10.0
    blog_count = _safe_number(serp_data.get("blogCount"), 0)
    official_count = _safe_number(serp_data.get("officialCount"), 0)
    total_results = _safe_number(serp_data.get("totalResults"), 0)

    official_ratio = (official_count / total_results) if total_results > 0 else 0
    if official_ratio > 0.6:
        score -= 4
    elif official_ratio > 0.4:
        score -= 3
    elif official_ratio > 0.2:
        score -= 2

    blog_ratio = (blog_count / total_results) if total_results > 0 else 0
    if blog_ratio > 0.6:
        score += 3
    elif blog_ratio > 0.4:
        score += 2
    elif blog_ratio > 0.2:
        score += 1

    return max(0, min(10, score))


def calculate_competition_score(result_count: Any) -> int:
    count = int(_safe_number(result_count, 0))
    if count < 100:
        return 10
    if count < 500:
        return 9
    if count < 1000:
        return 8
    if count < 5000:
        return 7
    if count < 10000:
        return 6
    if count < 50000:
        return 5
    if count < 100000:
        return 4
    if count < 500000:
        return 3
    if count < 1000000:
        return 2
    return 1


def calculate_specificity_score(keyword: str) -> int:
    word_count = len([part for part in str(keyword or "").strip().split() if part.strip()])
    if word_count >= 5:
        return 10
    if word_count == 4:
        return 9
    if word_count == 3:
        return 7
    if word_count == 2:
        return 5
    return 3


def calculate_blog_ratio_score(serp_data: Dict[str, Any]) -> int:
    if not isinstance(serp_data, dict):
        return 5

    total_results = _safe_number(serp_data.get("totalResults"), 0)
    if total_results <= 0:
        return 5
    blog_count = _safe_number(serp_data.get("blogCount"), 0)
    blog_ratio = blog_count / total_results
    if blog_ratio >= 0.8:
        return 10
    if blog_ratio >= 0.6:
        return 9
    if blog_ratio >= 0.4:
        return 7
    if blog_ratio >= 0.2:
        return 5
    return 3


def calculate_relevance_score(keyword: str, district: str, topic: str) -> int:
    score = 5
    lower_keyword = str(keyword or "").lower()
    lower_district = str(district or "").lower()
    lower_topic = str(topic or "").lower()

    if lower_district and lower_district in lower_keyword:
        score += 3
    if lower_topic and lower_topic in lower_keyword:
        score += 2

    political_keywords = [
        "\uC758\uC6D0",  # 의원
        "\uAD6D\uD68C",  # 국회
        "\uC2DC\uC758\uD68C",  # 시의회
        "\uAD6C\uC758\uD68C",  # 구의회
        "\uC815\uCC45",  # 정책
        "\uACF5\uC57D",  # 공약
        "\uC9C0\uC5ED",  # 지역
        "\uC8FC\uBBFC",  # 주민
        "\uBBFC\uC0DD",  # 민생
        "\uBCF5\uC9C0",  # 복지
        "\uAC1C\uBC1C",  # 개발
        "\uC608\uC0B0",  # 예산
        "\uC870\uB840",  # 조례
        "\uD589\uC815",  # 행정
        "\uD65C\uB3D9",  # 활동
        "\uC0AC\uC5C5",  # 사업
    ]
    if any(token in lower_keyword for token in political_keywords):
        score += 2

    return min(10, score)


def calculate_final_score(scores: Dict[str, Any]) -> int:
    competition_score = _safe_number(scores.get("competitionScore"), 5)
    specificity_score = _safe_number(scores.get("specificityScore"), 5)
    blog_ratio_score = _safe_number(scores.get("blogRatioScore"), 5)
    trend_score = _safe_number(scores.get("trendScore"), 5)
    relevance_score = _safe_number(scores.get("relevanceScore"), 5)

    final_score = (
        (competition_score * 0.35)
        + (specificity_score * 0.25)
        + (blog_ratio_score * 0.20)
        + (trend_score * 0.10)
        + (relevance_score * 0.10)
    )
    return int(round(final_score * 10))


def get_keyword_grade(final_score: int) -> str:
    if final_score >= 85:
        return "S"
    if final_score >= 70:
        return "A"
    if final_score >= 55:
        return "B"
    if final_score >= 40:
        return "C"
    return "D"


def generate_recommendation_reasons(scores: Dict[str, Any], final_score: int) -> List[str]:
    reasons: List[str] = []

    if _safe_number(scores.get("competitionScore"), 0) >= 8:
        reasons.append("경쟁도가 낮아 상위 노출 가능성이 높습니다")
    if _safe_number(scores.get("specificityScore"), 0) >= 7:
        reasons.append("구체적인 롱테일 키워드입니다")
    if _safe_number(scores.get("blogRatioScore"), 0) >= 7:
        reasons.append("블로그 콘텐츠 비중이 높아 개인 블로그에 유리합니다")
    if _safe_number(scores.get("trendScore"), 0) >= 8:
        reasons.append("검색량이 상승 중인 트렌드 키워드입니다")
    if _safe_number(scores.get("relevanceScore"), 0) >= 8:
        reasons.append("지역/정치 연관성이 높습니다")
    if final_score >= 85:
        reasons.append("최상위 등급의 키워드입니다")
    if len(reasons) == 0:
        reasons.append("일반적인 키워드입니다")

    return reasons


def analyze_keyword(params: Dict[str, Any]) -> Dict[str, Any]:
    keyword = str(params.get("keyword") or "")
    serp_data = params.get("serpData") if isinstance(params.get("serpData"), dict) else {}
    result_count = params.get("resultCount")
    trend_score = _safe_number(params.get("trendScore"), 5)
    district = str(params.get("district") or "")
    topic = str(params.get("topic") or "")

    scores: Dict[str, Any] = {
        "competitionScore": calculate_competition_score(result_count),
        "specificityScore": calculate_specificity_score(keyword),
        "blogRatioScore": calculate_blog_ratio_score(serp_data),
        "trendScore": trend_score,
        "relevanceScore": calculate_relevance_score(keyword, district, topic),
        "serpScore": calculate_serp_score(serp_data),
    }

    final_score = calculate_final_score(scores)
    grade = get_keyword_grade(final_score)
    reasons = generate_recommendation_reasons(scores, final_score)
    total_results = _safe_number(serp_data.get("totalResults"), 0)

    return {
        "keyword": keyword,
        "finalScore": final_score,
        "grade": grade,
        "scores": scores,
        "reasons": reasons,
        "metadata": {
            "resultCount": int(_safe_number(result_count, 0)),
            "blogRatio": (_safe_number(serp_data.get("blogCount"), 0) / total_results) if total_results > 0 else 0,
            "officialRatio": (_safe_number(serp_data.get("officialCount"), 0) / total_results) if total_results > 0 else 0,
        },
    }


def analyze_keyword_batch(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = [analyze_keyword(item if isinstance(item, dict) else {}) for item in keywords]
    results.sort(key=lambda item: int(item.get("finalScore") or 0), reverse=True)
    return results
