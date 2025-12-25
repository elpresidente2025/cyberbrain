'use strict';

/**
 * Firestore 기반 선거구 유틸리티 모듈
 * - districtKey 생성 및 정규화 함수 제공
 * - 선거구 1인 제한은 폐지됨 (district-priority.js에서 다중 사용자 허용)
 */

const { admin, db } = require('../utils/firebaseAdmin');

let HttpsError;
try {
  // Firebase Functions v2
  HttpsError = require('firebase-functions/v2/https').HttpsError;
} catch (_) {
  // Fallback: v1
  HttpsError = require('firebase-functions').https.HttpsError;
}

/* =========================================
 * Utils
 * =======================================*/

/**
 * 표준화: 앞뒤 공백 제거, 소문자, 모든 공백 제거, 문자/숫자만 남김(유니코드)
 */
function norm(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^\p{Letter}\p{Number}]/gu, '');
}

/**
 * 직책 표준화:
 * - 괄호/상태 표기 제거: (예비), (현역), 후보/후보자, candidate, incumbent 등
 * - 흔한 동의어를 하나로 접힘: 국회의원/광역의원/기초의원/광역자치단체장/기초자치단체장
 */
function canonicalPosition(pos) {
  let v = String(pos || '');

  // 괄호 속 표기 제거: (예비), (현역) 등
  v = v.replace(/\([^)]*\)/g, ' ');
  // 상태 키워드 제거
  v = v.replace(/(예비|현역|후보자?|candidate|incumbent)/gi, ' ');
  // 여분 공백 정리
  v = v.replace(/\s+/g, ' ').trim();

  // 동의어 접기
  const s = v;
  if (/국회|국회의원/i.test(s)) return '국회의원';
  if (/광역|도의원/i.test(s)) return '광역의원';
  if (/기초|구의원|군의원|시의원/i.test(s)) return '기초의원';
  if (/광역자치단체장/i.test(s)) return '광역자치단체장';
  if (/기초자치단체장/i.test(s)) return '기초자치단체장';

  // 모호하면 그대로 사용(그래도 상태는 제거돼 있음)
  return v || '기초의원';
}

/**
 * 선거구 키 생성 (position 포함 유지하되 status는 제거)
 * @param {{ position:string, regionMetro:string, regionLocal:string, electoralDistrict:string }} parts
 * @returns {string}
 */
function districtKey(parts = {}) {
  const { position, regionMetro, regionLocal, electoralDistrict } = parts;
  const pos = canonicalPosition(position); // ✅ 상태 제거된 직책 사용

  // 자치단체장의 경우 선거구 불필요
  if (pos === '광역자치단체장') {
    // 광역자치단체장: regionMetro만 필요
    const pieces = [pos, regionMetro].map(norm);
    if (pieces.some((p) => !p)) {
      throw new HttpsError(
        'invalid-argument',
        '광역자치단체장의 경우 position과 regionMetro가 필요합니다.'
      );
    }
    return pieces.join('__');
  } else if (pos === '기초자치단체장') {
    // 기초자치단체장: regionMetro, regionLocal 필요
    const pieces = [pos, regionMetro, regionLocal].map(norm);
    if (pieces.some((p) => !p)) {
      throw new HttpsError(
        'invalid-argument',
        '기초자치단체장의 경우 position, regionMetro, regionLocal이 필요합니다.'
      );
    }
    return pieces.join('__');
  } else {
    // 의원: 모든 필드 필요
    const pieces = [pos, regionMetro, regionLocal, electoralDistrict].map(norm);
    if (pieces.some((p) => !p)) {
      throw new HttpsError(
        'invalid-argument',
        '선거구 키를 만들기 위해 position/regionMetro/regionLocal/electoralDistrict가 모두 필요합니다.'
      );
    }
    return pieces.join('__');
  }
}


/**
 * 우선권 변경 알림 발송 (비동기)
 * 결제 기반 우선권 시스템에서 사용
 */
async function notifyPriorityChange({ newPrimaryUserId, oldPrimaryUserId, districtKey }) {
  if (!newPrimaryUserId || !districtKey) return;

  try {
    const { notifyPriorityGained, notifyPriorityLost } = require('./notification');

    // 새 우선권자에게 알림
    await notifyPriorityGained({
      userId: newPrimaryUserId,
      districtKey,
      previousUserId: oldPrimaryUserId
    });

    // 이전 우선권자에게 알림 (선택사항)
    if (oldPrimaryUserId) {
      await notifyPriorityLost({
        userId: oldPrimaryUserId,
        districtKey,
        newPrimaryUserId
      });
    }

    console.log('✅ [notifyPriorityChange] 알림 발송 완료:', {
      newPrimaryUserId,
      oldPrimaryUserId,
      districtKey
    });
  } catch (error) {
    console.error('❌ [notifyPriorityChange] 알림 발송 실패 (무시):', error.message);
    // 알림 실패는 메인 프로세스에 영향을 주지 않음
  }
}

/**
 * 관리자용 선거구 점유 기록 정리 (강제 해제)
 */
async function forceReleaseDistrict({ districtKey, requestedByUid }) {
  if (!districtKey) {
    throw new HttpsError('invalid-argument', 'districtKey가 필요합니다.');
  }

  console.log('🧹 [forceReleaseDistrict] 시작:', { districtKey, requestedByUid });

  const claimRef = db.collection('district_claims').doc(districtKey);
  const doc = await claimRef.get();

  if (!doc.exists) {
    console.log('ℹ️ [forceReleaseDistrict] 이미 해제됨:', { districtKey });
    return { success: true, message: '이미 해제된 선거구입니다.' };
  }

  const occupiedBy = doc.get('userId');
  console.log('🔍 [forceReleaseDistrict] 점유자 확인:', { districtKey, occupiedBy });

  await claimRef.delete();

  console.log('✅ [forceReleaseDistrict] 완료:', { districtKey, occupiedBy });
  return {
    success: true,
    message: '선거구 점유가 해제되었습니다.',
    previousOwner: occupiedBy
  };
}

/**
 * 특정 선거구 점유 상태 조회 (디버깅용)
 */
async function getDistrictStatus(districtKey) {
  if (!districtKey) {
    throw new HttpsError('invalid-argument', 'districtKey가 필요합니다.');
  }

  const doc = await db.collection('district_claims').doc(districtKey).get();

  if (!doc.exists) {
    return {
      status: 'available',
      districtKey,
      message: '사용 가능한 선거구입니다.'
    };
  }

  const data = doc.data();
  return {
    status: 'occupied',
    districtKey,
    occupiedBy: data.userId,
    claimedAt: data.claimedAt,
    lastUpdated: data.lastUpdated,
    message: `${data.userId}가 점유 중입니다.`
  };
}

/* =========================================
 * Exports
 * =======================================*/

module.exports = {
  norm,
  canonicalPosition,
  districtKey,
  notifyPriorityChange,
  forceReleaseDistrict,
  getDistrictStatus
};