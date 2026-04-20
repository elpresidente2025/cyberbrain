
import logging
import re
from typing import Dict, Any, List, Optional
from ..base_agent import Agent
from ..common.natural_tone import build_natural_tone_prompt

logger = logging.getLogger(__name__)

STYLE_FINGERPRINT_MIN_CONFIDENCE = 0.55
STYLE_GUIDE_MAX_CHARS = 700
STYLE_POLISH_LIMITS = {
    "light": {"max_sentences": 3, "max_ratio": "20%"},
    "medium": {"max_sentences": 6, "max_ratio": "30%"},
}


def _is_identity_signature_phrase(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return any(
        token in normalized
        for token in ("뼛속까지", "입니다", "저 ", "저는", "이재성!", "저 이재성")
    )


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
        from ..common.gemini_client import generate_json_async

        content = context.get('content', '')
        title = context.get('title', '')
        validation_result = context.get('validationResult', {})
        keyword_result = context.get('keywordResult', {})
        user_keywords = context.get('keywords', [])
        keyword_aliases = context.get('keywordAliases') or {}
        if not isinstance(keyword_aliases, dict):
            keyword_aliases = {}
        status = context.get('status', 'active')
        target_word_count = context.get('targetWordCount', 2000)
        polish_mode = bool(context.get('polishMode') is True)
        speaker_name = str(context.get('fullName') or context.get('speakerName') or '').strip()
        style_guide = str(context.get('styleGuide') or '').strip()
        style_fingerprint = context.get('styleFingerprint')
        if not isinstance(style_fingerprint, dict):
            style_fingerprint = {}
        generation_profile = context.get('generationProfile')
        if not isinstance(generation_profile, dict):
            generation_profile = {}
        style_polish_mode = str(context.get('stylePolishMode') or '').strip().lower()
        style_instruction = self._build_style_polish_instruction(
            style_guide=style_guide,
            style_fingerprint=style_fingerprint,
            generation_profile=generation_profile,
            mode=style_polish_mode,
            enabled=polish_mode,
        )

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
            target_word_count=target_word_count,
            speaker_name=speaker_name,
            polish_mode=polish_mode,
            style_instruction=style_instruction,
        )

        if not self._client:
            logger.warning("No client for EditorAgent, returning original")
            return self.apply_hard_constraints(content, title, user_keywords, status)

        # Call LLM
        try:
            result = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.7,
                max_output_tokens=8192,
                retries=2,
                required_keys=("content",),
                options={'json_parse_retries': 2},
            )

            new_content = result.get('content', content)
            new_title = result.get('title', title)
            edit_summary = result.get('editSummary', [])

            # 2. Apply Hard Constraints (Post-LLM)
            constrained = self.apply_hard_constraints(
                content=new_content,
                title=new_title,
                user_keywords=user_keywords,
                status=status,
                previous_summary=edit_summary
            )

            # 2.5. Kiwi 기반 "저는" pro-drop 라벨링 (humanize 힌트)
            from ..common import korean_morph
            _fp_plain_for_label = re.sub(r'<[^>]+>', ' ', constrained['content'])
            _fp_plain_for_label = re.sub(r'\s+', ' ', _fp_plain_for_label).strip()
            fp_labels = korean_morph.label_first_person_sentences(_fp_plain_for_label)
            print(
                f"[EditorAgent] Step 2.5 fp_labels="
                f"{len(fp_labels)}건" if isinstance(fp_labels, list) else f"fp_labels={fp_labels!r}"
            )

            # 2.5b. Kiwi 기반 AI 수사 반복 라벨링 (humanize 힌트)
            ai_rhetoric_labels = korean_morph.label_ai_rhetoric_sentences(_fp_plain_for_label)
            if ai_rhetoric_labels is None:
                print("[EditorAgent] Step 2.5b ai_rhetoric_labels=None (Kiwi 불가)")
            else:
                _rl_summary = {k: len(v) for k, v in ai_rhetoric_labels.items()} if ai_rhetoric_labels else {}
                print(f"[EditorAgent] Step 2.5b ai_rhetoric_labels={_rl_summary or 'clean'}")

            # 3. Humanize pass (oh-my-humanizer 스타일 2차 LLM)
            # stylometry aiAlternatives 추출 (AI 수사 힌트 연동용)
            _ai_alts: Dict[str, str] = {}
            _sf_alts = style_fingerprint.get("aiAlternatives") if isinstance(style_fingerprint, dict) else None
            if isinstance(_sf_alts, dict):
                for _ak, _av in _sf_alts.items():
                    _src = str(_ak or "").replace("instead_of_", "").replace("_", " ").strip()
                    _dst = str(_av or "").strip()
                    if _src and _dst:
                        _ai_alts[_src] = _dst
            # userNativeWords 화이트리스트: 사용자가 직접 쓴 patina 대상어는 교정 제외
            _user_native: set = set()
            if isinstance(style_fingerprint, dict):
                _unw = style_fingerprint.get("userNativeWords")
                if isinstance(_unw, list):
                    _user_native = {str(w).strip() for w in _unw if w}
            if _user_native:
                print(f"[EditorAgent] userNativeWords whitelist={sorted(_user_native)}")
            print(f"[EditorAgent] Step 3 humanize 시작, user_keywords={user_keywords}")
            humanized = await self._humanize_pass(
                content=constrained['content'],
                title=constrained['title'],
                speaker_name=speaker_name,
                style_instruction=style_instruction,
                user_keywords=user_keywords,
                keyword_aliases=keyword_aliases,
                edit_summary=constrained.get('editSummary', []),
                fp_labels=fp_labels,
                ai_rhetoric_labels=ai_rhetoric_labels,
                ai_alternatives=_ai_alts or None,
                user_native_words=_user_native or None,
            )
            _humanize_changed = humanized.get('content', '') != constrained['content']
            constrained['content'] = humanized.get('content', constrained['content'])
            constrained['editSummary'] = constrained['editSummary'] + humanized.get('changes', [])
            print(
                f"[EditorAgent] Step 3 humanize 완료, changed={_humanize_changed}, "
                f"changes={humanized.get('changes', [])}"
            )
            if (
                style_instruction
                and constrained['content'] != content
                and "사용자 문체 일부 반영" not in constrained['editSummary']
            ):
                constrained['editSummary'].append("사용자 문체 일부 반영")

            # 3.5. post-humanize 고유명사 속격 "의" 강제 치환
            # LLM이 "계양 테크노밸리" → "계양의 테크노밸리" / "계양의 TV" 로
            # 풀어쓰는 현상을 기계적으로 확정 복원한다.
            # HTML 태그가 끼어있을 수 있으므로 regex 로 처리.
            post_content = constrained['content']
            _genitive_fix_count = 0
            for kw in (user_keywords or []):
                kw_clean = str(kw).strip()
                if not kw_clean:
                    continue
                parts = kw_clean.split()
                if len(parts) < 2:
                    continue
                for i in range(len(parts) - 1):
                    left = re.escape(parts[i])
                    right = re.escape(" ".join(parts[i + 1:]))
                    # "X의 Y", "X의Y", "X의 <tag>Y" 등 다양한 패턴
                    pattern = left + r'의\s*(?:<[^>]*>\s*)*' + right
                    replacement = parts[i] + " " + " ".join(parts[i + 1:])
                    new_content = re.sub(pattern, replacement, post_content)
                    if new_content != post_content:
                        _genitive_fix_count += post_content.count(parts[i] + "의") - new_content.count(parts[i] + "의")
                        post_content = new_content
            if _genitive_fix_count > 0:
                constrained['editSummary'].append(
                    f"고유명사 속격 '의' 분해 {_genitive_fix_count}건 강제 복원"
                )
            constrained['content'] = post_content

            # 3.6. Deterministic progressive overuse fix (Layer 2)
            # "하고 있습니다" 초과분을 Kiwi 기반으로 기계적 치환
            _step36_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
            _step36_plain = re.sub(r'\s+', ' ', _step36_plain).strip()
            _prog_info = korean_morph.find_progressive_overuse_kiwi(_step36_plain)
            if _prog_info is not None and _prog_info.get("fixable"):
                _prog_fixed = 0
                _prog_content = constrained['content']
                _hada_map = korean_morph.HADA_PROGRESSIVE_MAP
                # 뒤에서부터 치환 (앞부분 문맥 보존)
                for item in reversed(_prog_info["fixable"]):
                    ending = item["ending_form"]
                    replacement = _hada_map.get(ending)
                    if not replacement:
                        continue
                    # HTML 태그를 허용하는 패턴 (속격 복원과 동일 전략)
                    pattern = r'하고\s*(?:<[^>]*>\s*)*있' + re.escape(ending)
                    new_content = re.sub(pattern, replacement, _prog_content, count=1)
                    if new_content != _prog_content:
                        _prog_content = new_content
                        _prog_fixed += 1
                if _prog_fixed > 0:
                    constrained['content'] = _prog_content
                    constrained['editSummary'].append(
                        f"진행형 '하고 있다' {_prog_fixed}건 → 현재형 강제 변환"
                        f" (전체 {_prog_info['total']}건 중 {_prog_info['total'] - len(_prog_info['fixable'])}건 유지)"
                    )
                print(
                    f"[EditorAgent] Step 3.6 progressive: total={_prog_info['total']}, "
                    f"fixable={len(_prog_info['fixable'])}, fixed={_prog_fixed}"
                )
            else:
                _prog_total = _prog_info["total"] if _prog_info else 0
                print(f"[EditorAgent] Step 3.6 progressive: total={_prog_total}, fixable=0")

            # 3.6c. Kiwi 기반 저-한자어 잘림 복원
            # humanize LLM이 "저해하는/저하되는" 등을 "저"로 잘라내는 환각을 기계적 복원
            _step36c_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
            _step36c_plain = re.sub(r'\s+', ' ', _step36c_plain).strip()
            _jeo_truncations = korean_morph.find_truncated_jeo_hanja_kiwi(
                _fp_plain_for_label, _step36c_plain
            )
            if _jeo_truncations:
                _jeo_fixed = 0
                _jeo_content = constrained['content']
                for t in _jeo_truncations:
                    word = t["original_word"]
                    bw = re.escape(t["before_word"]) if t.get("before_word") else ""
                    aw = re.escape(t["after_word"]) if t.get("after_word") else ""
                    # HTML 태그를 허용하는 context 매칭 패턴
                    _html_gap = r'(\s*(?:<[^>]*>\s*)*)'
                    if bw and aw:
                        pat = re.compile(bw + _html_gap + r'저' + _html_gap + aw)
                    elif aw:
                        pat = re.compile(r'(?<![가-힣])저' + _html_gap + aw)
                    else:
                        continue
                    m = pat.search(_jeo_content)
                    if m:
                        if bw and aw:
                            repl = t["before_word"] + m.group(1) + word + m.group(2) + t["after_word"]
                        else:
                            repl = word + m.group(1) + t["after_word"]
                        _jeo_content = _jeo_content[:m.start()] + repl + _jeo_content[m.end():]
                        _jeo_fixed += 1
                if _jeo_fixed > 0:
                    constrained['content'] = _jeo_content
                    constrained['editSummary'].append(
                        f"저-한자어 잘림 {_jeo_fixed}건 복원 ({', '.join(t['original_word'] for t in _jeo_truncations)})"
                    )
                print(
                    f"[EditorAgent] Step 3.6c jeo_hanja: detected={len(_jeo_truncations)}, "
                    f"fixed={_jeo_fixed}"
                )
            else:
                _jeo_label = "clean" if _jeo_truncations is not None else "Kiwi불가"
                print(f"[EditorAgent] Step 3.6c jeo_hanja: {_jeo_label}")

            # 3.7. post-humanize "저는" 문두 비율 경고 (기계적 삭제 없음)
            # 실제 교정은 humanize 프롬프트가 담당. 여기서는 비율만 측정해 editSummary 에 기록.
            _fp_re = re.compile(r'저는\s')
            _fp_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
            _fp_plain = re.sub(r'\s+', ' ', _fp_plain).strip()
            _fp_all_sents = [s.strip() for s in re.split(r'(?<=[.?!])\s+', _fp_plain) if len(s.strip()) > 5]
            _fp_matched = [s for s in _fp_all_sents if _fp_re.match(s)]
            _fp_ratio = len(_fp_matched) / len(_fp_all_sents) if _fp_all_sents else 0
            print(f"[EditorAgent] Step 3.7 '저는' 비율={len(_fp_matched)}/{len(_fp_all_sents)}({_fp_ratio:.0%})")
            if _fp_ratio > 0.20 and len(_fp_matched) >= 3:
                constrained['editSummary'].append(
                    f"'저는' 문두 과다 — {len(_fp_matched)}/{len(_fp_all_sents)}문장({_fp_ratio:.0%}), 목표 20% 이하"
                )

            # 3.7b. post-humanize AI 수사 반복 잔�� 경고
            _post_ai_labels = korean_morph.label_ai_rhetoric_sentences(_fp_plain)
            _post_rl_summary = {k: len(v) for k, v in _post_ai_labels.items()} if _post_ai_labels else {}
            print(f"[EditorAgent] Step 3.7b post-humanize ai_rhetoric={_post_rl_summary or '(clean/None)'}")
            if _post_ai_labels:
                _ai_rhet_instr = {
                    "unsourced_evidence": "출처 없는 근거",
                    "demonstrative_overuse": "지시 관형사",
                    "abstract_inclusive": "추상 포용 수사",
                    "suffix_jeok_overuse": "~적 접미사",
                    "ai_adjective_overuse": "AI 고빈도 수식",
                    "progressive_overuse": "진행형",
                    "vague_source": "모호 출처",
                    "hyperbole": "과장 수사",
                    "negative_parallel": "부정 병렬",
                    "verbose_particle": "장황 조사",
                    "translationese": "번역체",
                    "superficial_chain": "~하며 체인",
                    "cliche_prospect": "클리셰 전망",
                }
                _ai_warnings = []
                for _ai_key, _ai_items in _post_ai_labels.items():
                    if _ai_items:
                        _ai_warnings.append(f"'{_ai_rhet_instr.get(_ai_key, _ai_key)}' {len(_ai_items)}건")
                if _ai_warnings:
                    constrained['editSummary'].append(
                        f"AI 수사 잔존 — {', '.join(_ai_warnings)}"
                    )

            # 3.8. "테크노밸리" → "TV" 약어 분산
            # 트리거 1: 사용자 키워드에 "테크노밸리" 포함 & SEO 허용치 초과 → 초과분 TV
            # 트리거 2: 제목에 "테크노밸리" 포함 → 본문 5:5 비율로 TV 교체
            _tv_content = constrained['content']
            _tv_title = constrained.get('title', '')
            _TV_KEYWORD = "테크노밸리"
            _TV_ABBR = "TV"
            _TV_MAX_SEO = 6  # SEO 허용 최대 등장 횟수

            # 본문 plain text 에서 "테크노밸리" 횟수 측정 (제목 제외)
            _tv_plain = re.sub(r'<[^>]+>', ' ', _tv_content)
            _tv_plain = re.sub(r'\s+', ' ', _tv_plain).strip()
            _tv_body_count = len(re.findall(re.escape(_TV_KEYWORD), _tv_plain))

            # 키워드에 "테크노밸리" 가 포함된 키워드 찾기
            _tv_kw_match = [kw for kw in (user_keywords or []) if _TV_KEYWORD in str(kw)]
            _tv_in_title = _TV_KEYWORD in _tv_title

            print(f"[EditorAgent] Step 3.8 TV: body_count={_tv_body_count}, kw_match={_tv_kw_match}, in_title={_tv_in_title}")
            _tv_target_count = 0  # TV 로 바꿀 횟수
            if _tv_kw_match and _tv_body_count > _TV_MAX_SEO:
                # 트리거 1: SEO 초과분 전부 TV
                _tv_target_count = _tv_body_count - _TV_MAX_SEO
            elif _tv_in_title and _tv_body_count >= 4:
                # 트리거 2: 제목에 있으면 본문 절반을 TV
                _tv_target_count = _tv_body_count // 2

            if _tv_target_count > 0:
                # H2 제외 후 치환 가능한 위치 수집
                _tv_matches = list(re.finditer(re.escape(_TV_KEYWORD), _tv_content))
                _tv_eligible = []
                for m in _tv_matches:
                    before = _tv_content[:m.start()]
                    if re.search(r'<h2[^>]*>[^<]*$', before):
                        continue
                    _tv_eligible.append(m)

                # 균등 분산: eligible 중 등간격으로 target_count 개 선택
                _tv_replaced = 0
                n = len(_tv_eligible)
                if n > 0 and _tv_target_count > 0:
                    if _tv_target_count >= n:
                        to_replace = set(range(n))
                    else:
                        # 간격을 두고 분산 선택 (0번째는 보존, 1번째부터 시작)
                        step = n / (_tv_target_count + 1)
                        to_replace = set()
                        for k in range(1, _tv_target_count + 1):
                            idx = min(int(k * step), n - 1)
                            to_replace.add(idx)

                    # 뒤에서부터 치환 (offset 보존)
                    for idx in sorted(to_replace, reverse=True):
                        m = _tv_eligible[idx]
                        _tv_content = _tv_content[:m.start()] + _TV_ABBR + _tv_content[m.end():]
                        _tv_replaced += 1
                if _tv_replaced > 0:
                    constrained['content'] = _tv_content
                    constrained['editSummary'].append(
                        f"'테크노밸리' → 'TV' {_tv_replaced}건 약어 분산 (본문 {_tv_body_count}회 중)"
                    )
            print(f"[EditorAgent] Step 3.8 TV 결과: target={_tv_target_count}, replaced={_tv_replaced if _tv_target_count > 0 else 0}")

            # 3.9. 소스에 없는 허구 수치가 포함된 문장 삭제
            _source_texts = context.get('sourceTexts') or []
            if _source_texts:
                from ..common.fact_guard import build_fact_allowlist, find_unsupported_numeric_tokens
                _fact_allowlist = build_fact_allowlist(_source_texts)
                _fact_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
                _fact_plain = re.sub(r'\s+', ' ', _fact_plain).strip()
                _fact_check = find_unsupported_numeric_tokens(_fact_plain, _fact_allowlist)
                _unsupported = _fact_check.get('unsupported') or []
                if _unsupported:
                    # unsupported 수치가 포함된 문장을 HTML에서 삭제
                    _fact_removed = 0
                    _fc = constrained['content']
                    for token in _unsupported:
                        # token이 포함된 <p>...</p> 또는 문장을 찾아 삭제
                        escaped = re.escape(token)
                        # <p> 태그 안 문장 삭제
                        p_pattern = r'<p>[^<]*' + escaped + r'[^<]*</p>\s*'
                        new_fc = re.sub(p_pattern, '', _fc)
                        if new_fc != _fc:
                            _fact_removed += 1
                            _fc = new_fc
                    if _fact_removed > 0:
                        constrained['content'] = _fc
                        constrained['editSummary'].append(
                            f"소스에 없는 허구 수치 {_unsupported} 포함 문장 {_fact_removed}건 삭제"
                        )
                    print(f"[EditorAgent] Step 3.9 unsupported_numerics: {_unsupported}, removed={_fact_removed}")
                else:
                    print("[EditorAgent] Step 3.9 unsupported_numerics: none")
            else:
                print("[EditorAgent] Step 3.9 skipped (no sourceTexts)")

            # 4. post-humanize 필수 키워드 최소 등장 검증 (경고만, 자동 치환 안 함)
            # humanize 가 지시어로 과치환해 고유명사 빈도가 떨어지는 케이스를 플래그.
            MIN_BODY_OCCURRENCES = 3
            plain_body_final = re.sub(r'<[^>]+>', ' ', constrained['content'])
            plain_body_final = re.sub(r'\s+', ' ', plain_body_final).strip()
            for keyword in (user_keywords or []):
                kw = str(keyword).strip()
                if not kw:
                    continue
                body_count = plain_body_final.count(kw)
                if body_count < MIN_BODY_OCCURRENCES:
                    constrained['editSummary'].append(
                        f"필수 키워드 '{kw}' 본문 {body_count}회 — 기준({MIN_BODY_OCCURRENCES}회) 미달, 지시어 과치환 검토"
                    )

            return constrained

        except Exception as e:
            logger.error(f"EditorAgent failed: {e}")
            # Fallback to hard constraints only
            return self.apply_hard_constraints(content, title, user_keywords, status, error=str(e))

    def build_editor_prompt(
        self,
        content,
        title,
        validation_result,
        keyword_result,
        user_keywords,
        status,
        target_word_count,
        speaker_name: str = "",
        polish_mode: bool = False,
        style_instruction: str = "",
    ):
        issues = []
        
        # 1. Validation issues
        details = {}
        if hasattr(validation_result, 'get'):
             details = validation_result.get('details', {})

             # Election Law
             election_law = details.get('electionLaw', {}) or {}
             election_items = election_law.get('items') or []
             if isinstance(election_items, list) and election_items:
                  election_lines = []
                  for item in election_items[:3]:
                       if not isinstance(item, dict):
                            continue
                       reason = str(item.get('reason') or '선거법 위반 위험').strip()
                       sentence = str(item.get('sentence') or '').strip()
                       repair_hint = str(item.get('repairHint') or '').strip()
                       matched_text = str(item.get('matchedText') or '').strip()
                       detail_parts = [reason]
                       if sentence:
                            detail_parts.append(f'문제 문장: "{sentence}"')
                       if matched_text:
                            detail_parts.append(f'문제 표현: "{matched_text}"')
                       if repair_hint:
                            detail_parts.append(f'수정 가이드: {repair_hint}')
                       election_lines.append("   - " + " | ".join(detail_parts))
                  if election_lines:
                       issues.append(
                            "[CRITICAL] 선거법 위반 표현 발견:\n"
                            + "\n".join(election_lines)
                            + "\n   → 문제 문장만 최소 수정하되, 전언/소문/간접전언 표현은 완전히 제거"
                       )
             elif election_law.get('violations'):
                  violations = ", ".join(election_law['violations'])
                  issues.append(f"[CRITICAL] 선거법 위반 표현 발견: {violations}\n   → 선거법을 준수하는 완곡한 표현으로 수정 (예: '~하겠습니다' -> '~추진합니다')")

             # Repetition
             if details.get('repetition', {}).get('repeatedSentences'):
                  repeated = ", ".join(details['repetition']['repeatedSentences'][:3])
                  issues.append(f"[HIGH] 문장 반복 감지: {repeated}...\n   → 반복을 피하고 다른 표현으로 수정")

        # 3. Keyword issues
        if hasattr(keyword_result, 'get'):
             if not keyword_result.get('passed', True):
                  kw_issues = keyword_result.get('issues', [])
                  if kw_issues:
                       issues.append(f"[HIGH] 키워드 문제:\n" + "\n".join([f"   - {i}" for i in kw_issues]))

        # Format issues list
        if issues:
            issues_text = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(issues)])
        elif polish_mode:
            issues_text = "(치명 이슈 없음 - 최종 윤문 모드: 가독성/문장 완성도 중심으로 다듬으세요)"
        else:
            issues_text = "(없음 - 전반적인 톤앤매너와 구조만 다듬으세요)"
        
        status_note = ""
        if status in ['준비', '현역']:
             status_note = f"\n⚠️ 작성자 상태: {status} (예비후보 등록 전) - 공약성 표현 엄격 금지"
             
        natural_tone = build_natural_tone_prompt({'severity': 'strict'})
        speaker_guard = ""
        if speaker_name:
            speaker_guard = f"""
7. **화자 정체성 고정**: 이 글의 유일한 1인칭 화자는 \"{speaker_name}\"입니다.
   - \"저는 {speaker_name}\" 또는 \"저는/제가\" 시점만 허용
   - \"저는 [다른 인물명] 후보/시장/의원...\" 형태는 절대 금지
   - 경쟁자 언급은 반드시 3인칭(예: \"주진우 후보는\")으로만 작성
""".strip()
        else:
            speaker_guard = """
7. **화자 정체성 고정**: 1인칭 화자를 다른 인물로 바꾸지 마세요.
   - \"저는 [다른 인물명] 후보/시장/의원...\" 형태는 절대 금지
""".strip()
        
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
5. **최종 윤문**: 의미/사실/정치적 입장/수치/고유명사는 유지하고 문장 흐름, 연결어, 호흡만 개선
6. **과편집 금지**: 원문의 핵심 주장과 논리 순서를 바꾸지 말 것
{speaker_guard}
 
