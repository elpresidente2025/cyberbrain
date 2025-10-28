const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');

exports.mergeDuplicateUser = onCall({
  region: 'asia-northeast3',
  cors: true
}, async (request) => {
  const { sourceUid, targetUid } = request.data;

  if (!sourceUid || !targetUid) {
    throw new HttpsError('invalid-argument', 'sourceUid와 targetUid가 필요합니다.');
  }

  try {
    // 1. source 문서 읽기
    const sourceDoc = await db.collection('users').doc(sourceUid).get();
    if (!sourceDoc.exists) {
      throw new HttpsError('not-found', `source 문서를 찾을 수 없습니다: ${sourceUid}`);
    }

    // 2. target 문서 읽기
    const targetDoc = await db.collection('users').doc(targetUid).get();
    if (!targetDoc.exists) {
      throw new HttpsError('not-found', `target 문서를 찾을 수 없습니다: ${targetUid}`);
    }

    const sourceData = sourceDoc.data();
    const targetData = targetDoc.data();

    // 3. source에만 있는 필드 추출
    const fieldsToMerge = {};
    for (const [key, value] of Object.entries(sourceData)) {
      if (!(key in targetData) || targetData[key] === '' || targetData[key] === null) {
        fieldsToMerge[key] = value;
      }
    }

    // 4. target 문서에 병합
    if (Object.keys(fieldsToMerge).length > 0) {
      await db.collection('users').doc(targetUid).update({
        ...fieldsToMerge,
        updatedAt: admin.firestore.FieldValue.serverTimestamp()
      });
    }

    // 5. source 문서 삭제
    await db.collection('users').doc(sourceUid).delete();

    return {
      success: true,
      message: '중복 계정이 병합되고 삭제되었습니다.',
      mergedFields: Object.keys(fieldsToMerge),
      sourceUid,
      targetUid
    };
  } catch (error) {
    console.error('병합 실패:', error);
    throw new HttpsError('internal', '병합 실패: ' + error.message);
  }
});
