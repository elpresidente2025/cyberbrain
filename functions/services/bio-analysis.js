/**
 * functions/services/bio-analysis.js
 * 자기소개 텍스트에서 메타데이터를 추출하여 사용자의 선호도를 분석하는 서비스
 */

'use strict';

const { callGenerativeModel } = require('./gemini');
const { extractStyleFingerprint } = require('./stylometry');

/**
 * 자기소개 텍스트에서 종합 메타데이터를 추출합니다
 * @param {string} bioContent - 사용자 자기소개 내용
 * @returns {Promise<Object>} 추출된 메타데이터 객체
 */
async function extractBioMetadata(bioContent) {
  if (!bioContent || bioContent.trim().length < 50) {
    throw new Error('자기소개가 너무 짧아서 메타데이터를 추출할 수 없습니다.');
  }

  const prompt = `다음 정치인의 자기소개 텍스트를 분석하여 메타데이터를 JSON 형식으로 추출해주세요.

자기소개 내용:
"""
${bioContent}
"""

다음 구조로 분석 결과를 반환해주세요:

{
  "politicalStance": {
    "progressive": 0.0-1.0 (진보 성향 점수),
    "conservative": 0.0-1.0 (보수 성향 점수), 
    "moderate": 0.0-1.0 (온건 성향 점수)
  },
  "policyFocus": {
    "economy": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"},
    "education": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"},
    "welfare": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"},
    "environment": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"},
    "security": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"},
    "culture": {"weight": 0.0-1.0, "sentiment": "positive/negative/neutral"}
  },
  "communicationStyle": {
    "tone": "warm/formal/passionate/analytical/friendly",
    "approach": "inclusive/authoritative/collaborative/personal", 
    "rhetoric": "emotional/logical/practical/inspirational"
  },
  "localConnection": {
    "strength": 0.0-1.0 (지역 연관성 강도),
    "keywords": ["지역 관련 키워드들"],
    "experienceYears": 추정_경험_연수
  },
  "expertise": {
    "정책분야1": 0.0-1.0,
    "정책분야2": 0.0-1.0,
    "정책분야3": 0.0-1.0
  },
  "generationProfile": {
    "preferredStyle": "empathetic_practical/authoritative_data/inspirational_vision/collaborative_dialogue",
    "keywordDensity": "light/medium/heavy",
    "structurePreference": "narrative_with_facts/data_driven/story_focused/mixed",
    "emotionalTone": "warm_professional/serious_formal/passionate_engaging/calm_rational",
    "likelyPreferences": {
      "includePersonalExperience": 0.0-1.0,
      "useStatistics": 0.0-1.0, 
      "mentionLocalCases": 0.0-1.0,
      "focusOnFuture": 0.0-1.0,
      "emphasizeAchievements": 0.0-1.0
    }
  }
}

분석 기준:
1. 정치적 성향: 사용된 키워드, 정책 언급, 가치관 표현을 종합 판단
2. 정책 관심도: 언급 빈도와 서술 강도로 측정
3. 소통 스타일: 문체, 어조, 표현 방식 분석
4. 지역 연관성: 지역 관련 언급과 현장 경험 서술 정도
5. 전문성: 구체적 경험과 성과 언급으로 판단
6. 생성 선호도: 전체적인 스타일과 내용 패턴으로 추론

JSON만 반환하세요. 추가 설명은 하지 마세요.`;

  try {
    const response = await callGenerativeModel(prompt);
    const metadata = JSON.parse(response);
    
    // 데이터 검증 및 기본값 설정
    return validateAndNormalizeMetadata(metadata);
    
  } catch (error) {
    console.error('자기소개 메타데이터 추출 실패:', error);
    throw new Error('메타데이터 추출 중 오류가 발생했습니다: ' + error.message);
  }
}

/**
 * 추출된 메타데이터의 유효성을 검사하고 정규화합니다
 */
