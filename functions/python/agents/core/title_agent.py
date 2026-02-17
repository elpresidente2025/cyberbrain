
import logging
import re
from typing import Dict, Any, Optional

from ..base_agent import Agent
from ..common.title_generation import generate_and_validate_title, resolve_title_purpose

logger = logging.getLogger(__name__)

class TitleAgent(Agent):
    def __init__(self, name: str = 'TitleAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = (options or {}).get('modelName', DEFAULT_MODEL)
        self._client = get_client()
        if not self._client:
            logger.warning("GEMINI_API_KEY not set for TitleAgent")

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        TitleAgent main process
        """
        from ..common.gemini_client import generate_content_async

        # Extract inputs
        topic = context.get('topic', '')
        # Prefer optimized content from previous agents, otherwise use original content
        content_preview = context.get('optimizedContent') or context.get('content') or ''

        # Strip HTML for preview
        content_preview_text = re.sub(r'<[^>]*>', ' ', content_preview)
        content_preview_text = re.sub(r'\s+', ' ', content_preview_text).strip()

        user_keywords = context.get('userKeywords') or context.get('keywords') or []  # User provided keywords
        if not isinstance(user_keywords, list):
            user_keywords = []
        generated_keywords = (context.get('analysis') or {}).get('keywords', []) # SEO extracts
        context_analysis = context.get('contextAnalysis')
        if not isinstance(context_analysis, dict):
            context_analysis = {}

        author = context.get('author')
        if not isinstance(author, dict):
            author = {}
        user_profile = context.get('userProfile')
        if not isinstance(user_profile, dict):
            user_profile = {}

        full_name = str(
            author.get('name')
            or user_profile.get('name')
            or user_profile.get('displayName')
            or ''
        ).strip()
        category = context.get('category', 'activity-report')
        status = context.get('status', 'active') # Election status
        title_scope = (context.get('config') or {}).get('titleScope', {})
        background_text = context.get('background', '')
        
        # 🔑 [NEW] 입장문(심층 주제) 추출 - 제목에 핵심 주장 반영
        stance_text = context.get('stanceText', '')
        if stance_text:
            logger.info(f"[{self.name}] 입장문 {len(stance_text)}자 활용하여 제목 생성")

        params = {
            'topic': topic,
            'contentPreview': content_preview_text,
            'userKeywords': user_keywords, # User intent keywords
            'keywords': generated_keywords, # SEO extracts
            'fullName': full_name,
            'category': category,
            'status': status,
            'titleScope': title_scope,
            'backgroundText': background_text,
            'stanceText': stance_text,  # 🔑 [NEW] 입장문 전달
            'contextAnalysis': context_analysis,
        }

        # 최근 제목을 전달해 동일 패턴 재생산을 줄인다.
        recent_titles = []
        for key in ('recentTitles', 'previousTitles'):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        recent_titles.append(item.strip())
        title_history_ctx = context.get('titleHistory')
        if isinstance(title_history_ctx, list):
            for item in title_history_ctx:
                title_text = ''
                if isinstance(item, dict):
                    title_text = str(item.get('title') or '').strip()
                elif isinstance(item, str):
                    title_text = item.strip()
                if title_text:
                    recent_titles.append(title_text)
        dedup_recent_titles = []
        seen_recent_titles = set()
        for title in recent_titles:
            if title in seen_recent_titles:
                continue
            seen_recent_titles.add(title)
            dedup_recent_titles.append(title)
        if dedup_recent_titles:
            params['recentTitles'] = dedup_recent_titles[:10]

        # Override type if debug/forced
        if (self.options or {}).get('forceType'):
            params['_forcedType'] = self.options['forceType']

        generation_temperature = 0.7

        async def generate_fn(prompt: str) -> str:
            if not self._client:
                raise ValueError("Model not initialized")
            return await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=generation_temperature,
                options={
                    'top_p': 0.95,
                    'top_k': 40,
                },
            )

        logger.info(f"[{self.name}] Generating title for topic: {topic}")
        title_purpose = resolve_title_purpose(topic, params)
        # 행사 안내형은 규칙 준수 우선으로 샘플링 강도를 낮춰 안정적으로 생성한다.
        generation_temperature = 0.25 if title_purpose == 'event_announcement' else 0.7
        min_score = 70

        try:
            result = await generate_and_validate_title(
                generate_fn,
                params,
                options={
                    'minScore': min_score,
                    'maxAttempts': 3,
                    'candidateCount': int((self.options or {}).get('candidateCount', 5)),
                    'similarityThreshold': float((self.options or {}).get('similarityThreshold', 0.78)),
                    'maxSimilarityPenalty': int((self.options or {}).get('maxSimilarityPenalty', 18)),
                    'recentTitles': params.get('recentTitles', []),
                    'temperature': generation_temperature,
                    'onProgress': lambda p: logger.debug(f"[{self.name}] Attempt {p['attempt']} finished. Score: {p.get('score', 0)}")
                }
            )

            logger.info(f"[{self.name}] Selected Title: {result['title']} (Score: {result['score']})")

            return {
                'title': result['title'],
                'titleScore': result['score'],
                'titleHistory': result['history'],
                'titleType': result.get('analysis', {}).get('type', 'UNKNOWN')
            }

        except Exception as e:
            # 🚨 NO FALLBACK ALLOWED as per user request.
            # Fail loudly so debugging is possible.
            logger.error(f"[{self.name}] CRITICAL FAILURE: {e}")
            raise RuntimeError(f"[TitleAgent Failed] {str(e)}") from e
