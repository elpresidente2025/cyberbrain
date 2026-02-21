import re
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

from ..base_agent import Agent
from services.posts.validation import (
    count_keyword_occurrences,
    enforce_keyword_requirements,
    validate_keyword_insertion,
)
from services.posts.keyword_insertion_policy import build_keyword_injection_policy_lines

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
            counts[kw] = int(info.get('count') or info.get('coverage') or 0)
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

    def _finalize_keyword_result(
        self,
        *,
        content: str,
        title: str,
        user_keywords: List[str],
        auto_keywords: List[str],
        target_word_count: Any,
        mode: str,
        note: str = "",
    ) -> Dict[str, Any]:
        final_keyword_result = validate_keyword_insertion(
            content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        final_counts = self._extract_keyword_counts(final_keyword_result, user_keywords)
        passed = bool(final_keyword_result.get('valid'))
        if passed:
            print(f"[KeywordInjectorAgent] 키워드 기준 충족({mode}): {final_counts}")
        else:
            print(f"[KeywordInjectorAgent][WARN] 키워드 기준 미충족({mode}) - 베스트 에포트 진행: {final_counts}")

        return {
            'content': content,
            'title': title,
            'keywordCounts': final_counts,
            'keywordValidation': final_keyword_result,
            'keywordInjector': {
                'passed': passed,
                'mode': mode,
                'note': note,
            },
        }

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        previous_results = context.get('previousResults', {})

        # 키워드 fallback
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
            print('[KeywordInjectorAgent] 검색어 없음 - 스킵')
            return {'content': content, 'title': title, 'keywordCounts': {}}

        # Parse Sections
        sections = self.parse_sections(content)
        print(f"[KeywordInjectorAgent] 섹션 {len(sections)}개 파싱 완료")

        # 최소 삽입 목표 계산
        min_target = self.get_min_target(len(user_keywords))
        max_target = min_target + 1
        print(f"[KeywordInjectorAgent] 키워드 목표: {min_target}~{max_target}회")

        section_counts = self.count_keywords_per_section(sections, user_keywords)
        initial_keyword_result = validate_keyword_insertion(
            content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        total_counts = self._extract_keyword_counts(initial_keyword_result, user_keywords)

        print(f"[KeywordInjectorAgent] 초기 상태: sections={len(sections)}, totalCounts={total_counts}")

        # Validation Check (검증 모듈과 동일 기준)
        validation = self.validate_section_balance(
            section_counts,
            user_keywords,
            min_target=min_target,
            max_target=max_target,
            auto_keywords=auto_keywords,
        )
        if initial_keyword_result.get('valid') and validation['passed']:
            print('[KeywordInjectorAgent] 초기 상태부터 키워드 균형 달성')
            return self._finalize_keyword_result(
                content=content,
                title=title,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                target_word_count=target_word_count,
                mode='initial-pass',
            )

        # Retry Loop
        max_retries = 2
        attempt = 0
        current_content = content
        feedback = self._build_keyword_feedback(initial_keyword_result, validation.get('feedback', ''))

        last_error = ""
        while attempt <= max_retries:
            attempt += 1
            print(f"[KeywordInjectorAgent] 시도 {attempt}/{max_retries + 1}")

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
            print(f"[KeywordInjectorAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

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

                instructions = self.parse_instructions(response_text, sections=sections)

                if not instructions:
                    print("[KeywordInjectorAgent] 유효한 지시가 없어 재시도합니다")
                    feedback = '유효한 삽입/삭제 지시가 없었습니다. 다시 시도하세요.'
                    continue

                print(f"[KeywordInjectorAgent] 지시 {len(instructions)}개 파싱")

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
                    print(f"[KeywordInjectorAgent] 키워드 균형 달성: {new_total_counts}")
                    return self._finalize_keyword_result(
                        content=current_content,
                        title=title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        mode='llm-retry',
                    )

                feedback = self._build_keyword_feedback(new_keyword_result, validation.get('feedback', ''))
                print(f"[KeywordInjectorAgent][WARN] 검증 실패: {feedback}")

                if attempt > max_retries:
                    last_error = feedback
                    break

                # Update loop state (best effort chain)
                content = current_content
                sections = new_sections
                section_counts = new_section_counts

            except Exception as e:
                print(f"[KeywordInjectorAgent][ERROR] 에러 발생: {str(e)}")
                feedback = str(e)
                if attempt > max_retries:
                    last_error = feedback
                    break

        # 하드 실패 대신 마지막 자동 보정(enforce_keyword_requirements) 1회 실행 후 베스트에포트 반환.
        enforcement = enforce_keyword_requirements(
            current_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            max_iterations=3,
        )
        repaired_content = str(enforcement.get('content') or current_content)
        repaired_result = validate_keyword_insertion(
            repaired_content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        if repaired_result.get('valid'):
            return self._finalize_keyword_result(
                content=repaired_content,
                title=title,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                target_word_count=target_word_count,
                mode='deterministic-repair',
                note='LLM retry 미충족 후 enforce_keyword_requirements로 보정',
            )

        note_parts = []
        if last_error:
            note_parts.append(f"lastError={last_error}")
        if feedback:
            note_parts.append(f"feedback={feedback}")
        note = " | ".join(note_parts) if note_parts else "키워드 기준 미충족 상태로 베스트에포트 반환"
        return self._finalize_keyword_result(
            content=repaired_content,
            title=title,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            mode='best-effort',
            note=note,
        )

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
                counts[kw] = count_keyword_occurrences(section['content'], kw)
            result.append({'type': section['type'], 'counts': counts})
        return result

    def count_keywords(self, content: str, keywords: List[str]) -> Dict[str, int]:
        counts = {}
        for kw in keywords:
            counts[kw] = count_keyword_occurrences(content, kw)
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

        user_keywords: List[str] = []
        for kw in keywords:
            if kw in auto_keyword_set or kw in user_keywords:
                continue
            user_keywords.append(kw)

        if user_keywords:
            for i, section in enumerate(section_counts, start=1):
                section_user_total = sum(section['counts'].get(kw, 0) for kw in user_keywords)
                if section_user_total == 0:
                    issues.append(f"섹션 {i}에 검색어 없음")

        if len(user_keywords) >= 2:
            user_total = sum(
                sum(sc['counts'].get(kw, 0) for sc in section_counts)
                for kw in user_keywords
            )
            if user_total < 7:
                issues.append(f"검색어 총합 {user_total}회 (최소 7회 필요)")

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

        section_status_lines = []
        for i, sc in enumerate(section_counts):
            kw_info = ", ".join([f"{kw}: {sc['counts'].get(kw, 0)}회" for kw in user_keywords])
            section_status_lines.append(f"[섹션 {i}] {sc['type']}: {kw_info}")
        section_status = "\n".join(section_status_lines)

        kw_totals: Dict[str, int] = {}
        for kw in user_keywords:
            kw_totals[kw] = sum(sc['counts'].get(kw, 0) for sc in section_counts)

        problems = []
        for kw in user_keywords:
            total = kw_totals[kw]
            if total < min_target:
                deficit = min_target - total
                problems.append(f"전체 \"{kw}\": {total}회 -> {deficit}회 추가 필요 (목표 {min_target}회)")
            elif total > max_target:
                excess = total - max_target
                problems.append(f"전체 \"{kw}\": {total}회 -> {excess}회 삭제 필요 (최대 {max_target}회)")

        tone_instruction = ""
        responsibility_target = context_analysis.get('responsibilityTarget')
        expected_tone = context_analysis.get('expectedTone')
        if responsibility_target and expected_tone:
            tone_instruction = (
                "\n## 톤 지시\n"
                f"- 글 톤: \"{expected_tone}\"\n"
                f"- 비판/문제 제기 대상: \"{responsibility_target}\"\n"
                "- 감정적 과장 없이, 사실 중심의 표현을 사용하세요.\n"
            )

        context_preview = ""
        if sections:
            preview_lines = []
            for idx, sec in enumerate(sections):
                plain = re.sub(r'<[^>]*>', ' ', sec.get('content', ''))
                plain = re.sub(r'\s+', ' ', plain).strip()
                preview_lines.append(f"[섹션 {idx}] {plain[:900]}")
            context_preview = "\n".join(preview_lines)
        policy_lines = build_keyword_injection_policy_lines()
        policy_text = "\n".join([f"{idx + 1}. {line}" for idx, line in enumerate(policy_lines)])


        if len(user_keywords) >= 2:
            additional_rule = f"- 각 검색어 {min_target}~{max_target}회, 전체 검색어 총합 최소 7회\n"
        else:
            additional_rule = ""

        prompt = f"""검색어가 전체 {min_target}~{max_target}회 범위에 들어오도록 기존 원고를 최소 수정하세요.

## 검색어
{chr(10).join([f'- "{kw}" (현재 {kw_totals.get(kw, 0)}회)' for kw in user_keywords])}

## 섹션별 현황
{section_status}

## 필요한 조정
{chr(10).join(problems) if problems else '조정 불필요'}
{tone_instruction}

## 전체 문맥(요약)
{context_preview}

## 편집 원칙
{policy_text}

## 삽입 추가 규칙
{additional_rule}- 한 섹션(문단 묶음)에서는 insert 액션을 최대 1개만 사용하세요.
- 결말 섹션(conclusion)에는 insert 액션을 사용하지 말고 replace/delete만 사용하세요.
- "특히", "한편", "아울러", "또한"으로 시작하는 보강 문장을 연속 추가하지 마세요.
- 키워드 충족을 위해 동일 기능 문장을 반복 생성하지 마세요.

## Action 스키마
- replace: {{"section": 0, "action": "replace", "target": "원문 일부", "replacement": "치환 문구"}}
- insert: {{"section": 0, "action": "insert", "anchor": "기준 구절", "sentence": "삽입 문장"}}
- delete: {{"section": 0, "action": "delete", "target": "삭제 구절"}}

## 출력 형식 (JSON only)
{{"instructions":[{{"section":0,"action":"replace","target":"원문 일부","replacement":"치환 문구"}}]}}

수정이 필요 없으면 {{"instructions":[]}}"""

        if feedback:
            prompt += f"\n\n이전 시도 실패 피드백: {feedback}"

        return prompt

    def _is_low_context_insert_sentence(self, sentence: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(sentence or "")).strip()
        if not normalized:
            return True
        low_context_prefixes = ("특히", "한편", "아울러", "또한")
        return any(normalized.startswith(prefix) for prefix in low_context_prefixes)

    def parse_instructions(self, response: str, sections: Optional[List[Dict]] = None) -> List[Dict]:
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
            if not isinstance(instructions, list):
                return []

            validated = []
            per_section_insert_count: Dict[int, int] = {}
            for ins in instructions:
                if not isinstance(ins, dict):
                    continue

                section = ins.get('section')
                if not isinstance(section, int):
                    continue
                section_type = ""
                if isinstance(sections, list) and 0 <= section < len(sections):
                    section_type = str((sections[section] or {}).get('type') or '')

                action = str(ins.get('action') or '').strip().lower()

                if action == 'replace':
                    target = str(ins.get('target') or '').strip()
                    replacement = str(ins.get('replacement') or '').strip()
                    if not target or not replacement or target == replacement:
                        continue
                    validated.append({
                        'section': section,
                        'action': 'replace',
                        'target': target,
                        'replacement': replacement,
                    })
                    continue

                if action == 'delete':
                    target = str(ins.get('target') or '').strip()
                    if not target:
                        continue
                    validated.append({
                        'section': section,
                        'action': 'delete',
                        'target': target,
                    })
                    continue

                if action == 'insert':
                    anchor = str(ins.get('anchor') or '').strip()
                    sentence = str(ins.get('sentence') or '').strip()
                    if not anchor or not sentence:
                        continue
                    if len(sentence) > 220:
                        continue
                    if section_type == 'conclusion':
                        continue
                    if self._is_low_context_insert_sentence(sentence):
                        continue
                    if per_section_insert_count.get(section, 0) >= 1:
                        continue
                    validated.append({
                        'section': section,
                        'action': 'insert',
                        'anchor': anchor,
                        'sentence': sentence,
                    })
                    per_section_insert_count[section] = per_section_insert_count.get(section, 0) + 1

            return validated

        except Exception as e:
            print(f"[KeywordInjectorAgent] JSON 파싱 실패: {str(e)}")
            return []

    def _replace_first_occurrence(self, text: str, target: str, replacement: str) -> tuple[str, bool]:
        if target in text:
            return text.replace(target, replacement, 1), True

        target_tokens = [re.escape(token) for token in re.split(r'\s+', target.strip()) if token]
        if not target_tokens:
            return text, False

        pattern = re.compile(r'\s+'.join(target_tokens))
        if not pattern.search(text):
            return text, False

        return pattern.sub(replacement, text, count=1), True

    def _delete_first_occurrence(self, text: str, target: str) -> tuple[str, bool]:
        replaced, changed = self._replace_first_occurrence(text, target, '')
        if not changed:
            return text, False
        replaced = re.sub(r'\s{2,}', ' ', replaced)
        return replaced, True

    def _insert_after_anchor(self, text: str, anchor: str, sentence: str) -> tuple[str, bool]:
        idx = text.find(anchor)
        if idx >= 0:
            insert_at = idx + len(anchor)
            separator = '' if (insert_at > 0 and text[insert_at - 1].isspace()) else ' '
            return text[:insert_at] + separator + sentence + text[insert_at:], True

        anchor_tokens = [re.escape(token) for token in re.split(r'\s+', anchor.strip()) if token]
        if not anchor_tokens:
            return text, False

        pattern = re.compile(r'\s+'.join(anchor_tokens))
        match = pattern.search(text)
        if not match:
            return text, False

        insert_at = match.end()
        separator = '' if (insert_at > 0 and text[insert_at - 1].isspace()) else ' '
        return text[:insert_at] + separator + sentence + text[insert_at:], True

    def _is_meta_leak_sentence(self, sentence: str) -> bool:
        normalized = re.sub(r'\s+', ' ', str(sentence or '')).strip()
        if not normalized:
            return False
        leak_patterns = [
            r'다음은',
            r'검수',
            r'수정 지시',
            r'문제점',
            r'개선',
            r'주의사항',
            r'규칙 설명',
        ]
        return any(re.search(pattern, normalized) for pattern in leak_patterns)

    def _strip_meta_leak_sentences(self, content: str) -> str:
        if not content:
            return content

        def replace_paragraph(match: re.Match) -> str:
            inner = str(match.group(1) or '')
            fragments = re.findall(r'[^.!?。]+[.!?。]?', inner)
            if not fragments:
                return match.group(0)

            kept: List[str] = []
            for fragment in fragments:
                sentence = re.sub(r'\s+', ' ', fragment).strip()
                if not sentence:
                    continue
                if self._is_meta_leak_sentence(sentence):
                    continue
                kept.append(sentence)

            if not kept:
                return ''
            return f"<p>{' '.join(kept).strip()}</p>"

        cleaned = re.sub(
            r'<p\b[^>]*>([\s\S]*?)</p\s*>',
            replace_paragraph,
            content,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def apply_instructions(self, content: str, sections: List[Dict], instructions: List[Dict]) -> str:
        if not instructions:
            return content

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for ins in instructions:
            section_idx = ins.get('section')
            if section_idx is None or not isinstance(section_idx, int):
                continue
            grouped.setdefault(section_idx, []).append(ins)

        result = content

        for section_idx in sorted(grouped.keys(), reverse=True):
            if section_idx < 0 or section_idx >= len(sections):
                continue

            section = sections[section_idx]
            start_idx = int(section.get('startIndex') or 0)
            end_idx = int(section.get('endIndex') or 0)
            if end_idx < start_idx:
                continue

            section_html = result[start_idx:end_idx]
            section_type = str(section.get('type') or '')
            insert_applied = 0

            for ins in grouped.get(section_idx, []):
                action = str(ins.get('action') or '').strip().lower()

                if action == 'replace':
                    target = str(ins.get('target') or '').strip()
                    replacement = str(ins.get('replacement') or '').strip()
                    if not target or not replacement:
                        continue
                    section_html, changed = self._replace_first_occurrence(section_html, target, replacement)
                    if changed:
                        print(f"[KeywordInjectorAgent] 섹션 {section_idx} 치환 적용")
                    continue

                if action == 'delete':
                    target = str(ins.get('target') or '').strip()
                    if not target:
                        continue
                    section_html, changed = self._delete_first_occurrence(section_html, target)
                    if changed:
                        print(f"[KeywordInjectorAgent] 섹션 {section_idx} 삭제 적용")
                    continue

                if action == 'insert':
                    anchor = str(ins.get('anchor') or '').strip()
                    sentence = str(ins.get('sentence') or '').strip()
                    if not anchor or not sentence:
                        continue
                    if section_type == 'conclusion':
                        continue
                    if insert_applied >= 1:
                        continue
                    if self._is_low_context_insert_sentence(sentence):
                        continue
                    section_html, changed = self._insert_after_anchor(section_html, anchor, sentence)
                    if changed:
                        print(f"[KeywordInjectorAgent] 섹션 {section_idx} anchor 삽입 적용")
                        insert_applied += 1
                    continue

            result = result[:start_idx] + section_html + result[end_idx:]

        return result
