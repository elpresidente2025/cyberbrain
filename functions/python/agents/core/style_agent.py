import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

STYLE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "html_content": {"type": "string"},
    },
    "required": ["content"],
}

def strip_html(text: str) -> str:
    if not text:
        return ''
    return re.sub(r'<[^>]*>', '', str(text)).replace('&nbsp;', ' ').strip()

def normalize_artifacts(text: str) -> str:
    if not text:
        return text
    cleaned = str(text).strip()
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned).strip()
    cleaned = re.sub(r'^\s*\\"', '', cleaned)
    cleaned = re.sub(r'\\"?\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*[""]', '', cleaned)
    cleaned = re.sub(r'[""]\s*$', '', cleaned)

    cleaned = re.sub(r'카테고리:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'검색어 삽입 횟수:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'생성 시간:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^\s*\d+\s*자\s*$', '', cleaned, flags=re.MULTILINE)

    return cleaned.strip()

from ..base_agent import Agent

class StyleAgent(Agent):
    def __init__(self, name: str = 'StyleAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self._client = get_client()
        self.model_name = DEFAULT_MODEL

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        previous_results = context.get('previousResults', {})
        user_profile = context.get('userProfile', {})
        target_word_count = context.get('targetWordCount', 2000)

        keyword_result = previous_results.get('KeywordInjectorAgent', {})
        if not keyword_result or not keyword_result.get('content'):
            # Try to recover from WriterAgent if available, but StyleAgent expects injected content
             if previous_results.get('WriterAgent'):
                 keyword_result = previous_results['WriterAgent'].get('data', {})
             else:
                logger.error("KeywordInjectorAgent result missing for StyleAgent")
                # Return context content if exists?
                if context.get('content'):
                    keyword_result = {'content': context['content'], 'title': context.get('title', ''), 'keywordCounts': {}}
                else:
                    return {'success': False, 'error': 'No content to style'}

        content = keyword_result.get('content')
        title = keyword_result.get('title')
        keyword_counts = keyword_result.get('keywordCounts', {})

        current_length = len(strip_html(content))
        min_length = max(1200, int(target_word_count * 0.85))
        target_min = target_word_count
        max_length = int(target_word_count * 1.1)

        logger.info(f"📊 [StyleAgent] Current len: {current_length} (Target: {min_length}~{max_length})")

        needs_expansion = current_length < target_min
        needs_trimming = current_length > max_length
        needs_style_fix = self.check_style_issues(content)

        if not needs_expansion and not needs_trimming and not needs_style_fix:
            logger.info("✅ [StyleAgent] Style/Length Check OK - Skipping")
            return {
                'content': content,
                'title': title,
                'keywordCounts': keyword_counts,
                'finalLength': current_length
            }

        max_attempts = 2
        attempt = 0
        working_content = content
        final_content = content
        final_length = current_length

        from ..common.gemini_client import StructuredOutputError, generate_json_async

        while attempt < max_attempts:
            attempt += 1
            working_length = len(strip_html(working_content))

            prompt = self.build_prompt({
                'content': working_content,
                'currentLength': working_length,
                'minLength': target_min,
                'maxLength': max_length,
                'needsExpansion': working_length < target_min,
                'needsTrimming': working_length > max_length,
                'userProfile': user_profile,
                'keywordCounts': keyword_counts
            })
            prompt += (
                "\n\n# Output Contract\n"
                "Return JSON object only.\n"
                "{\n"
                '  "content": "<h2>...</h2><p>...</p>"\n'
                "}\n"
                "No markdown code fences."
            )

            logger.info(f"📝 [StyleAgent] Prompt generated ({len(prompt)} chars, Attempt {attempt})")

            try:
                response_payload = await generate_json_async(
                    prompt,
                    model_name=self.model_name,
                    response_schema=STYLE_RESPONSE_SCHEMA,
                    required_keys=("content",),
                    max_output_tokens=4000,
                    temperature=0.3,
                    retries=2,
                )

                styled = str(response_payload.get('content') or '').strip()
                if not styled:
                    raise StructuredOutputError("content is empty")
                styled_length = len(strip_html(styled))
                
                if styled_length < working_length * 0.7:
                     logger.warning(f"⚠️ [StyleAgent] Model collapse detected ({working_length} -> {styled_length}). Rolling back.")
                     final_content = working_content
                     final_length = working_length
                     break
                
                final_content = normalize_artifacts(styled)
                final_length = styled_length
                print(f"✅ [StyleAgent] Style correction done ({working_length} -> {final_length})")
                
                still_short = final_length < min_length
                still_long = final_length > max_length
                
                if not still_short and not still_long:
                    break
                    
                working_content = final_content
            
            except StructuredOutputError as e:
                logger.error(f"❌ [StyleAgent] Structured output validation failed: {e}")
                break
            except Exception as e:
                logger.error(f"❌ [StyleAgent] Error: {e}")
                break

        if final_length < min_length:
            logger.warning(f"⚠️ [StyleAgent] Final length insufficient ({final_length}/{min_length})")
            
        return {
            'content': final_content,
            'title': title,
            'keywordCounts': keyword_counts,
            'finalLength': final_length
        }

    def build_prompt(self, params: Dict[str, Any]) -> str:
        content = params['content']
        current_length = params['currentLength']
        min_length = params['minLength']
        max_length = params['maxLength']
        needs_expansion = params['needsExpansion']
        needs_trimming = params['needsTrimming']
        user_profile = params['userProfile'] or {}
        keyword_counts = params['keywordCounts'] or {}
        
        author_name = user_profile.get('name') or user_profile.get('displayName') or '화자'
        
        keywords_to_preserve = '\n'.join([f'- "{k}"' for k in keyword_counts.keys()])
        
        length_instruction = ''
        if needs_expansion:
            deficit = min_length - current_length
            length_instruction = f"""
## 분량 확장 필요
현재 {current_length}자 → 최소 {min_length}자 필요 ({deficit}자 추가)
- 기존 논점을 **더 깊이 설명**하세요 (예시, 근거 추가)
- **새로운 주제를 추가하지 마세요**
- 기존 문장을 풍부하게 확장하세요"""
        elif needs_trimming:
            excess = current_length - max_length
            length_instruction = f"""
## 분량 축소 필요
현재 {current_length}자 → 최대 {max_length}자 이하 ({excess}자 삭제)
- 중복/반복 표현 제거
- 불필요한 수식어 삭제
- 핵심 논점은 유지"""

        return f"""당신은 정치인 블로그 글의 최종 교정 전문가입니다.
아래 본문의 말투를 교정하고 분량을 조절해주세요.

⚠️ **[절대 원칙]**
1. **내용 요약 금지**: 전체 내용을 그대로 유지하며 서술만 다듬으세요.
2. **문단 삭제 금지**: 기존의 문단 구조(15개 내외)를 유지하세요.
3. **분량 보존**: 내용을 크게 줄이지 마세요.
4. **검색어(키워드) 절대 보존**: 아래 검색어는 SEO를 위해 필수적이므로 **절대 삭제하거나 변형하지 마십시오.**
{keywords_to_preserve}

## 작성자: {author_name}

## 현재 본문
{content}

{length_instruction}

## 말투 교정 규칙

    1. ** 확신에 찬 어조 ** 사용:
    - ❌ "~라고 생각합니다" → ✅ "~입니다"
      - ❌ "~할 것입니다" → ✅ "~하겠습니다"
        - ❌ "노력하겠습니다" → ✅ "반드시 해내겠습니다"

    2. ** 3자 관찰 표현 금지 **:
    - ❌ "~라는 점입니다", "~상황입니다", "~것으로 보입니다"
      - ✅ 당사자로서 직접 말하는 어조

    3. ** 기계적 반복 금지 **:
    - 같은 문장 구조가 연속되면 변형
      - 단, 수사학적 반복(대구법, 점층법)은 OK

    4. ** HTML 구조 유지 **: <h2>, <p> 태그 보존

      ## 문법/표현 교정 규칙 (필수)

      1. **행정구역명+여러분 오류**:
      - ❌ "부산광역시 여러분" → ✅ "부산 시민 여러분"
      - ❌ "서울특별시 여러분" → ✅ "서울 시민 여러분"
      - 지역명 뒤에 "시민", "도민", "구민" 등을 반드시 붙여야 함

      2. **지역 중복 오류**:
      - ❌ "부울경 부산광역시" → ✅ "부울경" 또는 "부산광역시" (둘 중 하나만)
      - "부울경"은 이미 부산+울산+경남을 포함하므로 중복 금지

      3. **구어체 → 문어체 변환**:
      - ❌ "역부족인 거예요" → ✅ "역부족입니다"
      - ❌ "~인 거죠" → ✅ "~입니다"
      - ❌ "~거에요" → ✅ "~것입니다"

      4. **인용문 정리**:
      - 인용 시 따옴표 앞뒤 불필요한 공백 제거
      - ❌ '" 역부족인 거예요. "' → ✅ '"역부족입니다"'

      ## 출력 형식
      교정된 전체 본문만 출력하세요. 설명 없이 HTML 본문만 출력하세요."""

    def check_style_issues(self, content: str) -> bool:
        issues = [
            r'라고 생각합니다',
            r'것으로 보입니다',
            r'라는 점입니다',
            r'상황입니다',
            r'노력하겠습니다',
            r'노력할 것입니다',
            r'부산광역시\s*여러분',
            r'서울특별시\s*여러분',
            r'대구광역시\s*여러분',
            r'인천광역시\s*여러분',
            r'광주광역시\s*여러분',
            r'대전광역시\s*여러분',
            r'울산광역시\s*여러분',
            r'부울경\s*부산',
            r'역부족인\s*거',
            r'거예요',
            r'거에요',
            r'인\s*거죠',
            r'"\s+',
            r'\s+"'
        ]
        
        for pattern in issues:
            if re.search(pattern, content):
                return True
        
        # 동사/구문 반복 탐지 (3회 이상이면 재교정 트리거)
        verb_patterns = ['던지면서', '던지며', '이끌어내며', '이끌어가며']
        for verb in verb_patterns:
            if content.count(verb) >= 3:
                return True
        
        return False
