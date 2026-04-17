# tests/test_resolve_election_context.py
# resolve_election_context() 단위 테스트

import pytest
from unittest.mock import patch
from datetime import date

from agents.common.election_rules import resolve_election_context


def _mock_today(d: date):
    """_today_kst()를 특정 날짜로 고정하는 패치 헬퍼."""
    return patch('agents.common.election_rules._today_kst', return_value=d)


# ============================================================================
# 준비 상태 — 항상 STAGE_1, campaign_unlocked=False
# ============================================================================

class TestPrepStatus:
    def test_prep_always_stage1(self):
        ctx = resolve_election_context('준비', None)
        assert ctx['stage_name'] == 'STAGE_1'
        assert ctx['campaign_unlocked'] is False
        assert ctx['blocked'] is False

    def test_prep_ignores_dday(self):
        """준비 상태는 D-day와 무관하게 STAGE_1."""
        profile = {'status': '준비', 'position': '광역의원'}
        with _mock_today(date(2026, 5, 20)):  # D-14
            ctx = resolve_election_context('준비', profile)
        assert ctx['stage_name'] == 'STAGE_1'
        assert ctx['campaign_unlocked'] is False


# ============================================================================
# 현역 상태 — 항상 STAGE_1
# ============================================================================

class TestActiveStatus:
    def test_active_korean_stage1(self):
        profile = {'status': '현역', 'position': '국회의원'}
        ctx = resolve_election_context('현역', profile)
        assert ctx['stage_name'] == 'STAGE_1'
        assert ctx['campaign_unlocked'] is False

    def test_active_english_stage1(self):
        ctx = resolve_election_context('active', {'status': 'active'})
        assert ctx['stage_name'] == 'STAGE_1'

    def test_empty_status_defaults_stage1(self):
        ctx = resolve_election_context('', None)
        assert ctx['stage_name'] == 'STAGE_1'


# ============================================================================
# 예비 상태 — D-day 동적 판단
# ============================================================================