다음 JSON 형식으로만 응답하세요:
{{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정 사항 1", "수정 사항 2"]
}}"""

    def _build_style_polish_instruction(
        self,
        *,
        style_guide: str,
        style_fingerprint: Dict[str, Any],
        generation_profile: Optional[Dict[str, Any]] = None,
        mode: str = "",
        enabled: bool = False,
    ) -> str:
        if not enabled:
            return ""
        gen_profile = generation_profile if isinstance(generation_profile, dict) else {}

        normalized_mode = mode if mode in STYLE_POLISH_LIMITS else "light"
        limits = STYLE_POLISH_LIMITS[normalized_mode]

        metadata = style_fingerprint.get("analysisMetadata") or {}
        try:
            confidence = float(metadata.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0

        normalized_guide = re.sub(r"\s+", " ", str(style_guide or "")).strip()
        if not normalized_guide and confidence < STYLE_FINGERPRINT_MIN_CONFIDENCE:
            return ""

        lines = [
            (
                f"- 전체 재작성은 금지하고 도입, 문단 연결, 강조, 결론 문장 위주로만 "
                f"최대 {limits['max_sentences']}문장 또는 전체의 {limits['max_ratio']} 이내에서 조정합니다."
            ),
            "- 숫자, 날짜, 인명, 지명, 인용, 정책 주장, 법적 표현, 필수 키워드는 절대 바꾸지 않습니다.",
            "- 내용과 논리 구조는 유지하고 말맛과 호흡만 사용자답게 다듬습니다.",
        ]

        if normalized_guide:
            guide_excerpt = normalized_guide[:STYLE_GUIDE_MAX_CHARS]
            if len(normalized_guide) > STYLE_GUIDE_MAX_CHARS:
                guide_excerpt += "..."
            lines.append(f"- 사용자 문체 가이드: {guide_excerpt}")

        if confidence >= STYLE_FINGERPRINT_MIN_CONFIDENCE:
            phrases = style_fingerprint.get("characteristicPhrases") or {}
            patterns = style_fingerprint.get("sentencePatterns") or {}
            tone = style_fingerprint.get("toneProfile") or {}
            alts = style_fingerprint.get("aiAlternatives") or {}

            signature_candidates = []
            identity_signatures: List[str] = []
            for key in ("signatures", "emphatics", "conclusions"):
                raw_values = phrases.get(key) or []
                if isinstance(raw_values, list):
                    for item in raw_values:
                        value = str(item).strip()
                        if not value:
                            continue
                        if key == "signatures" and _is_identity_signature_phrase(value):
                            if value not in identity_signatures:
                                identity_signatures.append(value)
                            continue
                        signature_candidates.append(value)
            deduped_signatures: List[str] = []
            seen_signatures = set()
            for item in signature_candidates:
                if item in seen_signatures:
                    continue
                seen_signatures.add(item)
                deduped_signatures.append(item)
                if len(deduped_signatures) >= 5:
                    break
            if deduped_signatures:
                lines.append(f"- 선호 표현 예시: {', '.join(deduped_signatures)}")
            if identity_signatures:
                lines.append(
                    "- 정체성 시그니처는 자기 이름/1인칭 선언 문장(도입·마감)에서만 사용: "
                    f"{', '.join(identity_signatures[:3])}"
                )

            starters = patterns.get("preferredStarters") or []
            if isinstance(starters, list):
                preferred_starters = [str(item).strip() for item in starters if str(item).strip()][:3]
                if preferred_starters:
                    lines.append(f"- 문장 시작 습관: {', '.join(preferred_starters)}")

            avg_length = patterns.get("avgLength")
            clause_complexity = str(patterns.get("clauseComplexity") or "").strip()
            if avg_length or clause_complexity:
                lines.append(
                    f"- 문장 호흡: 평균 {avg_length or 45}자 안팎, 복잡도 {clause_complexity or 'medium'}"
                )

            tone_tags: List[str] = []
            try:
                formality = float(tone.get("formality") or 0)
            except (TypeError, ValueError):
                formality = 0.0
            try:
                directness = float(tone.get("directness") or 0)
            except (TypeError, ValueError):
                directness = 0.0
            try:
                optimism = float(tone.get("optimism") or 0)
            except (TypeError, ValueError):
                optimism = 0.0
            if formality >= 0.6:
                tone_tags.append("격식 있는 존댓말")
            elif formality and formality <= 0.4:
                tone_tags.append("조금 더 구어적인 호흡")
            if directness >= 0.6:
                tone_tags.append("직설적인 전달")
            if optimism >= 0.6:
                tone_tags.append("희망과 확신의 어조")
            tone_description = str(tone.get("toneDescription") or "").strip()
            if tone_tags or tone_description:
                tone_text = ", ".join(tone_tags) if tone_tags else tone_description
                if tone_description and tone_description not in tone_text:
                    tone_text = f"{tone_text}, {tone_description}"
                lines.append(f"- 어조 목표: {tone_text}")

            replacement_pairs: List[str] = []
            for raw_key, raw_value in list(alts.items())[:4]:
                replacement = str(raw_value or "").strip()
                if not replacement:
                    continue
                source = str(raw_key or "").replace("instead_of_", "").replace("_", " ").strip()
                if not source:
                    continue
                replacement_pairs.append(f'"{source}" -> "{replacement}"')
                if len(replacement_pairs) >= 2:
                    break
            if replacement_pairs:
                lines.append(f"- AI 상투어 대체 예시: {', '.join(replacement_pairs)}")

        if gen_profile:
            target_len = gen_profile.get("target_sentence_length")
            if isinstance(target_len, (list, tuple)) and len(target_len) == 2:
                try:
                    lo = int(target_len[0])
                    hi = int(target_len[1])
                    if lo > 0 and hi > lo:
                        lines.append(f"- 목표 문장 길이: 평균 {lo}~{hi}자 범위 유지")
                except (TypeError, ValueError):
                    pass
            try:
                target_cv = float(gen_profile.get("target_cv") or 0)
            except (TypeError, ValueError):
                target_cv = 0.0
            if target_cv > 0:
                if target_cv < 0.25:
                    lines.append("- 문장 길이 변동: 고르게 유지(변동 최소)")
                elif target_cv < 0.45:
                    lines.append("- 문장 길이 변동: 자연스러운 리듬 변화")
                else:
                    lines.append("- 문장 길이 변동: 짧은 문장과 긴 문장 적극 혼합")
            forbidden = gen_profile.get("forbidden_patterns") or []
            if isinstance(forbidden, list):
                forbidden_clean = [str(p).strip() for p in forbidden if str(p).strip()][:4]
                if forbidden_clean:
                    lines.append(f"- 사용 금지 패턴: {', '.join(forbidden_clean)}")
            preferred_endings = gen_profile.get("preferred_endings") or []
            if isinstance(preferred_endings, list):
                endings_clean = [str(e).strip() for e in preferred_endings if str(e).strip()][:4]
                if endings_clean:
                    lines.append(f"- 선호 종결 어미: {', '.join(endings_clean)}")

            # ── 서술 전략 지시 ────────────────────────────────
            try:
                emo_dir = float(gen_profile.get("emotionDirectness") or gen_profile.get("emotion_directness") or 0.5)
            except (TypeError, ValueError):
                emo_dir = 0.5
            if emo_dir < 0.3:
                lines.append(
                    "- 감정 표현 전략: '안타깝다/감사하다/가슴 아프다' 등 감정 직접 명명을 최소화하세요. "
                    "상황·행동·장면 묘사로 독자가 감정을 추론하도록 유도합니다(show, don't tell)."
                )
            elif emo_dir > 0.7:
                lines.append(
                    "- 감정 표현 전략: 이 화자는 감정을 직접 명명하는 스타일입니다. 억누르지 마세요."
                )

            try:
                cdr = float(gen_profile.get("concreteDetailRatio") or gen_profile.get("concrete_detail_ratio") or 0.4)
            except (TypeError, ValueError):
                cdr = 0.4
            if cdr < 0.25:
                lines.append(
                    "- 구체 디테일: 이 화자는 수치·데이터보다 서사·경험 중심입니다. "
                    "숫자를 과도하게 삽입하지 마세요."
                )
            elif cdr > 0.6:
                lines.append(
                    "- 구체 디테일: 이 화자는 사실·수치·날짜를 적극 사용합니다. "
                    "추상 서술은 구체 근거로 뒷받침하세요."
                )

        return "\n".join(lines)

    async def _humanize_pass(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
        user_keywords: Optional[List[str]] = None,
        keyword_aliases: Optional[Dict[str, Any]] = None,
        edit_summary: Optional[List[str]] = None,
        fp_labels: Optional[List[Dict[str, str]]] = None,
        ai_rhetoric_labels: Optional[Dict[str, list]] = None,
        ai_alternatives: Optional[Dict[str, str]] = None,
        user_native_words: Optional[set] = None,
    ) -> Dict[str, Any]:
        """oh-my-humanizer 스타일 2차 LLM 패스.

        1단계(감지): AI 투 표현 식별
        2단계(교체): 자연스러운 구어체로 재작성
        3단계(검증): 스스로 잔존 패턴 확인
        """
        from ..common.gemini_client import generate_json_async

        prompt = self._build_humanize_prompt_v2(
            content,
            title,
            speaker_name,
            style_instruction=style_instruction,
            user_keywords=user_keywords,
            keyword_aliases=keyword_aliases,
            edit_summary=edit_summary,
            fp_labels=fp_labels,
            ai_rhetoric_labels=ai_rhetoric_labels,
            ai_alternatives=ai_alternatives,
            user_native_words=user_native_words,
        )
        try:
            result = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.2,
                max_output_tokens=8192,
                retries=1,
                required_keys=("content",),
                options={'json_parse_retries': 1},
            )
            return {
                'content': result.get('content', content),
                'changes': result.get('changes', []),
            }
        except Exception as e:
            logger.warning(f"humanize_pass 실패 (원본 유지): {e}")
            return {'content': content, 'changes': []}

    def _build_humanize_prompt(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
    ) -> str:
        speaker_note = f'화자는 "{speaker_name}"입니다. 화자 정체성을 바꾸지 마세요.' if speaker_name else ""
        return f"""당신은 AI가 생성한 한국어 텍스트를 인간이 쓴 것처럼 자연스럽게 다듬는 전문가입니다.
{speaker_note}

