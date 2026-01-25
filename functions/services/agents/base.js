'use strict';

/**
 * Agent Base Class - Multi-Agent 시스템 기반 클래스
 *
 * Context Engineering 적용:
 * - 각 Agent는 특정 역할에 집중
 * - 필요한 컨텍스트만 로드하여 토큰 효율화
 * - Agent 간 통신은 구조화된 메시지로
 */

/**
 * Agent 실행 결과
 * @typedef {Object} AgentResult
 * @property {boolean} success - 성공 여부
 * @property {*} data - 결과 데이터
 * @property {string} [error] - 에러 메시지
 * @property {Object} [metadata] - 메타데이터 (실행 시간 등)
 */

/**
 * Agent 컨텍스트
 * @typedef {Object} AgentContext
 * @property {string} uid - 사용자 ID
 * @property {string} category - 카테고리
 * @property {string} topic - 주제
 * @property {Object} userProfile - 사용자 프로필
 * @property {Object} [previousResults] - 이전 Agent 결과
 */

class BaseAgent {
  constructor(name, options = {}) {
    this.name = name;
    this.options = options;
    this.startTime = null;
  }

  /**
   * Agent 실행 (서브클래스에서 구현)
   * @param {AgentContext} context - 실행 컨텍스트
   * @returns {Promise<AgentResult>}
   */
  async execute(context) {
    throw new Error(`${this.name}: execute() must be implemented`);
  }

  /**
   * Agent 실행 래퍼 (로깅, 에러 핸들링)
   * @param {AgentContext} context
   * @returns {Promise<AgentResult>}
   */
  async run(context) {
    this.startTime = Date.now();
    console.log(`🤖 [${this.name}] 시작`);

    try {
      const required = this.getRequiredContext();
      const missingKeys = required.filter((key) => context[key] === undefined);
      if (missingKeys.length > 0) {
        const duration = Date.now() - this.startTime;
        const errorMessage = `${this.name}: 필수 컨텍스트 누락 (${missingKeys.join(', ')})`;
        console.warn(`⚠️ [${this.name}] ${errorMessage}`);
        return {
          success: false,
          data: null,
          error: errorMessage,
          metadata: {
            agent: this.name,
            duration,
            timestamp: new Date().toISOString()
          }
        };
      }

      const result = await this.execute(context);
      const duration = Date.now() - this.startTime;

      console.log(`✅ [${this.name}] 완료 (${duration}ms)`);

      return {
        success: true,
        data: result,
        metadata: {
          agent: this.name,
          duration,
          timestamp: new Date().toISOString()
        }
      };
    } catch (error) {
      const duration = Date.now() - this.startTime;
      console.error(`❌ [${this.name}] 실패 (${duration}ms):`, error.message);

      return {
        success: false,
        data: null,
        error: error.message,
        metadata: {
          agent: this.name,
          duration,
          timestamp: new Date().toISOString()
        }
      };
    }
  }

  /**
   * 필요한 컨텍스트 키 (서브클래스에서 오버라이드)
   * @returns {string[]}
   */
  getRequiredContext() {
    return [];
  }

  /**
   * 컨텍스트 검증
   * @param {AgentContext} context
   * @returns {boolean}
   */
  validateContext(context) {
    const required = this.getRequiredContext();
    for (const key of required) {
      if (context[key] === undefined) {
        console.warn(`⚠️ [${this.name}] 필수 컨텍스트 누락: ${key}`);
        return false;
      }
    }
    return true;
  }
}

module.exports = { BaseAgent };
