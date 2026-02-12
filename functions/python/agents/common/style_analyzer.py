import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MetricsAnalyzer:
    @staticmethod
    def analyze_sentence_length(text: str) -> Dict[str, Any]:
        # Split sentences by . ! ?
        sentences = re.split(r'[^.!?]+[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return {'avg': 0, 'distinct': 'N/A', 'count': 0}

        lengths = [len(s) for s in sentences]
        total = sum(lengths)
        avg = round(total / len(lengths))

        distinct = '중간 호흡 (40~60자)'
        if avg < 40:
            distinct = '짧고 간결한 호흡 (단문 위주)'
        elif avg > 70:
            distinct = '길고 논리적인 호흡 (만연체 경향)'

        return {'avg': avg, 'distinct': distinct, 'count': len(sentences)}

    @staticmethod
    def analyze_ending_patterns(text: str) -> Dict[str, Any]:
        patterns = {
            '합쇼체(격식)': r'합니다|습니다|입니다|습니까|십시요',
            '해요체(비격식)': r'해요|데요|나요|가요',
            '해라체(권위/선언)': r'한다|했다|이다|겠다',
            '청유형(제안)': r'합시다|자|시죠'
        }

        counts = {}
        total_matches = 0

        for key, pattern in patterns.items():
            matches = re.findall(pattern, text)
            count = len(matches)
            counts[key] = count
            total_matches += count

        ratios = {}
        if total_matches > 0:
            for key, count in counts.items():
                if count > 0:
                    ratios[key] = f"{round((count / total_matches) * 100)}%"

        return {'counts': counts, 'ratios': ratios}

async def extract_style_from_text(text: str) -> Optional[Dict[str, Any]]:
    from .gemini_client import generate_content_async, get_client

    if not text or len(text) < 50:
        return None

    # 1. Quantitative Analysis
    sentence_metrics = MetricsAnalyzer.analyze_sentence_length(text)
    ending_metrics = MetricsAnalyzer.analyze_ending_patterns(text)

    # 2. Qualitative Analysis (LLM)
    if not get_client():
        logger.error("Gemini API Key missing")
        return {
            'metrics': {
                'sentence_length': sentence_metrics,
                'ending_patterns': ending_metrics
            },
            'persona_summary': 'API 키 누락으로 분석 불가',
            'signature_keywords': [],
            'tone_manner': '알 수 없음'
        }

    prompt = f"""
당신은 문체 분석 전문가(Stylometry Expert)입니다.
아래 텍스트는 한 정치인의 프로필(Bio) 또는 과거 글입니다.
이 텍스트를 심층 분석하여, 이 사람의 '글쓰기 스타일(Persona)'을 정의하는 JSON을 생성하십시오.

[분석 대상 텍스트]
\"\"\"
{text[:3000]}
\"\"\"

[지시사항]
다음 구조의 JSON 객체만 출력하십시오. (부연 설명 금지)
{{
  "persona_summary": "이 사람의 캐릭터를 한 문장으로 요약",
  "signature_keywords": ["정체성 키워드 3~5개"],
  "tone_manner": "말투 특징",
  "narrative_strategy": "서사 전략",
  "forbidden_style": "절대 쓰지 않는 어색한 문체"
}}
"""
    try:
        response_text = await generate_content_async(
            prompt,
            model_name='gemini-2.0-flash',
            response_mime_type='application/json'
        )
        json_str = response_text.strip()

        try:
            qualitative_data = json.loads(json_str)
        except json.JSONDecodeError:
            clean_json = re.sub(r'```json|```', '', json_str).strip()
            try:
                qualitative_data = json.loads(clean_json)
            except:
                logger.warning('Style analysis JSON parse failed')
                qualitative_data = {'raw_analysis': json_str}

        return {
            'metrics': {
                'sentence_length': sentence_metrics,
                'ending_patterns': ending_metrics
            },
            **qualitative_data
        }

    except Exception as e:
        logger.error(f"Error during style extraction: {e}")
        return {
            'metrics': {
                'sentence_length': sentence_metrics,
                'ending_patterns': ending_metrics
            },
            'persona_summary': '분석 실패 (기본값 사용)',
            'signature_keywords': [],
            'tone_manner': '정중하고 차분한'
        }
