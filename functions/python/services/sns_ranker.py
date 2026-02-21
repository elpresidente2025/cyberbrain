"""
SNS 2단계 랭커 (Light -> Heavy).
Node.js `services/sns-ranker.js`의 Python 포팅 버전이다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)

RANKER_CONFIG: Dict[str, Any] = {
    "candidateCount": 3,
    "lightModel": "gemini-2.5-flash-lite",
    "heavyModel": "gemini-2.5-flash",
    "lightTimeoutSec": 20,
    "heavyTimeoutSec": 15,
    "minCandidates": 2,
}


async def with_timeout(awaitable, timeout_sec: int | float, message: str):
    try:
        return await asyncio.wait_for(awaitable, timeout=float(timeout_sec))
    except asyncio.TimeoutError as exc:
        raise TimeoutError(message) from exc


def extract_first_balanced_json(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


async def _generate_light_candidate(prompt: str) -> Optional[str]:
    try:
        text = await with_timeout(
            generate_content_async(
                prompt,
                model_name=RANKER_CONFIG["lightModel"],
                temperature=0.8,
                max_output_tokens=25000,
                response_mime_type="application/json",
                retries=1,
            ),
            RANKER_CONFIG["lightTimeoutSec"],
            "Light Ranker 타임아웃",
        )
        if isinstance(text, str) and text.strip():
            return text
    except Exception as exc:  # pragma: no cover
        logger.warning("Light Ranker 후보 생성 실패: %s", exc)
    return None


async def light_rank(prompt: str, candidate_count: Optional[int] = None) -> List[str]:
    count = candidate_count or RANKER_CONFIG["candidateCount"]
    tasks = [_generate_light_candidate(prompt) for _ in range(count)]
    candidates = await asyncio.gather(*tasks)
    valid = [item for item in candidates if isinstance(item, str) and item.strip()]
    logger.info("Light Ranker: %s/%s개 후보 생성 완료", len(valid), count)
    return valid


def build_scoring_prompt(
    candidates: List[str],
    platform: str,
    original_content: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    context = context or {}
    platform_config = context.get("platformConfig") or {}
    user_info = context.get("userInfo") or {}
    source_type = str(context.get("sourceType") or "").strip().lower()
    platform_name = platform_config.get("name", platform)
    author_label = f"{user_info.get('name', '작성자')} {user_info.get('position', '')}".strip()
    source_label = (
        "원본 입장문/페이스북 글"
        if source_type in {"position_statement", "statement", "stance", "facebook_post", "facebook", "fb"}
        else "원본 블로그 원고"
    )

    original_summary = original_content[:500] + "..." if len(original_content) > 500 else original_content
    candidate_blocks = []
    for idx, candidate in enumerate(candidates):
        candidate_blocks.append(f"--- 후보 {idx + 1} ---\n{candidate}\n--- 끝 ---")

    hashtag_rule = ""
    if platform_config.get("hashtagLimit"):
        hashtag_rule = f"\n   - 해시태그 {platform_config.get('hashtagLimit')}개 이내인가?"

    platform_lower = str(platform or "").strip().lower()
    platform_specific_rules = ""
    if platform_lower == "x":
        platform_specific_rules = """
**X 알고리즘 적합도 체크 (필수):**
- 첫 줄 훅이 강하고 스크롤 정지 효과가 있는가?
- 줄바꿈 카드형(2~5줄)으로 모바일 가독성이 확보되는가?
- 블로그 링크가 실제 본문에 포함되는가? (링크 누락 시 감점)
- "자세한 내용은 블로그에서 확인하세요" 같은 저품질 CTA 문구가 없는가? (발견 시 큰 감점)
- 원문의 고유명사/핵심 수치/핵심 주장 중 최소 1개를 보존하는가?
""".strip()
    elif platform_lower == "threads":
        platform_specific_rules = """
**Threads 알고리즘 적합도 체크 (필수):**
- 타래 전체가 훅 -> 맥락 -> 근거 -> 마무리 흐름을 갖는가?
- 각 게시물이 독립적으로도 이해 가능하고, 동시에 이전/다음 게시물과 자연스럽게 이어지는가?
- 게시물 간 문장 반복이 과도하지 않은가? (반복 시 감점)
- 마지막 게시물에 블로그 링크가 포함되는가? (링크 누락 시 감점)
- 과장/선동형 문구 대신 설명형 문체를 유지하는가?
- 원문의 핵심 사실/수치/고유명사를 왜곡 없이 보존하는가?
""".strip()

    return f"""
당신은 SNS 콘텐츠 성과 예측 전문가입니다.
아래 {source_label}를 {platform_name} 플랫폼용으로 변환한 {len(candidates)}개 후보를 평가해주세요.

**작성자:** {author_label}
**원본 원고 (요약):**
{original_summary}

**후보들:**
{chr(10).join(candidate_blocks)}

**평가 기준 (가중치 차등, 총 100점):**

1. **임팩트 (Hook Quality)** [25점]
2. **참여 예측 (Engagement Prediction)** [25점]
3. **정보 밀도 (Information Density)** [20점]
4. **형식 준수 (Format Compliance)** [15점]
   - JSON 형식이 올바른가?
   - 플랫폼 길이 규칙을 준수하는가?{hashtag_rule}
5. **원본 충실도 (Source Fidelity)** [15점]
6. **플랫폼 알고리즘 적합도 (Platform Fit)** [가산/감산]
   - 플랫폼별 요구 문체/구조를 충족하면 가산, 위반 시 감산

