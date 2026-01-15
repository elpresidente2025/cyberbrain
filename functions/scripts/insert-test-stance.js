'use strict';

// Firebase Admin 초기화 (로컬 실행용)
const admin = require('firebase-admin');
const serviceAccount = require('../../service-account.json'); // 로컬 테스트용 서비스 계정 키 필요

if (!admin.apps.length) {
    admin.initializeApp({
        credential: admin.credential.cert(serviceAccount)
    });
}

const db = admin.firestore();

async function insertTestStance() {
    const collectionRef = db.collection('party_stances');

    const stanceData = {
        title: '윤석열 사형 구형 및 내란 사건',
        isActive: true,
        keywords: ['윤석열', '사형', '내란', '구형'],
        stance: '사필귀정 (事必歸正)',
        logic_guide: `1. **[인과관계 명확화]**: "사형 구형 소식" 자체가 충격적인 것이 아니라, "12.3 내란 범죄"가 충격적인 사건이었고, "사형 구형"은 이에 대한 **당연한 심판(정의 실현)**임을 강조하십시오.
2. **[감정 통제]**: "안타깝다", "마음이 무겁다", "비극적 역사" 등 피고인을 동정하거나 상황을 비관하는 표현을 절대 쓰지 마십시오. 오직 냉철하게 **"법의 엄중함"**과 **"민주주의 회복"**에 초점을 맞추십시오.`,
        forbidden_phrases: [
            '충격적인 소식',
            '안타까운 일',
            '마음이 무겁다',
            '비극적 역사',
            '전직 대통령 예우'
        ],
        priority: 10,
        createdAt: admin.firestore.FieldValue.serverTimestamp()
    };

    try {
        // 키워드 기반 ID 생성 (중복 방지)
        const docId = 'yoon_sentencing_2026';
        await collectionRef.doc(docId).set(stanceData);
        console.log(`✅ [Success] 당론 데이터 삽입 완료: ${docId}`);
        console.log(stanceData);
    } catch (error) {
        console.error('❌ [Error] 데이터 삽입 실패:', error);
    }
}

insertTestStance();
