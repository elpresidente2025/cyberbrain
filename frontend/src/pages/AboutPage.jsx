// frontend/src/pages/AboutPage.jsx
// Secret LP build: no SEO exposure, demo-safe stats toggling, fast visuals.
// - Robots noindex via react-helmet-async
// - Demo numbers/claims only when ?demo=1 (or showDemo prop)
// - One eager hero image; all others lazy
// - Subtle in-view fades; reduced-motion respected

import React, { useLayoutEffect, useRef, useState, useEffect, useCallback } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);
import {
  Box,
  Container,
  Typography,
  Button,
  Grid,
  Card,
  CardContent,
  Stack,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useMediaQuery,
  Fade,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import SourceIcon from '@mui/icons-material/Source';
import StyleIcon from '@mui/icons-material/Style';
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted';
import { styled } from '@mui/material/styles';
import { Helmet } from 'react-helmet-async'; // ensure provider is set at app root
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

// -----------------------------
// Data (constants)
// -----------------------------

const CORE_FEATURES = [
  {
    title: 'AI 콘텐츠 자동 생성',
    desc: '정치인 맞춤형 블로그 포스트를 AI가 자동으로 생성할 수 있습니다. 정책, 활동, 소식을 전문적으로 작성해드립니다.',
  },
  {
    title: '네이버·구글 1페이지 진출 가능성 극대화',
    desc: '유권자가 내 이름을 검색했을 때 1페이지 노출 가능성을 높이는 콘텐츠를 작성합니다. 찾기 쉬워야 기억될 가능성이 높습니다.',
  },
  {
    title: '질문 답변 상위 노출 최적화',
    desc: '"○○구 의원 공약 뭐야?" 물으면 검색 상위 답변에 내 이름과 공약이 언급될 가능성을 높이도록 최적화합니다.',
  },
  {
    title: '시간 절약 자동화',
    desc: '매일 1-2시간씩 소요되던 콘텐츠 작성을 5분으로 단축할 수 있습니다. 본업인 정책과 현장활동에 집중할 수 있습니다.',
  },
];

const SAFETY_FEATURES = [
  {
    title: '법적 안전성 및 선거법 준수',
    desc: '정치적 리스크 키워드를 자동 회피하고 의견과 사실을 구분하여 법적 리스크를 최소화합니다. 선거법 180일 규정 등 정치 관련 법규를 자동으로 준수합니다.',
  },
  {
    title: '상황별 작법 및 지능적 톤앤매너',
    desc: '일상 소통, 정책 제안, 활동 보고, 시사 논평, 지역 현안 등 정치인의 다양한 상황에 맞춰 각각 다른 작법을 적용합니다. AI가 주제를 분석하여 최적의 톤앤매너와 문체를 자동 선택합니다.',
  },
];


// 샘플 원고 데이터
const SAMPLE_SPEECH = {
  title: '원고 샘플(요약)',
  source: '언론 보도 기반 자동 생성',
  disclaimer: '데모 샘플입니다. 실제와 다를 수 있습니다.',
  body: `○○구 어린이 통학로 안전 점검 결과를 공개합니다. 지난달 접수된 민원 12건을 바탕으로 현장 점검을 완료했고, 개선이 필요한 3곳에 예산 반영을 요청했습니다.

아이들이 안전하게 등하교할 수 있는 환경 조성을 위해 지속적으로 노력하겠습니다. 주민 여러분께서 제기해주신 의견을 바탕으로 실질적인 개선이 이루어질 수 있도록 관련 부서와 협력하고 있습니다.

앞으로도 지역 안전과 관련된 민원이나 제안사항이 있으시면 언제든지 연락 주시기 바랍니다. 함께 만들어가는 안전한 우리 동네가 되도록 최선을 다하겠습니다.`
};

// 샘플 원고 모달 컴포넌트
function SampleSpeechModal({ open, onClose }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      aria-labelledby="sample-speech-title"
      aria-describedby="sample-speech-desc"
      PaperProps={{
        sx: {
          backgroundColor: 'rgba(0,0,0,0.9)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: 2
        }
      }}
    >
      <DialogTitle id="sample-speech-title" sx={{ fontWeight: 800, color: '#fff' }}>
        {SAMPLE_SPEECH.title}
      </DialogTitle>
      <DialogContent dividers id="sample-speech-desc" sx={{ position: 'relative', color: '#fff' }}>
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Chip size="small" label="데모 샘플" sx={{ backgroundColor: 'rgba(255,255,255,0.1)', color: '#fff' }} />
          <Chip size="small" label={SAMPLE_SPEECH.source} sx={{ backgroundColor: 'rgba(0,212,255,0.2)', color: '#00d4ff' }} />
          <Chip size="small" label="전문 비공개" sx={{ backgroundColor: 'rgba(255,255,255,0.1)', color: '#fff' }} />
        </Stack>
        <Typography variant="caption" sx={{ opacity: 0.7, display: 'block', mb: 2, color: '#fff' }}>
          {SAMPLE_SPEECH.disclaimer}
        </Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.7, color: '#fff' }}>
          {SAMPLE_SPEECH.body}
        </Typography>
        <Box sx={{
          position: 'absolute',
          right: 12,
          bottom: 12,
          px: 1,
          py: 0.25,
          border: '1px solid rgba(255,255,255,0.25)',
          borderRadius: 1,
          fontSize: 12,
          opacity: 0.8,
          color: '#fff'
        }}>DEMO</Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} variant="contained" sx={{ backgroundColor: '#00d4ff', color: '#041120' }}>
          닫기
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// 글로벌 권위 사례 데이터 (이재명 → 트럼프 → 정청래 순)
const GLOBAL_AUTHORITY_CASES = [
  {
    id: 1,
    title: '이재명',
    subtitle: 'K-정치 디지털 모델',
    description: 'SNS로 팩트체크와 정책 해설을 직접 전달하는 디지털 정치의 선도 모델.',
    image: '/sns/lee-jae-myung.png',
    impact: '디지털 소통의 새로운 기준',
    color: '#4267B2'
  },
  {
    id: 2,
    title: '트럼프',
    subtitle: 'X(트위터) 정치 혁명',
    description: '전통 미디어를 뛰어넘어 트위터 직접 소통으로 대통령에 당선된 최초 사례.',
    image: '/sns/trump.png',
    impact: 'SNS로 정치적 성과를 발휘한 사례',
    color: '#1DA1F2'
  },
];


const FAQS = [
  {
    q: '생성되는 콘텐츠의 정치적 안전성은 어떻게 유지되나요?',
    a: '더불어민주당의 가치와 정책 방향에 부합하는 콘텐츠만 생성하도록 AI가 학습되어 있습니다. 또한 모든 콘텐츠는 정치적 리스크 검토 시스템을 거쳐 안전성을 유지할 수 있습니다.',
  },
  {
    q: '개인정보 수집과 데이터 보안은 어떻게 처리되나요?',
    a: '최소한의 필수 정보만 수집하며, 모든 데이터는 최고 수준 보안 암호화로 저장됩니다. 개인정보보호법과 정치자금법을 완전히 준수하며, 제3자와 데이터를 공유하지 않습니다. 정기적인 보안 점검을 통해 안전성을 유지합니다.',
  },
  {
    q: '당적 인증은 어떻게 이루어지나요?',
    a: '당적 증명서와 당비 납부 내역 2가지 문서로 확인합니다. 모두 휴대폰에서 간편하게 확인 가능하며, 스크린샷을 찍어 업로드하면 자동으로 문서 내용을 읽어 검증합니다. 인증은 분기별(연 4회) 진행되며, 인증이 확인되지 않으면 서비스 이용이 제한됩니다.',
  },
  {
    q: '선거법 180일 규정은 어떻게 준수하나요?',
    a: '선거일 180일 전부터는 선거운동으로 간주될 수 있는 콘텐츠 생성을 자동으로 제한합니다. 해당 기간에는 정책 홍보와 의정활동 보고에 집중한 콘텐츠만 생성 가능하며, 법적 검토를 강화합니다.',
  },
  {
    q: '콘텐츠 스타일을 개인 취향에 맞게 조정할 수 있나요?',
    a: '네, 개인의 글쓰기 스타일, 선호하는 주제, 톤앤매너 등을 학습하여 개별 맞춤형 콘텐츠를 생성합니다. 지속적인 피드백을 통해 더욱 정교해집니다.',
  },
  {
    q: '선거구 독점 정책은 어떻게 운영되나요?',
    a: '동일 선거구(국회의원 선거구 기준) 내에는 1인만 서비스를 이용할 수 있습니다. 선착순으로 선거구를 확보하며, 계약 종료 시에만 해당 선거구가 다시 개방됩니다. 이를 통해 지역 내 독점적 디지털 우위를 확보할 수 있습니다.',
  },
];

