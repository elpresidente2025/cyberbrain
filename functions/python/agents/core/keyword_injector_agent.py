import re
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

from ..base_agent import Agent
from services.posts.validation import count_keyword_coverage, validate_keyword_insertion

class KeywordInjectorAgent(Agent):
    def __init__(self, name: str = 'KeywordInjectorAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self._client = get_client()
        self.model_name = DEFAULT_MODEL

    def get_min_target(self, keyword_count: int) -> int:
        """검증 규칙과 동일한 사용자 키워드 최소 등장 횟수."""
        return 3 if keyword_count >= 2 else 5

    def _extract_keyword_counts(self, keyword_result: Dict[str, Any], keywords: List[str]) -> Dict[str, int]:
        details = (keyword_result.get('details') or {}).get('keywords') or {}
        counts: Dict[str, int] = {}
        for kw in keywords:
            info = details.get(kw) or {}
            counts[kw] = int(info.get('coverage') or info.get('count') or 0)
        return counts

    def _build_keyword_feedback(self, keyword_result: Dict[str, Any], extra_feedback: str = '') -> str:
        details = (keyword_result.get('details') or {}).get('keywords') or {}
        issues: List[str] = []
        for keyword, info in details.items():
            if not isinstance(info, dict):
                continue
            current = int(info.get('coverage') or info.get('count') or 0)
            expected = int(info.get('expected') or 0)
            max_allowed = int(info.get('max') or 9999)
            if current < expected:
                issues.append(f"\"{keyword}\" 부족: {current}/{expected}")
            elif current > max_allowed:
                issues.append(f"\"{keyword}\" 과다: {current}/{max_allowed}")
        if extra_feedback:
            issues.append(extra_feedback)
        return ", ".join(issues) if issues else "키워드 기준에 맞게 조정하세요."

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        previous_results = context.get('previousResults', {})

        # 🔧 키워드 fallback
        user_keywords = (
            context.get('userKeywords') or
            context.get('keywords') or
            context.get('searchKeywords') or
            []
        )
        if isinstance(user_keywords, str):
            user_keywords = [user_keywords] if user_keywords.strip() else []
        auto_keywords = context.get('autoKeywords') or []
        if not isinstance(auto_keywords, list):
            auto_keywords = []
        target_word_count = context.get('targetWordCount')

        structure_result = previous_results.get('StructureAgent', {})
        content = structure_result.get('content') if structure_result else None

        if not content:
            content = context.get('content')
            if not content:
                raise ValueError('Content not found in context or previousResults')

        title = structure_result.get('title') or context.get('title', '')
        source_text = context.get('sourceText', '')
        context_analysis = structure_result.get('contextAnalysis')

        if not user_keywords:
            print('⏭️ [KeywordInjectorAgent] 검색어 없음 - 스킵')
            return {'content': content, 'title': title, 'keywordCounts': {}}

        # Parse Sections
        sections = self.parse_sections(content)
        print(f"📊 [KeywordInjectorAgent] 섹션 {len(sections)}개 파싱 완료")

        # 최소 삽입 목표 계산
        min_target = self.get_min_target(len(user_keywords))
        max_target = min_target + 1
        print(f"📊 [KeywordInjectorAgent] 키워드 목표: {min_target}~{max_target}회")

        section_counts = self.count_keywords_per_section(sections, user_keywords)
        initial_keyword_result = validate_keyword_insertion(
            content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        total_counts = self._extract_keyword_counts(initial_keyword_result, user_keywords)

        print(f"📊 [KeywordInjectorAgent] 초기 상태: sections={len(sections)}, totalCounts={total_counts}")

        # Validation Check (검증 모듈과 동일 기준)
        validation = self.validate_section_balance(
            section_counts,
            user_keywords,
            min_target=min_target,
            max_target=max_target,
            auto_keywords=auto_keywords,
        )
        if initial_keyword_result.get('valid') and validation['passed']:
            print('✅ [KeywordInjectorAgent] 초기 상태부터 키워드 완벽 균형')
            return {'content': content, 'title': title, 'keywordCounts': total_counts}

        # Retry Loop
        max_retries = 2
        attempt = 0
        current_content = content
        feedback = self._build_keyword_feedback(initial_keyword_result, validation.get('feedback', ''))

        while attempt <= max_retries:
            attempt += 1
            print(f"🔄 [KeywordInjectorAgent] 시도 {attempt}/{max_retries + 1}")

            prompt = self.build_prompt({
                'sections': sections,
                'userKeywords': user_keywords,
                'sectionCounts': section_counts,
                'feedback': feedback,
                'contextAnalysis': context_analysis,
                'minTarget': min_target,
                'maxTarget': max_target,
            })

            # Logging prompt length only
            print(f"📝 [KeywordInjectorAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

            try:
                from ..common.gemini_client import generate_content_async
                response_text = await generate_content_async(
                    prompt,
                    model_name=self.model_name,
                    # Temperature Lowered: 0.3 for precision and less hallucination
                    temperature=0.3,
                    max_output_tokens=4000,
                    response_mime_type='application/json'
                )

                instructions = self.parse_instructions(response_text)

                if not instructions:
                    print('⚠️ [KeywordInjectorAgent] 유효한 지시 없음 - 재시도')
                    feedback = '유효한 삽입/삭제 지시가 없었습니다. 다시 시도하세요.'
                    continue

                print(f"📋 [KeywordInjectorAgent] {len(instructions)}개 지시 파싱됨")

                current_content = self.apply_instructions(current_content, sections, instructions)

                # Re-parse and validate
                new_sections = self.parse_sections(current_content)
                new_section_counts = self.count_keywords_per_section(new_sections, user_keywords)
                new_keyword_result = validate_keyword_insertion(
                    current_content,
                    user_keywords,
                    auto_keywords,
                    target_word_count,
                )
                new_total_counts = self._extract_keyword_counts(new_keyword_result, user_keywords)
                validation = self.validate_section_balance(
                    new_section_counts,
                    user_keywords,
                    min_target=min_target,
                    max_target=max_target,
                    auto_keywords=auto_keywords,
                )

                if new_keyword_result.get('valid') and validation['passed']:
                    print(f"✅ [KeywordInjectorAgent] 키워드 균형 달성: {new_total_counts}")
                    return {
                        'content': current_content,
                        'title': title,
                        'keywordCounts': new_total_counts
                    }

                feedback = self._build_keyword_feedback(new_keyword_result, validation.get('feedback', ''))
                print(f"⚠️ [KeywordInjectorAgent] 검증 실패: {feedback}")

                if attempt > max_retries:
                    print('⛔ [KeywordInjectorAgent] 재시도 횟수 초과 - 현재 결과 반환')
                    return {
                        'content': current_content,
                        'title': title,
                        'keywordCounts': new_total_counts
                    }

                # Update loop state (best effort chain)
                content = current_content
                sections = new_sections
                section_counts = new_section_counts

            except Exception as e:
                print(f"❌ [KeywordInjectorAgent] 에러 발생: {str(e)}")
                feedback = str(e)
                if attempt > max_retries:
                    return {'content': current_content, 'title': title, 'keywordCounts': {}}

        return {'content': content, 'title': title, 'keywordCounts': total_counts}

    def parse_sections(self, content: str) -> List[Dict]:
        sections = []
        h2_iter = list(re.finditer(r'<h2[^>]*>[\s\S]*?<\/h2>', content, re.IGNORECASE))
        
        if not h2_iter:
            sections.append({
                'type': 'single',
                'startIndex': 0,
                'endIndex': len(content),
                'content': content
            })
            return sections
            
        first_h2_start = h2_iter[0].start()
        if first_h2_start > 0:
            sections.append({
                'type': 'intro',
                'startIndex': 0,
                'endIndex': first_h2_start,
                'content': content[:first_h2_start]
            })
            
        for i, match in enumerate(h2_iter):
            start_index = match.start()
            end_index = h2_iter[i+1].start() if i < len(h2_iter) - 1 else len(content)
            
            is_last = (i == len(h2_iter) - 1)
            sections.append({
                'type': 'conclusion' if is_last else f'body{i+1}',
                'startIndex': start_index,
                'endIndex': end_index,
                'content': content[start_index:end_index]
            })
            
        return sections

    def count_keywords_per_section(self, sections: List[Dict], keywords: List[str]) -> List[Dict]:
        result = []
        for section in sections:
            counts = {}
            for kw in keywords:
                counts[kw] = count_keyword_coverage(section['content'], kw)
            result.append({'type': section['type'], 'counts': counts})
        return result

    def count_keywords(self, content: str, keywords: List[str]) -> Dict[str, int]:
        counts = {}
        for kw in keywords:
            counts[kw] = count_keyword_coverage(content, kw)
        return counts

    def validate_section_balance(
        self,
        section_counts: List[Dict],
        keywords: List[str],
        min_target: Optional[int] = None,
        max_target: Optional[int] = None,
        auto_keywords: Optional[List[str]] = None,
    ) -> Dict:
        issues = []
        auto_keyword_set = set(auto_keywords or [])

        for kw in keywords:
            total_kw_count = sum(sc['counts'].get(kw, 0) for sc in section_counts)

            if kw in auto_keyword_set:
                if total_kw_count < 1:
                    issues.append(f"전체 \"{kw}\" 0회 (자동 키워드 최소 1회 필요)")
                continue

            if min_target is not None and total_kw_count < min_target:
                deficit = min_target - total_kw_count
                issues.append(f"전체 \"{kw}\" {total_kw_count}회 (최소 {min_target}회 필요, {deficit}회 추가 필요)")

            if max_target is not None and total_kw_count > max_target:
                excess = total_kw_count - max_target
                issues.append(f"전체 \"{kw}\" {total_kw_count}회 (최대 {max_target}회 허용, {excess}회 삭제 필요)")

        if not issues:
            return {'passed': True}

        return {
            'passed': False,
            'reason': f"키워드 삽입 미달: {len(issues)}개 문제",
            'feedback': ", ".join(issues)
        }

    def build_prompt(self, params: Dict[str, Any]) -> str:
        sections = params['sections']
        user_keywords = params['userKeywords']
        section_counts = params['sectionCounts']
        feedback = params.get('feedback', '')
        context_analysis = params.get('contextAnalysis') or {}
        min_target = params.get('minTarget', len(sections))
        max_target = params.get('maxTarget', min_target + 1)

        # Section Status
        section_status_lines = []
        for i, sc in enumerate(section_counts):
            kw_info = ", ".join([f"{kw}: {sc['counts'].get(kw, 0)}회" for kw in user_keywords])
            section_status_lines.append(f"[섹션 {i}] {sc['type']}: {kw_info}")
        section_status = "\n".join(section_status_lines)

        # Per-keyword totals
        kw_totals = {}
        for kw in user_keywords:
            kw_totals[kw] = sum(sc['counts'].get(kw, 0) for sc in section_counts)

        # Problems
        problems = []
        for kw in user_keywords:
            total = kw_totals[kw]
            if total < min_target:
                deficit = min_target - total
                problems.append(f"전체 \"{kw}\": {total}회 → {deficit}회 추가 삽입 필요 (목표 {min_target}회)")
            elif total > max_target:
                excess = total - max_target
                problems.append(f"전체 \"{kw}\": {total}회 → {excess}회 삭제 필요 (최대 {max_target}회)")
        
        tone_instruction = ""
        responsibility_target = context_analysis.get('responsibilityTarget')
        expected_tone = context_analysis.get('expectedTone')
        
        if responsibility_target and expected_tone:
            critical_keywords = [kw for kw in user_keywords if responsibility_target in kw or kw in responsibility_target]
            if critical_keywords:
                tone_instruction = f"""
## ⚠️ 톤 지시 (필수)
이 원고의 논조: "{expected_tone}"
비판/요구 대상: "{responsibility_target}"
→ "{', '.join(critical_keywords)}" 키워드는 **{expected_tone}적 맥락**으로 작성할 것
→ 절대 우호적/존경하는 표현 금지 (예: "존경", "감사", "성과", "노력" 등)"""

        # [CRITICAL UPDATE] Full Context Preview
        # Join all sections to provide full context
        context_preview = ""
        if sections and len(sections) > 0:
            preview_text = " ".join([s['content'] for s in sections])
            # Strip tags for readability but keep structure roughly? 
            # Actually LLM reads HTML fine. Let's keep it simple or strip.
            # Stripping tags is better for token efficiency, assuming textual flow.
            preview_text = re.sub(r'<[^>]*>', '', preview_text)
            preview_text = re.sub(r'\s+', ' ', preview_text).strip()
            
            # Use a much larger limit or no limit (Gemini Flash has huge context)
            # 10,000 chars should cover any normal generated post.
            context_preview = f"""
## 전체 원고 내용 (반드시 읽고 맥락에 맞게 작성할 것)
{preview_text[:12000]}
"""

        prompt = f"""검색어가 전체 {min_target}~{max_target}회 범위에 들어오도록 새 문장을 생성하거나 기존 문장을 수정해야 합니다.
{context_preview}

## 검색어
{chr(10).join([f'- "{kw}" (현재 {kw_totals.get(kw, 0)}회, 목표 {min_target}회 이상)' for kw in user_keywords])}

## 현재 섹션별 현황
{section_status}

## 필요한 조정
{chr(10).join(problems) if problems else '조정 불필요'}
{tone_instruction}

## 규칙
1. ⚠️ **[CRITICAL] 맥락 일치**: 위 '전체 원고 내용'을 읽고, 해당 섹션의 내용과 자연스럽게 이어지는 문장을 작성하십시오. '뜬금없는 문장'을 절대 금지합니다.
2. **전체 합계 우선**: 키워드별 총합을 반드시 {min_target}~{max_target}회로 맞추십시오.
3. **부족 시 배치**: 현재 0회인 섹션 또는 맥락이 맞는 긴 섹션부터 우선 삽입하십시오.
4. **검색어 원문 유지**: "{user_keywords[0] if user_keywords else ''}" 형태 그대로 사용
5. **짧은 한 문장만 생성**: 30자~50자 내외의 **자연스러운 한 문장**만 생성 (문단 전체 생성 금지)
6. **사실 관계 주의**: 원고에 없는 내용을 날조하지 마십시오. (예: 대통령 호칭, 가짜 공약 등 금지)
7. **위치 지정**: 섹션 번호와 동작(insert/delete) 명시

## 출력 형식 (JSON)
{{"instructions":[{{"section":0,"action":"insert","sentence":"맥락에 맞는 자연스러운 문장"}}]}}

⚠️ 조정이 필요 없으면: {{"instructions":[]}}
⚠️ sentence는 50자 이내, 줄바꿈 금지"""

        if feedback:
            prompt += f"\n\n🚨 이전 시도 실패: {feedback}"
        
        return prompt

    def parse_instructions(self, response: str) -> List[Dict]:
        if not response:
            return []
        
        try:
            text = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', response).strip()
            text = re.sub(r'[\r\n]+', ' ', text)
            
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                text = json_match.group(0)
            
            parsed = json.loads(text)
            instructions = parsed.get('instructions', [])
            
            validated = []
            for ins in instructions:
                if ins.get('action') != 'insert' or not ins.get('sentence'):
                    validated.append(ins)
                    continue

                sentence = ins['sentence'].strip()
                if len(sentence) > 300: # Increased limit slightly as we allow slightly longer context
                    print(f"⚠️ [KeywordInjectorAgent] 문장 너무 김 ({len(sentence)}자)")
                    # but maybe allow it if context insists? No, keep it checks.
                    # Strict limit 200 is safer to prevent rambling.
                    if len(sentence) > 200:
                         print("   -> 200자 초과로 거부")
                         continue
                
                # Filter '...' pattern
                if '...' in sentence and sentence.find('...') < len(sentence) - 5:
                     continue
                
                # Filter greeting duplication
                if '존경하는' in sentence and '안녕하십니까' in sentence:
                     print(f"⚠️ [KeywordInjectorAgent] 인사말 복사 감지 - 거부")
                     continue

                validated.append(ins)
            
            return validated
            
        except Exception as e:
            print(f"⚠️ [KeywordInjectorAgent] JSON 파싱 실패: {str(e)}")
            return []

    def apply_instructions(self, content: str, sections: List[Dict], instructions: List[Dict]) -> str:
        if not instructions:
            return content
        
        sorted_ins = sorted(instructions, key=lambda x: x.get('section', -1), reverse=True)
        result = content
        
        for ins in sorted_ins:
            section_idx = ins.get('section')
            if section_idx is None or section_idx < 0 or section_idx >= len(sections):
                continue
            
            section = sections[section_idx]
            
            if ins.get('action') == 'insert' and ins.get('sentence'):
                # Insert at end of section?
                # Best place is typically end of section paragraph.
                insert_pos = section['endIndex']
                # Add newline <p>sentence</p>
                new_paragraph = f"\n<p>{ins['sentence']}</p>"
                result = result[:insert_pos] + new_paragraph + result[insert_pos:]
                print(f"📝 [KeywordInjectorAgent] 섹션 {section_idx}에 삽입: \"{ins['sentence'][:50]}...\"")
            
            elif ins.get('action') == 'delete':
                print(f"🗑️ [KeywordInjectorAgent] 섹션 {section_idx}에서 삭제 시도 (스킵됨)")
        
        return result