function validateAndNormalizeMetadata(metadata) {
  const normalized = {
    politicalStance: {
      progressive: Math.max(0, Math.min(1, metadata.politicalStance?.progressive || 0.5)),
      conservative: Math.max(0, Math.min(1, metadata.politicalStance?.conservative || 0.5)),
      moderate: Math.max(0, Math.min(1, metadata.politicalStance?.moderate || 0.5))
    },
    
    policyFocus: {},
    
    communicationStyle: {
      tone: metadata.communicationStyle?.tone || 'warm',
      approach: metadata.communicationStyle?.approach || 'inclusive',
      rhetoric: metadata.communicationStyle?.rhetoric || 'practical'
    },
    
    localConnection: {
      strength: Math.max(0, Math.min(1, metadata.localConnection?.strength || 0.5)),
      keywords: Array.isArray(metadata.localConnection?.keywords) ? metadata.localConnection.keywords : [],
      experienceYears: Math.max(0, metadata.localConnection?.experienceYears || 0)
    },
    
    expertise: metadata.expertise || {},
    
    generationProfile: {
      preferredStyle: metadata.generationProfile?.preferredStyle || 'empathetic_practical',
      keywordDensity: metadata.generationProfile?.keywordDensity || 'medium',
      structurePreference: metadata.generationProfile?.structurePreference || 'narrative_with_facts',
      emotionalTone: metadata.generationProfile?.emotionalTone || 'warm_professional',
      likelyPreferences: {
        includePersonalExperience: Math.max(0, Math.min(1, metadata.generationProfile?.likelyPreferences?.includePersonalExperience || 0.7)),
        useStatistics: Math.max(0, Math.min(1, metadata.generationProfile?.likelyPreferences?.useStatistics || 0.5)),
        mentionLocalCases: Math.max(0, Math.min(1, metadata.generationProfile?.likelyPreferences?.mentionLocalCases || 0.6)),
        focusOnFuture: Math.max(0, Math.min(1, metadata.generationProfile?.likelyPreferences?.focusOnFuture || 0.6)),
        emphasizeAchievements: Math.max(0, Math.min(1, metadata.generationProfile?.likelyPreferences?.emphasizeAchievements || 0.5))
      }
    }
  };

  // policyFocus 정규화
  const policyFields = ['economy', 'education', 'welfare', 'environment', 'security', 'culture'];
  for (const field of policyFields) {
    if (metadata.policyFocus?.[field]) {
      normalized.policyFocus[field] = {
        weight: Math.max(0, Math.min(1, metadata.policyFocus[field].weight || 0)),
        sentiment: ['positive', 'negative', 'neutral'].includes(metadata.policyFocus[field].sentiment) 
          ? metadata.policyFocus[field].sentiment 
          : 'neutral'
      };
    } else {
      normalized.policyFocus[field] = { weight: 0, sentiment: 'neutral' };
    }
  }

  return normalized;
}

/**
 * 메타데이터를 기반으로 원고 생성 최적화 힌트를 생성합니다
 */
function generateOptimizationHints(metadata) {
  const hints = {
    styleRecommendations: [],
    contentSuggestions: [],
    toneAdjustments: []
  };

  // 정치적 성향 기반 힌트
  if (metadata.politicalStance.progressive > 0.7) {
    hints.styleRecommendations.push('변화와 혁신을 강조하는 표현 사용');
  } else if (metadata.politicalStance.conservative > 0.7) {
    hints.styleRecommendations.push('안정성과 전통을 중시하는 표현 사용');
  }

  // 소통 스타일 기반 힌트
  if (metadata.communicationStyle.tone === 'warm') {
    hints.toneAdjustments.push('친근하고 따뜻한 어조 유지');
  }

  // 지역 연관성 기반 힌트
  if (metadata.localConnection.strength > 0.8) {
    hints.contentSuggestions.push('지역 현안과 주민 사례를 적극 활용');
  }

  return hints;
}

/**
 * Bio 텍스트에서 메타데이터와 Style Fingerprint를 동시에 추출합니다
 * (Phase 1+2 통합 분석)
 * @param {string} bioContent - 사용자 자기소개 내용
 * @param {Object} options - 추가 옵션
 * @param {string} options.userName - 사용자 이름
 * @param {string} options.region - 지역
 * @returns {Promise<Object>} { metadata, styleFingerprint, hints }
 */
async function extractBioWithStyle(bioContent, options = {}) {
  if (!bioContent || bioContent.trim().length < 50) {
    throw new Error('자기소개가 너무 짧아서 분석할 수 없습니다.');
  }

  console.log(`🧠 [Bio 분석] 통합 분석 시작 (${bioContent.length}자)`);

  // 병렬로 두 분석 실행 (효율성)
  const [metadata, styleFingerprint] = await Promise.all([
    extractBioMetadata(bioContent).catch(err => {
      console.warn('⚠️ 메타데이터 추출 실패:', err.message);
      return null;
    }),
    extractStyleFingerprint(bioContent, options).catch(err => {
      console.warn('⚠️ 스타일 추출 실패:', err.message);
      return null;
    })
  ]);

  const hints = metadata ? generateOptimizationHints(metadata) : null;

  console.log(`✅ [Bio 분석] 통합 분석 완료`, {
    hasMetadata: !!metadata,
    hasStyleFingerprint: !!styleFingerprint,
    styleConfidence: styleFingerprint?.analysisMetadata?.confidence || 0
  });

  return {
    metadata,
    styleFingerprint,
    hints
  };
}

module.exports = {
  extractBioMetadata,
  generateOptimizationHints,
  extractBioWithStyle,
  extractStyleFingerprint
};