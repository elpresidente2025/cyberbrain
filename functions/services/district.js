'use strict';

/**
 * Firestore 기반 선거구 점유(락) 모듈
 * - 규칙: 동일 districtKey(= 직책+지역+선거구; 단, 직책은 현역/예비 등 상태를 제거)에는 동시에 1명만 가능
 * - 핵심: 트랜잭션 내부에서 타 점유자 존재 시 무조건 실패(already-exists, reason: DISTRICT_TAKEN)
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
 * - 흔한 동의어를 하나로 접힘: 국회의원/광역의원/기초의원
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
  const pieces = [pos, regionMetro, regionLocal, electoralDistrict].map(norm);
  if (pieces.some((p) => !p)) {
    throw new HttpsError(
      'invalid-argument',
      '선거구 키를 만들기 위해 position/regionMetro/regionLocal/electoralDistrict가 모두 필요합니다.'
    );
  }
  return pieces.join('__');
}

/* =========================================
 * Availability (읽기 전용)
 * =======================================*/

/**
 * 선거구 사용 가능 여부 조회(사전 안내용)
 * - 호출 형태 호환: checkDistrictAvailability('key') 또는 { newKey:'key', excludeUid:'...' }
 * - 실제 보장은 claimDistrict가 담당
 */
async function checkDistrictAvailability(arg) {
  const isObj = arg && typeof arg === 'object';
  const newKey = isObj ? arg.newKey : arg;
  const excludeUid = isObj ? arg.excludeUid : undefined;

  if (!newKey) throw new HttpsError('invalid-argument', 'newKey가 필요합니다.');

  const doc = await db.collection('district_claims').doc(newKey).get();
  if (!doc.exists) return { available: true };

  const userId = doc.get('userId');
  if (!userId) return { available: true };
  if (excludeUid && userId === excludeUid) return { available: true };

  return { available: false, occupiedBy: userId };
}

/* =========================================
 * Claiming (쓰기)
 * =======================================*/

/**
 * 선거구 점유 처리 (트랜잭션 규칙 준수)
 * 모든 읽기 작업을 먼저 수행한 후 쓰기 작업 실행
 */
async function claimDistrict({ uid, newKey, oldKey }) {
  if (!uid || !newKey) {
    throw new HttpsError('invalid-argument', 'uid와 newKey가 필요합니다.');
  }

  const newRef = db.collection('district_claims').doc(newKey);
  const oldRef = oldKey ? db.collection('district_claims').doc(oldKey) : null;

  return await db.runTransaction(async (tx) => {
    // ✅ 1단계: 모든 읽기 작업을 먼저 수행
    const newDoc = await tx.get(newRef);
    const oldDoc = oldRef ? await tx.get(oldRef) : null;
    
    // 2단계: 읽은 데이터를 기반으로 검증 로직 실행
    // 새로운 선거구가 이미 다른 사용자에 의해 점유되었는지 확인
    if (newDoc.exists) {
      const existingUserId = newDoc.get('userId');
      if (existingUserId && existingUserId !== uid) {
        throw new HttpsError('already-exists', 
          '해당 선거구는 이미 다른 사용자가 사용 중입니다.',
          { reason: 'DISTRICT_TAKEN', existingUserId }
        );
      }
    }

    // 기존 선거구가 본인 소유인지 확인 (다른 사람 것이면 삭제하지 않음)
    let canDeleteOld = false;
    if (oldDoc && oldDoc.exists) {
      const oldUserId = oldDoc.get('userId');
      canDeleteOld = (oldUserId === uid);
    }

    // ✅ 3단계: 모든 쓰기 작업을 순차적으로 수행
    // 새로운 선거구 점유 설정
    tx.set(newRef, {
      userId: uid,
      claimedAt: admin.firestore.FieldValue.serverTimestamp(),
      lastUpdated: admin.firestore.FieldValue.serverTimestamp()
    });

    // 기존 선거구 해제 (본인 소유인 경우에만)
    if (oldRef && canDeleteOld && oldKey !== newKey) {
      tx.delete(oldRef);
    }

    return { success: true, newKey, oldKey };
  });
}

/**
 * 중복 점유자 정리 (별도 트랜잭션으로 분리)
 * 메인 트랜잭션과 분리하여 안전성 확보
 */
async function scrubDuplicateHolders({ key, ownerUid }) {
  if (!key || !ownerUid) return;

  try {
    // 동일한 선거구를 점유한 모든 문서 조회
    const snapshot = await db.collection('district_claims').where('userId', '==', ownerUid).get();
    
    const batch = db.batch();
    let hasChanges = false;

    snapshot.forEach(doc => {
      if (doc.id !== key) {
        // 다른 키를 가진 문서는 삭제 (사용자당 하나의 선거구만 허용)
        batch.delete(doc.ref);
        hasChanges = true;
      }
    });

    if (hasChanges) {
      await batch.commit();
    }
  } catch (error) {
    console.warn('[scrubDuplicateHolders] 정리 중 오류 (무시):', error.message);
    // 정리 작업 실패는 메인 프로세스에 영향을 주지 않음
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
  checkDistrictAvailability,
  claimDistrict,
  scrubDuplicateHolders,
  forceReleaseDistrict,
  getDistrictStatus
};