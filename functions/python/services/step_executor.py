# services/step_executor.py
"""
Agent Step Executor for Pipeline Processing
"""

import importlib
import asyncio
import time
import logging
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger(__name__)


PIPELINE_STEPS = {
    "modular": [
        {"name": "StructureAgent", "module": "agents.core.structure_agent", "class": "StructureAgent"},
        {"name": "KeywordInjectorAgent", "module": "agents.core.keyword_injector_agent", "class": "KeywordInjectorAgent"},
        {"name": "StyleAgent", "module": "agents.core.style_agent", "class": "StyleAgent"},
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
        
        try:
            # Lazy import로 Cold Start 최적화
            module = importlib.import_module(module_path)
            AgentClass = getattr(module, class_name)
            agent = AgentClass(options=self.options)
            
            # 에이전트 실행
            result = await agent.run(context)
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Step {agent_name} completed in {duration_ms}ms")
            
            return result or {}, duration_ms
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Step {agent_name} failed after {duration_ms}ms: {e}")
            raise
    
    def run_sync(self, step_info: Dict[str, str], context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        동기식 래퍼 - Cloud Functions 환경용
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.execute_step(step_info, context))
        finally:
            loop.close()
