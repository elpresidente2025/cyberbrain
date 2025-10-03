'use strict';

const { HttpsError, onCall } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { httpWrap } = require('../common/http-wrap');
const { auth } = require('../common/auth');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { fetchNaverNews, formatNewsForPrompt, shouldFetchNews } = require('../services/news-fetcher');

/**
 * 怨듬갚 ?쒖쇅 湲?먯닔 怨꾩궛 (Java 肄붾뱶? ?숈씪??濡쒖쭅)
 * @param {string} str - 怨꾩궛??臾몄옄??
 * @returns {number} 怨듬갚???쒖쇅??湲?먯닔
 */
function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i++) {
    if (!/\s/.test(str.charAt(i))) { // 怨듬갚 臾몄옄媛 ?꾨땶 寃쎌슦
      count++;
    }
  }
  return count;
}

/**
 * Bio 硫뷀??곗씠?곕? 湲곕컲?쇰줈 媛쒖씤?붾맂 ?먭퀬 ?묒꽦 ?뚰듃瑜??앹꽦?⑸땲??
 * @param {Object} bioMetadata - 異붿텧???먭린?뚭컻 硫뷀??곗씠??
 * @returns {string} 媛쒖씤???뚰듃 臾몄옄??
 */
function generatePersonalizedHints(bioMetadata) {
  if (!bioMetadata) return '';

  const hints = [];
  
  // ?뺤튂???깊뼢 湲곕컲 ?뚰듃
  if (bioMetadata.politicalStance?.progressive > 0.7) {
    hints.push('蹂?붿? ?곸떊??媛뺤“?섎뒗 吏꾨낫??愿?먯쑝濡??묒꽦');
  } else if (bioMetadata.politicalStance?.conservative > 0.7) {
    hints.push('?덉젙?깃낵 ?꾪넻 媛移섎? 以묒떆?섎뒗 蹂댁닔??愿?먯쑝濡??묒꽦');
  } else if (bioMetadata.politicalStance?.moderate > 0.8) {
    hints.push('洹좏삎?≫엺 以묐룄??愿?먯뿉???ㅼ뼇???섍껄???ъ슜?섏뿬 ?묒꽦');
  }

  // ?뚰넻 ?ㅽ???湲곕컲 ?뚰듃
  const commStyle = bioMetadata.communicationStyle;
  if (commStyle?.tone === 'warm') {
    hints.push('?곕쑜?섍퀬 移쒓렐???댁“ ?ъ슜');
  } else if (commStyle?.tone === 'formal') {
    hints.push('寃⑹떇?덇퀬 ?꾨Ц?곸씤 ?댁“ ?ъ슜');
  }
  
  if (commStyle?.approach === 'inclusive') {
    hints.push('紐⑤뱺 怨꾩링???꾩슦瑜대뒗 ?ъ슜???묎렐');
  } else if (commStyle?.approach === 'collaborative') {
    hints.push('?묐젰怨??뚰넻??媛뺤“?섎뒗 ?묒뾽???묎렐');
  }

  // ?뺤콉 愿?щ텇??湲곕컲 ?뚰듃
  const topPolicy = Object.entries(bioMetadata.policyFocus || {})
    .sort(([,a], [,b]) => b.weight - a.weight)[0];
    
  if (topPolicy && topPolicy[1].weight > 0.6) {
    const policyNames = {
      economy: '寃쎌젣?뺤콉',
      education: '援먯쑁?뺤콉', 
      welfare: '蹂듭??뺤콉',
      environment: '?섍꼍?뺤콉',
      security: '?덈낫?뺤콉',
      culture: '臾명솕?뺤콉'
    };
    hints.push(`${policyNames[topPolicy[0]] || topPolicy[0]} 愿?먯뿉???묎렐`);
  }

  // 吏???곌???湲곕컲 ?뚰듃
  if (bioMetadata.localConnection?.strength > 0.8) {
    hints.push('吏???꾩븞怨?二쇰??ㅼ쓽 ?ㅼ젣 寃쏀뿕???곴레 諛섏쁺');
    if (bioMetadata.localConnection.keywords?.length > 0) {
      hints.push(`吏???ㅼ썙???쒖슜: ${bioMetadata.localConnection.keywords.slice(0, 3).join(', ')}`);
    }
  }

  // ?앹꽦 ?좏샇??湲곕컲 ?뚰듃
  const prefs = bioMetadata.generationProfile?.likelyPreferences;
  if (prefs?.includePersonalExperience > 0.8) {
    hints.push('媛쒖씤??寃쏀뿕怨??щ?瑜??띾??섍쾶 ?ы븿');
  }
  if (prefs?.useStatistics > 0.7) {
    hints.push('援ъ껜???섏튂? ?듦퀎 ?곗씠?곕? ?곸젅???쒖슜');
  }
  if (prefs?.focusOnFuture > 0.7) {
    hints.push('誘몃옒 鍮꾩쟾怨?諛쒖쟾 諛⑺뼢???쒖떆');
  }

  return hints.join(' | ');
}

/**
 * ?ъ슜??媛쒖씤???뺣낫瑜?湲곕컲?쇰줈 ?섎Ⅴ?뚮굹 ?뚰듃瑜??앹꽦?⑸땲??
 * @param {Object} userProfile - ?ъ슜???꾨줈???뺣낫
 * @param {string} category - 湲 移댄뀒怨좊━
 * @param {string} topic - 湲 二쇱젣
 * @returns {string} ?섎Ⅴ?뚮굹 ?뚰듃 臾몄옄??
 */
function generatePersonaHints(userProfile, category, topic) {
  if (!userProfile) return '';
  
  const hints = [];
  const topicLower = topic ? topic.toLowerCase() : '';
  
  // 移댄뀒怨좊━蹂?愿?⑤룄 ?믪? ?뺣낫 ?곗꽑 ?좏깮
  const relevantInfo = getRelevantPersonalInfo(userProfile, category, topicLower);
  
  // ?좏깮???뺣낫留??먯뿰?ㅻ읇寃?援ъ꽦
  if (relevantInfo.age) {
    hints.push(relevantInfo.age);
  }
  
  if (relevantInfo.family) {
    hints.push(relevantInfo.family);
  }
  
  if (relevantInfo.background) {
    hints.push(relevantInfo.background);
  }
  
  if (relevantInfo.experience) {
    hints.push(relevantInfo.experience);
  }
  
  if (relevantInfo.committees && relevantInfo.committees.length > 0) {
    hints.push(`${relevantInfo.committees.join(', ')} ?쒕룞 寃쏀뿕??諛뷀깢?쇰줈`);
  }
  
  if (relevantInfo.connection) {
    hints.push(relevantInfo.connection);
  }
  
  // X(?몄쐞?? ?꾨━誘몄뾼 援щ룆 ?щ???SNS 蹂????湲?먯닔 ?쒗븳 泥댄겕?⑹씠誘濡??섎Ⅴ?뚮굹??諛섏쁺?섏? ?딆쓬
  
  const persona = hints.filter(h => h).join(' ');
  return persona ? `[?묒꽦 愿?? ${persona}]` : '';
}

/**
 * 湲 移댄뀒怨좊━? 二쇱젣???곕씪 愿?⑥꽦 ?믪? 媛쒖씤???뺣낫留??좊퀎?⑸땲??
 */