아래 원고를 3단계로 처리하세요.

[1단계 — 감지]
다음 AI 투 패턴을 찾으세요:
- 대칭 구조 남발: "~뿐만 아니라 ~도", "~은 물론 ~까지", "~을 넘어 ~로"
- 추상 수식어: "혁신적인", "실현 가능한", "진정성", "새로운 미래", "더 나은 내일"
- 형식적 마무리: "함께 만들겠습니다", "함께 나아가겠습니다", "도움이 되었으면 합니다"
- 결론 클리셰: "결론적으로", "요약하자면", "이러한 점에서"
- 과도한 확신: "확신합니다", "분명합니다", "틀림없습니다" (사실 근거 없이)

[2단계 — 교체]
감지된 표현을 아래 원칙으로 교체하세요:
- 추상어 → 구체적 사실/수치/경험으로 대체
- 대칭 구조 → 단문으로 분리하거나 어순 변경
- 형식적 마무리 → 구체적 다짐이나 행동으로 대체
- 수정 시 의미·사실·수치·고유명사는 절대 변경 금지
- 5단 구조(서론-본론1-본론2-본론3-결론) 유지

예시:
BAD:  "이는 단순한 경제 성장을 넘어, 시민 모두가 함께 잘사는 부산을 의미합니다."
GOOD: "부산 경제가 살아나면 시민 삶의 질도 함께 오릅니다."

