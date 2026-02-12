
import logging
import asyncio
from typing import Dict, Any, List, Optional
import copy

from .core.structure_agent import StructureAgent
from .core.keyword_injector_agent import KeywordInjectorAgent
from .core.style_agent import StyleAgent
from .core.title_agent import TitleAgent
from .core.compliance_agent import ComplianceAgent
from .core.subheading_agent import SubheadingAgent
from .core.seo_agent import SEOAgent
from .core.editor_agent import EditorAgent
from .core.writer_agent import WriterAgent

logger = logging.getLogger(__name__)

PIPELINES = {
    'modular': [
        {'agent': StructureAgent, 'name': 'StructureAgent', 'required': True},
        {'agent': KeywordInjectorAgent, 'name': 'KeywordInjectorAgent', 'required': True},
        {'agent': StyleAgent, 'name': 'StyleAgent', 'required': True},
        {'agent': SubheadingAgent, 'name': 'SubheadingAgent', 'required': True},
        {'agent': TitleAgent, 'name': 'TitleAgent', 'required': True},
        {'agent': ComplianceAgent, 'name': 'ComplianceAgent', 'required': True},
        {'agent': SEOAgent, 'name': 'SEOAgent', 'required': False}
    ],
    'standard': [
        {'agent': WriterAgent, 'name': 'WriterAgent', 'required': True},
        {'agent': SEOAgent, 'name': 'SEOAgent', 'required': True}
    ]
}

QUALITY_THRESHOLDS = {
    'MAX_REFINEMENT_ATTEMPTS': 3,
    'SEO_SCORE_MIN': 0.8  # Not strictly used if pass/fail boolean
}

