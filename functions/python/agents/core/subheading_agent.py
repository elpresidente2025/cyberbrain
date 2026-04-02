import logging
import re
from typing import Dict, Any, List, Optional
from ..base_agent import Agent

# Local imports
from ..common.h2_guide import (
    H2_BEST_RANGE,
    H2_MAX_LENGTH,
    build_h2_rules,
    has_incomplete_h2_ending,
    normalize_h2_style,
    sanitize_h2_text,
)
from ..common.gemini_client import StructuredOutputError, generate_json_async

logger = logging.getLogger(__name__)

SUBHEADING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "headings": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        }
    },
    "required": ["headings"],
}

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
        'style': 'aeo',
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
        'style': 'aeo',
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
        'style': 'aeo',
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
        'style': 'aeo',
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
        h2_style = normalize_h2_style(style_config.get('style'))
        is_assertive = h2_style == 'assertive'
        
        # 🔑 [NEW] 입장문 요약 (소제목에 핵심 주장 반영용)
        stance_hint = f"**[입장문 핵심]**: {stance_text[:300]}..." if stance_text else ""
        style_description = str(style_config.get('description') or '').strip() or '(없음)'
        preferred_types = ", ".join(
            str(item).strip() for item in style_config.get('preferredTypes', []) if str(item).strip()
        ) or '(없음)'
        role_name = (
            "정치 논평 전문 에디터"
            if is_assertive
            else "AEO(Answer Engine Optimization) & SEO 전문 카피라이터"
        )
        task_summary = (
            "주어진 논평/입장문 단락들을 분석하여, 날카롭고 주장이 담긴 소제목(H2)을 생성해야 합니다."
            if is_assertive
            else "주어진 본문 단락들을 분석하여, 검색 엔진과 사용자 모두에게 매력적인 최적의 소제목(H2)을 생성해야 합니다."
        )
        prompt = f"""
# Role Definition
당신은 대한민국 최고의 **{role_name}**입니다.
{task_summary}

# Input Data
- **Context**: {entity_hints or '(없음)'}
- **Target Count**: {target_count} Headings
- **Style Summary**: {style_description}
- **Preferred Types**: {preferred_types}
{stance_hint}

# [CRITICAL] H2 Rulebook (SSOT)
아래 XML 규칙 블록을 절대 우선으로 따르세요. 규칙, 금지어, few-shot 예시는 이 블록이 단일 원천입니다.
{build_h2_rules(h2_style)}

# Additional Constraints
- 단락마다 소제목 1개씩만 생성하세요.
- 입력 순서를 바꾸지 마세요.
- 소제목 텍스트만 생성하고 번호, 따옴표, 불릿은 넣지 마세요.
- {H2_MAX_LENGTH - 2}자를 넘기지 마세요. (네이버 최적 범위 {H2_BEST_RANGE}자 이내를 목표로 하세요.)
- 소제목은 반드시 완결된 어절로 끝나야 합니다. 조사("를", "을", "의", "에서", "과" 등)나 미완결 어미("겠", "하는", "있는" 등)로 끝나는 소제목은 금지입니다.
- 본문 구절("미래에 대한 확신을", "이뤄내겠습니다" 등)을 잘라 붙여 소제목을 만들지 마세요.
- 생성한 소제목을 다시 읽고 조사나 단어가 중복되거나 의미가 어색한 부분이 있으면 고친 뒤 최종 결과만 출력하세요.
- 같은 단어를 연속으로 반복하거나 "도약을을"처럼 조사 오타가 남은 소제목은 출력하지 마세요.

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
        
        try:
            payload = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.3,
                max_output_tokens=1200,
                retries=2,
                response_schema=SUBHEADING_RESPONSE_SCHEMA,
                required_keys=("headings",),
            )

            headings = payload.get("headings")
            if not isinstance(headings, list):
                raise StructuredOutputError("headings must be an array.")

            processed: List[str] = []
            blocked_headings: List[str] = []
            for heading in headings:
                try:
                    heading_text = sanitize_h2_text(str(heading))
                except ValueError:
                    continue
                if has_incomplete_h2_ending(heading_text):
                    blocked_headings.append(heading_text)
                    continue
                processed.append(heading_text)

            if blocked_headings:
                logger.warning("[%s] Incomplete H2 surfaces blocked: %s", self.name, blocked_headings[:3])
                raise StructuredOutputError(f"incomplete headings after normalization: {blocked_headings[:3]}")
            if not processed:
                raise StructuredOutputError("headings array is empty after normalization.")
            return processed
        except StructuredOutputError as error:
            logger.error(f"❌ [SubheadingAgent] Structured output validation failed: {error}")
        except Exception as error:
            logger.error(f"❌ [SubheadingAgent] Generation failed: {error}")
        return []