BAD:  "저의 혁신적인 비전과 실현 가능한 정책들을 통해"
GOOD: "제가 준비한 정책들을 통해"

BAD:  "저의 진정성은 시민 여러분께 큰 공감을 얻을 것이라고 확신합니다."
GOOD: "시민 여러분이 직접 판단해 주시리라 믿습니다."

[3단계 — 검증]
수정 후 스스로 확인: "아직도 AI가 쓴 것처럼 들리는 문장이 있는가?"
있다면 추가 수정.

[원본 제목]
{title}

[원본 본문]
{content}

다음 JSON 형식으로만 응답하세요:
{{
  "content": "수정된 본문 (HTML 태그 유지)",
  "changes": ["교체한 표현 1: BAD → GOOD", "교체한 표현 2: BAD → GOOD"]
}}"""

    def _build_humanize_prompt_v2(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
        user_keywords: Optional[List[str]] = None,
        keyword_aliases: Optional[Dict[str, Any]] = None,
        edit_summary: Optional[List[str]] = None,
        fp_labels: Optional[List[Dict[str, str]]] = None,
        ai_rhetoric_labels: Optional[Dict[str, list]] = None,
        ai_alternatives: Optional[Dict[str, str]] = None,
        user_native_words: Optional[set] = None,
    ) -> str:
        speaker_note = (
            f'화자는 "{speaker_name}"입니다. 화자 정체성을 바꾸지 마세요.'
            if speaker_name
            else ""
        )
        style_note = ""
        if style_instruction:
            style_note = f"""
