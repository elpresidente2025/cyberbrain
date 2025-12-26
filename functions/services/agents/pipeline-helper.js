'use strict';

/**
 * Multi-Agent Pipeline Helper (통합 리팩토링 버전)
 *
 * 기존 generatePosts 로직과 통합하기 위한 헬퍼 함수
 * - 전체 파이프라인 실행 (생성 → 검수 → SEO)
 * - 기존 프롬프트 기반 생성과 병행 가능
 * - 설정으로 Multi-Agent 모드 활성화
 */

const { runAgentPipeline, PIPELINES } = require('./orchestrator');
const { db } = require('../../utils/firebaseAdmin');

/**
 * Multi-Agent 모드 활성화 여부 확인
 * @returns {Promise<boolean>}
 */
async function isMultiAgentEnabled() {
  try {
    const configDoc = await db.collection('system').doc('config').get();
    if (configDoc.exists) {
      return configDoc.data().useMultiAgent === true;
    }
    return false;
  } catch (error) {
    console.warn('⚠️ [MultiAgent] 설정 조회 실패:', error.message);
    return false;
  }
}

/**
 * 전체 Multi-Agent 파이프라인으로 원고 생성
 *
 * @param {Object} params
 * @param {string} params.topic - 주제
 * @param {string} params.category - 카테고리
 * @param {Object} params.userProfile - 사용자 프로필
 * @param {string} params.memoryContext - 메모리 컨텍스트
 * @param {string} params.instructions - 배경 정보
 * @param {string} params.newsContext - 뉴스 컨텍스트
 * @param {string} params.regionHint - 타 지역 힌트
 * @param {Array<string>} params.keywords - 키워드
 * @param {number} params.targetWordCount - 목표 글자수
 * @returns {Promise<Object>} 생성 결과
 */
async function generateWithMultiAgent({
  topic,
  category,
  userProfile,
  memoryContext = '',
  instructions = '',
  newsContext = '',
  regionHint = '',
  keywords = [],
  userKeywords = [],  // 🔑 사용자 직접 입력 키워드 (최우선)
  targetWordCount = 1700
}) {
  console.log('🤖 [MultiAgent] 전체 파이프라인 시작');

  const context = {
    topic,
    category,
    userProfile,
    memoryContext,
    instructions,
    newsContext,
    regionHint,
    keywords,
    userKeywords,  // 🔑 사용자 직접 입력 키워드 전달
    targetWordCount
  };

  // 표준 파이프라인 실행 (KeywordAgent → WriterAgent → ComplianceAgent → SEOAgent)
  const result = await runAgentPipeline(context, { pipeline: 'standard' });

  if (!result.success) {
    console.error('❌ [MultiAgent] 파이프라인 실패:', result.error);
    throw new Error(result.error || 'Multi-Agent 파이프라인 실패');
  }

  console.log('✅ [MultiAgent] 파이프라인 완료', {
    hasContent: !!result.content,
    hasTitle: !!result.title,
    duration: result.metadata?.duration,
    seoScore: result.metadata?.seo?.score,
    compliancePassed: result.metadata?.compliance?.passed
  });

  return {
    content: result.content,
    title: result.title,
    wordCount: result.metadata?.wordCount || 0,
    metadata: result.metadata,
    agentResults: result.agentResults
  };
}

/**
 * 검수만 실행 (기존 생성 결과에 적용)
 * @param {Object} params
 * @param {string} params.content - 생성된 콘텐츠
 * @param {Object} params.userProfile - 사용자 프로필
 * @returns {Promise<Object>} 검수 결과
 */
async function runComplianceCheck({ content, userProfile }) {
  const context = {
    previousResults: {
      WriterAgent: {
        success: true,
        data: { content }
      }
    },
    userProfile
  };

  const result = await runAgentPipeline(context, { pipeline: 'complianceOnly' });

  return {
    passed: result.metadata?.compliance?.passed ?? true,
    content: result.content || content,
    issues: result.agentResults?.ComplianceAgent?.data?.issues || [],
    replacements: result.agentResults?.ComplianceAgent?.data?.replacements || []
  };
}

/**
 * SEO 최적화만 실행 (기존 생성 결과에 적용)
 * @param {Object} params
 * @param {string} params.content - 생성된 콘텐츠
 * @param {string} params.topic - 주제
 * @param {Object} params.userProfile - 사용자 프로필
 * @returns {Promise<Object>} SEO 최적화 결과
 */
async function runSEOOptimization({ content, topic, userProfile }) {
  const { SEOAgent } = require('./seo-agent');
  const { KeywordAgent } = require('./keyword-agent');

  const keywordAgent = new KeywordAgent();
  const seoAgent = new SEOAgent();

  // 키워드 추출
  const keywordResult = await keywordAgent.run({
    topic,
    category: 'general',
    userProfile
  });

  // SEO 최적화
  const seoResult = await seoAgent.run({
    previousResults: {
      KeywordAgent: keywordResult,
      ComplianceAgent: {
        success: true,
        data: { content }
      }
    },
    userProfile
  });

  return {
    title: seoResult.data?.title || null,
    content: seoResult.data?.content || content,
    keywords: seoResult.data?.keywords || [],
    seoScore: seoResult.data?.seoScore || null,
    suggestions: seoResult.data?.suggestions || []
  };
}

/**
 * 기존 생성 결과 후처리 (검수 + SEO)
 * @param {Object} params
 * @param {string} params.content - 생성된 콘텐츠
 * @param {string} params.topic - 주제
 * @param {Object} params.userProfile - 사용자 프로필
 * @returns {Promise<Object>} 후처리 결과
 */
async function postProcessContent({ content, topic, userProfile }) {
  console.log('🔄 [MultiAgent] 콘텐츠 후처리 시작');

  // 1. 검수
  const complianceResult = await runComplianceCheck({ content, userProfile });

  if (!complianceResult.passed) {
    console.warn('⚠️ [MultiAgent] 검수 경고:', complianceResult.issues.length, '개 이슈');
  }

  // 2. SEO 최적화 (검수 통과한 콘텐츠로)
  const seoResult = await runSEOOptimization({
    content: complianceResult.content,
    topic,
    userProfile
  });

  console.log('✅ [MultiAgent] 콘텐츠 후처리 완료', {
    compliancePassed: complianceResult.passed,
    issueCount: complianceResult.issues.length,
    seoScore: seoResult.seoScore
  });

  return {
    content: seoResult.content,
    title: seoResult.title,
    originalContent: content,
    compliance: {
      passed: complianceResult.passed,
      issues: complianceResult.issues,
      replacements: complianceResult.replacements
    },
    seo: {
      score: seoResult.seoScore,
      keywords: seoResult.keywords,
      suggestions: seoResult.suggestions
    }
  };
}

module.exports = {
  isMultiAgentEnabled,
  generateWithMultiAgent,
  runComplianceCheck,
  runSEOOptimization,
  postProcessContent
};
