'use strict';

/**
 * Orchestrator - Multi-Agent 시스템 조율 (통합 리팩토링 버전)
 *
 * 역할:
 * - Agent 실행 순서 관리
 * - Agent 간 결과 및 컨텍스트 전달
 * - 에러 복구 및 폴백 처리
 * - 전체 파이프라인 모니터링
 */

const { KeywordAgent } = require('./keyword-agent');
const { WriterAgent } = require('./writer-agent');
const { ComplianceAgent } = require('./compliance-agent');
const { SEOAgent } = require('./seo-agent');

/**
 * 파이프라인 정의
 */
const PIPELINES = {
  // 전체 파이프라인: 키워드 → 작성 → 검수 → SEO
  standard: [
    { agent: KeywordAgent, name: 'KeywordAgent', required: false },
    { agent: WriterAgent, name: 'WriterAgent', required: true },
    { agent: ComplianceAgent, name: 'ComplianceAgent', required: true },
    { agent: SEOAgent, name: 'SEOAgent', required: false }
  ],

  // 빠른 파이프라인: 작성 → 검수만
  fast: [
    { agent: WriterAgent, name: 'WriterAgent', required: true },
    { agent: ComplianceAgent, name: 'ComplianceAgent', required: true }
  ],

  // 검수만 파이프라인 (외부 콘텐츠 검수용)
  complianceOnly: [
    { agent: ComplianceAgent, name: 'ComplianceAgent', required: true }
  ],

  // SEO 최적화만 (검수 + SEO)
  seoOptimize: [
    { agent: ComplianceAgent, name: 'ComplianceAgent', required: true },
    { agent: SEOAgent, name: 'SEOAgent', required: false }
  ]
};

class Orchestrator {
  constructor(options = {}) {
    this.options = {
      pipeline: 'standard',
      continueOnError: true,  // 선택적 Agent 실패 시 계속 진행
      timeout: 120000,        // 전체 타임아웃 (120초, WriterAgent가 오래 걸릴 수 있음)
      ...options
    };

    this.results = {};
    this.startTime = null;
  }

  /**
   * 파이프라인 실행
   * @param {Object} context - 초기 컨텍스트
   * @returns {Promise<Object>} 최종 결과
   */
  async run(context) {
    this.startTime = Date.now();
    this.results = {};

    const pipelineName = this.options.pipeline;
    const pipeline = PIPELINES[pipelineName];

    if (!pipeline) {
      throw new Error(`Unknown pipeline: ${pipelineName}`);
    }

    console.log(`🎭 [Orchestrator] 파이프라인 시작: ${pipelineName}`);
    console.log(`🎭 [Orchestrator] Agent 순서: ${pipeline.map(p => p.name).join(' → ')}`);

    // 초기 컨텍스트 설정
    let currentContext = {
      ...context,
      previousResults: {}
    };

    for (const step of pipeline) {
      const { agent: AgentClass, name, required } = step;

      // 타임아웃 체크
      const elapsed = Date.now() - this.startTime;
      if (elapsed > this.options.timeout) {
        console.warn(`⏱️ [Orchestrator] 타임아웃 (${elapsed}ms) - 파이프라인 중단`);
        break;
      }

      try {
        const agent = new AgentClass();

        // 이전 결과를 컨텍스트에 포함
        currentContext.previousResults = { ...this.results };

        // 컨텍스트 보강 (Agent별 필요 데이터 전달)
        const enrichedContext = this.enrichContext(name, currentContext);

        console.log(`▶️ [Orchestrator] ${name} 실행 시작`);

        // Agent 실행
        const result = await agent.run(enrichedContext);
        this.results[name] = result;

        console.log(`✅ [Orchestrator] ${name} 완료 (${result.metadata?.duration || 0}ms)`);

        // 필수 Agent 실패 시 중단
        if (!result.success && required) {
          console.error(`❌ [Orchestrator] 필수 Agent 실패: ${name}`);
          return this.buildFinalResult(false, `${name} 실패: ${result.error}`);
        }

        // 선택적 Agent 실패 시 경고만
        if (!result.success && !required) {
          console.warn(`⚠️ [Orchestrator] 선택적 Agent 실패 (계속 진행): ${name}`);
        }

      } catch (error) {
        console.error(`❌ [Orchestrator] Agent 실행 오류 (${name}):`, error.message);

        if (required) {
          return this.buildFinalResult(false, `${name} 오류: ${error.message}`);
        }
      }
    }

    return this.buildFinalResult(true);
  }

