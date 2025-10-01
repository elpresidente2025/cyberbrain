import { styled } from '@mui/material/styles';
import { Box, Card, Button, Container } from '@mui/material';

export const Page = styled('main')({
  background: '#050511',
  color: '#fff !important',
  minHeight: '100vh',
  wordBreak: 'keep-all',
  '& *': {
    color: '#fff !important',
    wordBreak: 'keep-all',
  },
  '& .MuiTypography-root': {
    color: '#fff !important',
    wordBreak: 'keep-all',
  },
  // 모든 환경에서 scroll snap 활성화
  scrollSnapType: 'y mandatory',
  overflowY: 'scroll',
  height: '100vh',
  // 세로 태블릿/폴드폰에서도 height 100vh 유지 (스크롤 스냅을 위해)
  '@media (min-width: 768px) and (orientation: portrait)': {
    height: '100vh',
    overflowY: 'scroll',
  },
  // 갤럭시 폴드 7 메인 디스플레이 최적화 (8인치, 1968x2184 세로모드)
  '@media (min-width: 1900px) and (orientation: portrait)': {
    height: '100vh',
    fontSize: '1.1rem',
    overflowY: 'scroll',
  },
  // 갤럭시 폴드 7 커버 디스플레이 최적화 (6.5인치, 2520x1080)
  '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
    height: '100vh',
    overflowY: 'scroll',
    padding: '2vh 1rem',
  },
});

export const Section = styled('section')(({ theme }) => ({
  padding: theme.spacing(12, 0),
  borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
  position: 'relative',
  minHeight: '100dvh', // 동적 뷰포트 높이 사용
  scrollSnapAlign: 'start',
  display: 'flex',
  alignItems: 'center',
  [theme.breakpoints.down('sm')]: {
    padding: theme.spacing(8, 0),
    minHeight: '100dvh' // 모바일에서도 동적 뷰포트 높이 적용
  },
  // dvh 미지원 브라우저를 위한 fallback
  '@supports not (height: 100dvh)': {
    minHeight: '100vh'
  },
}));

export const HeroRoot = styled('header')(({ theme }) => ({
  position: 'relative',
  height: '100vh',
  display: 'grid',
  placeItems: 'center',
  overflow: 'hidden',
  borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
  scrollSnapAlign: 'start',
  // 세로 태블릿/폴드폰에서는 높이와 패딩 조정
  '@media (min-width: 768px) and (orientation: portrait)': {
    height: 'auto',
    minHeight: '100vh',
    paddingTop: '10vh',
    paddingBottom: '10vh',
  },
  // 갤럭시 폴드 7 메인 디스플레이 히어로 섹션 최적화
  '@media (min-width: 1950px) and (min-height: 2150px)': {
    height: '100vh',
    paddingTop: '8vh',
    paddingBottom: '8vh',
  },
  // 갤럭시 폴드 7 커버 디스플레이 히어로 섹션 최적화
  '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
    height: '100vh',
    paddingTop: '5vh',
    paddingBottom: '5vh',
  },
  // 가로 태블릿
  [theme.breakpoints.between('md', 'lg')]: {
    height: '100vh',
    minHeight: '800px',
  },
  [theme.breakpoints.down('md')]: {
    height: '100vh',
    minHeight: '700px',
  },
}));

export const HeroBlur = styled(Box)({
  position: 'absolute',
  inset: 0,
  backdropFilter: 'blur(3px)',
  pointerEvents: 'none',
  zIndex: -0.3,
});

export const HeroOverlay = styled(Box)({
  position: 'absolute',
  inset: 0,
  background:
    'linear-gradient(180deg, rgba(5, 11, 17, 0.35) 0%, rgba(5, 11, 17, 0.55) 45%, rgba(5, 11, 17, 0.80) 100%)',
  pointerEvents: 'none',
  zIndex: -1,
});

