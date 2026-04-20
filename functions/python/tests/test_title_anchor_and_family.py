"""제목 파이프라인 복합 패널티 수정 회귀 테스트.

대상 변경:
- title_hook_quality._slot_token_used_in_title: compact + stem stripping 으로
  "테크노밸리 사업" → stem "테크노밸리" 가 제목 substring 에 매칭.
- title_scoring._assess_body_anchor_coverage: _slot_token_used_in_title 사용.
- title_keywords._topic_keyword_matches_text: stem fallback 추가.
- title_common.detect_content_type / select_title_family: 질문 톤이 법률 어휘보다 우선.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.common.title_common import select_title_family, detect_content_type
from agents.common.title_scoring import _assess_body_anchor_coverage
from agents.common.title_hook_quality import _slot_token_used_in_title
from agents.common.title_keywords import _topic_keyword_matches_text


# ---------------------------------------------------------------------------
# _slot_token_used_in_title — stem stripping
# ---------------------------------------------------------------------------

def test_slot_stem_strips_policy_suffix():
    """'테크노밸리 사업' stem '테크노밸리' 가 제목에 매칭."""
    assert _slot_token_used_in_title(
        "계양 테크노밸리, 2단계 지정 왜 늦어지나?",
        "테크노밸리 사업",
    )


def test_slot_stem_strips_institution_suffix():
    """'주민참여예산시민위원회' stem '주민참여예산시민' 이 제목에 매칭."""
    assert _slot_token_used_in_title(
        "주민참여예산시민 제도 안내",
        "주민참여예산시민위원회",
    )


def test_slot_exact_match_still_works():
    """접미사 없는 토큰은 그대로 exact substring 매칭."""
    assert _slot_token_used_in_title("서울시의회 의정보고", "서울시의회")


def test_slot_no_false_positive_on_short_stem():
    """stem 이 2자 미만이면 매칭하지 않음."""
    assert not _slot_token_used_in_title("아무 제목", "가사업")


def test_slot_compact_ignores_whitespace():
    """토큰과 제목 모두 공백 제거 후 비교."""
    assert _slot_token_used_in_title(
        "취득세 감면 조례 개정",
        "취득세감면조례",
    )


# ---------------------------------------------------------------------------
# _topic_keyword_matches_text — stem fallback
# ---------------------------------------------------------------------------

def test_topic_keyword_stem_fallback():
    """compact match 실패해도 stem fallback 이 잡아준다."""
    assert _topic_keyword_matches_text(
        "테크노밸리사업",
        "계양 테크노밸리, 2단계 지정",
    )


def test_topic_keyword_exact_match_still_works():
    assert _topic_keyword_matches_text("계양", "계양 테크노밸리")


# ---------------------------------------------------------------------------
# _assess_body_anchor_coverage — _slot_token_used_in_title 사용
# ---------------------------------------------------------------------------

def test_body_anchor_stem_matching_passes():
    """policy 토큰 '테크노밸리 사업' 이 stem 으로 제목에 매칭 성공.

    body-exclusive 후보가 최소 1개 존재해야 gate 가 작동하므로,
    institution 에 topic/stanceText 에 없는 고유 토큰을 추가한다.
    """
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": ["샘플구청"],
            "policy": ["샘플밸리 사업"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {
            "topic": "샘플 샘플밸리 2단계",
            "contentPreview": "샘플구청 주관 샘플밸리 사업 추진",
        }
        result = _assess_body_anchor_coverage(
            "샘플 샘플밸리, 2단계 지정 왜 늦어지나?", params
        )
        assert result.get("passed") is True, f"결과: {result}"
        assert "policy" in (result.get("hitBuckets") or [])
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_exact_token_still_works():
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": ["서울시의회"],
            "policy": [],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {"topic": "지역 현안", "contentPreview": "..."}
        result = _assess_body_anchor_coverage(
            "서울시의회 의정보고, 주민과의 약속", params
        )
        assert result.get("passed") is True
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_fails_when_no_match():
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": [],
            "policy": ["기본소득 확대"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {"topic": "다른 주제", "contentPreview": "..."}
        result = _assess_body_anchor_coverage("아주 일반적인 제목입니다", params)
        assert result.get("passed") is False
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


# ---------------------------------------------------------------------------
# Family classifier — 질문 톤이 법률 어휘보다 우선
# ---------------------------------------------------------------------------

def test_question_tone_prevents_expert_knowledge_prior():
    """질문 + 법률 어휘 → detect_content_type 이 EXPERT_KNOWLEDGE 안 돼야."""
    content = "조례 개정이 필요하다. 왜 지금 추진해야 하는가?"
    result = detect_content_type(content, "daily-communication")
    assert result != "EXPERT_KNOWLEDGE", f"질문 톤인데 EXPERT_KNOWLEDGE 반환: {result}"


def test_question_tone_demotes_legal_boost():
    """질문형 source 에 법률 어휘 있어도 EXPERT_KNOWLEDGE 가 낮게 부스트."""
    params = {
        "topic": "테크노밸리 2단계 지정, 왜 늦어지나?",
        "stanceText": (
            "시의회와 함께 조례 개정도 뒷받침해야 합니다. "
            "이 제도를 왜 미루는 것인가? 어떻게 해결할 것인가?"
        ),
        "contentPreview": "",
        "category": "daily-communication",
    }
    result = select_title_family(params)
    expert_score = result["scores"].get("EXPERT_KNOWLEDGE", 0)
    question_score = result["scores"].get("QUESTION_ANSWER", 0)
    assert question_score > expert_score, (
        f"QUESTION_ANSWER={question_score} > EXPERT_KNOWLEDGE={expert_score} 여야 함. "
        f"scores={result['scores']}"
    )


def test_dominant_legal_no_question_still_expert():
    """질문 없이 법률 용어 3회+ → 여전히 EXPERT_KNOWLEDGE +6."""
    params = {
        "topic": "조례 개정안 발의",
        "stanceText": "이번 조례 개정안은 제도 개선을 위한 법률 정비다. 법안 통과를 목표로 한다.",
        "category": "policy-proposal",
    }
    result = select_title_family(params)
    expert_reasons = result["reasons"].get("EXPERT_KNOWLEDGE", [])
    assert any("주요" in r for r in expert_reasons), (
        f"기대: 주요 배지. reasons={expert_reasons}"
    )
    assert result["scores"].get("EXPERT_KNOWLEDGE", 0) >= 6


def test_incidental_legal_no_question_gets_minor_boost():
    """질문 없고 법률 1회 + 다짐형 다수 → 부수 +2."""
    params = {
        "topic": "숙원 사업 완성",
        "stanceText": (
            "저는 앞장서서 추진하겠습니다. 조례도 뒷받침하고, "
            "약속을 지키며 완성해 나가겠습니다."
        ),
        "contentPreview": "",
        "category": "daily-communication",
    }
    result = select_title_family(params)
    expert_reasons = result["reasons"].get("EXPERT_KNOWLEDGE", [])
    assert any("부수" in r for r in expert_reasons), (
        f"기대: 부수 배지. reasons={expert_reasons}"
    )


# ---------------------------------------------------------------------------
# body-exclusive anchor — topic/stance 에는 없고 본문에서만 발견된 토큰을
# LLM 이 실제로 제목에 쓰도록 유도하기 위한 판정/가산 로직
# ---------------------------------------------------------------------------

def test_body_exclusive_detection_true():
    """topic 에 없는 구체 정책명은 body-exclusive."""
    from agents.common.title_hook_quality import _is_body_exclusive

    assert _is_body_exclusive(
        "도시첨단산업단지 2단계 지정",
        topic="샘플구 특화지구 2단계",
        stance="",
    ) is True


def test_body_exclusive_topic_shared_false():
    """topic 에 이미 있는 단어는 body-exclusive 아님."""
    from agents.common.title_hook_quality import _is_body_exclusive

    assert _is_body_exclusive(
        "특화지구",
        topic="샘플구 특화지구",
        stance="",
    ) is False


def test_body_exclusive_stem_strip_matches_topic():
    """stem stripping: 접미사 확장형은 topic stem 에 먹혀 body-exclusive 아님."""
    from agents.common.title_hook_quality import _is_body_exclusive

    # "특화지구 사업" 은 stem "특화지구" 가 topic 에 있음 → 본문 전용이 아님
    assert _is_body_exclusive(
        "특화지구 사업",
        topic="특화지구",
        stance="",
    ) is False


def test_body_exclusive_empty_reference_returns_true():
    """topic/stance 모두 비면 기본 exclusive."""
    from agents.common.title_hook_quality import _is_body_exclusive

    assert _is_body_exclusive("고유정책명", topic="", stance="") is True


def test_body_anchor_coverage_reports_exclusive_hits():
    """fake slot 주입 — 제목이 body-exclusive 토큰 인용 시 bodyExclusiveHits 에 포함."""
    from agents.common import title_hook_quality as thq

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        # 두 토큰 모두 policy bucket — 하나는 topic 공유, 하나는 본문 전용
        return {
            "region": [],
            "institution": [],
            "policy": ["도시첨단산업단지 2단계 지정", "특화지구"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {
            "topic": "샘플구 특화지구 2단계",
            "stanceText": "",
            "contentPreview": "...",
        }

        # 1) body-exclusive 토큰만 인용한 제목
        result_exclusive = _assess_body_anchor_coverage(
            "샘플구 도시첨단산업단지 2단계 지정을 완성합니다", params
        )
        assert result_exclusive.get("passed") is True
        assert "도시첨단산업단지 2단계 지정" in (
            result_exclusive.get("bodyExclusiveHits") or []
        )

        # 2) topic 공유 토큰만 인용한 제목 → bodyExclusiveHits 는 비어야 함
        result_shared = _assess_body_anchor_coverage(
            "샘플구 특화지구 2단계 완성", params
        )
        assert result_shared.get("passed") is True
        assert not (result_shared.get("bodyExclusiveHits") or [])
        # 후보는 존재하므로 hasBodyExclusiveAvailable 은 True
        assert result_shared.get("hasBodyExclusiveAvailable") is True
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_body_anchor_strength_bonus_for_exclusive():
    """동일 policy bucket 이어도 body-exclusive 토큰 인용 시 +6점 우위."""
    from agents.common import title_hook_quality as thq
    from agents.common.title_scoring import calculate_title_quality_score

    original = thq.extract_slot_opportunities

    def fake_extract(topic, content_preview, params):
        return {
            "region": [],
            "institution": [],
            "policy": ["도시첨단산업단지 2단계 지정", "특화지구"],
            "numeric": [],
            "year": [],
        }

    thq.extract_slot_opportunities = fake_extract  # type: ignore
    try:
        params = {
            "topic": "샘플구 특화지구 2단계",
            "stanceText": "",
            "contentPreview": "...본문에 도시첨단산업단지 2단계 지정이 나옵니다...",
            "fullName": "홍길동",
        }

        # A: topic 공유 토큰만 인용 (body-exclusive 0)
        score_a = calculate_title_quality_score(
            "샘플구 특화지구, 홍길동이 2단계 완성을 책임집니다", params
        )
        # B: body-exclusive 토큰까지 인용
        score_b = calculate_title_quality_score(
            "샘플구, 홍길동이 도시첨단산업단지 2단계 지정을 완성합니다", params
        )

        anchor_a = (score_a.get("breakdown") or {}).get("bodyAnchorStrength") or {}
        anchor_b = (score_b.get("breakdown") or {}).get("bodyAnchorStrength") or {}

        assert anchor_a.get("score", 0) + 6 <= anchor_b.get("score", 0), (
            f"기대: B.score >= A.score + 6. a={anchor_a}, b={anchor_b}"
        )
        # B 는 bodyExclusiveHits 가 비어 있지 않아야 함
        assert anchor_b.get("bodyExclusiveHits"), f"B 에 exclusive hit 없음: {anchor_b}"
    finally:
        thq.extract_slot_opportunities = original  # type: ignore


def test_render_slot_block_marks_body_exclusive():
    """render_slot_opportunities_block 출력에 body_exclusive='true' 속성이 등장.

    본문에만 있는 policy 접미사("사업" / "조례") 토큰이 있으면 body_exclusive 로
    분류돼 <item> 에 속성이 달려야 한다.
    """
    from agents.common.title_hook_quality import (
        extract_slot_opportunities,
        render_slot_opportunities_block,
    )

    # topic 은 일반 문구, 본문엔 policy 접미사를 가진 고유명이 등장
    params = {"regionLocal": "샘플구"}
    opps = extract_slot_opportunities(
        topic="샘플구 2단계 추진 의지",
        content=(
            "체육문화센터 건립 사업을 속도 있게 추진하겠다. "
            "취득세 감면 조례 개정도 함께 발의한다."
        ),
        params=params,
    )
    # _bodyExclusive 메타가 dict 에 있어야 함
    meta = opps.get("_bodyExclusive")
    assert isinstance(meta, dict)
    # policy bucket 에 body-exclusive 토큰이 하나 이상 있어야 함
    assert meta.get("policy"), f"policy body-exclusive 없음: opps={opps}"

    xml = render_slot_opportunities_block(opps)
    assert 'body_exclusive="true"' in xml, f"body_exclusive 속성 없음:\n{xml}"


# ---------------------------------------------------------------------------
# ① 시설·인프라 고유명 coverage 확장
#   - 산업단지/산단/테크노밸리/캠퍼스/타운/특화지구 → institution bucket
#   - 역명(2~3자 + 역), 다만 지역/광역/전역 같은 일반어는 배제
# ---------------------------------------------------------------------------


def test_institution_bucket_captures_industrial_complex():
    """본문의 '도시첨단산업단지'·'마곡산단' 이 institution bucket 에 잡힌다."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = (
        "경기 부천 대장지구나 서울 마곡산단에 비해 발전 속도가 더디다. "
        "도시첨단산업단지 2단계 지정을 신속히 완료하겠습니다."
    )
    opps = extract_slot_opportunities(
        topic="샘플구 특화지구 2단계",
        content=content,
        params={"regionLocal": "샘플구"},
    )
    institutions = opps.get("institution") or []
    assert "마곡산단" in institutions, f"마곡산단 누락: {institutions}"
    assert "도시첨단산업단지" in institutions, f"도시첨단산업단지 누락: {institutions}"