  /**
   * Agent별 컨텍스트 보강
   */
  enrichContext(agentName, context) {
    const enriched = { ...context };

    switch (agentName) {
      case 'KeywordAgent':
        // KeywordAgent는 topic과 category만 필요
        break;

      case 'WriterAgent':
        // WriterAgent는 userProfile, memoryContext, keywords 필요
        // KeywordAgent 결과에서 키워드 가져오기
        if (this.results.KeywordAgent?.success) {
          enriched.extractedKeywords = this.results.KeywordAgent.data.keywords;
        }
        break;

      case 'ComplianceAgent':
        // ComplianceAgent는 WriterAgent 결과 필요 (previousResults에 포함됨)
        break;

      case 'SEOAgent':
        // SEOAgent는 모든 이전 결과 필요 (previousResults에 포함됨)
        break;
    }

    return enriched;
  }

  /**
   * 최종 결과 빌드
   */
  buildFinalResult(success, error = null) {
    const duration = Date.now() - this.startTime;

    // 최종 콘텐츠는 마지막 성공한 콘텐츠 Agent에서 가져옴
    let finalContent = null;
    let finalTitle = null;

    // SEOAgent → ComplianceAgent → WriterAgent 순으로 fallback
    if (this.results.SEOAgent?.success) {
      finalContent = this.results.SEOAgent.data.content;
      finalTitle = this.results.SEOAgent.data.title;
    } else if (this.results.ComplianceAgent?.success) {
      finalContent = this.results.ComplianceAgent.data.content;
      // ComplianceAgent는 title을 생성하지 않으므로 WriterAgent에서 가져옴
      finalTitle = this.results.WriterAgent?.data?.title || null;
    } else if (this.results.WriterAgent?.success) {
      finalContent = this.results.WriterAgent.data.content;
      finalTitle = this.results.WriterAgent.data.title;
    }

    // 메타데이터 수집
    const keywords = this.results.KeywordAgent?.data?.keywords || [];
    const complianceResult = this.results.ComplianceAgent?.data || {};
    const seoResult = this.results.SEOAgent?.data || {};

    console.log(`🎭 [Orchestrator] 파이프라인 완료 (${duration}ms)`, {
      success,
      agentsRun: Object.keys(this.results).length,
      hasContent: !!finalContent,
      hasTitle: !!finalTitle
    });

    return {
      success,
      error,
      content: finalContent,
      title: finalTitle,
      metadata: {
        duration,
        pipeline: this.options.pipeline,
        agents: Object.fromEntries(
          Object.entries(this.results).map(([name, result]) => [
            name,
            {
              success: result.success,
              duration: result.metadata?.duration,
              error: result.error || null
            }
          ])
        ),
        // 키워드 정보
        keywords: keywords.slice(0, 5).map(k => k.keyword || k),
        primaryKeyword: this.results.KeywordAgent?.data?.primary || null,
        // 검수 정보
        compliance: {
          passed: complianceResult.passed ?? null,
          issueCount: complianceResult.issues?.length || 0,
          score: complianceResult.score || null,
          electionStage: complianceResult.electionStage || null
        },
        // SEO 정보
        seo: {
          score: seoResult.seoScore || null,
          suggestions: seoResult.suggestions || []
        },
        // 글자수
        wordCount: finalContent ? finalContent.replace(/<[^>]*>/g, '').length : 0
      },
      agentResults: this.results
    };
  }

  /**
   * 특정 Agent 결과 조회
   */
  getAgentResult(agentName) {
    return this.results[agentName] || null;
  }
}

/**
 * 간편 실행 함수
 */
async function runAgentPipeline(context, options = {}) {
  const orchestrator = new Orchestrator(options);
  return orchestrator.run(context);
}

module.exports = {
  Orchestrator,
  runAgentPipeline,
  PIPELINES
};
