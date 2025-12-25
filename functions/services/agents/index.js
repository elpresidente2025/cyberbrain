'use strict';

/**
 * Multi-Agent System - 통합 모듈
 *
 * Context Engineering 기반 에이전트 시스템
 * - 각 Agent는 특정 역할에 집중
 * - Orchestrator가 파이프라인 조율
 * - 필요한 컨텍스트만 로드하여 효율화
 */

const { BaseAgent } = require('./base');
const { KeywordAgent } = require('./keyword-agent');
const { WriterAgent } = require('./writer-agent');
const { ComplianceAgent } = require('./compliance-agent');
const { SEOAgent } = require('./seo-agent');
const { Orchestrator, runAgentPipeline, PIPELINES } = require('./orchestrator');

module.exports = {
  // Base
  BaseAgent,

  // Agents
  KeywordAgent,
  WriterAgent,
  ComplianceAgent,
  SEOAgent,

  // Orchestrator
  Orchestrator,
  runAgentPipeline,
  PIPELINES
};
