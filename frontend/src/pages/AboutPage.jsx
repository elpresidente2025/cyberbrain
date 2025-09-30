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
    desc: '정책, 활동, 소식을 전문적으로 작성합니다.',
  },
  {
    title: '네이버·구글 1페이지 진출',
    desc: '유권자가 먼저 찾아오는 의원이 되세요.',
    subtext: '검색 1페이지 노출 가능성 극대화'
  },
  {
    title: '질문 답변 상위 노출',
    desc: '"○○구 의원 공약 뭐야?" 검색 상위 답변에 내 이름이 나옵니다.',
  },
  {
    title: '5분 작성 자동화',
    desc: '시간은 줄이고, 품질은 높이고.',
    subtext: '본업인 정책과 현장활동에 집중하세요'
  },
];

const SAFETY_FEATURES = [
  {
    title: '법적 안전성 및 선거법 준수',
    desc: '선거법 걱정 없이 안전하게.',
    subtext: '180일 규정 등 모든 선거법을 AI가 자동 적용합니다. 정치적 리스크 키워드를 자동 회피하고 의견과 사실을 명확히 구분합니다.'
  },
  {
    title: '상황별 작법 및 지능적 톤앤매너',
    desc: '상황마다 다른 말투, AI가 알아서 선택합니다.',
    subtext: '일상 소통, 정책 제안, 활동 보고, 시사 논평 등 주제를 분석하여 최적의 톤앤매너를 자동 적용합니다.'
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


const STATS_DATA = [
  {
    title: "콘텐츠 생성 시간",
    number: "5",
    unit: "분",
    description: "시간은 줄이고, 품질은 높이고",
    subtext: "기존 대비 평균 90% 이상 단축"
  },
  {
    title: "검색 노출률",
    number: "1",
    unit: "페이지",
    description: "유권자가 먼저 찾아오는 의원이 되세요",
    subtext: "구글·네이버 1페이지 노출 최적화"
  },
  {
    title: "법적 안전성",
    number: "180",
    unit: "일",
    description: "선거법 걱정 없이 안전하게",
    subtext: "선거법 180일 규정 자동 준수"
  },
];

const FAQS = [
  {
    q: '생성되는 콘텐츠의 정치적 안전성은 어떻게 유지되나요?',
    a: '당의 가치와 정책 방향에 맞는 콘텐츠만 생성됩니다.',
    detail: 'AI는 당 강령과 정책 기조를 학습하여 당론에 부합하는 콘텐츠만 생성합니다. 정치적으로 민감한 키워드는 자동 회피하며, 의견과 사실을 명확히 구분합니다.'
  },
  {
    q: '개인정보 수집과 데이터 보안은 어떻게 처리되나요?',
    a: '최소한의 필수 정보만 수집하며, 최고 수준 암호화로 보호합니다.',
    detail: '모든 데이터는 최고 수준 보안 암호화로 저장됩니다. 개인정보보호법과 정치자금법을 완전히 준수하며, 제3자와 데이터를 공유하지 않습니다. 정기적인 보안 점검을 통해 안전성을 유지합니다.'
  },
  {
    q: '당적 인증은 어떻게 이루어지나요?',
    a: '당적 증명서와 당비 납부 내역으로 간편하게 인증됩니다.',
    detail: '모두 휴대폰에서 간편하게 확인 가능하며, 스크린샷을 찍어 업로드하면 자동으로 문서 내용을 읽어 검증합니다. 인증은 분기별(연 4회) 진행되며, 인증이 확인되지 않으면 서비스 이용이 제한됩니다.'
  },
  {
    q: '선거법 180일 규정은 어떻게 준수하나요?',
    a: '180일 규정 등 모든 선거법을 AI가 자동 적용합니다.',
    detail: '선거 기간, 금지 행위, 표현 제한 등 정치 관련 법규를 AI가 실시간으로 모니터링하며 자동 적용합니다. 법적 리스크가 있는 표현은 생성 단계에서 차단됩니다.'
  },
  {
    q: '콘텐츠 스타일을 개인 취향에 맞게 조정할 수 있나요?',
    a: '개인의 글쓰기 스타일과 톤앤매너를 학습하여 맞춤형 콘텐츠를 생성합니다.',
    detail: '선호하는 주제, 문체, 어조 등을 학습하여 개별 맞춤형 콘텐츠를 생성합니다. 지속적인 피드백을 통해 더욱 정교해집니다.'
  },
  {
    q: '선거구 독점 정책은 어떻게 운영되나요?',
    a: '우리 지역구에서는 나만 사용할 수 있는 디지털 우위입니다.',
    detail: '하나의 선거구에는 한 명의 정치인만 서비스를 이용할 수 있습니다. 선착순으로 등록이 완료되며, 동일 지역구 내 경쟁자는 이용이 제한됩니다.'
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

const Section = styled('section')(({ theme }) => ({
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

  // FAQ accordion state - only one panel can be open at a time
  const [expandedFaq, setExpandedFaq] = React.useState(false);

  const handleAccordionChange = (panel) => (event, isExpanded) => {
    setExpandedFaq(isExpanded ? panel : false);
  };

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
                mb: { xs: 4, md: 5, lg: 5 }, // 로고와의 여백을 위해 마진 증가
                fontSize: { xs: '1.1rem', md: '1.35rem', lg: '1.5rem' }, // 태블릿 사이즈 추가
                opacity: 0.9
              }}
            >
              검색되지 않으면 이런 칭찬도 못 듣습니다.
            </Typography>
            <Box sx={{ mb: 3, display: 'flex', justifyContent: 'center' }}>
              <img
                src="/logo-landscape.png"
                alt="AI Secretary Logo"
                style={{
                  height: '48px',
                  width: 'auto',
                  opacity: 0.9,
                  filter: 'brightness(1.1)'
                }}
              />
            </Box>
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

      {/* 핵심 성과 지표 */}
      <Box component="section" id="stats" sx={{
        py: 10,
        scrollSnapAlign: 'start',
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center'
      }}>
        <Container>
          <InViewFade>
            <Typography variant="h4" sx={{ fontWeight: 800, textAlign: 'center', mb: 6 }}>
              핵심 성과 지표
            </Typography>
          </InViewFade>
          <Grid container spacing={6}>
            {STATS_DATA.map((stat, idx) => (
              <Grid item xs={12} sm={4} md={4} key={stat.title}>
                <InViewFade timeout={600 + idx * 100}>
                  <Card sx={{
                    bgcolor: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(0, 212, 255, 0.2)',
                    borderRadius: 3,
                    height: '100%',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      borderColor: 'rgba(0, 212, 255, 0.5)',
                      transform: 'translateY(-8px)',
                      boxShadow: '0 12px 40px rgba(0, 212, 255, 0.2)'
                    }
                  }}>
                    <CardContent sx={{ p: { xs: 3, sm: 2, md: 3, lg: 4 }, textAlign: 'center' }}>
                      <Typography variant="h2" sx={{
                        fontWeight: 900,
                        color: '#00d4ff',
                        mb: 0.5,
                        fontSize: { xs: '3.5rem', sm: '3rem', md: '3.5rem', lg: '4.5rem' },
                        lineHeight: 1
                      }}>
                        {stat.number}
                        <Typography component="span" variant="h4" sx={{
                          ml: 1,
                          color: 'rgba(255,255,255,0.8)',
                          fontWeight: 700,
                          fontSize: { xs: '1.8rem', sm: '1.5rem', md: '1.8rem', lg: '2.2rem' }
                        }}>
                          {stat.unit}
                        </Typography>
                      </Typography>
                      <Typography variant="subtitle2" sx={{
                        color: 'rgba(255,255,255,0.5)',
                        mb: 2,
                        fontWeight: 500,
                        fontSize: { xs: '0.75rem', sm: '0.65rem', md: '0.7rem', lg: '0.75rem' }
                      }}>
                        {stat.title}
                      </Typography>
                      <Typography sx={{
                        color: '#00d4ff',
                        mb: 1,
                        fontSize: { xs: '0.95rem', sm: '0.75rem', md: '0.85rem', lg: '0.95rem' },
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {stat.description}
                      </Typography>
                      <Typography variant="body2" sx={{
                        color: 'rgba(255,255,255,0.5)',
                        fontSize: { xs: '0.8rem', sm: '0.65rem', md: '0.7rem', lg: '0.8rem' },
                        lineHeight: 1.4
                      }}>
                        {stat.subtext}
                      </Typography>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

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
        minHeight: '700px',
        display: 'flex',
        alignItems: 'center',
        scrollSnapAlign: 'start',
      }}>
        <ContentContainer maxWidth="lg" sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center' }}>
          <Grid container spacing={4} sx={{
            width: '100%',
            // 세로형 + 정사각형 + 가로 4:3까지 높이 기반 레이아웃
            '@media (max-aspect-ratio: 16/9)': {
              height: '100%',
            }
          }}>
            {/* 좌측: 이미지 */}
            <Grid item xs={12} md={6} sx={{
              // [데스크톱] 16:9 이상 - 중앙 정렬
              '@media (min-aspect-ratio: 16/9)': {
                display: 'flex',
                alignItems: 'center',
              },
              // [모바일/태블릿] 16:9 미만 - 전체 너비, 상단 60% 차지, 하단 정렬
              '@media (max-aspect-ratio: 16/9)': {
                flexBasis: '100%',
                maxWidth: '100%',
                height: '60%',
                maxHeight: '60%',
                pb: 2,
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
              }
            }}>
              <Box sx={{
                width: '100%',
                p: { xs: 1, md: 2 },
                // [데스크톱] 16:9 이상 - aspectRatio 제거하여 내용에 맞게 높이 자동 조정
                '@media (min-aspect-ratio: 16/9)': {
                  aspectRatio: 'auto',
                },
                // [태블릿] 9/16~16/9 (정사각형~4:3) - 정사각형 유지
                '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                  aspectRatio: '1 / 1',
                  height: '100%',
                  p: 0,
                },
                // [모바일] 9/16 미만 (세로형) - 높이 90%로 여백 확보
                '@media (max-aspect-ratio: 9/16)': {
                  height: '90%',
                  aspectRatio: 'auto',
                  p: 0,
                },
              }}>
                <Grid container spacing={2} sx={{
                  height: '100%',
                  // [모바일] 세로 배치, spacing 제거
                  '@media (max-aspect-ratio: 9/16)': {
                    spacing: 0,
                  },
                  // [태블릿] 가로 2열 배치, spacing 추가
                  '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                    spacing: 1,
                  }
                }}>
                  {/* 이재명 이미지 */}
                  <Grid item xs={12} sx={{
                    // [모바일] 세로 배치, 상단 50%
                    '@media (max-aspect-ratio: 9/16)': {
                      height: '50%',
                      maxHeight: '50%',
                    },
                    // [태블릿] 가로 2열 배치, 좌측 50%
                    '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                      flexBasis: '50%',
                      maxWidth: '50%',
                      height: '100%',
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
                      // [태블릿] 패딩 조정
                      '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                        p: 1,
                      },
                      // [모바일] 패딩 줄이기
                      '@media (max-aspect-ratio: 9/16)': {
                        p: 1,
                      }
                    }}>
                      <img
                        src="/sns/lee-jae-myung.png"
                        alt="이재명"
                        style={{
                          maxWidth: '95%',
                          maxHeight: '95%',
                          borderRadius: 8,
                          objectFit: 'contain'
                        }}
                      />
                    </Box>
                  </Grid>

                  {/* 트럼프 이미지 */}
                  <Grid item xs={12} sx={{
                    // [모바일] 세로 배치, 하단 50%
                    '@media (max-aspect-ratio: 9/16)': {
                      height: '50%',
                      maxHeight: '50%',
                    },
                    // [태블릿] 가로 2열 배치, 우측 50%
                    '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                      flexBasis: '50%',
                      maxWidth: '50%',
                      height: '100%',
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
                      // [태블릿] 패딩 조정
                      '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 16/9)': {
                        p: 1,
                      },
                      // [모바일] 패딩 줄이기
                      '@media (max-aspect-ratio: 9/16)': {
                        p: 1,
                      }
                    }}>
                      <img
                        src="/sns/trump.png"
                        alt="트럼프"
                        style={{
                          maxWidth: '95%',
                          maxHeight: '95%',
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
              justifyContent: { xs: 'center', md: 'center' },
              // [모바일/태블릿] 16:9 미만 - 전체 너비, 하단 40% 차지
              '@media (max-aspect-ratio: 16/9)': {
                flexBasis: '100%',
                maxWidth: '100%',
                height: '40%',
                maxHeight: '40%',
                alignItems: 'flex-start',
                pt: 2,
              }
            }}>
              <Box sx={{
                px: { xs: 1, md: 2, lg: 2 },
                py: { xs: 3, md: 4, lg: 4 },
                textAlign: 'center',
                maxWidth: { xs: '400px', md: '500px', lg: '600px' },
                // 16:9 미만: 세로 패딩 최소화
                '@media (max-aspect-ratio: 16/9)': {
                  py: 0,
                  px: 2,
                },
                // 16:9 이상: 세로 패딩 줄임
                '@media (min-aspect-ratio: 16/9)': {
                  py: 2,
                }
              }}>
                <Typography variant="h3" sx={{
                  fontWeight: 900,
                  mb: 4,
                  color: '#00d4ff',
                  textShadow: '0 0 30px rgba(0,212,255,0.5)',
                  fontSize: { xs: '1.6rem', md: '2.5rem' },
                  // 세로형 (모바일, 폴드 커버): 작은 폰트
                  '@media (max-aspect-ratio: 9/16)': {
                    fontSize: '1.6rem',
                    mb: 3,
                  },
                  // 정사각형 (폴드 메인, 세로 태블릿): 중간 폰트
                  '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 4/3)': {
                    fontSize: 'clamp(2rem, 4vw, 3rem)',
                    mb: 2,
                  },
                  // 가로형 (데스크톱): 큰 폰트
                  '@media (min-aspect-ratio: 16/9)': {
                    fontSize: '2.5rem',
                    mb: 4,
                  }
                }}>
                  이미 검증된 성공 방식
                </Typography>
                <Typography variant="h6" sx={{
                  fontWeight: 500,
                  mb: 3,
                  lineHeight: 1.8,
                  color: 'rgba(255,255,255,0.9)',
                  fontSize: { xs: '1.0rem', md: '1.25rem' },
                  // 정사각형 비율에서 마진 줄이기
                  '@media (min-aspect-ratio: 9/16) and (max-aspect-ratio: 4/3)': {
                    mb: 1.5,
                    fontSize: '1.15rem',
                  }
                }}>
                  전 세계 정치인들이 이미 증명한 디지털 소통의 힘. 이제 대한민국 정치에서도 같은 성과를 거둘 때입니다.
                </Typography>
                <Typography variant="body1" sx={{
                  lineHeight: 1.8,
                  color: 'rgba(255,255,255,0.7)',
                  fontSize: { xs: '0.9rem', md: '1.0rem', lg: '1rem' } // 태블릿 사이즈 추가
                }}>
                  검색 노출부터 유권자 소통까지, 전략적 블로그 콘텐츠로 정치인의 인지도와 영향력을 높이세요.
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

          <Box sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: { xs: 2, md: 3 },
            justifyContent: 'center',
            alignItems: 'stretch',
            gridTemplateRows: '200px'
          }}>
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
              <Box key={index} sx={{ height: '100%' }}>
                <InViewFade timeout={600 + index * 100}>
                  <Card
                    sx={{
                      bgcolor: 'rgba(255,255,255,0.05)',
                      border: `2px solid ${rule.color}40`,
                      borderRadius: 3,
                      height: '200px',
                      display: 'flex',
                      flexDirection: 'column',
                      transition: 'all 0.3s ease',
                      '&:hover': {
                        borderColor: `${rule.color}80`,
                        transform: 'translateY(-4px)',
                        boxShadow: `0 8px 32px ${rule.color}20`
                      }
                    }}
                  >
                    <CardContent sx={{
                      p: { xs: 2, md: 4 },
                      textAlign: 'center',
                      flex: 1,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center'
                    }}>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          mb: { xs: 1, md: 2 },
                          color: rule.color,
                          fontSize: { xs: '0.9rem', sm: '1rem', md: '1.25rem' }
                        }}
                      >
                        {rule.title}
                      </Typography>
                      <Typography sx={{
                        lineHeight: 1.6,
                        fontSize: { xs: '0.75rem', sm: '0.85rem', md: '1rem' }
                      }}>
                        {rule.description}
                      </Typography>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Box>
            ))}
          </Box>
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
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: { xs: 2, md: 3 },
            alignItems: 'stretch',
            gridAutoRows: '1fr'
          }}>
            {[
              { icon: <FactCheckIcon />, label: '사실 검증' },
              { icon: <StyleIcon />, label: '톤앤매너' },
              { icon: <FormatListBulletedIcon />, label: '구조화' },
            ].map((it, i) => (
              <Box key={i} sx={{ height: '100%' }}>
                <CardSoft sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <CardContent sx={{
                    textAlign: 'center',
                    py: { xs: 3, md: 4 },
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center'
                  }}>
                    <Box sx={{
                      mb: 1.5,
                      '& svg': {
                        fontSize: { xs: 28, md: 32 },
                        color: '#00d4ff'
                      }
                    }}>{it.icon}</Box>
                    <Typography
                      variant="subtitle1"
                      sx={{
                        fontWeight: 700,
                        fontSize: { xs: '0.9rem', md: '1rem' }
                      }}
                    >{it.label}</Typography>
                  </CardContent>
                </CardSoft>
              </Box>
            ))}
          </Box>

          {/* 프로세스 플로우 */}
          <Box sx={{ mt: 6 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, textAlign: 'center' }}>
              4단계 검수 프로세스
            </Typography>
            <Grid container spacing={2}>
              {[
                { label: '초안', desc: '주제 입력' },
                { label: '검증', desc: '사실 확인' },
                { label: '교열', desc: '문체 조정' },
                { label: '발행', desc: '최종 게시' }
              ].map((step, i) => (
                <Grid item xs={6} md={3} key={step.label}>
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
                      <Typography sx={{ fontWeight: 700, fontSize: '0.9rem', mb: 0.5 }}>{step.label}</Typography>
                      <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>{step.desc}</Typography>
                    </CardContent>
                  </CardSoft>
                </Grid>
              ))}
            </Grid>
          </Box>
        </ContentContainer>
      </Section>

      {/* 첫 번째 섹션: 영향력 확장의 두 축 */}
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
              영향력 확장의 두 축
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)'
            }}>
              인바운드와 아웃바운드 마케팅으로 완전한 정치적 영향력을 구축하세요
            </Typography>
          </InViewFade>

          <InViewFade>
            <Grid container spacing={4} sx={{
              justifyContent: 'center',
              mb: 6,
              // 갤럭시 폴드 7 메인 디스플레이 그리드 최적화
              '@media (min-width: 1950px) and (min-height: 2150px)': {
                spacing: 6,
                mb: 8,
              },
              // 갤럭시 폴드 7 커버 디스플레이 그리드 최적화
              '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
                spacing: 2,
                mb: 4,
              }
            }}>
              {/* 찾아오는 신규 유권자 */}
              <Grid item xs={6}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  border: '1px solid #f8c02340',
                  display: 'flex',
                  flexDirection: 'column',
                  // 갤럭시 폴드 7 메인 디스플레이 카드 최적화
                  '@media (min-width: 1950px) and (min-height: 2150px)': {
                    padding: '2rem',
                    fontSize: '1.1rem',
                  },
                  // 갤럭시 폴드 7 커버 디스플레이 카드 최적화
                  '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
                    padding: '1rem',
                    fontSize: '0.9rem',
                  }
                }}>
                  <CardContent sx={{ p: 4, display: 'flex', flexDirection: 'column', flex: 1 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: '#f8c023', mb: 3 }}>
                      찾아오는 신규 유권자
                    </Typography>
                    <Typography variant="body1" sx={{ textAlign: 'left', lineHeight: 1.8, mb: 3 }}>
                      • 지역 현안 검색 → 전문가 블로그 발견<br/>
                      • 능동적 정보 탐색으로 높은 관여도<br/>
                      • 완전한 정책 설명에 논리적 설득<br/>
                      • 검색 유입으로 새로운 지지층 확장
                    </Typography>
                    <Box sx={{
                      p: 2,
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: 2,
                      border: '1px solid #f8c02340',
                      mt: 'auto'
                    }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, color: 'rgba(255,255,255,0.9)' }}>
                        자연스러운 발견을 통한 진정성 있는 소통
                      </Typography>
                    </Box>
                  </CardContent>
                </CardSoft>
              </Grid>

              {/* 찾아가는 기존 지지자 */}
              <Grid item xs={6}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  border: '1px solid #00d4ff40',
                  display: 'flex',
                  flexDirection: 'column',
                  // 갤럭시 폴드 7 메인 디스플레이 카드 최적화
                  '@media (min-width: 1950px) and (min-height: 2150px)': {
                    padding: '2rem',
                    fontSize: '1.1rem',
                  },
                  // 갤럭시 폴드 7 커버 디스플레이 카드 최적화
                  '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
                    padding: '1rem',
                    fontSize: '0.9rem',
                  }
                }}>
                  <CardContent sx={{ p: 4, display: 'flex', flexDirection: 'column', flex: 1 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: '#00d4ff', mb: 3 }}>
                      찾아가는 기존 지지자
                    </Typography>
                    <Typography variant="body1" sx={{ textAlign: 'left', lineHeight: 1.8, mb: 3 }}>
                      • 팔로우한 지지자에게 직접 전달<br/>
                      • 즉시 알림으로 빠른 반응 유도<br/>
                      • 좋아요, 공유로 확산 네트워크 가동<br/>
                      • 결집된 힘으로 여론 주도권 확보
                    </Typography>
                    <Box sx={{
                      p: 2,
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: 2,
                      border: '1px solid #00d4ff40',
                      mt: 'auto'
                    }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, color: 'rgba(255,255,255,0.9)' }}>
                        확실한 전달을 통한 즉각적 반응 유도
                      </Typography>
                    </Box>
                  </CardContent>
                </CardSoft>
              </Grid>
            </Grid>

            {/* 결론 메시지 */}
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h5" sx={{
                fontWeight: 700,
                color: 'rgba(255,255,255,0.9)',
                lineHeight: 1.6,
                p: 3,
                border: '2px solid rgba(255,255,255,0.2)',
                borderRadius: 2,
                backgroundColor: 'rgba(255,255,255,0.05)',
                maxWidth: 600,
                mx: 'auto'
              }}>
                신규 유입 + 기존 결집 = 정치적 영향력 확대
              </Typography>
            </Box>
          </InViewFade>
        </ContentContainer>
      </Section>

      {/* 두 번째 섹션: 이미 증명된 전략 */}
      <Section sx={{
        backgroundColor: 'rgba(0,0,0,0.02)',
        py: { xs: 6, md: 10 }
      }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 700,
              mb: 2,
              textAlign: 'center'
            }}>
              이미 증명된 전략
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)'
            }}>
              전문직들이 검증한 네이버 블로그 중심 마케팅 전략
            </Typography>
          </InViewFade>

          <InViewFade>
            <Grid container spacing={4} sx={{ justifyContent: 'center' }}>
              <Grid item xs={12} md={8}>
                <CardSoft sx={{ height: '100%' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Grid container spacing={4} alignItems="center">
                      {/* 왼쪽: 전문직 마케팅 사례 */}
                      <Grid item xs={12} md={6}>
                        <Typography variant="h5" sx={{
                          fontWeight: 700,
                          mb: 3,
                          color: '#00d4ff',
                          textAlign: 'center'
                        }}>
                          전문직 마케팅 사례
                        </Typography>

                        <Box sx={{ textAlign: 'left', mb: 3 }}>
                          <Typography variant="body1" sx={{ mb: 2, fontWeight: 600 }}>
                            • 의사, 변호사, 세무사
                          </Typography>
                          <Typography variant="body1" sx={{ mb: 2, fontWeight: 600 }}>
                            • 네이버 블로그 → SNS 허브 전략
                          </Typography>
                          <Typography variant="body1" sx={{ mb: 2, fontWeight: 600 }}>
                            • 검색 유입 → 고객 전환
                          </Typography>
                        </Box>

                        <Box sx={{
                          p: 3,
                          backgroundColor: 'rgba(255, 255, 255, 0.03)',
                          borderRadius: 2,
                          border: '1px solid #00d4ff40',
                          textAlign: 'center'
                        }}>
                          <Typography variant="body1" sx={{
                            fontWeight: 600
                          }}>
                            블로그 작성 → SNS 확산 → 유입 증가 → 성과 창출
                          </Typography>
                        </Box>
                      </Grid>

                      {/* 오른쪽: 동심원 SNS 다이어그램 */}
                      <Grid item xs={12} md={6}>
                        <Box sx={{
                          position: 'relative',
                          width: '300px',
                          height: '300px',
                          mx: 'auto'
                        }}>
                          {/* 동심원들 - SNS 아이콘이 원의 테두리에 걸치도록 조정 */}
                          <Box sx={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: '220px', // SNS 아이콘들이 테두리에 걸치도록
                            height: '220px',
                            borderRadius: '50%',
                            border: '2px solid rgba(0, 212, 255, 0.3)',
                            zIndex: 1
                          }} />
                          <Box sx={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: '140px',
                            height: '140px',
                            borderRadius: '50%',
                            border: '2px solid rgba(0, 212, 255, 0.4)',
                            zIndex: 2
                          }} />
                          <Box sx={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: '90px',
                            height: '90px',
                            borderRadius: '50%',
                            border: '2px solid rgba(0, 212, 255, 0.5)',
                            zIndex: 3
                          }} />

                          {/* 중앙 네이버 블로그 */}
                          <Box sx={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            zIndex: 10
                          }}>
                            <img
                              src="/icons/Nblog.webp"
                              alt="네이버 블로그"
                              style={{
                                width: 36,
                                height: 36,
                                filter: 'drop-shadow(0 0 8px rgba(248, 192, 35, 0.8)) drop-shadow(0 0 16px rgba(248, 192, 35, 0.4))',
                                transition: 'filter 0.3s ease'
                              }}
                            />
                          </Box>

                          {/* SNS 아이콘들 */}
                          {[
                            { angle: 23, icon: 'icon-facebook.png', name: '페이스북', radius: 110 },
                            { angle: 127, icon: 'icon-instagram.png', name: '인스타그램', radius: 70 },
                            { angle: 203, icon: 'icon-X.png', name: 'X(트위터)', radius: 110 },
                            { angle: 311, icon: 'icon-threads.png', name: '스레드', radius: 110 }
                          ].map((sns, index) => {
                            const radian = (sns.angle * Math.PI) / 180;
                            const x = Math.cos(radian) * sns.radius;
                            const y = Math.sin(radian) * sns.radius;

                            return (
                              <Box key={sns.name} sx={{
                                position: 'absolute',
                                top: '50%',
                                left: '50%',
                                transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
                                zIndex: 5
                              }}>
                                <img
                                  src={`/icons/${sns.icon}`}
                                  alt={sns.name}
                                  style={{
                                    width: 24,
                                    height: 24,
                                    filter: 'drop-shadow(0 0 6px rgba(0, 212, 255, 0.8)) drop-shadow(0 0 12px rgba(0, 212, 255, 0.4))',
                                    transition: 'filter 0.3s ease'
                                  }}
                                />
                              </Box>
                            );
                          })}
                        </Box>
                      </Grid>
                    </Grid>

                    <Typography variant="h6" sx={{
                      fontWeight: 600,
                      color: 'rgba(255,255,255,0.9)',
                      lineHeight: 1.6,
                      textAlign: 'center',
                      mt: 4
                    }}>
                      전문직도 선택한 검증된 전략을 정치에도 적용하세요
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
              border: '1px solid #f8c02340',
              borderRadius: 3,
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              maxWidth: 800,
              mx: 'auto',
              mt: 4
            }}>
              <Typography variant="h5" sx={{
                fontWeight: 900,
                mb: 2,
                color: '#f8c023'
              }}>
                네이버 블로그로 정치적 영향력 확대
              </Typography>
              <Typography variant="body1" sx={{
                color: 'rgba(255,255,255,0.9)',
                lineHeight: 1.8
              }}>
                검색 노출부터 유권자 소통까지, 전략적 블로그 콘텐츠로 정치인의 인지도와 영향력을 높이세요.
              </Typography>
            </Box>
          </InViewFade>
        </ContentContainer>
      </Section>

      {/* 텍스트 위주 vs 비텍스트 위주 매체 섹션 */}
      <Section sx={{
        backgroundColor: 'rgba(0,0,0,0.02)',
        py: { xs: 6, md: 10 }
      }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 700,
              mb: 2,
              textAlign: 'center'
            }}>
              텍스트 위주 vs 비텍스트 위주 매체
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)'
            }}>
              매체별 특성과 네이버 블로그의 차별화된 장점
            </Typography>
          </InViewFade>

          <InViewFade>
            <Grid container spacing={4} sx={{
              justifyContent: 'center',
              mb: 6,
              // 갤럭시 폴드 7 메인 디스플레이 그리드 최적화
              '@media (min-width: 1950px) and (min-height: 2150px)': {
                spacing: 6,
                mb: 8,
              },
              // 갤럭시 폴드 7 커버 디스플레이 그리드 최적화
              '@media (min-width: 1080px) and (max-width: 1080px) and (min-height: 2520px)': {
                spacing: 2,
                mb: 4,
              }
            }}>
              {/* 텍스트 위주 매체 */}
              <Grid item xs={6} sm={6} md={5}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  border: '1px solid #f8c02340'
                }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 3,
                      color: '#f8c023'
                    }}>
                      텍스트 위주 매체
                    </Typography>

                    <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }}>
                      <img
                        src="/icons/Nblog.webp"
                        alt="네이버 블로그"
                        style={{
                          height: '60px',
                          width: 'auto',
                          filter: 'drop-shadow(0 0 8px rgba(0, 212, 255, 0.6))'
                        }}
                      />
                    </Box>

                    <Typography variant="body1" sx={{
                      mb: 3,
                      lineHeight: 1.6,
                      color: 'rgba(255,255,255,0.9)'
                    }}>
                      깊이 있는 글 읽기를 기대하는 독자들에게<br />
                      논리적 설득과 완전한 메시지 전달 가능
                    </Typography>
                  </CardContent>
                </CardSoft>
              </Grid>

              {/* 비텍스트 위주 매체 */}
              <Grid item xs={6} sm={6} md={5}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  border: '1px solid #00d4ff40'
                }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 3,
                      color: '#00d4ff'
                    }}>
                      비텍스트 위주 매체
                    </Typography>

                    <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                      {/* 페이스북 */}
                      <Box>
                        <Box sx={{ mb: 1, display: 'flex', justifyContent: 'center' }}>
                          <img
                            src="/icons/icon-facebook.png"
                            alt="페이스북"
                            style={{
                              height: '40px',
                              width: 'auto',
                              filter: 'drop-shadow(0 0 8px rgba(0, 212, 255, 0.6))'
                            }}
                          />
                        </Box>
                        <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                          이미지/영상 + 간단한 텍스트
                        </Typography>
                      </Box>

                      {/* 인스타그램 */}
                      <Box>
                        <Box sx={{ mb: 1, display: 'flex', justifyContent: 'center' }}>
                          <img
                            src="/icons/icon-instagram.png"
                            alt="인스타그램"
                            style={{
                              height: '40px',
                              width: 'auto',
                              filter: 'drop-shadow(0 0 8px rgba(0, 212, 255, 0.6))'
                            }}
                          />
                        </Box>
                        <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                          시각적 콘텐츠 중심
                        </Typography>
                      </Box>

                      {/* X(트위터) */}
                      <Box>
                        <Box sx={{ mb: 1, display: 'flex', justifyContent: 'center' }}>
                          <img
                            src="/icons/icon-X.png"
                            alt="X(트위터)"
                            style={{
                              height: '40px',
                              width: 'auto',
                              filter: 'drop-shadow(0 0 8px rgba(0, 212, 255, 0.6))'
                            }}
                          />
                        </Box>
                        <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                          즉석 반응과 짧은 메시지
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </CardSoft>
              </Grid>
            </Grid>
          </InViewFade>

          {/* 네이버 블로그의 3가지 핵심 장점 */}
          <InViewFade>
            <Box sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 3,
              mb: 4,
              alignItems: 'stretch'
            }}>
              <Box sx={{
                p: { xs: 2, md: 3 },
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: 3,
                border: '1px solid #003a8740',
                textAlign: 'center',
                transition: 'all 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: '0 8px 32px #003a8730'
                }
              }}>
                <Typography variant="h6" sx={{
                  fontWeight: 700,
                  color: '#003a87',
                  mb: 2,
                  fontSize: { xs: '0.9rem', sm: '1rem', md: '1.25rem' }
                }}>
                  검색 우선 노출
                </Typography>
                <Typography variant="body1" sx={{
                  color: 'rgba(255,255,255,0.9)',
                  lineHeight: 1.6,
                  fontSize: { xs: '0.75rem', sm: '0.85rem', md: '1rem' }
                }}>
                  유권자가 찾을 때 가장 먼저 발견되는 콘텐츠로 첫인상을 좌우합니다
                </Typography>
              </Box>
              <Box sx={{
                p: { xs: 2, md: 3 },
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: 3,
                border: '1px solid #55207d40',
                textAlign: 'center',
                transition: 'all 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: '0 8px 32px #55207d30'
                }
              }}>
                <Typography variant="h6" sx={{
                  fontWeight: 700,
                  color: '#55207d',
                  mb: 2,
                  fontSize: { xs: '0.9rem', sm: '1rem', md: '1.25rem' }
                }}>
                  깊이 있는 설득력
                </Typography>
                <Typography variant="body1" sx={{
                  color: 'rgba(255,255,255,0.9)',
                  lineHeight: 1.6,
                  fontSize: { xs: '0.75rem', sm: '0.85rem', md: '1rem' }
                }}>
                  장문으로 논리적 설득이 가능하여 정책과 비전을 완전히 전달합니다
                </Typography>
              </Box>
              <Box sx={{
                p: { xs: 2, md: 3 },
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: 3,
                border: '1px solid #00626140',
                textAlign: 'center',
                transition: 'all 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: '0 8px 32px #00626130'
                }
              }}>
                <Typography variant="h6" sx={{
                  fontWeight: 700,
                  color: '#006261',
                  mb: 2,
                  fontSize: { xs: '0.9rem', sm: '1rem', md: '1.25rem' }
                }}>
                  전문 콘텐츠 준비
                </Typography>
                <Typography variant="body1" sx={{
                  color: 'rgba(255,255,255,0.9)',
                  lineHeight: 1.6,
                  fontSize: { xs: '0.75rem', sm: '0.85rem', md: '1rem' }
                }}>
                  체계적으로 정리된 전문 콘텐츠로 신뢰도와 전문성을 구축합니다
                </Typography>
              </Box>
            </Box>
          </InViewFade>

          {/* 결론 메시지 */}
          <InViewFade>
            <Box sx={{
              textAlign: 'center',
              p: 4,
              border: '1px solid #00d4ff40',
              borderRadius: 3,
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              maxWidth: 600,
              mx: 'auto'
            }}>
              <Typography variant="h5" sx={{
                fontWeight: 700,
                color: 'rgba(255,255,255,0.9)',
                lineHeight: 1.6
              }}>
                SNS 소통만으로는 한계 - 검색되는 순간이 결정적
              </Typography>
            </Box>
          </InViewFade>
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
                    p: { xs: 2, md: 3 },
                    textAlign: 'center',
                    maxWidth: '80%',
                    mx: 'auto'
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
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
                    체험판 제공
                  </Typography>
                  <Stack spacing={1.5}>
                    <Typography sx={{ fontSize: '0.9rem', display: 'flex', alignItems: 'center' }}>
                      <Box component="span" sx={{ color: '#00d4ff', mr: 1, fontWeight: 'bold' }}>✓</Box>
                      의정활동 콘텐츠 8편 자동 생성
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', display: 'flex', alignItems: 'center' }}>
                      <Box component="span" sx={{ color: '#00d4ff', mr: 1, fontWeight: 'bold' }}>✓</Box>
                      최대 31일 체험 기간 제공
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', display: 'flex', alignItems: 'center' }}>
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

          <Box sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: { xs: 2, md: 4 },
            justifyContent: 'center',
            alignItems: 'stretch'
          }}>
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
              <Box key={index}>
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
                    <CardContent sx={{ p: { xs: 2, md: 4 }, textAlign: 'center' }}>
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          mb: 1,
                          color: plan.color,
                          fontSize: { xs: '0.9rem', sm: '1.1rem', md: '1.25rem' }
                        }}
                      >
                        {plan.name}
                      </Typography>
                      <Typography
                        variant="h4"
                        sx={{
                          fontWeight: 900,
                          mb: 1,
                          fontSize: { xs: '1.2rem', sm: '1.5rem', md: '2rem' }
                        }}
                      >
                        {plan.price}
                      </Typography>
                      <Typography
                        sx={{
                          color: 'rgba(255,255,255,0.7)',
                          mb: { xs: 2, md: 4 },
                          fontSize: { xs: '0.75rem', sm: '0.85rem', md: '1rem' }
                        }}
                      >
                        {plan.description}
                      </Typography>
                      <Typography
                        variant="h3"
                        sx={{
                          fontWeight: 900,
                          mb: { xs: 2, md: 4 },
                          color: plan.color,
                          fontSize: { xs: '1.5rem', sm: '2rem', md: '2.5rem' }
                        }}
                      >
                        {plan.count}
                      </Typography>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Box>
            ))}
          </Box>

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
                  expanded={expandedFaq === `panel${i}`}
                  onChange={handleAccordionChange(`panel${i}`)}
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