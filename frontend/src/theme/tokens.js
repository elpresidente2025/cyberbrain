// frontend/src/theme/tokens.js
// 디자인 토큰 - Single Source of Truth

/**
 * 색상 토큰
 * - 게슈탈트 법칙: 유사성(Similarity)을 위한 일관된 컬러 체계
 */
export const colors = {
  // 브랜드 컬러 (파랑 계열 - 사이버펑크 테마)
  brand: {
    primary: '#152484',                    // 메인 파랑 (헤더 통일)
    primaryHover: '#003A87',               // 호버 시 어두운 파랑
    primaryLight: 'rgba(21, 36, 132, 0.1)', // 반투명 배경용
    primaryBorder: 'rgba(21, 36, 132, 0.4)', // 테두리용
    accent: '#00d4ff',                     // 강조 시안
    accentGlow: 'rgba(0, 212, 255, 0.8)',  // 시안 글로우
  },

  // UI 구조 컬러
  ui: {
    header: '#152484',                     // 헤더/푸터 네이비
    headerHover: '#003A87',                // 헤더 호버
    background: '#050511',                 // 다크 배경
    backgroundLight: 'rgba(255, 255, 255, 0.03)', // 카드 배경
    gridLineHorizontal: 'rgba(0, 212, 255, 0.8)', // 그리드 가로선 (시안)
    gridLineVertical: 'rgba(0, 200, 200, 0.6)',   // 그리드 세로선 (시안)
    divider: 'rgba(21, 36, 132, 0.3)',     // 구분선
  },

  // 시맨틱 컬러
  semantic: {
    success: '#1ca152',                    // 성공은 녹색 유지
    info: '#00d4ff',                       // 정보는 시안
    warning: '#ffa726',
    error: '#f44336',
  },

  // 텍스트 컬러
  text: {
    primary: '#ffffff',
    secondary: 'rgba(255, 255, 255, 0.9)',
    tertiary: 'rgba(255, 255, 255, 0.7)',
    disabled: 'rgba(255, 255, 255, 0.5)',
    black: '#000000',
  }
};

/**
 * 간격 토큰 (4px 배수 체계)
 * - 게슈탈트 법칙: 근접성(Proximity)을 위한 일관된 간격
 */
export const spacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
  section: {
    xs: 64,   // 8 * 8
    md: 96,   // 12 * 8
  }
};

/**
 * 테두리 토큰
 */
export const borders = {
  radius: {
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
    round: 9999,
  },
  width: {
    thin: 1,
    medium: 2,
    thick: 3,
  }
};

/**
 * 그림자 토큰
 */
export const shadows = {
  glow: {
    brand: '0 0 10px rgba(21, 36, 132, 0.8)',      // 파랑 글로우
    brandHover: '0 0 15px rgba(21, 36, 132, 1.0)', // 파랑 글로우 강조
    accent: '0 0 10px rgba(0, 212, 255, 0.8)',     // 시안 글로우
    accentHover: '0 0 15px rgba(0, 212, 255, 1.0)', // 시안 글로우 강조
  },
  card: '0 4px 6px rgba(0, 0, 0, 0.1)',
  cardHover: '0 8px 12px rgba(0, 0, 0, 0.15)',
};

/**
 * 폰트 웨이트 토큰
 */
export const fontWeights = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  extrabold: 800,
  black: 900,
};

/**
 * z-index 토큰
 */
export const zIndex = {
  background: -2,
  backgroundOverlay: -1,
  base: 0,
  dropdown: 1000,
  sticky: 1100,
  modal: 1300,
  popover: 1400,
  tooltip: 1500,
};

/**
 * 트랜지션 토큰
 */
export const transitions = {
  fast: '150ms',
  normal: '300ms',
  slow: '500ms',
  easing: {
    easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    easeOut: 'cubic-bezier(0.0, 0, 0.2, 1)',
    easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
  }
};