def test_institution_bucket_captures_station_names():
    """본문의 '박촌역', '계양역' 이 institution bucket 에 잡힌다."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = "박촌역 직결과 계양역 연결 등 여러 노선 검토가 이루어지고 있다."
    opps = extract_slot_opportunities(
        topic="광역교통망 확충",
        content=content,
        params={"regionLocal": "샘플구"},
    )
    institutions = opps.get("institution") or []
    assert "박촌역" in institutions, f"박촌역 누락: {institutions}"
    assert "계양역" in institutions, f"계양역 누락: {institutions}"


def test_institution_bucket_rejects_general_area_words():
    """'공업지역', '수도권', '지역' 같은 일반어는 institution 에 들어가지 않는다."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = (
        "인천 내 공업지역 물량 재배치를 통한 도시첨단산업단지 2단계 지정이 "
        "시급하다. 수도권 마지막 노른자 땅이다."
    )
    opps = extract_slot_opportunities(
        topic="샘플구 2단계",
        content=content,
        params={"regionLocal": "샘플구"},
    )
    institutions = opps.get("institution") or []
    for forbidden in ("공업지역", "지역", "수도권", "광역"):
        assert forbidden not in institutions, (
            f"일반어 '{forbidden}' 가 institution 에 섞임: {institutions}"
        )


