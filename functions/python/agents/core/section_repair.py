import re
from typing import Any, Dict, Optional, Tuple

from ..common.aeo_config import uses_aeo_answer_first
from services.topic_classifier import classify_topic
from ..common.constants import refine_writing_method, resolve_writing_method
from ..common.editorial import STRUCTURE_SPEC
from ..common.theminjoo import get_party_stance
from ..templates.intelligent_selector import select_prompt_parameters
from .prompt_builder import (
    build_retry_directive,
    build_structure_prompt,
    build_style_role_priority_summary,
)
from .structure_normalizer import normalize_structure
from .structure_utils import (
    normalize_artifacts,
    normalize_context_text,
    normalize_html_structure_tags,
    split_into_context_items,
    strip_html,
)


class SectionRepairMixin:
    async def _attempt_section_level_recovery(
        self,
        *,
        content: str,
        title: str,
        topic: str,
        length_spec: Dict[str, int],
        author_bio: str,
        validation: Dict[str, Any],
        poll_focus_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Tuple[str, str, str]]:
        code = str(validation.get('code') or '')
        if code not in {'SECTION_ROLE_CONTRACT', 'SECTION_LENGTH', 'SECTION_P_COUNT'}:
            return None
        if bool(validation.get('isIntroSection')):
            return None

        block_index, section_block_html, section_heading = self._resolve_section_block_from_validation(content, validation)
        if block_index < 0 or not section_block_html or not section_heading:
            return None

        section_contract = self._resolve_section_contract_for_block(
            poll_focus_bundle=poll_focus_bundle,
            length_spec=length_spec,
            block_index=block_index,
        )
        recovered_block = await self.repairer.recover_section_shortfall(
            title=title,
            topic=topic,
            section_heading=section_heading,
            section_html=section_block_html,
            length_spec=length_spec,
            author_bio=author_bio,
            failed_code=code,
            failed_reason=str(validation.get('reason') or ''),
            failed_feedback=str(validation.get('feedback') or ''),
            failed_meta=dict(validation or {}),
            section_contract=section_contract,
        )
        if recovered_block:
            print(f"🧩 [StructureAgent] 섹션 단위 복구 성공: block={block_index + 1}, heading={section_heading}")
            return self._replace_h2_block(content, block_index, recovered_block), title, 'section-repair'

        degraded_block = self._build_degraded_section_block(
            heading_text=section_heading,
            section_block_html=section_block_html,
            section_contract=section_contract,
            validation=validation,
        )
        if degraded_block and degraded_block != section_block_html:
            print(f"🪫 [StructureAgent] 섹션 단위 복구 실패, 축소 블록으로 계속 진행: block={block_index + 1}")
            return self._replace_h2_block(content, block_index, degraded_block), title, 'section-degraded'
        return None

    _PLEDGE_TAIL_RE = re.compile(r'하겠습니다\s*[.!]?\s*$')

    def _strip_counterargument_pledge_tail(
        self,
        content: str,
        outline: Dict[str, Any],
    ) -> str:
        """counterargument_rebuttal 섹션의 모든 문단에서 '~하겠습니다' 문장을 제거."""
        body = outline.get('body', [])
        cr_indices = [
            i for i, sec in enumerate(body) if sec.get('role') == 'counterargument_rebuttal'
        ]
        if not cr_indices:
            return content

        from ..common.korean_morph import split_sentences as kiwi_split

        # HTML에서 body section 위치 식별 (빈 <h2></h2> 마커 기준)
        h2_positions = [m.start() for m in re.finditer(r'<h2\b', content, re.IGNORECASE)]
        for cr_idx in cr_indices:
            if cr_idx >= len(h2_positions):
                continue
            section_start = h2_positions[cr_idx]
            section_end = h2_positions[cr_idx + 1] if cr_idx + 1 < len(h2_positions) else len(content)
            section_html = content[section_start:section_end]

            p_blocks = re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', section_html, re.IGNORECASE)
            if not p_blocks:
                continue

            # 모든 문단을 순회하며 다짐 문장 제거
            total_removed = 0
            for p_inner in p_blocks:
                p_text = re.sub(r'<[^>]*>', '', p_inner).strip()
                if not self._PLEDGE_TAIL_RE.search(p_text):
                    continue
                sentences = kiwi_split(p_text) or [p_text]
                kept = [s for s in sentences if not self._PLEDGE_TAIL_RE.search(s.strip())]
                if kept and len(kept) < len(sentences):
                    removed_count = len(sentences) - len(kept)
                    total_removed += removed_count
                    new_p_text = ' '.join(kept).strip()
                    old_p_tag = f'<p>{p_inner}</p>'
                    new_p_tag = f'<p>{new_p_text}</p>' if new_p_text else ''
                    content = content.replace(old_p_tag, new_p_tag, 1)
                elif not kept:
                    print(
                        f"⚠️ [StructureAgent] counterargument_rebuttal 문단 전체가 다짐 — 유지"
                    )
            if total_removed:
                print(
                    f"🩹 [StructureAgent] counterargument_rebuttal 역할 이탈 교정: "
                    f"다짐 문장 {total_removed}개 제거"
                )

        return content

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        topic = context.get('topic', '')
        user_profile = context.get('userProfile', {})
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}
        category = context.get('category', '')
        sub_category = context.get('subCategory', '')
        instructions = normalize_context_text(context.get('instructions', ''))
        news_context = normalize_context_text(context.get('newsContext', ''))
        # 🔑 [NEW] 입장문과 뉴스/데이터 분리
        stance_text = normalize_context_text(context.get('stanceText', ''))
        news_data_text = normalize_context_text(context.get('newsDataText', ''))
        poll_focus_bundle = context.get('pollFocusBundle') if isinstance(context.get('pollFocusBundle'), dict) else {}
        focused_news_context = normalize_context_text(poll_focus_bundle.get('focusedSourceText'), sep="\n")
        source_instructions = normalize_context_text(stance_text)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(instructions)
        if not strip_html(source_instructions):
            source_instructions = normalize_context_text(topic)
        effective_news_context = focused_news_context or news_data_text or news_context
        target_word_count = context.get('targetWordCount', int(STRUCTURE_SPEC['idealTotalMin']))
        user_keywords = context.get('userKeywords', [])
        style_guide = normalize_context_text(context.get('styleGuide', ''), sep="\n")
        style_fingerprint = context.get('styleFingerprint') if isinstance(context.get('styleFingerprint'), dict) else {}
        generation_profile = context.get('generationProfile') if isinstance(context.get('generationProfile'), dict) else {}
        style_role_priority = build_style_role_priority_summary(style_guide, style_fingerprint)
        personalized_hints = normalize_context_text(context.get('personalizedHints', ''), sep="\n")
        memory_context = normalize_context_text(context.get('memoryContext', ''), sep="\n")
        personalization_context = normalize_context_text(
            [style_role_priority, personalized_hints, memory_context],
            sep="\n",
        )
        profile_support_context = self._build_profile_support_context(user_profile)
        if style_role_priority:
            print("🎯 [StructureAgent] 실제 사용자 전환 예시 우선 주입")
        has_news_source = bool(strip_html(effective_news_context))
        profile_substitute = self._build_profile_substitute_context(user_profile, target_items=3) if not has_news_source else {}
        analyzer_news_context = effective_news_context
        news_source_mode = 'news'
        if not has_news_source:
            news_source_mode = 'profile_fallback'
            substitute_text = normalize_context_text(profile_substitute.get('contextText'))
            if not substitute_text and profile_support_context:
                fallback_items = split_into_context_items(
                    profile_support_context,
                    min_len=12,
                    max_items=3,
                )
                if fallback_items:
                    substitute_text = "\n".join(f"- {item}" for item in fallback_items)
                    if isinstance(profile_substitute, dict):
                        profile_substitute["selectedItems"] = fallback_items
                        profile_substitute["contextText"] = substitute_text
                        profile_substitute["usedBioCount"] = max(
                            int(profile_substitute.get("usedBioCount") or 0),
                            len(fallback_items),
                        )
                    print(
                        "⚠️ [StructureAgent] 프로필 추가정보가 부족하여 Bio 보강 1차 문맥을 대체자료로 사용합니다."
                    )
            # 프로필 대체자료는 context_analyzer에 넘기지 않는다.
            # context_analyzer가 mustIncludeFacts로 추출하면 별도 본론 주제로 오염됨.
            # 대신 prompt_builder의 profileSubstituteContext로만 전달하여
            # 소스 블록 참조용으로 활용한다.
            analyzer_news_context = ""

        print(f"🚀 [StructureAgent] 시작 - 카테고리: {category or '(자동)'}, 주제: {topic}")
        print(f"📊 [StructureAgent] 입장문: {len(stance_text)}자, 뉴스/데이터: {len(news_data_text)}자")
        if news_source_mode == 'news':
            print(f"🧭 [StructureAgent] ContextAnalyzer 소스: 뉴스/데이터 사용 ({len(strip_html(effective_news_context))}자)")
        else:
            print(
                "🧭 [StructureAgent] ContextAnalyzer 소스: 프로필 대체 "
                f"(추가정보 풀 {profile_substitute.get('additionalPoolCount', 0)}개, "
                f"사용 추가정보 {profile_substitute.get('usedAdditionalCount', 0)}개, "
                f"bio 보충 {profile_substitute.get('usedBioCount', 0)}개)"
            )

        # 1. Determine Writing Method
        writing_method = ''
        if category and category != 'auto':
            writing_method = resolve_writing_method(category, sub_category)
            refined = refine_writing_method(writing_method, topic=topic, stance_text=stance_text)
            if refined != writing_method:
                print(f"✍️ [StructureAgent] 작법 선택 정제: {writing_method} → {refined} (기념·성찰 주제 감지)")
                writing_method = refined
            else:
                print(f"✍️ [StructureAgent] 작법 선택 (카테고리 기반): {writing_method}")
        else:
            classification = await classify_topic(topic)
            writing_method = classification['writingMethod']
            refined = refine_writing_method(writing_method, topic=topic, stance_text=stance_text)
            if refined != writing_method:
                print(f"🤖 [StructureAgent] 작법 자동 추론 정제: {writing_method} → {refined} (기념·성찰 주제 감지)")
                writing_method = refined
            else:
                print(f"🤖 [StructureAgent] 작법 자동 추론: {writing_method} (신뢰도: {classification.get('confidence')}, 소스: {classification.get('source')})")

        # 2. Build Author Bio
        author_bio, author_name = self.build_author_bio(user_profile)

        # 3. Get Party Stance
        party_stance_guide = None
        try:
             party_stance_guide = get_party_stance(topic)
        except Exception as e:
             print(f"⚠️ [StructureAgent] 당론 조회 실패: {str(e)}")

        # 4. ContextAnalyzer (입장문/뉴스 분리 처리)
        analyzer_stance_text = source_instructions
        if len(strip_html(analyzer_stance_text)) < 24:
            analyzer_stance_text = normalize_context_text([analyzer_stance_text, topic], sep="\n\n")
        analyzer_news_text = analyzer_news_context

        context_analysis = await self.run_context_analyzer(
            analyzer_stance_text,
            analyzer_news_text,
            author_name
        )
        if isinstance(context_analysis, dict):
            context_analysis = self._normalize_context_analysis_materials(context_analysis)
        # validate_output 호출에 사용하는 이벤트 컨텍스트 힌트는
        # process 스코프에서 항상 초기화되어야 한다.
        is_event_announcement = False
        event_date_hint = ''
        event_location_hint = ''
        if isinstance(context_analysis, dict):
            analysis_intent = str(context_analysis.get('intent') or '').strip().lower()
            must_preserve = context_analysis.get('mustPreserve')
            if analysis_intent == 'event_announcement':
                is_event_announcement = True
                if isinstance(must_preserve, dict):
                    event_date_hint = str(must_preserve.get('eventDate') or '').strip()
                    event_location_hint = str(must_preserve.get('eventLocation') or '').strip()

        reference_text_len = (
            len(strip_html(stance_text))
            + len(strip_html(news_data_text))
            + len(strip_html(instructions))
        )
        stance_count = len(context_analysis.get('mustIncludeFromStance', [])) if context_analysis else 0
        length_spec = self._build_length_spec(
            target_word_count,
            stance_count,
            reference_text_len=reference_text_len,
        )
        print(
            f"📏 [StructureAgent] 분량 계획: {length_spec['total_sections']}섹션, "
            f"{length_spec['min_chars']}~{length_spec['max_chars']}자 "
            f"(섹션당 {length_spec['per_section_recommended']}자)"
        )

        prompt_variation_params: Dict[str, Any] = {}
        if category == 'educational-content':
            try:
                selected = select_prompt_parameters(
                    category='educational-content',
                    topic=topic,
                    instructions=source_instructions,
                )
                if isinstance(selected, dict):
                    prompt_variation_params = selected
                if prompt_variation_params:
                    print(f"🎛️ [StructureAgent] 교육 카테고리 배리에이션 적용: {prompt_variation_params}")
            except Exception as e:
                print(f"⚠️ [StructureAgent] 교육 카테고리 배리에이션 선택 실패: {str(e)}")

        # 5. Build Prompt
        rag_context = normalize_context_text(context.get('ragContext', ''))
        prompt_params: Dict[str, Any] = {
            'topic': topic,
            'category': category,
            'writingMethod': writing_method,
            'authorName': author_name,
            'authorBio': author_bio,
            'instructions': source_instructions,
            'newsContext': effective_news_context,
            'ragContext': rag_context,
            'targetWordCount': target_word_count,
            'partyStanceGuide': party_stance_guide,
            'contextAnalysis': context_analysis,
            'userProfile': user_profile,
            'personalizationContext': personalization_context,
            'memoryContext': memory_context,
            'styleGuide': style_guide,
            'styleFingerprint': style_fingerprint,
            'generationProfile': generation_profile,
            'profileSupportContext': profile_support_context,
            'profileSubstituteContext': profile_substitute.get('contextText') if isinstance(profile_substitute, dict) else '',
            'newsSourceMode': news_source_mode,
            'userKeywords': user_keywords,
            'pollFocusBundle': poll_focus_bundle,
            'lengthSpec': length_spec,
            'outputMode': 'json',
        }
        if prompt_variation_params:
            prompt_params.update(prompt_variation_params)
        prompt = build_structure_prompt(prompt_params)

        print(f"📝 [StructureAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

        # 6. Retry Loop
        max_retries = self.max_retries
        attempt = 0
        feedback = ''
        retry_directive = ''
        validation: Dict[str, Any] = {}
        last_error = None
        best_candidate: Dict[str, Any] = {}
        is_aeo = uses_aeo_answer_first(writing_method)
        aeo_outline: Optional[Dict[str, Any]] = None
        structural_recoverable_codes = {
            'H2_SHORT',
            'H2_LONG',
            'P_SHORT',
            'P_LONG',
            'SECTION_P_COUNT',
            'H2_MALFORMED',
            'P_MALFORMED',
            'TAG_DISALLOWED',
            'DUPLICATE_SENTENCE',
            'PHRASE_REPEAT',
            'VERB_REPEAT',
            'PHRASE_REPEAT_CAP',
            'MATERIAL_REUSE',
            'INTRO_STANCE_MISSING',
            'INTRO_CONCLUSION_ECHO',
            'LOCATION_ORPHAN_REPEAT',
            'META_PROMPT_LEAK',
            'EVENT_FACT_REPEAT',
            'EVENT_INVITE_REDUNDANT',
            'SECTION_LENGTH',
            'SECTION_ROLE_CONTRACT',
            'H2_TEXT_LONG',
            'H2_TEXT_MODIFIER',
            'H2_TEXT_FIRST_PERSON',
            'H2_TEXT_SHORT',
        }

        def _candidate_rank(candidate_validation: Dict[str, Any], candidate_content: str) -> tuple:
            plain_len = len(strip_html(candidate_content or ''))
            code = str(candidate_validation.get('code') or '')
            penalties = {
                'LENGTH_SHORT': 8,
                'LENGTH_LONG': 7,
                'H2_SHORT': 4,
                'H2_LONG': 4,
                'P_SHORT': 5,
                'P_LONG': 5,
                'H2_MALFORMED': 6,
                'P_MALFORMED': 6,
                'TAG_DISALLOWED': 6,
            }
            penalty = penalties.get(code, 5)
            return (
                1 if bool(candidate_validation.get('passed')) else 0,
                1 if plain_len >= int(length_spec.get('min_chars') or 0) else 0,
                1 if plain_len <= int(length_spec.get('max_chars') or 999999) else 0,
                -penalty,
                -abs(plain_len - int(length_spec.get('min_chars') or 0)),
                plain_len,
            )

        def _remember_best(
            candidate_content: str,
            candidate_title: str,
            candidate_validation: Dict[str, Any],
            source: str,
            source_attempt: int,
        ) -> None:
            nonlocal best_candidate
            if not candidate_content:
                return
            rank = _candidate_rank(candidate_validation, candidate_content)
            if (not best_candidate) or rank > tuple(best_candidate.get('rank') or ()):
                best_candidate = {
                    'content': candidate_content,
                    'title': candidate_title,
                    'validation': dict(candidate_validation or {}),
                    'rank': rank,
                    'plain_len': len(strip_html(candidate_content or '')),
                    'source': source,
                    'attempt': source_attempt,
                }

        def _evaluate_candidate_with_normalizer(
            candidate_content: str,
            candidate_title: str,
            *,
            source: str,
            source_attempt: int,
        ) -> Tuple[str, Dict[str, Any], str]:
            structural_gate_codes = {
                'LENGTH_SHORT',
                'LENGTH_LONG',
                'H2_SHORT',
                'H2_LONG',
                'SECTION_P_COUNT',
                'P_SHORT',
                'P_LONG',
                'SECTION_LENGTH',
                'H2_MALFORMED',
                'P_MALFORMED',
                'TAG_DISALLOWED',
                'H2_TEXT_SHORT',
                'H2_TEXT_LONG',
                'H2_TEXT_MODIFIER',
                'H2_TEXT_FIRST_PERSON',
            }

            def _failure_stage(validation_result: Dict[str, Any]) -> int:
                if validation_result.get('passed'):
                    return 3
                code = str(validation_result.get('code') or '')
                if code in structural_gate_codes:
                    return 0
                return 1

            base_content = normalize_artifacts(candidate_content)
            base_content = normalize_html_structure_tags(base_content)
            raw_validation = self.validator.validate(
                base_content,
                length_spec,
                category=category,
                context_analysis=context_analysis,
                is_event_announcement=is_event_announcement,
                event_date_hint=event_date_hint,
                event_location_hint=event_location_hint,
                poll_focus_bundle=poll_focus_bundle,
            )
            raw_rank = _candidate_rank(raw_validation, base_content)
            raw_source = f"{source}-raw"
            _remember_best(base_content, candidate_title, raw_validation, source=raw_source, source_attempt=source_attempt)

            normalized_content = normalize_structure(
                base_content,
                length_spec,
                user_keywords=user_keywords,
                context_analysis=context_analysis,
            )
            normalized_validation = self.validator.validate(
                normalized_content,
                length_spec,
                category=category,
                context_analysis=context_analysis,
                is_event_announcement=is_event_announcement,
                event_date_hint=event_date_hint,
                event_location_hint=event_location_hint,
                poll_focus_bundle=poll_focus_bundle,
            )
            normalized_rank = _candidate_rank(normalized_validation, normalized_content)
            _remember_best(normalized_content, candidate_title, normalized_validation, source=source, source_attempt=source_attempt)

            if raw_validation.get('passed') and not normalized_validation.get('passed'):
                print(
                    f"⚠️ [StructureAgent] 정규화 후 품질 퇴행 감지: "
                    f"raw=PASS, normalized=FAIL({normalized_validation.get('code')})"
                )
                return base_content, raw_validation, raw_source

            if normalized_validation.get('passed') and not raw_validation.get('passed'):
                print(
                    f"✅ [StructureAgent] 정규화 교정 성공: "
                    f"raw=FAIL({raw_validation.get('code')}), normalized=PASS"
                )
                return normalized_content, normalized_validation, source

            raw_stage = _failure_stage(raw_validation)
            normalized_stage = _failure_stage(normalized_validation)
            if normalized_stage > raw_stage:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧭 [StructureAgent] 단계 우선 선택(normalized): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return normalized_content, normalized_validation, source
            if raw_stage > normalized_stage:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧭 [StructureAgent] 단계 우선 선택(raw): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return base_content, raw_validation, raw_source

            if raw_rank > normalized_rank:
                if raw_validation.get('code') != normalized_validation.get('code'):
                    print(
                        f"🧪 [StructureAgent] 후보 선택(raw 우선): "
                        f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                    )
                return base_content, raw_validation, raw_source

            if raw_validation.get('code') != normalized_validation.get('code'):
                print(
                    f"🧪 [StructureAgent] 후보 선택(normalized 우선): "
                    f"raw={raw_validation.get('code')} / normalized={normalized_validation.get('code')}"
                )
            return normalized_content, normalized_validation, source

        while attempt <= max_retries:
            attempt += 1
            print(f"🔄 [StructureAgent] 생성 시도 {attempt}/{max_retries + 1}")

            current_prompt = prompt
            if feedback:
                retry_block = f"\n\n{retry_directive}" if retry_directive else ""
                current_prompt += (
                    f"\n\n🚨 [중요 - 재작성 지시] 이전 작성본이 다음 이유로 반려되었습니다:\n"
                    f"\"{feedback}\"{retry_block}"
                )

            try:
                # === AEO 2단계: 아웃라인 생성 (첫 시도에서만) ===
                if is_aeo and aeo_outline is None:
                    try:
                        outline_prompt = self._build_outline_json_prompt(
                            prompt=prompt,
                            length_spec=length_spec,
                            writing_method=writing_method,
                        )
                        outline_schema = self._build_outline_json_schema(
                            length_spec, writing_method=writing_method,
                        )
                        aeo_outline = await self.call_llm_json_contract(
                            outline_prompt,
                            response_schema=outline_schema,
                            required_keys=("title", "intro_lead", "body", "conclusion_heading"),
                            stage="outline",
                            max_output_tokens=2048,
                        )
                        outline_roles = [s.get('role', '-') for s in aeo_outline.get('body', [])]
                        print(
                            f"📋 [StructureAgent] 아웃라인 생성 완료: "
                            f"title='{aeo_outline.get('title', '')[:30]}', "
                            f"body_sections={len(aeo_outline.get('body', []))}, "
                            f"roles={outline_roles}"
                        )
                        # --- 두괄식 검증 게이트 ---
                        lead_failures = self._validate_outline_lead_sentences(aeo_outline, writing_method=writing_method)
                        if lead_failures:
                            print(
                                f"⚠️ [StructureAgent] 아웃라인 lead_sentence 검증 실패 "
                                f"({len(lead_failures)}건): {lead_failures}"
                            )
                            # 실패 사유를 피드백으로 넣어 1회 재시도
                            feedback_lines = "\n".join(f"  - {f}" for f in lead_failures)
                            retry_outline_prompt = (
                                outline_prompt
                                + "\n\n<feedback priority='critical'>\n"
                                  "이전 아웃라인의 다음 lead_sentence가 행동 선언이 아닌 상황 진단형으로 판정되어 반려됨:\n"
                                + feedback_lines
                                + "\n모든 lead_sentence를 '~하겠습니다', '~추진합니다', '~확보합니다' 등 "
                                  "행동을 선언하는 어미로 다시 작성하십시오. "
                                  "'~상황입니다', '~과제입니다', '~핵심입니다', '~필요합니다' 등 "
                                  "진단·평가 어미는 절대 사용 금지.\n</feedback>"
                            )
                            aeo_outline = await self.call_llm_json_contract(
                                retry_outline_prompt,
                                response_schema=outline_schema,
                                required_keys=("title", "intro_lead", "body", "conclusion_heading"),
                                stage="outline-retry",
                                max_output_tokens=2048,
                            )
                            retry_failures = self._validate_outline_lead_sentences(aeo_outline, writing_method=writing_method)
                            if retry_failures:
                                print(
                                    f"⚠️ [StructureAgent] 아웃라인 재시도 후에도 검증 실패 "
                                    f"({len(retry_failures)}건), 단일 호출로 폴백: {retry_failures}"
                                )
                                is_aeo = False
                            else:
                                print("📋 [StructureAgent] 아웃라인 재생성 후 검증 통과")
                        # --- 검증 게이트 끝 ---

                        # --- 변증법 역할 시퀀스 검증 ---
                        if is_aeo and aeo_outline is not None:
                            role_failures = self._validate_outline_roles(
                                aeo_outline, writing_method=writing_method,
                            )
                            if role_failures:
                                print(
                                    f"⚠️ [StructureAgent] 아웃라인 role 시퀀스 검증 실패 "
                                    f"({len(role_failures)}건): {role_failures}"
                                )
                                # role이 스키마 enum이므로 값 자체는 유효 — 순서만 수정
                                # 아웃라인의 role을 강제로 올바른 시퀀스로 덮어쓰기
                                from ..common.aeo_config import build_dialectical_roles
                                body = aeo_outline.get('body', [])
                                expected = build_dialectical_roles(len(body))
                                for section, exp in zip(body, expected):
                                    section['role'] = exp['role']
                                print("📋 [StructureAgent] role 시퀀스 강제 교정 완료")
                    except Exception as outline_err:
                        print(f"⚠️ [StructureAgent] 아웃라인 생성 실패, 단일 호출로 폴백: {outline_err}")
                        is_aeo = False

                # === LLM 본문 생성 ===
                print(
                    f"📋 [StructureAgent] 본문 생성 경로: "
                    f"is_aeo={is_aeo}, has_outline={aeo_outline is not None}"
                )
                if is_aeo and aeo_outline is not None:
                    json_prompt = self._build_expansion_json_prompt(
                        outline=aeo_outline,
                        base_prompt=current_prompt,
                        length_spec=length_spec,
                        writing_method=writing_method,
                    )
                    response_schema = self._build_structure_json_schema(length_spec)
                    payload = await self.call_llm_json_contract(
                        json_prompt,
                        response_schema=response_schema,
                        required_keys=("title", "intro", "body", "conclusion"),
                        stage="expansion",
                        max_output_tokens=8192,
                    )
                else:
                    json_prompt = self._build_structure_json_prompt(
                        prompt=current_prompt,
                        length_spec=length_spec,
                    )
                    response_schema = self._build_structure_json_schema(length_spec)
                    payload = await self.call_llm_json_contract(
                        json_prompt,
                        response_schema=response_schema,
                        required_keys=("title", "intro", "body", "conclusion"),
                        stage="structure",
                        max_output_tokens=8192,
                    )

                raw_content, title = self._build_html_from_structure_json(
                    payload,
                    length_spec=length_spec,
                    topic=topic,
                    poll_focus_bundle=poll_focus_bundle,
                )
                raw_content = normalize_artifacts(raw_content)
                raw_content = normalize_html_structure_tags(raw_content)

                # counterargument_rebuttal 역할 이탈 검증:
                # 마지막 문단이 "~하겠습니다"로 끝나면 정책 다짐 침투
                if is_aeo and aeo_outline is not None:
                    raw_content = self._strip_counterargument_pledge_tail(
                        raw_content, aeo_outline,
                    )
                title = normalize_artifacts(title)

                plain_len = len(strip_html(raw_content))
                body_sections = len(payload.get('body') or []) if isinstance(payload, dict) else 0
                print(
                    f"📐 [StructureAgent] 시도 {attempt} 길이: "
                    f"json_body_sections={body_sections}, parsed={len(raw_content)}자, plain={plain_len}자"
                )
                if plain_len < 400:
                    raise Exception(f"JSON 구조 결과가 비정상적으로 짧습니다 ({plain_len}자)")

                content, validation, selected_source = _evaluate_candidate_with_normalizer(
                    raw_content,
                    title,
                    source='draft',
                    source_attempt=attempt,
                )

                if validation['passed']:
                    print(f"✅ [StructureAgent] 검증 통과({selected_source}): {len(strip_html(content))}자")
                    if not title.strip():
                        title = topic[:20] if topic else '새 원고'
                    return {
                        'content': content,
                        'title': title,
                        'writingMethod': writing_method,
                        'contextAnalysis': context_analysis
                    }

                print(
                    f"⚠️ [StructureAgent] 검증 실패: code={validation.get('code')} "
                    f"reason={validation['reason']}"
                )
                if str(validation.get('code') or '') == 'DUPLICATE_SENTENCE':
                    dup_samples = validation.get('duplicateSamples') or []
                    dup_count = validation.get('duplicateCount')
                    print(
                        f"🔎 [StructureAgent] DUPLICATE_SENTENCE details: "
                        f"count={dup_count}, samples={dup_samples}"
                    )
                if str(validation.get('code') or '') == 'INTRO_CONCLUSION_ECHO':
                    dup_samples = validation.get('duplicatePhrases') or []
                    dup_count = validation.get('duplicateCount')
                    print(
                        f"🔎 [StructureAgent] INTRO_CONCLUSION_ECHO details: "
                        f"count={dup_count}, samples={dup_samples}"
                    )

                recovery_code = str(validation.get('code') or '')
                recovery_content = content
                recovery_title = title
                recovery_validation = dict(validation or {})
                section_recovery_attempt = await self._attempt_section_level_recovery(
                    content=recovery_content,
                    title=recovery_title,
                    topic=topic,
                    length_spec=length_spec,
                    author_bio=author_bio,
                    validation=recovery_validation,
                    poll_focus_bundle=poll_focus_bundle,
                )
                if section_recovery_attempt:
                    recovered_content, recovered_title, recovered_source = section_recovery_attempt
                    recovered_content, recovered_validation, normalized_source = _evaluate_candidate_with_normalizer(
                        recovered_content,
                        recovered_title,
                        source=recovered_source,
                        source_attempt=attempt,
                    )
                    if recovered_validation.get('passed'):
                        print(
                            f"✅ [StructureAgent] 섹션 단위 복구 통과({normalized_source}): "
                            f"{len(strip_html(recovered_content))}자"
                        )
                        if not recovered_title.strip():
                            recovered_title = topic[:20] if topic else '새 원고'
                        return {
                            'content': recovered_content,
                            'title': recovered_title,
                            'writingMethod': writing_method,
                            'contextAnalysis': context_analysis,
                        }
                    print(
                        f"⚠️ [StructureAgent] 섹션 단위 복구 후에도 검증 실패: "
                        f"code={recovered_validation.get('code')} reason={recovered_validation.get('reason')}"
                    )
                    recovery_content = recovered_content
                    recovery_title = recovered_title
                    recovery_validation = dict(recovered_validation or {})
                    recovery_code = str(recovery_validation.get('code') or '')
                if recovery_code == 'LENGTH_SHORT':
                    max_recovery_rounds = self.length_recovery_rounds
                elif recovery_code in structural_recoverable_codes:
                    max_recovery_rounds = self.structural_recovery_rounds
                else:
                    max_recovery_rounds = 0

                # 후반 시도에서는 복구 루프를 1회로 제한해 꼬리 지연을 줄인다.
                if attempt >= self.late_recovery_start_attempt:
                    max_recovery_rounds = min(max_recovery_rounds, self.late_recovery_cap)

                for recovery_round in range(1, max_recovery_rounds + 1):
                    current_code = str(recovery_validation.get('code') or '')
                    recovery_result: Optional[Tuple[str, str]] = None

                    if current_code == 'LENGTH_SHORT':
                        recovery_result = await self.repairer.recover_length_shortfall(
                            content=recovery_content,
                            title=recovery_title,
                            topic=topic,
                            length_spec=length_spec,
                            author_bio=author_bio,
                        )
                    elif current_code in structural_recoverable_codes:
                        recovery_result = await self.repairer.recover_structural_shortfall(
                            content=recovery_content,
                            title=recovery_title,
                            topic=topic,
                            length_spec=length_spec,
                            author_bio=author_bio,
                            failed_code=current_code,
                            failed_reason=str(recovery_validation.get('reason') or ''),
                            failed_feedback=str(recovery_validation.get('feedback') or ''),
                            failed_meta=dict(recovery_validation or {}),
                        )

                    if not recovery_result:
                        break

                    recovered_content, recovered_title = recovery_result
                    recovered_content, recovered_validation, recovered_source = _evaluate_candidate_with_normalizer(
                        recovered_content,
                        recovered_title,
                        source='repair',
                        source_attempt=attempt,
                    )
                    if recovered_validation.get('passed'):
                        print(
                            f"✅ [StructureAgent] 복구 검증 통과({recovered_source}): "
                            f"{len(strip_html(recovered_content))}자"
                        )
                        if not recovered_title.strip():
                            recovered_title = topic[:20] if topic else '새 원고'
                        return {
                            'content': recovered_content,
                            'title': recovered_title,
                            'writingMethod': writing_method,
                            'contextAnalysis': context_analysis
                        }

                    next_code = str(recovered_validation.get('code') or '')
                    print(
                        f"⚠️ [StructureAgent] 복구 시도 {recovery_round}/{max_recovery_rounds} 실패: "
                        f"code={next_code} reason={recovered_validation.get('reason')}"
                    )

                    same_code = next_code == current_code
                    unchanged_text = strip_html(recovered_content) == strip_html(recovery_content)
                    recovery_content = recovered_content
                    recovery_title = recovered_title
                    recovery_validation = dict(recovered_validation or {})

                    if same_code and unchanged_text:
                        print(
                            "⚠️ [StructureAgent] 복구 결과가 동일해 추가 복구를 중단합니다."
                        )
                        break

                content = recovery_content
                title = recovery_title
                validation = recovery_validation

                feedback = str(validation.get('feedback') or validation.get('reason') or '')
                retry_directive = build_retry_directive(validation, length_spec)
                last_error = None

            except Exception as e:
                error_msg = str(e)
                print(f"❌ [StructureAgent] 에러 발생: {error_msg}")
                feedback = error_msg
                retry_directive = ''
                last_error = error_msg

            if attempt > max_retries:
                if best_candidate:
                    best_content = best_candidate.get('content', '')
                    best_title = best_candidate.get('title') or topic[:20] or '새 원고'
                    best_validation = best_candidate.get('validation') or {}
                    best_code = str(best_validation.get('code') or '').strip()
                    best_len = int(best_candidate.get('plain_len') or 0)

                    # 구조 검증 실패(SECTION_P_COUNT)면 normalizer 최종 시도
                    if best_code in ('SECTION_P_COUNT', 'P_SHORT'):
                        print(
                            f"🩹 [StructureAgent] best-effort 구조 보정 시도: code={best_code}"
                        )
                        patched = normalize_structure(
                            best_content,
                            length_spec,
                            user_keywords=user_keywords,
                            context_analysis=context_analysis,
                        )
                        patched_validation = self.validator.validate(
                            patched,
                            length_spec,
                            category=category,
                            context_analysis=context_analysis,
                            is_event_announcement=is_event_announcement,
                            event_date_hint=event_date_hint,
                            event_location_hint=event_location_hint,
                            poll_focus_bundle=poll_focus_bundle,
                        )
                        patched_code = str(patched_validation.get('code') or '').strip()
                        if patched_validation.get('passed') or patched_code != best_code:
                            best_content = patched
                            best_validation = patched_validation
                            best_code = patched_code
                            print(
                                f"✅ [StructureAgent] best-effort 구조 보정 성공: code={best_code}"
                            )
                        else:
                            print(
                                f"⚠️ [StructureAgent] best-effort 구조 보정 실패, 원본 유지"
                            )

                    if best_code in ('SECTION_P_COUNT', 'P_SHORT'):
                        final_reason = (
                            best_validation.get('reason')
                            or best_validation.get('feedback')
                            or f"구조 검증 실패: {best_code}"
                        )
                        raise Exception(
                            f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason}"
                        )

                    print(
                        f"⚠️ [StructureAgent] 검증 미통과 — best-effort 반환: "
                        f"code={best_code}, len={best_len}, "
                        f"source={best_candidate.get('source')}"
                    )
                    return {
                        'content': best_content,
                        'title': best_title,
                        'writingMethod': writing_method,
                        'contextAnalysis': context_analysis,
                    }
                final_reason = last_error or validation.get('reason', '알 수 없는 오류')
                raise Exception(f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason}")
