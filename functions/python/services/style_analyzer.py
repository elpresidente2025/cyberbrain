
import logging
from typing import Dict, Any, Optional
from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)

async def analyze_style_from_bio(bio_text: str) -> Dict[str, Any]:
    """
    사용자 Bio 텍스트를 분석하여 스타일 힌트와 페르소나를 추출합니다.
    """
    if not bio_text or len(bio_text) < 50:
        return {}

    try:
        prompt = f"""당신은 텍스트 스타일 분석 전문가입니다.
아래 제공된 사용자의 소개글(Bio)을 분석하여, 이 사용자가 선호하는 문체(Tone & Manner)와 주요 키워드, 그리고 페르소나를 추출하세요.

[사용자 Bio]
{bio_text}

[분석 목표]
1. 문체 (Style): 격식/비격식, 감성적/논리적, 단호함/부드러움 등
2. 주요 키워드 (Keywords): 자주 사용하는 단어나 강조하는 가치
3. 페르소나 (Persona): 글쓴이의 사회적 역할이나 성격 (예: 열정적인 청년 정치인, 노련한 전문가 등)

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "tone": ["격식있는", "논리적인", ...],
  "keywords": ["키워드1", "키워드2", ...],
  "persona": "열정적인 청년 정치인",
  "styleGuide": "문장은 명확하게 끝맺으며, 구체적인 수치를 인용하는 것을 선호함."
}}"""

        response = await generate_content_async(
            prompt, 
            model_name="gemini-2.0-flash",
            temperature=0.2,
            response_mime_type="application/json"
        )
        
        import json
        import re
        
        try:
             result = json.loads(response)
        except json.JSONDecodeError:
             match = re.search(r'\{.*\}', response, re.DOTALL)
             if match:
                 result = json.loads(match.group(0))
             else:
                 logger.warning("Failed to parse style analysis JSON")
                 return {}

        return result

    except Exception as e:
        logger.error(f"Style analysis failed: {e}")
        return {}