def test_region_bucket_rejects_particle_form():
    """'~에도' 보조사 결합형이 region 에 잡히지 않는다."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = (
        "인재 양성과 유치에도 힘쓸 것입니다. 조성에도 속도를 내겠습니다."
    )
    opps = extract_slot_opportunities(
        topic="샘플구 2단계",
        content=content,
        params={"regionLocal": "샘플구"},
    )
    region = opps.get("region") or []
    for forbidden in ("유치에도", "조성에도", "추진에도"):
        assert forbidden not in region, f"조사형 '{forbidden}' 가 region 에 섞임: {region}"


# ---------------------------------------------------------------------------
# ③ stem stripping — 기초 행정구역 접미
# ---------------------------------------------------------------------------


def test_slot_stem_strips_admin_suffix_gu():
    """'계양구' stem '계양' 이 제목에 매칭된다."""
    from agents.common.title_hook_quality import _slot_token_used_in_title

    assert _slot_token_used_in_title("계양 테크노밸리 2단계", "계양구")


def test_slot_stem_strips_admin_suffix_keeps_two_char_guard():
    """len(stem) >= 2 가드로 '구' 같은 1자 stem 은 매칭 안 됨."""
    from agents.common.title_hook_quality import _slot_token_used_in_title

    # "연구" 는 stem "연" (1자) 이라 매칭 실패해야 한다.
    assert not _slot_token_used_in_title("연 보고서", "연구")


def test_topic_keyword_stem_strips_admin_suffix():
    """_topic_keyword_matches_text 도 admin suffix stem fallback 작동."""
    from agents.common.title_keywords import _topic_keyword_matches_text

    # 제목 "계양 테크노밸리" 가 topic 키워드 "계양구" 에 stem 매칭돼야 함.
    assert _topic_keyword_matches_text("계양구", "계양 테크노밸리 2단계")


def test_topic_keyword_kiwi_morph_fallback(monkeypatch):
    """형태소 기반 fallback 으로 띄어쓰기/조사 변형을 흡수한다."""
    from agents.common import korean_morph
    from agents.common.title_keywords import _topic_keyword_matches_text

    monkeypatch.setattr(
        korean_morph,
        "matches_content_keyword",
        lambda keyword, text: keyword == "청년정책" and "청년을 위한 정책" in text,
    )
    assert _topic_keyword_matches_text("청년정책", "청년을 위한 정책 설명회")


# ---------------------------------------------------------------------------
# ② allowDegradedPass — soft 점수 미달이어도 하드 게이트 통과한 best_result 반환
# ---------------------------------------------------------------------------


def test_generate_and_validate_title_degraded_pass_returns_best():
    """min_score 미달이어도 allowDegradedPass=True 면 best_result 반환."""
    import asyncio
    from agents.common import title_generation as tg

    # generate_fn 은 단순히 정해진 제목 반환.
    fake_title = "샘플구 도시첨단산업단지 2단계 지정 완성"

    async def fake_generate_fn(prompt: str) -> str:
        return fake_title

    # calculate_title_quality_score 가 아래 점수/결과 반환하도록 stub.
    original_score = tg.calculate_title_quality_score

    def fake_score(title, params, options=None):
        # 하드 게이트 통과(score>0) + soft 점수 min_score 미달
        return {
            "score": 50,
            "rawScore": 60,
            "maxScore": 120,
            "passed": False,
            "breakdown": {
                "bodyAnchorCoverage": {"score": 100, "max": 100, "status": "OK"},
                "topicMatch": {"score": 5, "max": 25, "status": "낮음"},
            },
            "suggestions": ["topicMatch 낮음"],
        }

    tg.calculate_title_quality_score = fake_score  # type: ignore
    try:
        params = {
            "topic": "샘플구 2단계",
            "contentPreview": "...도시첨단산업단지 2단계 지정 본문...",
            "fullName": "홍길동",
        }
        # allowDegradedPass=True — 예외 대신 best_result 반환해야 함.
        result = asyncio.run(
            tg.generate_and_validate_title(
                fake_generate_fn,
                params,
                options={
                    "minScore": 70,
                    "maxAttempts": 1,
                    "candidateCount": 1,
                    "allowDegradedPass": True,
                    "allowAutoRepair": False,
                },
            )
        )
        assert result.get("degradedPass") is True, f"degradedPass flag 누락: {result}"
        assert result.get("passed") is False
        assert result.get("title") == fake_title
        assert int(result.get("score") or 0) < 70
    finally:
        tg.calculate_title_quality_score = original_score  # type: ignore


def test_generate_and_validate_title_degraded_pass_off_raises():
    """allowDegradedPass=False (기본) 면 기존대로 RuntimeError 발생."""
    import asyncio
    import pytest
    from agents.common import title_generation as tg

    async def fake_generate_fn(prompt: str) -> str:
        return "샘플구 도시첨단산업단지 2단계 지정 완성"

    original_score = tg.calculate_title_quality_score

    def fake_score(title, params, options=None):
        return {
            "score": 50,
            "rawScore": 60,
            "maxScore": 120,
            "passed": False,
            "breakdown": {
                "bodyAnchorCoverage": {"score": 100, "max": 100, "status": "OK"},
            },
            "suggestions": ["low"],
        }

    tg.calculate_title_quality_score = fake_score  # type: ignore
    try:
        params = {
            "topic": "샘플구 2단계",
            "contentPreview": "...",
            "fullName": "홍길동",
        }
        with pytest.raises(RuntimeError, match="최소 점수"):
            asyncio.run(
                tg.generate_and_validate_title(
                    fake_generate_fn,
                    params,
                    options={
                        "minScore": 70,
                        "maxAttempts": 1,
                        "candidateCount": 1,
                        "allowDegradedPass": False,
                        "allowAutoRepair": False,
                    },
                )
            )
    finally:
        tg.calculate_title_quality_score = original_score  # type: ignore


# ---------------------------------------------------------------------------
# Phase 1 — source_tone_analysis 블록이 build_title_prompt 에 주입되는지
# ---------------------------------------------------------------------------

def test_build_title_prompt_emits_source_tone_analysis_block():
    """일반 제목 경로에서 source_tone_analysis 블록이 프롬프트 상단에 등장한다."""
    from agents.common.title_generation import build_title_prompt

    prompt = build_title_prompt({
        "topic": "샘플구 샘플사업 2단계",
        "contentPreview": "샘플구의 샘플사업 2단계 지정이 예정됐습니다. 책임지고 완성하겠습니다.",
        "fullName": "홍길동",
        "userKeywords": ["샘플구"],
    })

    assert "<source_tone_analysis" in prompt, "source_tone_analysis 오프닝 태그 누락"
    assert "</source_tone_analysis>" in prompt, "source_tone_analysis 클로징 태그 누락"
    for tone_id in ("pledge", "report", "question", "commentary", "hybrid"):
        assert f'id="{tone_id}"' in prompt, f"톤 id={tone_id} 블록 누락"
    assert "sourceTone" in prompt, "sourceTone 필드 지시 누락"
    assert "sourceToneReason" in prompt, "sourceToneReason 필드 지시 누락"


def test_build_title_prompt_source_tone_block_precedes_objective():
    """source_tone_analysis 는 objective 보다 먼저 등장해야 LLM 이 톤 판정을 먼저 한다."""
    from agents.common.title_generation import build_title_prompt

    prompt = build_title_prompt({
        "topic": "샘플구 정책 브리핑",
        "contentPreview": "샘플구 정책 브리핑 본문입니다.",
        "fullName": "홍길동",
    })

    tone_idx = prompt.find("<source_tone_analysis")
    obj_idx = prompt.find("<objective>")
    assert tone_idx != -1 and obj_idx != -1, "블록 중 하나가 없음"
    assert tone_idx < obj_idx, (
        "source_tone_analysis 는 objective 블록보다 먼저 배치돼야 한다 "
        f"(tone_idx={tone_idx}, obj_idx={obj_idx})"
    )


def test_title_response_schema_includes_source_tone_fields():
    """TITLE_RESPONSE_SCHEMA 에 sourceTone/sourceToneReason 가 선택 필드로 포함된다."""
    from agents.core.title_agent import TITLE_RESPONSE_SCHEMA

    props = TITLE_RESPONSE_SCHEMA.get("properties") or {}
    assert "sourceTone" in props
    assert "sourceToneReason" in props
    # 기존 응답 호환성: required 에서 제외돼 있어야 한다.
    required = set(TITLE_RESPONSE_SCHEMA.get("required") or [])
    assert "sourceTone" not in required
    assert "sourceToneReason" not in required
    assert "title" in required


# ── Archetype ending constraint tests ──────────────────────────────


def test_archetype_constraint_block_rendered_for_slogan():
    from agents.common.title_prompt_parts import build_archetype_constraint_block

    block = build_archetype_constraint_block('SLOGAN_COMMITMENT')
    assert '<archetype_ending_constraint' in block
    assert 'family="SLOGAN_COMMITMENT"' in block
    assert '질문' in block or 'forbidden' in block


def test_archetype_constraint_block_empty_for_unknown():
    from agents.common.title_prompt_parts import build_archetype_constraint_block

    assert build_archetype_constraint_block('NONEXISTENT') == ''


def test_archetype_constraint_block_in_prompt():
    from agents.common.title_generation import build_title_prompt

    prompt = build_title_prompt({
        "topic": "샘플구 시민 약속",
        "contentPreview": "샘플구 시민 여러분께 약속드리겠습니다.",
        "fullName": "홍길동",
        "_forcedType": "SLOGAN_COMMITMENT",
    })
    assert "<archetype_ending_constraint" in prompt
    tone_idx = prompt.find("</source_tone_analysis>")
    arch_idx = prompt.find("<archetype_ending_constraint")
    obj_idx = prompt.find("<objective")
    assert tone_idx < arch_idx < obj_idx


def test_ending_constraint_slogan_forbids_question():
    from agents.common.title_scoring import _assess_title_ending_constraint

    result = _assess_title_ending_constraint(
        '샘플구 테크노밸리, 4년간 무엇이 달라졌을까요?',
        {'_forcedType': 'SLOGAN_COMMITMENT'},
    )
    assert not result['passed']
    assert result['ending_class'] in ('real_question', 'rhetorical_question')


def test_ending_constraint_slogan_allows_commitment():
    from agents.common.title_scoring import _assess_title_ending_constraint

    result = _assess_title_ending_constraint(
        '홍길동, 샘플구를 책임감으로 끝까지 뛰겠습니다',
        {'_forcedType': 'SLOGAN_COMMITMENT'},
    )
    assert result['passed']


def test_ending_constraint_question_answer_allows_real_question():
    from agents.common.title_scoring import _assess_title_ending_constraint

    result = _assess_title_ending_constraint(
        '샘플구 청년 주거, 월세 지원 얼마까지?',
        {'_forcedType': 'QUESTION_ANSWER'},
    )
    assert result['passed']


def test_ending_constraint_commentary_forbids_commitment():
    from agents.common.title_scoring import _assess_title_ending_constraint

    result = _assess_title_ending_constraint(
        '홍길동, 샘플구를 끝까지 지키겠습니다',
        {'_forcedType': 'COMMENTARY'},
    )
    assert not result['passed']


def test_regex_fallback_detects_commitment():
    from agents.common.title_scoring import _detect_ending_class_regex_fallback

    assert _detect_ending_class_regex_fallback('끝까지 뛰겠습니다') == 'commitment'


def test_regex_fallback_detects_real_question():
    from agents.common.title_scoring import _detect_ending_class_regex_fallback

    assert _detect_ending_class_regex_fallback('월세 지원 얼마까지?') == 'real_question'


def test_regex_fallback_detects_rhetorical_question():
    from agents.common.title_scoring import _detect_ending_class_regex_fallback

    assert _detect_ending_class_regex_fallback('성과를 낼 수 있을까?') == 'rhetorical_question'


def test_tone_family_compatibility_pledge_slogan():
    from agents.common.title_common import assess_tone_family_compatibility

    result = assess_tone_family_compatibility('pledge', 'SLOGAN_COMMITMENT')
    assert result['compatible']


def test_tone_family_compatibility_pledge_question_answer():
    from agents.common.title_common import assess_tone_family_compatibility

    result = assess_tone_family_compatibility('pledge', 'QUESTION_ANSWER')
    assert not result['compatible']


def test_tone_family_compatibility_hybrid_all():
    from agents.common.title_common import assess_tone_family_compatibility

    for family in ('SLOGAN_COMMITMENT', 'QUESTION_ANSWER', 'DATA_BASED', 'COMMENTARY'):
        result = assess_tone_family_compatibility('hybrid', family)
        assert result['compatible'], f'hybrid should be compatible with {family}'


# ── region 도 화이트리스트 / 교통 인프라 패턴 ──


def test_region_whitelist_rejects_false_do_suffix():
    """'광역철도', '분석도', '감면도' 같은 비지명 ~도 토큰이 region 에 안 잡힘."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = '광역철도 유치를 추진한다. B/C 분석도 완료됐다. 취득세 감면도 추진한다.'
    slots = extract_slot_opportunities('샘플 주제', content, {})
    region = slots.get('region', [])
    assert '광역철도' not in region
    assert '분석도' not in region
    assert '감면도' not in region


