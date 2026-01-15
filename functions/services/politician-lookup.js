'use strict';

/**
 * functions/services/politician-lookup.js
 * 정치인 소속 정당 조회 및 관계 판단 서비스
 * 
 * 주요 기능:
 * 1. getPoliticianByName(name) - 이름으로 정치인 조회
 * 2. getRelationship(userParty, targetName) - 두 정치인 간 관계 판단
 * 3. syncFromOpenAssembly() - API에서 전체 데이터 동기화
 */

const admin = require('firebase-admin');

// Firestore 초기화 (이미 초기화된 경우 재사용)
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

// 메모리 캐시 (Cold Start 최적화)
const cache = new Map();
const CACHE_TTL = 1000 * 60 * 60; // 1시간

/**
 * 이름으로 정치인 정보 조회
 * @param {string} name - 정치인 이름 (예: "조경태")
 * @returns {Promise<Object|null>} 정치인 정보 또는 null
 */
async function getPoliticianByName(name) {
    if (!name || typeof name !== 'string') return null;

    const normalizedName = name.trim();

    // 1. 캐시 확인
    const cached = cache.get(normalizedName);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data;
    }

    // 2. Firestore 조회
    try {
        const db = getDb();
        const doc = await db.collection('shared').doc('politicians').collection('members').doc(normalizedName).get();

        if (doc.exists) {
            const data = doc.data();
            cache.set(normalizedName, { data, timestamp: Date.now() });
            return data;
        }

        // 3. 이름 검색 (부분 일치)
        const snapshot = await db.collection('shared').doc('politicians').collection('members')
            .where('name', '==', normalizedName)
            .limit(1)
            .get();

        if (!snapshot.empty) {
            const data = snapshot.docs[0].data();
            cache.set(normalizedName, { data, timestamp: Date.now() });
            return data;
        }

        return null;
    } catch (error) {
        console.error('정치인 조회 실패:', error);
        return null;
    }
}

/**
 * 두 정치인 간 관계 판단
 * @param {string} userParty - 사용자(화자)의 소속 정당
 * @param {string} targetName - 대상 정치인 이름
 * @returns {Promise<Object>} 관계 정보 { relationship, description, targetParty }
 */
async function getRelationship(userParty, targetName) {
    const target = await getPoliticianByName(targetName);

    if (!target) {
        return {
            relationship: 'unknown',
            description: null,
            targetParty: null
        };
    }

    const targetParty = target.party || '무소속';

    // 관계 판단 로직
    if (!userParty || userParty === '무소속') {
        return {
            relationship: 'neutral',
            description: `${targetParty} 소속`,
            targetParty
        };
    }

    if (userParty === targetParty) {
        return {
            relationship: 'ally',
            description: '같은 당 동료',
            targetParty
        };
    }

    return {
        relationship: 'rival',
        description: `타당(${targetParty}) 소속 경쟁자`,
        targetParty
    };
}

/**
 * 텍스트에서 정치인 이름 추출 및 관계 분석
 * @param {string} text - 분석할 텍스트
 * @param {string} userParty - 사용자 소속 정당
 * @returns {Promise<Array>} 감지된 정치인 및 관계 목록
 */
async function analyzeTextForPoliticians(text, userParty) {
    if (!text) return [];

    // 주요 정치인 이름 목록 (확장 가능)
    const knownPoliticians = [
        '윤석열', '이재명', '한동훈', '조경태', '박형준',
        '이준석', '안철수', '홍준표', '김기현', '나경원',
        // 추가 필요...
    ];

    const detected = [];

    for (const name of knownPoliticians) {
        if (text.includes(name)) {
            const rel = await getRelationship(userParty, name);
            if (rel.targetParty) {
                detected.push({
                    name,
                    ...rel
                });
            }
        }
    }

    return detected;
}

/**
 * 관계 정보를 프롬프트용 텍스트로 변환
 * @param {Array} detectedPoliticians - analyzeTextForPoliticians 결과
 * @returns {string} 프롬프트 주입용 텍스트
 */
function formatRelationshipsForPrompt(detectedPoliticians) {
    if (!detectedPoliticians || detectedPoliticians.length === 0) {
        return '';
    }

    const lines = detectedPoliticians.map(p => {
        return `- ${p.name}: ${p.description || p.targetParty + ' 소속'}`;
    });

    return `
[자동 감지된 인물 관계]
${lines.join('\n')}
※ 위 관계를 참고하여 톤앤매너를 조절하세요.
`;
}

/**
 * 열린국회정보 API에서 데이터 동기화
 * (Scheduled Function에서 호출)
 */
async function syncFromOpenAssembly(apiKey) {
    // TODO: 열린국회정보 API 연동 구현
    // API 엔드포인트: https://open.assembly.go.kr/portal/openapi/...
    console.log('syncFromOpenAssembly: Not yet implemented');
    return { synced: 0 };
}

module.exports = {
    getPoliticianByName,
    getRelationship,
    analyzeTextForPoliticians,
    formatRelationshipsForPrompt,
    syncFromOpenAssembly
};
