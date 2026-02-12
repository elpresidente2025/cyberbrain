import logging
import re
import json
import asyncio
from typing import Dict, Any, List, Optional
from ..base_agent import Agent

# Local imports
from ..common.gemini_client import get_client, generate_content_async

logger = logging.getLogger(__name__)

# 🔑 카테고리별 소제목 스타일 정의 (Node.js 포팅)
SUBHEADING_STYLES = {
    # 논평/시사: 주장형 소제목 (질문형 금지)
    'current-affairs': {
        'style': 'assertive',
        'description': '논평/시사 카테고리는 주장형 소제목을 사용합니다.',
        'preferredTypes': ['주장형', '명사형'],
        # Node.js: 'forbiddenPatterns': ['~인가요?', '~일까요?', '~는?', '~할까?', '~인가?']
        'examples': [
            '"신공안 프레임"은 책임 회피에 불과하다',
            '특검은 정치 보복이 아니다',
            '당당하면 피할 이유 없다',
            '민주주의의 기본 질서를 지켜야'
        ]
    },
    # 정책 제안: 정보형/데이터형 소제목
    'policy-proposal': {
        'style': 'informative',
        'description': '정책 제안 카테고리는 구체적인 정보형 소제목을 사용합니다.',
        'preferredTypes': ['데이터형', '명사형', '절차형'],
        'examples': [
            '청년 일자리 3대 핵심 전략',
            '국비 100억 확보 내역',
            '교통 체계 개편 5단계 로드맵'
        ]
    },
    # 의정활동: 실적/성과 중심
    'activity-report': {
        'style': 'achievement',
        'description': '의정활동 보고는 성과 중심 소제목을 사용합니다.',
        'preferredTypes': ['데이터형', '명사형'],
        'examples': [
            '국정감사 5대 핵심 성과',
            '지역 현안 해결 실적',
            '국회 발의 법안 현황'
        ]
    },
    # 일상 소통: 친근한 질문형 허용
    'daily-communication': {
        'style': 'friendly',
        'description': '일상 소통은 친근한 질문형도 허용됩니다.',
        'preferredTypes': ['질문형', '명사형'],
        'examples': [
            '요즘 어떻게 지내시나요?',
            '함께 나눈 이야기들',
            '시민 여러분께 전하는 말씀'
        ]
    },
    # 기본값
    'default': {
        'style': 'aeo-optimized',
        'description': '기본 AEO 최적화 스타일을 사용합니다.',
        'preferredTypes': ['질문형', '명사형', '데이터형'],
        'examples': []
    }
}

