
const { db } = require('../utils/firebaseAdmin');
const { https } = require('firebase-functions');
const { getNaverAuth, naverAuthMiddleware } = require('../common/auth');

exports.getPost = https.onCall(async (data, context) => {
    const { postId } = data;
    const { uid } = getNaverAuth(context);

    if (!uid) {
        throw new https.HttpsError('unauthenticated', '인증되지 않은 사용자입니다.');
    }

    if (!postId) {
        throw new https.HttpsError('invalid-argument', '원고 ID가 필요합니다.');
    }

    try {
        const postDoc = await db.collection('users').doc(uid).collection('posts').doc(postId).get();

        if (!postDoc.exists) {
            throw new https.HttpsError('not-found', '해당 원고를 찾을 수 없습니다.');
        }

        const post = { id: postDoc.id, ...postDoc.data() };
        return { post };
    } catch (error) {
        console.error('Error fetching post:', error);
        throw new https.HttpsError('internal', '원고를 불러오는 중 오류가 발생했습니다.');
    }
});
