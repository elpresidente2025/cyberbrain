
import logging
import re
import json
import asyncio
from typing import Dict, Any, List, Optional
from ..base_agent import Agent
from ..common.natural_tone import build_natural_tone_prompt

logger = logging.getLogger(__name__)

# 선거법 위반 표현 패턴 (Regex)
PLEDGE_REPLACEMENTS = [
    (r'약속드?립니다', '필요성을 말씀드립니다'),
    (r'약속합니다', '필요하다고 봅니다'),
    (r'공약드?립니다', '방향을 제시합니다'),
    (r'공약합니다', '방향을 제시합니다'),
    (r'추진하겠(?:습니다)?', '추진이 필요합니다'),
    (r'마련하겠(?:습니다)?', '마련이 필요합니다'),
    (r'실현하겠(?:습니다)?', '실현이 필요합니다'),
    (r'강화하겠(?:습니다)?', '강화가 필요합니다'),
    (r'확대하겠(?:습니다)?', '확대가 필요합니다'),
    (r'줄이겠(?:습니다)?', '줄이는 노력이 필요합니다'),
    (r'늘리겠(?:습니다)?', '늘리는 방안이 필요합니다'),
    (r'되겠(?:습니다)?', '되는 방향을 모색해야 합니다'),
    (r'하겠(?:습니다)?', '할 필요가 있습니다')
]

# 서명 마커 (요약문 삽입 위치 파악용)
SIGNATURE_REGEX = r'(<p[^>]*>\s*감사합니다\.?\s*<\/p>|<p[^>]*>\s*감사드립니다\.?\s*<\/p>|<p[^>]*>\s*고맙습니다\.?\s*<\/p>|<p[^>]*>\s*[^<]*드림\s*<\/p>|감사합니다|감사드립니다|고맙습니다|사랑합니다|드림)'