def test_region_whitelist_accepts_real_province():
    """실제 도 이름(경기도, 강원도 등)은 정상 매칭."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = '경기도 샘플시 일대에서 사업이 진행된다. 강원도 관광 개발도 병행한다.'
    slots = extract_slot_opportunities('샘플 주제', content, {})
    region = slots.get('region', [])
    assert '경기도' in region


def test_transport_infra_captured_as_institution():
    """'광역철도' 가 institution bucket 에 잡히고, 조사 '로' 가 붙은 형태는 제외."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = '광역철도 유치. 광역철도로 전환. 경부도로 확장.'
    slots = extract_slot_opportunities('샘플 주제', content, {})
    inst = slots.get('institution', [])
    assert '광역철도' in inst
    assert '경부도로' in inst
    assert '광역철도로' not in inst


def test_policy_plan_suffix_captured():
    """'구축계획', '발전전략' 등 계획·전략 접미 정책명이 policy 에 잡힘."""
    from agents.common.title_hook_quality import extract_slot_opportunities

    content = '인천시 도시철도망 구축계획에 반영. 지역 균형발전전략 수립. 추진방안 마련.'
    slots = extract_slot_opportunities('샘플 주제', content, {})
    policy = slots.get('policy', [])
    joined = ' '.join(policy)
    assert '구축계획' in joined, f'policy should contain 구축계획, got {policy}'
    assert '추진방안' in joined, f'policy should contain 추진방안, got {policy}'