class Orchestrator:
    def __init__(self, options: Dict[str, Any] = None):
        self.options = options or {}
        self.pipeline_name = self.options.get('pipeline', 'modular')
        self.pipeline = PIPELINES.get(self.pipeline_name, PIPELINES['modular'])
        self.editor_agent = EditorAgent(options=self.options)

    async def run(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        context = copy.deepcopy(initial_context)
        context['history'] = []
        
        logger.info(f"Starting pipeline: {self.pipeline_name}")
        
        for step in self.pipeline:
            AgentClass = step['agent']
            agent_name = step['name']
            required = step['required']
            
            logger.info(f"Running agent: {agent_name}")
            
            try:
                # Instantiate agent
                agent = AgentClass(options=self.options)
                
                # Execution
                result = await agent.run(context)
                
                # Update context with result
                # Different agents return specific keys, but commonly 'content', 'title', etc.
                if result:
                    context.update(result)
                    if 'previousResults' not in context:
                        context['previousResults'] = {}
                    context['previousResults'][agent_name] = result
                    
                    context['history'].append({
                        'agent': agent_name,
                        'success': True,
                        'result': result
                    })
                
                # Check for critical failure or quality check if needed per step?
                # Usually Orchestrator checks quality at the end or specific checkpoints.
                # In JS, it ran sequentially.
                
                # Special handling for Writer/Structure output to become 'content'
                if result.get('content') and agent_name in ['StructureAgent', 'WriterAgent']:
                    context['content'] = result['content']
                
            except Exception as e:
                logger.error(f"Agent {agent_name} failed: {e}")
                context['history'].append({
                    'agent': agent_name,
                    'success': False,
                    'error': str(e)
                })
                if required:
                    raise RuntimeError(f"Required agent {agent_name} failed: {e}")
        
        # Post-pipeline Quality Assurance (Refinement Loop)
        final_context = await self.ensure_quality_threshold(context)
        
        return final_context

    async def ensure_quality_threshold(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check compliance and SEO results. If validation fails, run refinement loop.
        """
        # We need validation results. If ComplianceAgent or SEOAgent ran, they are in context.
        # But `context.update(result)` merges keys.
        # ComplianceAgent returns 'compliancePassed', 'issues'.
        # SEOAgent returns 'seoPassed', 'details'.
        
        compliance_passed = context.get('compliancePassed', True)
        seo_passed = context.get('seoPassed', True)
        
        # If ComplianceAgent wasn't run (not in pipeline), treat as passed or check requirements
        has_compliance = any(s['name'] == 'ComplianceAgent' for s in self.pipeline)
        if has_compliance and 'compliancePassed' not in context:
             # It ran but maybe failed? Or we are checking context state
             pass
             
        # Check critical issues
        issues = context.get('issues', [])
        # Defensive filter
        critical_issues = [i for i in issues if isinstance(i, dict) and i.get('severity') in ['critical', 'high']]
        
        if compliance_passed and seo_passed and not critical_issues:
             logger.info("Quality threshold met.")
             return context
             
        logger.info(f"Quality threshold FAILED. Compliance: {compliance_passed}, SEO: {seo_passed}, Critical Issues: {len(critical_issues)}")
        
        # Start Refinement Loop
        return await self.run_refinement_loop(context)

    async def run_refinement_loop(self, context: Dict[str, Any]) -> Dict[str, Any]:
        max_attempts = self.options.get('maxRefinementSteps', QUALITY_THRESHOLDS['MAX_REFINEMENT_ATTEMPTS'])
        attempt = 0
        current_context = context
        
        while attempt < max_attempts:
            attempt += 1
            logger.info(f"Refinement Attempt {attempt}/{max_attempts}")
            
            # Prepare inputs for EditorAgent
            # EditorAgent expects 'validationResult', 'keywordResult', etc.
            # We map context to EditorAgent input structure
            editor_input = {
                'content': current_context.get('content', ''),
                'title': current_context.get('title', ''),
                'validationResult': {
                    'details': {
                         'electionLaw': {'violations': [i['message'] for i in current_context.get('issues', []) if isinstance(i, dict) and i.get('type') == 'ELECTION_LAW_VIOLATION']},
                         'repetition': {'repeatedSentences': [i['message'] for i in current_context.get('issues', []) if isinstance(i, dict) and i.get('type') == 'repetition']}, # Logic to extract
                         # We need to preserve 'details' structure better from previous agents if possible.
                         # Context merging flattens it.
                         # ComplianceAgent returns 'issues', 'factCheck', 'riskReport'.
                         # SEOAgent returns 'details' (nested).
                    }
                },
                'keywordResult': current_context.get('details', {}).get('keywords', {}),
                'keywords': current_context.get('keywords', []),
                'status': current_context.get('status', 'active'),
                'targetWordCount': 2000 # Default or from config
            }
            
            # Run EditorAgent
            editor_result = await self.editor_agent.run(editor_input)
            
            if not editor_result.get('fixed'):
                logger.warning("EditorAgent made no changes.")
                break
                
            # Update content
            current_context['content'] = editor_result['content']
            current_context['title'] = editor_result['title']
            
            # Re-validate
            # We must run ComplianceAgent and SEOAgent again on the NEW content.
            # Using standalone agents to re-verify.
            
            logger.info("Re-validating refined content...")
            
            compliance_agent = ComplianceAgent(options=self.options)
            seo_agent = SEOAgent(options=self.options)
            
            c_res = await compliance_agent.run(current_context)
            current_context.update(c_res) # Update issues/status
            
            s_res = await seo_agent.run(current_context)
            current_context.update(s_res)
            
            # Check pass
            issues = current_context.get('issues', [])
            critical_issues = [i for i in issues if isinstance(i, dict) and i.get('severity') in ['critical', 'high']]
            
            if current_context.get('compliancePassed') and current_context.get('seoPassed') and not critical_issues:
                logger.info("Refinement Successful!")
                return current_context
                
            logger.info("Refinement failed to meet threshold, retrying if attempts left.")
            
        logger.warning("Max refinement attempts reached. Returning last best result.")
        return current_context
