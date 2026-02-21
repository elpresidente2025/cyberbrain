import re
from typing import Dict, Any, Optional, Tuple
from .structure_utils import (
    strip_html,
    normalize_artifacts,
    normalize_html_structure_tags,
    _xml_text,
    _xml_cdata,
    parse_response
)

class ContentRepairAgent:
    def __init__(self, model_name: str):
        self.model_name = model_name

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
            rewrite_mode = best_len < int(min_len * 0.6)

            if rewrite_mode:
                prompt = f"""
<length_recovery_prompt version="xml-v1" mode="full_rewrite">
  <role>당신은 엄격한 한국어 정치 에디터입니다. 현재 초안이 지나치게 짧으므로 완전 재작성합니다.</role>
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
    <rule order="6">최종 분량은 {min_len}~{max_len}자 범위를 반드시 충족.</rule>
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
                    max_output_tokens=8192,
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
    ) -> Optional[Tuple[str, str]]:
        from ..common.gemini_client import generate_content_async

        current_len = len(strip_html(content))
        min_len = int(length_spec.get('min_chars', 0))
        max_len = int(length_spec.get('max_chars', 0))
        expected_h2 = int(length_spec.get('expected_h2', 0))
        total_sections = int(length_spec.get('total_sections', 5))
        min_p = total_sections * 2
        max_p = total_sections * 4

        prompt = f"""
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

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.1,
                max_output_tokens=8192,
            )
            parsed = parse_response(response_text)
            recovered_content = normalize_html_structure_tags(normalize_artifacts(parsed.get('content', '')))
            recovered_title = normalize_artifacts(parsed.get('title', '')) or title
            if not recovered_content:
                return None
            return recovered_content, recovered_title
        except Exception as e:
            print(f"⚠️ [ContentRepairAgent] 구조/분량 보강 복구 실패: {str(e)}")
            return None
