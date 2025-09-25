/**
 * frontend/src/constants/formConstants.js (최종본)
 * 전자두뇌비서관의 카테고리 체계를 사용자 친화적인 '용도 기반'으로 재편성한 파일입니다.
 * 사용자는 '글의 목적'을 먼저 선택하며, 각 목적에 맞는 내부 '작법'이 자동으로 매핑됩니다.
 */

// 사용자에게 보여질 용도 기반 카테고리 (User-Facing, Purpose-Based Categories)
export const CATEGORIES = [
  {
    value: 'activity-report',
    label: '의정활동 보고',
    description: '의정 성과, 국정감사, 조례 발의 등 공식적인 의정활동을 주민들께 보고합니다.',
    subCategories: [
      { value: 'performance_report', label: '성과 보고 (예산 확보, 공약 이행 등)', writingMethod: 'logical_writing', needsAudienceStance: false },
      { value: 'parliamentary_audit_report', label: '국정감사 활동 보고', writingMethod: 'critical_writing', needsAudienceStance: false },
      { value: 'bill_ordinance_report', label: '법안/조례 발의 및 위원회 활동 보고', writingMethod: 'analytical_writing', needsAudienceStance: false },
    ],
  },
  {
    value: 'local-issues',
    label: '지역 현안 및 활동',
    description: '지역의 문제점을 분석하고, 주민들과 함께한 활동 내용을 공유합니다.',
    subCategories: [
      { value: 'local_issue_analysis', label: '지역 현안 분석 및 해결책 제시', writingMethod: 'analytical_writing', needsAudienceStance: false },
      { value: 'event_complaint_report', label: '지역 행사/민원 처리 결과 보고', writingMethod: 'analytical_writing', needsAudienceStance: false },
      { value: 'volunteering_review', label: '봉사 후기', writingMethod: 'emotional_writing', needsAudienceStance: false },
    ],
  },
  {
    value: 'policy-proposal',
    label: '정책 및 비전',
    description: '자신의 정치적 비전과 핵심 정책을 주민들께 알기 쉽게 설명합니다.',
    subCategories: [
      { value: 'policy_pledge_announcement', label: '정책/공약 발표', writingMethod: 'logical_writing', needsAudienceStance: false },
      { value: 'vision_philosophy_declaration', label: '비전과 철학 선언', writingMethod: 'direct_writing', needsAudienceStance: false },
    ],
  },
  {
    value: 'educational-content',
    label: '정책/법률/조례 소개',
    description: '복잡한 정책이나 법률, 조례를 주민들이 이해하기 쉽게 설명합니다.',
    subCategories: [
      { value: 'policy_explanation', label: '정책 해설 (국정/지방정부 정책)', writingMethod: 'analytical_writing', needsAudienceStance: false },
      { value: 'law_ordinance_explanation', label: '법률/조례 안내 (새로운 법률, 개정 조례 등)', writingMethod: 'analytical_writing', needsAudienceStance: false },
      { value: 'citizen_guide', label: '시민 생활 가이드 (제도 활용법, 신청 방법)', writingMethod: 'logical_writing', needsAudienceStance: false },
    ],
  },
  {
    value: 'current-affairs',
    label: '이슈 대응 및 논평',
    description: '사회적 현안이나 특정 이슈에 대한 자신의 입장을 명확하게 밝힙니다.',
    subCategories: [
      { value: 'current_affairs_commentary', label: '시사 논평', writingMethod: 'critical_writing', needsAudienceStance: true },
      { value: 'fake_news_rebuttal', label: '가짜뉴스 반박', writingMethod: 'critical_writing', needsAudienceStance: true },
    ],
  },
  {
    value: 'daily-communication',
    label: '일상 소통',
    description: '주민들과 더 가까이 소통하기 위한 감사, 격려, 축하, 일상 이야기 등을 나눕니다.',
    subCategories: [
      { value: 'gratitude_message', label: '감사 메시지', writingMethod: 'emotional_writing', needsAudienceStance: true },
      { value: 'encouragement_support', label: '격려 및 응원', writingMethod: 'emotional_writing', needsAudienceStance: true },
      { value: 'celebration_congratulation', label: '축하 및 기념', writingMethod: 'emotional_writing', needsAudienceStance: true },
      { value: 'daily_life_sharing', label: '일상 공유', writingMethod: 'emotional_writing', needsAudienceStance: false },
    ],
  },
];
