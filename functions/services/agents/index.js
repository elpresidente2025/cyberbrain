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

// 🆕 모듈형 에이전트 (프롬프트 분산)
const { DraftAgent } = require('./draft-agent');
const { StructureAgent } = require('./structure-agent');
const { KeywordInjectorAgent } = require('./keyword-injector-agent');
const { StyleAgent } = require('./style-agent');

module.exports = {
  // Base
  BaseAgent,

  // Agents (기존)
  KeywordAgent,
  WriterAgent,
  ComplianceAgent,
  SEOAgent,

  // 🆕 Modular Agents (프롬프트 분산)
  DraftAgent,
  StructureAgent,
  KeywordInjectorAgent,
  StyleAgent,

  // Orchestrator
  Orchestrator,
  runAgentPipeline,
  PIPELINES
};
