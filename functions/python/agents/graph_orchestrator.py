import asyncio
import logging
import operator
from typing import Dict, Any, List, Optional, Annotated, TypedDict
import copy

from langgraph.graph import StateGraph, END

# Import existing agents
from .core.structure_agent import StructureAgent
from .core.keyword_injector_agent import KeywordInjectorAgent
from .core.style_agent import StyleAgent
from .core.title_agent import TitleAgent
from .core.compliance_agent import ComplianceAgent
from .core.seo_agent import SEOAgent
from .core.editor_agent import EditorAgent

logger = logging.getLogger(__name__)

# 1. State Definition
class AgentState(TypedDict):
    # Inputs
    topic: str
    category: str
    user_keywords: List[str]
    user_profile: Dict[str, Any]
    options: Dict[str, Any] # Configuration options (model name, etc.)
    
    # Shared Data
    content: Optional[str]
    title: Optional[str]
    
    # Analysis & Verification Results
    keywords: List[Dict[str, Any]]
    compliance_result: Dict[str, Any]
    seo_result: Dict[str, Any]
    
    # History & Control
    history: Annotated[List[Dict[str, Any]], operator.add]
    refinement_count: int
    quality_met: bool
    fatal_error: bool
    
    # Miscellaneous context (preserved from input)
    check_run_id: Optional[str]
    background: Optional[str]
    instructions: Optional[str]
    
