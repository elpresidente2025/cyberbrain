const { onDocumentUpdated } = require('firebase-functions/v2/firestore');
const { extractStyleFromText } = require('../utils/style-analyzer');
const { db } = require('../utils/firebaseAdmin');

/**
 * 사용자 프로필(Bio) 변경 시 스타일 분석 자동 수행
 * - users 컬렉션의 문서가 업데이트될 때 실행됨
 * - bio 필드가 변경되었을 때만 스타일 분석 트리거
 */
exports.analyzeUserStyleOnUpdate = onDocumentUpdated('users/{userId}', async (event) => {
    const newUser = event.data.after.data();
    const oldUser = event.data.before.data();
    const userId = event.params.userId;

    // Bio가 없거나, 변경되지 않았으면 무시
    if (!newUser.bio || newUser.bio === oldUser.bio) {
        return null;
    }

    // 글자 수가 너무 적으면 분석 가치가 없음 (50자 미만)
    if (newUser.bio.length < 50) {
        console.log(`ℹ️ [StyleTrigger] Bio가 너무 짧아 분석 건너뜀 (User: ${userId})`);
        return null;
    }

    console.log(`🎨 [StyleTrigger] 사용자 스타일 분석 시작 (User: ${userId})`);

    try {
        // 스타일 분석 수행 (LLM + 정량분석)
        const styleProfile = await extractStyleFromText(newUser.bio);
        if (!styleProfile) {
            console.warn(`⚠️ [StyleTrigger] 스타일 분석 결과가 비어있음 (User: ${userId})`);
            return null;
        }

        // 분석 결과를 사용자 문서에 업데이트 (styleProfile 필드)
        // 무한 루프 방지: styleProfile 필드 변경은 이 트리거를 다시 실행시키지 않도록 주의해야 하지만,
        // 위에서 bio 변경 여부를 체크하므로 안전함.
        await event.data.after.ref.update({
            styleProfile: styleProfile,
            styleAnalyzedAt: new Date().toISOString()
        });

        console.log(`✅ [StyleTrigger] 스타일 분석 완료 및 저장 (User: ${userId})`);
        return styleProfile;

    } catch (error) {
        console.error(`❌ [StyleTrigger] 스타일 분석 중 오류 발생 (User: ${userId}):`, error);
        return null;
    }
});
