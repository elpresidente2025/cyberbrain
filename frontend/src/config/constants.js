/**
 * 애플리케이션 상수 설정
 */

export const CONFIG = {
  // 원고 생성 관련
  MAX_GENERATION_ATTEMPTS: 3,
  MAX_DRAFTS_STORAGE: 10,
  GENERATE_TIMEOUT_MS: 540000,

  // AI 모델 설정
  DEFAULT_AI_MODEL: 'gemini-2.5-flash-lite',

  // 콘텐츠 품질 기준
  SEO_WORD_THRESHOLD: 1500,
  MIN_CONTENT_LENGTH: 100,

  // UI 설정
  LOADING_DEBOUNCE: 300,
  ERROR_DISPLAY_DURATION: 5000,

  // Firebase 함수 이름
  FUNCTIONS: {
    GENERATE_POSTS: 'generatePosts',
    SAVE_POST: 'saveSelectedPost',
    COLLECT_METADATA: 'collectMetadata'
  }
};