class GraphOrchestrator:
    def __init__(self, options: Dict[str, Any] = None):
        self.options = options or {}
        # Make sure valid 'modelName' is in options if not present
        if 'modelName' not in self.options:
             self.options['modelName'] = 'models/gemini-2.5-flash'
             
        self.max_refinement_steps = self.options.get('maxRefinementSteps', 2)
        self.app = self.build_graph()
        
    def build_graph(self):
        # Initialize Graph
        workflow = StateGraph(AgentState)
        
        # Add Nodes
        workflow.add_node("structure_node", self.run_structure_agent)
        workflow.add_node("parallel_mid_node", self.run_parallel_mid_agents)
        workflow.add_node("style_node", self.run_style_agent)
        workflow.add_node("compliance_node", self.run_compliance_agent)
        workflow.add_node("seo_node", self.run_seo_agent)
        workflow.add_node("editor_node", self.run_editor_agent)
        
        # Set Entry Point
        workflow.set_entry_point("structure_node")
        
        # Optimized Flow: KeywordInjector + Title run in parallel, then Style
        workflow.add_edge("structure_node", "parallel_mid_node")
        workflow.add_edge("parallel_mid_node", "style_node")
        workflow.add_edge("style_node", "compliance_node")
        
        # Conditional Edges for Compliance
        workflow.add_conditional_edges(
            "compliance_node",
            self.check_compliance_status,
            {
                "end": END,
                "next": "seo_node"
            }
        )
        
        # Conditional Edges for SEO (Refinement Loop)
        workflow.add_conditional_edges(
            "seo_node",
            self.check_seo_quality,
            {
                "end": END,
                "refine": "editor_node"
            }
        )
        
        # Refinement Loop back to Compliance
        workflow.add_edge("editor_node", "compliance_node")
        
        return workflow.compile()
        
    async def run(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry point to run the graph"""
        
        logger.info("[GraphOrchestrator] Initializing Graph Run")
        
        # Initialize State from context
        # Extract keywords correctly
        user_keywords = initial_context.get("userKeywords", [])
        if not user_keywords and initial_context.get("keywords"):
             user_keywords = initial_context.get("keywords")
             
        # Extract author/profile
        user_profile = initial_context.get("userProfile", {})
        if not user_profile and initial_context.get("author"):
             user_profile = initial_context.get("author")

        state: AgentState = {
            "topic": initial_context.get("topic", ""),
            "category": initial_context.get("category", ""),
            "user_keywords": user_keywords,
            "user_profile": user_profile,
            "options": self.options,
            
            "content": initial_context.get('content', None), # Sometimes predefined content?
            "title": initial_context.get('title', None),
            
            "keywords": [],
            "compliance_result": {},
            "seo_result": {},
            
            "history": [],
            "refinement_count": 0,
            "quality_met": False,
            "fatal_error": False,
            
            "check_run_id": initial_context.get("check_run_id"),
            "background": initial_context.get("background"),
            "instructions": initial_context.get("instructions"),
        }
        
        try:
            # Explicitly enable tracing for this run
            from langchain_core.tracers.context import tracing_v2_enabled
            project_name = "ai-secretary-trace" # Hardcoded or from env
            
            with tracing_v2_enabled(project_name=project_name):
                 result_state = await self.app.ainvoke(state)
            
            # Create a final result object compatible with legacy format
            final_result = {
                "content": result_state.get("content"),
                "title": result_state.get("title"),
                "success": not result_state.get("fatal_error"),
                "compliancePassed": result_state.get("compliance_result", {}).get("passed", False),
                "seoPassed": result_state.get("seo_result", {}).get("seoPassed", False),
                "issues": result_state.get("compliance_result", {}).get("issues", []) + result_state.get("seo_result", {}).get("issues", []),
                # Include full history for debugging
                "history": result_state.get("history", [])
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"[GraphOrchestrator] Graph Execution Failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }


    # --- Node Functions ---
    # NOTE: LangGraph nodes should return a update DICT, not the full state (unless configured otherwise).
    # Since we use TypedDict state, we return partial updates.
    
    async def run_structure_agent(self, state: AgentState):
        logger.info("[Graph] Running StructureAgent")
        agent = StructureAgent(options=self.options)
        context = self._map_state_to_context(state)
        
        try:
            result = await agent.run(context)
            if not result: raise ValueError("StructureAgent returned empty result")
            return {
                "content": result.get("content"),
                "history": [{"agent": "StructureAgent", "success": True, "result_summary": "Content Generated"}]
            }
        except Exception as e:
            logger.error(f"StructureAgent failed: {e}")
            return {"history": [{"agent": "StructureAgent", "success": False, "error": str(e)}], "fatal_error": True}

    async def run_parallel_mid_agents(self, state: AgentState):
        """KeywordInjectorAgent와 TitleAgent를 병렬 실행하여 ~10초 절감."""
        logger.info("[Graph] Running KeywordInjectorAgent + TitleAgent in parallel")
        context = self._map_state_to_context(state)

        keyword_agent = KeywordInjectorAgent(options=self.options)
        title_agent = TitleAgent(options=self.options)

        async def _run_keyword():
            try:
                result = await keyword_agent.run(context)
                return {
                    "keywords": result.get("keywords", []) if result else [],
                    "history": [{"agent": "KeywordInjectorAgent", "success": True}],
                }
            except Exception as e:
                logger.warning(f"KeywordInjectorAgent failed (non-fatal): {e}")
                return {"history": [{"agent": "KeywordInjectorAgent", "success": False, "error": str(e)}]}

        async def _run_title():
            try:
                result = await title_agent.run(context)
                return {
                    "title": result.get("title"),
                    "history": [{"agent": "TitleAgent", "success": True, "title": result.get("title")}],
                }
            except Exception as e:
                logger.warning(f"TitleAgent failed (non-fatal): {e}")
                return {"history": [{"agent": "TitleAgent", "success": False, "error": str(e)}]}

        keyword_result, title_result = await asyncio.gather(_run_keyword(), _run_title())

        # 두 결과를 병합하여 state 업데이트
        merged = {}
        for partial in [keyword_result, title_result]:
            for key, value in partial.items():
                if key == "history":
                    merged.setdefault("history", []).extend(value)
                else:
                    merged[key] = value
        return merged

    async def run_style_agent(self, state: AgentState):
        logger.info("[Graph] Running StyleAgent")
        agent = StyleAgent(options=self.options)
        context = self._map_state_to_context(state)
        
        try:
            result = await agent.run(context)
            return {
                "content": result.get("content"),
                "history": [{"agent": "StyleAgent", "success": True}]
            }
        except Exception as e:
             return {"history": [{"agent": "StyleAgent", "success": False, "error": str(e)}], "fatal_error": True}

    async def run_compliance_agent(self, state: AgentState):
        logger.info("[Graph] Running ComplianceAgent")
        agent = ComplianceAgent(options=self.options)
        context = self._map_state_to_context(state)
        
        try:
            result = await agent.run(context)
            
            # Check for fatal errors
            issues = result.get('issues', [])
            # Assume 'critical' severity issues are fatal if not fixable by editor?
            # For now, let's just log them. The loop will handle refinement.
            # TRUE FATAL might be API errors or violations that AI explicitly refused.
            # We implemented logic: fatal if critical and not fixable.
            # But let's simplify: if result['pass'] is False, it's not fatal unless repeated.
            
            return {
                "compliance_result": result,
                "history": [{"agent": "ComplianceAgent", "success": True, "passed": result.get("compliancePassed", False)}]
            }
        except Exception as e:
             return {"history": [{"agent": "ComplianceAgent", "success": False, "error": str(e)}]}

    async def run_seo_agent(self, state: AgentState):
        logger.info("[Graph] Running SEOAgent")
        agent = SEOAgent(options=self.options)
        context = self._map_state_to_context(state)
        
        try:
            result = await agent.run(context)
            return {
                "seo_result": result,
                "history": [{"agent": "SEOAgent", "success": True, "passed": result.get("seoPassed", False)}]
            }
        except Exception as e:
             return {"history": [{"agent": "SEOAgent", "success": False, "error": str(e)}]}

    async def run_editor_agent(self, state: AgentState):
        logger.info(f"[Graph] Running EditorAgent (Refinement #{state['refinement_count'] + 1})")
        agent = EditorAgent(options=self.options)
        
        # Prepare special input for Editor (Mocking legacy orchestrator logic)
        context = self._map_state_to_context(state)
        
        # Extract issues
        comp_res = state.get("compliance_result", {})
        seo_res = state.get("seo_result", {})
        
        # Map to Editor Inputs
        editor_input = {
            'content': state.get('content', ''),
            'title': state.get('title', ''),
            'validationResult': {
                'details': {
                    'electionLaw': {'violations': [i.get('message') for i in comp_res.get('issues', []) if isinstance(i, dict) and i.get('type') == 'ELECTION_LAW_VIOLATION']},
                    'seo': {'issues': seo_res.get('issues', [])},
                }
            },
            'keywordResult': {'keywords': state.get('keywords', [])},
            'keywords': state.get('user_keywords', []),
            'status': state.get('user_profile', {}).get('status', 'active'),
            'targetWordCount': 2000,
            
            # Add optionals for migration completeness (even if missing in Python agent init)
            'userKeywords': state.get('user_keywords', [])
        }
        
        try:
            result = await agent.run(editor_input)
            
            if not result.get('fixed'):
                 return {
                     "refinement_count": state["refinement_count"] + 1,
                     "history": [{"agent": "EditorAgent", "success": True, "result": "No changes made"}]
                 }
            
            return {
                "content": result.get("content"),
                "title": result.get("title") or state["title"],
                "refinement_count": state["refinement_count"] + 1,
                "history": [{"agent": "EditorAgent", "success": True, "edited": True}]
            }
        except Exception as e:
            return {
                "refinement_count": state["refinement_count"] + 1,
                "history": [{"agent": "EditorAgent", "success": False, "error": str(e)}]
            }

    # --- Conditional Functions ---
    
    def check_compliance_status(self, state: AgentState):
        if state.get("fatal_error"):
            logger.warning("[Graph] Fatal error flagged. Stopping.")
            return "end"
        return "next"
        
    def check_seo_quality(self, state: AgentState):
        # Determine Pass/Fail logic
        c_res = state.get("compliance_result", {})
        s_res = state.get("seo_result", {})
        
        # Python agents often use keys 'compliancePassed' / 'seoPassed' or generic 'passed'
        # Adjust logic to look for any of them
        c_passed = c_res.get("passed") or c_res.get("compliancePassed", False)
        s_passed = s_res.get("passed") or s_res.get("seoPassed", False)
        
        # Critical issues check
        c_issues = c_res.get("issues", [])
        has_critical = any(i.get('severity') in ['critical', 'high'] for i in c_issues if isinstance(i, dict))
        
        quality_met = c_passed and s_passed and not has_critical
        
        if quality_met:
            logger.info("[Graph] Quality threshold met.")
            return "end"
            
        if state["refinement_count"] >= self.max_refinement_steps:
            logger.warning("[Graph] Max refinement attempts reached.")
            return "end"
            
        logger.info(f"[Graph] Quality not met (Compliance={c_passed}, SEO={s_passed}). Proceeding to Refinement.")
        return "refine"

    # --- Helpers ---
    
    def _map_state_to_context(self, state: AgentState) -> Dict[str, Any]:
        """Maps State back to the flat context structure expected by legacy Agents"""
        
        # Safely get nested dicts
        comp_res = state.get("compliance_result", {})
        seo_res = state.get("seo_result", {})
        
        context = {
            "topic": state["topic"],
            "category": state["category"],
            "userKeywords": state["user_keywords"],
            "keywords": state["user_keywords"], # Alias
            "userProfile": state["user_profile"],
            "options": state["options"],
            
            # Content state
            "content": state.get("content"),
            "title": state.get("title"),
            
            # Previous results (Approximation for legacy agent expects)
            "previousResults": {
                "KeywordInjectorAgent": {"keywords": state.get("keywords")},
                "StyleAgent": {"content": state.get("content")},
                "WriterAgent": {"content": state.get("content")}, # Alias for legacy compatibility
                "StructureAgent": {"content": state.get("content")},
                "TitleAgent": {"title": state.get("title")},
                "ComplianceAgent": comp_res,
                "SEOAgent": seo_res,
            },
            
            # Pass-throughs
            "check_run_id": state.get("check_run_id"),
            "background": state.get("background"),
            "instructions": state.get("instructions"),
        }
        
        # Helper to merge issues flattened if some agents expect it
        context['issues'] = comp_res.get('issues', []) + seo_res.get('issues', [])
        
        return context