[사용자 문체 덧씌우기]
{style_instruction}
- 이 지시는 필요한 문장에만 부분 적용합니다.
- 특히 도입, 연결, 강조, 결론에 우선 적용하고 나머지는 최소한으로 손봅니다.
""".strip()

        # 고유명사 보호 목록 (사용자 지정 키워드) — 사이에 "의" 삽입 금지 + 최소 등장 횟수
        proper_noun_note = ""
        if user_keywords:
            protected = [str(k).strip() for k in user_keywords if str(k).strip()]
            if protected:
                joined = ", ".join(f'"{name}"' for name in protected)
                proper_noun_note = (
                    "[고유명사 보호 목록 — 필수 키워드]\n"
                    f"{joined}\n"
                    "- 위 고유명사는 한 덩어리입니다. 어절 사이에 속격 조사 '의'를 넣지 말고 원형대로 붙여 쓰세요.\n"
                    "  예: '계양 테크노밸리'를 '계양의 테크노밸리'로 풀어쓰지 않습니다.\n"
                    "- 필수 키워드는 본문 전체에서 최소 3회 이상, 각 섹션의 첫 문장에는 반드시 고유명사 원형으로 등장해야 합니다.\n"
                    "- 지시어('이곳', '이 사업', '우리 지역')로 과도하게 바꾸면 무엇을 가리키는지 흐려집니다. 섹션이 바뀌면 지시어 대신 고유명사를 다시 씁니다."
                )

        # 키워드 변형어 (동어 반복 회피용) — 사용자 텍스트에서 추출된 별칭
        alias_note = ""
        if keyword_aliases and isinstance(keyword_aliases, dict):
            kw_set = set(str(k).strip() for k in (user_keywords or []) if str(k).strip())
            alias_lines = []
            for canonical, aliases in keyword_aliases.items():
                canonical = str(canonical).strip()
                if not canonical:
                    continue
                if kw_set and canonical not in kw_set:
                    continue
                if not isinstance(aliases, list) or not aliases:
                    continue
                clean = [str(a).strip() for a in aliases if str(a).strip()]
                if clean:
                    alias_lines.append(f'- "{canonical}" → {", ".join(f"{a!r}" for a in clean)}')
            if alias_lines:
                alias_note = (
                    "[키워드 변형어 — 동어 반복 회피용]\n"
                    + "\n".join(alias_lines) + "\n"
                    "- 위 변형어는 사용자 본인이 실제로 쓰는 축약어·별칭입니다. 본문에서 2~3회 사용 가능합니다.\n"
                    "- 원형과 변형어의 합산 횟수가 상한을 넘지 않도록 배분하세요.\n"
                    "- 변형어도 고유명사 보호 대상입니다. 사이에 '의'를 넣거나 분해하지 마세요.\n"
                    "- '이곳', '이 사업' 같은 지시어 대신 변형어를 우선 사용하세요."
                )

        # 직전 단계에서 감지된 비문 — humanize 가 반드시 수정
        # (형태소 분석기 + regex 가 이미 문장을 특정했으므로 LLM 은 해당 문장만
        # 집중 수정하면 된다. 이전 버전은 "N건" 카운트만 넘겨 LLM 이 위치 특정에
        # 실패하는 경우가 많았다.)
        prior_flags_note = ""
        if edit_summary:
            suspicious = [
                s for s in edit_summary
                if isinstance(s, str)
                and (
                    "주술 불일치" in s
                    or "속격" in s
                    or "중복 조사" in s
                    or "이중 주어" in s
                    or "어간 반복" in s
                    or "지시어 고립" in s
                    or "지시어 역전" in s
                    or "'저는' 문두 과다" in s
                )
            ]
            if suspicious:
                lines = "\n".join(f"- {line}" for line in suspicious)
                prior_flags_note = (
                    "[직전 단계 감지 — 다음 문장들은 반드시 수정하세요]\n"
                    f"{lines}\n"
                    "- 위 인용된 문장을 본문에서 찾아 해당 문장만 골라 고치세요. 문장 전체가 자연스러워질 때까지 바꾸되, 의미·수치·고유명사는 유지합니다.\n"
                    "- 각 flag 가 \"'X' 로 복원\" 형식의 후보 고유명사를 명시한 경우, 해당 문장의 지시어(이곳/이는/이를/이러한)를 그 고유명사 원형으로 치환하세요. 후보가 문맥상 어색하면 다른 사용자 필수 키워드로 대체하되, 지시어 상태로 방치하지 마세요.\n"
                    "- 아래 [1단계-감지] 의 각 규칙별 BAD/GOOD 예시를 이 문장들에 그대로 적용하세요.\n"
                    "- 위 문장을 손대지 않으면 이 윤문은 실패한 것으로 간주합니다."
                )

        # "저는" pro-drop 라벨 힌트 생성
        fp_hint_note = ""
        if fp_labels:
            delete_count = sum(1 for l in fp_labels if l["label"] == "삭제 권장")
            keep_count = sum(1 for l in fp_labels if l["label"] == "유지")
            if delete_count > 0:
                lines = []
                for l in fp_labels:
                    marker = "→ 삭제/분산" if l["label"] == "삭제 권장" else "→ 유지"
                    lines.append(f'  {marker} ({l["reason"]}): "{l["text"][:60]}{"…" if len(l["text"]) > 60 else ""}"')
                fp_hint_note = (
                    f'["저는" 문장별 교정 지시 — 형태소 분석 결과]\n'
                    f'총 {len(fp_labels)}개 "저는" 문장 중 {delete_count}개 삭제/분산 권장, {keep_count}개 유지.\n'
                    + "\n".join(lines)
                    + "\n위 지시에 따라 '삭제/분산' 표시된 문장에서 '저는'을 생략하거나, 문중으로 이동하거나, 주어를 구체 사실로 전환하세요."
                )

        # AI 수사 패턴 힌트 생성
        _AI_RHETORIC_INSTRUCTIONS = {
            "unsourced_evidence": ("출처 없는 근거 호출", "실제 수치가 없으면 해당 수식��를 삭제하고 직접 서술로 재���성"),
            "demonstrative_overuse": ("지시 관형사 남용", "절반 이상을 구체 명사(정책���·사업명·지역명)로 교체"),
            "abstract_inclusive": ("추상 포용 수사 반복", "하나만 남기고 나머지는 구체 대상으로 전환"),
            "suffix_jeok_overuse": ("~적 접미사 남용", "한 문장에 '~적' 3개 이상 — 하나를 풀어쓰거나 구체어로 전환"),
            "ai_adjective_overuse": ("AI 고빈도 관형사", "절반 이상��� 구체 서술이�� 다른 수식어로 교체"),
            "progressive_overuse": ("~하고 있다 진행형 남용", "과거형·���재형·명사형으로 다양화"),
            "vague_source": ("모호 출처 표현", "구체적 인명·기관·날짜 없으면 수식구 삭제"),
            "hyperbole": ("과장 수사", "일상적 대상에 '전환점/패러다임' 등 ���장 — 축소하거나 삭제"),
            "negative_parallel": ("���정 병렬 과다", "'뿐만 아니라' 류가 2회+ — 하나만 남기고 직접 연결"),
            "verbose_particle": ("장황 조사", "'에 있어서' 류를 '에서/으로/은' 등 간결 조사로 교체"),
            "translationese": ("번역체", "'것은 사실이다/에 의해' 등을 자연스러운 한국어로 전환"),
            "superficial_chain": ("~하며 피상 체인", "3회+ 연결 체인을 끊어 문장 분리"),
            "cliche_prospect": ("과제��� 전망 클리셰", "'밝은 ���망/새로운 도약' 류를 구체 계획·일정으로 교체"),
        }
        ai_rhetoric_hint = ""
        if ai_rhetoric_labels:
            # ai_alternatives 연동: 탐지된 패턴에 사용자별 대체어 매핑
            _alts = ai_alternatives or {}
            _native = user_native_words or set()
            hints = []
            for key, (label, instruction) in _AI_RHETORIC_INSTRUCTIONS.items():
                items = ai_rhetoric_labels.get(key, [])
                if _native and items:
                    # userNativeWords 화이트리스트: 사용자가 직접 쓴 단어가
                    # 포함된 탐지 항목은 교정 대상에서 제외
                    items = [
                        item for item in items
                        if not any(nw in item.get("text", "") for nw in _native)
                    ]
                if items:
                    # 탐지 문장에서 aiAlternatives 매칭 검색
                    alt_note = ""
                    if _alts and key in ("ai_adjective_overuse", "suffix_jeok_overuse", "hyperbole", "cliche_prospect"):
                        matched_alts = []
                        for item in items:
                            txt = item.get("text", "")
                            for src, dst in _alts.items():
                                if src in txt and f'"{src}"→"{dst}"' not in matched_alts:
                                    matched_alts.append(f'"{src}"→"{dst}"')
                        if matched_alts:
                            alt_note = f" (사용자 선호 대체: {', '.join(matched_alts[:3])})"
                    hints.append(f"\u25b8 {label} ({len(items)}건) — {instruction}{alt_note}:")
                    for item in items[:5]:
                        txt = item.get("text", "")
                        hints.append(f'  \u00b7 "{txt[:60]}{"���" if len(txt) > 60 else ""}"')
            if hints:
                ai_rhetoric_hint = (
                    "[AI 수사 패턴 �� 형태소 분석 결과 (필수 교정)]\n"
                    + "\n".join(hints)
                    + "\n\n[필수 교정 규칙]\n"
                    + "위 항목은 형태소 분석기가 기계적으로 확정한 패턴입니다.\n"
                    + "'문맥상 자연스러움'을 이유로 유지하는 것을 금지합니다.\n"
                    + "모든 플래그 문장을 교정하세요. 교정하지 않은 항목이 있으면 이 윤문은 실패입니다.\n"
                    + "changes 배열에 각 항목의 원문→수정문을 반드시 기록하세요."
                )

        return f"""당신은 AI가 생성한 한국어 정치 원고를 더 사람답고 자연스럽게 다듬는 편집자입니다.
{speaker_note}