class EditorAgent(Agent):
    def __init__(self, name: str = 'EditorAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = (options or {}).get('modelName', DEFAULT_MODEL)
        self._client = get_client()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refine content using LLM based on validation issues.
        Matches Node.js refineWithLLM logic.
        """
        from ..common.gemini_client import generate_content_async

        content = context.get('content', '')
        title = context.get('title', '')
        validation_result = context.get('validationResult', {})
        keyword_result = context.get('keywordResult', {})
        user_keywords = context.get('keywords', [])
        status = context.get('status', 'active')
        target_word_count = context.get('targetWordCount', 2000)

        # 1. Apply Hard Constraints First (Pre-LLM cleanups if any? Node.js does it post-LLM usually, but applyHardConstraintsOnly uses it)
        # We will use LLM first, then apply hard constraints as fallback/final polish.
        
        # Build prompt
        prompt = self.build_editor_prompt(
            content=content,
            title=title,
            validation_result=validation_result,
            keyword_result=keyword_result,
            user_keywords=user_keywords,
            status=status,
            target_word_count=target_word_count
        )

        if not self._client:
            logger.warning("No client for EditorAgent, returning original")
            return self.apply_hard_constraints(content, title, user_keywords, status)

        # Call LLM
        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                response_mime_type='application/json'
            )
            text = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', response_text).strip()
            result = json.loads(text)

            new_content = result.get('content', content)
            new_title = result.get('title', title)
            edit_summary = result.get('editSummary', [])

            # 2. Apply Hard Constraints (Post-LLM)
            final_result = self.apply_hard_constraints(
                content=new_content,
                title=new_title,
                user_keywords=user_keywords,
                status=status,
                previous_summary=edit_summary
            )
            
            return final_result

        except Exception as e:
            logger.error(f"EditorAgent failed: {e}")
            # Fallback to hard constraints only
            return self.apply_hard_constraints(content, title, user_keywords, status, error=str(e))

    def build_editor_prompt(self, content, title, validation_result, keyword_result, user_keywords, status, target_word_count):
        issues = []
        
        # 1. Validation issues
        if hasattr(validation_result, 'get'):
             details = validation_result.get('details', {})
             
             # Election Law
             if details.get('electionLaw', {}).get('violations'):
                  violations = ", ".join(details['electionLaw']['violations'])
                  issues.append(f"[CRITICAL] 선거법 위반 표현 발견: {violations}\n   → 선거법을 준수하는 완곡한 표현으로 수정 (예: '~하겠습니다' -> '~추진합니다')")
             
             # Repetition
             if details.get('repetition', {}).get('repeatedSentences'):
                  repeated = ", ".join(details['repetition']['repeatedSentences'][:3])
                  issues.append(f"[HIGH] 문장 반복 감지: {repeated}...\n   → 반복을 피하고 다른 표현으로 수정")

        # 2. Keyword issues
        if hasattr(keyword_result, 'get'):
             if not keyword_result.get('passed', True):
                  kw_issues = keyword_result.get('issues', [])
                  if kw_issues:
                       issues.append(f"[HIGH] 키워드 문제:\n" + "\n".join([f"   - {i}" for i in kw_issues]))

        # Format issues list
        issues_text = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(issues)]) if issues else "(없음 - 전반적인 톤앤매너와 구조만 다듬으세요)"
        
        status_note = ""
        if status in ['준비', '현역']:
             status_note = f"\n⚠️ 작성자 상태: {status} (예비후보 등록 전) - 공약성 표현 엄격 금지"
             
        natural_tone = build_natural_tone_prompt({'severity': 'strict'})
        
        return f"""당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
{issues_text}
{status_note}

[원본 제목]
{title}

[원본 본문]
{content}

[필수 포함 키워드]
{", ".join(user_keywords) if user_keywords else "(없음)"}

[수정 가이드]
1. **5단 구조 유지**: 서론-본론1-본론2-본론3-결론
2. **소제목**: H2 태그 사용, 뉴스 헤드라인처럼 구체적으로
3. **분량**: 목표 {target_word_count}자 내외 유지
4. **말투 ( tone)**:
{natural_tone}

다음 JSON 형식으로만 응답하세요:
{{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정 사항 1", "수정 사항 2"]
}}"""

    def apply_hard_constraints(self, content: str, title: str, user_keywords: List[str], status: str, previous_summary: List[str] = [], error: str = None) -> Dict[str, Any]:
        """
        Node.js applyHardConstraints logic ported.
        Handles:
        1. Election law neutralization (Regex)
        2. Keyword spam reduction
        3. Double transformation prevention
        """
        updated_content = content
        updated_title = title
        summary = previous_summary[:]
        
        if error:
            summary.append(f"LLM 실패로 인한 자동 보정: {error}")

        # 1. 선거법 위반 표현 필터 (기계적 치환)
        # Node.js switched to LLM delegation, but kept regex as fallback/safety. 
        # Since user complained about rules not being followed, strict regex is safer.
        if status in ['준비', '현역']: # Pre-candidate constraints
            original_content = updated_content
            for pattern, replacement in PLEDGE_REPLACEMENTS:
                updated_content = re.sub(pattern, replacement, updated_content)
                updated_title = re.sub(pattern, replacement, updated_title)
            
            if original_content != updated_content:
                summary.append("선거법 위험 표현 기계적 완화 적용")

        # 2. 과다 키워드 강제 분산 (reduceKeywordSpam)
        # Porting strict logic: max 6 times allowed
        MAX_ALLOWED = 6
        PRESERVE_FRONT = 4
        PRESERVE_BACK = 2
        
        for keyword in user_keywords:
            # Count occurrences using simple text search to avoid complex regex issues for now
            # (or use regex to be accurate)
            # Python's re.escape is useful
            escaped_kw = re.escape(keyword)
            # Find all (overlapping not needed usually)
            matches = list(re.finditer(escaped_kw, updated_content))
            count = len(matches)
            
            if count > MAX_ALLOWED:
                excess = count - MAX_ALLOWED
                summary.append(f"키워드 과다('{keyword}' {count}회) -> {excess}회 분산 필요 (자동 보정)")
                
                # Replace logic: Keep first 4, keep last 2, replace middle ones with synonyms
                # Since we don't have a robust synonym generator in Python yet, we just remove/dilute the middle ones
                # or replace with "이 문제", "해당 사안" etc.
                
                indices_to_replace = matches[PRESERVE_FRONT : count - PRESERVE_BACK]
                
                # We need to replace from back to front to not mess up indices
                indices_to_replace.reverse()
                
                for match in indices_to_replace:
                    start, end = match.span()
                    # Check context to choose replacement?
                    # Simple fallback: "관련 현안" or just delete if safe? Replacement is better.
                    replacement = "관련 현안" 
                    updated_content = updated_content[:start] + replacement + updated_content[end:]

        # 3. Double Transformation Check ("것일 것입니다" -> "것입니다")
        updated_content = re.sub(r'것일 것입니다', '것입니다', updated_content)
        updated_content = re.sub(r'것일 것', '것', updated_content)

        return {
            'content': updated_content,
            'title': updated_title,
            'editSummary': summary,
            'fixed': True
        }