class SubheadingAgent(Agent):
    def __init__(self, name: str = 'SubheadingAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        self.model_name = (options or {}).get('modelName', 'gemini-2.0-flash') # Node uses 2.5-flash, but python default usually 2.0-flash alias

    def get_style_config(self, category: str) -> Dict:
        return SUBHEADING_STYLES.get(category, SUBHEADING_STYLES['default'])

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process content to optimize subheadings.
        Context expects: 'content', 'fullName', 'category'
        """
        content = context.get('content')
        if not content:
            return {'content': '', 'optimized': False}

        full_name = (context.get('author') or {}).get('name', '')
        # fullRegion might be in context or userProfile
        user_profile = context.get('userProfile', {})
        full_region = f"{user_profile.get('regionMetro', '')} {user_profile.get('regionDistrict', '')}".strip()
        category = context.get('category', '')
        
        # 🔑 [NEW] 입장문 추출 - 소제목에 핵심 주장 반영
        stance_text = context.get('stanceText', '')
        if stance_text:
            logger.info(f"[{self.name}] 입장문 {len(stance_text)}자 활용하여 소제목 최적화")
        
        optimized_content = await self.optimize_headings_in_content(
            content=content, 
            full_name=full_name, 
            full_region=full_region,
            category=category,
            stance_text=stance_text  # 🔑 [NEW]
        )
        
        return {
            'content': optimized_content,
            'optimized': True
        }

    async def optimize_headings_in_content(self, content: str, full_name: str, full_region: str, category: str, stance_text: str = '') -> str:
        # 1. H2 태그 추출
        h2_pattern = re.compile(r'<h2>(.*?)</h2>', re.IGNORECASE)
        matches = list(h2_pattern.finditer(content))
        
        if not matches:
            return content

        logger.info(f"✨ [SubheadingAgent] 소제목 {len(matches)}개 최적화 시작 (Category: {category})")

        # 2. 본문 텍스트 추출 (맥락 파악용)
        def strip_html(text):
            return re.sub(r'<[^>]*>', ' ', text).strip()

        sections_for_prompt = []
        for match in matches:
            start_pos = match.end()
            # 다음 600자 정도를 컨텍스트로 사용
            next_text = content[start_pos : start_pos + 600]
            cleaned = strip_html(next_text)
            sections_for_prompt.append(cleaned)

        # 3. LLM 호출
        style_config = self.get_style_config(category)
        aeo_headings = await self.generate_aeo_subheadings(
            sections=sections_for_prompt,
            style_config=style_config,
            full_name=full_name,
            full_region=full_region,
            stance_text=stance_text  # 🔑 [NEW] 입장문 전달
        )

        if not aeo_headings or len(aeo_headings) != len(matches):
            logger.warning("⚠️ [SubheadingAgent] 생성된 소제목 개수 불일치/실패. 원본 유지.")
            return content

        # 4. 교체 (String Reconstruction)
        parts = []
        last_index = 0
        
        for i, match in enumerate(matches):
            parts.append(content[last_index : match.start()]) # 태그 앞부분
            parts.append(f"<h2>{aeo_headings[i]}</h2>")      # 교체된 태그
            last_index = match.end()                         # 태그 뒷부분 시작점 갱신
            
        parts.append(content[last_index:]) # 남은 뒷부분
        
        logger.info("✅ [SubheadingAgent] 소제목 전면 교체 완료")
        return "".join(parts)

    async def generate_aeo_subheadings(self, sections: List[str], style_config: Dict, full_name: str, full_region: str, stance_text: str = '') -> List[str]:
        entity_hints = ", ".join(filter(None, [full_name, full_region]))
        target_count = len(sections)
        is_assertive = style_config.get('style') == 'assertive'
        
        # 🔑 [NEW] 입장문 요약 (소제목에 핵심 주장 반영용)
        stance_hint = f"**[입장문 핵심]**: {stance_text[:300]}..." if stance_text else ""

        prompt = ""
        
        # 프롬프트 구성 (Node.js 로직 Mirroring)
        if is_assertive:
            prompt = f"""
# Role Definition
당신은 대한민국 최고의 **정치 논평 전문 에디터**입니다.
주어진 논평/입장문 단락들을 분석하여, **날카롭고 주장이 담긴 소제목(H2)**을 생성해야 합니다.

# Input Data
- **Context**: {entity_hints or '(없음)'}
- **Target Count**: {target_count} Headings
- **글 유형**: 논평/입장문 (주장형 소제목 필수)
{stance_hint}

# [CRITICAL] 논평용 H2 작성 가이드라인
⚠️ 이 글은 논평/입장문입니다. 질문형 소제목은 절대 금지됩니다.

## 1. 필수 요소
- **길이**: **12~25자** (네이버 최적: 15~22자)
- **형식**: **주장형** 또는 **명사형** (질문형 절대 금지)
- **어조**: 단정적, 비판적, 명확한 입장 표명

## 2. ✅ 권장 유형 (주장형)
- **유형 A (단정형)**: "~이다", "~해야 한다"
  - ✅ "특검은 정치 보복이 아니다" (12자)
  - ✅ "당당하면 피할 이유 없다" (12자)
- **유형 B (비판형)**: 대상을 명시한 비판
  - ✅ "진실 규명을 거부하는 태도" (13자)
- **유형 C (명사형)**: 핵심 쟁점 명시
  - ✅ "특검법의 정당성과 의의" (12자)

## 3. ❌ 절대 금지 (질문형)
- ❌ "~인가요?", "~일까요?", "~는?", "~할까?"
- ❌ "어떻게 해소해야 하나?"

# Input Paragraphs
"""
        else:
            prompt = f"""
# Role Definition
당신은 대한민국 최고의 **AEO(Answer Engine Optimization) & SEO 전문 카피라이터**입니다.
주어진 본문 단락들을 분석하여, 검색 엔진과 사용자 모두에게 매력적인 **최적의 소제목(H2)**을 생성해야 합니다.

# Input Data
- **Context**: {entity_hints or '(없음)'}
- **Target Count**: {target_count} Headings
{stance_hint}

# [CRITICAL] AEO H2 작성 가이드라인
아래 규칙을 위반할 경우 해고될 수 있습니다. 반드시 준수하세요.

## 1. 필수 요소
- **길이**: **12~25자** (네이버 최적: 15~22자)
- **키워드**: 핵심 키워드를 **문장 앞쪽 1/3**에 배치할 것.
- **형식**: 구체적인 **질문형** 또는 **명확한 명사형**.
- **금지**: "~에 대한", "~관련", "좋은 성과", "이관훈은?" 같은 모호한 표현.

## 2. AEO 최적화 유형 (상황에 맞춰 사용)
- **유형 1 (질문형 - AEO 최강)**: 검색자의 의도를 저격. (예: "청년 일자리 부족, 원인은 무엇인가요?")
- **유형 2 (명사형 - 구체적)**: 핵심 정보 제공. (예: "청년이 돌아오는 도시를 만드는 방법")
- **유형 3 (데이터형 - 신뢰성)**: 숫자 포함. (예: "공공 임대 5만 호 공급 세부 계획")
- **유형 4 (절차형 - 실용성)**: 단계별 가이드.
- **유형 5 (비교형 - 차별화)**: 대조 분석.

# Input Paragraphs
"""

        # Append Paragraphs
        for i, sec in enumerate(sections):
            prompt += f"[Paragraph {i+1}]\n{sec[:400]}...\n\n"

        prompt += """
# Output Format (JSON Only)
반드시 아래 JSON 포맷으로 출력하세요. 순서는 단락 순서와 일치해야 합니다.
{
  "headings": [
    "생성된 소제목1",
    "생성된 소제목2"
  ]
}
"""
        
        # Retry Logic
        max_retries = 3
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                response_text = await generate_content_async(
                    prompt, 
                    model_name=self.model_name,
                    response_mime_type='application/json'
                )
                
                # Check JSON validity
                parsed = json.loads(response_text)
                if 'headings' in parsed and isinstance(parsed['headings'], list):
                    processed = []
                    for h in parsed['headings']:
                        h_str = str(h).strip().strip('"\'')
                        if len(h_str) > 28:
                             h_str = h_str[:27] + "..."
                        processed.append(h_str)
                    return processed
                else:
                    raise ValueError("JSON parse successful but 'headings' array missing")

            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ [SubheadingAgent] Attempt {attempt} failed: {e}")
                await asyncio.sleep(1)

        logger.error(f"❌ [SubheadingAgent] Failed after {max_retries} attempts.")
        return []