{style_note}

{proper_noun_note}

{alias_note}

{prior_flags_note}

{fp_hint_note}

{ai_rhetoric_hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[전제 조건] "저는" 문두 비율 제한 — 모든 단계에 우선
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
한국어는 pro-drop 언어입니다. 1인칭 주어�� 70~80% 생략이 자연스럽고, 매 문장 "저는"으로 시작하면 AI가 쓴 글처럼 보입니다.

먼저 원문에서 "저는"으로 시작하는 문장 수를 세세요. 그 다음, 아래 기준에 따라 교정하세요.

"저는" 유지 조건 (삭제 금지):
  · 대조/전환 — 직전 문장 주어가 다른 사람/기관일 때: "주민들은 불편을 호소했습니다. 저는 이를 해결하겠습니다."
  · 첫 등장 — 글에서 화자가 처음 주어로 나설 때
  · 강조/책임 — 의지를 특별히 부각: "저는 이 약속을 반드시 지키겠습니다."
  · 모호성 해소 — 생략하면 주어가 불분명해질 때

"저는" 생략 조건 (삭제 권장):
  · 동일 주어 연속 — 직전 문장도 "저는"이거나 주어 생략 상태
  · 의지/다짐 — 서술어(-겠습니다)로 화자임이 자명
  · 나열/병렬 — 같은 화자의 행동 연속 열거

생략 외 분산 전략:
  (a) "저는"을 문중으로 이동 — "이번 개정이 기업 환경을 바꿀 것이라 저는 봅니다."
  (b) 주어를 사실·정책으로 전환 — "취득세 감면 조례는 지난 9월 시행에 들어갔습니다."

★ 수치 기준: 출력에서 "저는"으로 시작하는 문장 ≤ 전체의 20%. 연속 2문장 "저는" 금지. ★
이 기준을 충족하지 못하면 아래 3단계 결과물이 아무리 좋아도 실패입니다.

⚠ 동음이의 주의 — "저"가 대명사가 아닌 경우:
"저해(沮害)·저축·저장·저항·저지·저감·저하·저변·저력" 등 한자어 어두의 "저"는 1인칭 대명사가 아닙니다.
이런 단어에서 "저"만 분리하거나 뒷부분을 삭제하면 비문이 됩니다 (예: "저해하는→저", "저하되는→저").
삭제/분산 대상은 오직 문장 맨 앞의 대명사 "저는/저도/저의/저에게"뿐입니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

아래 원고를 3단계로 처리하세요.

[1단계 - 감지]
다음과 같은 AI 티 표현과 비문을 찾으세요.
- 과도한 대칭 구조와 추상적 수식
- 출처 없는 근거 호출: "객관적 지표에 따르면", "데이터를 바탕으로", "전문가들은" 등 실제 수치·인명·기관·날짜가 뒤따르지 않는 빈 수사. 삭제하고 직접 서술로 재구성.
  예: BAD "객관적 지표에 따르면, 보행 환경 개선은 상권 활성화에 긍정적인 영향을 미칩니다."
       GOOD "보행 환경이 개선된 상권은 유동인구가 늘어 매출 회복이 빠릅니다."
- 지시 관형사·연결어 남용: "이러한", "그러한", "이를 통해", "이러한 맥락에서" 가 본문 전체 3회 이상이면 절반을 구체 명사로 교체.
- 추상 포용 수사 반복: "모든 계층", "다양한 계층을 포용" 이 2회+ → 하나만 남기고 구체 대상 전환.
- ~적 접미사 남용: "혁신적", "체계적", "효과적" 이 한 문장에 3개+ → 하나를 풀어쓰거나 구체어 전환.
- AI 고빈도 수식어: "혁신적인", "체계적인", "지속적인", "종합적인" 등이 본문 전체 3회+ → 절반을 구체 서술로 교체.
- 번역체: "것은 사실이다", "에 의해", "경향이 있다" → 자연스러운 한국어로 전환.
- 과장 수사: "전환점", "패러다임", "새로운 지평" 이 일상적 대상에 쓰이면 축소.
- 과제와 전망 클리셰: "밝은 전망이 기대된다", "새로운 도약" → 구체 계획·일정으로 교체.
- 결론과 다짐 문장이 지나치게 형식적인 경우
- 연결어가 기계적으로 반복되는 경우
- 주술 불일치: 문장이 "저는"으로 시작했는데 중간에 다른 주어("~이/~가")를 끼워 넣고 그 다른 주어의 서술어("~할 것입니다")로 닫히는 경우. "저는"이 갈 곳 없이 떠 있다.
  예: BAD "저는 이러한 노력이 큰 효과를 낼 것입니다."
       GOOD "저는 이러한 노력이 큰 효과를 내리라 기대합니다."
       또는 "이러한 노력이 큰 효과를 낼 것입니다." (저는 제거)
- 속격 '의' 체인: 한 문장에 속격 조사 "의"가 3회 이상 사슬처럼 이어지는 경우. 특히 위 보호 목록의 고유명사가 "X의 Y"로 풀어써져서 "X의 Y의 Z"가 되는 경우.
  예: BAD "A의 B의 성공적인 조성" (A B가 한 고유명사)
       GOOD "A B의 성공적인 조성"
- 이중 주어: 한 절(쉼표·연결어미 없이 이어지는 덩어리) 안에 "~가/~이"가 두 번 연이어 나오고, 서술어가 동사(형용사 제외)인 경우. 주어가 둘이라 누가 주체인지 흐려진다.
  예: BAD "부천 대장지구가 기초단체장이 영업 사원을 자처하며 유치를 성사시킨 사례"
       GOOD "부천 대장지구에서는 기초단체장이 영업 사원을 자처하며 유치를 성사시킨 사례"
       또는 "부천 대장지구의 기초단체장이 영업 사원을 자처하며 유치를 성사시킨 사례"
- 추상 동작명사 모호: "활성화·완성·추진·조성·개선" 류 동작성 추상 명사를 수식 명사구 없이 조사("을/를/에")와 붙여 쓰면 무엇의 X인지 알 수 없다. 반드시 앞에 수식 명사구를 붙이거나 구체어로 치환한다.
  예: BAD "활성화에 매달려 온 저는 성공적인 완성을 꿈꾸고 있습니다."
       GOOD "계양 테크노밸리 활성화에 매달려 온 저는 이 사업의 성공적인 조성을 꿈꾸고 있습니다."
- 시점 역행: "~을 통과시켰습니다 / 시행되고 있습니다" 같이 이미 완료된 행동을 서술한 뒤, 같은 맥락에서 "~이 필요합니다 / 해야 합니다" 같은 당위 문장을 이어 붙이지 말 것. 이미 한 일은 과거·현재완료로 닫고, 앞으로 할 일만 미래형으로 이어 붙인다.
  예: BAD "조례는 본회의를 통과하여 지난 9월부터 시행되고 있습니다. 성공적인 조성을 위해 이러한 노력이 필요합니다."
       GOOD "조례는 본회의를 통과하여 지난 9월부터 시행되고 있습니다. 이번 개정이 성공적인 조성의 첫 단추가 될 것입니다."
- 주술 혼합 (능동+피동): "저는 ~을 확보하고 ~이 개선될 것이라고 생각합니다"처럼 한 문장 안에서 '저는'이 능동 동작(확보하다)과 피동 서술(개선되다)을 함께 이끄는 경우. '저는'은 자신의 판단·기대 동사(생각하다/기대하다/전망하다/봅니다)로만 닫고, 외부 변화는 분리된 절로 쓰거나 완전 피동으로 정렬한다.
  예: BAD "저는 이번 개정으로 세제 인센티브의 형평성을 확보하고 앵커기업 유치 여건도 개선될 것이라고 생각합니다."
       GOOD "이번 개정으로 세제 인센티브의 형평성이 확보되고 앵커기업 유치 여건도 개선될 것이라고 저는 봅니다."
       또는 "저는 이번 개정으로 세제 인센티브의 형평성을 바로잡고, 앵커기업 유치 여건을 개선하겠습니다."
- 명사구 스태킹: 한 구 안에서 "N1의 N2 N3 N4의 N5" 처럼 명사구를 3개 이상 연속해서 포개지 마세요. 하나는 동사/서술로, 하나는 관형절(~하는 N)로 풀어 쓰면 문장이 숨을 쉽니다.
  예: BAD "세제 인센티브를 통한 기업 유치 경쟁력 회복의 중요한 신호탄"
       GOOD "세제 인센티브로 기업 유치 경쟁력을 되살리는 중요한 신호탄"
- 지시어 역전: 직전 문장이 '문제/현실/한계/부재' 같이 부정적 상태로 닫혔는데 바로 뒤에 "이를 위해 ~해야 합니다"로 이어지면, "이를"이 문제 자체를 가리켜 논리가 뒤집힙니다. 이럴 때는 "이를 해소하려면 / 그래서 / 이러한 상황을 바꾸려면"으로 교체합니다.
  예: BAD "~은 이중 규제의 꼬리표를 달고 있는 것이 현실입니다. 이를 위해 ~을 신속히 완료해야 합니다."
       GOOD "~은 이중 규제의 꼬리표를 달고 있는 것이 현실입니다. 이 상황을 해소하려면 ~을 신속히 완료해야 합니다."
- 병렬 구조 혼합: "A와 B이/가 ~한 점"처럼 '~와/과'로 묶는 두 항목의 문법 성격이 다르면 문장이 꼬입니다. 양쪽 다 명사구(체언)로 통일하거나, 양쪽 다 관형절(~이 ~한 것)로 통일하세요.
  예: BAD "'일자리 창출' 공약 이행 실태와 '매립지 종료' 공약이 사실상 달성되지 못한 점"
       GOOD "'일자리 창출'과 '매립지 종료' 공약이 사실상 달성되지 못한 점"
       또는 "'일자리 창출' 공약 이행 실태와 '매립지 종료' 공약의 미이행"
- 어조 혼입: 한 문단 안에서 선언체("하겠습니다/기대합니다")와 당위체/평문("~것이 중요합니다 / ~할 필요가 있습니다")이 섞이지 않게 합니다. 화자의 목소리가 주된 어조라면 끝까지 그 어조로 닫고, 객관 평문이 필요하면 별도 문단으로 분리하세요.
  예: BAD "저는 ~에 최선을 다하겠습니다. 이 과제에 매진하는 것이 중요합니다."
       GOOD "저는 ~에 최선을 다하겠습니다. 이 과제에 끝까지 매진하겠습니다."
- 어휘 반복: 같은 용언의 어간(예: "갖추"의 "갖춰진/갖추기")이 한 문장 안에 2회 이상 나오면 한쪽을 유의어로 바꾸거나 구조를 바꿉니다.
  예: BAD "광역교통망이 갖춰진 자족도시의 면모를 갖추기 위해서는"
       GOOD "광역교통망이 갖춰진 자족도시로 자리 잡으려면"

[2단계 - 교정]
- 의미, 사실, 수치, 고유명사, 정치적 입장은 유지합니다.
- 문장 흐름, 연결, 호흡, 어미 반복만 더 자연스럽게 바꿉니다.
- 각 섹션(<h2> 뒤)의 첫 문장을 지시 대명사('이·그·저' 계열: 이는, 이것은, 이러한, 이와 같은, 이를 통해 등)로 시작하지 마십시오. 섹션이 바뀌면 독자는 새 주제를 기대합니다. 해당 섹션의 핵심 주어·주제어로 시작하십시오.
- 고유명사 보호 목록에 있는 이름은 어절 사이에 "의"를 넣지 말고 붙여 씁니다.
- 사용자 문체 지시가 있으면 전체 재작성 없이 일부 문장에만 반영합니다.
- 5단 구조와 HTML 형식은 유지합니다.
- "저는" 비율이 [전제 조건]의 수치 기준을 초과하면 생략·이동·전환 전략으로 줄이세요.

[3단계 - 검증]
- 수정 후에도 원문 의미가 바뀌지 않았는지 다시 확인하세요.
- 과장되거나 캐릭터화된 말투는 피하세요.
- "저는"으로 시작하는 문장 수를 세서 [전제 조건] 기준(≤20%, 연속 금지)을 충족하는지 확인하세요. 미충족 시 2단계로 돌아가세요.

[원문 제목]
{title}

[원문 본문]
{content}

반드시 다음 JSON만 반환하세요.
{{
  "content": "수정된 본문 (HTML 유지)",
  "changes": ["수정 사항 1", "수정 사항 2"]
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

        # 0. 프롬프트 누출 감지 및 제거
        # personalization_guide 의 hints 조각이 본문에 그대로 복사되는 현상 차단.
        # 문장 단위로 매칭해서, 키프레이즈를 2개 이상 포함하는 문장을 통째로 제거.
        _PROMPT_LEAK_PHRASES = [
            "신선한 관점에서",
            "따뜻하고 친근한 어조",
            "모든 계층을 포용하는 수용적 표현",
            "지역현안과 주민들의 실제 경험을 구체적으로 반영",
            "지역 용어를 사용",
            "개인적 경험과 사례를 풍부하게 포함",
            "구체적인 숫자와 데이터를 적극적으로",
            "미래 비전과 발전 방향을 제시",
            "보수보다 혁신을 강조하는 진보적 관점",
            "안정성과 전통 가치를 중시하는 보수적 관점",
            "균형잡힌 중도적 관점에서",
            "협력과 소통을 강조하는 협업적 표현",
            "격식있고 전문적인 어조",
        ]

        def _remove_leaked_sentences(html: str) -> tuple[str, int]:
            """<p> 블록 내 문장 중 프롬프트 키프레이즈를 2개+ 포함하면 제거."""
            removed = 0

            def _clean_p(m: re.Match) -> str:
                nonlocal removed
                full = m.group(0)
                inner_m = re.match(r'(<p[^>]*>)(.*?)(</p>)', full, re.DOTALL)
                if not inner_m:
                    return full
                open_tag, inner, close_tag = inner_m.groups()
                # 문장 분리
                sents = re.split(r'(?<=[.?!])\s+', inner)
                clean = []
                for s in sents:
                    hit = sum(1 for phrase in _PROMPT_LEAK_PHRASES if phrase in s)
                    if hit >= 2:
                        removed += 1
                    else:
                        clean.append(s)
                if not clean:
                    return ""  # 전체 <p> 가 누출이면 태그째 제거
                return f"{open_tag}{' '.join(clean)}{close_tag}"

            result = re.sub(r'<p[^>]*>.*?</p>', _clean_p, html, flags=re.DOTALL)
            return result, removed

        updated_content, leak_count = _remove_leaked_sentences(updated_content)
        if leak_count:
            summary.append(f"프롬프트 누출 문장 {leak_count}건 제거")

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
                # Kiwi 기반 치환 후 문법 검증 (중복 조사 탐지)
                from ..common import korean_morph
                dup_tokens = korean_morph.find_duplicate_particles(updated_content)
                if dup_tokens:  # None 이면 Kiwi 불가 → 스킵
                    summary.append(
                        f"치환 후 중복 조사 {len(dup_tokens)}건 감지 — 수동 확인 필요"
                    )

        # 1.2. 고유명사 속격 "의" 삽입 강제 치환
        # LLM이 "계양 테크노밸리" → "계양의 테크노밸리"로 풀어쓰는 것을
        # regex 로 강제 복원. HTML 태그가 끼어있어도 잡는다.
        for kw in (user_keywords or []):
            kw = str(kw).strip()
            if not kw:
                continue
            parts = kw.split()
            if len(parts) < 2:
                continue
            for i in range(len(parts) - 1):
                left = re.escape(parts[i])
                right = re.escape(" ".join(parts[i + 1:]))
                pattern = left + r'의\s*(?:<[^>]*>\s*)*' + right
                replacement = parts[i] + " " + " ".join(parts[i + 1:])
                new_content = re.sub(pattern, replacement, updated_content)
                if new_content != updated_content:
                    updated_content = new_content
                    summary.append(f"고유명사 '{kw}' 속격 분해 강제 복원")

        # 1.5. 문장 레벨 비문 스캔 (치환 여부와 무관하게 항상 수행)
        # 자동 교정은 하지 않음 — humanize 가 정확히 어느 문장인지 찾을 수 있도록
        # 문제 문장 원문을 editSummary 에 박아 전달한다. (이전 버전은 "N건" 카운트만
        # 남겨 LLM 이 위치 특정을 못하고 규칙을 무시하는 문제가 있었음.)
        from ..common import korean_morph

        def _truncate_sentence_for_flag(text: str, limit: int = 120) -> str:
            """flag 문자열에 들어갈 문장 축약. 너무 길면 말줄임."""
            stripped = (text or "").strip()
            if len(stripped) <= limit:
                return stripped
            return stripped[: limit - 1] + "…"

        plain_body = re.sub(r'<[^>]+>', ' ', updated_content)
        plain_body = re.sub(r'\s+', ' ', plain_body).strip()
        sentences = korean_morph.split_sentences(plain_body)
        if sentences:  # None 이면 Kiwi 불가 → 스킵
            for sent in sentences:
                if korean_morph.detect_subject_predicate_mismatch(sent) is True:
                    summary.append(
                        f"주술 불일치 — 다음 문장 재검토: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                chain = korean_morph.find_genitive_chain(sent, min_count=3)
                if chain:
                    summary.append(
                        f"속격 '의' 체인 3회+ — 다음 문장 축약: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                if korean_morph.detect_double_nominative(sent) is True:
                    summary.append(
                        f"이중 주어 — 다음 문장 절 분리: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                dup_stems = korean_morph.find_duplicate_stems(sent, min_count=2)
                if dup_stems:
                    stems_str = ", ".join(stem for stem, _n in dup_stems)
                    summary.append(
                        f"어간 반복('{stems_str}') — 다음 문장 유의어 교체: \"{_truncate_sentence_for_flag(sent)}\""
                    )

            # 인접 쌍: "이를 위해" 지시어 역전
            for prev_s, next_s in zip(sentences, sentences[1:]):
                if korean_morph.detect_purpose_pointer_inversion(prev_s, next_s) is True:
                    summary.append(
                        f"지시어 역전 — '이를 위해' 가 부정 상태를 받음. 직전 문장: \"{_truncate_sentence_for_flag(prev_s)}\" / 해당 문장: \"{_truncate_sentence_for_flag(next_s)}\""
                    )

        # 1.55. "저는" 문두 과다 반복 감지 (Kiwi 불필요 — regex 문장 분리)
        # Kiwi split_sentences 가 None 이어도 독립 동작해야 하므로 별도 블록.
        _fp_plain = re.sub(r'<[^>]+>', ' ', updated_content)
        _fp_plain = re.sub(r'\s+', ' ', _fp_plain).strip()
        # regex 기반 문장 분리: 마침표/물음표/느낌표 + 공백/끝 경계
        _fp_sents = [s.strip() for s in re.split(r'(?<=[.?!])\s+', _fp_plain) if len(s.strip()) > 5]
        if _fp_sents:
            _first_person_re = re.compile(r'^저는\s')
            _fp_matched = [s for s in _fp_sents if _first_person_re.match(s)]
            _fp_ratio = len(_fp_matched) / len(_fp_sents)
            if _fp_ratio >= 0.4 and len(_fp_matched) >= 4:
                examples = _fp_matched[:5]
                example_lines = " / ".join(
                    f"\"{_truncate_sentence_for_flag(s, 60)}\"" for s in examples
                )
                summary.append(
                    f"'저는' 문두 과다 반복 — 전체 {len(_fp_sents)}문장 중 {len(_fp_matched)}문장({_fp_ratio:.0%})이 '저는'으로 시작. "
                    f"예시: {example_lines}"
                )

        # 1.6. H2 섹션 첫 문장 지시어 고립 스캔
        # "이 사업/이곳/이 정책/이러한 노력" 류가 섹션 시작 위치에 오면 referent 가
        # 앞 섹션까지 거슬러 가야 해석됨 → humanize 에 경고.
        # humanize 가 무엇으로 복원할지 모호해 손대지 않던 문제를 피하려, 해당 섹션
        # H2 텍스트에서 사용자 키워드 후보를 뽑아 flag 에 명시한다.
        try:
            import re as _re
            # <h2>...</h2> + 그 뒤 첫 <p>...</p> 를 쌍으로 포착 (H2 내용 → 후보 선정에 사용)
            section_pairs = _re.findall(
                r'<h2[^>]*>(.*?)</h2>\s*(<p[^>]*>.*?</p>)',
                updated_content,
                flags=_re.DOTALL | _re.IGNORECASE,
            )
            # 두 종류 패턴:
            # (a) "이/그/저" + 사업·정책·... 류 일반명사 (referent 모호)
            # (b) "이는/이로써/이로/이를/이러한" 단독 지시어 (referent 이전 섹션까지)
            _ORPHAN_WITH_NOUN_RE = _re.compile(
                r'^\s*(?:이|그|저)\s*(?:사업|정책|조치|조례|노력|곳|것|분|때|문제|사안|사례|현상|방침|계획|성과|비전|과제|원칙|방안)'
            )
            _ORPHAN_STANDALONE_RE = _re.compile(
                r'^\s*(?:이는|이로써|이로|이를|이러한)\s'
            )

            def _pick_section_proper_noun(h2_text: str) -> str:
                """섹션 H2 에 등장하는 user_keyword 중 첫 매칭을 반환. 없으면 primary.

                우선순위:
                  1. H2 에 그대로 들어있는 user_keyword 중 첫 매칭 (가장 문맥 근거 있음)
                  2. user_keywords[0] (primary)
                  3. 빈 문자열 (user_keywords 가 없을 때)
                """
                keywords = [str(k).strip() for k in (user_keywords or []) if str(k).strip()]
                if not keywords:
                    return ""
                for kw in keywords:
                    if kw in h2_text:
                        return kw
                return keywords[0]

            for h2_inner, p_block in section_pairs:
                h2_text = _re.sub(r'<[^>]+>', ' ', h2_inner)
                h2_text = _re.sub(r'\s+', ' ', h2_text).strip()
                inner = _re.sub(r'<[^>]+>', ' ', p_block)
                inner = _re.sub(r'\s+', ' ', inner).strip()
                if _ORPHAN_WITH_NOUN_RE.match(inner) or _ORPHAN_STANDALONE_RE.match(inner):
                    quoted = inner[:120] + ('…' if len(inner) > 120 else '')
                    candidate = _pick_section_proper_noun(h2_text)
                    if candidate:
                        summary.append(
                            f"섹션 첫 문장 지시어 고립 — '{candidate}' 로 복원: \"{quoted}\""
                        )
                    else:
                        summary.append(
                            f"섹션 첫 문장 지시어 고립 — 고유명사 원형 복원: \"{quoted}\""
                        )
        except Exception:
            # 지시어 스캔은 보조 — 실패해도 파이프라인 중단하지 않음.
            pass

        # 2. 과다 키워드 강제 분산 (reduceKeywordSpam)
        # Porting strict logic: max 6 times allowed
        MAX_ALLOWED = 6
        
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
                summary.append(
                    f"키워드 과다('{keyword}' {count}회) 감지 - 문장 파손 방지를 위해 자동 치환은 수행하지 않음 ({excess}회 초과)"
                )

        # Double Transformation 은 content_processor.GRAMMATICAL_ERROR_PATTERNS 에서
        # 더 포괄적으로 처리하므로 여기서는 제거함.

        return {
            'content': updated_content,
            'title': updated_title,
            'editSummary': summary,
            'fixed': True
        }
