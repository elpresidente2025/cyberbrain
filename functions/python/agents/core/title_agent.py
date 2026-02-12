
import logging
import re
from typing import Dict, Any, Optional

from ..base_agent import Agent
from ..common.title_generation import generate_and_validate_title

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
        # Prefer optimized content from previous agents, fallback to original
        content_preview = context.get('optimizedContent') or context.get('content') or ''

        # Strip HTML for preview
        content_preview_text = re.sub(r'<[^>]*>', ' ', content_preview)
        content_preview_text = re.sub(r'\s+', ' ', content_preview_text).strip()

        user_keywords = context.get('keywords', []) # User provided keywords
        generated_keywords = (context.get('analysis') or {}).get('keywords', []) # SEO extracts

        full_name = (context.get('author') or {}).get('name', '')
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
            'stanceText': stance_text  # 🔑 [NEW] 입장문 전달
        }

        # Override type if debug/forced
        if (self.options or {}).get('forceType'):
            params['_forcedType'] = self.options['forceType']

        async def generate_fn(prompt: str) -> str:
            if not self._client:
                raise ValueError("Model not initialized")
            return await generate_content_async(prompt, model_name=self.model_name)

        logger.info(f"[{self.name}] Generating title for topic: {topic}")

        try:
            result = await generate_and_validate_title(
                generate_fn,
                params,
                options={
                    'minScore': 70,
                    'maxAttempts': 3,
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
