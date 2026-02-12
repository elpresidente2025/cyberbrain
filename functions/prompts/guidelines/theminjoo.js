'use strict';

const { db } = require('../../utils/firebaseAdmin');

/**
 * 🏛️ 더불어민주당 공식 당론 및 어조 가이드 중앙 저장소 (DB 기반)
 * 
 * 역할:
 * 1. Firestore `party_stances` 컬렉션에서 주제와 관련된 당론 조회
 * 2. 매칭되는 당론이 있을 경우 프롬프트에 주입할 가이드 객체 반환
 */

// 컬렉션 이름
const COLLECTION_NAME = 'party_stances';

// 캐싱 (메모리 내) - 콜드 스타트 시에만 DB 조회, 이후 재사용 (선택 사항)
// 현재는 실시간성이 중요하므로 캐싱하지 않거나 짧게 유지
const stanceCache = null;
const lastCacheTime = 0;
const CACHE_TTL = 60 * 1000; // 1분

/**
 * 주제(topic)와 관련된 당론을 조회합니다.
 * @param {string} topic - 사용자가 입력한 주제
 * @returns {Promise<Object|null>} 당론 객체 또는 null
 */
async function getPartyStance(topic) {
  if (!topic) return null;

  try {
    // 1. 모든 활성화된 당론 가져오기 (문서 수가 적을 것으로 가정하고 전체 로드 후 필터링)
    // 문서 수가 많아지면 쿼리 최적화 필요
    const snapshot = await db.collection(COLLECTION_NAME).where('isActive', '==', true).get();

    if (snapshot.empty) {
      return null;
    }

    let matchedStance = null;
    let maxMatchedKeywords = 0;

    // 2. 키워드 매칭 로직
    // 가장 많은 키워드가 매칭된 당론을 선택 (단순 포함 여부)
    snapshot.docs.forEach(doc => {
      const data = doc.data();
      const keywords = data.keywords || [];

      let matchCount = 0;
      keywords.forEach(keyword => {
        if (topic.includes(keyword)) {
          matchCount++;
        }
      });

      // 매칭된 키워드가 있고, 기존보다 더 많이 매칭되었거나 (우선순위 고려 가능)
      if (matchCount > 0 && matchCount > maxMatchedKeywords) {
        maxMatchedKeywords = matchCount;
        matchedStance = { id: doc.id, ...data };
      }
    });

    if (matchedStance) {
      console.log(`🏛️ [PartyStance] 당론 매칭 성공: "${matchedStance.title}" (키워드 매칭: ${maxMatchedKeywords}개)`);
      return formatStanceForPrompt(matchedStance);
    }

    return null;

  } catch (error) {
    console.error('❌ [PartyStance] 당론 조회 실패:', error);
    return null;
  }
}

/**
 * 당론 데이터를 프롬프트용 텍스트로 변환
 */
function formatStanceForPrompt(stanceData) {
  const forbiddenPhrases = (stanceData.forbidden_phrases || []).join(', ');

  return `
╔═══════════════════════════════════════════════════════════════╗
║  🏛️ [CRITICAL] 더불어민주당 공식 당론 가이드 (자동 적용)      ║
╚═══════════════════════════════════════════════════════════════╝

**관련 이슈**: ${stanceData.title}

1. **[핵심 입장 - Stance]**:
   "${stanceData.stance}"

2. **[필수 논리 구조 - Logic Guide]**:
   ${stanceData.logic_guide}

3. **[절대 금지 표현]**:
   - 금지: ${forbiddenPhrases}
   ${stanceData.additional_instructions ? `\n4. **[추가 지침]**:\n   ${stanceData.additional_instructions}` : ''}
`;
}

module.exports = {
  getPartyStance
};
