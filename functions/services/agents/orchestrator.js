'use strict';

/**
 * Orchestrator - Multi-Agent 시스템 조율 (통합 리팩토링 버전)
 *
 * 역할:
 * - Agent 실행 순서 관리
 * - Agent 간 결과 및 컨텍스트 전달
 * - 에러 복구 및 폴백 처리
 * - 전체 파이프라인 모니터링
 * - 품질 기준 충족까지 재검증 루프 실행
 */

const { KeywordAgent } = require('./keyword-agent');
const { WriterAgent } = require('./writer-agent');
const { ChainWriterAgent } = require('./chain-writer-agent'); // 🆕 추가
const { TitleAgent } = require('./title-agent');
const { ComplianceAgent } = require('./compliance-agent');
const { SEOAgent } = require('./seo-agent');
const { refineWithLLM } = require('../posts/editor-agent');

// 품질 기준 상수
const QUALITY_THRESHOLDS = {
  SEO_REQUIRED: true,          // SEO Pass/Fail 기준 적용
  MAX_REFINEMENT_ATTEMPTS: 2,  // 🔴 [PERF] 5→2로 축소 (-90초 절감)
  ALLOWED_ISSUE_SEVERITIES: ['low', 'info']  // 허용되는 이슈 심각도 (critical, high는 불허)
};

/**
 * 파이프라인 정의
 */