// GlobalAuthorityCaseContainer 컴포넌트 - 2행 이미지 레이아웃
const GlobalAuthorityCaseContainer = ({ scrollerEl }) => {
  const containerRef = useRef(null);

  return (
    <Box
      ref={containerRef}
      sx={{
        height: '100%',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
        p: 1
      }}
    >
      {/* 이재명 - 상단 */}
      <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Box component="img"
             src={GLOBAL_AUTHORITY_CASES[0].image}
             alt={GLOBAL_AUTHORITY_CASES[0].title}
             sx={{
               maxWidth: '70%',
               maxHeight: '70%',
               width: 'auto',
               height: 'auto',
               borderRadius: 2,
               border: '1px solid rgba(255,255,255,0.1)',
               objectFit: 'contain'
             }} />
      </Box>

      {/* 트럼프 - 하단 */}
      <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Box component="img"
             src={GLOBAL_AUTHORITY_CASES[1].image}
             alt={GLOBAL_AUTHORITY_CASES[1].title}
             sx={{
               maxWidth: '70%',
               maxHeight: '70%',
               width: 'auto',
               height: 'auto',
               borderRadius: 2,
               border: '1px solid rgba(255,255,255,0.1)',
               objectFit: 'contain'
             }} />
      </Box>
    </Box>
  );
};

// 글로벌 사례 섹션
const GlobalCasesSection = () => {

  return (
    <Section sx={{
      backgroundColor: 'rgba(21, 36, 132, 0.08)',
      height: '100vh',
      borderTop: '1px solid rgba(0, 212, 255, 0.2)',
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '100px',
        background: 'linear-gradient(180deg, rgba(21, 36, 132, 0.1) 0%, transparent 100%)',
        pointerEvents: 'none'
      }
    }}>
      <ContentContainer maxWidth="lg">
        <Grid container spacing={4} sx={{
          flexDirection: { xs: 'column', md: 'row' },
          height: '100%'
        }}>
          <Grid item xs={12} md={6} sx={{
            order: { xs: 1, md: 1 },
            height: { xs: '50vh', md: 'calc(100vh - 32px)' },
            position: 'relative',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: 2,
            overflow: 'hidden'
          }}>
            <Box sx={{ position: 'relative', overflow: 'hidden', height: '100%' }}>
              <GlobalAuthorityCaseContainer scrollerEl={pageRef.current} />
            </Box>
          </Grid>

          <Grid item xs={12} md={6} sx={{
            order: { xs: 2, md: 2 },
            height: { xs: '50vh', md: 'calc(100vh - 32px)' },
            display: 'flex',
            alignItems: 'center'
          }}>
            <Box ref={textRef} sx={{
              position: 'relative',
              width: '100%',
              px: { xs: 2, md: 0 },
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              textAlign: 'center',
              pt: { xs: 0, md: 4 }
            }}>
              <Typography variant="h3" sx={{
                fontWeight: 900,
                mb: 4,
                color: '#00d4ff',
                fontSize: { xs: '1.8rem', md: '2.5rem' }
              }}>
                이미 검증된 성공 방식
              </Typography>
              <Typography variant="body1" sx={{
                fontSize: { xs: '1rem', md: '1.125rem' },
                lineHeight: 1.8,
                mb: 3,
                color: 'rgba(255,255,255,0.9)'
              }}>
                전 세계 정치인들이 이미 증명한 디지털 소통의 힘. 이제 대한민국 정치에서도 같은 성과를 거둘 때입니다.
              </Typography>
              <Typography variant="body2" sx={{
                fontSize: { xs: '0.9rem', md: '1rem' },
                color: 'rgba(255,255,255,0.7)',
                lineHeight: 1.6
              }}>
                AI 원고 생성 시스템으로 일관된 메시지 전달과 브랜딩을 구축하여, 유권자들에게 더 강력한 인상을 남길 수 있습니다.
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </ContentContainer>
    </Section>
  );
};

// 우측 텍스트 컨테이너 - 스크롤에 따라 움직임
const RightTextContainer = ({ pageRef }) => {
  const textRef = useRef(null);

  useLayoutEffect(() => {
    const text = textRef.current;
    if (!text) return;

    const isMobile = window.innerWidth <= 768;
    if (isMobile) return; // 모바일에서는 애니메이션 없음

    // 텍스트를 섹션 내에서만 움직이도록 제한
    gsap.fromTo(text,
      { y: 0 }, // 시작: 원래 위치
      {
        y: '20vh', // 끝: 약간 아래로만
        scrollTrigger: {
          trigger: text.parentElement.parentElement, // Grid container
          scroller: pageRef.current || undefined,
          start: 'top bottom', // 섹션이 화면에 들어올 때 시작
          end: 'bottom top',   // 섹션이 화면에서 나갈 때 끝
          scrub: 1,
          invalidateOnRefresh: true
        }
      }
    );

    return () => {
      ScrollTrigger.getAll().forEach(st => {
        if (st.trigger === text.parentElement.parentElement) st.kill();
      });
    };
  }, [pageRef]);

  return (
    <Box sx={{
      px: { xs: 2, md: 0 },
      py: 4,
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center'
    }}>
      <Typography variant="h3" sx={{
        fontWeight: 900,
        mb: 4,
        color: '#00d4ff',
        fontSize: { xs: '1.8rem', md: '2.5rem' }
      }}>
        이미 검증된 성공 방식
      </Typography>
      <Typography variant="body1" sx={{
        fontSize: { xs: '1rem', md: '1.125rem' },
        lineHeight: 1.8,
        mb: 3,
        color: 'rgba(255,255,255,0.9)'
      }}>
        전 세계 정치인들이 이미 증명한 디지털 소통의 힘. 이제 대한민국 정치에서도 같은 성과를 거둘 때입니다.
      </Typography>
      <Typography variant="body2" sx={{
        fontSize: { xs: '0.9rem', md: '1rem' },
        color: 'rgba(255,255,255,0.7)',
        lineHeight: 1.6
      }}>
        AI 원고 생성 시스템으로 일관된 메시지 전달과 브랜딩을 구축하여, 유권자들에게 더 강력한 인상을 남길 수 있습니다.
      </Typography>
    </Box>
  );
};

// -----------------------------
// Styled
// -----------------------------

const Page = styled('main')({
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
  // 세로 태블릿/폴드폰에서는 높이 조정하되 scroll snap 유지
  '@media (min-width: 768px) and (orientation: portrait)': {
    height: 'auto',
    minHeight: '100vh',
  },
});

const Section = styled('section')(({ theme }) => ({
  padding: theme.spacing(12, 0),
  borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
  position: 'relative',
  minHeight: '100vh',
  scrollSnapAlign: 'start',
  display: 'flex',
  alignItems: 'center',
  [theme.breakpoints.down('sm')]: { padding: theme.spacing(8, 0) },
}));

