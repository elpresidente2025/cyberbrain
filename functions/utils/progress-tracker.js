'use strict';

const { db } = require('./firebaseAdmin');

/**
 * 원고 생성 진행 상황 추적기
 */
class ProgressTracker {
  constructor(sessionId) {
    this.sessionId = sessionId;
    this.progressRef = db.collection('generation_progress').doc(sessionId);
  }

  /**
   * 진행 상황 업데이트
   * @param {number} step - 현재 단계 (1-5)
   * @param {number} progress - 진행률 (0-100)
   * @param {string} message - 진행 메시지
   */
  async update(step, progress, message) {
    try {
      await this.progressRef.set({
        step,
        progress,
        message,
        timestamp: new Date().toISOString(),
        updatedAt: Date.now()
      }, { merge: true });

      console.log(`📊 진행 상황 업데이트: Step ${step} (${progress}%) - ${message}`);
    } catch (error) {
      console.error('⚠️ 진행 상황 업데이트 실패:', error.message);
      // 에러가 발생해도 원고 생성은 계속 진행
    }
  }

  /**
   * 1단계: 준비 중
   */
  async stepPreparing() {
    await this.update(1, 10, '준비 중...');
  }

  /**
   * 2단계: 자료 수집 중
   */
  async stepCollecting() {
    await this.update(2, 25, '자료 수집 중...');
  }

  /**
   * 3단계: AI 원고 작성 중
   */
  async stepGenerating() {
    await this.update(3, 50, 'AI 원고 작성 중...');
  }

  /**
   * 4단계: 품질 검증 중
   */
  async stepValidating() {
    await this.update(4, 80, '품질 검증 중...');
  }

  /**
   * 5단계: 마무리 중
   */
  async stepFinalizing() {
    await this.update(5, 95, '마무리 중...');
  }

  /**
   * 완료
   */
  async complete() {
    await this.update(5, 100, '완료');

    // 완료 후 30초 뒤 자동 삭제 (클라이언트가 읽을 시간 확보)
    setTimeout(async () => {
      try {
        await this.progressRef.delete();
        console.log('🗑️ 진행 상황 문서 자동 삭제:', this.sessionId);
      } catch (error) {
        console.error('⚠️ 진행 상황 문서 삭제 실패:', error.message);
      }
    }, 30000);
  }

  /**
   * 에러 상태로 설정
   */
  async error(errorMessage) {
    try {
      await this.progressRef.set({
        step: -1,
        progress: 0,
        message: `오류: ${errorMessage}`,
        error: true,
        timestamp: new Date().toISOString(),
        updatedAt: Date.now()
      }, { merge: true });

      // 에러 발생 시에도 30초 뒤 삭제
      setTimeout(async () => {
        try {
          await this.progressRef.delete();
        } catch (err) {
          console.error('⚠️ 에러 문서 삭제 실패:', err.message);
        }
      }, 30000);
    } catch (error) {
      console.error('⚠️ 에러 상태 업데이트 실패:', error.message);
    }
  }
}

module.exports = { ProgressTracker };
