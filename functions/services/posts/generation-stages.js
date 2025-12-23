/**
 * functions/services/posts/generation-stages.js
 * 원고 생성 진행 단계 정의 - Progress Tracker 연동용
 *
 * 프론트엔드에서 사용자에게 현재 진행 상황을 표시하기 위한 단계 정보
 */

'use strict';

/**
 * 생성 단계 정의
 */
const GENERATION_STAGES = {
  // 1단계: 초안 작성
  DRAFTING: {
    step: 1,
    id: 'DRAFTING',
    message: '초안을 작성하고 있습니다...',
    detail: '전뇌비서관이 주제에 맞는 원고를 구상 중입니다',
    icon: '✍️',
    estimatedSeconds: 10
  },

  // 2단계: 기본 검수
  BASIC_CHECK: {
    step: 2,
    id: 'BASIC_CHECK',
    message: '기본 검수를 진행 중입니다...',
    detail: '선거법 준수 여부와 문장 반복을 확인합니다',
    icon: '🔍',
    estimatedSeconds: 2
  },

  // 3단계: 편집장 검토
  EDITOR_REVIEW: {
    step: 3,
    id: 'EDITOR_REVIEW',
    message: '전뇌 편집장이 원고를 정밀 검토 중입니다...',
    detail: '팩트 확인, 정무적 적합성, 유권자 관점을 종합 검토합니다',
    icon: '👔',
    estimatedSeconds: 8
  },

  // 4단계: 수정 반영
  CORRECTING: {
    step: 4,
    id: 'CORRECTING',
    message: '피드백을 반영하여 원고를 다듬고 있습니다...',
    detail: '지적된 사항을 수정하여 품질을 높입니다',
    icon: '✨',
    estimatedSeconds: 8
  },

  // 5단계: 최종 완성
  FINALIZING: {
    step: 5,
    id: 'FINALIZING',
    message: '최종 검수 후 완성합니다...',
    detail: '마지막 품질 확인을 진행합니다',
    icon: '✅',
    estimatedSeconds: 2
  },

  // 완료
  COMPLETED: {
    step: 6,
    id: 'COMPLETED',
    message: '원고가 완성되었습니다!',
    detail: '',
    icon: '🎉',
    estimatedSeconds: 0
  },

  // 오류
  ERROR: {
    step: -1,
    id: 'ERROR',
    message: '원고 생성 중 문제가 발생했습니다',
    detail: '다시 시도해 주세요',
    icon: '❌',
    estimatedSeconds: 0
  }
};

/**
 * 단계별 예상 소요 시간 합계 (초)
 */
const TOTAL_ESTIMATED_SECONDS = Object.values(GENERATION_STAGES)
  .filter(s => s.step > 0)
  .reduce((sum, s) => sum + s.estimatedSeconds, 0);

/**
 * 단계 ID로 단계 정보 조회
 */
function getStageById(stageId) {
  return GENERATION_STAGES[stageId] || GENERATION_STAGES.ERROR;
}

/**
 * 단계 번호로 단계 정보 조회
 */
function getStageByStep(step) {
  return Object.values(GENERATION_STAGES).find(s => s.step === step) || GENERATION_STAGES.ERROR;
}

/**
 * 진행률 계산 (0-100)
 */
function calculateProgress(currentStageId) {
  const stage = GENERATION_STAGES[currentStageId];
  if (!stage || stage.step <= 0) return 0;
  if (stage.id === 'COMPLETED') return 100;

  const totalSteps = 5;  // COMPLETED 제외
  return Math.round((stage.step / totalSteps) * 100);
}

/**
 * Progress Tracker용 상태 객체 생성
 */
function createProgressState(stageId, additionalInfo = {}) {
  const stage = getStageById(stageId);

  return {
    stage: stage.id,
    step: stage.step,
    message: stage.message,
    detail: stage.detail,
    icon: stage.icon,
    progress: calculateProgress(stageId),
    estimatedSecondsRemaining: calculateRemainingTime(stageId),
    ...additionalInfo
  };
}

/**
 * 남은 예상 시간 계산 (초)
 */
function calculateRemainingTime(currentStageId) {
  const currentStage = GENERATION_STAGES[currentStageId];
  if (!currentStage || currentStage.step <= 0) return 0;

  return Object.values(GENERATION_STAGES)
    .filter(s => s.step >= currentStage.step && s.step > 0)
    .reduce((sum, s) => sum + s.estimatedSeconds, 0);
}

/**
 * Critic/Corrector 루프 메시지 생성
 */
function createRetryMessage(attempt, maxAttempts, score) {
  if (attempt === 1) {
    return {
      message: '전뇌 편집장이 원고를 정밀 검토 중입니다...',
      detail: '팩트 확인, 정무적 적합성, 유권자 관점을 종합 검토합니다'
    };
  }

  return {
    message: `원고 품질 개선 중입니다... (${attempt}/${maxAttempts})`,
    detail: `현재 품질 점수: ${score}점 - 더 좋은 결과를 위해 다듬고 있습니다`
  };
}

module.exports = {
  GENERATION_STAGES,
  TOTAL_ESTIMATED_SECONDS,
  getStageById,
  getStageByStep,
  calculateProgress,
  createProgressState,
  calculateRemainingTime,
  createRetryMessage
};
