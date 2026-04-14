# services/step_executor.py
"""
Agent Step Executor for Pipeline Processing
"""

import asyncio
import importlib
import logging
import time
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger(__name__)


PIPELINE_STEPS = {
    "modular": [
        {"name": "StructureAgent", "module": "agents.core.structure_agent", "class": "StructureAgent"},
        {"name": "KeywordInjectorAgent", "module": "agents.core.keyword_injector_agent", "class": "KeywordInjectorAgent"},
        {"name": "StyleAgent", "module": "agents.core.style_agent", "class": "StyleAgent"},
        {"name": "SubheadingAgent", "module": "agents.core.subheading_agent", "class": "SubheadingAgent"},
        {"name": "ComplianceAgent", "module": "agents.core.compliance_agent", "class": "ComplianceAgent"},
        {"name": "SEOAgent", "module": "agents.core.seo_agent", "class": "SEOAgent"},
        {"name": "TitleAgent", "module": "agents.core.title_agent", "class": "TitleAgent"},
    ],
    "standard": [
        {"name": "WriterAgent", "module": "agents.core.writer_agent", "class": "WriterAgent"},
        {"name": "SEOAgent", "module": "agents.core.seo_agent", "class": "SEOAgent"},
    ]
}


class StepExecutor:
    """에이전트 단계 실행기"""
    
    def __init__(self, options: Dict[str, Any] = None):
        self.options = options or {}
    
    def get_step_info(self, pipeline: str, step_index: int) -> Optional[Dict[str, str]]:
        """단계 정보 조회"""
        steps = PIPELINE_STEPS.get(pipeline, PIPELINE_STEPS["modular"])
        if step_index < 0 or step_index >= len(steps):
            return None
        return steps[step_index]
    
    def get_total_steps(self, pipeline: str) -> int:
        """전체 단계 수"""
        return len(PIPELINE_STEPS.get(pipeline, PIPELINE_STEPS["modular"]))
    
    def get_all_steps(self, pipeline: str) -> List[Dict[str, str]]:
        """파이프라인의 모든 단계 반환"""
        return PIPELINE_STEPS.get(pipeline, PIPELINE_STEPS["modular"])
    
    async def execute_step(self, step_info: Dict[str, str], context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        에이전트 단계 비동기 실행
        
        Returns:
            Tuple[Dict[str, Any], int]: (result, duration_ms)
        """
        module_path = step_info["module"]
        class_name = step_info["class"]
        agent_name = step_info["name"]
        
        start_time = time.time()
        logger.info(f"Executing step: {agent_name}")

        max_step_attempts = 2 if agent_name == "TitleAgent" else 1
        last_error: Optional[Exception] = None

        def _is_retryable_title_error(error: Exception) -> bool:
            message = str(error or "").lower()
            retry_markers = (
                "structured output is not valid json",
                "unterminated string",
                "empty response",
                "ai 응답이 비어 있습니다",
                "timeout",
                "timed out",
                "deadline exceeded",
                "service unavailable",
                "connection reset",
                "econnreset",
                "titlegen",
            )
            return any(marker in message for marker in retry_markers)

        for step_attempt in range(1, max_step_attempts + 1):
            try:
                # Lazy import로 Cold Start 최적화
                module = importlib.import_module(module_path)
                AgentClass = getattr(module, class_name)
                agent = AgentClass(options=self.options)

                # 에이전트 실행
                result = await agent.run(context)

                duration_ms = int((time.time() - start_time) * 1000)
                if step_attempt > 1:
                    logger.info(
                        "Step %s recovered on retry %s/%s in %sms",
                        agent_name,
                        step_attempt,
                        max_step_attempts,
                        duration_ms,
                    )
                else:
                    logger.info(f"Step {agent_name} completed in {duration_ms}ms")
                return result or {}, duration_ms

            except Exception as e:
                last_error = e
                duration_ms = int((time.time() - start_time) * 1000)
                retryable = (
                    agent_name == "TitleAgent"
                    and step_attempt < max_step_attempts
                    and _is_retryable_title_error(e)
                )
                if not retryable:
                    logger.error(f"Step {agent_name} failed after {duration_ms}ms: {e}")
                    raise

                wait_sec = 0.8 * step_attempt
                logger.warning(
                    "Step %s retrying (%s/%s) after %.1fs due to retryable error: %s",
                    agent_name,
                    step_attempt + 1,
                    max_step_attempts,
                    wait_sec,
                    e,
                )
                await asyncio.sleep(wait_sec)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Step {agent_name} failed after {duration_ms}ms: {last_error}")
        raise last_error if last_error else RuntimeError(f"Step {agent_name} failed")
    
    def run_sync(self, step_info: Dict[str, str], context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        동기식 래퍼 - Cloud Functions 환경용
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.execute_step(step_info, context))
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
            asyncio.set_event_loop(None)