/**
 * 타이포그래피 스케일 토큰
 * - 게슈탈트 법칙: 유사성(Similarity)을 위한 일관된 타이포그래피
 * - 1.25 배수 스케일 (Major Third) 사용
 */
export const typography = {
  // 폰트 크기 스케일
  fontSize: {
    xs: '0.75rem',      // 12px - caption, helper text
    sm: '0.875rem',     // 14px - body2, small text
    base: '1rem',       // 16px - body1, base
    md: '1.125rem',     // 18px - subtitle
    lg: '1.25rem',      // 20px - h6
    xl: '1.5rem',       // 24px - h5
    '2xl': '1.875rem',  // 30px - h4
    '3xl': '2.25rem',   // 36px - h3
    '4xl': '3rem',      // 48px - h2
    '5xl': '3.75rem',   // 60px - h1
  },

  // Line Height (수직 리듬)
  lineHeight: {
    tight: 1.2,         // 제목용
    snug: 1.375,        // 부제목용
    normal: 1.5,        // 본문용
    relaxed: 1.625,     // 긴 텍스트용
    loose: 2,           // 여유있는 간격
  },

  // Letter Spacing
  letterSpacing: {
    tighter: '-0.05em',
    tight: '-0.025em',
    normal: '0',
    wide: '0.025em',
    wider: '0.05em',
    widest: '0.1em',
  }
};

/**
 * 수직 리듬(Vertical Rhythm) 토큰
 * - 게슈탈트 법칙: 연속성(Continuity)을 위한 baseline grid
 * - 8px 베이스라인 그리드 시스템
 */
export const verticalRhythm = {
  baselineGrid: 8,

  // 베이스라인 배수 계산 헬퍼
  calculate: (multiplier) => multiplier * 8,

  // 자주 사용하는 값들
  common: {
    xs: 8,      // 1 unit
    sm: 16,     // 2 units
    md: 24,     // 3 units
    lg: 32,     // 4 units
    xl: 48,     // 6 units
    xxl: 64,    // 8 units
  }
};

/**
 * 시각적 가중치(Visual Weight) 토큰
 * - 게슈탈트 법칙: 폐쇄성(Closure)을 위한 일관된 계층 구조
 * - 중요도에 따른 시각적 강도 정의
 */
export const visualWeight = {
  // 최우선 강조 (페이지 제목, 핵심 CTA)
  primary: {
    fontSize: typography.fontSize['2xl'],      // 30px
    fontWeight: fontWeights.bold,              // 700
    lineHeight: typography.lineHeight.tight,   // 1.2
    letterSpacing: typography.letterSpacing.tight, // -0.025em
  },

  // 2차 강조 (섹션 제목, 중요 버튼)
  secondary: {
    fontSize: typography.fontSize.xl,          // 24px
    fontWeight: fontWeights.semibold,          // 600
    lineHeight: typography.lineHeight.snug,    // 1.375
    letterSpacing: typography.letterSpacing.normal, // 0
  },

  // 3차 강조 (카드 제목, 일반 버튼)
  tertiary: {
    fontSize: typography.fontSize.lg,          // 20px
    fontWeight: fontWeights.medium,            // 500
    lineHeight: typography.lineHeight.normal,  // 1.5
    letterSpacing: typography.letterSpacing.normal, // 0
  },

  // 본문 (일반 텍스트)
  body: {
    fontSize: typography.fontSize.base,        // 16px
    fontWeight: fontWeights.regular,           // 400
    lineHeight: typography.lineHeight.normal,  // 1.5
    letterSpacing: typography.letterSpacing.normal, // 0
  },

  // 보조 텍스트 (설명, caption)
  caption: {
    fontSize: typography.fontSize.sm,          // 14px
    fontWeight: fontWeights.regular,           // 400
    lineHeight: typography.lineHeight.relaxed, // 1.625
    letterSpacing: typography.letterSpacing.wide, // 0.025em
  }
};
