import { createTheme } from '@mui/material/styles';
import { colors } from './theme/tokens';

const createCustomTheme = (isDarkMode) => createTheme({
  // 1. 색상(Color) 설정 - 라이트/다크 모드 대응
  palette: {
    mode: isDarkMode ? 'dark' : 'light',
    primary: {
      main: isDarkMode ? '#4FC3F7' : '#013c95',
    },
    // 브랜드 컬러 (디자인 토큰 통합)
    brand: {
      primary: colors.brand.primary,
      primaryHover: colors.brand.primaryHover,
      primaryLight: colors.brand.primaryLight,
      primaryBorder: colors.brand.primaryBorder,
    },
    // UI 구조 컬러 (디자인 토큰 통합)
    ui: {
      header: colors.ui.header,
      headerHover: colors.ui.headerHover,
      background: colors.ui.background,
      backgroundLight: colors.ui.backgroundLight,
      gridLineHorizontal: colors.ui.gridLineHorizontal,
      gridLineVertical: colors.ui.gridLineVertical,
      divider: colors.ui.divider,
    },
    background: {
      default: 'transparent',
      paper: isDarkMode ? '#1a1a1a' : '#f5f5f5',
    },
    text: {
      primary: isDarkMode ? '#ffffff' : '#000000',
      secondary: isDarkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)',
    },
  },
  // 2. 브레이크포인트 설정 (가이드 2절)
  breakpoints: {
    values: {
      xs: 360,    // 모바일 세로
      sm: 600,    // 모바일 가로 / 태블릿 세로
      md: 900,    // 태블릿 가로
      lg: 1280,   // 데스크탑 작은 화면
      xl: 1680,   // 데스크탑 큰 화면
      xxl: 2560,  // QHD 2K 화면 (2560px)
      xxxl: 3840, // 4K UHD 화면 (3840px)
    },
  },
  // 3. 타이포그래피 설정 (가이드 4절)
  typography: {
    fontFamily: '"Spoqa Han Sans Neo", -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif',
    h1: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
      fontSize: '2.5rem', // 기본 폰트 크기 설정
      '@media (min-width: 2560px)': {
        fontSize: '3rem', // 2K에서 더 큰 폰트
      },
      '@media (min-width: 3840px)': {
        fontSize: '3.5rem', // 4K에서 더 큰 폰트
      },
    },
    h2: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
      '@media (min-width: 2560px)': {
        fontSize: '2.5rem',
      },
      '@media (min-width: 3840px)': {
        fontSize: '3rem',
      },
    },
    h3: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
      '@media (min-width: 2560px)': {
        fontSize: '2rem',
      },
      '@media (min-width: 3840px)': {
        fontSize: '2.25rem',
      },
    },
    h4: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
    },
    h5: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
    },
    h6: {
      fontFamily: '"NanumSquare", "Spoqa Han Sans Neo", sans-serif',
    },
    body1: {
      '@media (min-width: 2560px)': {
        fontSize: '1.125rem', // 2K에서 더 큰 본문 텍스트
      },
      '@media (min-width: 3840px)': {
        fontSize: '1.25rem', // 4K에서 더 큰 본문 텍스트
      },
    },
    body2: {
      '@media (min-width: 2560px)': {
        fontSize: '1rem',
      },
      '@media (min-width: 3840px)': {
        fontSize: '1.125rem',
      },
    },
    // 사이버펑크 터미널 폰트
    mono: {
      fontFamily: '"Courier New", "SF Mono", "Monaco", monospace',
    }
  },
  // 4. 간격(Spacing) 설정 (가이드 4절)
  spacing: 4, // Spacing Base를 4px로 설정 (theme.spacing(2) === 8px)
  // 5. 컴포넌트 기본 스타일 오버라이드
  components: {
    MuiContainer: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.up('xl')]: {
            maxWidth: '1440px', // XL 뷰포트에서 최대 너비 제한
          },
          [theme.breakpoints.up('xxl')]: {
            maxWidth: '1920px', // 2K 화면에서 최대 너비
          },
          [theme.breakpoints.up('xxxl')]: {
            maxWidth: '2560px', // 4K 화면에서 최대 너비
          },
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          // 글래스모피즘 효과
          backgroundColor: isDarkMode 
            ? 'rgba(255, 255, 255, 0.05)' 
            : 'rgba(255, 255, 255, 0.15)',
          color: isDarkMode ? '#ffffff' : '#000000',
          borderRadius: '12px',
          border: isDarkMode 
            ? '1px solid rgba(255, 255, 255, 0.1)' 
            : '1px solid rgba(255, 255, 255, 0.2)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
          boxShadow: isDarkMode
            ? '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
            : '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          // 글래스모피즘 효과
          backgroundColor: isDarkMode 
            ? 'rgba(255, 255, 255, 0.05)' 
            : 'rgba(255, 255, 255, 0.15)',
          color: isDarkMode ? '#ffffff' : '#000000',
          borderRadius: '12px',
          border: isDarkMode 
            ? '1px solid rgba(255, 255, 255, 0.1)' 
            : '1px solid rgba(255, 255, 255, 0.2)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
          boxShadow: isDarkMode
            ? '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
            : '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
        },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: ({ ownerState }) => ({
          // Paper 내부의 Typography 색상 - 다크모드 대응
          '.MuiPaper-root &': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
          // Alert 내부의 Typography 색상 - 다크모드 대응
          '.MuiAlert-root &': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
        }),
      },
    },
    MuiCircularProgress: {
      styleOverrides: {
        root: {
          color: '#f8c023',
          filter: 'drop-shadow(0 0 6px #f8c023)',
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-input': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
          '& .MuiSelect-select': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-input': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          color: isDarkMode ? '#ffffff' : '#000000',
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          color: isDarkMode ? '#ffffff !important' : '#000000 !important',
          '&.Mui-focused': {
            color: isDarkMode ? '#ffffff !important' : '#000000 !important',
          },
        },
      },
    },
    MuiFormControl: {
      styleOverrides: {
        root: {
          '& .MuiInputBase-root': {
            color: isDarkMode ? '#ffffff' : '#000000',
          },
          '& .MuiOutlinedInput-root': {
            '& fieldset': {
              borderColor: isDarkMode ? '#ffffff' : '#000000',
            },
            '&:hover fieldset': {
              borderColor: isDarkMode ? '#ffffff' : '#000000',
            },
            '&.Mui-focused fieldset': {
              borderColor: isDarkMode ? '#ffffff' : '#000000',
            },
          },
        },
      },
    },
    // CSS 렌더링 최적화 - 폰트 블러 방지
    MuiCssBaseline: {
      styleOverrides: {
        html: {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
          textRendering: 'optimizeLegibility',
          fontFeatureSettings: '"kern" 1',
        },
        body: {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
          textRendering: 'optimizeLegibility',
          fontFeatureSettings: '"kern" 1',
        },
        '*': {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
          textRendering: 'optimizeLegibility',
          backfaceVisibility: 'hidden',
          // transform: 'translateZ(0)', // 전역 가속은 스택 컨텍스트를 생성해 fixed 기준을 왜곡시킬 수 있음
        },
      },
    },
    // Dialog 컴포넌트 - 백드롭 그라데이션 및 글로우 효과
    MuiDialog: {
      styleOverrides: {
        root: {
          '& .MuiBackdrop-root': {
            // 백드롭 그라데이션 (중앙에서 밝아짐)
            background: isDarkMode 
              ? 'radial-gradient(circle at center, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0.8) 70%)'
              : 'radial-gradient(circle at center, rgba(0, 0, 0, 0.3) 0%, rgba(0, 0, 0, 0.6) 70%)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
          },
        },
        paper: {
          // 팝업창 글로우 효과 및 강조
          boxShadow: isDarkMode
            ? '0 0 80px rgba(79, 195, 247, 0.3), 0 20px 60px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
            : '0 0 60px rgba(1, 60, 149, 0.25), 0 20px 60px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
          border: isDarkMode 
            ? '2px solid rgba(79, 195, 247, 0.3)' 
            : '2px solid rgba(1, 60, 149, 0.2)',
          borderRadius: '12px',
          backgroundColor: isDarkMode 
            ? 'rgba(26, 26, 26, 0.95)' 
            : 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
          // 글로우 애니메이션
          animation: 'dialogGlow 3s ease-in-out infinite alternate',
          '@keyframes dialogGlow': {
            '0%': {
              boxShadow: isDarkMode
                ? '0 0 80px rgba(79, 195, 247, 0.3), 0 20px 60px rgba(0, 0, 0, 0.7)'
                : '0 0 60px rgba(1, 60, 149, 0.25), 0 20px 60px rgba(0, 0, 0, 0.3)',
            },
            '100%': {
              boxShadow: isDarkMode
                ? '0 0 100px rgba(79, 195, 247, 0.4), 0 25px 70px rgba(0, 0, 0, 0.8)'
                : '0 0 80px rgba(1, 60, 149, 0.35), 0 25px 70px rgba(0, 0, 0, 0.4)',
            },
          },
        },
      },
    },
  },
});

export default createCustomTheme;
