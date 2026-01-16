// frontend/src/theme/tokens.js
// 디자인 토큰 - Single Source of Truth

/**
 * 색상 토큰
 * - 게슈탈트 법칙: 유사성(Similarity)을 위한 일관된 컬러 체계
 */
export const colors = {
  // 브랜드 컬러
  brand: {
    primary: '#152484',                         // 더불어민주당 블루
    primaryHover: '#1e30a0',                    // 호버 시 밝은 블루
    primaryLight: 'rgba(21, 36, 132, 0.05)',    // 배경용 연한 블루
    primaryLight10: 'rgba(21, 36, 132, 0.1)',   // 배경용 10% 투명도
    primaryBorder: 'rgba(21, 36, 132, 0.3)',    // 테두리용 블루
    primaryText: '#152484',                      // 텍스트용 블루

    secondary: '#152484',                        // 더불어민주당 블루
    secondaryHover: '#0f1a5f',                   // 호버 시 어두운 블루
    secondaryLight: 'rgba(21, 36, 132, 0.05)',  // 배경용 연한 민주당 블루

    accent: '#00d4ff',                           // 강조 시안
    accentHover: '#00c4ef',                      // 시안 호버
    accentLight5: 'rgba(0, 212, 255, 0.05)',    // 시안 배경 5%
    accentLight20: 'rgba(0, 212, 255, 0.2)',    // 시안 배경 20%
    accentBorder30: 'rgba(0, 212, 255, 0.3)',   // 시안 테두리 30%
    accentBorder40: 'rgba(0, 212, 255, 0.4)',   // 시안 테두리 40%
    accentBorder50: 'rgba(0, 212, 255, 0.5)',   // 시안 테두리 50%
    accentGlow60: 'rgba(0, 212, 255, 0.6)',     // 시안 글로우 60%
    accentGlow80: 'rgba(0, 212, 255, 0.8)',     // 시안 글로우 80%

    gold: '#f8c023',                             // 골드/노란색
    goldBorder: 'rgba(248, 192, 35, 0.25)',     // 골드 테두리 (40 in hex = 25%)
    goldGlow40: 'rgba(248, 192, 35, 0.4)',      // 골드 글로우 40%
    goldGlow80: 'rgba(248, 192, 35, 0.8)',      // 골드 글로우 80%

    warning: 'rgba(255, 193, 7, 1)',            // 경고 색상
    warningLight10: 'rgba(255, 193, 7, 0.1)',   // 경고 배경
    warningBorder30: 'rgba(255, 193, 7, 0.3)',  // 경고 테두리
  },

  // UI 구조 컬러
  ui: {
    header: 'rgba(0, 0, 0, 0.3)',
    headerHover: 'rgba(79, 195, 247, 0.15)',
    background: '#0a0a0a',
    backgroundDark1: 'rgba(0, 0, 0, 0.02)',      // 섹션 배경
    backgroundLight1: 'rgba(255, 255, 255, 0.01)', // 매우 연한 배경
    backgroundLight2: 'rgba(255, 255, 255, 0.02)', // 연한 배경
    backgroundLight3: 'rgba(255, 255, 255, 0.03)', // 카드 배경
    backgroundLight5: 'rgba(255, 255, 255, 0.05)', // 강조 배경
    backgroundLight6: 'rgba(255, 255, 255, 0.06)', // 더 강한 배경
    backgroundEmphasis: 'rgba(79, 195, 247, 0.05)', // 강조 배경
    gridLineHorizontal: 'rgba(79, 195, 247, 0.15)',
    gridLineVertical: 'rgba(79, 195, 247, 0.08)',
    divider: 'rgba(255, 255, 255, 0.1)',
    divider12: 'rgba(255, 255, 255, 0.12)',      // 테두리용
    divider20: 'rgba(255, 255, 255, 0.2)',       // 테두리용
    divider30: 'rgba(255, 255, 255, 0.3)',       // 테두리용
  },

  // 텍스트 컬러
  text: {
    primary: 'rgba(255, 255, 255, 0.9)',      // 제목용
    secondary: 'rgba(255, 255, 255, 0.7)',    // 본문용
    tertiary: 'rgba(255, 255, 255, 0.5)',     // 부가설명용
    muted60: 'rgba(255, 255, 255, 0.6)',      // 더 흐린 텍스트
    muted75: 'rgba(255, 255, 255, 0.75)',     // 중간 흐림
    muted80: 'rgba(255, 255, 255, 0.8)',      // 약간 흐림
    emphasis: '#4FC3F7',                       // 강조 텍스트
    black: '#000000',
    white: '#ffffff',
  },

  // 테두리 컬러
  border: {
    default: 'rgba(255, 255, 255, 0.1)',
    emphasis: 'rgba(79, 195, 247, 0.3)',
    dashed: 'rgba(255, 255, 255, 0.2)',
    accent: 'rgba(0, 212, 255, 0.4)',         // #00d4ff40와 동일
    gold: 'rgba(248, 192, 35, 0.25)',         // #f8c02340과 동일
  },

  // 플랜 컬러 (요금제 등)
  plan: {
    local: '#003a87',                          // 로컬 블로거
    localBorder: 'rgba(0, 58, 135, 0.25)',    // #003a8740과 동일
    localShadow: 'rgba(0, 58, 135, 0.19)',    // #003a8730과 동일

    region: '#55207d',                         // 리전 인플루언서
    regionBorder: 'rgba(85, 32, 125, 0.25)',  // #55207d40과 동일
    regionShadow: 'rgba(85, 32, 125, 0.19)',  // #55207d30과 동일

    opinion: '#006261',                        // 오피니언 리더
    opinionBorder: 'rgba(0, 98, 97, 0.25)',   // #00626140과 동일
    opinionShadow: 'rgba(0, 98, 97, 0.19)',   // #00626130과 동일
  },

  // 상태별 컬러
  state: {
    success: '#10b981',
    warning: '#f59e0b',
    error: '#ef4444',
    info: '#4FC3F7',
  },

  // 그라데이션
  gradient: {
    divider: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
    footer: 'linear-gradient(to bottom, #001320, #050511)',
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
 * - 명시적 px 단위 사용으로 일관성 확보
 */
export const borders = {
  radius: {
    none: '0px',
    sm: '2px',
    md: '4px',
    lg: '8px',
    xl: '12px',
    round: '9999px',
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
