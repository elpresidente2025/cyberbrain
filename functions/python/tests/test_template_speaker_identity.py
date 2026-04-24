"""Phase 3 회귀 테스트: 7 개 글쓰기 템플릿이 공통 speaker_identity 블록을
사용하는지 검증.

Phase 1·2 가 TitleAgent / ContextAnalyzer / role policy 에 화자 직책
앵커와 ally 룰을 추가했고, 본 Phase 3 는 StructureAgent 의 7 개 글쓰기
템플릿이 모두 같은 build_speaker_identity_xml() helper 를 호출해
일관된 화자 정체성 블록을 LLM 프롬프트에 주입하는지 확인한다.

CLAUDE.md 범용성 원칙: 모든 인물명·지역명·직책 인스턴스는 placeholder
(홍길동·아무개·샘플특별시·샘플구) 만 사용한다.
"""

from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.speaker_identity import build_speaker_identity_xml
from agents.templates.activity_report import build_activity_report_prompt
from agents.templates.bipartisan_cooperation import build_bipartisan_cooperation_prompt
from agents.templates.current_affairs import (
    build_critical_writing_prompt,
    build_diagnosis_writing_prompt,
)
from agents.templates.daily_communication import build_daily_communication_prompt
from agents.templates.local_issues import build_local_issues_prompt
from agents.templates.offline_engagement import build_offline_engagement_prompt
from agents.templates.policy_proposal import build_policy_proposal_prompt


def _base_options() -> dict:
    return {
        'topic': '샘플구 활동 보고',
        'authorBio': '광역의원 홍길동, 샘플특별시 샘플구 출신',
        'authorName': '홍길동',
        'userProfile': {
            'name': '홍길동',
            'position': '광역의원',
            'regionMetro': '샘플특별시',
            'regionLocal': '샘플구',
            'electoralDistrict': '샘플구 제1선거구',
        },
        'instructions': '아무개 시장후보와 함께 뛰는 이야기',
        'keywords': ['샘플구', '활동 보고'],
        'targetWordCount': 1500,
        'personalizedHints': '',
    }


# ── helper 자체 검증 ─────────────────────────────────────────────────


def test_helper_produces_block_with_structured_fields() -> None:
    options = _base_options()
    block = build_speaker_identity_xml(
        full_name=options['authorName'],
        author_bio=options['authorBio'],
        user_profile=options['userProfile'],
    )
    assert '<speaker_identity priority="critical"' in block
    assert '<full_name>홍길동</full_name>' in block
    assert '<position>샘플특별시의원</position>' in block  # 광역의원+regionMetro 결합
    assert '<region_metro>샘플특별시</region_metro>' in block
    assert '<region_local>샘플구</region_local>' in block
    assert '<electoral_district>샘플구 제1선거구</electoral_district>' in block


def test_helper_includes_role_attribution_and_ally_rules() -> None:
    block = build_speaker_identity_xml(
        full_name='홍길동',
        author_bio='홍길동',
        user_profile={'position': '광역의원', 'regionMetro': '샘플특별시'},
    )
    # 1인칭, 본인 이름 사용 제한, 타인은 3인칭, ally 룰 모두 들어가야 함
    assert 'first_person' in block
    assert 'name_usage_limit' in block
    assert 'others_third_person' in block
    assert 'ally_role_anchor' in block
    assert '러닝메이트' in block
    assert '본인 직책을 그 사람의 직책으로 바꿔 적지 마세요' in block
    assert 'own_election_specificity' in block
    assert '직책 기반 선거 유형' in block


def test_helper_returns_empty_when_all_inputs_blank() -> None:
    block = build_speaker_identity_xml(
        full_name='', author_bio='', user_profile={}
    )
    assert block == ''


# ── 7 템플릿 통합 검증 ───────────────────────────────────────────────


def _assert_template_emits_speaker_identity(prompt: str, label: str) -> None:
    assert '<speaker_identity priority="critical"' in prompt, (
        f'{label}: speaker_identity 블록 누락'
    )
    assert '<full_name>홍길동</full_name>' in prompt, (
        f'{label}: full_name 필드 누락'
    )
    assert '<position>샘플특별시의원</position>' in prompt, (
        f'{label}: position 라벨 누락'
    )
    assert 'ally_role_anchor' in prompt, (
        f'{label}: ally 룰 누락'
    )


def test_activity_report_template_includes_speaker_identity() -> None:
    prompt = build_activity_report_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'activity_report')


def test_local_issues_template_includes_speaker_identity() -> None:
    prompt = build_local_issues_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'local_issues')


def test_critical_writing_template_includes_speaker_identity() -> None:
    prompt = build_critical_writing_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'critical_writing')


def test_diagnosis_writing_template_includes_speaker_identity() -> None:
    prompt = build_diagnosis_writing_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'diagnosis_writing')


def test_offline_engagement_template_includes_speaker_identity() -> None:
    prompt = build_offline_engagement_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'offline_engagement')


def test_bipartisan_cooperation_template_includes_speaker_identity() -> None:
    prompt = build_bipartisan_cooperation_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'bipartisan_cooperation')


def test_daily_communication_template_includes_speaker_identity() -> None:
    prompt = build_daily_communication_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'daily_communication')


def test_policy_proposal_template_includes_speaker_identity() -> None:
    prompt = build_policy_proposal_prompt(_base_options())
    _assert_template_emits_speaker_identity(prompt, 'policy_proposal')


# ── 빈 프로필에도 템플릿이 깨지지 않는지 ─────────────────────────────


def test_template_does_not_crash_when_user_profile_missing() -> None:
    """userProfile 이 비어 있어도 템플릿이 정상 생성된다 (블록만 빠짐)."""
    options = _base_options()
    options['userProfile'] = {}
    options['authorName'] = ''
    options['authorBio'] = ''
    prompt = build_activity_report_prompt(options)
    # speaker_identity 블록은 비어 있을 수 있으나 task 자체는 정상 출력
    assert '<task type="의정활동 보고"' in prompt