const PIPELINES = {
  // 전체 파이프라인: 키워드 → 작성 → 검수 → SEO
  standard: [
    { agent: KeywordAgent, name: 'KeywordAgent', required: false },
    { agent: WriterAgent, name: 'WriterAgent', required: true },
    { agent: TitleAgent, name: 'TitleAgent', required: true },
    { agent: ComplianceAgent, name: 'ComplianceAgent', required: true },
    { agent: SEOAgent, name: 'SEOAgent', required: false }
  ],

  // 💎 고품질 파이프라인 (ChainWriterAgent 사용) - A/B 테스트 Group B
  highQuality: [
    { agent: KeywordAgent, name: 'KeywordAgent', required: false },
    { agent: ChainWriterAgent, name: 'WriterAgent', required: true }, // 이름은 WriterAgent로 위장하여 후속 Agent 호환성 유지
    { agent: TitleAgent, name: 'TitleAgent', required: true },
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
      timeout: 120000,        // 🔴 [PERF] 180초→120초로 단축
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
        // 🔴 [PERF] KeywordAgent 조건부 스킵: 사용자가 userKeywords 입력 시 건너뛰기 (-10초)
        if (name === 'KeywordAgent' && context.userKeywords && context.userKeywords.length > 0) {
          console.log('⏭️ [Orchestrator] KeywordAgent 스킵 (사용자 키워드 있음):', context.userKeywords);
          this.results[name] = {
            success: true,
            data: { keywords: context.userKeywords.map(kw => ({ keyword: kw, score: 1 })), primary: context.userKeywords[0] },
            metadata: { duration: 0, skipped: true }
          };
          continue;  // 다음 Agent로
        }

        const agent = new AgentClass();

        // 이전 결과를 컨텍스트에 포함
        currentContext.previousResults = { ...this.results };

        // 컨텍스트 보강 (Agent별 필요 데이터 전달)
        const enrichedContext = this.enrichContext(name, currentContext);

        console.log(`▶️ [Orchestrator] ${name} 실행 시작`);

        // Agent 실행
        const result = await agent.run(enrichedContext);
        this.results[name] = result; // 실행된 인스턴스 이름으로 저장 (ChainWriterAgent여도 'WriterAgent' 키로 저장됨)

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

        // 🔧 ComplianceAgent 검증 실패 시 재검증 루프 실행
        if (name === 'ComplianceAgent' && result.success && result.data?.passed === false) {
          await this.runRefinementLoop(result, currentContext);
        }

      } catch (error) {
        console.error(`❌ [Orchestrator] Agent 실행 오류 (${name}):`, error.message);

        if (required) {
          return this.buildFinalResult(false, `${name} 오류: ${error.message}`);
        }
      }
    }

    // 🎯 파이프라인 종료 전 최종 품질 검사
    await this.ensureQualityThreshold(currentContext);

    return this.buildFinalResult(true);
  }

  isTimedOut() {
    if (!this.startTime) return false;
    return (Date.now() - this.startTime) > this.options.timeout;
  }

  /**
   * 🎯 최종 품질 기준 검사 - SEO 통과 여부 및 이슈 체크
   * ComplianceAgent가 통과해도 SEO가 실패면 EditorAgent로 개선
   */
  async ensureQualityThreshold(context) {
    let seoResult = this.results.SEOAgent?.data;
    let complianceResult = this.results.ComplianceAgent?.data;

    if (!seoResult || !complianceResult) return;

    let currentSeoPassed = seoResult.seoPassed ?? seoResult.passed ?? false;
    let criticalIssues = (complianceResult.issues || [])
      .filter(i => i.severity === 'critical' || i.severity === 'high').length;

    // 이미 기준 충족이면 종료
    if (currentSeoPassed && criticalIssues === 0) {
      complianceResult.qualityThresholdMet = true;
      return;
    }

    console.log(`🎯 [Orchestrator] 최종 품질 검사 시작: SEO=${currentSeoPassed ? 'PASS' : 'FAIL'}, 심각 이슈=${criticalIssues}`);

    // SEO 기준 미달 시 EditorAgent로 개선 시도
    let currentContent = complianceResult.content;
    let currentTitle = complianceResult.title || this.results.WriterAgent?.data?.title || '';
    let attempt = 0;
    const maxAttempts = QUALITY_THRESHOLDS.MAX_REFINEMENT_ATTEMPTS;

    // 🔧 refinementAttempts 보존 (SEO 루프에서 complianceResult 덮어쓰기 전에 저장)
    const previousRefinementAttempts = complianceResult.refinementAttempts || 0;

    while (attempt < maxAttempts && !currentSeoPassed) {
      if (this.isTimedOut()) {
        console.warn('[Orchestrator] Timeout reached during SEO refinement loop.');
        break;
      }

      attempt++;
      console.log(`🔧 [Orchestrator] SEO 개선 시도 ${attempt}/${maxAttempts}`);

      try {
        const currentSuggestions = this.results.SEOAgent?.data?.suggestions || [];
        if (currentSuggestions.length === 0) break;

        const editorResult = await refineWithLLM({
          content: currentContent,
          title: currentTitle,
          validationResult: {
            passed: true,
            details: {
              electionLaw: { violations: [] },
              repetition: { repeatedSentences: [] },
              seo: {
                passed: currentSeoPassed,
                issues: this.results.SEOAgent?.data?.issues || [],
                suggestions: currentSuggestions.map(s => s.suggestion || s)
              }
            }
          },
          keywordResult: null,
          userKeywords: context.userKeywords || [],
          seoKeywords: context.keywords || [],
          status: context.userProfile?.status || '준비',
          modelName: 'gemini-2.5-flash',
          factAllowlist: context.factAllowlist || null,
          targetWordCount: context.targetWordCount,
          dilutionAnalysis: this.results.SEOAgent?.data?.analysis?.dilutionAnalysis || null  // 🔑 키워드 희석 분석
        });

        if (editorResult.edited) {
          currentContent = editorResult.content;
          currentTitle = editorResult.title || currentTitle;
          console.log(`✅ [Orchestrator] SEO 개선 완료:`, editorResult.editSummary);

          // 🔧 SEO 개선 후 Compliance 재검증 (제목 변경 시 필수)
          const complianceAgent = new ComplianceAgent();
          const complianceRecheck = await complianceAgent.run({
            ...context,
            previousResults: {
              ...this.results,
              WriterAgent: { success: true, data: { content: currentContent, title: currentTitle } }
            }
          });

          if (complianceRecheck.success) {
            this.results.ComplianceAgent = complianceRecheck;
            complianceResult = complianceRecheck.data;

            // 🔧 Compliance auto-fix 동기화 (빈 문자열도 유효한 값이므로 !== undefined 체크)
            if (complianceResult.content !== undefined) {
              currentContent = complianceResult.content;
            }
            if (complianceResult.title !== undefined) {
              currentTitle = complianceResult.title;
            }

            criticalIssues = (complianceResult.issues || [])
              .filter(i => i.severity === 'critical' || i.severity === 'high').length;

            if (criticalIssues > 0) {
              console.warn(`⚠️ [Orchestrator] SEO 개선 후 Compliance 실패: ${criticalIssues}개 이슈`);
              // Compliance 실패 시 루프 중단 - 이전 상태로 롤백하지 않고 경고만
            }
          }

          // SEO 재검증
          const seoAgent = new SEOAgent();
          const newSeoResult = await seoAgent.run({
            ...context,
            previousResults: {
              ...this.results,
              WriterAgent: { success: true, data: { content: currentContent, title: currentTitle } }
            }
          });

          if (newSeoResult.success) {
            this.results.SEOAgent = newSeoResult;
            currentSeoPassed = newSeoResult.data.seoPassed ?? newSeoResult.data.passed ?? false;
            if (currentSeoPassed) {
              console.log('✅ [Orchestrator] SEO 기준 충족: PASS');
              break;
            }
          }
        } else {
          break;
        }
      } catch (error) {
        console.warn(`⚠️ [Orchestrator] SEO 개선 실패:`, error.message);
        break;
      }
    }

    // 최종 결과 업데이트
    this.results.ComplianceAgent.data.content = currentContent;
    this.results.ComplianceAgent.data.title = currentTitle;

    const finalSeoPassed = this.results.SEOAgent?.data?.seoPassed ?? this.results.SEOAgent?.data?.passed ?? false;
    const finalCriticalIssues = (this.results.ComplianceAgent?.data?.issues || [])
      .filter(i => i.severity === 'critical' || i.severity === 'high').length;
    const finalQualityMet = finalSeoPassed && finalCriticalIssues === 0;
    this.results.ComplianceAgent.data.qualityThresholdMet = finalQualityMet;
    this.results.ComplianceAgent.data.refinementAttempts = previousRefinementAttempts + attempt;

    console.log(`🎯 [Orchestrator] 최종 품질 결과: SEO=${finalSeoPassed ? 'PASS' : 'FAIL'}, 이슈=${finalCriticalIssues}, 기준충족=${finalQualityMet}`);
  }

  /**
   * 🔄 재검증 루프 - 품질 기준 충족까지 EditorAgent 반복 호출
   * @param {Object} complianceResult - 초기 ComplianceAgent 결과
   * @param {Object} context - 현재 컨텍스트
   */
  async runRefinementLoop(complianceResult, context) {
    const maxAttempts = QUALITY_THRESHOLDS.MAX_REFINEMENT_ATTEMPTS;
    let attempt = 0;
    let currentContent = complianceResult.data.content;
    let currentTitle = complianceResult.data.title || this.results.WriterAgent?.data?.title || '';
    let qualityMet = false;

    console.log(`🔄 [Orchestrator] 재검증 루프 시작 (최대 ${maxAttempts}회)`);

    while (attempt < maxAttempts && !qualityMet) {
      if (this.isTimedOut()) {
        console.warn('[Orchestrator] Timeout reached during compliance refinement loop.');
        break;
      }

      attempt++;
      console.log(`🔄 [Orchestrator] 재검증 시도 ${attempt}/${maxAttempts}`);

      // 1. 현재 이슈 수집
      const issues = complianceResult.data.issues || [];
      const titleIssues = complianceResult.data.titleIssues || [];

      const factIssues = issues.filter(i => i.type === 'fact_check');
      const factTitleIssues = titleIssues.filter(i => i.type === 'title_fact_check');
      const factCheckDetails = (factIssues.length > 0 || factTitleIssues.length > 0) ? {
        content: { unsupported: factIssues.flatMap(i => i.matches || []) },
        title: { unsupported: factTitleIssues.flatMap(i => i.matches || []) }
      } : null;


      // critical, high 이슈만 필터링 (반드시 해결해야 함)
      const criticalIssues = issues.filter(i =>
        i.severity === 'critical' || i.severity === 'high'
      );

      console.log(`📊 [Orchestrator] 현재 이슈: critical/high=${criticalIssues.length}, 제목=${titleIssues.length}`);

      // 2. EditorAgent 호출
      try {
        const titleQualityDetails = titleIssues.length > 0 ? {
          passed: false,
          issues: titleIssues.map(i => ({
            type: i.type,
            severity: i.severity,
            description: i.reason,
            instruction: i.suggestion
          }))
        } : null;

        const editorResult = await refineWithLLM({
          content: currentContent,
          title: currentTitle,
          validationResult: {
            passed: false,
            details: {
              electionLaw: {
                violations: issues
                  .filter(i => i.type === 'election_law' || i.type === 'election_law_legal_js')
                  .map(i => i.match || i.matches?.join(', ') || i.reason)
              },
              repetition: { repeatedSentences: [] },
              titleQuality: titleQualityDetails,
              factCheck: factCheckDetails
            }
          },
          keywordResult: null,
          userKeywords: context.userKeywords || [],
          seoKeywords: context.keywords || [],
          status: context.userProfile?.status || '준비',
          modelName: 'gemini-2.5-flash',
          factAllowlist: context.factAllowlist || null,
          targetWordCount: context.targetWordCount,
          dilutionAnalysis: this.results.SEOAgent?.data?.analysis?.dilutionAnalysis || null  // 🔑 키워드 희석 분석
        });

        if (editorResult.edited) {
          currentContent = editorResult.content;
          currentTitle = editorResult.title || currentTitle;
          console.log(`✅ [Orchestrator] EditorAgent 수정 완료 (시도 ${attempt}):`, editorResult.editSummary);
        } else {
          console.log(`⚠️ [Orchestrator] EditorAgent 수정 없음 (시도 ${attempt})`);
        }
      } catch (editorError) {
        console.warn(`⚠️ [Orchestrator] EditorAgent 실패 (시도 ${attempt}):`, editorError.message);
        continue;
      }

      // 3. ComplianceAgent 재검증
      try {
        const complianceAgent = new ComplianceAgent();
        const revalidationContext = {
          ...context,
          previousResults: {
            ...this.results,
            WriterAgent: {
              success: true,
              data: {
                content: currentContent,
                title: currentTitle
              }
            }
          }
        };

        const revalidationResult = await complianceAgent.run(revalidationContext);

        if (revalidationResult.success) {
          complianceResult = revalidationResult;
          // 🔧 this.results에도 반영 (buildFinalResult, ensureQualityThreshold가 최신 상태 참조)
          this.results.ComplianceAgent = revalidationResult;

          // 🔧 Compliance auto-fix 동기화 (빈 문자열도 유효한 값이므로 !== undefined 체크)
          if (revalidationResult.data.content !== undefined) {
            currentContent = revalidationResult.data.content;
          }
          if (revalidationResult.data.title !== undefined) {
            currentTitle = revalidationResult.data.title;
          }

          // critical/high 이슈 체크
          const newCriticalIssues = (revalidationResult.data.issues || [])
            .filter(i => i.severity === 'critical' || i.severity === 'high');
          const newTitleIssues = revalidationResult.data.titleIssues || [];

          console.log(`📊 [Orchestrator] 재검증 결과: critical/high=${newCriticalIssues.length}, 제목=${newTitleIssues.length}, passed=${revalidationResult.data.passed}`);

          // 품질 기준 충족 여부 판단
          if (revalidationResult.data.passed && newCriticalIssues.length === 0 && newTitleIssues.length === 0) {
            qualityMet = true;
            console.log(`✅ [Orchestrator] 품질 기준 충족! (시도 ${attempt})`);
          }
        }
      } catch (revalidationError) {
        console.warn(`⚠️ [Orchestrator] 재검증 실패 (시도 ${attempt}):`, revalidationError.message);
      }
    }

    // 4. SEOAgent 검증 및 SEO 개선 루프 (선거법 통과 후)
    if (qualityMet) {
      let seoAttempt = 0;
      const maxSeoAttempts = 2;  // SEO 개선 최대 2회 시도

      while (seoAttempt < maxSeoAttempts) {
        if (this.isTimedOut()) {
          console.warn('[Orchestrator] Timeout reached during post-compliance SEO loop.');
          break;
        }

        seoAttempt++;

        try {
          const seoAgent = new SEOAgent();
          const seoContext = {
            ...context,
            previousResults: {
              ...this.results,
              WriterAgent: { success: true, data: { content: currentContent, title: currentTitle } },
              ComplianceAgent: complianceResult
            }
          };

          const seoResult = await seoAgent.run(seoContext);

          if (seoResult.success) {
            const seoPassed = seoResult.data.seoPassed ?? seoResult.data.passed ?? false;
            const suggestions = seoResult.data.suggestions || [];
            console.log(`📊 [Orchestrator] SEO 상태: ${seoPassed ? 'PASS' : 'FAIL'} (시도 ${seoAttempt})`);

            this.results.SEOAgent = seoResult;

            if (seoPassed) {
              console.log(`✅ [Orchestrator] SEO 기준 충족!`);
              break;
            }

            // SEO 미달 시 EditorAgent로 개선 시도
            if (seoAttempt < maxSeoAttempts && suggestions.length > 0) {
              console.log(`🔧 [Orchestrator] SEO 개선 시도 (${suggestions.length}개 제안)`);

              try {
                const seoEditorResult = await refineWithLLM({
                  content: currentContent,
                  title: currentTitle,
                  validationResult: {
                    passed: true,
                    details: {
                      electionLaw: { violations: [] },
                      repetition: { repeatedSentences: [] },
                      seo: {
                        passed: seoPassed,
                        issues: seoResult.data.issues || [],
                        suggestions: suggestions.map(s => s.suggestion || s)
                      }
                    }
                  },
                  keywordResult: null,
                  userKeywords: context.userKeywords || [],
                  seoKeywords: context.keywords || [],
                  status: context.userProfile?.status || '준비',
                  modelName: 'gemini-2.5-flash',
                  factAllowlist: context.factAllowlist || null,
                  targetWordCount: context.targetWordCount,
                  dilutionAnalysis: this.results.SEOAgent?.data?.analysis?.dilutionAnalysis || null  // 🔑 키워드 희석 분석
                });

                if (seoEditorResult.edited) {
                  currentContent = seoEditorResult.content;
                  currentTitle = seoEditorResult.title || currentTitle;
                  console.log(`✅ [Orchestrator] SEO 개선 완료:`, seoEditorResult.editSummary);

                  // 콘텐츠 업데이트
                  this.results.ComplianceAgent.data.content = currentContent;
                  this.results.ComplianceAgent.data.title = currentTitle;
                }
              } catch (seoEditorError) {
                console.warn(`⚠️ [Orchestrator] SEO 개선 실패:`, seoEditorError.message);
                break;
              }
            } else {
              qualityMet = false;
              console.warn('⚠️ [Orchestrator] SEO 기준 미달 (FAIL)');
              break;
            }
          }
        } catch (seoError) {
          console.warn(`⚠️ [Orchestrator] SEO 검증 실패:`, seoError.message);
          break;
        }
      }
    }

    // 5. 최종 결과 업데이트
    this.results.ComplianceAgent.data.content = currentContent;
    this.results.ComplianceAgent.data.title = currentTitle;
    this.results.ComplianceAgent.data.editorApplied = true;
    this.results.ComplianceAgent.data.refinementAttempts = attempt;
    this.results.ComplianceAgent.data.qualityThresholdMet = qualityMet;

    if (!qualityMet) {
      console.warn(`⚠️ [Orchestrator] ${maxAttempts}회 시도 후에도 품질 기준 미충족`);
    }
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

      case 'TitleAgent':
        // TitleAgent는 WriterAgent 결과 필요 (previousResults에 포함됨)
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
      // 🏷️ ComplianceAgent도 제목을 반환하므로 우선 사용 (EditorAgent로 수정된 제목 포함)
      finalTitle = this.results.ComplianceAgent.data.title || this.results.TitleAgent?.data?.title || this.results.WriterAgent?.data?.title || null;
    } else if (this.results.WriterAgent?.success) {
      finalContent = this.results.WriterAgent.data.content;
      finalTitle = this.results.TitleAgent?.data?.title || this.results.WriterAgent.data.title;
    }

    // 메타데이터 수집
    const keywords = this.results.KeywordAgent?.data?.keywords || [];
    const complianceResult = this.results.ComplianceAgent?.data || {};
    const seoResult = this.results.SEOAgent?.data || {};

    // 품질 기준 충족 여부
    const qualityThresholdMet = complianceResult.qualityThresholdMet ?? null;
    const refinementAttempts = complianceResult.refinementAttempts ?? 0;

    console.log(`🎭 [Orchestrator] 파이프라인 완료 (${duration}ms)`, {
      success,
      agentsRun: Object.keys(this.results).length,
      hasContent: !!finalContent,
      hasTitle: !!finalTitle,
      qualityThresholdMet,
      refinementAttempts
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
          passed: seoResult.seoPassed ?? seoResult.passed ?? null,
          issueCount: seoResult.issues?.length || 0,
          issues: seoResult.issues || [],
          suggestions: seoResult.suggestions || []
        },
        // 글자수
        wordCount: finalContent ? finalContent.replace(/<[^>]*>/g, '').length : 0,
        // 🎯 품질 기준 정보
        quality: {
          thresholdMet: qualityThresholdMet,
          refinementAttempts,
          seoRequired: QUALITY_THRESHOLDS.SEO_REQUIRED,
          maxRefinementAttempts: QUALITY_THRESHOLDS.MAX_REFINEMENT_ATTEMPTS
        }
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