def test_slot_keywords_use_topic_base_when_sufficient():
    """topic 토큰이 2개 이상이면 body-exclusive 를 섞지 않는다."""
    from agents.common.title_keywords import compute_required_topic_keywords

    topic = '샘플구 테크노밸리 2단계'
    content = '샘플구 테크노밸리 2단계 사업의 핵심은 광역철도 유치다.'
    kws = compute_required_topic_keywords(
        topic, {'topic': topic, 'contentPreview': content}, content=content,
    )
    assert '테크노밸리' in kws or any('테크노' in k for k in kws)
    assert '광역철도' not in kws, 'body-exclusive 는 topicMatch 에 섞이면 안 됨'


def test_title_with_body_exclusive_passes_topic_match():
    """topic 토큰 + body-exclusive 토큰을 쓴 제목이 topicMatch 높음."""
    from agents.common.title_scoring import calculate_title_quality_score

    title = '샘플구 테크노밸리 광역철도, 2026년 추진 현황 공개'
    params = {
        'topic': '샘플구 테크노밸리 2단계',
        'contentPreview': '샘플구 테크노밸리 2단계 사업의 핵심은 광역철도 유치다. 2026년 상반기 추진.',
        'stanceText': '',
        'userKeywords': ['샘플구 테크노밸리'],
        'authorName': '홍길동',
    }
    result = calculate_title_quality_score(title, params)
    topic_match = result['breakdown']['topicMatch']
    assert topic_match['score'] >= 15, f'topicMatch should be 보통 or higher, got {topic_match}'
