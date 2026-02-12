
import logging
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup
from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)

async def fetch_naver_news(topic: str, limit: int = 3) -> list:
    """
    네이버 뉴스 검색 (스크래핑)
    Node.js의 fetchNaverNews 로직 포팅
    """
    if not topic or not topic.strip():
        return []

    try:
        # requests automatically handles URL encoding of params
        url = "https://search.naver.com/search.naver"
        params = {
            "where": "news",
            "query": topic,
            "sort": "date" # 최신순
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        logger.info(f"🔍 네이버 뉴스 검색: {topic}")
        
        # 동기 requests 사용 (Cloud Functions 환경에서는 간단함)
        # 필요시 aiohttp로 변경 가능하지만, 여기선 bs4 파싱이 주 목적
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'lxml')
        news_list = []
        
        areas = soup.select('.news_area')
        for el in areas[:limit]:
            title_node = el.select_one('.news_tit')
            if not title_node:
                continue
                
            title = title_node.get('title') or title_node.get_text(strip=True)
            link = title_node.get('href')
            
            summary_node = el.select_one('.news_dsc')
            summary = summary_node.get_text(strip=True) if summary_node else ""
            
            press_node = el.select_one('.info.press')
            press = press_node.get_text(strip=True) if press_node else ""
            
            # 날짜 정보 (보통 .info 그룹의 마지막)
            # .info_group 안의 .info들을 찾거나 단순하게 처리
            info_nodes = el.select('.info_group .info')
            date = ""
            if info_nodes:
                date = info_nodes[-1].get_text(strip=True)
            
            news_list.append({
                "title": title,
                "summary": summary,
                "press": press,
                "date": date,
                "link": link
            })
            
        logger.info(f"✅ 뉴스 {len(news_list)}개 수집 완료: {topic}")
        return news_list

    except Exception as e:
        logger.error(f"❌ 네이버 뉴스 조회 실패: {e}")
        return []

async def compress_news_with_ai(news_list: list) -> dict:
    """
    AI로 뉴스를 핵심만 압축 (토큰 절감)
    Node.js의 compressNewsWithAI 로직 포팅
    """
    if not news_list:
        return None

    # TODO: 캐싱 로직 추가 가능 (Node.js는 node-cache 사용)
    # Python에선 메모리 캐시나 Redis 등을 고려해야 함.
    # 일단은 매번 호출.

    combined = "\n\n".join([
        f"{n['title']}{'. ' + n['summary'] if n['summary'] else ''}"
        for n in news_list
    ])

    prompt = f"""다음 뉴스를 핵심만 100자 이내로 요약하세요:

{combined}

출력 형식 (반드시 JSON):
{{
  "summary": "핵심 요약 (100자 이내)",
  "keyPoints": ["포인트1", "포인트2", "포인트3"]
}}"""

    try:
        response_text = await generate_content_async(
            prompt,
            model_name='gemini-2.5-flash',
            response_mime_type='application/json'
        )
        
        # JSON 파싱
        # 마크다운 코드블록 제거
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_text)
        
        compressed = {
            "summary": parsed.get("summary", ""),
            "keyPoints": parsed.get("keyPoints", []),
            "sources": [n['link'] for n in news_list]
        }
        
        logger.info(f"✅ 뉴스 AI 압축 완료: {compressed['summary'][:50]}...")
        return compressed

    except Exception as e:
        logger.error(f"❌ 뉴스 압축 실패: {e}")
        # 폴백
        first = news_list[0] if news_list else {}
        return {
            "summary": first.get("title", ""),
            "keyPoints": [n["title"] for n in news_list[:3]],
            "sources": [n["link"] for n in news_list]
        }

def format_news_for_prompt(news_data: dict | list) -> str:
    """
    뉴스 컨텍스트를 프롬프트용 텍스트로 변환
    """
    if not news_data:
        return ""

    # 압축된 뉴스 형식 (dict)
    if isinstance(news_data, dict) and "summary" in news_data:
        key_points = "\n".join([f"{i+1}. {p}" for i, p in enumerate(news_data.get("keyPoints", []))])
        sources = ", ".join(news_data.get("sources", [])[:2])
        return f"""
[📰 뉴스 핵심]
{news_data['summary']}

주요 포인트:
{key_points}

출처: {sources if sources else '네이버 뉴스'}

---
"""

    # 원본 뉴스 리스트 형식 (list)
    if isinstance(news_data, list) and news_data:
        news_text = "\n\n".join([
            f"{i+1}. {item['title']} ({item.get('date', '')})\n   요약: {item.get('summary', '')}"
            for i, item in enumerate(news_data)
        ])
        return f"""
[📰 최신 뉴스 정보]
아래는 실제 최신 뉴스입니다. 이 정보를 참고하여 구체적이고 사실 기반의 원고를 작성하세요.

{news_text}

---
"""

    return ""

def should_fetch_news(category: str) -> bool:
    """
    카테고리별로 뉴스가 필요한지 판단
    Node.js 로직 동일
    """
    needs_news = [
        'critical_writing', # 시사비평 (Node: 시사비평) - 매핑 확인 필요
        'logical_writing',  # 정책제안 (Node: 정책제안)
        'direct_writing',   # 의정활동 (Node: 의정활동)
        'analytical_writing' # 지역현안 (Node: 지역현안)
    ]
    # Python 쪽 category는 영문 키값일 가능성이 높음 (const.py 확인 필요)
    # 일단 Node.js의 영문 키값 기준으로 매핑
    
    # Node.js: '시사비평', '정책제안', etc. (한글 사용)
    # Python: topic_classifier.py 등을 보면 영문 키 사용 ('critical_writing' 등)
    # 안전하게 둘 다 체크
    
    return category in needs_news or category in [
        '시사비평', '정책제안', '의정활동', '지역현안'
    ]
