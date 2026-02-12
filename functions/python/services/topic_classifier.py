
import re
import json
import logging
from typing import Dict, Optional, Tuple
from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)

# Writing Method Definitions
WRITING_METHODS = {
    "emotional_writing": "감사, 축하, 격려, 일상 공유 등 따뜻하고 감성적인 글",
    "logical_writing": "정책 제안, 공약 발표, 성과 보고 등 논리적이고 설득력 있는 글",
    "critical_writing": "비판적 논평, 가짜뉴스 반박, 시사 논평 등 날카로운 비판이 필요한 글",
    "diagnostic_writing": "현안 진단, 문제 분석, 원인 규명 등 심층 분석이 필요한 글",
    "analytical_writing": "지역 현안 분석, 해결책 제시, 민원 처리 보고 등 분석적인 글",
    "direct_writing": "의정활동 보고, 국정감사 활동, 법안 발의 등 직접적인 활동 보고"
}

# Keyword Patterns for Quick Classification
KEYWORD_PATTERNS = {
    "critical_writing": [
        r"비판", r"논평", r"반박", r"규탄", r"성토", r"심판", r"퇴진", r"탄핵", r"사퇴", r"구속", r"기소", r"수사", r"부패", r"비리", r"의혹",
        r"사형", r"구형", r"판결", r"재판", r"검찰", r"공소"
    ],
    "emotional_writing": [
        r"감사", r"축하", r"격려", r"응원", r"위로", r"추모", r"기념", r"명절", r"새해", r"설날", r"추석", r"어버이", r"스승",
        r"생일", r"결혼", r"출산", r"졸업", r"입학", r"취업"
    ],
    "logical_writing": [
        r"예산", r"확보", r"공약", r"정책", r"제안", r"발표", r"계획", r"추진", r"성과", r"달성", r"이행"
    ],
    "analytical_writing": [
        r"지역", r"현안", r"민원", r"교통", r"주거", r"환경", r"시설", r"개선", r"해결책"
    ],
    "direct_writing": [
        r"국정감사", r"국감", r"의정활동", r"법안", r"조례", r"위원회", r"회의", r"본회의"
    ]
}

def quick_classify(topic: str) -> Optional[str]:
    """키워드 기반 빠른 분류"""
    if not topic:
        return None
        
    for method, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, topic):
                return method
    return None

async def classify_with_llm(topic: str) -> Dict[str, any]:
    """LLM 기반 주제 분류"""
    try:
        method_descriptions = "\n".join([f"- {key}: {desc}" for key, desc in WRITING_METHODS.items()])
        
        prompt = f"""당신은 정치인 블로그 글의 작법(writing style)을 분류하는 전문가입니다.

아래 주제에 가장 적합한 작법을 **하나만** 선택하세요.

[주제]
"{topic}"

[작법 목록]
{method_descriptions}

[판단 기준]
- 비판, 논평, 반박, 규탄 → critical_writing
- 감사, 축하, 격려, 일상 → emotional_writing  
- 정책, 공약, 성과, 예산 → logical_writing
- 현안 진단, 문제 분석 → diagnostic_writing
- 지역 현안, 민원, 해결책 → analytical_writing
- 의정활동, 국감, 법안 → direct_writing

반드시 아래 JSON 형식으로만 응답하세요:
{{"writingMethod": "선택한_작법", "confidence": 0.0~1.0}}"""

        response = await generate_content_async(
            prompt, 
            model_name="gemini-2.0-flash",
            temperature=0.1,
            max_output_tokens=100,
            response_mime_type="application/json"
        )
        
        # JSON Parsing handled by client or manual
        try:
             result = json.loads(response)
        except json.JSONDecodeError:
             # Fallback if raw text
             match = re.search(r'\{.*\}', response, re.DOTALL)
             if match:
                 result = json.loads(match.group(0))
             else:
                 raise ValueError("Invalid JSON format")

        if result.get("writingMethod") not in WRITING_METHODS:
            logger.warning(f"Unknown writing method: {result.get('writingMethod')}")
            return {"writingMethod": "emotional_writing", "confidence": 0.5}
            
        return {
            "writingMethod": result["writingMethod"],
            "confidence": result.get("confidence", 0.8)
        }
        
    except Exception as e:
        logger.error(f"LLM classification failed: {e}")
        return {"writingMethod": "emotional_writing", "confidence": 0.5}

async def classify_topic(topic: str) -> Dict[str, any]:
    """주제 분류 메인 함수"""
    if not topic or len(topic.strip()) < 2:
        return {"writingMethod": "emotional_writing", "confidence": 0.5, "source": "default"}
        
    # 1. Quick Classify
    quick_result = quick_classify(topic)
    if quick_result:
        logger.info(f"⚡ Keyword classification: {quick_result}")
        return {"writingMethod": quick_result, "confidence": 0.9, "source": "keyword"}
        
    # 2. LLM Classify
    logger.info(f"🤖 LLM classification start: {topic[:50]}...")
    llm_result = await classify_with_llm(topic)
    logger.info(f"🤖 LLM result: {llm_result['writingMethod']} ({llm_result['confidence']})")
    
    return {**llm_result, "source": "llm"}