{platform_specific_rules}

반드시 JSON으로만 답하세요.
{{
  "rankings": [
    {{
      "candidateIndex": 0,
      "scores": {{
        "hookQuality": 22,
        "engagementPrediction": 20,
        "informationDensity": 18,
        "formatCompliance": 14,
        "sourceFidelity": 13,
        "platformFit": 9
      }},
      "totalScore": 87,
      "strengths": "강점",
      "weaknesses": "약점"
    }}
  ],
  "bestIndex": 0,
  "reason": "선정 이유"
}}
""".strip()


def parse_heavy_rank_result(raw_result: str, candidate_count: int) -> Dict[str, Any]:
    try:
        json_str = extract_first_balanced_json(raw_result)
        if not json_str:
            raise ValueError("JSON 형식 없음")
        parsed = json.loads(json_str)

        rankings = parsed.get("rankings") if isinstance(parsed.get("rankings"), list) else []
        best_index = parsed.get("bestIndex")

        # bestIndex 교차 검증
        if rankings:
            highest = max(rankings, key=lambda item: item.get("totalScore", 0))
            highest_index = highest.get("candidateIndex")
            if isinstance(highest_index, int) and highest_index != best_index:
                logger.warning(
                    "bestIndex(%s)와 최고점수 후보(%s) 불일치, 최고점수 기준으로 보정",
                    best_index,
                    highest_index,
                )
                best_index = highest_index

        if not isinstance(best_index, int) or best_index < 0 or best_index >= candidate_count:
            raise ValueError(f"유효하지 않은 bestIndex: {best_index}")

        return {
            "bestIndex": best_index,
            "rankings": rankings,
            "reason": parsed.get("reason") or "이유 미제공",
        }
    except Exception as exc:
        logger.warning("Heavy Ranker 파싱 실패: %s", exc)
        return {
            "bestIndex": 0,
            "rankings": [],
            "reason": f"파싱 실패 ({exc}), 첫 번째 후보 fallback",
        }


async def heavy_rank(
    candidates: List[str],
    platform: str,
    original_content: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not candidates:
        return {"bestIndex": -1, "bestCandidate": None, "rankings": [], "reason": "후보 없음"}
    if len(candidates) == 1:
        return {
            "bestIndex": 0,
            "bestCandidate": candidates[0],
            "rankings": [{"candidateIndex": 0, "totalScore": 0}],
            "reason": "단일 후보 (스코어링 스킵)",
        }

    try:
        scoring_prompt = build_scoring_prompt(candidates, platform, original_content, context=context)
        raw_result = await with_timeout(
            generate_content_async(
                scoring_prompt,
                model_name=RANKER_CONFIG["heavyModel"],
                temperature=0.25,
                max_output_tokens=4096,
                response_mime_type="application/json",
                retries=1,
            ),
            RANKER_CONFIG["heavyTimeoutSec"],
            "Heavy Ranker 타임아웃",
        )
        parsed = parse_heavy_rank_result(raw_result, len(candidates))
        best_index = parsed["bestIndex"]
        return {
            **parsed,
            "bestCandidate": candidates[best_index],
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("Heavy Ranker 실패, 첫 번째 후보 선택: %s", exc)
        return {
            "bestIndex": 0,
            "bestCandidate": candidates[0],
            "rankings": [],
            "reason": f"Heavy Ranker 실패 ({exc}), 첫 번째 후보 fallback",
        }


async def rank_and_select(
    prompt: str,
    platform: str,
    original_content: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    candidate_count = options.get("candidateCount") or RANKER_CONFIG["candidateCount"]

    logger.info("[SNS Ranker] %s 2단계 랭킹 시작 (후보 %s개)", platform, candidate_count)
    start_time = time.time()

    candidates = await light_rank(prompt, candidate_count=candidate_count)

    if not candidates:
        logger.warning("Light Ranker 전체 실패, 단일 생성 fallback")
        try:
            fallback_text = await with_timeout(
                generate_content_async(
                    prompt,
                    model_name=RANKER_CONFIG["heavyModel"],
                    temperature=0.25,
                    max_output_tokens=25000,
                    response_mime_type="application/json",
                    retries=1,
                ),
                25,
                "Fallback 단일 생성 타임아웃",
            )
            return {
                "text": fallback_text,
                "ranking": {
                    "bestIndex": 0,
                    "rankings": [],
                    "reason": "Light Ranker 전체 실패, 단일 생성 fallback",
                },
            }
        except Exception as exc:
            logger.error("Fallback 생성도 실패: %s", exc)
            return {
                "text": None,
                "ranking": {
                    "bestIndex": -1,
                    "rankings": [],
                    "reason": "Light + Fallback 모두 실패",
                },
            }

    if len(candidates) < RANKER_CONFIG["minCandidates"]:
        return {
            "text": candidates[0],
            "ranking": {"bestIndex": 0, "rankings": [], "reason": "후보 부족, Heavy Ranker 스킵"},
        }

    ranking = await heavy_rank(
        candidates,
        platform,
        original_content,
        context={
            "platformConfig": options.get("platformConfig"),
            "userInfo": options.get("userInfo"),
        },
    )
    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "[SNS Ranker] %s 완료: %sms, 후보 %s개 중 #%s 선택",
        platform,
        elapsed_ms,
        len(candidates),
        ranking.get("bestIndex", -1) + 1,
    )

    return {
        "text": ranking.get("bestCandidate"),
        "ranking": ranking,
    }
