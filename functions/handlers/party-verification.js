const { onCall, HttpsError } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { extractTextFromImage, extractPartyInfo, extractPaymentInfo, NAVER_OCR_SECRET_KEY, NAVER_OCR_API_URL } = require('../utils/naver-ocr');
const { extractUserInfo } = require('../common/auth');

const db = admin.firestore();

/**
 * 당적증명서를 OCR로 인증합니다.
 * @route POST /verifyPartyCertificate
 * @body {string} imageUrl - Firebase Storage에 업로드된 이미지 URL
 * @body {string} imageFormat - 이미지 형식 (jpg, png, pdf)
 * @returns {Object} 인증 결과
 */
const verifyPartyCertificate = onCall({
  region: 'asia-northeast3',
  secrets: [NAVER_OCR_SECRET_KEY, NAVER_OCR_API_URL],
  timeoutSeconds: 120,
  memory: '512MiB'
}, async (request) => {
  try {
    const { userId, base64Data, fileName, imageFormat = 'jpg' } = request.data;

    // userId 필수 체크
    if (!userId) {
      throw new HttpsError(
        'invalid-argument',
        '사용자 ID가 필요합니다.'
      );
    }

    if (!base64Data || !fileName) {
      throw new HttpsError(
        'invalid-argument',
        '파일 데이터와 파일명이 필요합니다.'
      );
    }

    console.log(`당적증명서 인증 시작: userId=${userId}, fileName=${fileName}`);

    // 사용자 프로필에서 성명 가져오기
    const userDoc = await db.collection('users').doc(userId).get();
    const userData = userDoc.data();
    const userName = userData?.name;

    if (!userName) {
      throw new HttpsError(
        'failed-precondition',
        '사용자 프로필에 성명이 등록되지 않았습니다. 먼저 프로필을 완성해주세요.'
      );
    }

    // Storage 저장 없이 바로 OCR 처리 (Base64 데이터 사용)
    const storagePath = `party-certificates/${userId}/${fileName}`; // 로깅용
    console.log(`OCR 처리 시작: ${storagePath}`);

    // OCR 실행 (Base64 데이터 + 당적증명서 템플릿 ID 전달)
    const PARTY_CERT_TEMPLATE_ID = 39477;
    console.log(`템플릿 ID ${PARTY_CERT_TEMPLATE_ID} 사용하여 OCR 호출`);
    const ocrResult = await extractTextFromImage(base64Data, imageFormat, PARTY_CERT_TEMPLATE_ID);

      // OCR 결과 전체 로그 출력 (디버깅)
      console.log('OCR 원본 결과:', JSON.stringify(ocrResult.extractedText, null, 2));

      if (!ocrResult.success) {
        console.error('OCR 처리 실패:', ocrResult.error);

        // OCR 실패 시 수동 검토로 전환
        await saveVerificationRequest(userId, {
          type: 'party_certificate',
          storagePath: storagePath,
          status: 'pending_manual_review',
          ocrError: ocrResult.error,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: 'OCR 자동 인증에 실패했습니다. 수동 검토로 전환되었습니다.'
        };
      }

      // 당적 정보 추출 (전체 ocrResult 객체 전달)
      const partyInfo = extractPartyInfo(ocrResult.extractedText);

      // 유효성 검증
      if (!partyInfo.isValid) {
        console.warn('당적증명서 유효성 검증 실패:', partyInfo);

        // 수동 검토 요청
        await saveVerificationRequest(userId, {
          type: 'party_certificate',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          partyInfo: partyInfo,
          reason: '필수 정보를 찾을 수 없습니다.',
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '당적증명서에서 필수 정보를 찾을 수 없습니다. 수동 검토로 전환되었습니다.',
          extractedInfo: partyInfo
        };
      }

      // 성명 검증: 사용자 프로필의 이름과 일치하는지 확인
      if (partyInfo.name !== userName) {
        console.warn('성명 불일치:', { extracted: partyInfo.name, user: userName });

        await saveVerificationRequest(userId, {
          type: 'party_certificate',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          partyInfo: partyInfo,
          userName: userName,
          reason: `성명이 일치하지 않습니다. (증명서: ${partyInfo.name}, 프로필: ${userName})`,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '당적증명서의 성명이 프로필 정보와 일치하지 않습니다. 수동 검토로 전환되었습니다.',
          extractedInfo: partyInfo
        };
      }

      // 발행일 검증: 당월에 발행된 증명서만 유효
      const issueDate = new Date(partyInfo.issueDate);
      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth(); // 0-11

      if (issueDate.getFullYear() !== currentYear || issueDate.getMonth() !== currentMonth) {
        console.warn('발행일이 당월이 아님:', partyInfo.issueDate);

        await saveVerificationRequest(userId, {
          type: 'party_certificate',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          partyInfo: partyInfo,
          reason: `발행일이 당월이 아닙니다. (발행일: ${partyInfo.issueDate}, 현재: ${currentYear}-${String(currentMonth + 1).padStart(2, '0')})`,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '당월에 발행된 증명서만 인증 가능합니다. 최신 증명서를 제출해주세요.',
          extractedInfo: partyInfo
        };
      }

      // 분기별 인증 필요 여부 확인
      const verificationCheck = await checkQuarterlyVerification(userId, userData);
      if (!verificationCheck.needsVerification) {
        console.log(`분기 인증 면제: ${verificationCheck.reason}`);

        return {
          success: true,
          exempted: true,
          message: verificationCheck.reason,
          nextVerificationQuarter: verificationCheck.nextQuarter
        };
      }

      // 인증 성공 - Firestore에 저장
      const quarter = getCurrentQuarter();
      await saveVerificationResult(userId, {
        type: 'party_certificate',
        quarter: quarter,
        status: 'verified',
        method: 'ocr_auto',
        partyInfo: partyInfo,
        storagePath: storagePath,
        verifiedAt: admin.firestore.FieldValue.serverTimestamp()
      });

      console.log(`당적증명서 인증 완료: userId=${userId}, quarter=${quarter}`);

      return {
        success: true,
        message: '당적증명서 인증이 완료되었습니다.',
        quarter: quarter,
        partyInfo: partyInfo
      };

  } catch (error) {
    console.error('당적증명서 인증 중 오류:', error);
    throw new HttpsError(
      'internal',
      '인증 처리 중 오류가 발생했습니다.',
      error.message
    );
  }
});

/**
 * 당비 납부 내역을 OCR로 인증합니다.
 * @route POST /verifyPaymentReceipt
 * @body {string} imageUrl - Firebase Storage에 업로드된 이미지 URL
 * @body {string} imageFormat - 이미지 형식
 * @body {string} payerName - 납부자명 (선택)
 * @body {string} paymentPeriod - 납부 기간 (선택)
 * @returns {Object} 인증 결과
 */
const verifyPaymentReceipt = onCall({
  region: 'asia-northeast3',
  secrets: [NAVER_OCR_SECRET_KEY, NAVER_OCR_API_URL],
  timeoutSeconds: 120,
  memory: '512MiB'
}, async (request) => {
  try {
    const { userId, base64Data, fileName, imageFormat = 'jpg' } = request.data;

    // userId 필수 체크
    if (!userId) {
      throw new HttpsError(
        'invalid-argument',
        '사용자 ID가 필요합니다.'
      );
    }

    if (!base64Data || !fileName) {
      throw new HttpsError(
        'invalid-argument',
        '파일 데이터와 파일명이 필요합니다.'
      );
    }

    console.log(`당비 납부 내역 인증 시작: userId=${userId}, fileName=${fileName}`);

    // 사용자 프로필에서 성명 가져오기
    const userDoc = await db.collection('users').doc(userId).get();
    const userData = userDoc.data();
    const userName = userData?.name;

    if (!userName) {
      throw new HttpsError(
        'failed-precondition',
        '사용자 프로필에 성명이 등록되지 않았습니다. 먼저 프로필을 완성해주세요.'
      );
    }

    // Storage 저장 없이 바로 OCR 처리 (Base64 데이터 사용)
    const storagePath = `payment-receipts/${userId}/${fileName}`; // 로깅용
    console.log(`OCR 처리 시작: ${storagePath}`);

    // OCR 실행 (Base64 데이터 + 당비납부내역서 템플릿 ID 전달)
    const PAYMENT_RECEIPT_TEMPLATE_ID = 39478;
    console.log(`템플릿 ID ${PAYMENT_RECEIPT_TEMPLATE_ID} 사용하여 OCR 호출`);
    const ocrResult = await extractTextFromImage(base64Data, imageFormat, PAYMENT_RECEIPT_TEMPLATE_ID);

      // OCR 결과 전체 로그 출력 (디버깅)
      console.log('OCR 원본 결과:', JSON.stringify(ocrResult.extractedText, null, 2));

      if (!ocrResult.success) {
        console.error('OCR 처리 실패:', ocrResult.error);

        // OCR 실패 시 수동 검토로 전환
        await saveVerificationRequest(userId, {
          type: 'payment_receipt',
          storagePath: storagePath,
          status: 'pending_manual_review',
          ocrError: ocrResult.error,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: 'OCR 자동 인증에 실패했습니다. 수동 검토로 전환되었습니다.'
        };
      }

      // 납부 정보 추출 (전체 ocrResult 객체 전달)
      const paymentInfo = extractPaymentInfo(ocrResult.extractedText);

      // 유효성 검증
      if (!paymentInfo.isValid) {
        console.warn('당비 납부 내역 유효성 검증 실패:', paymentInfo);

        // 수동 검토 요청
        await saveVerificationRequest(userId, {
          type: 'payment_receipt',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          paymentInfo: paymentInfo,
          reason: '필수 정보를 찾을 수 없습니다.',
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '납부 내역에서 필수 정보를 찾을 수 없습니다. 수동 검토로 전환되었습니다.',
          extractedInfo: paymentInfo
        };
      }

      // 성명 검증: 사용자 프로필의 이름과 일치하는지 확인
      if (paymentInfo.name !== userName) {
        console.warn('성명 불일치:', { extracted: paymentInfo.name, user: userName });

        await saveVerificationRequest(userId, {
          type: 'payment_receipt',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          paymentInfo: paymentInfo,
          userName: userName,
          reason: `성명이 일치하지 않습니다. (납부내역서: ${paymentInfo.name}, 프로필: ${userName})`,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '납부내역서의 성명이 프로필 정보와 일치하지 않습니다. 수동 검토로 전환되었습니다.',
          extractedInfo: paymentInfo
        };
      }

      // 발행일 검증: 당월에 발행된 내역서만 유효
      const issueDate = new Date(paymentInfo.issueDate);
      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth(); // 0-11

      if (issueDate.getFullYear() !== currentYear || issueDate.getMonth() !== currentMonth) {
        console.warn('발행일이 당월이 아님:', paymentInfo.issueDate);

        await saveVerificationRequest(userId, {
          type: 'payment_receipt',
          storagePath: storagePath,
          status: 'pending_manual_review',
          extractedText: ocrResult.extractedText.text,
          paymentInfo: paymentInfo,
          reason: `발행일이 당월이 아닙니다. (발행일: ${paymentInfo.issueDate}, 현재: ${currentYear}-${String(currentMonth + 1).padStart(2, '0')})`,
          requestedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        return {
          success: false,
          requiresManualReview: true,
          message: '당월에 발행된 납부내역서만 인증 가능합니다. 최신 내역서를 제출해주세요.',
          extractedInfo: paymentInfo
        };
      }

      // 납입연월 검증 제거: 증명서 발급 시점에 따라 당월 당비가 아직 납부되지 않을 수 있음
      // 성명과 발행일만 검증하고, 납입연월은 선택사항으로 처리
      if (paymentInfo.paymentMonth) {
        console.log('납입연월 확인:', paymentInfo.paymentMonth);
      } else {
        console.log('납입연월 정보 없음 (증명서 발급 시점에 당월 납부 전일 수 있음)');
      }

      // 인증 성공 - Firestore에 저장
      await saveVerificationResult(userId, {
        type: 'payment_receipt',
        quarter: currentQuarter,
        status: 'verified',
        method: 'ocr_auto',
        paymentInfo: paymentInfo,
        storagePath: storagePath,
        verifiedAt: admin.firestore.FieldValue.serverTimestamp()
      });

      console.log(`당비 납부 내역 인증 완료: userId=${userId}, quarter=${currentQuarter}`);

      return {
        success: true,
        message: '당비 납부 내역 인증이 완료되었습니다.',
        quarter: currentQuarter,
        paymentInfo: paymentInfo
      };

  } catch (error) {
    console.error('당비 납부 내역 인증 중 오류:', error);
    throw new HttpsError(
      'internal',
      '인증 처리 중 오류가 발생했습니다.',
      error.message
    );
  }
});

/**
 * 사용자의 당적 인증 이력을 조회합니다.
 * @route GET /getVerificationHistory
 * @returns {Object[]} 인증 이력 배열
 */
const getVerificationHistory = onCall({
  region: 'asia-northeast3'
}, async (request) => {
  try {
    // 인증 확인
    if (!request.auth) {
      throw new HttpsError(
        'unauthenticated',
        '로그인이 필요합니다.'
      );
    }

    const userId = request.auth.uid;

    // Firestore에서 인증 이력 조회
    const historySnapshot = await db
      .collection('users')
      .doc(userId)
      .collection('verifications')
      .orderBy('verifiedAt', 'desc')
      .limit(20)
      .get();

    const history = [];
    historySnapshot.forEach(doc => {
      const data = doc.data();
      history.push({
        id: doc.id,
        quarter: data.quarter,
        status: data.status,
        method: data.method,
        type: data.type,
        verifiedAt: data.verifiedAt?.toDate().toISOString(),
        partyInfo: data.partyInfo,
        paymentInfo: data.paymentInfo
      });
    });

    return {
      success: true,
      history: history
    };

  } catch (error) {
    console.error('인증 이력 조회 중 오류:', error);
    throw new HttpsError(
      'internal',
      '인증 이력 조회 중 오류가 발생했습니다.',
      error.message
    );
  }
});

/**
 * 현재 분기를 반환합니다.
 * @returns {string} "2025년 1분기" 형식
 */
function getCurrentQuarter() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;

  let quarter;
  if (month <= 3) quarter = 1;
  else if (month <= 6) quarter = 2;
  else if (month <= 9) quarter = 3;
  else quarter = 4;

  return `${year}년 ${quarter}분기`;
}

/**
 * 분기별 인증 필요 여부를 확인합니다.
 * @param {string} userId - 사용자 ID
 * @param {Object} userData - 사용자 프로필 데이터
 * @returns {Promise<Object>} 인증 필요 여부 및 사유
 */
async function checkQuarterlyVerification(userId, userData) {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth(); // 0-11
  const currentQuarter = getCurrentQuarter();

  // 분기 시작 월: 1월(0), 4월(3), 7월(6), 10월(9)
  const quarterStartMonths = [0, 3, 6, 9];
  const isQuarterStartMonth = quarterStartMonths.includes(currentMonth);

  // 1. 가입 시점 확인 - 분기 시작 월에 가입했으면 해당 분기 인증 면제
  const createdAt = userData?.createdAt?.toDate?.() || userData?.createdAt;
  if (createdAt) {
    const joinYear = createdAt.getFullYear();
    const joinMonth = createdAt.getMonth();
    const joinQuarter = getQuarterFromMonth(joinMonth);

    // 분기 시작 월(1/4/7/10월)에 가입한 경우, 해당 분기는 인증 면제
    const joinedInQuarterStartMonth = quarterStartMonths.includes(joinMonth);
    if (joinedInQuarterStartMonth) {
      const joinQuarterStr = `${joinYear}년 ${joinQuarter}분기`;

      // 가입한 분기와 현재 분기가 같으면 면제
      if (joinQuarterStr === currentQuarter) {
        const nextQuarter = getNextQuarter(currentQuarter);
        return {
          needsVerification: false,
          reason: `${joinMonth + 1}월(분기 시작 월)에 가입하셨으므로 ${currentQuarter} 인증이 면제됩니다.`,
          nextQuarter: nextQuarter
        };
      }
    }
  }

  // 2. 현재 분기에 이미 인증했는지 확인
  const lastVerification = userData?.lastVerification;
  if (lastVerification?.quarter === currentQuarter && lastVerification?.status === 'verified') {
    const nextQuarter = getNextQuarter(currentQuarter);
    return {
      needsVerification: false,
      reason: `${currentQuarter} 인증이 이미 완료되었습니다.`,
      nextQuarter: nextQuarter
    };
  }

  // 3. 분기별 인증이 필요한 달인지 확인
  if (!isQuarterStartMonth) {
    // 분기 시작 월이 아니면 인증 불필요 (단, 최초 가입 시는 예외)
    const hasAnyVerification = await db
      .collection('users')
      .doc(userId)
      .collection('verifications')
      .limit(1)
      .get();

    if (!hasAnyVerification.empty) {
      // 이미 과거에 인증한 적이 있으면 분기 시작 월까지 대기
      const nextQuarterMonth = getNextQuarterStartMonth(currentMonth);
      return {
        needsVerification: false,
        reason: `분기별 인증은 ${nextQuarterMonth}월에 진행됩니다.`,
        nextQuarter: getNextQuarter(currentQuarter)
      };
    }
  }

  // 4. 인증 필요
  return {
    needsVerification: true,
    reason: '당적 인증이 필요합니다.',
    currentQuarter: currentQuarter
  };
}

/**
 * 월(0-11)을 분기로 변환합니다.
 * @param {number} month - 월 (0-11)
 * @returns {number} 분기 (1-4)
 */
function getQuarterFromMonth(month) {
  if (month <= 2) return 1;  // 0-2 (1-3월)
  if (month <= 5) return 2;  // 3-5 (4-6월)
  if (month <= 8) return 3;  // 6-8 (7-9월)
  return 4;                  // 9-11 (10-12월)
}

/**
 * 다음 분기를 반환합니다.
 * @param {string} currentQuarter - 현재 분기 (예: "2025년 1분기")
 * @returns {string} 다음 분기
 */
function getNextQuarter(currentQuarter) {
  const match = currentQuarter.match(/(\d{4})년 (\d)분기/);
  if (!match) return '';

  let year = parseInt(match[1]);
  let quarter = parseInt(match[2]);

  quarter += 1;
  if (quarter > 4) {
    quarter = 1;
    year += 1;
  }

  return `${year}년 ${quarter}분기`;
}

/**
 * 다음 분기 시작 월을 반환합니다.
 * @param {number} currentMonth - 현재 월 (0-11)
 * @returns {number} 다음 분기 시작 월 (1-12)
 */
function getNextQuarterStartMonth(currentMonth) {
  // 분기 시작 월: 1월(0), 4월(3), 7월(6), 10월(9)
  if (currentMonth < 3) return 4;  // 1-3월 → 4월
  if (currentMonth < 6) return 7;  // 4-6월 → 7월
  if (currentMonth < 9) return 10; // 7-9월 → 10월
  return 1; // 10-12월 → 다음해 1월
}

/**
 * 납입연월이 현재 분기에 속하는지 검증합니다.
 * @param {string} paymentYearMonth - 납입연월 (YYYY-MM)
 * @param {string} currentQuarter - 현재 분기 (예: "2025년 1분기")
 * @returns {boolean} 유효 여부
 */
function validatePaymentMonth(paymentYearMonth, currentQuarter) {
  if (!paymentYearMonth || !currentQuarter) return false;

  // 분기에서 연도와 분기 추출
  const quarterMatch = currentQuarter.match(/(\d{4})년 (\d)분기/);
  if (!quarterMatch) return false;

  const year = parseInt(quarterMatch[1]);
  const quarter = parseInt(quarterMatch[2]);

  // 납입연월에서 연도와 월 추출
  const paymentMatch = paymentYearMonth.match(/(\d{4})-(\d{2})/);
  if (!paymentMatch) return false;

  const paymentYear = parseInt(paymentMatch[1]);
  const paymentMonth = parseInt(paymentMatch[2]);

  // 연도 불일치면 false
  if (paymentYear !== year) return false;

  // 분기별 유효 월 범위
  let validMonths = [];
  if (quarter === 1) validMonths = [1, 2, 3];
  else if (quarter === 2) validMonths = [4, 5, 6];
  else if (quarter === 3) validMonths = [7, 8, 9];
  else if (quarter === 4) validMonths = [10, 11, 12];

  return validMonths.includes(paymentMonth);
}

/**
 * 인증 결과를 Firestore에 저장합니다.
 * @param {string} userId - 사용자 ID
 * @param {Object} verificationData - 인증 데이터
 */
async function saveVerificationResult(userId, verificationData) {
  const verificationRef = db
    .collection('users')
    .doc(userId)
    .collection('verifications')
    .doc();

  await verificationRef.set(verificationData);

  // 사용자 프로필에 최신 인증 상태 업데이트
  await db.collection('users').doc(userId).update({
    verificationStatus: verificationData.status, // 'verified' 상태로 업데이트
    lastVerification: {
      quarter: verificationData.quarter,
      status: verificationData.status,
      verifiedAt: verificationData.verifiedAt
    }
  });
}

/**
 * 수동 검토 요청을 Firestore에 저장합니다.
 * @param {string} userId - 사용자 ID
 * @param {Object} requestData - 요청 데이터
 */
async function saveVerificationRequest(userId, requestData) {
  const requestRef = db
    .collection('verification_requests')
    .doc();

  await requestRef.set({
    userId: userId,
    ...requestData
  });

  // 사용자 프로필에 수동 검토 대기 상태 업데이트
  await db.collection('users').doc(userId).update({
    verificationStatus: 'pending_manual_review',
    lastVerification: {
      quarter: requestData.quarter || getCurrentQuarter(),
      status: 'pending_manual_review',
      requestedAt: admin.firestore.FieldValue.serverTimestamp(),
      type: requestData.type
    }
  });
}

module.exports = {
  verifyPartyCertificate,
  verifyPaymentReceipt,
  getVerificationHistory
};