function getRelevantPersonalInfo(userProfile, category, topicLower) {
  const result = {};
  
  // ?곕졊? (?쇱긽 ?뚰넻, 媛議??≪븘 愿??二쇱젣?먯꽌 愿?⑥꽦 ?믪쓬)
  if (category === 'daily-communication' || 
      topicLower.includes('family') || topicLower.includes('youth') || topicLower.includes('romance')) {
    if (userProfile.ageDecade) {
      result.age = userProfile.ageDetail ? 
        `${userProfile.ageDecade} ${userProfile.ageDetail}` : userProfile.ageDecade;
    }
  }
  
  // 媛議??곹솴 (援먯쑁, 蹂듭?, ?쇱긽 ?뚰넻?먯꽌 愿?⑥꽦 ?믪쓬)
  if (category === 'daily-communication' || 
      topicLower.includes('援먯쑁') || topicLower.includes('?≪븘') || topicLower.includes('蹂듭?')) {
    if (userProfile.familyStatus) {
      const familyMap = {
        '?먮??덉쓬': '???꾩씠??遺紐⑤줈??,
        '?쒕?紐?: '?쒕?紐?媛?뺤쓽 寃쏀뿕??媛吏?,
        '湲고샎': '媛?뺤쓣 袁몃━硫?,
        '誘명샎': '?딆? ?몃?濡쒖꽌'
      };
      result.family = familyMap[userProfile.familyStatus];
    }
  }
  
  // 諛곌꼍 寃쎈젰 (愿???뺤콉 遺꾩빞?먯꽌 愿?⑥꽦 ?믪쓬)
  if (userProfile.backgroundCareer) {
    const careerRelevance = {
      '援먯쑁??: ['援먯쑁', '?숆탳', '?숈깮', '援먯궗'],
      '?ъ뾽媛': ['寃쎌젣', '?뚯긽怨듭씤', '?먯쁺??, '李쎌뾽'],
      '怨듬Т??: ['?됱젙', '?뺤콉', '怨듦났?쒕퉬??],
      '?섎즺??: ['?섎즺', '嫄닿컯', '肄붾줈??, '蹂닿굔'],
      '踰뺤“??: ['踰?, '?쒕룄', '?뺤쓽', '沅뚮━']
    };
    
    const relevantKeywords = careerRelevance[userProfile.backgroundCareer] || [];
    const isRelevant = relevantKeywords.some(keyword => topicLower.includes(keyword));
    
    if (isRelevant) {
      result.background = `${userProfile.backgroundCareer} 異쒖떊?쇰줈??;
    }
  }
  
  // ?뺤튂 寃쏀뿕 (?섏젙?쒕룞 蹂닿퀬, ?뺤콉 ?쒖븞?먯꽌 愿?⑥꽦 ?믪쓬)
  if (category === 'activity-report' || category === 'policy-proposal') {
    if (userProfile.politicalExperience) {
      const expMap = {
        '珥덉꽑': '珥덉꽑 ?섏썝?쇰줈???좎꽑??愿?먯뿉??,
        '?ъ꽑': '?섏젙 寃쏀뿕??諛뷀깢?쇰줈',
        '3???댁긽': '?띾????섏젙 寃쏀뿕?쇰줈',
        '?뺤튂 ?좎씤': '?덈줈???쒓컖?먯꽌'
      };
      result.experience = expMap[userProfile.politicalExperience];
    }
  }
  
  // ?뚯냽 ?꾩썝??(愿??遺꾩빞?먯꽌留??멸툒)
  if (userProfile.committees && userProfile.committees.length > 0) {
    const validCommittees = userProfile.committees.filter(c => c && c !== '');
    const relevantCommittees = validCommittees.filter(committee => {
      const committeeKeywords = {
        '援먯쑁?꾩썝??: ['援먯쑁', '?숆탳', '?숈깮', '???],
        '蹂닿굔蹂듭??꾩썝??: ['蹂듭?', '?섎즺', '嫄닿컯', '?뚮큵'],
        '援?넗援먰넻?꾩썝??: ['援먰넻', '二쇳깮', '?꾨줈', '嫄댁꽕'],
        '?섍꼍?몃룞?꾩썝??: ['?섍꼍', '?몃룞', '?쇱옄由?],
        '?ъ꽦媛議깆쐞?먰쉶': ['?ъ꽦', '媛議?, '?≪븘', '異쒖궛']
      };
      
      const keywords = committeeKeywords[committee] || [];
      return keywords.some(keyword => topicLower.includes(keyword));
    });
    
    if (relevantCommittees.length > 0) {
      result.committees = relevantCommittees;
    }
  }
  
  // 吏???곌퀬 (吏???꾩븞?먯꽌 愿?⑥꽦 ?믪쓬)
  if (category === 'local-issues' || topicLower.includes('吏??) || topicLower.includes('?곕━ ?숇꽕')) {
    if (userProfile.localConnection) {
      const connectionMap = {
        '?좊컯??: '吏???좊컯?대줈??,
        '?ㅻ옒 嫄곗＜': '?ㅻ옯?숈븞 ??吏??뿉 ?대㈃??,
        '?댁＜誘?: '?吏?먯꽌 ?????吏??쓣 ????怨좏뼢?쇰줈 ?쇱?',
        '洹??: '怨좏뼢?쇰줈 ?뚯븘???
      };
      result.connection = connectionMap[userProfile.localConnection];
    }
  }
  
  return result;
}
const { buildDailyCommunicationPrompt } = require('../templates/prompts/daily-communication');

// 媛꾨떒???묐떟 ?ы띁
const ok = (data) => ({ success: true, ...data });
const okMessage = (message) => ({ success: true, message });

// ?ъ슜???ъ뒪??紐⑸줉 議고쉶
exports.getUserPosts = wrap(async (req) => {
  const { uid } = await auth(req);
  console.log('POST getUserPosts ?몄텧:', { userId: uid });

  try {
    const postsSnapshot = await db.collection('posts')
      .where('userId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(50)
      .get();

    const posts = [];
    postsSnapshot.forEach(doc => {
      const data = doc.data();
      // draft ?곹깭媛 ?꾨땶 ?ъ뒪?몃쭔 ?ы븿 (?대씪?댁뼵???꾪꽣留?
      if (data.status !== 'draft') {
        posts.push({
          id: doc.id,
          ...data,
          createdAt: data.createdAt?.toDate?.()?.toISOString() || null,
          updatedAt: data.updatedAt?.toDate?.()?.toISOString() || null
        });
      }
    });

    console.log('POST getUserPosts ?깃났:', { count: posts.length });
    return ok({ posts });
  } catch (error) {
    console.error('POST getUserPosts ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?ъ뒪??紐⑸줉??遺덈윭?ㅻ뒗???ㅽ뙣?덉뒿?덈떎.');
  }
});

// ?뱀젙 ?ъ뒪??議고쉶
exports.getPost = wrap(async (req) => {
  const { uid } = await auth(req);
  const { postId } = req.data || {};
  console.log('POST getPost ?몄텧:', { userId: uid, postId });

  if (!postId) {
    throw new HttpsError('invalid-argument', '?ъ뒪??ID瑜??낅젰?댁＜?몄슂.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '?ъ뒪?몃? 李얠쓣 ???놁뒿?덈떎.');
    }

    const data = postDoc.data();
    if (data.userId !== uid) {
      throw new HttpsError('permission-denied', '?ъ뒪?몃? 議고쉶??沅뚰븳???놁뒿?덈떎.');
    }

    const post = {
      id: postDoc.id,
      ...data,
      createdAt: data.createdAt?.toDate?.()?.toISOString() || null,
      updatedAt: data.updatedAt?.toDate?.()?.toISOString() || null
    };

    console.log('POST getPost ?깃났:', postId);
    return ok({ post });
  } catch (error) {
    if (error.code) throw error;
    console.error('POST getPost ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?ъ뒪?몃? 遺덈윭?ㅻ뒗???ㅽ뙣?덉뒿?덈떎.');
  }
});

// ?ъ뒪???낅뜲?댄듃
exports.updatePost = wrap(async (req) => {
  const { uid } = await auth(req);
  const { postId, updates } = req.data || {};
  console.log('POST updatePost ?몄텧:', { userId: uid, postId });

  if (!postId || !updates) {
    throw new HttpsError('invalid-argument', '?ъ뒪??ID? ?섏젙 ?곗씠?곕? ?낅젰?댁＜?몄슂.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '?ъ뒪?몃? 李얠쓣 ???놁뒿?덈떎.');
    }

    const current = postDoc.data() || {};
    if (current.userId !== uid) {
      throw new HttpsError('permission-denied', '?ъ뒪?몃? ?섏젙??沅뚰븳???놁뒿?덈떎.');
    }

    const allowed = ['title', 'content', 'category', 'subCategory', 'keywords', 'status'];
    const sanitized = {};
    for (const k of allowed) {
      if (updates[k] !== undefined) sanitized[k] = updates[k];
    }
    
    if (sanitized.content) {
      sanitized.wordCount = String(sanitized.content).replace(/<[^>]*>/g, '').replace(/\s/g, '').length;
    }
    sanitized.updatedAt = admin.firestore.FieldValue.serverTimestamp();

    await db.collection('posts').doc(postId).update(sanitized);
    console.log('POST updatePost ?깃났:', postId);
    return okMessage('?ъ뒪?멸? ?깃났?곸쑝濡??섏젙?섏뿀?듬땲??');
  } catch (error) {
    if (error.code) throw error;
    console.error('POST updatePost ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?ъ뒪???섏젙???ㅽ뙣?덉뒿?덈떎.');
  }
});

// ?ъ뒪????젣
exports.deletePost = wrap(async (req) => {
  const { uid } = await auth(req);
  const { postId } = req.data || {};
  console.log('POST deletePost ?몄텧:', { userId: uid, postId });

  if (!postId) {
    throw new HttpsError('invalid-argument', '?ъ뒪??ID瑜??낅젰?댁＜?몄슂.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '?ъ뒪?몃? 李얠쓣 ???놁뒿?덈떎.');
    }
    
    const data = postDoc.data() || {};
    if (data.userId !== uid) {
      throw new HttpsError('permission-denied', '?ъ뒪?몃? ??젣??沅뚰븳???놁뒿?덈떎.');
    }

    await db.collection('posts').doc(postId).delete();
    console.log('POST deletePost ?깃났:', postId);
    return okMessage('?ъ뒪?멸? ?깃났?곸쑝濡???젣?섏뿀?듬땲??');
  } catch (error) {
    if (error.code) throw error;
    console.error('POST deletePost ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?ъ뒪????젣???ㅽ뙣?덉뒿?덈떎.');
  }
});

// ?ъ슜???쒗븳 泥댄겕
exports.checkUsageLimit = wrap(async (req) => {
  const { uid } = await auth(req);
  console.log('USAGE checkUsageLimit ?몄텧:', { userId: uid });

  try {
    const now = new Date();
    const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const snap = await db.collection('posts')
      .where('userId', '==', uid)
      .where('createdAt', '>=', admin.firestore.Timestamp.fromDate(thisMonth))
      .get();

    const used = snap.size;
    const limit = 50;
    
    console.log('USAGE checkUsageLimit ?깃났:', { used, limit });
    return ok({
      postsGenerated: used,
      monthlyLimit: limit,
      canGenerate: used < limit,
      remainingPosts: Math.max(0, limit - used),
    });
  } catch (error) {
    console.error('USAGE ?ㅻ쪟:', error.message);
    if (error.code === 'failed-precondition') {
      return ok({ 
        postsGenerated: 0, 
        monthlyLimit: 50, 
        canGenerate: true, 
        remainingPosts: 50 
      });
    }
    throw new HttpsError('internal', '?ъ슜?됱쓣 ?뺤씤?섎뒗???ㅽ뙣?덉뒿?덈떎.');
  }
});

// 吏꾩쭨 AI ?먭퀬 ?앹꽦 ?⑥닔 (諛깆뾽?먯꽌 蹂듦뎄) - HTTP 踰꾩쟾
exports.generatePosts = httpWrap(async (req) => {
  console.log('?뵦 generatePosts HTTP ?쒖옉');

  let uid;
  let decodedToken = null;

  // ?곗씠??異붿텧 - Firebase SDK? HTTP ?붿껌 紐⑤몢 泥섎━
  let requestData = req.data || req.rawRequest?.body || {};

  // 以묒꺽??data 援ъ“ 泥섎━ (Firebase SDK?먯꽌 {data: {?ㅼ젣?곗씠??} ?뺥깭濡??????덉쓬)
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // ?ъ슜???몄쬆 ?곗씠???뺤씤 (紐⑤뱺 ?ъ슜?먮뒗 ?ㅼ씠踰?濡쒓렇??
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    console.log('?벑 ?ъ슜???몄쬆 泥섎━:', requestData.__naverAuth.uid);
    uid = requestData.__naverAuth.uid;
    // ?몄쬆 ?뺣낫 ?쒓굅 (泥섎━ ?꾨즺)
    delete requestData.__naverAuth;
  } else {
    const authHeader = (req.rawRequest && (req.rawRequest.headers.authorization || req.rawRequest.headers.Authorization)) || '';
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const idToken = authHeader.split('Bearer ')[1];
      try {
        const verified = await admin.auth().verifyIdToken(idToken);
        uid = verified.uid;
      } catch (authError) {
        console.error('ID token verify failed:', authError);
        throw new HttpsError('unauthenticated', '유효하지 않은 인증 토큰입니다.');
      }
    } else {
      console.error('인증 정보 누락:', requestData);
      throw new HttpsError('unauthenticated', '인증이 필요합니다.');
    }
  }

  console.log('???ъ슜???몄쬆 ?깃났:', uid);

  console.log('?뵇 ?꾩껜 ?붿껌 援ъ“:', JSON.stringify({
    data: req.data,
    body: req.rawRequest?.body,
    method: req.rawRequest?.method,
    headers: req.rawRequest?.headers
  }, null, 2));

  // ?곗씠?곕뒗 ?대? ?꾩뿉??異붿텧?덉쑝誘濡?requestData 蹂???ъ슜
  const useBonus = requestData?.useBonus || false;

  // ?댁젣 data瑜?requestData濡??좊떦
  const data = requestData;
  
  console.log('?뵦 generatePosts ?쒖옉 (?ㅼ젣 AI ?앹꽦) - 諛쏆? ?곗씠??', JSON.stringify(data, null, 2));
  
  // prompt ?꾨뱶 ?곗꽑 泥섎━
  const topic = data.prompt || data.topic || '';
  const category = data.category || '';
  const modelName = data.modelName || 'gemini-1.5-flash'; // 湲곕낯媛믪? 1.5-flash
  const targetWordCount = data.wordCount || 1700; // ?ъ슜???붿껌 湲?먯닔 (湲곕낯媛?1700)
  
  console.log('?뵇 寃利?以?', { 
    topic: topic ? topic.substring(0, 50) : topic, 
    category,
    modelName,
    rawPrompt: data.prompt,
    rawTopic: data.topic,
    fullTopic: topic
  });
  if (!topic || typeof topic !== 'string' || topic.trim().length === 0) {
    console.error('??二쇱젣 寃利??ㅽ뙣:', { topic, type: typeof topic });
    throw new HttpsError('invalid-argument', '二쇱젣瑜??낅젰?댁＜?몄슂.');
  }
  
  if (!category || typeof category !== 'string' || category.trim().length === 0) {
    console.error('??移댄뀒怨좊━ 寃利??ㅽ뙣:', { category, type: typeof category });
    throw new HttpsError('invalid-argument', '移댄뀒怨좊━瑜??좏깮?댁＜?몄슂.');
  }
  
  console.log(`???곗씠??寃利??듦낵: 二쇱젣="${topic.substring(0, 50)}..." 移댄뀒怨좊━="${category}"`);
  
  try {
    // ?ъ슜???꾨줈??諛?Bio 硫뷀??곗씠??媛?몄삤湲?
    let userProfile = {};
    let bioMetadata = null;
    let personalizedHints = '';
    let dailyLimitWarning = false;

    try {
      // ?ъ슜??湲곕낯 ?뺣낫 議고쉶
      console.log(`?뵇 ?꾨줈??議고쉶 ?쒕룄 - UID: ${uid}, 湲몄씠: ${uid?.length}`);
      const userDoc = await Promise.race([
        db.collection('users').doc(uid).get(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('?꾨줈??議고쉶 ??꾩븘??)), 5000))
      ]);

      console.log(`?뱥 ?꾨줈??臾몄꽌 議댁옱 ?щ?: ${userDoc.exists}`);
      if (userDoc.exists) {
        userProfile = userDoc.data();
        console.log('???ъ슜???꾨줈??議고쉶 ?깃났:', userProfile.name || 'Unknown');
        
        // ?섎（ ?앹꽦???쒗븳 ?뺤씤 (愿由ъ옄???쒗븳 ?놁쓬)
        const isAdmin = userProfile.isAdmin === true;

        if (!isAdmin) {
          // ?쇰컲 ?ъ슜???섎（ 3??珥덇낵 ??寃쎄퀬 (李⑤떒?섏????딆쓬)
          const today = new Date();
          const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
          const dailyUsage = userProfile.dailyUsage || {};
          const todayGenerated = dailyUsage[todayKey] || 0;

          if (todayGenerated >= 3) {
            console.log('?좑툘 ?섎（ 3??珥덇낵 ?앹꽦 - 寃쎄퀬留??쒖떆');
            dailyLimitWarning = true;
            // 李⑤떒?섏? ?딄퀬 怨꾩냽 吏꾪뻾 (寃쎄퀬 硫붿떆吏???묐떟???ы븿)
          }

          console.log('???쇰컲 ?ъ슜???섎（ ?ъ슜???뺤씤:', { todayGenerated, warning: todayGenerated >= 3 });
        } else {
          console.log('??愿由ъ옄 怨꾩젙 - ?섎（ ?앹꽦???쒗븳 ?고쉶');
        }

        // 蹂대꼫???ъ슜 ?щ????곕Ⅸ ?ъ슜 媛?λ웾 ?뺤씤
        if (useBonus) {
          const usage = userProfile.usage || { bonusGenerated: 0, bonusUsed: 0 };
          const availableBonus = Math.max(0, usage.bonusGenerated - (usage.bonusUsed || 0));
          
          if (availableBonus <= 0) {
            throw new HttpsError('failed-precondition', '?ъ슜 媛?ν븳 蹂대꼫???먭퀬媛 ?놁뒿?덈떎.');
          }
          
          console.log('??蹂대꼫???먭퀬 ?ъ슜 媛??', { availableBonus });
        } else {
          // ?쇰컲 ?ъ슜???뺤씤 (愿由ъ옄???쒗븳 ?놁쓬)
          if (!isAdmin) {
            const usage = userProfile.usage || { postsGenerated: 0, monthlyLimit: 50 };

            if (usage.postsGenerated >= usage.monthlyLimit) {
              throw new HttpsError('resource-exhausted', '?붽컙 ?앹꽦 ?쒕룄瑜?珥덇낵?덉뒿?덈떎.');
            }

            console.log('???쇰컲 ?먭퀬 ?앹꽦 媛??', {
              current: usage.postsGenerated,
              limit: usage.monthlyLimit
            });
          } else {
            console.log('??愿由ъ옄 怨꾩젙 - ?붽컙 ?앹꽦???쒗븳 ?고쉶');
          }
        }
      }

      // Bio 硫뷀??곗씠??議고쉶 (?좏깮??
      console.log(`?뵇 Bio 硫뷀??곗씠??議고쉶 ?쒕룄 - UID: ${uid}`);
      const bioDoc = await db.collection('bios').doc(uid).get();
      console.log(`?뱥 Bio 臾몄꽌 議댁옱 ?щ?: ${bioDoc.exists}`);
      if (bioDoc.exists && bioDoc.data().extractedMetadata) {
        bioMetadata = bioDoc.data().extractedMetadata;
        
        // 硫뷀??곗씠??湲곕컲 媛쒖씤???뚰듃 ?앹꽦
        personalizedHints = generatePersonalizedHints(bioMetadata);
        console.log('??Bio 硫뷀??곗씠???쒖슜:', Object.keys(bioMetadata));
        
        // Bio ?ъ슜 ?듦퀎 ?낅뜲?댄듃
        await db.collection('bios').doc(uid).update({
          'usage.generatedPostsCount': admin.firestore.FieldValue.increment(1),
          'usage.lastUsedAt': admin.firestore.FieldValue.serverTimestamp()
        });
      }
      
      // 媛쒖씤???뺣낫 湲곕컲 ?섎Ⅴ?뚮굹 ?뚰듃 ?앹꽦 諛?異붽?
      const personaHints = generatePersonaHints(userProfile, category, topic);
      if (personaHints) {
        personalizedHints = personalizedHints ? `${personalizedHints} | ${personaHints}` : personaHints;
        console.log('???섎Ⅴ?뚮굹 ?뚰듃 異붽?:', personaHints);
      }

    } catch (profileError) {
      console.error('???꾨줈??Bio 議고쉶 ?ㅽ뙣:', {
        error: profileError.message,
        stack: profileError.stack,
        uid: uid,
        uidType: typeof uid,
        uidLength: uid?.length
      });

      // ?꾨줈?꾩씠 ?덉뼱???섎뒗 ?ъ슜?먯엯?덈떎
      throw new HttpsError('internal', `?꾨줈??議고쉶 ?ㅽ뙣: ${profileError.message}`);
    }

    // ?ъ슜???곹깭???곕Ⅸ ???ㅼ젙 諛??몄묶 寃곗젙
    const statusConfig = {
      '?꾩뿭': {
        guideline: '?꾩뿭 ?섏썝?쇰줈??寃쏀뿕怨??깃낵瑜?諛뷀깢?쇰줈 ???댁슜???ы븿?섏꽭?? ?ㅼ젣 ?섏젙?쒕룞 寃쏀뿕???멸툒?????덉뒿?덈떎.',
        title: userProfile.position || '?섏썝'
      },
      '?꾨낫': {
        guideline: '?꾨낫?먮줈???뺤콉怨?怨듭빟??以묒떖?쇰줈 ???댁슜???묒꽦?섏꽭?? 誘몃옒 鍮꾩쟾怨?援ъ껜??怨꾪쉷???쒖떆?섏꽭??',
        title: `${userProfile.position || ''}?꾨낫`.replace('?섏썝?꾨낫', '?꾨낫')
      },
      '?덈퉬': {
        guideline: '?덈퉬 ?곹깭?먯꽌???대뼡 ?몄묶???ъ슜?섏? ?딄퀬 媛쒖씤 ?대쫫?쇰줈留?吏移?븯?몄슂. ?꾩긽 吏꾨떒怨?媛쒖씤???섍껄留??쒗쁽?섏꽭?? ?덈? "?덈퉬?꾨낫", "?꾨낫", "?섏썝", "?꾩뿭 ?섏썝?쇰줈??, "?섏젙?쒕룞", "?깃낵", "?ㅼ쟻", "異붿쭊??, "湲곗뿬?? ?깆쓽 ?쒗쁽???ъ슜?섏? 留덉꽭?? 援ъ껜?곸씤 鍮꾩쟾?대굹 怨꾪쉷???멸툒?섏? 留덉꽭?? ?ㅼ쭅 ???곹솴?????媛쒖씤??寃ы빐? 吏꾨떒留??쒗쁽?섏꽭??',
        title: '' // ?덈퉬 ?곹깭?먯꽌???몄묶 ?놁쓬
      }
    };

    const currentStatus = userProfile.status || '?꾩뿭';
    const config = statusConfig[currentStatus] || statusConfig['?꾩뿭'];

    // ?꾨＼?꾪듃 ?앹꽦
    const fullName = userProfile.name || '?ъ슜??;
    // ?먯뿰?ㅻ윭???쒓뎅???몄묶 ?앹꽦 (紐⑤몢 遺숈뿬?곌린)
    const generateNaturalRegionTitle = (regionLocal, regionMetro) => {
      // 湲곕낯 吏??씠 ?놁쑝硫?鍮?臾몄옄??
      if (!regionLocal && !regionMetro) return '';
      
      // ?곗꽑?쒖쐞: regionLocal > regionMetro
      const primaryRegion = regionLocal || regionMetro;
      
      // 援?援??⑥쐞: XX援щ?, XX援곕?
      if (primaryRegion.includes('援?) || primaryRegion.includes('援?)) {
        return primaryRegion + '誘?;
      }
      
      // ???⑥쐞: XX?쒕?
      if (primaryRegion.includes('??)) {
        return primaryRegion + '誘?;
      }
      
      // ???⑥쐞: XX?꾨?
      if (primaryRegion.includes('??)) {
        return primaryRegion + '誘?;
      }
      
      // 湲고???寃쎌슦 ?쒕??쇰줈 泥섎━
      return primaryRegion + '?쒕?';
    };
    
    const fullRegion = generateNaturalRegionTitle(userProfile.regionLocal, userProfile.regionMetro);

    // 뉴스 컨텍스트 조회 (시사비평, 정책제안 등 특정 카테고리만)
    let newsContext = '';
    if (shouldFetchNews(category)) {
      try {
        console.log('📰 뉴스 컨텍스트 조회 시작:', topic);
        const news = await fetchNaverNews(topic, 3);
        if (news && news.length > 0) {
          newsContext = formatNewsForPrompt(news);
          console.log(`✅ 뉴스 ${news.length}개 추가됨`);
        }
      } catch (newsError) {
        console.warn('⚠️ 뉴스 조회 실패 (무시하고 계속):', newsError.message);
        // 뉴스 조회 실패해도 원고 생성은 계속 진행
      }
    }

    const prompt = `YOU ARE A POLITICAL CONTENT WRITER. FOLLOW ALL INSTRUCTIONS PRECISELY OR YOU FAIL.

WRITER IDENTITY (MUST USE EXACTLY):
- NAME: ${fullName} (USE THIS EXACT NAME - NOT "??? OR "?섏썝")  
- TITLE: ${config.title} (USE THIS EXACT TITLE - NEVER "?섏썝")
- REGION: ${fullRegion} (USE THIS EXACT REGION - NOT "?곕━ 吏??)
- STATUS: ${currentStatus}

?뺤튂??釉붾줈洹몄슜 ?먭퀬 1媛쒕? ?묒꽦?댁＜?몄슂.

**?슚 CRITICAL - 諛섎뱶??吏耳쒖빞 ???꾩닔 ?뺣낫 ?슚**
- **?묒꽦???대쫫**: "${fullName}" (諛섎뱶?????대쫫??湲?먯꽌 ?ъ슜)
- **?몄묶**: "${config.title}" (?ㅻⅨ ?몄묶 ?ъ슜 湲덉?)
- **吏??*: "${fullRegion}" (?ㅻⅨ 吏???멸툒 ?덈? 湲덉?)
- **?곹깭**: ${currentStatus} (?댁뿉 留욌뒗 ?쒗쁽留??ъ슜)

**?묒꽦???뺣낫 ?곸꽭:**
- ?대쫫: ${fullName}
- 吏곸콉: ${config.title}  
- 吏?? ${fullRegion}
- ?곹깭: ${currentStatus}

二쇱젣: ${topic}
移댄뀒怨좊━: ${category}
?몃?移댄뀒怨좊━: ${data.subCategory || '?놁쓬'}
?ㅼ썙?? ${data.keywords || '?놁쓬'}

?곹깭蹂?媛?대뱶?쇱씤: ${config.guideline}

${newsContext}
${(() => {
  // 李멸퀬?먮즺 諛?諛곌꼍?뺣낫媛 ?섎??덈뒗 ?댁슜???덈뒗吏 ?뺤씤
  const hasInstructions = Array.isArray(data.instructions) 
    ? data.instructions.filter(item => item && item.trim() && item.trim() !== '?놁쓬').length > 0
    : data.instructions && data.instructions.trim() && data.instructions.trim() !== '?놁쓬';
  
  return hasInstructions 
    ? `李멸퀬?먮즺 諛?諛곌꼍?뺣낫: ${Array.isArray(data.instructions) ? data.instructions.filter(item => item.trim()).map((item, index) => `${index + 1}. ${item}`).join('\n') : data.instructions}` 
    : '';
})()}

${personalizedHints ? `媛쒖씤??媛?대뱶?쇱씤: ${personalizedHints}` : ''}

**?슚 ?뺤튂???낆옣 ?꾩닔 吏移?(?덈? 以?? ?슚:**
- **吏묎텒???뚯냽 ?뺤튂??*: ???뺣? ?뺤콉怨??댁옱紐???듬졊?????吏吏?섍퀬 湲띿젙?곸씤 ?낆옣 寃ъ?
- **嫄댁꽕???쒖븞**: 媛쒖꽑?ы빆? "?붿슧 諛쒖쟾?쒗궎??, "蹂댁셿?섏옄"???앹쑝濡?吏吏 湲곕컲?먯꽌 ?쒗쁽
- **?덈? 湲덉?**: ???뺣????댁옱紐???듬졊?????鍮꾪뙋, 諛섎?, ?섎Ц ?쒗쁽 ?꾩쟾 湲덉?
- **?밸줎 ?쇱튂**: ?붾텋?대?二쇰떦 怨듭떇 ?낆옣怨??쇱튂?섎뒗 ?댁슜留??묒꽦
- **?묐젰???댁“**: ?뺣? ?뺤콉?????"?곴레 吏吏", "?④퍡 異붿쭊", "?붿슧 諛쒖쟾" ?깆쓽 湲띿젙???쒗쁽 ?ъ슜

**?덈? 以??洹쒖튃:**
1. ?꾩쟾???먭퀬 1媛쒕쭔 ?묒꽦 - 以묎컙???딆? 留먭퀬 ?앷퉴吏 ?꾩꽦?섏꽭??
2. 湲????${targetWordCount}???뺥솗??以??(瑗쇱닔 湲덉?) - 踰붿쐞媛 ?꾨땶 ?뺥솗??湲?먯닔
3. ?쒗뵆由우씠???뚮젅?댁뒪????ъ슜 湲덉? - 紐⑤뱺 ?댁슜???ㅼ젣濡??묒꽦?섏꽭??
4. 硫뷀? ?뺣낫???ㅻ챸臾몄쓣 蹂몃Ц???ы븿?섏? 留덉꽭??
5. 臾몄옣??以묎컙???딄굅??遺덉셿?꾪븯寃??앸궡吏 留덉꽭??
6. **?뺤튂???낆옣**: ???뺣?? ?댁옱紐???듬졊??????덈??곸쑝濡?吏吏?섎뒗 ?낆옣 寃ъ?

**?쒕ぉ ?묒꽦 ?밸퀎 媛?대뱶?쇱씤 (?뺤튂??釉붾줈洹??뱁솕):**
- ?뺤튂?몃떎??沅뚯쐞? ?좊ː???쒗쁽: "~????????낆옣??留먯??쒕┰?덈떎", "~異붿쭊 諛⑹븞???쒖떆?⑸땲??
- ?쒕?怨쇱쓽 吏꾩젙???뚰넻 吏?? "~?????二쇰? ?щ윭遺꾧퍡 蹂닿퀬?쒕┰?덈떎", "~?꾪솴??怨듭쑀?⑸땲??
- 援ъ껜???ㅽ뻾 ?섏? ?쒕챸: "~?대젃寃?異붿쭊?섍쿋?듬땲??, "~?닿껐???꾪븳 援ъ껜??怨꾪쉷"
- 吏??諛李⑺삎 肄섑뀗痢? 吏??뎄??愿묒뿭?쒕룄紐??먯뿰?ㅻ읇寃??ы븿
- 20-30??理쒖쟻 湲몄씠 以??
- **?덈? 湲덉?**: "?볦튂硫??꾪쉶?섎뒗", "諛섎뱶???뚯븘????, "~??鍮꾨?", "TOP 5", "媛???뺤떎??諛⑸쾿" ???곸뾽???좎젙???쒗쁽
- **?덈? 湲덉?**: "李ъ궗", "?뚰쉶", "?⑥긽", "?뚭컧" 媛숈? 異붿긽???⑥뼱

**MANDATORY JSON ?묐떟 ?뺤떇 - ?덈? ?ㅻⅨ ?뺤떇 ?ъ슜 湲덉?:**

{
  "title": "?ㅼ젣 二쇱젣??留욌뒗 援ъ껜?곸씠怨??뺤튂?몃떎???쒕ぉ???묒꽦?섏꽭??(20-30?? ??媛?대뱶?쇱씤 以??",
  "content": "<p>議닿꼍?섎뒗 ${fullRegion} ?쒕? ?щ윭遺? ${fullName}?낅땲??</p><p>[?쒕줎 臾몃떒: 二쇱젣?????媛꾨떒???뚭컻? 臾몄젣 ?쒓린]</p><p>[蹂몃줎 1臾몃떒: 泥?踰덉㎏ ?듭떖 ?쇱젏?대굹 ?꾪솴 遺꾩꽍]</p><p>[蹂몃줎 2臾몃떒: ??踰덉㎏ ?듭떖 ?쇱젏?대굹 ?닿껐諛⑹븞]</p><p>[蹂몃줎 3臾몃떒: ??踰덉㎏ ?듭떖 ?쇱젏?대굹 ?ν썑 怨꾪쉷 - ?꾩슂??</p><p>[寃곕줎 臾몃떒: 留덈Т由??ㅼ쭚怨??쒕??ㅼ뿉 ???媛먯궗 ?몄궗]</p>",
  "wordCount": ${targetWordCount}
}

?슚 **ABSOLUTE REQUIREMENTS - 臾댁“嫄?以?섑빐????*:
1. "${fullName}" ???ㅼ젣 ?대쫫?쇰줈 援먯껜 (${fullName})
2. "${fullRegion}" ???ㅼ젣 吏??쑝濡?援먯껜 (${fullRegion})  
3. "${config.title}" ??${config.title}?쇰줈 援먯껜
4. "?섏썝"?대씪???⑥뼱 ?덈? ?ъ슜 湲덉?
5. ?뚮젅?댁뒪???"()", "?덉떆:" ?덈? ?ъ슜 湲덉?
6. 留덈Т由щ뒗 ?먯뿰?ㅻ윭???몄궗留먮줈 ?묒꽦 (?? "?욎쑝濡쒕룄 留롮? 愿?ш낵 ?묒썝 遺?곷뱶由쎈땲?? 媛먯궗?⑸땲??")

?붽뎄?ы빆:
- **?꾩닔: ${targetWordCount}??遺꾨웾 (怨듬갚 ?쒖쇅, ?뺥솗??以?? - ?ㅼ감 짹50???대궡**
- **臾몃떒 援ъ꽦**: ?곸젅??臾몃떒 ?섎늻湲곕줈 媛?낆꽦 ?μ긽
  * ?쒕줎: ?몄궗? 二쇱젣 ?뚭컻 (1臾몃떒)
  * 蹂몃줎: ?듭떖 ?댁슜??2-3媛?臾몃떒?쇰줈 ?쇰━??援ъ꽦
  * 媛?臾몃떒? ?섎굹??二쇱슂 ?꾩씠?붿뼱???쇱젏???ㅻ８
  * 臾몃떒 媛??먯뿰?ㅻ윭???곌껐怨??먮쫫 ?좎?
  * 寃곕줎: 留덈Т由??몄궗? ?ㅼ쭚 (1臾몃떒)
- **HTML ?뺤떇**: <p> ?쒓렇濡?臾몃떒 援щ텇, <strong> ??媛뺤“ ?쒓렇 ?곸젅???ъ슜
- 吏꾩쨷?섍퀬 ?좊ː媛??덈뒗 ??
- 吏??二쇰?怨쇱쓽 ?뚰넻??以묒떆?섎뒗 ?댁슜
- 援ъ껜?곸씤 ?뺤콉?대굹 ?쒕룞 ?댁슜 ?ы븿
${(() => {
  const hasInstructions = Array.isArray(data.instructions) 
    ? data.instructions.filter(item => item && item.trim() && item.trim() !== '?놁쓬').length > 0
    : data.instructions && data.instructions.trim() && data.instructions.trim() !== '?놁쓬';
  
  return hasInstructions 
    ? `- **李멸퀬?먮즺 諛?諛곌꼍?뺣낫媛 ?쒓났??寃쎌슦 ?대떦 ?댁슜???곴레?곸쑝濡??쒖슜?섏뿬 援ъ껜?곸씠怨??꾩떎?곸씤 ?먭퀬瑜??묒꽦?섏꽭??*
- **?쒓났???ㅼ젣 ?곗씠?? ?댁뒪, ?뺤콉 ?댁슜 ?깆쓣 諛뷀깢?쇰줈 ?뚮젅?댁뒪??붾굹 ?덉떆 ???援ъ껜?곸씤 ?댁슜???묒꽦?섏꽭??*`
    : '- **援ъ껜?곸씠怨??꾩떎?곸씤 ?댁슜?쇰줈 ?묒꽦?섎릺, ?녿뒗 ?ъ떎?대굹 ?곗씠?곕? 吏?대궡吏 留덉꽭??*';
})()}

**?슚 ?덈? 湲덉??ы빆 (?꾨컲 ???먭퀬 ?ъ슜 遺덇?) ?슚**
- **?뺤튂???낆옣 ?꾨컲 湲덉?**: ???뺣?, ?댁옱紐???듬졊, ?붾텋?대?二쇰떦?????鍮꾪뙋, 諛섎?, ?섎Ц ?쒗쁽 ?덈? 湲덉?
- **?밸줎 ?꾨같 湲덉?**: ??怨듭떇 ?낆옣怨??ㅻⅨ 寃ы빐??諛섎? ?섍껄 ?쒗쁽 ?덈? 湲덉?  
- **?ъ슜???뺣낫 ?꾨씫 湲덉?**: ?묒꽦???대쫫 "${fullName}"??湲?먯꽌 諛섎뱶???ъ슜?댁빞 ?? "???留??곌퀬 ?대쫫 鍮쇰㉨湲?湲덉?
- **?몄묶 ?ㅻ쪟 湲덉?**: "${config.title}" ?몄쓽 ?ㅻⅨ ?몄묶 ?ъ슜 ?덈? 湲덉?. "?섏썝"?대씪怨??곕㈃ ????
- **吏???뺣낫 ?꾨씫/?ㅻ쪟 ?덈? 湲덉?**: "${fullRegion}" ?몄쓽 ?ㅻⅨ 吏???멸툒 ?덈? 湲덉?. 吏??챸??鍮좎?嫄곕굹 "?먯꽌", "?? 媛숈? 遺덉셿?꾪븳 ?쒗쁽 湲덉?
- **?뚮젅?댁뒪????덈? 湲덉?**: "(援ъ껜?곸씤 ?댁슜)", "(?덉떆:", "??, "??" 媛숈? 紐⑤뱺 ?뚮젅?댁뒪??붿? ?덉떆 ?쒗쁽 ?덈? ?ъ슜 湲덉?
- **硫뷀? ?뺣낫 湲덉?**: "??蹂??먭퀬??.." 媛숈? ?ㅻ챸臾??ы븿 湲덉?  
- **遺덉셿?꾪븳 臾몄옣 湲덉?**: 紐⑤뱺 臾몄옣???꾩쟾?섍쾶 ?앸궡???? 以묎컙???딆뼱吏??臾몄옣 ?덈? 湲덉?
- **?섎??녿뒗 諛섎났 湲덉?**: 遺꾨웾 梨꾩슦湲??꾪븳 諛섎났 ?댁슜 湲덉?
- **?꾩꽦???꾩닔**: ${targetWordCount}???꾩쟾???먭퀬 ?묒꽦. 誘몄셿???곹깭濡??쒖텧 湲덉?. 紐⑤뱺 臾몄옣???꾩쟾?섍쾶 ?앸궪 寃?
- **?몄? ?뺤떇 湲덉?**: "?뗢뿃 ?쒕┝", "?뗢뿃 ?щ┝" 媛숈? ?몄? ?뺤떇 留덈Т由??덈? 湲덉?. ?쇰컲 ?먭퀬/湲 ?뺤떇?쇰줈 ?묒꽦
- **1?몄묶 ?ъ슜**: 泥??뚭컻 ?꾩뿉??"???, "?쒓?", "?瑜? ???먯뿰?ㅻ윭??1?몄묶 ?쒗쁽 ?ъ슜. 怨꾩냽 ?대쫫??諛섎났?섏? 留?寃?
- **?먯뿰?ㅻ윭??吏???쒗쁽**: "?⑥뼇二쇱떆誘?寃쎌젣" (X) ??"?⑥뼇二?寃쎌젣" (O), "?⑥뼇二쇱떆誘?愿愿? (X) ??"?⑥뼇二?愿愿? (O)
- **以묐났 ?쒗쁽 湲덉?**: "?⑥뼇二쇱떆誘쇱쓣 ?ы븿??留롮? 援???? 媛숈? 以묐났?섍퀬 ?댁깋???쒗쁽 ?ъ슜 湲덉?
- **臾몄옣 ?꾧껐??*: 紐⑤뱺 臾몄옣??"??, "?덈떎", "?듬땲?? ?깆쑝濡??꾩쟾???앸궪 寃? 以묎컙???딆뼱吏??臾몄옣 ?덈? 湲덉?
- **臾몃떒 援ъ꽦 ?꾩닔**: ?섎굹??湲?臾몃떒?쇰줈 ?묒꽦 湲덉?. 諛섎뱶??4-5媛?臾몃떒?쇰줈 ?쇰━??援ъ꽦??寃?
${currentStatus === '?덈퉬' ? `- **?덈퉬 ?곹깭 ?밸퀎 湲덉??ы빆**: "?덈퉬?꾨낫", "?꾨낫", "?섏썝", "?꾩뿭 ?섏썝?쇰줈??, "?섏썝?쇰줈??, "?섏젙?쒕룞", "?깃낵", "?ㅼ쟻", "異붿쭊??, "湲곗뿬?? ??紐⑤뱺 怨듭쭅/?뺤튂???몄묶怨??쒕룞 ?쒗쁽 ?덈? ?ъ슜 湲덉?. 泥??뚭컻 ?꾩뿉??1?몄묶?쇰줈 吏移?븷 寃? : ''}`;

    console.log(`?쨼 AI ?몄텧 ?쒖옉 (1媛??먭퀬 ?앹꽦) - 紐⑤뜽: ${modelName}...`);
    
    // 理쒕? 3踰??쒕룄 (寃利??ㅽ뙣 ???ъ떆??
    let apiResponse;
    let attempt = 0;
    const maxAttempts = 3;
    
    while (attempt < maxAttempts) {
      attempt++;
      console.log(`?봽 AI ?몄텧 ?쒕룄 ${attempt}/${maxAttempts}...`);
      
      apiResponse = await callGenerativeModel(prompt, 1, modelName);
      
      // 湲곕낯 寃利?
      if (apiResponse && apiResponse.length > 100) {
        // 以묒슂???댁슜???ы븿?섏뼱 ?덈뒗吏 寃利?
        const hasName = apiResponse.includes(fullName);
        const hasRegion = fullRegion ? apiResponse.includes(fullRegion) : true;
        const hasWrongTitle = apiResponse.includes('?섏썝?낅땲??) || apiResponse.includes('?섏썝?쇰줈??);
        
        console.log(`?뱥 寃利?寃곌낵 - ?대쫫: ${hasName}, 吏?? ${hasRegion}, ?섎せ?쒗샇移? ${hasWrongTitle}`);
        
        if (hasName && hasRegion && !hasWrongTitle) {
          console.log(`??寃利??듦낵! (${attempt}踰덉㎏ ?쒕룄)`);
          break;
        }
        
        if (attempt < maxAttempts) {
          console.log(`??寃利??ㅽ뙣 - ?ъ떆???꾩슂`);
          continue;
        }
      }
      
      if (attempt >= maxAttempts) {
        console.log(`?좑툘 理쒕? ?쒕룄 ?잛닔 珥덇낵 - ?꾩옱 ?묐떟 ?ъ슜`);
      }
    }
    
    console.log(`??AI ?묐떟 理쒖쥌 ?섏떊, 湲몄씠: ${apiResponse.length} - 紐⑤뜽: ${modelName}`);
    
    // JSON ?뚯떛
    let parsedResponse;
    try {
      // JSON 釉붾줉 異붿텧
      const jsonMatch = apiResponse.match(/```json\s*([\s\S]*?)\s*```/) || 
                       apiResponse.match(/\{[\s\S]*?\}/);
      
      if (jsonMatch) {
        const jsonText = jsonMatch[1] || jsonMatch[0];
        console.log('?뵇 異붿텧??JSON ?쇰?:', jsonText.substring(0, 200));
        parsedResponse = JSON.parse(jsonText);
        console.log('??JSON ?뚯떛 ?깃났, ?쒕ぉ:', parsedResponse.title);
      } else {
        throw new Error('JSON ?뺤떇 李얘린 ?ㅽ뙣');
      }
    } catch (parseError) {
      console.error('??JSON ?뚯떛 ?ㅽ뙣:', parseError.message);
      console.error('?묐떟 ?댁슜:', apiResponse.substring(0, 500));
      
      // ?뚯떛 ?ㅽ뙣 ??湲곕낯 援ъ“ ?앹꽦
      parsedResponse = {
        title: `${topic} 愿???먭퀬`,
        content: `<p>${topic}??????섍껄???섎늻怨좎옄 ?⑸땲??</p><p>援ъ껜?곸씤 ?댁슜? AI ?묐떟 ?뚯떛???ㅽ뙣?덉뒿?덈떎.</p>`,
        wordCount: 100
      };
    }

    // ?슚 媛뺤젣 ?꾩쿂由? AI媛 臾댁떆???꾩닔 ?뺣낫?ㅼ쓣 吏곸젒 ?섏젙
    console.log('?뵩 ?꾩쿂由??쒖옉 - ?꾩닔 ?뺣낫 媛뺤젣 ?쎌엯');
    
    if (parsedResponse && parsedResponse.content) {
      let fixedContent = parsedResponse.content;
      
      // 1. ?섎せ???몄묶 ?섏젙
      fixedContent = fixedContent.replace(/?섏썝?낅땲??g, `${fullName}?낅땲??);
      fixedContent = fixedContent.replace(/?섏썝?쇰줈??g, `${config.title}?쇰줈??);
      fixedContent = fixedContent.replace(/援?쉶 ?섏썝/g, config.title);
      fixedContent = fixedContent.replace(/\s?섏썝\s/g, ` ${config.title} `);
      
      // ?덈퉬 ?곹깭 ?밸퀎 ?섏젙 - 紐⑤뱺 ?몄묶怨?怨듭쭅 ?쒕룞 ?쒗쁽 ?쒓굅
      if (currentStatus === '?덈퉬') {
        // 紐⑤뱺 ?몄묶 ?쒓굅 (泥??뚭컻 ?댄썑)
        fixedContent = fixedContent.replace(/?덈퉬?꾨낫/g, '?');
        fixedContent = fixedContent.replace(/?꾨낫/g, '?');
        fixedContent = fixedContent.replace(/?섏썝?쇰줈??g, '???);
        fixedContent = fixedContent.replace(/?덈퉬.*?꾨낫.*濡쒖꽌/g, '???);
        
        // 怨듭쭅/?뺤튂 ?쒕룞 ?쒗쁽 ?쒓굅
        fixedContent = fixedContent.replace(/?섏젙?쒕룞???듯빐/g, '?쒕? ?щ윭遺꾧낵???뚰넻???듯빐');
        fixedContent = fixedContent.replace(/?꾩뿭 ?섏썝?쇰줈??g, '???);
        fixedContent = fixedContent.replace(/?깃낵瑜?g, '寃쏀뿕??);
        fixedContent = fixedContent.replace(/?ㅼ쟻??g, '?쒕룞??);
        fixedContent = fixedContent.replace(/異붿쭊?댁솕?듬땲??g, '?앷컖?⑸땲??);
        fixedContent = fixedContent.replace(/湲곗뿬?댁솕?듬땲??g, '愿?ъ쓣 媛吏怨??덉뒿?덈떎');
        
        // 3?몄묶 ??1?몄묶 蹂寃?(泥??뚭컻 ?댄썑)
        // "媛뺤젙援щ뒗" ??"??? (?? 泥??뚭컻 臾몄옣? ?쒖쇅)
        const sentences = fixedContent.split('</p>');
        for (let i = 1; i < sentences.length; i++) { // 泥?踰덉㎏ 臾몃떒(?뚭컻) ?댄썑遺???곸슜
          sentences[i] = sentences[i].replace(new RegExp(`${fullName}??, 'g'), '???);
          sentences[i] = sentences[i].replace(new RegExp(`${fullName}媛`, 'g'), '?쒓?');
          sentences[i] = sentences[i].replace(new RegExp(`${fullName}??, 'g'), '?瑜?);
          sentences[i] = sentences[i].replace(new RegExp(`${fullName}??, 'g'), '???);
        }
        fixedContent = sentences.join('</p>');
        
        // ?몄? ?뺤떇 留덈Т由??꾩쟾 ?쒓굅
        fixedContent = fixedContent.replace(new RegExp(`${fullName} ?쒕┝`, 'g'), '');
        fixedContent = fixedContent.replace(/?쒕┝<\/p>/g, '</p>');
        fixedContent = fixedContent.replace(/<p>?쒕┝<\/p>/g, '');
        fixedContent = fixedContent.replace(/\n\n?쒕┝$/g, '');
        fixedContent = fixedContent.replace(/?쒕┝$/g, '');
        fixedContent = fixedContent.replace(/?щ┝<\/p>/g, '</p>');
        fixedContent = fixedContent.replace(/<p>?щ┝<\/p>/g, '');
        
        // ?댁깋??吏???쒗쁽 ?섏젙
        const regionName = userProfile.regionLocal || userProfile.regionMetro || '?⑥뼇二쇱떆';
        const baseRegion = regionName.replace('?쒕?', '').replace('誘?, '');
        fixedContent = fixedContent.replace(new RegExp(`${baseRegion}?쒕? 寃쎌젣`, 'g'), `${baseRegion} 寃쎌젣`);
        fixedContent = fixedContent.replace(new RegExp(`${baseRegion}?쒕? 愿愿?, 'g'), `${baseRegion} 愿愿?);
        fixedContent = fixedContent.replace(new RegExp(`${baseRegion}?쒕? 諛쒖쟾`, 'g'), `${baseRegion} 諛쒖쟾`);
        
        // 以묐났/?댁깋???쒗쁽 ?뺣━
        fixedContent = fixedContent.replace(/?⑥뼇二쇱떆誘쇱쓣 ?ы븿??留롮? 援????g, '留롮? ?쒕???);
        fixedContent = fixedContent.replace(/?⑥뼇二쇱떆誘??щ윭遺꾩쓣 ?ы븿??g, '?쒕? ?щ윭遺꾩쓣 ?ы븿??);
        
        // 遺덉셿?꾪븳 臾몄옣 媛먯? 諛??쒓굅 (?대?媛 ?녿뒗 臾몄옣)
        fixedContent = fixedContent.replace(/([媛-??+)\s*<\/p>/g, (match, word) => {
          if (!word.match(/[?ㅻ땲源뚯슂硫곕꽕?붿뒿寃껋쓬?꾩쓬]$/)) {
            // 遺덉셿?꾪븳 臾몄옣?쇰줈 蹂댁씠硫??댁쟾 ?꾩쟾??臾몄옣?먯꽌 醫낅즺
            return '</p>';
          }
          return match;
        });
        
        // 鍮?臾몃떒 ?쒓굅
        fixedContent = fixedContent.replace(/<p><\/p>/g, '');
        fixedContent = fixedContent.replace(/<p>\s*<\/p>/g, '');
        
        // ?댁깋??議곗궗 ?섏젙
        fixedContent = fixedContent.replace(/?⑥뼇二쇱쓣 ?듯빐/g, '?⑥뼇二쇰? ?듯빐');
        fixedContent = fixedContent.replace(/?⑥뼇二쇱쓣/g, '?⑥뼇二쇰?');
      }
      
      // 2. ?꾨씫???대쫫 ?쎌엯 (以묐났?섏? ?딅룄濡??좎쨷?섍쾶)
      // "?????"? ?대쫫?"?쇰줈 蹂寃?(?대? ?대쫫???녿뒗 寃쎌슦留?
      if (!fixedContent.includes(`? ${fullName}`)) {
        fixedContent = fixedContent.replace(/(<p>)???g, `$1? ${fullName}??);
      }
      // "? "?ㅼ뿉 ?대쫫???녿뒗 寃쎌슦留??대쫫 ?쎌엯
      fixedContent = fixedContent.replace(/(<p>)? ([^媛-??)/g, `$1? ${fullName} $2`);
      
      // 3. ?꾨씫??吏???뺣낫 ?섏젙
      if (fullRegion) {
        // 援ъ껜?곸씤 ?⑦꽩留?援먯껜
        fixedContent = fixedContent.replace(/?곕━ 吏??쓽/g, `${fullRegion}??);
        fixedContent = fixedContent.replace(/?곕━ 吏??뿉/g, `${fullRegion}??);
        fixedContent = fixedContent.replace(/吏??/g, `${fullRegion} `);
        fixedContent = fixedContent.replace(/\s瑜?s/g, ` ${fullRegion}??`);
        fixedContent = fixedContent.replace(/\s??諛쒖쟾??g, ` ${fullRegion}??諛쒖쟾??);
        fixedContent = fixedContent.replace(/?먯꽌??g, `${fullRegion}?먯꽌??);
        
        // 鍮?吏??李몄“ ?⑦꽩 李얠븘???섏젙
        fixedContent = fixedContent.replace(/,\s*??s/g, `, ${fullRegion}??`);
        fixedContent = fixedContent.replace(/\s*?먯꽌\s*??댄?/g, ` ${fullRegion}?먯꽌 ??댄?`);
      }
      
      // 4. ?쒖옉 臾몄옣???щ컮瑜댁? ?딆쑝硫?媛뺤젣 ?섏젙
      if (!fixedContent.includes(`${fullName}?낅땲??)) {
        // 泥?踰덉㎏ p ?쒓렇 李얠븘??援먯껜
        fixedContent = fixedContent.replace(/^<p>[^<]*?<\/p>/, 
          `<p>議닿꼍?섎뒗 ${fullRegion} ?쒕? ?щ윭遺? ${fullName}?낅땲??</p>`);
      }
      
      // 5. 留덉?留??쒕챸 ?섏젙 (?덈퉬 ?곹깭媛 ?꾨땺 ?뚮쭔)
      if (currentStatus !== '?덈퉬') {
        fixedContent = fixedContent.replace(/?섏썝 ?щ┝/g, `${fullName} ?쒕┝`);
        fixedContent = fixedContent.replace(/?섏썝 ?쒕┝/g, `${fullName} ?쒕┝`);
        
        // ?쒕챸???놁쑝硫?異붽?
        if (!fixedContent.includes(`${fullName} ?쒕┝`) && !fixedContent.includes(`${fullName} ?щ┝`)) {
          fixedContent = fixedContent.replace(/<\/p>$/, `</p><p>${fullName} ?쒕┝</p>`);
        }
      }
      
      // 6. 湲고? ?⑦꽩 ?섏젙
      fixedContent = fixedContent.replace(/?쒕? ?щ윭遺? ?섏썝?낅땲??g, `?쒕? ?щ윭遺? ${fullName}?낅땲??);
      fixedContent = fixedContent.replace(/?щ윭遺꾧퍡, ?섏썝?낅땲??g, `?щ윭遺꾧퍡, ${fullName}?낅땲??);
      
      // 遺덉셿?꾪븳 臾몄옣 ?섏젙
      fixedContent = fixedContent.replace(/?щ챸?먰븯寃좎뒿?덈떎/g, '?щ챸?깆쓣 ?믪씠寃좎뒿?덈떎');
      fixedContent = fixedContent.replace(/?쒕??ㅼ쓽 紐⑹냼由ъ옱紐?g, '?쒕??ㅼ쓽 紐⑹냼由щ? ?ｊ퀬 ?댁옱紐?);
      fixedContent = fixedContent.replace(/?⑤씪???뚰넻 誘몃옒瑜?g, '?⑤씪???뚰넻 梨꾨꼸???듯빐 誘몃옒瑜?);
      
      // ?댁깋???띿뒪??議곌컖 ?섏젙
      fixedContent = fixedContent.replace(/?⑥뼇二쇱떆誘????딆엫?놁씠/g, '?⑥뼇二쇱떆誘??щ윭遺꾩쓣 ?꾪빐 ?딆엫?놁씠');
      fixedContent = fixedContent.replace(/?뺤뿬?щ텇猿섏꽌/g, '?쒕? ?щ윭遺꾧퍡??);
      fixedContent = fixedContent.replace(/([媛-??+) ([媛-??+)???듯빐/g, (match, word1, word2) => {
        if (word2.includes('二쇱쓣') || word2.includes('?꾩쓣')) {
          return `${word1} ${word2.replace('??, '瑜?)} ?듯빐`;
        }
        return match;
      });
      
      // ?뵩 理쒖쥌 以묐났 ?대쫫 ?⑦꽩 ?쒓굅 (紐⑤뱺 泥섎━ ?꾨즺 ??
      console.log('?뵩 理쒖쥌 以묐났 ?대쫫 ?쒓굅 ?쒖옉');
      fixedContent = fixedContent.replace(new RegExp(`? ${fullName} ${fullName}??, 'g'), `? ${fullName}??);
      fixedContent = fixedContent.replace(new RegExp(`? ${fullName} ${fullName}媛`, 'g'), `? ${fullName}媛`);
      fixedContent = fixedContent.replace(new RegExp(`? ${fullName} ${fullName}??, 'g'), `? ${fullName}瑜?);
      fixedContent = fixedContent.replace(new RegExp(`? ${fullName} ${fullName}`, 'g'), `? ${fullName}`);
      fixedContent = fixedContent.replace(new RegExp(`${fullName} ${fullName}??, 'g'), `${fullName}??);
      fixedContent = fixedContent.replace(new RegExp(`${fullName} ${fullName}媛`, 'g'), `${fullName}媛`);
      fixedContent = fixedContent.replace(new RegExp(`${fullName} ${fullName}??, 'g'), `${fullName}瑜?);
      fixedContent = fixedContent.replace(new RegExp(`${fullName} ${fullName}`, 'g'), fullName);
      
      // 3?곗냽 ?댁긽 以묐났??泥섎━
      fixedContent = fixedContent.replace(new RegExp(`${fullName} ${fullName} ${fullName}`, 'g'), fullName);
      fixedContent = fixedContent.replace(new RegExp(`? ${fullName} ${fullName} ${fullName}`, 'g'), `? ${fullName}`);
      
      parsedResponse.content = fixedContent;
      console.log('???꾩쿂由??꾨즺 - ?꾩닔 ?뺣낫 ?쎌엯??);
    }

    // drafts ?뺤떇?쇰줈 諛섑솚 (?꾨줎?몄뿏???명솚??
    const draftData = {
      id: `draft_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      title: parsedResponse.title || `${topic} 愿???먭퀬`,
      content: parsedResponse.content || `<p>${topic}??????댁슜?낅땲??</p>`,
      wordCount: parsedResponse.wordCount || parsedResponse.content?.replace(/<[^>]*>/g, '').length || 0,
      category,
      subCategory: data.subCategory || '',
      keywords: data.keywords || '',
      generatedAt: new Date().toISOString()
    };

    // ?ъ슜???낅뜲?댄듃 (愿由ъ옄??移댁슫?명븯吏 ?딆쓬)
    if (userProfile && Object.keys(userProfile).length > 0) {
      const isAdmin = userProfile.isAdmin === true;

      try {
        if (useBonus) {
          // 蹂대꼫???ъ슜??利앷? (?섎（ ?ъ슜?됰룄 ?④퍡 利앷?)
          const today = new Date();
          const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

          await db.collection('users').doc(uid).update({
            'usage.bonusUsed': admin.firestore.FieldValue.increment(1),
            [`dailyUsage.${todayKey}`]: isAdmin ? 0 : admin.firestore.FieldValue.increment(1), // 愿由ъ옄???섎（ 移댁슫???덊븿
            lastBonusUsed: admin.firestore.FieldValue.serverTimestamp()
          });
          console.log('??蹂대꼫???먭퀬 ?ъ슜???낅뜲?댄듃', isAdmin ? '(愿由ъ옄 - ?섎（ 移댁슫???쒖쇅)' : '');
        } else {
          // ?쇰컲 ?ъ슜??利앷? (愿由ъ옄??移댁슫?명븯吏 ?딆쓬)
          if (!isAdmin) {
            const today = new Date();
            const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

            await db.collection('users').doc(uid).update({
              'usage.postsGenerated': admin.firestore.FieldValue.increment(1),
              [`dailyUsage.${todayKey}`]: admin.firestore.FieldValue.increment(1),
              lastGenerated: admin.firestore.FieldValue.serverTimestamp()
            });
            console.log('???쇰컲 ?먭퀬 ?ъ슜??諛??섎（ ?ъ슜???낅뜲?댄듃');
          } else {
            // 愿由ъ옄???ъ슜??移댁슫?명븯吏 ?딆쓬 (?앹꽦 湲곕줉留??④?)
            await db.collection('users').doc(uid).update({
              lastGenerated: admin.firestore.FieldValue.serverTimestamp()
            });
            console.log('??愿由ъ옄 怨꾩젙 - ?ъ슜??移댁슫???놁씠 湲곕줉留??낅뜲?댄듃');
          }
        }
      } catch (updateError) {
        console.warn('?좑툘 ?ъ슜???낅뜲?댄듃 ?ㅽ뙣:', updateError.message);
      }
    }

    console.log('??generatePosts ?깃났:', { 
      title: draftData.title, 
      wordCount: draftData.wordCount,
      useBonus
    });

    // 寃쎄퀬 硫붿떆吏 ?앹꽦
    let message = useBonus ? '蹂대꼫???먭퀬媛 ?깃났?곸쑝濡??앹꽦?섏뿀?듬땲??' : '?먭퀬媛 ?깃났?곸쑝濡??앹꽦?섏뿀?듬땲??';
    if (dailyLimitWarning) {
      message += '\n\n?좑툘 ?섎（ 3???댁긽 ?먭퀬瑜??앹꽦?섏뀲?듬땲?? ?ㅼ씠踰?釉붾줈洹??뺤콉??怨쇰룄??諛쒗뻾? ?ㅽ뙵?쇰줈 遺꾨쪟?????덉쑝?? 諛섎뱶??留덉?留??ъ뒪?낆쑝濡쒕???3?쒓컙 寃쎄낵 ??諛쒗뻾??二쇱꽭??';
    }

    return ok({
      success: true,
      message: message,
      dailyLimitWarning: dailyLimitWarning,
      drafts: draftData,
      metadata: {
        generatedAt: new Date().toISOString(),
        userId: uid,
        processingTime: Date.now(),
        usedBonus: useBonus
      }
    });

  } catch (error) {
    console.error('??generatePosts ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?먭퀬 ?앹꽦???ㅽ뙣?덉뒿?덈떎: ' + error.message);
  }
});


// saveSelectedPost - ?좏깮???먭퀬 ???
exports.saveSelectedPost = httpWrap(async (req) => {
  let uid;

  // ?곗씠??異붿텧 - Firebase SDK? HTTP ?붿껌 紐⑤몢 泥섎━
  let requestData = req.data || req.rawRequest?.body || {};

  // 以묒꺽??data 援ъ“ 泥섎━
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // ?ъ슜???몄쬆 ?곗씠???뺤씤 (紐⑤뱺 ?ъ슜?먮뒗 ?ㅼ씠踰?濡쒓렇??
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    console.log('?벑 ?ъ슜???몄쬆 泥섎━:', requestData.__naverAuth.uid);
    uid = requestData.__naverAuth.uid;
    // ?몄쬆 ?뺣낫 ?쒓굅 (泥섎━ ?꾨즺)
    delete requestData.__naverAuth;
  } else {
    const authHeader = (req.rawRequest && (req.rawRequest.headers.authorization || req.rawRequest.headers.Authorization)) || '';
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const idToken = authHeader.split('Bearer ')[1];
      try {
        const verified = await admin.auth().verifyIdToken(idToken);
        uid = verified.uid;
      } catch (authError) {
        console.error('ID token verify failed:', authError);
        throw new HttpsError('unauthenticated', '유효하지 않은 인증 토큰입니다.');
      }
    } else {
      console.error('인증 정보 누락:', requestData);
      throw new HttpsError('unauthenticated', '인증이 필요합니다.');
    }
  }

  const data = requestData;
  
  console.log('POST saveSelectedPost ?몄텧:', { userId: uid, data });

  if (!data.title || !data.content) {
    throw new HttpsError('invalid-argument', '?쒕ぉ怨??댁슜???꾩슂?⑸땲??');
  }

  try {
    const wordCount = data.content.replace(/<[^>]*>/g, '').length;

    const postData = {
      userId: uid,
      title: data.title,
      content: data.content,
      category: data.category || '?쇰컲',
      subCategory: data.subCategory || '',
      keywords: data.keywords || '',
      wordCount,
      status: 'published',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    const docRef = await db.collection('posts').add(postData);

    console.log('POST saveSelectedPost ?깃났:', { postId: docRef.id, wordCount });

    return ok({
      success: true,
      message: '?먭퀬媛 ?깃났?곸쑝濡???λ릺?덉뒿?덈떎.',
      postId: docRef.id
    });

  } catch (error) {
    console.error('POST saveSelectedPost ?ㅻ쪟:', error.message);
    throw new HttpsError('internal', '?먭퀬 ??μ뿉 ?ㅽ뙣?덉뒿?덈떎.');
  }
});