const HeroRoot = styled('header')(({ theme }) => ({
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

const HeroBlur = styled(Box)({
  position: 'absolute',
  inset: 0,
  backdropFilter: 'blur(3px)',
  pointerEvents: 'none',
  zIndex: -0.3,
});

const HeroOverlay = styled(Box)({
  position: 'absolute',
  inset: 0,
  background:
    'linear-gradient(180deg, rgba(5, 11, 17, 0.35) 0%, rgba(5, 11, 17, 0.55) 45%, rgba(5, 11, 17, 0.80) 100%)',
  pointerEvents: 'none',
  zIndex: -1,
});

const HeroContent = styled(Box)(({ theme }) => ({
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

const CTAButton = styled(Button)(({ theme }) => ({
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

const OutlineButton = styled(Button)(({ theme }) => ({
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

const CardSoft = styled(Card)({
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

const CardEmphasis = styled(Card)({
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

const StatBadge = styled(Box)(({ theme }) => ({
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

const DemoWatermark = styled(Box)({
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

const ContentContainer = styled(Container)({
  position: 'relative',
  zIndex: 10,
});

// -----------------------------
// In-view fade (lightweight)
// -----------------------------

function InViewFade({ children, threshold = 0.16, timeout = 800, ...props }) {
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const ref = React.useRef(null);
  const [inView, setInView] = React.useState(false);

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          obs.disconnect();
        }
      },
      { threshold }
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [threshold]);

  return (
    <Box ref={ref} {...props}>
      <Fade in={inView} timeout={prefersReducedMotion ? 0 : timeout}>
        <Box>{children}</Box>
      </Fade>
    </Box>
  );
}

// -----------------------------
// Page
// -----------------------------

const AboutPage = ({ showDemo: showDemoProp }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const [openSample, setOpenSample] = React.useState(false);
  const pageRef = useRef(null);

  useLayoutEffect(() => {
    if (!pageRef.current) return;
    ScrollTrigger.defaults({ scroller: pageRef.current });
    const onLoad = () => ScrollTrigger.refresh();
    window.addEventListener('load', onLoad);
    const t = setTimeout(() => ScrollTrigger.refresh(), 300);
    return () => { window.removeEventListener('load', onLoad); clearTimeout(t); };
  }, []);

  // Demo toggle: prop OR ?demo=1 OR dev env
  const [demoMode, setDemoMode] = React.useState(() => {
    if (typeof showDemoProp === 'boolean') return showDemoProp;
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '');
    return params.get('demo') === '1';
  });

  // Show demo switch only in dev or with ?demo=1
  const showDemoSwitch = process.env.NODE_ENV !== 'production' ||
    new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '').get('demo') === '1';

  const handlePrimaryCTA = () => {
    if (user) navigate('/dashboard');
    else navigate('/register');
  };


  return (
    <Page ref={pageRef}>
      {/* Secret: noindex */}
      <Helmet>
        <meta name="robots" content="noindex,nofollow" />
        <meta name="googlebot" content="noindex,nofollow" />
      </Helmet>

      {/* Demo switch (only in dev or with ?demo=1) */}
      {showDemoSwitch && (
        <Box sx={{ position: 'fixed', right: 16, top: 16, zIndex: 10 }}>
          <FormControlLabel
            control={
              <Switch
                checked={demoMode}
                onChange={(e) => setDemoMode(e.target.checked)}
                color="info"
                size="small"
              />
            }
            label="데모 데이터"
            sx={{
              color: 'rgba(255,255,255,0.75)',
              bgcolor: 'rgba(255,255,255,0.06)',
              px: 1.25,
              py: 0.5,
              borderRadius: 2,
              border: '1px solid rgba(255,255,255,0.12)',
            }}
          />
        </Box>
      )}

      {/* Hero */}
      <HeroRoot>
        <Box sx={{ position: 'absolute', inset: 0, zIndex: -2 }}>
          <picture>
            <source
              media="(min-width:1200px)"
              srcSet="/images/hero-search-xl.webp"
              type="image/webp"
            />
            <source
              media="(min-width:600px)"
              srcSet="/images/hero-search-lg.webp"
              type="image/webp"
            />
            <img
              src="/images/hero-search.jpg"
              alt="검색 노출 예시 화면"
              loading="eager"
              decoding="async"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              fetchpriority="high"
            />
          </picture>
          {demoMode && <DemoWatermark>DEMO</DemoWatermark>}
        </Box>
        <HeroBlur />
        <HeroOverlay />
        <HeroContent>
          <InViewFade threshold={0.01} timeout={650}>
            <Typography
              component="h1"
              sx={{
                fontWeight: 800,
                letterSpacing: '0',
                lineHeight: 1.1,
                fontSize: {
                  xs: 'clamp(28px, 7vw, 44px)',
                  md: 'clamp(40px, 5.5vw, 56px)',
                  lg: 'clamp(48px, 6vw, 64px)'
                },
                mb: { xs: 1.5, md: 2, lg: 2 }, // 태블릿에서 마진 조정
                // 모든 세로 태블릿/폴드폰
                '@media (min-width: 768px) and (orientation: portrait)': {
                  fontSize: 'clamp(40px, 5vw, 60px)',
                  whiteSpace: 'normal',
                },
                whiteSpace: { xs: 'normal', md: 'normal', lg: 'nowrap' }, // 태블릿에서도 줄바꿈 허용
                textAlign: 'center',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                width: '100%',
                position: 'relative',
                left: '50%',
                transform: 'translateX(-50%)'
              }}
            >
              <Box
                component="span"
                sx={{
                  display: 'inline',
                  wordBreak: 'keep-all',
                  // 실제 텍스트 길이와 폰트 크기를 고려한 정밀한 브레이크포인트
                  whiteSpace: 'nowrap',
                  // 4K 절반 브라우저: ~1920px
                  '@media (max-width: 1500px)': {
                    whiteSpace: 'normal'
                  },
                  // QHD 절반 브라우저: ~1280px
                  '@media (max-width: 1300px)': {
                    whiteSpace: 'normal'
                  },
                  // FHD 절반 브라우저: ~960px
                  '@media (max-width: 1200px)': {
                    whiteSpace: 'normal'
                  },
                  // 태블릿 가로 모드
                  '@media (max-width: 1024px)': {
                    whiteSpace: 'normal'
                  },
                  // 태블릿 세로 모드
                  '@media (max-width: 768px)': {
                    whiteSpace: 'normal'
                  },
                  // 모바일 가로 모드
                  '@media (max-width: 640px)': {
                    whiteSpace: 'normal'
                  }
                }}
              >
                "의원님 덕분에 살기 좋은 동네가 됐어요!"
              </Box>
            </Typography>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 600,
                letterSpacing: '0.01em',
                mb: { xs: 3, md: 4, lg: 4 }, // 태블릿에서 마진 조정
                fontSize: { xs: '1.1rem', md: '1.35rem', lg: '1.5rem' }, // 태블릿 사이즈 추가
                opacity: 0.9
              }}
            >
              검색되지 않으면 이런 칭찬도 못 듣습니다.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
              <CTAButton aria-label="영향력 확인" onClick={handlePrimaryCTA}>
                영향력 확인
              </CTAButton>
            </Stack>

          </InViewFade>
        </HeroContent>
      </HeroRoot>

      {/* 섹션 구분선 */}
      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* 글로벌 사례 */}
      <Box sx={{
        backgroundColor: 'rgba(21, 36, 132, 0.08)',
        borderTop: '1px solid rgba(0, 212, 255, 0.2)',
        borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
        height: '100vh',
        minHeight: { xs: '700px', md: '800px', lg: '100vh' }, // 태블릿 사이즈에서 최소 높이 보장
        display: 'flex',
        alignItems: 'center',
        scrollSnapAlign: 'start',
        // 세로 태블릿/폴드폰에서는 높이를 100vh로 고정
        '@media (min-width: 768px) and (orientation: portrait)': {
          height: '100vh',
          minHeight: '100vh',
          paddingTop: '2vh',
          paddingBottom: '2vh',
        }
      }}>
        <ContentContainer maxWidth="lg" sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center' }}>
          <Grid container spacing={4} sx={{
            width: '100%',
            // 세로 태블릿에서는 세로 배치
            '@media (min-width: 768px) and (orientation: portrait)': {
              flexDirection: 'column',
            }
          }}>
            {/* 좌측: 이미지 */}
            <Grid item xs={12} md={6} sx={{
              // 세로 태블릿에서는 전체 너비
              '@media (min-width: 768px) and (orientation: portrait)': {
                width: '100%',
                maxWidth: '100%',
                flexBasis: 'auto',
              }
            }}>
              <Box sx={{
                height: { xs: '50vh', md: '65vh', lg: '60vh' },
                p: { xs: 1, md: 2 },
                // 세로 태블릿에서 높이 조정 (25% 정도)
                '@media (min-width: 768px) and (orientation: portrait)': {
                  height: '25vh',
                  p: 1,
                }
              }}>
                <Grid container spacing={2} sx={{
                  height: '100%',
                  // 세로 태블릿에서만 2열 배치
                  '@media (min-width: 768px) and (orientation: portrait)': {
                    spacing: 1,
                  }
                }}>
                  {/* 이재명 이미지 */}
                  <Grid item xs={12} sx={{
                    // 세로 태블릿에서는 6 (절반)
                    '@media (min-width: 768px) and (orientation: portrait)': {
                      flexBasis: '50%',
                      maxWidth: '50%',
                    }
                  }}>
                    <Box sx={{
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: 2,
                      p: 2,
                      '@media (min-width: 768px) and (orientation: portrait)': {
                        p: 1,
                      }
                    }}>
                      <img
                        src="/sns/lee-jae-myung.png"
                        alt="이재명"
                        style={{
                          maxWidth: '80%',
                          maxHeight: '80%',
                          borderRadius: 8,
                          objectFit: 'contain'
                        }}
                      />
                    </Box>
                  </Grid>

                  {/* 트럼프 이미지 */}
                  <Grid item xs={12} sx={{
                    // 세로 태블릿에서는 6 (절반)
                    '@media (min-width: 768px) and (orientation: portrait)': {
                      flexBasis: '50%',
                      maxWidth: '50%',
                    }
                  }}>
                    <Box sx={{
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: 2,
                      p: 2,
                      '@media (min-width: 768px) and (orientation: portrait)': {
                        p: 1,
                      }
                    }}>
                      <img
                        src="/sns/trump.png"
                        alt="트럼프"
                        style={{
                          maxWidth: '80%',
                          maxHeight: '80%',
                          borderRadius: 8,
                          objectFit: 'contain'
                        }}
                      />
                    </Box>
                  </Grid>
                </Grid>
              </Box>
            </Grid>

            {/* 우측: 텍스트 */}
            <Grid item xs={12} md={6} sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              // 세로 태블릿에서는 전체 너비
              '@media (min-width: 768px) and (orientation: portrait)': {
                width: '100%',
                maxWidth: '100%',
                flexBasis: 'auto',
                mt: 3, // 이미지와 텍스트 사이 간격 조정
              }
            }}>
              <Box sx={{
                px: { xs: 1, md: 2, lg: 2 },
                py: { xs: 3, md: 4, lg: 4 }, // 태블릿에서 패딩 조정
                textAlign: 'center',
                maxWidth: { xs: '400px', md: '500px', lg: '600px' }, // 태블릿에서 최대 너비 조정
                // 모든 세로 태블릿/폴드폰
                '@media (min-width: 768px) and (orientation: portrait)': {
                  px: 3,
                  py: 2, // 패딩 줄여서 공간 절약
                  maxWidth: '80%',
                }
              }}>
                <Typography variant="h3" sx={{
                  fontWeight: 900,
                  mb: { xs: 3, md: 4, lg: 4 }, // 태블릿에서 마진 조정
                  color: '#00d4ff',
                  // 세로 태블릿에서 마진 줄이기
                  '@media (min-width: 768px) and (orientation: portrait)': {
                    mb: 2,
                  },
                  textShadow: '0 0 30px rgba(0,212,255,0.5)',
                  whiteSpace: { xs: 'normal', md: 'nowrap', lg: 'nowrap' }, // 태블릿에서 줄바꿈 허용
                  fontSize: { xs: '1.6rem', md: '2.0rem', lg: '2.5rem' }, // 태블릿 사이즈 추가
                  // 모든 세로 태블릿/폴드폰
                  '@media (min-width: 768px) and (orientation: portrait)': {
                    fontSize: 'clamp(2rem, 4vw, 2.8rem)',
                    whiteSpace: 'normal',
                  }
                }}>
                  이미 검증된 성공 방식
                </Typography>
                <Typography variant="h6" sx={{
                  fontWeight: 500,
                  mb: { xs: 2, md: 3, lg: 3 }, // 태블릿에서 마진 조정
                  lineHeight: 1.8,
                  color: 'rgba(255,255,255,0.9)',
                  fontSize: { xs: '1.0rem', md: '1.15rem', lg: '1.25rem' }, // 태블릿 사이즈 추가
                  // 세로 태블릿에서 마진 줄이기
                  '@media (min-width: 768px) and (orientation: portrait)': {
                    mb: 1.5,
                  }
                }}>
                  전 세계 정치인들이 이미 증명한 디지털 소통의 힘. 이제 대한민국 정치에서도 같은 성과를 거둘 때입니다.
                </Typography>
                <Typography variant="body1" sx={{
                  lineHeight: 1.8,
                  color: 'rgba(255,255,255,0.7)',
                  fontSize: { xs: '0.9rem', md: '1.0rem', lg: '1rem' } // 태블릿 사이즈 추가
                }}>
                  온라인 검색에서 먼저 발견되는 콘텐츠와 논리적 설득부터 감정적 공감까지, 상황별 맞춤 원고로 유권자에게 더 깊이 다가갈 수 있습니다.
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </ContentContainer>
      </Box>

      {/* Core Features */}
      <Section id="how" aria-labelledby="features-heading">
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="features-heading" variant="h4" sx={{ fontWeight: 800, mb: 6 }}>
              핵심 기능
            </Typography>
          </InViewFade>
          <Grid container spacing={3}>
            {CORE_FEATURES.map((f, idx) => (
              <Grid item xs={12} md={6} key={f.title}>
                <InViewFade timeout={600 + idx * 80}>
                  <CardSoft>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Typography variant="h6" sx={{ fontWeight: 700 }}>
                        {f.title}
                      </Typography>
                      <Typography sx={{ mt: 1.25 }}>
                        {f.desc}
                      </Typography>
                    </CardContent>
                  </CardSoft>
                </InViewFade>
              </Grid>
            ))}
          </Grid>
        </ContentContainer>
      </Section>

      {/* Safety & Quality Management */}
      <Section sx={{ backgroundColor: 'rgba(255,255,255,0.02)' }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{ fontWeight: 800, mb: 2, textAlign: 'center' }}>
              안전성과 품질 관리
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 6, textAlign: 'center' }}>
              정치인을 위한 안전하고 신뢰할 수 있는 콘텐츠 생성 시스템입니다.
            </Typography>
          </InViewFade>

          <Grid container spacing={3} sx={{ mb: 6 }}>
            {SAFETY_FEATURES.map((f, idx) => (
              <Grid item xs={12} md={6} key={f.title}>
                <InViewFade timeout={600 + idx * 80}>
                  <CardSoft>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Typography variant="h6" sx={{ fontWeight: 700 }}>
                        {f.title}
                      </Typography>
                      <Typography sx={{ mt: 1.25 }}>
                        {f.desc}
                      </Typography>
                    </CardContent>
                  </CardSoft>
                </InViewFade>
              </Grid>
            ))}
          </Grid>

          <Grid container spacing={3} justifyContent="center">
            {[
              {
                title: '1회 = 1원고',
                description: '한 번의 요청으로 하나의 완성된 원고를 생성합니다.',
                color: '#003a87'
              },
              {
                title: '최대 3회 재생성',
                description: '동일한 주제에 대해 최대 3번까지 다른 버전을 생성할 수 있습니다.',
                color: '#55207d'
              },
              {
                title: '사실 검증 시스템',
                description: 'AI가 잘못된 정보를 만들어내지 않도록 원칙적 제한을 적용합니다.',
                color: '#006261'
              }
            ].map((rule, index) => (
              <Grid item xs={12} md={4} key={index}>
                <InViewFade timeout={600 + index * 100}>
                  <Card
                    sx={{
                      bgcolor: 'rgba(255,255,255,0.05)',
                      border: `2px solid ${rule.color}40`,
                      borderRadius: 3,
                      height: '100%',
                      transition: 'all 0.3s ease',
                      '&:hover': {
                        borderColor: `${rule.color}80`,
                        transform: 'translateY(-4px)',
                        boxShadow: `0 8px 32px ${rule.color}20`
                      }
                    }}
                  >
                    <CardContent sx={{ p: 4, textAlign: 'center' }}>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          mb: 2,
                          color: rule.color
                        }}
                      >
                        {rule.title}
                      </Typography>
                      <Typography sx={{ lineHeight: 1.6 }}>
                        {rule.description}
                      </Typography>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Grid>
            ))}
          </Grid>
        </ContentContainer>
      </Section>

      {/* Quality (Infographic) */}
      <Section aria-labelledby="quality-heading">
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="quality-heading" variant="h4" sx={{ fontWeight: 800, mb: 2 }}>
              원고 품질과 검수 프로세스
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 6 }}>
              모든 글은 아래 기준과 절차를 통과합니다. 최종 검토는 사용자가 수행합니다.
            </Typography>
          </InViewFade>

          {/* 품질 기준 아이콘 그리드 */}
          <Grid container spacing={3}>
            {[
              { icon: <FactCheckIcon />, label: '사실 검증' },
              { icon: <SourceIcon />, label: '출처 표기' },
              { icon: <StyleIcon />, label: '톤앤매너' },
              { icon: <FormatListBulletedIcon />, label: '구조화' },
            ].map((it, i) => (
              <Grid item xs={6} md={3} key={i}>
                <CardSoft>
                  <CardContent sx={{ textAlign: 'center', py: 4 }}>
                    <Box sx={{ mb: 1.5, '& svg': { fontSize: 32, color: '#00d4ff' } }}>{it.icon}</Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{it.label}</Typography>
                  </CardContent>
                </CardSoft>
              </Grid>
            ))}
          </Grid>

          {/* 프로세스 플로우 */}
          <Box sx={{ mt: 6 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, textAlign: 'center' }}>
              4단계 검수 프로세스
            </Typography>
            <Grid container spacing={2}>
              {['초안', '검증', '교열', '발행'].map((step, i) => (
                <Grid item xs={6} md={3} key={step}>
                  <CardSoft sx={{ position: 'relative' }}>
                    <CardContent sx={{ py: 3, textAlign: 'center' }}>
                      <Box sx={{
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        mx: 'auto',
                        mb: 1.5,
                        border: '1px solid rgba(255,255,255,0.3)',
                        display: 'grid',
                        placeItems: 'center',
                        fontSize: 12,
                        color: 'rgba(255,255,255,0.7)'
                      }}>{i + 1}</Box>
                      <Typography sx={{ fontWeight: 700, fontSize: '0.9rem' }}>{step}</Typography>
                    </CardContent>
                  </CardSoft>
                </Grid>
              ))}
            </Grid>
          </Box>

          {/* 샘플 문단 */}
          <Box sx={{ mt: 6 }}>
            <CardSoft>
              <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
                  샘플 문단(예시)
                </Typography>
                <Typography sx={{ color: 'rgba(255,255,255,0.85)', fontStyle: 'italic', mb: 2 }}>
                  "○○구 어린이 통학로 안전 점검 결과를 공개합니다. 지난달 접수된 민원 12건을 바탕으로
                  현장 점검을 완료했고, 개선이 필요한 3곳에 예산 반영을 요청했습니다."
                </Typography>
                <Typography variant="caption" sx={{ display: 'block', opacity: 0.6 }}>
                  ※ 예시 문구입니다. 실제 발행 전 수치·출처·일정을 확인하세요.
                </Typography>
              </CardContent>
            </CardSoft>
          </Box>
        </ContentContainer>
      </Section>

      {/* SNS vs Blog Comparison */}
      <Section sx={{
        backgroundColor: 'rgba(255,255,255,0.01)',
        py: { xs: 6, md: 10 }
      }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 700,
              mb: 2,
              textAlign: 'center'
            }}>
              왜 네이버 블로그인가?
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)'
            }}>
              7천만 이용자가 매일 찾는 곳에서, 제한 없는 긴 글로 당신의 철학을 전하세요
            </Typography>
          </InViewFade>

          {/* 1단계: 검색 점유율 우위 */}
          <InViewFade>
            <Grid container spacing={4} sx={{ mb: 8 }}>
              <Grid item xs={12} md={4}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
                      대한민국 검색의 중심
                    </Typography>

                    <Box sx={{ mb: 3 }}>
                      <Typography variant="h3" sx={{ fontWeight: 900, color: '#f8c023' }}>
                        70%
                      </Typography>
                      <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                        네이버 점유율
                      </Typography>
                    </Box>

                    <Box sx={{ mb: 3 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Box sx={{
                          width: 20, height: 12,
                          backgroundColor: '#00d4ff',
                          mr: 1, borderRadius: 1
                        }} />
                        <Typography variant="body2">네이버 70%</Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Box sx={{
                          width: 8, height: 12,
                          backgroundColor: 'rgba(255,255,255,0.4)',
                          mr: 1, borderRadius: 1
                        }} />
                        <Typography variant="body2">구글 27%</Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Box sx={{
                          width: 2, height: 12,
                          backgroundColor: 'rgba(255,255,255,0.2)',
                          mr: 1, borderRadius: 1
                        }} />
                        <Typography variant="body2">기타 3%</Typography>
                      </Box>
                    </Box>

                    <Typography variant="body1" sx={{
                      fontWeight: 600,
                      color: 'rgba(255,255,255,0.9)',
                      lineHeight: 1.6
                    }}>
                      가장 많은 유권자가 모이는 곳
                    </Typography>
                  </CardContent>
                </CardSoft>
              </Grid>

              {/* 2단계: 플랫폼 특성 비교 */}
              <Grid item xs={12} md={4}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
                      무제한 텍스트 vs 제약적 SNS
                    </Typography>

                    <Box sx={{ mb: 3 }}>
                      <Box sx={{
                        p: 2,
                        border: '2px solid #f8c023',
                        borderRadius: 2,
                        mb: 2,
                        backgroundColor: 'rgba(248, 192, 35, 0.1)'
                      }}>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8c023' }}>
                          네이버 블로그
                        </Typography>
                        <Typography variant="body1" sx={{ fontWeight: 600 }}>
                          무제한 장문
                        </Typography>
                      </Box>

                      <Box sx={{ opacity: 0.6 }}>
                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                          페이스북: 63,206자 제한
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                          인스타그램: 2,200자 제한
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                          X(트위터): 280자 제한
                        </Typography>
                      </Box>
                    </Box>

                    <Typography variant="body1" sx={{
                      fontWeight: 600,
                      color: 'rgba(255,255,255,0.9)',
                      lineHeight: 1.6
                    }}>
                      정치인의 비전과 신념을 온전히 전달
                    </Typography>
                  </CardContent>
                </CardSoft>
              </Grid>

              {/* 3단계: 전문가 마케팅 사례 */}
              <Grid item xs={12} md={4}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
                      이미 검증된 전략
                    </Typography>

                    <Box sx={{ mb: 3 }}>
                      <Typography variant="body1" sx={{
                        fontWeight: 600,
                        mb: 2,
                        color: 'rgba(255,255,255,0.9)'
                      }}>
                        전문직 마케팅 사례
                      </Typography>

                      <Box sx={{ textAlign: 'left', mb: 3 }}>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          • 의사, 변호사, 세무사
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          • 네이버 블로그 → SNS 허브 전략
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          • 검색 유입 → 고객 전환
                        </Typography>
                      </Box>

                      {/* 방사형 연결 다이어그램 */}
                      <Box sx={{
                        position: 'relative',
                        width: '200px',
                        height: '200px',
                        mx: 'auto',
                        mb: 2
                      }}>
                        {/* 중앙 네이버 블로그 */}
                        <Box sx={{
                          position: 'absolute',
                          top: '50%',
                          left: '50%',
                          transform: 'translate(-50%, -50%)',
                          width: 60,
                          height: 60,
                          borderRadius: '50%',
                          border: '3px solid #f8c023',
                          backgroundColor: 'rgba(248, 192, 35, 0.2)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          zIndex: 10
                        }}>
                          <img
                            src="/icons/Nblog.webp"
                            alt="네이버 블로그"
                            style={{ width: 40, height: 40 }}
                          />
                        </Box>

                        {/* 연결선들 */}
                        {[
                          { angle: 0, icon: 'icon-facebook.png', name: '페이스북' },
                          { angle: 72, icon: 'icon-instagram.png', name: '인스타그램' },
                          { angle: 144, icon: 'icon-X.png', name: 'X(트위터)' },
                          { angle: 216, icon: 'icon-threads.png', name: '스레드' }
                        ].map((sns, index) => {
                          const radian = (sns.angle * Math.PI) / 180;
                          const x = Math.cos(radian) * 70;
                          const y = Math.sin(radian) * 70;

                          return (
                            <React.Fragment key={sns.name}>
                              {/* 연결선 */}
                              <Box sx={{
                                position: 'absolute',
                                top: '50%',
                                left: '50%',
                                width: '70px',
                                height: '2px',
                                backgroundColor: 'rgba(0, 212, 255, 0.4)',
                                transformOrigin: '0 50%',
                                transform: `translate(0, -50%) rotate(${sns.angle}deg)`,
                                zIndex: 1
                              }} />

                              {/* SNS 아이콘 */}
                              <Box sx={{
                                position: 'absolute',
                                top: '50%',
                                left: '50%',
                                transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
                                width: 40,
                                height: 40,
                                borderRadius: '50%',
                                border: '2px solid rgba(255, 255, 255, 0.3)',
                                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                opacity: 0.7,
                                zIndex: 5
                              }}>
                                <img
                                  src={`/icons/${sns.icon}`}
                                  alt={sns.name}
                                  style={{ width: 24, height: 24 }}
                                />
                              </Box>
                            </React.Fragment>
                          );
                        })}
                      </Box>

                      <Box sx={{
                        p: 2,
                        backgroundColor: 'rgba(0, 212, 255, 0.1)',
                        borderRadius: 2,
                        border: '1px solid rgba(0, 212, 255, 0.3)'
                      }}>
                        <Typography variant="body2" sx={{
                          fontWeight: 600,
                          textAlign: 'center'
                        }}>
                          블로그 작성 → SNS 확산 → 유입 증가 → 성과 창출
                        </Typography>
                      </Box>
                    </Box>

                    <Typography variant="body1" sx={{
                      fontWeight: 600,
                      color: 'rgba(255,255,255,0.9)',
                      lineHeight: 1.6
                    }}>
                      전문직도 선택한 검증된 전략을 정치에도
                    </Typography>
                  </CardContent>
                </CardSoft>
              </Grid>
            </Grid>
          </InViewFade>

          {/* 결론 메시지 */}
          <InViewFade>
            <Box sx={{
              textAlign: 'center',
              p: 4,
              border: '2px solid #f8c023',
              borderRadius: 3,
              backgroundColor: 'rgba(248, 192, 35, 0.1)',
              maxWidth: 800,
              mx: 'auto'
            }}>
              <Typography variant="h4" sx={{
                fontWeight: 900,
                mb: 2,
                color: '#f8c023'
              }}>
                정치인이라면 당연히 네이버 블로그
              </Typography>
              <Typography variant="body1" sx={{
                color: 'rgba(255,255,255,0.9)',
                lineHeight: 1.8
              }}>
                온라인 검색에서 먼저 발견되는 콘텐츠와 논리적 설득부터 감정적 공감까지, 상황별 맞춤 원고로 유권자에게 더 깊이 다가갈 수 있습니다.
              </Typography>
            </Box>
          </InViewFade>

          {/* 통계 섹션 */}
          <Box sx={{ mt: 6, textAlign: 'center' }}>
            <InViewFade timeout={1200}>
              <Box sx={{
                backgroundColor: 'rgba(255,255,255,0.04)',
                borderRadius: '16px',
                p: 4,
                border: '1px solid rgba(255,255,255,0.08)'
              }}>
                <Typography variant="h6" sx={{
                  fontWeight: 800,
                  mb: 2,
                  color: '#00d4ff'
                }}>
정치인 검색 플랫폼 현황
                </Typography>
                <Typography sx={{
                  fontSize: '1.1rem',
                  color: 'rgba(255,255,255,0.9)',
                  fontWeight: 600,
                  lineHeight: 1.6
                }}>
                  유권자가 후보자 정보를 찾을 때 주요 포털 검색이 일반적입니다.<br />
                  <Box component="span" sx={{ color: '#00d4ff', fontWeight: 800 }}>
                    네이버 블로그 검색 순위가 정치적 영향력에 도움이 될 수 있습니다.
                  </Box>
                </Typography>
              </Box>
            </InViewFade>
          </Box>

          {/* 핵심 메시지 */}
          <Box sx={{ mt: 6, textAlign: 'center' }}>
            <InViewFade timeout={1400}>
              <Typography variant="h5" sx={{
                fontWeight: 800,
                color: '#00d4ff',
                mb: 2,
                fontSize: { xs: '1.3rem', md: '1.5rem' }
              }}>
핵심 통찰
              </Typography>
              <Typography sx={{
                fontSize: { xs: '1.1rem', md: '1.2rem' },
                fontWeight: 600,
                color: 'rgba(255,255,255,0.9)',
                lineHeight: 1.7,
                maxWidth: '800px',
                mx: 'auto'
              }}>
                "정치 활동에서 SNS '소통'만으로는 한계가 있습니다.<br />
                <Box component="span" sx={{ color: '#00d4ff', fontWeight: 800 }}>
                  유권자가 검색하는 순간에 잡히는 것이 결정적입니다."
                </Box>
              </Typography>
            </InViewFade>
          </Box>
        </ContentContainer>
      </Section>

      {/* Before/After + Testimonials Combined */}
      <Section id="proof" aria-labelledby="evidence-heading">
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="evidence-heading" variant="h4" sx={{ fontWeight: 800, mb: 2, textAlign: 'center' }}>
              전자두뇌비서관 도입 전후 비교
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              color: 'rgba(255,255,255,0.7)',
              fontWeight: 500
            }}>
              전후 비교
            </Typography>
          </InViewFade>

          {/* Before/After Visual Evidence */}
          <Grid container spacing={4} alignItems="stretch" sx={{ mb: 6 }}>
            <Grid item xs={12} md={6}>
              <InViewFade>
                <CardSoft sx={{ height: '100%' }}>
                  <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: '#999', mb: 2 }}>
Before
                    </Typography>
                    <Typography sx={{ mb: 3, lineHeight: 1.6 }}>
                      수동으로 블로그 콘텐츠 작성하느라 시간 부족.<br />
                      일관성 없는 메시지 전달로 검색 노출 저조.
                    </Typography>
                    <Box
                      component="img"
                      src="/images/search-before.jpg"
                      alt="AI 도입 전 상태"
                      loading="lazy"
                      decoding="async"
                      style={{ width: '100%', borderRadius: 12 }}
                    />
                    <Typography variant="caption" sx={{ mt: 1, opacity: 0.7, display: 'block' }}>
                      예시 화면(데모). 실제 결과와 다를 수 있음.
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>

            <Grid item xs={12} md={6}>
              <InViewFade timeout={400}>
                <CardEmphasis sx={{ height: '100%' }}>
                  <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                    <Typography variant="h6" sx={{ fontWeight: 800, color: '#4FC3F7', mb: 2 }}>
After
                    </Typography>
                    <Typography sx={{ mb: 3, lineHeight: 1.6 }}>
                      AI가 자동으로 전문적인 콘텐츠 생성.<br />
                      정책 연구와 현장 활동에 집중 가능.
                    </Typography>
                    <Box
                      component="img"
                      src="/images/search-after.jpg"
                      alt="AI 도입 후 상태"
                      loading="lazy"
                      decoding="async"
                      style={{ width: '100%', borderRadius: 12 }}
                    />
                    <Typography variant="caption" sx={{ mt: 1, opacity: 0.7, display: 'block' }}>
                      예시 화면(데모). 실제 결과와 다를 수 있음.
                    </Typography>
                    {demoMode && (
                      <Box sx={{
                        mt: 3,
                        p: 2,
                        backgroundColor: 'rgba(79, 195, 247, 0.1)',
                        borderRadius: '8px',
                        border: '1px solid rgba(79, 195, 247, 0.3)'
                      }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#4FC3F7' }}>
콘텐츠 생성 시간 대폭 단축<br />
                          온라인 영향력 향상
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </CardEmphasis>
              </InViewFade>
            </Grid>
          </Grid>

          {/* Content Examples */}
          <Box sx={{ mt: 6 }}>
            <InViewFade>
              <Typography variant="h5" sx={{
                fontWeight: 700,
                mb: 4,
                textAlign: 'center',
                color: 'rgba(255,255,255,0.95)'
              }}>
                원고 작성 품질 비교
              </Typography>
            </InViewFade>

            <Grid container spacing={4}>
              <Grid item xs={12} md={6}>
                <InViewFade>
                  <CardSoft>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: '#999', mb: 3 }}>
                        Before: 직접 작성
                      </Typography>
                      <Box
                        sx={{
                          minHeight: 300,
                          backgroundColor: 'rgba(255,255,255,0.02)',
                          border: '2px dashed rgba(255,255,255,0.2)',
                          borderRadius: 2,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          p: 3
                        }}
                      >
                        <Typography variant="body2" sx={{
                          color: 'rgba(255,255,255,0.5)',
                          textAlign: 'center',
                          fontStyle: 'italic'
                        }}>
                          스크린샷 추가 예정<br />
                          (기존 방식의 원고 예시)
                        </Typography>
                      </Box>
                    </CardContent>
                  </CardSoft>
                </InViewFade>
              </Grid>

              <Grid item xs={12} md={6}>
                <InViewFade timeout={400}>
                  <CardEmphasis>
                    <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                      <Typography variant="h6" sx={{ fontWeight: 800, color: '#4FC3F7', mb: 3 }}>
                        After: AI 생성 + 검토
                      </Typography>
                      <Box
                        sx={{
                          minHeight: 300,
                          backgroundColor: 'rgba(79, 195, 247, 0.05)',
                          border: '2px dashed rgba(79, 195, 247, 0.3)',
                          borderRadius: 2,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          p: 3
                        }}
                      >
                        <Typography variant="body2" sx={{
                          color: 'rgba(79, 195, 247, 0.7)',
                          textAlign: 'center',
                          fontStyle: 'italic'
                        }}>
                          스크린샷 추가 예정<br />
                          (AI 생성 + 검토 완료 원고 예시)
                        </Typography>
                      </Box>
                    </CardContent>
                  </CardEmphasis>
                </InViewFade>
              </Grid>
            </Grid>
          </Box>

          {/* Final Evidence CTA */}
          <Box sx={{ textAlign: 'center', mt: 6 }}>
            <InViewFade timeout={1000}>
              <Typography variant="h6" sx={{
                mb: 3,
                fontWeight: 600,
                color: 'rgba(255,255,255,0.9)'
              }}>
                더 많은 유권자와 소통하고, 정치적 영향력을 확대할 준비가 되셨나요?<br />
                전자두뇌비서관과 함께 새로운 정치 커뮤니케이션을 시작해보세요.
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
                <CTAButton aria-label="Before & After 확인" onClick={handlePrimaryCTA}>
                  Before & After
                </CTAButton>
                <OutlineButton aria-label="원고 샘플 확인" onClick={() => setOpenSample(true)}>
                  원고 샘플 확인
                </OutlineButton>
              </Stack>
            </InViewFade>
          </Box>
        </ContentContainer>
      </Section>

      {/* Urgency */}
      <Section id="urgency" aria-labelledby="urgency-heading" sx={{
        bgcolor: 'rgba(255,255,255,0.02)',
        py: { xs: 4, md: 8 },
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center'
      }}>
        <ContentContainer maxWidth="lg">
          <Grid container spacing={4} alignItems="center">
            {/* 좌측: 정청래 이미지 */}
            <Grid item xs={12} md={6}>
              <InViewFade>
                <Box
                  sx={{
                    backgroundColor: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '16px',
                    backdropFilter: 'blur(6px)',
                    p: 4,
                    textAlign: 'center'
                  }}
                >
                  <Box
                    component="img"
                    src="/sns/jeongcr_news.png"
                    alt="정청래 대표 SNS 공천 필수화 발언"
                    sx={{
                      maxWidth: '100%',
                      width: '100%',
                      height: 'auto',
                      borderRadius: '8px',
                      mb: 3
                    }}
                  />
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      mb: 1,
                      fontSize: { xs: '1.1rem', md: '1.3rem' }
                    }}
                  >
                    정청래 대표 발언
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 600,
                      mb: 2,
                      fontSize: { xs: '1rem', md: '1.1rem' },
                      fontStyle: 'italic',
                      color: '#00d4ff'
                    }}
                  >
                    "SNS 활동, 공천 평가에 반영"
                  </Typography>
                  <Typography variant="caption" sx={{
                    fontSize: '0.85rem',
                    opacity: 0.7
                  }}>
                    정청래 대표의 실제 발언 내용
                  </Typography>
                </Box>
              </InViewFade>
            </Grid>

            {/* 우측: 텍스트 및 CTA */}
            <Grid item xs={12} md={6}>
              <InViewFade timeout={400}>
                <Typography variant="h4" sx={{
                  fontWeight: 800,
                  mb: 3,
                  fontSize: { xs: '1.8rem', md: '2.2rem' }
                }}>
                  준비는 미룰 수 없습니다
                </Typography>

                <Typography variant="body1" sx={{
                  lineHeight: 1.7,
                  color: 'rgba(255,255,255,0.9)',
                  mb: 4,
                  fontSize: '1.1rem'
                }}>
                  민주당은 공천 심사에서 온라인 활동을 평가 지표로 검토하고 있습니다.
                  <br /><br />
                  검색과 SNS에서 의원 이름이 보이지 않으면 유권자가 확인하기 어렵습니다.
                </Typography>

                {/* Trial Information */}
                <Box sx={{
                  p: 4,
                  backgroundColor: 'rgba(0, 212, 255, 0.05)',
                  border: '1px solid rgba(0, 212, 255, 0.2)',
                  borderRadius: 3,
                  mb: 4
                }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
                    체험판 제공
                  </Typography>
                  <Stack spacing={1.5}>
                    <Typography sx={{ fontSize: '1rem', display: 'flex', alignItems: 'center' }}>
                      <Box component="span" sx={{ color: '#00d4ff', mr: 1, fontWeight: 'bold' }}>✓</Box>
                      의정활동 콘텐츠 8편 자동 생성
                    </Typography>
                    <Typography sx={{ fontSize: '1rem', display: 'flex', alignItems: 'center' }}>
                      <Box component="span" sx={{ color: '#00d4ff', mr: 1, fontWeight: 'bold' }}>✓</Box>
                      최대 31일 체험 기간 제공
                    </Typography>
                    <Typography sx={{ fontSize: '1rem', display: 'flex', alignItems: 'center' }}>
                      <Box component="span" sx={{ color: '#00d4ff', mr: 1, fontWeight: 'bold' }}>✓</Box>
                      효과 확인 후 이용 여부 결정
                    </Typography>
                  </Stack>
                </Box>

                <CTAButton
                  size="large"
                  onClick={handlePrimaryCTA}
                  sx={{
                    fontSize: '1.2rem',
                    px: 5,
                    py: 1.5
                  }}
                >
                  준비 시작
                </CTAButton>
              </InViewFade>
            </Grid>
          </Grid>
        </ContentContainer>
      </Section>


      {/* 요금제 */}
      <Section>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{ fontWeight: 800, mb: 2, textAlign: 'center' }}>
              요금제
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 4, textAlign: 'center' }}>
              선거구 독점 운영으로 효과적인 정치 마케팅을 지원합니다.
            </Typography>

            {/* 공통 기능 안내 */}
            <Box sx={{
              mb: 6,
              p: 4,
              backgroundColor: 'rgba(0, 212, 255, 0.05)',
              border: '1px solid rgba(0, 212, 255, 0.2)',
              borderRadius: 3,
              textAlign: 'center'
            }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, color: '#00d4ff' }}>
                모든 플랜 공통 제공
              </Typography>
              <Typography sx={{ mb: 2 }}>
                기본 블로그 원고 (1,250자 내외) • AI 원고 생성 • 3회 재생성 • 네이버 검색 최적화 • 개인 맞춤 설정
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)' }}>
                플랜별 차이는 월 제공 횟수입니다
              </Typography>
            </Box>
          </InViewFade>

          <Grid container spacing={4} justifyContent="center">
            {[
              {
                name: '로컬 블로거',
                price: '월 55,000원',
                count: '월 8회',
                description: '기초의원 개인 활동',
                color: '#003a87'
              },
              {
                name: '리전 인플루언서',
                price: '월 132,000원',
                count: '월 20회',
                description: '활발한 의정활동',
                color: '#55207d'
              },
              {
                name: '오피니언 리더',
                price: '월 330,000원',
                count: '월 60회',
                description: '집중 홍보 기간',
                color: '#006261'
              }
            ].map((plan, index) => (
              <Grid item xs={12} md={4} key={index}>
                <InViewFade timeout={600 + index * 100}>
                  <Card
                    sx={{
                      bgcolor: 'rgba(255,255,255,0.05)',
                      border: `1px solid ${plan.color}40`,
                      borderRadius: 3,
                      height: '100%',
                      position: 'relative',
                      transition: 'all 0.3s ease',
                      '&:hover': {
                        transform: 'translateY(-8px)',
                        boxShadow: `0 12px 40px ${plan.color}30`
                      }
                    }}
                  >
                    <CardContent sx={{ p: 4, textAlign: 'center' }}>
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          mb: 1,
                          color: plan.color
                        }}
                      >
                        {plan.name}
                      </Typography>
                      <Typography
                        variant="h4"
                        sx={{
                          fontWeight: 900,
                          mb: 1
                        }}
                      >
                        {plan.price}
                      </Typography>
                      <Typography
                        sx={{
                          color: 'rgba(255,255,255,0.7)',
                          mb: 4
                        }}
                      >
                        {plan.description}
                      </Typography>
                      <Typography
                        variant="h3"
                        sx={{
                          fontWeight: 900,
                          mb: 4,
                          color: plan.color
                        }}
                      >
                        {plan.count}
                      </Typography>
                      <Button
                        variant="outlined"
                        sx={{
                          backgroundColor: 'transparent',
                          borderColor: plan.color,
                          color: plan.color,
                          fontWeight: 700,
                          px: 4,
                          py: 1.5,
                          '&:hover': {
                            backgroundColor: plan.color,
                            color: 'black'
                          }
                        }}
                      >
                        상담 신청
                      </Button>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Grid>
            ))}
          </Grid>

          <InViewFade>
            <Box
              sx={{
                mt: 6,
                p: 4,
                backgroundColor: 'rgba(255, 193, 7, 0.1)',
                border: '1px solid rgba(255, 193, 7, 0.3)',
                borderRadius: 3,
                textAlign: 'center'
              }}
            >
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  color: '#f8c023'
                }}
              >
                🏛️ 선거구 독점 정책
              </Typography>
              <Typography sx={{ lineHeight: 1.6 }}>
                동일 선거구 내에는 1인만 서비스를 이용할 수 있습니다.
                <br />
                선착순으로 선거구를 확보하여 독점적인 디지털 우위를 점하세요.
              </Typography>
            </Box>
          </InViewFade>
        </ContentContainer>
      </Section>

      {/* FAQ */}
      <Section aria-labelledby="faq-heading">
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="faq-heading" variant="h4" sx={{ fontWeight: 800, mb: 4 }}>
              자주 묻는 질문
            </Typography>
          </InViewFade>
          <Stack spacing={2}>
            {FAQS.map((item, i) => (
              <InViewFade key={item.q} timeout={600 + i * 80}>
                <Accordion
                  disableGutters
                  sx={{ backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 2, '&::before': { display: 'none' } }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon sx={{ color: '#00d4ff' }} />}
                    aria-controls={`faq-${i}-content`}
                    id={`faq-${i}-header`}
                    sx={{ px: 3, py: 2 }}
                  >
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                      {item.q}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 3, pb: 3 }}>
                    <Typography sx={{  }}>{item.a}</Typography>
                  </AccordionDetails>
                </Accordion>
              </InViewFade>
            ))}
          </Stack>
        </ContentContainer>
      </Section>

      {/* Final CTA & Footer */}
      <Box
        component="footer"
        sx={{
          textAlign: 'center',
          background: 'linear-gradient(to bottom, #001320, #050511)',
          borderBottom: 'none',
          scrollSnapAlign: 'start',
          minHeight: '100vh',
          position: 'relative',
        }}
        aria-labelledby="final-cta-heading"
      >
        {/* Final CTA - 중앙 배치 */}
        <Box
          sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '100%',
          }}
        >
          <ContentContainer maxWidth="lg">
            <InViewFade>
              <Typography id="final-cta-heading" variant="h4" sx={{ fontWeight: 900, mb: 2 }}>
                성과 홍보 고민 해결
              </Typography>
              <Typography
                sx={{
                  mb: 4,
                  maxWidth: 800,
                  mx: 'auto',
                }}
              >
                더 많은 유권자와 소통하고, 정치적 영향력을 확대할 준비가 되셨나요?<br />
                전자두뇌비서관과 함께 새로운 정치 커뮤니케이션을 시작해보세요.
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
                <CTAButton aria-label="성과 미리보기" onClick={handlePrimaryCTA}>
                  성과 미리보기
                </CTAButton>
              </Stack>
            </InViewFade>
          </ContentContainer>
        </Box>

        {/* Footer - 하단 바짝 배치 */}
        <Box
          sx={{
            position: 'absolute',
            bottom: 0,
            left: '50%',
            transform: 'translateX(-50%)',
            width: '100%',
            pb: 2,
          }}
        >
          <ContentContainer maxWidth="lg">
            <InViewFade>
              <Typography
                sx={{
                  mb: 2,
                  fontSize: '0.875rem',
                  borderTop: '1px solid rgba(255,255,255,0.1)',
                  pt: 3,
                }}
              >
                전자두뇌비서관
              </Typography>
              <Typography
                sx={{
                  color: 'rgba(255,255,255,0.8)',
                  fontSize: '0.75rem',
                  lineHeight: 1.6,
                  whiteSpace: 'pre-line',
                }}
              >
                사이버브레인 | 사업자등록번호: 870-55-00786 | 통신판매업신고번호: (비움){'\n'}
                대표: 차서영 | 인천광역시 계양구 용종로 124, 학마을한진아파트 139동 1504호{'\n'}
                대표번호: 010-4885-6206{'\n\n'}
                Copyright 2025. CyberBrain. All Rights Reserved.
              </Typography>
            </InViewFade>
          </ContentContainer>
        </Box>
      </Box>

      <SampleSpeechModal open={openSample} onClose={() => setOpenSample(false)} />
    </Page>
  );
};

export default AboutPage;