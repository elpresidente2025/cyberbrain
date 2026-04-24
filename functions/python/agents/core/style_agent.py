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

    cleaned = re.sub(r'카테고리\s*:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'검색어\s*(?:삽입|반영)\s*횟수\s*:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'생성\s*시간\s*:[\s\S]*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^\s*\d+\s*자\s*$', '', cleaned, flags=re.MULTILINE)

    return cleaned.strip()

def _count_keyword(text: str, keyword: str) -> int:
    return strip_html(text or '').count(keyword)


def _kw_min_count(n_keywords: int) -> int:
    from ..common.editorial import KEYWORD_SPEC
    if n_keywords == 1:
        return int(KEYWORD_SPEC['singleKeywordMin'])
    return int(KEYWORD_SPEC['perKeywordMin'])


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

        required_keywords = [
            str(k).strip()
            for k in (context.get('keywords') or keyword_counts.keys())
            if str(k).strip()
        ]
        before_counts = {kw: _count_keyword(content, kw) for kw in required_keywords}

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
            final_counts = {kw: _count_keyword(content, kw) for kw in required_keywords} if required_keywords else keyword_counts
            return {
                'content': content,
                'title': title,
                'keywordCounts': final_counts,
                'keywordCountsBeforeStyle': before_counts,
                'keywordLossDetected': False,
                'lostKeywords': [],
                'finalLength': current_length,
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

        # StyleAgent가 Gemini 재작성 시 문단을 병합하는 문제 방어:
        # normalize_section_p_count로 섹션당 3문단 구조를 복원한다.
        if final_content != content:
            from .structure_normalizer import normalize_section_p_count
            before_p = len(re.findall(r'<p\b[^>]*>', final_content, re.IGNORECASE))
            final_content = normalize_section_p_count(final_content)
            after_p = len(re.findall(r'<p\b[^>]*>', final_content, re.IGNORECASE))
            if before_p != after_p:
                print(f"🩹 [StyleAgent] 문단 구조 복원: {before_p}p → {after_p}p")
            final_length = len(strip_html(final_content))

        # ── 키워드 무결성 게이트 ────────────────────────────────────────────
        keyword_loss_detected = False
        repair_keywords: list = []
        warning_keywords: list = []
        after_counts: dict = {}

        if required_keywords:
            kw_min = _kw_min_count(len(required_keywords))
            after_counts = {kw: _count_keyword(final_content, kw) for kw in required_keywords}

            for kw in required_keywords:
                b = before_counts.get(kw, 0)
                a = after_counts.get(kw, 0)
                if a < kw_min and b >= kw_min:
                    repair_keywords.append(kw)
                elif a < b and a >= kw_min:
                    warning_keywords.append(kw)

            if warning_keywords:
                logger.info("[StyleAgent] Keyword count reduced but above min. warning=%s", warning_keywords)

            if repair_keywords:
                keyword_loss_detected = True
                logger.warning(
                    "[StyleAgent] Keyword below min=%s. Attempting repair. repair=%s before=%s after=%s",
                    kw_min, repair_keywords, before_counts, after_counts,
                )
                try:
                    repair_prompt = self.build_repair_prompt(final_content, repair_keywords, after_counts, kw_min)
                    repair_payload = await generate_json_async(
                        repair_prompt,
                        model_name=self.model_name,
                        response_schema=STYLE_RESPONSE_SCHEMA,
                        required_keys=("content",),
                        max_output_tokens=4000,
                        temperature=0.2,
                        retries=1,
                    )
                    repaired = normalize_artifacts(str(repair_payload.get('content') or '').strip())
                    if repaired:
                        repaired_counts = {kw: _count_keyword(repaired, kw) for kw in required_keywords}
                        still_below = [kw for kw in repair_keywords if repaired_counts.get(kw, 0) < kw_min]
                        if not still_below:
                            final_content = repaired
                            after_counts = repaired_counts
                            final_length = len(strip_html(final_content))
                            logger.info("[StyleAgent] Keyword repair succeeded. repaired=%s", repair_keywords)
                        else:
                            logger.warning(
                                "[StyleAgent] Keyword repair failed. Rolling back. still_below=%s",
                                still_below,
                            )
                            final_content = content
                            after_counts = before_counts
                            final_length = current_length
                except Exception as exc:
                    logger.warning("[StyleAgent] Keyword repair error. Rolling back. err=%s", exc)
                    final_content = content
                    after_counts = before_counts
                    final_length = current_length

        recalculated_counts = (
            after_counts
            if required_keywords
            else {kw: _count_keyword(final_content, kw) for kw in keyword_counts.keys()}
        )

        return {
            'content': final_content,
            'title': title,
            'keywordCounts': recalculated_counts,
            'keywordCountsBeforeStyle': before_counts,
            'keywordLossDetected': keyword_loss_detected,
            'lostKeywords': repair_keywords,
            'finalLength': final_length,
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
2. **문단 구조 완전 보존**: 각 섹션(서론·본론·결론)의 <p> 개수를 **정확히** 유지하세요. 현재 섹션당 3개 문단이면 교정 후에도 반드시 3개여야 합니다. 두 문단을 합치거나, 한 문단을 삭제하는 것은 **금지**입니다.
3. **분량 보존**: 내용을 크게 줄이지 마세요.
4. **검색어(키워드) 절대 보존**: 아래 검색어는 SEO를 위해 필수적이므로 **절대 삭제하거나 변형하지 마십시오.**
5. **섹션 첫 문장 지시어 금지**: 각 <h2> 바로 뒤 첫 <p>의 첫 문장을 지시 대명사(이는/이것은/이러한/이와 같은/이를 통해 등 '이·그·저' 계열)로 시작하지 마십시오. 해당 섹션의 핵심 주어·주제어로 독립적으로 시작하십시오.
6. **문단 첫 문장 구체적 주어**: 2·3번째 문단의 첫 문장에서도 '이는/이러한/이것은' 등 지시 대명사 대신 구체적 주어(정책명·제도명·지역명 등)를 사용하십시오. 구체적 주어로 시작하면 문장이 독립적으로 의미를 전달하고 분량 확장에도 도움이 됩니다.
7. **실질 문단 유지**: 한 문장짜리 <p>를 만들지 마십시오. 문장 중간을 끊어 새 <p>로 나누지 말고, 각 문단 안에서 주장·근거·의미를 완성하십시오.
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

    def build_repair_prompt(
        self,
        content: str,
        lost_keywords: list,
        after_counts: dict,
        min_count: int,
    ) -> str:
        keyword_lines = '\n'.join([
            f'- "{kw}": 현재 {after_counts.get(kw, 0)}회 → 최소 {min_count}회 필요'
            for kw in lost_keywords
        ])
        return f"""아래 HTML 본문에서 누락된 필수 검색어만 자연스럽게 복구하세요.

절대 조건:
1. 전체 문단 구조, h2/p 개수 유지
2. 새 주제 추가 금지
3. 문장 1~2개만 최소 수정
4. 아래 검색어는 정확한 표기로 지정 횟수 이상 포함
5. 설명 없이 JSON만 반환

누락 검색어:
{keyword_lines}

본문:
{content}

# Output Contract
Return JSON object only.
{{
  "content": "<h2>...</h2><p>...</p>"
}}
No markdown code fences."""

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