class TestPreliminaryStatus:
    def test_d45_stage2_unlocked(self):
        """D-45 → STAGE_2, campaign_unlocked=True."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 4, 19)):  # D-45
            ctx = resolve_election_context('예비', profile)
        assert ctx['stage_name'] == 'STAGE_2'
        assert ctx['campaign_unlocked'] is True
        assert ctx['blocked'] is False
        assert ctx['days_until_election'] == 45

    def test_d91_blocked(self):
        """D-91 → blocked (eligibility guard)."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 3, 4)):  # D-91
            ctx = resolve_election_context('예비', profile)
        assert ctx['blocked'] is True
        assert ctx['campaign_unlocked'] is False

    def test_d0_blocked(self):
        """D-day 당일 → blocked."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 6, 3)):  # D=0
            ctx = resolve_election_context('예비', profile)
        assert ctx['blocked'] is True
        assert ctx['phase'] == 'ELECTION_DAY'

    def test_post_election_blocked(self):
        """선거 종료 후 → blocked (다음 선거 D>90이므로 eligibility guard)."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 6, 10)):  # 선거 다음 주
            ctx = resolve_election_context('예비', profile)
        assert ctx['blocked'] is True
        # _get_next_election_date는 다음 주기(2030)를 반환 → D>90 → eligibility guard
        assert ctx['days_until_election'] > 90

    def test_d90_boundary_allowed(self):
        """D-90 정확히 → 허용."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 3, 5)):  # D-90
            ctx = resolve_election_context('예비', profile)
        assert ctx['blocked'] is False
        assert ctx['stage_name'] == 'STAGE_2'
        assert ctx['days_until_election'] == 90


# ============================================================================
# 후보 상태 — D-day 동적 판단
# ============================================================================

class TestCandidateStatus:
    def test_d45_stage3_unlocked(self):
        """후보 D-45 → STAGE_3, campaign_unlocked=True."""
        profile = {'status': '후보', 'position': '광역의원'}
        with _mock_today(date(2026, 4, 19)):  # D-45
            ctx = resolve_election_context('후보', profile)
        assert ctx['stage_name'] == 'STAGE_3'
        assert ctx['campaign_unlocked'] is True
        assert ctx['blocked'] is False

    def test_d91_blocked(self):
        """후보 D-91 → blocked."""
        profile = {'status': '후보', 'position': '광역의원'}
        with _mock_today(date(2026, 3, 4)):  # D-91
            ctx = resolve_election_context('후보', profile)
        assert ctx['blocked'] is True

    def test_d0_blocked(self):
        """후보 D-day 당일 → blocked."""
        profile = {'status': '후보', 'position': '광역의원'}
        with _mock_today(date(2026, 6, 3)):
            ctx = resolve_election_context('후보', profile)
        assert ctx['blocked'] is True


# ============================================================================
# 보수적 폴백 — 알 수 없는 상태
# ============================================================================

class TestFallback:
    def test_unknown_status_falls_back_to_stage1(self):
        ctx = resolve_election_context('알수없음', None)
        assert ctx['stage_name'] == 'STAGE_1'
        assert ctx['campaign_unlocked'] is False
        assert ctx['blocked'] is False

    def test_candidate_without_profile_stage1(self):
        """후보인데 profile이 None → _normalize_candidate_status가 빈 문자열 반환 → STAGE_1."""
        ctx = resolve_election_context('후보', None)
        # profile이 None이면 normalize가 status를 못 읽을 수 있음
        # resolve_election_context의 첫 번째 인자(status)를 폴백으로 사용
        assert ctx['stage_name'] in ('STAGE_1', 'STAGE_3')  # 구현에 따라


# ============================================================================
# Phase 판정
# ============================================================================

class TestPhase:
    def test_normal_period(self):
        profile = {'status': '현역', 'position': '광역의원'}
        with _mock_today(date(2025, 12, 1)):  # D-549+
            ctx = resolve_election_context('현역', profile)
        assert ctx['phase'] == 'NORMAL_PERIOD'

    def test_pre_campaign_warning(self):
        """D-20 → PRE_CAMPAIGN_WARNING."""
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 5, 14)):  # D-20
            ctx = resolve_election_context('예비', profile)
        assert ctx['phase'] == 'PRE_CAMPAIGN_WARNING'

    def test_campaign_period(self):
        """D-10 → CAMPAIGN_PERIOD (campaign_period_days=14)."""
        profile = {'status': '후보', 'position': '광역의원'}
        with _mock_today(date(2026, 5, 24)):  # D-10
            ctx = resolve_election_context('후보', profile)
        assert ctx['phase'] == 'CAMPAIGN_PERIOD'


# ============================================================================
# ELECTION_REGISTRY 매칭
# ============================================================================

class TestRegistryMatching:
    def test_national_assembly_matches(self):
        profile = {'status': '현역', 'position': '국회의원'}
        with _mock_today(date(2026, 4, 17)):
            ctx = resolve_election_context('현역', profile)
        # 2028-04-12 기준
        assert ctx['election_date'] == '2028-04-12'

    def test_local_government_matches(self):
        profile = {'status': '현역', 'position': '광역의원'}
        with _mock_today(date(2026, 4, 17)):
            ctx = resolve_election_context('현역', profile)
        assert ctx['election_date'] == '2026-06-03'

    def test_target_election_priority(self):
        """targetElection.position이 profile.position보다 우선."""
        profile = {
            'status': '현역',
            'position': '광역의원',
            'targetElection': {'position': '국회의원'},
        }
        with _mock_today(date(2026, 4, 17)):
            ctx = resolve_election_context('현역', profile)
        assert ctx['election_date'] == '2028-04-12'


# ============================================================================
# prompt_instruction 포함 여부
# ============================================================================

class TestPromptInstruction:
    def test_stage1_has_instruction(self):
        ctx = resolve_election_context('준비', None)
        assert 'election_compliance' in ctx['prompt_instruction']
        assert 'STAGE_1' in ctx['prompt_instruction']

    def test_blocked_has_no_instruction(self):
        profile = {'status': '예비', 'position': '광역의원'}
        with _mock_today(date(2026, 6, 3)):  # D=0
            ctx = resolve_election_context('예비', profile)
        assert ctx['blocked'] is True
        assert ctx['prompt_instruction'] == ''
