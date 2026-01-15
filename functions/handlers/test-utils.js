'use strict';

const { onRequest } = require('firebase-functions/v2/https');
const { db } = require('../utils/firebaseAdmin');

/**
 * 🧪 [TEST-UTILS] 당론 데이터 시딩용 HTTP 함수
 * curl "https://.../seedPartyStance"
 */
exports.seedPartyStance = onRequest({ cors: true }, async (req, res) => {
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
        createdAt: new Date()
    };

    try {
        const docId = 'yoon_sentencing_2026';
        await collectionRef.doc(docId).set(stanceData);

        res.json({
            success: true,
            message: `✅ 당론 데이터 삽입 완료: ${docId}`,
            data: stanceData
        });
    } catch (error) {
        console.error('❌ 데이터 삽입 실패:', error);
        res.status(500).json({ error: error.message });
    }
});
