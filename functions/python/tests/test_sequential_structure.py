"""ENABLE_SEQUENTIAL_STRUCTURE 경로 단위 테스트.

Plan 1-2-wild-anchor.md 의 검증 항목 중 단위 테스트 가능 항목:
- (2) stage 호출 순서 — seq-outline → seq-intro → seq-body-N → seq-conclusion
- (3) prior_sections 블록 XML escape + CDATA 종결자 보호
- (5) outline 호출 실패 시 _run_sequential_structure 가 None 반환
- (6) _build_conclusion_archetype_paragraphs default branch 에 '본론에서 확인한' 문자열 없음
- (6') content_validator META_PROMPT_LEAK 패턴이 plan 에서 추가한 표현을 잡아냄
- (추가) _select_conclusion_anchor 의 body 앵커 추출 (수치+단위, 인용)

CLAUDE.md 범용성 원칙: `{user_name}` 같은 슬롯 placeholder 만 사용.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeAgent:
    """SectionRepair + Structure helper 들의 최소 인터페이스만 스텁."""

    _PRIOR_PLAIN_WS_RE = __import__('re').compile(r'\s+')
    _CDATA_TERMINATOR_RE = __import__('re').compile(r'\]\]>')

    def __init__(self):
        self.llm_calls = []  # 각 호출의 stage 기록
        self.responses = {}  # stage -> payload 매핑
        self.outline_should_fail = False

    def _plain_from_paragraphs(self, paragraphs):
        from agents.core.structure_agent import StructureAgent
        return StructureAgent._plain_from_paragraphs(self, paragraphs)

    def _build_prior_sections_block(self, completed):
        from agents.core.structure_agent import StructureAgent
        return StructureAgent._build_prior_sections_block(self, completed)


# ---------------------------------------------------------------------------
# prior_sections escaping
# ---------------------------------------------------------------------------

class TestPriorSectionsBlock:
    def test_empty_returns_empty_string(self):
        agent = _FakeAgent()
        assert agent._build_prior_sections_block([]) == ''

    def test_xml_escapes_ampersand_and_brackets(self):
        agent = _FakeAgent()
        completed = [{
            'role': 'intro',
            'heading': 'A & B <sample>',
            'paragraphs': ['첫 문단 & 특수문자 <tag>', '둘째 문단'],
        }]
        block = agent._build_prior_sections_block(completed)
        # heading 속성은 escape 된 형태로 나와야 함
        assert 'A &amp; B &lt;sample&gt;' in block
        # 본문은 CDATA 내부에 보존되며 <tag> 는 strip 되어 공백으로 치환
        assert '<![CDATA[' in block and ']]>' in block
        assert '<tag>' not in block  # HTML strip 된 후 CDATA 안에 들어감

    def test_cdata_terminator_is_neutralized(self):
        agent = _FakeAgent()
        completed = [{
            'role': 'evidence',
            'heading': '',
            'paragraphs': ['문단에 ]]> 가 포함됨'],
        }]
        block = agent._build_prior_sections_block(completed)
        # 원본 ']]>'  CDATA 종결자가 그대로 살아있으면 안 됨
        # 유일한 ]]>  최종 </section> 닫힘이어야 한다
        # 실제로는 ']]]]><![CDATA[>' 치환으로 안전해진다
        assert ']]]]><![CDATA[>' in block


# ---------------------------------------------------------------------------
# META_PROMPT_LEAK patterns
# ---------------------------------------------------------------------------

class TestMetaPromptLeakPatterns:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from agents.core.content_validator import ContentValidator
        self.validator = ContentValidator()

    @pytest.mark.parametrize("sentence", [
        "본론에서 확인한 문제를 실행으로 연결하겠습니다.",
        "서론에서 다룬 쟁점을 다시 정리하겠습니다.",
        "결론에서 살펴본 해법이 바로 이것입니다.",
        "앞서 확인한 바와 같이 구조적 문제가 있습니다.",
        "앞서 언급한 지점을 다시 짚어보겠습니다.",
        "위에서 살펴본 흐름대로 진행됩니다.",
        "위 다룬 내용을 이어받아 정리하면 다음과 같습니다.",
    ])
    def test_new_patterns_flagged(self, monkeypatch, sentence):
        monkeypatch.setenv("ENABLE_SEQUENTIAL_STRUCTURE", "true")
        leaks = self.validator._find_meta_prompt_leak_sentences(
            f"<p>{sentence}</p>"
        )
        assert sentence in leaks, f"패턴 매치 실패: {sentence}"

    @pytest.mark.parametrize("sentence", [
        "이 문제는 현장에서 오래 확인된 사안입니다.",
        "시민들이 느끼는 불편은 다양한 방식으로 드러났습니다.",
        "문제가 지속되는 이유는 제도적 공백 때문입니다.",
    ])
    def test_false_positives_not_flagged(self, monkeypatch, sentence):
        monkeypatch.setenv("ENABLE_SEQUENTIAL_STRUCTURE", "true")
        leaks = self.validator._find_meta_prompt_leak_sentences(
            f"<p>{sentence}</p>"
        )
        assert sentence not in leaks

    def test_new_patterns_disabled_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        sentence = "본론에서 확인한 문제를 실행으로 연결하겠습니다."
        leaks = self.validator._find_meta_prompt_leak_sentences(
            f"<p>{sentence}</p>"
        )
        assert sentence not in leaks


# ---------------------------------------------------------------------------
# _build_conclusion_archetype_paragraphs default branch 문구 제거
# ---------------------------------------------------------------------------

class TestConclusionDefaultFallback:
    def test_default_fallback_has_no_meta_discourse(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        from handlers.generate_posts_pkg.pipeline import (
            _build_conclusion_archetype_paragraphs,
        )
        paragraphs = _build_conclusion_archetype_paragraphs(
            writing_method="",  # 빈 writing_method → default branch
            category="",
            heading="",
            body_text="<p>샘플 본론입니다.</p>",
            user_keywords=[],
            full_name="{user_name}",
        )
        joined = " ".join(paragraphs)
        forbidden = [
            "본론에서 확인한 문제",
            "앞서 살펴본",
            "위에서 다룬",
            "서론에서 언급한",
            "결론에서 제기한",
        ]
        for phrase in forbidden:
            assert phrase not in joined, f"default fallback 에 금지 문구 잔존: {phrase}"

    def test_default_fallback_uses_body_anchors_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        from handlers.generate_posts_pkg.pipeline import (
            _build_conclusion_archetype_paragraphs,
        )
        paragraphs = _build_conclusion_archetype_paragraphs(
            writing_method="logical_writing",
            category="정책 및 비전",
            heading="",
            body_text="<p>샘플 정책은 캐시백 요율과 발행 규모를 함께 점검해야 합니다. 소상공인 매출도 확인해야 합니다.</p>",
            user_keywords=["샘플 정책"],
            full_name="{user_name}",
        )
        joined = " ".join(paragraphs)
        assert "샘플 정책" in joined
        assert "캐시백 요율" in joined or "발행 규모" in joined
        assert "본론에서 확인한 문제" not in joined


# ---------------------------------------------------------------------------
# _select_conclusion_anchor body 앵커 추출
# ---------------------------------------------------------------------------

class TestSelectConclusionAnchor:
    def test_user_keyword_priority(self):
        from handlers.generate_posts_pkg.pipeline import _select_conclusion_anchor
        anchor = _select_conclusion_anchor(
            "<p>샘플 정책이 본문에 등장합니다.</p>",
            user_keywords=["샘플 정책"],
            full_name="{user_name}",
        )
        assert anchor == "샘플 정책"

    def test_falls_back_to_number_unit(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        from handlers.generate_posts_pkg.pipeline import _select_conclusion_anchor
        anchor = _select_conclusion_anchor(
            "<p>예산 300억원이 집행될 예정입니다.</p>",
            user_keywords=[],
            full_name="{user_name}",
        )
        # 300억원 혹은 공백을 포함한 변형
        compact = anchor.replace(" ", "")
        assert "300억원" in compact

    def test_falls_back_to_quoted_proper_noun(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        from handlers.generate_posts_pkg.pipeline import _select_conclusion_anchor
        anchor = _select_conclusion_anchor(
            '<p>이 사업은 "샘플 특구" 지정을 포함합니다.</p>',
            user_keywords=[],
            full_name="{user_name}",
        )
        assert anchor == "샘플 특구"

    def test_body_anchor_fallback_available_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEQUENTIAL_STRUCTURE", raising=False)
        from handlers.generate_posts_pkg.pipeline import _select_conclusion_anchor
        anchor = _select_conclusion_anchor(
            "<p>예산 300억원과 \"샘플 특구\"가 함께 등장합니다.</p>",
            user_keywords=[],
            full_name="{user_name}",
        )
        assert anchor == "샘플 특구"

    def test_final_fallback_when_no_anchor(self):
        from handlers.generate_posts_pkg.pipeline import _select_conclusion_anchor
        anchor = _select_conclusion_anchor(
            "<p>추상적인 본문 텍스트입니다.</p>",
            user_keywords=[],
            full_name="{user_name}",
        )
        assert anchor == "이 과제"


# ---------------------------------------------------------------------------
# _run_sequential_structure: stage 호출 순서 + outline 실패 시 None 반환
# ---------------------------------------------------------------------------

class _MockRunner:
    """SectionRepairMixin._run_sequential_structure 단위 호출용 최소 스텁.

    - call_llm_json_contract 를 stage 기반 dict 로 대체
    - outline/intro/body/conclusion 응답을 준비해 순차 호출 순서를 기록
    """

    def __init__(self, *, outline_body_count=3, outline_fail=False):
        self.calls = []
        self.generate_requests = []
        self.outline_fail = outline_fail
        self.outline_body_count = outline_body_count

    def _validate_outline_lead_sentences(self, outline, *, writing_method=''):
        return []

    def _validate_outline_roles(self, outline, *, writing_method=''):
        return []

    def _build_outline_json_prompt(self, *, prompt, length_spec, writing_method=''):
        return "OUTLINE_PROMPT"

    def _build_outline_json_schema(self, length_spec, *, writing_method=''):
        return {"type": "object"}

    async def call_llm_json_contract(
        self, prompt, *, response_schema, required_keys, stage, max_output_tokens,
    ):
        self.calls.append(stage)
        if stage == "seq-outline":
            if self.outline_fail:
                raise RuntimeError("outline 강제 실패")
            body = [
                {
                    "heading": f"섹션 {i+1}",
                    "lead_sentence": f"섹션 {i+1}의 핵심 행동을 추진하겠습니다.",
                    "role": "evidence" if i < self.outline_body_count - 2
                             else ("counterargument_rebuttal" if i == self.outline_body_count - 2
                                   else "higher_principle"),
                }
                for i in range(self.outline_body_count)
            ]
            return {
                "title": "샘플 제목",
                "intro_lead": "안녕하세요, {user_name} 의원입니다. 샘플 정책을 추진하겠습니다.",
                "body": body,
                "conclusion_heading": "마치며",
            }
        # intro/body/conclusion 모두 paragraphs 반환
        return {
            "paragraphs": [
                "첫 문단 " + "가" * 100,
                "둘째 문단 " + "나" * 100,
                "셋째 문단 " + "다" * 100,
            ]
        }

    async def generate_section(
        self, *, role, heading, lead_sentence, prior_sections, base_prompt,
        length_spec, writing_method, stage, section_order, body_total,
        topic, instructions, user_keywords,
    ):
        # 실제 generate_section 호출 흔적을 stage 로 남긴다
        self.calls.append(stage)
        self.generate_requests.append({
            "stage": stage,
            "role": role,
            "heading": heading,
            "prior_roles": [sec.get("role") for sec in prior_sections],
        })
        return [
            f"{role} 섹션 첫 문단 " + "가" * 100,
            f"{role} 섹션 둘째 문단 " + "나" * 100,
            f"{role} 섹션 셋째 문단 " + "다" * 100,
        ]


class TestRunSequentialStructure:
    def _make_runner(self, **kwargs):
        from agents.core.section_repair import SectionRepairMixin
        # _MockRunner 에 SectionRepairMixin._run_sequential_structure 만 붙인 인스턴스
        runner = _MockRunner(**kwargs)
        runner._run_sequential_structure = SectionRepairMixin._run_sequential_structure.__get__(
            runner, type(runner)
        )
        runner._regenerate_sequential_payload_section = SectionRepairMixin._regenerate_sequential_payload_section.__get__(
            runner, type(runner)
        )
        return runner

    def test_stage_call_order_for_three_body_sections(self):
        runner = self._make_runner(outline_body_count=3)
        payload = asyncio.new_event_loop().run_until_complete(
            runner._run_sequential_structure(
                is_aeo=True,
                writing_method='logical_writing',
                current_prompt='BASE_PROMPT',
                length_spec={'body_sections': 3, 'per_section_min': 300, 'paragraphs_per_section': 3},
                topic='샘플 주제',
                source_instructions='샘플 입장문',
                user_keywords=['샘플'],
            )
        )
        assert payload is not None
        # 정확한 호출 순서 확인
        assert runner.calls == [
            'seq-outline',
            'seq-intro',
            'seq-body-1',
            'seq-body-2',
            'seq-body-3',
            'seq-conclusion',
        ]
        # payload shape 검증
        assert payload['title'] == '샘플 제목'
        assert len(payload['body']) == 3
        assert 'paragraphs' in payload['intro']
        assert 'paragraphs' in payload['conclusion']

    def test_outline_failure_returns_none(self):
        runner = self._make_runner(outline_fail=True)
        payload = asyncio.new_event_loop().run_until_complete(
            runner._run_sequential_structure(
                is_aeo=True,
                writing_method='logical_writing',
                current_prompt='BASE_PROMPT',
                length_spec={'body_sections': 3, 'per_section_min': 300, 'paragraphs_per_section': 3},
                topic='샘플 주제',
                source_instructions='샘플 입장문',
                user_keywords=[],
            )
        )
        assert payload is None
        # outline 호출만 기록되고 intro/body/conclusion 은 호출되지 않았어야 함
        assert runner.calls == ['seq-outline']

    def test_validator_failure_regenerates_only_failed_body_section(self):
        runner = self._make_runner()
        payload = {
            "title": "샘플 제목",
            "intro": {"paragraphs": ["서론 문단"]},
            "body": [
                {"heading": "섹션 1", "paragraphs": ["본문 1"]},
                {"heading": "섹션 2", "paragraphs": ["본문 2"]},
                {"heading": "섹션 3", "paragraphs": ["본문 3"]},
            ],
            "conclusion": {"heading": "마치며", "paragraphs": ["결론 문단"]},
        }
        outline = {
            "body": [
                {"heading": "섹션 1", "lead_sentence": "첫째를 추진하겠습니다.", "role": "evidence"},
                {"heading": "섹션 2", "lead_sentence": "둘째를 추진하겠습니다.", "role": "counterargument_rebuttal"},
                {"heading": "섹션 3", "lead_sentence": "셋째를 추진하겠습니다.", "role": "higher_principle"},
            ],
            "conclusion_heading": "마치며",
        }
        repaired = asyncio.new_event_loop().run_until_complete(
            runner._regenerate_sequential_payload_section(
                payload=payload,
                outline=outline,
                validation={"code": "SECTION_LENGTH", "sectionIndex": 3},
                current_prompt="BASE_PROMPT",
                length_spec={"body_sections": 3, "per_section_min": 300, "paragraphs_per_section": 3},
                writing_method="logical_writing",
                topic="샘플 주제",
                source_instructions="샘플 입장문",
                user_keywords=["샘플"],
            )
        )
        assert repaired is not None
        assert runner.calls == ["seq-repair-body-2"]
        assert runner.generate_requests[-1]["prior_roles"] == ["intro", "evidence"]
        assert repaired["body"][0]["paragraphs"] == ["본문 1"]
        assert repaired["body"][1]["paragraphs"][0].startswith("counterargument_rebuttal 섹션")

    def test_meta_prompt_leak_regenerates_conclusion_when_section_unknown(self):
        runner = self._make_runner()
        payload = {
            "title": "샘플 제목",
            "intro": {"paragraphs": ["서론 문단"]},
            "body": [{"heading": "섹션 1", "paragraphs": ["본문 1"]}],
            "conclusion": {"heading": "마치며", "paragraphs": ["결론 문단"]},
        }
        outline = {
            "body": [
                {"heading": "섹션 1", "lead_sentence": "첫째를 추진하겠습니다.", "role": "evidence"},
            ],
            "conclusion_heading": "마치며",
        }
        repaired = asyncio.new_event_loop().run_until_complete(
            runner._regenerate_sequential_payload_section(
                payload=payload,
                outline=outline,
                validation={"code": "META_PROMPT_LEAK"},
                current_prompt="BASE_PROMPT",
                length_spec={"body_sections": 1, "per_section_min": 300, "paragraphs_per_section": 3},
                writing_method="logical_writing",
                topic="샘플 주제",
                source_instructions="샘플 입장문",
                user_keywords=[],
            )
        )
        assert repaired is not None
        assert runner.calls == ["seq-repair-conclusion"]
        assert runner.generate_requests[-1]["prior_roles"] == ["intro", "evidence"]
        assert repaired["conclusion"]["paragraphs"][0].startswith("conclusion 섹션")
