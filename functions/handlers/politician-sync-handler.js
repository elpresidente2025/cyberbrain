'use strict';

/**
 * functions/handlers/politician-sync-handler.js
 * 정치인 데이터 동기화 핸들러 (열린국회정보 API → Firestore)
 * 
 * - 일 1회 스케줄 실행 (오전 6시 KST)
 * - 수동 트리거 지원 (관리자용)
 */

const { onSchedule } = require('firebase-functions/v2/scheduler');
const { onCall } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { getOpenAssemblyApiKey, OPEN_ASSEMBLY_API_KEY } = require('../common/secrets');

// Firestore 초기화
let db;
function getDb() {
    if (!db) {
        if (!admin.apps.length) {
            admin.initializeApp();
        }
        db = admin.firestore();
    }
    return db;
}

/**
 * 열린국회정보 API에서 현역 국회의원 목록 가져오기
 */
async function fetchAssemblyMembers(apiKey) {
    const fetch = (await import('node-fetch')).default;

    // 열린국회정보 API - 국회의원 현황 조회
    // 참고: https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu
    const url = `https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu?Key=${apiKey}&Type=json&pIndex=1&pSize=400`;

    try {
        const response = await fetch(url, { timeout: 30000 });
        const data = await response.json();

        // API 응답 구조 확인
        const result = data?.nwvrqwxyaytdsfvhu?.[1]?.row || [];
        console.log(`📡 열린국회정보 API 응답: ${result.length}명 조회됨`);

        return result.map(member => ({
            name: member.HG_NM || '',           // 한글 이름
            party: member.POLY_NM || '무소속',   // 정당명
            district: member.ORIG_NM || '',      // 지역구
            position: '국회의원',
            assemblyId: member.MONA_CD || '',    // 의원 코드
            birthDate: member.BTH_DATE || '',    // 생년월일
            electionCount: member.REELE_GBN_NM || '', // 당선 횟수
            source: 'open_assembly',
            updatedAt: admin.firestore.FieldValue.serverTimestamp()
        }));
    } catch (error) {
        console.error('❌ 열린국회정보 API 호출 실패:', error);
        throw error;
    }
}

/**
 * Firestore에 정치인 데이터 저장
 */
async function savePoliticiansToFirestore(politicians) {
    const db = getDb();
    const batch = db.batch();
    const collectionRef = db.collection('shared').doc('politicians').collection('members');

    let count = 0;
    for (const politician of politicians) {
        if (politician.name) {
            const docRef = collectionRef.doc(politician.name);
            batch.set(docRef, politician, { merge: true });
            count++;
        }
    }

    await batch.commit();
    console.log(`✅ ${count}명의 정치인 데이터를 Firestore에 저장 완료`);

    // 동기화 메타데이터 저장
    await db.collection('shared').doc('politicians').set({
        lastSyncAt: admin.firestore.FieldValue.serverTimestamp(),
        memberCount: count,
        source: 'open_assembly'
    }, { merge: true });

    return count;
}

/**
 * 동기화 실행 함수
 */
async function runSync() {
    const apiKey = getOpenAssemblyApiKey();

    if (!apiKey) {
        throw new Error('OPEN_ASSEMBLY_API_KEY가 설정되지 않았습니다.');
    }

    console.log('🔄 정치인 데이터 동기화 시작...');

    // 1. API에서 데이터 가져오기
    const politicians = await fetchAssemblyMembers(apiKey);

    // 2. Firestore에 저장
    const savedCount = await savePoliticiansToFirestore(politicians);

    console.log(`🎉 동기화 완료: ${savedCount}명`);

    return { success: true, syncedCount: savedCount };
}

// ============================================================================
// 스케줄 함수: 매일 오전 6시 (KST) 실행
// ============================================================================
exports.scheduledPoliticianSync = onSchedule(
    {
        schedule: 'every day 06:00',
        timeZone: 'Asia/Seoul',
        secrets: [OPEN_ASSEMBLY_API_KEY]
    },
    async (event) => {
        console.log('⏰ 정치인 데이터 일일 동기화 시작 (Scheduled)');

        try {
            const result = await runSync();
            console.log('✅ 스케줄 동기화 완료:', result);
        } catch (error) {
            console.error('❌ 스케줄 동기화 실패:', error);
        }
    }
);

// ============================================================================
// 수동 트리거 함수: 관리자가 즉시 동기화
// ============================================================================
exports.syncPoliticiansManual = onCall(
    {
        secrets: [OPEN_ASSEMBLY_API_KEY]
    },
    async (request) => {
        // 관리자 권한 체크
        const uid = request.auth?.uid;
        if (!uid) {
            throw new Error('인증이 필요합니다.');
        }

        const db = getDb();
        const userDoc = await db.collection('users').doc(uid).get();
        const userData = userDoc.data();

        if (userData?.role !== 'admin' && !userData?.isAdmin) {
            throw new Error('관리자 권한이 필요합니다.');
        }

        console.log(`👤 관리자 ${uid}에 의한 수동 동기화 시작`);

        try {
            const result = await runSync();
            return { success: true, message: `${result.syncedCount}명 동기화 완료` };
        } catch (error) {
            console.error('❌ 수동 동기화 실패:', error);
            return { success: false, error: error.message };
        }
    }
);
