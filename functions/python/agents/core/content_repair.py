import re
from typing import Dict, Any, Optional, Tuple, List
from .structure_utils import (
    strip_html,
    normalize_artifacts,
    normalize_html_structure_tags,
    normalize_context_text,
    _xml_text,
    _xml_cdata,
    parse_response
)
from ..common.editorial import STRUCTURE_SPEC
from ..common.h2_guide import H2_OPTIMAL_MIN, H2_MAX_LENGTH

class ContentRepairAgent:
    def __init__(self, model_name: str):
        self.model_name = model_name

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    async def recover_length_shortfall(
        self,
        *,
        content: str,
        title: str,
        topic: str,
        length_spec: Dict[str, int],
        author_bio: str = '',
    ) -> Optional[Tuple[str, str]]:
        current_len = len(strip_html(content))
        min_len = int(length_spec.get('min_chars', 0))
        max_len = int(length_spec.get('max_chars', 0))
        expected_h2 = int(length_spec.get('expected_h2', 0))

        if min_len <= 0:
            return None

        from ..common.gemini_client import generate_content_async

        best_content = content
        best_title = title
        best_len = current_len
        max_recovery_attempts = 2

        for recovery_attempt in range(1, max_recovery_attempts + 1):
            gap = max(0, min_len - best_len)
            # 부분 보강 우선: 극단적 축약일 때만 마지막 수단으로 전면 재작성
            rewrite_mode = (
                recovery_attempt == max_recovery_attempts
                and best_len < int(min_len * 0.4)
            )

            if rewrite_mode:
                prompt = f"""
<length_recovery_prompt version="xml-v1" mode="full_rewrite">
  <role>당신은 엄격한 한국어 정치 에디터입니다. 기존 초안이 과도하게 짧아 예외적으로 전면 재작성합니다.</role>
  <goal>
    <current_chars>{best_len}</current_chars>
    <min_chars>{min_len}</min_chars>
    <max_chars>{max_len}</max_chars>
    <expected_h2>{expected_h2}</expected_h2>
  </goal>
  <rules>
    <rule order="1">최종 결과는 완성형 본문이어야 하며, 개요/요약/예시 금지.</rule>
    <rule order="2">태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="3">도입 1 + 본론/결론 구조를 유지하고 분량을 충족.</rule>
    <rule order="4">출력에는 title/content XML 외 설명문 금지.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(best_title)}</draft_title>
    <draft_content>{_xml_cdata(best_content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\\n<content>...</content>')}</example>
  </output_contract>
</length_recovery_prompt>
""".strip()
            else:
                prompt = f"""
<length_recovery_prompt version="xml-v1" mode="expand_only">
  <role>당신은 엄격한 한국어 정치 에디터입니다. 기존 흐름을 유지하며 분량만 보강합니다.</role>
  <goal>
    <current_chars>{best_len}</current_chars>
    <min_chars>{min_len}</min_chars>
    <max_chars>{max_len}</max_chars>
    <required_additional_chars>{gap}</required_additional_chars>
    <expected_h2>{expected_h2}</expected_h2>
  </goal>
  <rules>
    <rule order="1">기존 &lt;h2&gt; 제목 삭제/변경 금지.</rule>
    <rule order="2">&lt;h2&gt; 개수는 정확히 {expected_h2}개 유지.</rule>
    <rule order="3">문단은 &lt;p&gt;...&lt;/p&gt;만 사용하고 태그를 정확히 닫을 것.</rule>
    <rule order="4">기존 사실/주장을 삭제하거나 왜곡하지 말 것.</rule>
    <rule order="5">중복/반복 금지. 각 단락은 새로운 근거/설명으로 보강.</rule>
    <rule order="6">원문 표현과 전개를 최대한 유지하고, 수정 범위는 전체의 30% 이내로 제한.</rule>
    <rule order="7">최종 분량은 {min_len}~{max_len}자 범위를 반드시 충족.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(best_title)}</draft_title>
    <draft_content>{_xml_cdata(best_content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\\n<content>...</content>')}</example>
  </output_contract>
</length_recovery_prompt>
""".strip()

            try:
                response_text = await generate_content_async(
                    prompt,
                    model_name=self.model_name,
                    temperature=0.0,
                    max_output_tokens=4096,
                    retries=1,
                )
                parsed = parse_response(response_text)
                recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
                recovered_title = normalize_artifacts(parsed.get('title', '')) or best_title
                if not recovered_content:
                    continue

                recovered_len = len(strip_html(recovered_content))
                print(
                    f"🔧 [ContentRepairAgent] 분량 보강 시도 {recovery_attempt}/{max_recovery_attempts}: "
                    f"{best_len}자 -> {recovered_len}자"
                )
                if recovered_len > best_len:
                    best_content = recovered_content
                    best_title = recovered_title
                    best_len = recovered_len

                if recovered_len >= min_len:
                    return recovered_content, recovered_title
            except Exception as e:
                print(f"⚠️ [ContentRepairAgent] 분량 보강 복구 실패: {str(e)}")

        if best_len > current_len:
            print(
                f"⚠️ [ContentRepairAgent] 분량 기준 미달이지만 보강 개선: "
                f"{current_len}자 -> {best_len}자"
            )
            return best_content, best_title
        return None

    async def recover_structural_shortfall(
        self,
        *,
        content: str,
        title: str,
        topic: str,
        length_spec: Dict[str, int],
        author_bio: str = '',
        failed_code: str,
        failed_reason: str,
        failed_feedback: str,
        failed_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, str]]:
        from ..common.gemini_client import generate_content_async

        current_len = len(strip_html(content))
        min_len = int(length_spec.get('min_chars', 0))
        max_len = int(length_spec.get('max_chars', 0))
        expected_h2 = int(length_spec.get('expected_h2', 0))
        total_sections = int(length_spec.get('total_sections', 5))
        per_section_min = int(length_spec.get('per_section_min', 0))
        per_section_max = int(length_spec.get('per_section_max', 0))
        from ..common.aeo_config import paragraph_contract_from_length_spec
        contract = paragraph_contract_from_length_spec(length_spec)
        section_paragraph_min = int(contract['section_paragraph_min'])
        section_paragraph_max = int(contract['section_paragraph_max'])
        paragraphs_per_section = int(contract['paragraphs_per_section'])
        min_p = total_sections * section_paragraph_min
        max_p = total_sections * section_paragraph_max

        failed_meta = failed_meta if isinstance(failed_meta, dict) else {}
        section_index = self._to_int(failed_meta.get('sectionIndex'), 0)
        section_min = self._to_int(failed_meta.get('sectionMin'), per_section_min)
        section_max = self._to_int(failed_meta.get('sectionMax'), per_section_max)
        section_lengths = failed_meta.get('sectionLengths')
        if isinstance(section_lengths, list):
            safe_lengths = [self._to_int(item, -1) for item in section_lengths]
            section_lengths_text = ",".join(str(item) for item in safe_lengths if item >= 0)
        else:
            section_lengths_text = ""

        code_specific_rule = "실패 코드에 해당하는 항목만 우선 수정하고, 나머지 단락은 그대로 유지하십시오."
        if failed_code == 'SECTION_LENGTH' and section_index > 0:
            code_specific_rule = (
                f"{section_index}번 섹션의 길이를 {section_min}~{section_max}자로만 조정하십시오. "
                "다른 섹션은 최소 수정 원칙을 유지하십시오."
            )
        elif failed_code == 'SECTION_P_COUNT' and section_index > 0:
            code_specific_rule = (
                f"{section_index}번 섹션의 <p> 개수만 기준에 맞게 조정하십시오. "
                f"각 섹션은 최소 {section_paragraph_min}개, 최대 {section_paragraph_max}개의 <p>를 유지해야 합니다."
            )
        elif failed_code == 'INTRO_STANCE_MISSING':
            code_specific_rule = (
                "서론 첫 1~2문단에 입장문 핵심 주장/문제의식을 1~2문장으로 보강하십시오. "
                "기존 본론·결론은 유지하십시오."
            )
        elif failed_code == 'INTRO_CONCLUSION_ECHO':
            code_specific_rule = (
                "결론의 중복 문구만 변형하고, 나머지 구조와 핵심 근거는 유지하십시오."
            )
        elif failed_code == 'SECTION_ROLE_CONTRACT':
            code_specific_rule = (
                "실패한 섹션의 첫 문장은 소제목에 직접 답하는 사실·해법 문장으로 다시 쓰고, "
                "경험 문장 다음의 자기 역량 인증·청중 반응 해설 문장은 삭제하거나 "
                "당시 행동·구체 결과·현재 해법 연결 문장으로만 바꾸십시오."
            )

        targeted_patch_prompt = f"""
<structural_recovery_prompt version="xml-v1" mode="targeted_patch">
  <role>당신은 엄격한 편집자입니다. 원문을 최대한 유지하고 실패한 지점만 부분 수정합니다.</role>
  <failure>
    <code>{_xml_text(failed_code)}</code>
    <reason>{_xml_cdata(failed_reason)}</reason>
    <feedback>{_xml_cdata(failed_feedback)}</feedback>
    <section_index>{section_index if section_index > 0 else 'unknown'}</section_index>
    <section_lengths>{_xml_text(section_lengths_text or 'unknown')}</section_lengths>
  </failure>
  <goal>
    <current_chars>{current_len}</current_chars>
    <target_chars>{min_len}~{max_len}</target_chars>
    <expected_h2>{expected_h2}</expected_h2>
    <expected_p>{min_p}~{max_p}</expected_p>
  </goal>
  <rules>
    <rule order="1">원문 구조와 표현을 최대한 유지하고 수정 범위는 전체의 25% 이내로 제한.</rule>
    <rule order="2">{_xml_text(code_specific_rule)}</rule>
    <rule order="3">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용하고 태그는 정확히 닫을 것.</rule>
    <rule order="4">기존 사실/주장/맥락을 삭제하지 말고, 필요한 구간만 압축·보강할 것.</rule>
    <rule order="5">최종 응답은 title/content XML 태그만 출력할 것.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(title)}</draft_title>
    <draft_content>{_xml_cdata(content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\\n<content>...</content>')}</example>
  </output_contract>
</structural_recovery_prompt>
""".strip()

        # 동적 HTML 스켈레톤 생성 (계약상 paragraphs_per_section 개수만큼 문단 슬롯 배치)
        skeleton_lines = ['<!-- 서론: h2 없음 -->']
        for i in range(1, paragraphs_per_section + 1):
            min_sentence = 2 if i == 1 else 3
            min_chars = 60 if i == 1 else 80
            skeleton_lines.append(f'<p>서론 {i}문단 (최소 {min_sentence}문장, {min_chars}자 이상)</p>')
        body_count = max(1, expected_h2 - 1)  # 본론 섹션 수 (결론 제외)
        for i in range(1, body_count + 1):
            skeleton_lines.append(f'<!-- 본론 {i} -->')
            skeleton_lines.append(f'<h2>본론{i} 소제목 ({H2_OPTIMAL_MIN}~{H2_MAX_LENGTH}자, 질문형 권장)</h2>')
            for j in range(1, paragraphs_per_section + 1):
                skeleton_lines.append(f'<p>본론{i} {j}문단 (최소 3문장, 80자 이상)</p>')
        skeleton_lines.append('<!-- 결론 -->')
        skeleton_lines.append('<h2>결론 소제목</h2>')
        for i in range(1, paragraphs_per_section + 1):
            is_last = (i == paragraphs_per_section)
            min_sentence = 2 if is_last else 3
            min_chars = 60 if is_last else 80
            tail = ', CTA 포함' if is_last else ''
            skeleton_lines.append(f'<p>결론 {i}문단 (최소 {min_sentence}문장, {min_chars}자 이상{tail})</p>')
        skeleton_text = '\n'.join(skeleton_lines)

        full_rewrite_prompt = f"""
<structural_recovery_prompt version="xml-v1">
  <role>당신은 엄격한 편집자입니다. 아래 원고는 구조/형식 검증에 실패했으므로 완전 교정합니다.</role>
  <failure>
    <code>{_xml_text(failed_code)}</code>
    <reason>{_xml_cdata(failed_reason)}</reason>
    <feedback>{_xml_cdata(failed_feedback)}</feedback>
  </failure>
  <goal>
    <current_chars>{current_len}</current_chars>
    <target_chars>{min_len}~{max_len}</target_chars>
    <expected_h2>{expected_h2}</expected_h2>
    <expected_p>{min_p}~{max_p}</expected_p>
  </goal>
  <target_skeleton description="반드시 아래 구조를 따를 것">
{_xml_cdata(skeleton_text)}
  </target_skeleton>
  <rules>
    <rule order="1">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="2">모든 &lt;h2&gt;, &lt;p&gt; 태그를 정확히 열고 닫을 것.</rule>
    <rule order="3">본문에 예시 플레이스홀더([제목], [내용], [구체적 대안] 등)를 남기지 말 것.</rule>
    <rule order="4">기존 핵심 의미/사실은 유지하되 형식과 구조를 완전 교정할 것.</rule>
    <rule order="5">분량 부족이면 구체 근거를 보강하고, 분량 초과면 중복을 압축할 것.</rule>
    <rule order="6">최종 응답은 title/content XML 태그만 출력할 것.</rule>
    <rule order="7">실패 코드({ _xml_text(failed_code) })를 최우선으로 해결하고, 동일 실패 코드가 재발하지 않게 재작성할 것.</rule>
    <rule order="8">반복 관련 실패 코드라면 동일 어구 반복을 줄이고, 초과 부분은 새로운 사실/근거/행동 문장으로 치환할 것(의미 보존).</rule>
    <rule order="9">검증 규칙 설명문이나 메타 문장을 본문으로 출력하지 말 것.</rule>
    <rule order="10">h2 개수를 정확히 {expected_h2}개로 맞출 것. 서론에는 h2를 넣지 말 것.</rule>
    <rule order="11">각 섹션(서론/본론/결론)마다 p 태그를 최소 {section_paragraph_min}개, 최대 {section_paragraph_max}개로 유지할 것. 최소 개수보다 적은 섹션은 허용되지 않습니다.</rule>
    <rule order="12">서론과 결론에 동일 문구를 반복하지 말 것. 결론에서는 새로운 표현으로 재작성.</rule>
    <rule order="13">한 문장짜리 &lt;p&gt;를 만들지 말 것. 문장을 공백 기준으로 반으로 자르지 말고, 주장·근거·의미를 한 문단 안에서 완성할 것.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1800])}</author_bio>
  <draft>
    <draft_title>{_xml_cdata(title)}</draft_title>
    <draft_content>{_xml_cdata(content)}</draft_content>
  </draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata('<title>...</title>\\n<content>...</content>')}</example>
  </output_contract>
</structural_recovery_prompt>
""".strip()

        prompt_plan: List[Tuple[str, float, str]] = [
            (targeted_patch_prompt, 0.0, 'targeted'),
            (full_rewrite_prompt, 0.1, 'full_rewrite'),
        ]

        for prompt, temperature, mode in prompt_plan:
            try:
                response_text = await generate_content_async(
                    prompt,
                    model_name=self.model_name,
                    temperature=temperature,
                    max_output_tokens=4096,
                    retries=1,
                )
                parsed = parse_response(response_text)
                recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
                recovered_title = normalize_artifacts(parsed.get('title', '')) or title
                if not recovered_content:
                    continue

                recovered_plain = strip_html(recovered_content)
                recovered_len = len(recovered_plain)
                h2_count = len(re.findall(r'<h2\b', recovered_content, re.IGNORECASE))
                if mode == 'targeted':
                    # 부분 수정 단계에서 구조가 심하게 무너진 결과는 전면 교정으로 폴백.
                    if recovered_len < int(min_len * 0.55):
                        continue
                    if expected_h2 > 0 and h2_count == 0:
                        continue

                print(
                    f"🔧 [ContentRepairAgent] 구조 보강({mode}) 결과: "
                    f"len={recovered_len}, h2={h2_count}"
                )
                return recovered_content, recovered_title
            except Exception as e:
                print(f"⚠️ [ContentRepairAgent] 구조/분량 보강 복구 실패({mode}): {str(e)}")
                continue

        return None

    async def recover_section_shortfall(
        self,
        *,
        title: str,
        topic: str,
        section_heading: str,
        section_html: str,
        length_spec: Dict[str, int],
        author_bio: str = '',
        failed_code: str,
        failed_reason: str,
        failed_feedback: str,
        failed_meta: Optional[Dict[str, Any]] = None,
        section_contract: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        from ..common.gemini_client import generate_content_async

        failed_meta = failed_meta if isinstance(failed_meta, dict) else {}
        section_contract = section_contract if isinstance(section_contract, dict) else {}
        per_section_min = int(length_spec.get('per_section_min', 0))
        per_section_max = int(length_spec.get('per_section_max', 0))
        from ..common.aeo_config import paragraph_contract_from_length_spec
        section_contract_spec = paragraph_contract_from_length_spec(length_spec)
        section_paragraph_min = int(section_contract_spec['section_paragraph_min'])
        section_paragraph_max = int(section_contract_spec['section_paragraph_max'])
        expected_heading = normalize_context_text(section_heading)
        answer_lead = normalize_context_text(section_contract.get('answerLead'))
        body_writer_hint = normalize_context_text(section_contract.get('bodyWriterHint'))
        first_sentence_roles = normalize_context_text(section_contract.get('firstSentenceRoles'), sep=", ")
        followup_roles = normalize_context_text(section_contract.get('experienceFollowupRoles'), sep=", ")
        violation_sentence = normalize_context_text(
            (failed_meta.get('violation') or {}).get('sentence') if isinstance(failed_meta.get('violation'), dict) else ''
        )
        shortfall_focus_rule = ""
        if failed_code in {"SECTION_LENGTH", "SECTION_P_COUNT"}:
            shortfall_focus_rule = (
                "이 섹션을 읽은 독자가 '그래서 구체적으로 어떻게 할 건데?'라고 물을 만한 지점을 찾아 "
                "실행 방식, 대상, 순서, 근거 중 하나를 분명히 하는 구체 문장 1~2개를 보강하십시오. "
                "어떤 후보나 어떤 선거에도 쓸 수 있는 일반 공약 문장은 금지합니다."
            )
        shortfall_focus_rule_line = (
            f'    <rule order="6">{_xml_text(shortfall_focus_rule)}</rule>\n'
            if shortfall_focus_rule
            else ""
        )

        prompt = f"""
<section_recovery_prompt version="xml-v1">
  <role>당신은 구조 계약 위반 섹션만 다시 쓰는 엄격한 한국어 정치 에디터입니다.</role>
  <goal>
    <section_heading>{_xml_text(expected_heading)}</section_heading>
    <section_chars>{per_section_min}~{per_section_max}</section_chars>
    <section_paragraphs>{section_paragraph_min}~{section_paragraph_max}</section_paragraphs>
    <rule>전체 원고를 다시 쓰지 말고, 아래 섹션 블록 하나만 다시 작성하십시오.</rule>
  </goal>
  <failure>
    <code>{_xml_text(failed_code)}</code>
    <reason>{_xml_cdata(failed_reason)}</reason>
    <feedback>{_xml_cdata(failed_feedback)}</feedback>
    <violation_sentence>{_xml_cdata(violation_sentence or '(없음)')}</violation_sentence>
  </failure>
  <contract>
    <heading_exact>{_xml_text(expected_heading)}</heading_exact>
    <answer_lead>{_xml_cdata(answer_lead or '(없음)')}</answer_lead>
    <first_sentence_roles>{_xml_text(first_sentence_roles or '(없음)')}</first_sentence_roles>
    <experience_followup_roles>{_xml_text(followup_roles or '(없음)')}</experience_followup_roles>
    <body_writer_hint>{_xml_cdata(body_writer_hint or '(없음)')}</body_writer_hint>
  </contract>
  <rules>
    <rule order="1">&lt;h2&gt; 텍스트는 정확히 "{_xml_text(expected_heading)}"로 유지하십시오.</rule>
    <rule order="2">첫 문장은 answer_lead를 그대로 쓰거나, 같은 사실을 더 간결하게 다시 말하십시오.</rule>
    <rule order="3">이 섹션 블록은 &lt;p&gt;를 최소 {section_paragraph_min}개, 최대 {section_paragraph_max}개로 유지하십시오. 최소 개수보다 적은 문단 구성은 허용되지 않습니다.</rule>
    <rule order="4">경험 문장 다음에는 사실, 당시 행동, 구체 결과, 현재 해법 연결만 허용합니다.</rule>
    <rule order="5">자기 역량 인증, 청중 반응 해설, 인지도 자기서술은 금지합니다.</rule>
    <rule order="7">각 &lt;p&gt;는 최소 3문장, 80자 이상의 실질 문단으로 작성하십시오. 한 문장짜리 문단이나 문장 중간을 끊은 문단은 금지합니다.</rule>
{shortfall_focus_rule_line}    <rule order="8">최종 응답은 title/content XML만 출력하고, content 안에는 이 섹션 블록 하나만 넣으십시오.</rule>
  </rules>
  <topic>{_xml_cdata(topic)}</topic>
  <title>{_xml_cdata(title)}</title>
  <author_bio>{_xml_cdata((author_bio or '(없음)')[:1200])}</author_bio>
  <current_section>{_xml_cdata(section_html)}</current_section>
  <output_contract>
    <format>XML</format>
    <allowed_tags>title, content</allowed_tags>
    <example>{_xml_cdata(f'<title>{title or "..."}</title>\\n<content><h2>{expected_heading}</h2><p>...</p><p>...</p><p>...</p></content>')}</example>
  </output_contract>
</section_recovery_prompt>
""".strip()

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.0,
                max_output_tokens=2048,
                retries=1,
            )
            parsed = parse_response(response_text)
            recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
            if not recovered_content:
                return None
            if not re.search(r'<h2\b', recovered_content, re.IGNORECASE):
                recovered_content = f"<h2>{expected_heading}</h2>\n{recovered_content}".strip()
            recovered_heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', recovered_content, re.IGNORECASE | re.DOTALL)
            recovered_heading = strip_html(recovered_heading_match.group(1)).strip() if recovered_heading_match else ''
            if recovered_heading and recovered_heading != expected_heading:
                recovered_content = re.sub(
                    r'<h2[^>]*>.*?</h2>',
                    f"<h2>{expected_heading}</h2>",
                    recovered_content,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            if not re.search(r'<p\b[^>]*>[\s\S]*?</p\s*>', recovered_content, re.IGNORECASE):
                return None
            return recovered_content.strip()
        except Exception as e:
            print(f"⚠️ [ContentRepairAgent] 섹션 복구 실패: {str(e)}")
            return None
