import json
import re
import time
from typing import Dict, Optional, Any

# Classifier timeout
CLASSIFIER_TIMEOUT = 30  # 30초 타임아웃

WRITING_METHODS = {
    'emotional_writing': '감사, 축하, 격려, 일상 공유 등 따뜻하고 감성적인 글',
    'logical_writing': '정책 제안, 공약 발표, 성과 보고 등 논리적이고 설득력 있는 글',
    'critical_writing': '비판적 논평, 가짜뉴스 반박, 시사 논평 등 날카로운 비판이 필요한 글',
    'diagnostic_writing': '현안 진단, 문제 분석, 원인 규명 등 심층 분석이 필요한 글',
    'analytical_writing': '지역 현안 분석, 해결책 제시, 민원 처리 보고 등 분석적인 글',
    'direct_writing': '의정활동 보고, 국정감사 활동, 법안 발의 등 직접적인 활동 보고'
}

KEYWORD_PATTERNS = {
    'critical_writing': [
        r'비판|논평|반박|규탄|성토|심판|퇴진|탄핵|사퇴|구속|기소|수사|부패|비리|의혹',
        r'사형|구형|판결|재판|검찰|수사|기소|공소'
    ],
    'emotional_writing': [
        r'감사|축하|격려|응원|위로|추모|기념|명절|새해|설날|추석|어버이|스승',
        r'생일|결혼|출산|졸업|입학|취업'
    ],
    'logical_writing': [
        r'예산|확보|공약|정책|제안|발표|계획|추진|성과|달성|이행'
    ],
    'analytical_writing': [
        r'지역|현안|민원|교통|주거|환경|시설|개선|해결책'
    ],
    'direct_writing': [
        r'국정감사|국감|의정활동|법안|조례|위원회|회의|본회의'
    ]
}

def quick_classify(topic: str) -> Optional[str]:
    for method, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, topic):
                return method
    return None

async def classify_with_llm(topic: str) -> Dict[str, Any]:
    # 공통 Gemini 클라이언트 사용 (새 google-genai SDK)
    from .gemini_client import generate_content_async, get_client

    if not get_client():
        print("⚠️ [TopicClassifier] API 키 없음, 기본값 반환")
        return {'writingMethod': 'emotional_writing', 'confidence': 0.5}

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

    print(f"📤 [TopicClassifier] LLM 호출 시작 (타임아웃: {CLASSIFIER_TIMEOUT}초)")
    start_time = time.time()

    try:
        response_text = await generate_content_async(
            prompt,
            temperature=0.1,
            max_output_tokens=100,
            response_mime_type='application/json'
        )

        elapsed = time.time() - start_time
        parsed = json.loads(response_text)

        print(f"✅ [TopicClassifier] LLM 응답 완료 ({elapsed:.1f}초)")

        if parsed.get('writingMethod') not in WRITING_METHODS:
            print(f"⚠️ [TopicClassifier] 알 수 없는 작법: {parsed.get('writingMethod')}")
            return {'writingMethod': 'emotional_writing', 'confidence': 0.5}

        return {
            'writingMethod': parsed['writingMethod'],
            'confidence': parsed.get('confidence', 0.8)
        }

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        print(f"❌ [TopicClassifier] LLM 분류 실패 ({elapsed:.1f}초): {error_msg}")
        return {'writingMethod': 'emotional_writing', 'confidence': 0.5}

async def classify_topic(topic: str) -> Dict[str, Any]:
    if not topic or len(topic.strip()) < 3:
        return {'writingMethod': 'emotional_writing', 'confidence': 0.5, 'source': 'default'}

    # 1. Quick Classify
    quick_result = quick_classify(topic)
    if quick_result:
        print(f"⚡ [TopicClassifier] 키워드 매칭: {quick_result}")
        return {'writingMethod': quick_result, 'confidence': 0.9, 'source': 'keyword'}

    # 2. LLM Classify
    print(f"🤖 [TopicClassifier] LLM 분류 시작: \"{topic[:50]}...\"")
    llm_result = await classify_with_llm(topic)
    print(f"🤖 [TopicClassifier] LLM 결과: {llm_result['writingMethod']} ({llm_result['confidence']})")
    
    result = llm_result.copy()
    result['source'] = 'llm'
    return result