export const HeroContent = styled(Box)(({ theme }) => ({
  position: 'relative',
  zIndex: 10,
  textAlign: 'center',
  width: '100%',
  maxWidth: 960,
  margin: '0 auto',
  padding: theme.spacing(0, 3),
  // 모든 세로 태블릿/폴드폰
  '@media (min-width: 768px) and (orientation: portrait)': {
    maxWidth: '80%',
    padding: theme.spacing(0, 4),
  },
  // 갤럭시 폴드 7 메인 디스플레이 컨테이너 최적화
  '@media (min-width: 1950px) and (min-height: 2150px)': {
    maxWidth: '85%',
    padding: theme.spacing(0, 6),
  },
  // 갤럭시 폴드 7 커버 디스플레이 컨테이너 최적화
  '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
    maxWidth: '90%',
    padding: theme.spacing(0, 2),
  },
  // 가로 태블릿
  [theme.breakpoints.between('md', 'lg')]: {
    maxWidth: 800,
    padding: theme.spacing(0, 2),
  },
  [theme.breakpoints.down('md')]: {
    maxWidth: '100%',
    padding: theme.spacing(0, 2),
  },
}));

export const CTAButton = styled(Button)(({ theme }) => ({
  backgroundColor: '#00d4ff',
  color: '#041120',
  fontWeight: 700,
  padding: theme.spacing(1.25, 3),
  borderRadius: 12,
  letterSpacing: '0.02em',
  transition: 'transform 200ms ease, background-color 200ms ease',
  '&:hover': {
    backgroundColor: '#00bde6',
    transform: 'translateY(-1px)',
  },
}));

export const OutlineButton = styled(Button)(({ theme }) => ({
  borderColor: '#00d4ff',
  color: '#00d4ff',
  fontWeight: 700,
  padding: theme.spacing(1.25, 3),
  borderRadius: 12,
  letterSpacing: '0.02em',
  '&:hover': {
    backgroundColor: 'rgba(0, 212, 255, 0.10)',
    borderColor: '#00d4ff',
  },
}));

export const CardSoft = styled(Card)({
  backgroundColor: 'rgba(255,255,255,0.04)',
  borderRadius: 16,
  border: '1px solid rgba(255,255,255,0.06)',
  backdropFilter: 'blur(6px)',
  transition: 'all 0.3s ease',
  cursor: 'pointer',
  '&:hover': {
    transform: 'scale(0.98)',
    boxShadow: '0 0 20px rgba(0, 212, 255, 0.3), 0 0 40px rgba(0, 212, 255, 0.1)',
    borderColor: 'rgba(0, 212, 255, 0.2)',
  },
});

export const CardEmphasis = styled(Card)({
  backgroundColor: 'rgba(0, 212, 255, 0.10)',
  borderRadius: 16,
  border: '1px solid rgba(0, 212, 255, 0.25)',
  backdropFilter: 'blur(6px)',
  transition: 'all 0.3s ease',
  cursor: 'pointer',
  '&:hover': {
    transform: 'scale(0.98)',
    boxShadow: '0 0 20px rgba(79, 195, 247, 0.4), 0 0 40px rgba(79, 195, 247, 0.2)',
    borderColor: 'rgba(79, 195, 247, 0.4)',
  },
});

export const StatBadge = styled(Box)(({ theme }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  padding: theme.spacing(0.75, 1.25),
  borderRadius: 999,
  fontSize: 13,
  lineHeight: 1.2,
  color: '#00d4ff',
  backgroundColor: 'rgba(0, 212, 255, 0.10)',
  border: '1px solid rgba(0, 212, 255, 0.22)',
}));

export const DemoWatermark = styled(Box)({
  position: 'absolute',
  right: 12,
  bottom: 12,
  padding: '4px 8px',
  fontSize: 12,
  borderRadius: 8,
  color: 'rgba(255,255,255,0.85)',
  background: 'rgba(0,0,0,0.35)',
  border: '1px solid rgba(255,255,255,0.25)',
  pointerEvents: 'none',
});

export const ContentContainer = styled(Container)({
  position: 'relative',
  zIndex: 10,
});
