'use strict';

/**
 * 선거구 동기화 Cloud Functions 핸들러
 * - 자동 스케줄: 매월 1일 새벽 3시 (KST)
 * - 수동 트리거: HTTP 호출 (관리자 전용)
 */

const { onSchedule } = require('firebase-functions/v2/scheduler');
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const {
  syncUpcomingElections,
  syncSpecificElection,
  fetchElectionList
} = require('../services/district-sync');

/**
 * 월간 자동 동기화 스케줄러
 * - 매월 1일 새벽 3시 (KST = UTC+9)
 * - Cron: '0 18 1 * *' (UTC 기준: 18시 = KST 03시)
 */
exports.scheduledDistrictSync = onSchedule(
  {
    schedule: '0 18 1 * *', // 매월 1일 UTC 18:00 (KST 03:00)
    timeZone: 'Asia/Seoul',
    region: 'asia-northeast3',
    memory: '256MiB',
    timeoutSeconds: 540,
    maxInstances: 1
  },
  async (event) => {
    console.log('⏰ [scheduledDistrictSync] 월간 선거구 동기화 시작...');
    console.log('   시간:', new Date().toISOString());

    try {
      const result = await syncUpcomingElections();

      console.log('✅ [scheduledDistrictSync] 동기화 완료:', result);
      return result;
    } catch (error) {
      console.error('❌ [scheduledDistrictSync] 동기화 실패:', error);
      throw error;
    }
  }
);

/**
 * 수동 동기화 트리거 (관리자용)
 * 호출 예시:
 * ```javascript
 * const syncElectoralDistricts = httpsCallable(functions, 'syncElectoralDistricts');
 * const result = await syncElectoralDistricts({ sgId: '20260603' }); // 선택사항
 * ```
 */
exports.syncElectoralDistricts = onCall(
  {
    region: 'asia-northeast3',
    memory: '256MiB',
    timeoutSeconds: 540,
    maxInstances: 1
  },
  async (request) => {
    const { auth, data } = request;

    console.log('🔧 [syncElectoralDistricts] 수동 동기화 요청');
    console.log('   요청자:', auth?.uid || 'anonymous');
    console.log('   파라미터:', data);

    // 인증 확인 (선택사항: 추후 관리자 권한 체크 추가 가능)
    if (!auth) {
      throw new HttpsError(
        'unauthenticated',
        '로그인이 필요합니다.'
      );
    }

    try {
      let result;

      if (data?.sgId) {
        // 특정 선거만 동기화
        console.log(`   ℹ️ [syncElectoralDistricts] 특정 선거 동기화: ${data.sgId}`);
        result = await syncSpecificElection(data.sgId);
      } else {
        // 모든 미래 선거 동기화
        console.log('   ℹ️ [syncElectoralDistricts] 전체 미래 선거 동기화');
        result = await syncUpcomingElections();
      }

      console.log('✅ [syncElectoralDistricts] 동기화 성공:', result);
      return result;
    } catch (error) {
      console.error('❌ [syncElectoralDistricts] 동기화 실패:', error);
      throw new HttpsError(
        'internal',
        `동기화 실패: ${error.message}`,
        error
      );
    }
  }
);

/**
 * 선거 목록 조회 (클라이언트용)
 * 호출 예시:
 * ```javascript
 * const getElectionList = httpsCallable(functions, 'getElectionList');
 * const result = await getElectionList();
 * ```
 */
exports.getElectionList = onCall(
  {
    region: 'asia-northeast3',
    memory: '128MiB',
    timeoutSeconds: 60
  },
  async (request) => {
    console.log('📋 [getElectionList] 선거 목록 조회 요청');

    try {
      const elections = await fetchElectionList();

      // 2020년 이후 선거만 필터링
      const upcomingElections = elections.filter(e => parseInt(e.sgId) >= 20200000);

      console.log(`✅ [getElectionList] ${upcomingElections.length}개 미래 선거 반환`);

      return {
        success: true,
        elections: upcomingElections.map(e => ({
          id: e.sgId,
          name: e.sgName,
          date: e.sgVotedate,
          type: e.sgTypecode
        })),
        total: upcomingElections.length
      };
    } catch (error) {
      console.error('❌ [getElectionList] 조회 실패:', error);
      throw new HttpsError(
        'internal',
        `선거 목록 조회 실패: ${error.message}`,
        error
      );
    }
  }
);
