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

const FEATURES = [
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
    title: '법적 안전성 가이드라인',
    desc: '단정적 표현을 회피하고 의견과 사실을 구분하여 법적 리스크를 최소화합니다. 정치인에게 중요한 표현 안전성을 확보할 수 있습니다.',
  },
  {
    title: '할루시네이션 방지 시스템',
    desc: 'AI가 사실을 지어내지 않도록 원칙적 제한을 적용합니다. 근거 없는 통계나 추측성 내용을 배제하여 신뢰성을 유지합니다.',
  },
  {
    title: '시간 절약 자동화',
    desc: '매일 1-2시간씩 소요되던 콘텐츠 작성을 5분으로 단축할 수 있습니다. 본업인 정책과 현장활동에 집중할 수 있습니다.',
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
    image: '/sns/leejm_x.png',
    impact: '디지털 소통의 새로운 기준',
    color: '#4267B2'
  },
  {
    id: 2,
    title: '트럼프',
    subtitle: 'X(트위터) 정치 혁명',
    description: '전통 미디어를 뛰어넘어 트위터 직접 소통으로 대통령에 당선된 최초 사례.',
    image: '/sns/trump_x.png',
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
    a: '최소한의 필수 정보만 수집하며, 모든 데이터는 AES-256 암호화로 저장됩니다. 개인정보보호법과 정치자금법을 완전히 준수하며, 제3자와 데이터를 공유하지 않습니다. 정기적인 보안 감사를 통해 안전성을 유지합니다.',
  },
  {
    q: '당적 인증은 어떻게 이루어지나요?',
    a: '더불어민주당 당원 인증은 당원번호와 신분증을 통해 진행됩니다. 인증 정보는 90일마다 재확인하며, 당적이 확인되지 않으면 서비스 이용이 제한됩니다. 당원 정보는 당 본부와의 연동을 통해 실시간으로 검증합니다.',
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
    q: '지역구 독점 정책은 어떻게 운영되나요?',
    a: '동일 지역구(국회의원 선거구 기준) 내에는 1인만 서비스를 이용할 수 있습니다. 선착순으로 지역구를 확보하며, 계약 종료 시에만 해당 지역구가 다시 개방됩니다. 이를 통해 지역 내 독점적 디지털 우위를 확보할 수 있습니다.',
  },
];

// GlobalAuthorityCaseContainer 컴포넌트 - GSAP ScrollTrigger 패럴랙스
const GlobalAuthorityCaseContainer = ({ scrollerEl }) => {
  const containerRef = useRef(null);
  const leeRef = useRef(null);
  const trumpRef = useRef(null);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el || !leeRef.current || !trumpRef.current) return;

    // 모바일 감지
    const isMobile = window.innerWidth <= 768;

    gsap.set(leeRef.current,   { opacity: 1, scale: 1 });
    gsap.set(trumpRef.current, { opacity: 0, scale: 0.95 });

    if (!isMobile) {
      // 데스크톱: 단순하게 LEE 카드만 먼저 보이도록
      gsap.set(leeRef.current, { opacity: 1, scale: 1 });
      gsap.set(trumpRef.current, { opacity: 0, scale: 0.95 });

      // LEE 카드를 스크롤 중간에 페이드아웃
      gsap.to(leeRef.current, {
        opacity: 0,
        scale: 0.9,
        scrollTrigger: {
          trigger: el,
          scroller: scrollerEl || undefined,
          start: 'center center',
          end: 'bottom center',
          scrub: 1
        }
      });

      // TRUMP 카드를 스크롤 중간부터 페이드인
      gsap.fromTo(trumpRef.current,
        { opacity: 0, scale: 0.9 },
        {
          opacity: 1,
          scale: 1,
          scrollTrigger: {
            trigger: el,
            scroller: scrollerEl || undefined,
            start: 'center center',
            end: 'bottom center',
            scrub: 1
          }
        }
      );
    } else {
      // 모바일: 순차적 스크롤 애니메이션
      gsap.fromTo(leeRef.current,
        { opacity: 0, scale: 0.9 },
        {
          opacity: 1,
          scale: 1,
          scrollTrigger: {
            trigger: el,
            scroller: scrollerEl || undefined,
            start: 'top 80%',
            end: 'center center',
            scrub: 1
          }
        }
      );

      gsap.to(leeRef.current, {
        opacity: 0,
        scale: 0.9,
        scrollTrigger: {
          trigger: el,
          scroller: scrollerEl || undefined,
          start: 'center center',
          end: 'bottom 30%',
          scrub: 1
        }
      });

      gsap.fromTo(trumpRef.current,
        { opacity: 0, scale: 0.9 },
        {
          opacity: 1,
          scale: 1,
          scrollTrigger: {
            trigger: el,
            scroller: scrollerEl || undefined,
            start: 'center center',
            end: 'bottom 20%',
            scrub: 1
          }
        }
      );
    }

    // 이미지 지연 로드 대응
    const onImg = () => ScrollTrigger.refresh();
    el.querySelectorAll('img').forEach(img => { if (!img.complete) img.addEventListener('load', onImg); });

    return () => {
      el.querySelectorAll('img').forEach(img => img.removeEventListener('load', onImg));
      ScrollTrigger.getAll().forEach(st => st.kill());
    };
  }, [scrollerEl]);

  return (
    <Box
      ref={containerRef}
      sx={{
        position: 'relative',
        height: '100%', // 부모 높이에 맞춤 (모바일: 50vh, 데스크톱: 100vh)
        width: '100%',
        display: 'grid',
        placeItems: 'center',
        overflow: 'hidden'
      }}
    >
      {[GLOBAL_AUTHORITY_CASES[0], GLOBAL_AUTHORITY_CASES[1]].map((c, i) => (
        <Box key={c.id} ref={i === 0 ? leeRef : trumpRef}
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            px: { xs: 2, md: 4 }
          }}
        >
          <Box component="img"
               src={c.image}
               alt={c.title}
               sx={{
                 maxWidth: { xs: 400, md: 500 },
                 width: '100%',
                 height: 'auto',
                 borderRadius: 2,
                 border: '1px solid rgba(255,255,255,0.1)'
               }} />
        </Box>
      ))}
    </Box>
  );
};

// 글로벌 사례 섹션 - 전체 pin 적용
const GlobalCasesSection = ({ pageRef }) => {
  const sectionRef = useRef(null);
  const textRef = useRef(null);

  useLayoutEffect(() => {
    const section = sectionRef.current;
    const text = textRef.current;
    if (!section || !text) return;

    const isMobile = window.innerWidth <= 768;

    if (!isMobile) {
      // 데스크톱: 전체 섹션 pin + 텍스트 애니메이션
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: section,
          scroller: pageRef.current || undefined,
          start: 'top top',
          end: '+=200%',
          pin: true,
          scrub: 1,
          anticipatePin: 1,
        }
      });

      // 텍스트를 스크롤 진행률에 따라 이동
      tl.fromTo(text,
        { y: 0 },
        { y: '-50vh', duration: 1 }
      );
    }

    return () => {
      ScrollTrigger.getAll().forEach(st => {
        if (st.trigger === section) st.kill();
      });
    };
  }, [pageRef]);

  return (
    <Section ref={sectionRef} sx={{
      backgroundColor: 'rgba(21, 36, 132, 0.08)',
      py: { xs: 6, md: 10 },
      minHeight: '200vh',
      borderTop: '1px solid rgba(0, 212, 255, 0.2)',
      position: 'relative',
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
          height: { xs: '100vh', md: 'auto' }
        }}>
          <Grid item xs={12} md={6} sx={{
            order: { xs: 1, md: 1 },
            height: { xs: '50vh', md: 'auto' },
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
            height: { xs: '50vh', md: 'auto' },
            display: 'flex',
            alignItems: { xs: 'center', md: 'flex-start' }
          }}>
            <Box ref={textRef} sx={{
              position: 'relative',
              width: '100%',
              px: { xs: 2, md: 0 },
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: { xs: 'center', md: 'flex-start' },
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
    <Box ref={textRef} sx={{
      px: { xs: 2, md: 0 },
      py: 4,
      minHeight: '100vh', // 충분한 높이 확보
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
  scrollSnapType: 'y mandatory',
  overflowY: 'scroll',
  height: '100vh',
  '& *': {
    color: '#fff !important',
  },
  '& .MuiTypography-root': {
    color: '#fff !important',
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

const HeroRoot = styled('header')({
  position: 'relative',
  height: '100vh', // 정확히 전체 화면 높이로 고정
  display: 'grid',
  placeItems: 'center',
  overflow: 'hidden',
  borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
  scrollSnapAlign: 'start',
});

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
});

const CardEmphasis = styled(Card)({
  backgroundColor: 'rgba(0, 212, 255, 0.10)',
  borderRadius: 16,
  border: '1px solid rgba(0, 212, 255, 0.25)',
  backdropFilter: 'blur(6px)',
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
                fontSize: { xs: 'clamp(32px, 8vw, 48px)', md: 'clamp(48px, 6vw, 64px)' },
                mb: 2,
                whiteSpace: { xs: 'normal', md: 'nowrap' },
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
                mb: 4,
                fontSize: { xs: '1.25rem', md: '1.5rem' },
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

            {/* 민주당 전용 서비스 배지 */}
            <Box sx={{
              display: 'flex',
              justifyContent: 'center',
              gap: 2,
              mt: 4,
              flexWrap: 'wrap'
            }}>
              <Chip
                label="민주당 당원 전용"
                sx={{
                  backgroundColor: 'rgba(0, 212, 255, 0.15)',
                  color: '#00d4ff',
                  border: '1px solid rgba(0, 212, 255, 0.3)',
                  fontWeight: 600,
                  '&:hover': {
                    backgroundColor: 'rgba(0, 212, 255, 0.25)'
                  }
                }}
              />
              <Chip
                label="선거법 준수"
                sx={{
                  backgroundColor: 'rgba(76, 175, 80, 0.15)',
                  color: '#4caf50',
                  border: '1px solid rgba(76, 175, 80, 0.3)',
                  fontWeight: 600,
                  '&:hover': {
                    backgroundColor: 'rgba(76, 175, 80, 0.25)'
                  }
                }}
              />
            </Box>

          </InViewFade>
        </HeroContent>
      </HeroRoot>

      {/* 섹션 구분선 */}
      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* 글로벌 사례 - 패럴랙스 */}
      <Section sx={{
        backgroundColor: 'rgba(21, 36, 132, 0.08)',
        py: { xs: 6, md: 10 },
        borderTop: '1px solid rgba(0, 212, 255, 0.2)',
        position: 'relative',
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
          <Grid container spacing={4}>
            {/* 좌측: 카드만 pin */}
            <Grid item xs={12} md={6} sx={{
              order: { xs: 1, md: 1 },
              position: 'relative',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              overflow: 'hidden'
            }}>
              <GlobalAuthorityCaseContainer scrollerEl={pageRef.current} />
            </Grid>

            {/* 우측: 텍스트 */}
            <Grid item xs={12} md={6} sx={{ order: { xs: 2, md: 2 } }}>
              <RightTextContainer pageRef={pageRef} />
            </Grid>
          </Grid>
        </ContentContainer>
      </Section>

      {/* Features */}
      <Section id="how" aria-labelledby="features-heading">
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="features-heading" variant="h4" sx={{ fontWeight: 800, mb: 6 }}>
              전자두뇌비서관을 고려해야 하는 이유
            </Typography>
          </InViewFade>
          <Grid container spacing={3}>
            {FEATURES.map((f, idx) => (
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

      {/* 생성 규칙 */}
      <Section sx={{ backgroundColor: 'rgba(255,255,255,0.02)' }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{ fontWeight: 800, mb: 2, textAlign: 'center' }}>
              서비스 이용 규칙
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 6, textAlign: 'center' }}>
              효율적인 콘텐츠 생성을 위한 제한사항입니다.
            </Typography>
          </InViewFade>

          <Grid container spacing={3} justifyContent="center">
            {[
              {
                title: '1회 = 1원고',
                description: '한 번의 요청으로 하나의 완성된 원고를 생성합니다.',
                color: '#00d4ff'
              },
              {
                title: '최대 3회 재생성',
                description: '동일한 주제에 대해 최대 3번까지 다른 버전을 생성할 수 있습니다.',
                color: '#ff6b6b'
              },
              {
                title: '동시 노출 3개 제한',
                description: '화면에는 최대 3개의 원고 미리보기만 표시됩니다.',
                color: '#4ecdc4'
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
          <Box sx={{ mt: 6, display: 'flex', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
            {['초안', '검증', '교열', '발행'].map((step, i) => (
              <CardSoft key={step} sx={{ flex: '1 1 200px' }}>
                <CardContent sx={{ py: 3, textAlign: 'center' }}>
                  <Box sx={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    mx: 'auto',
                    mb: 1.5,
                    border: '1px solid rgba(255,255,255,0.25)',
                    display: 'grid',
                    placeItems: 'center',
                    fontSize: 14,
                    color: 'rgba(255,255,255,0.85)'
                  }}>{i + 1}</Box>
                  <Typography sx={{ fontWeight: 700 }}>{step}</Typography>
                </CardContent>
              </CardSoft>
            ))}
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
              정치적 소통 방식 비교
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 500,
              color: 'rgba(255,255,255,0.7)'
            }}>
              SNS 소통만으로는 한계가 있습니다. 검색되는 순간이 중요합니다.
            </Typography>
          </InViewFade>

          <InViewFade>
            <Box sx={{
              maxWidth: 800,
              mx: 'auto',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '8px',
              overflow: 'hidden'
            }}>
              {/* 테이블 헤더 */}
              <Grid container>
                <Grid item xs={12} md={6} sx={{
                  borderBottom: '1px solid rgba(255,255,255,0.08)',
                  borderRight: { md: '1px solid rgba(255,255,255,0.08)' }
                }}>
                  <Box sx={{ p: 3, textAlign: 'center' }}>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      전통적 SNS 소통
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)', mt: 1 }}>
                      페이스북, 인스타그램
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={6} sx={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <Box sx={{ p: 3, textAlign: 'center' }}>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      검색 기반 소통
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)', mt: 1 }}>
                      네이버 블로그
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              {/* 테이블 내용 */}
              <Grid container>
                <Grid item xs={12} md={6} sx={{
                  borderRight: { md: '1px solid rgba(255,255,255,0.08)' },
                  borderBottom: '1px solid rgba(255,255,255,0.08)'
                }}>
                  <Box sx={{ p: 3 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: 'rgba(255,255,255,0.9)' }}>
                      특징
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', lineHeight: 1.6, color: 'rgba(255,255,255,0.8)' }}>
                      • 좋아요, 댓글 중심<br />
                      • 팔로워 대상 소통<br />
                      • 일시적 노출<br />
                      • 검색 노출 제한적
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={6} sx={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <Box sx={{ p: 3 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: 'rgba(255,255,255,0.9)' }}>
                      특징
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', lineHeight: 1.6, color: 'rgba(255,255,255,0.8)' }}>
                      • 검색 최적화<br />
                      • 불특정 다수 접근<br />
                      • 지속적 노출<br />
                      • 지역 키워드 활용
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              <Grid container>
                <Grid item xs={12} md={6} sx={{ borderRight: { md: '1px solid rgba(255,255,255,0.08)' } }}>
                  <Box sx={{ p: 3 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: 'rgba(255,255,255,0.9)' }}>
                      결과
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.7)', fontStyle: 'italic' }}>
"소통은 되지만 발견이 어려움"
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Box sx={{ p: 3 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: 'rgba(255,255,255,0.9)' }}>
                      결과
                    </Typography>
                    <Typography sx={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.7)', fontStyle: 'italic' }}>
                      "검색하는 순간 발견 가능"
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
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
        py: { xs: 4, md: 6 },
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        textAlign: 'center'
      }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Box
              sx={{
                backgroundColor: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '16px',
                backdropFilter: 'blur(6px)',
                p: 4,
                mb: 6,
                maxWidth: 800,
                mx: 'auto'
              }}
            >
              <Box
                component="img"
                src="/sns/jeongcr_news.png"
                alt="정청래 대표 SNS 공천 필수화 발언"
                sx={{
                  maxWidth: '100%',
                  width: '400px',
                  height: 'auto',
                  borderRadius: '8px',
                  mb: 3
                }}
              />
              <Typography
                variant="h5"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  fontSize: { xs: '1.3rem', md: '1.5rem' }
                }}
              >
                정청래 대표 발언
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 600,
                  mb: 3,
                  fontSize: { xs: '1.1rem', md: '1.2rem' },
                  fontStyle: 'italic'
                }}
              >
                "SNS 활동, 공천 평가에 반영"
              </Typography>
              <Typography variant="body1" sx={{ lineHeight: 1.6, mb: 2, fontSize: '1rem' }}>
                민주당은 공천 심사에서 온라인 활동을 평가 지표로 검토하고 있습니다.
              </Typography>
              <Typography variant="caption" sx={{
                fontSize: '0.85rem',
                opacity: 0.7
              }}>
                정청래 대표의 실제 발언 내용
              </Typography>
            </Box>

            <Typography variant="body1" sx={{ lineHeight: 1.8, color: 'rgba(255,255,255,0.8)', mb: 4, maxWidth: 900, mx: 'auto', fontSize: '1.1rem' }}>
              검색과 SNS에서 의원 이름이 보이지 않으면 유권자가 확인하기 어렵습니다.
              <br /><br />
              준비는 미룰 수 없습니다.
            </Typography>

            {/* Trial Information */}
            <Box sx={{
              borderTop: '1px solid rgba(255,255,255,0.1)',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              py: 4,
              my: 4,
              maxWidth: 600,
              mx: 'auto'
            }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 3, textAlign: 'center' }}>
                체험판 제공
              </Typography>
              <Stack spacing={2} sx={{ mb: 4 }}>
                <Typography sx={{ fontSize: '1rem', textAlign: 'center' }}>
                  • 의정활동 콘텐츠 8편 자동 생성
                </Typography>
                <Typography sx={{ fontSize: '1rem', textAlign: 'center' }}>
                  • 효과 확인 후 이용 여부 결정
                </Typography>
                <Typography sx={{ fontSize: '1rem', textAlign: 'center' }}>
                  • 언제든 중단 가능
                </Typography>
              </Stack>
            </Box>

            <CTAButton
              size="large"
              onClick={handlePrimaryCTA}
              sx={{
                fontSize: '1.1rem',
                px: 5,
                py: 1.5
              }}
            >
              준비 시작
            </CTAButton>
          </InViewFade>
        </ContentContainer>
      </Section>

      {/* 로드맵 */}
      <Section sx={{ backgroundColor: 'rgba(0,0,0,0.03)' }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{ fontWeight: 800, mb: 2, textAlign: 'center' }}>
              개발 로드맵
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 6, textAlign: 'center' }}>
              더 강력한 기능들이 단계적으로 출시됩니다.
            </Typography>
          </InViewFade>

          <Grid container spacing={4}>
            {[
              {
                phase: 'Phase 2',
                title: 'RAG 시스템',
                description: '실시간 뉴스와 정책 데이터를 활용한 더 정확한 콘텐츠 생성',
                timeline: '2025 Q2',
                status: '개발중',
                color: '#00d4ff'
              },
              {
                phase: 'Phase 3',
                title: '워드프레스 자동발행',
                description: '생성된 콘텐츠를 블로그에 자동으로 발행하는 기능',
                timeline: '2025 Q3',
                status: '예정',
                color: '#ff6b6b'
              },
              {
                phase: 'Phase 4',
                title: 'AEO/GEO 최적화',
                description: 'AI 엔진 최적화와 검색 엔진 최적화 고도화',
                timeline: '2025 Q4',
                status: '계획중',
                color: '#4ecdc4'
              }
            ].map((item, index) => (
              <Grid item xs={12} md={4} key={index}>
                <InViewFade timeout={600 + index * 100}>
                  <Card
                    sx={{
                      bgcolor: 'rgba(255,255,255,0.05)',
                      border: `1px solid ${item.color}40`,
                      borderRadius: 3,
                      height: '100%',
                      transition: 'all 0.3s ease',
                      position: 'relative',
                      overflow: 'visible',
                      '&:hover': {
                        borderColor: `${item.color}80`,
                        transform: 'translateY(-8px)',
                        boxShadow: `0 12px 40px ${item.color}20`
                      }
                    }}
                  >
                    <Box
                      sx={{
                        position: 'absolute',
                        top: -12,
                        right: 16,
                        backgroundColor: item.color,
                        color: 'black',
                        px: 2,
                        py: 0.5,
                        borderRadius: 2,
                        fontSize: '0.75rem',
                        fontWeight: 700
                      }}
                    >
                      {item.status}
                    </Box>
                    <CardContent sx={{ p: 4 }}>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          color: item.color,
                          fontWeight: 600,
                          mb: 1
                        }}
                      >
                        {item.phase}
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          mb: 2
                        }}
                      >
                        {item.title}
                      </Typography>
                      <Typography
                        sx={{
                          lineHeight: 1.6,
                          mb: 3,
                          color: 'rgba(255,255,255,0.8)'
                        }}
                      >
                        {item.description}
                      </Typography>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          color: 'rgba(255,255,255,0.6)',
                          fontWeight: 600
                        }}
                      >
                        📅 {item.timeline}
                      </Typography>
                    </CardContent>
                  </Card>
                </InViewFade>
              </Grid>
            ))}
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
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', mb: 6, textAlign: 'center' }}>
              지역구 독점 운영으로 효과적인 정치 마케팅을 지원합니다.
            </Typography>
          </InViewFade>

          <Grid container spacing={4} justifyContent="center">
            {[
              {
                name: '베이직',
                price: '월 29만원',
                description: '개인 의원 1명',
                features: [
                  '월 30개 원고 생성',
                  '기본 SEO 최적화',
                  '법적 안전성 검토',
                  '이메일 지원'
                ],
                color: '#4caf50',
                popular: false
              },
              {
                name: '스탠다드',
                price: '월 59만원',
                description: '보좌관 포함 운영',
                features: [
                  '월 100개 원고 생성',
                  '고급 SEO 최적화',
                  '실시간 법적 검토',
                  '우선 지원 서비스',
                  '커스텀 톤앤매너'
                ],
                color: '#00d4ff',
                popular: true
              },
              {
                name: '프리미엄',
                price: '월 99만원',
                description: '당 지역위원회',
                features: [
                  '무제한 원고 생성',
                  '전문가 SEO 컨설팅',
                  '24시간 법적 모니터링',
                  '전담 매니저 지원',
                  '멀티 플랫폼 연동',
                  '성과 분석 리포트'
                ],
                color: '#ff6b6b',
                popular: false
              }
            ].map((plan, index) => (
              <Grid item xs={12} md={4} key={index}>
                <InViewFade timeout={600 + index * 100}>
                  <Card
                    sx={{
                      bgcolor: plan.popular ? 'rgba(0, 212, 255, 0.1)' : 'rgba(255,255,255,0.05)',
                      border: plan.popular ? `2px solid ${plan.color}` : `1px solid ${plan.color}40`,
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
                    {plan.popular && (
                      <Box
                        sx={{
                          position: 'absolute',
                          top: -12,
                          left: '50%',
                          transform: 'translateX(-50%)',
                          backgroundColor: plan.color,
                          color: 'black',
                          px: 3,
                          py: 0.5,
                          borderRadius: 3,
                          fontSize: '0.75rem',
                          fontWeight: 700
                        }}
                      >
                        POPULAR
                      </Box>
                    )}
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
                      <Stack spacing={2} sx={{ mb: 4 }}>
                        {plan.features.map((feature, idx) => (
                          <Typography
                            key={idx}
                            sx={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.9rem'
                            }}
                          >
                            <Box
                              component="span"
                              sx={{
                                color: plan.color,
                                mr: 1,
                                fontWeight: 'bold'
                              }}
                            >
                              ✓
                            </Box>
                            {feature}
                          </Typography>
                        ))}
                      </Stack>
                      <Button
                        variant={plan.popular ? 'contained' : 'outlined'}
                        sx={{
                          backgroundColor: plan.popular ? plan.color : 'transparent',
                          borderColor: plan.color,
                          color: plan.popular ? 'black' : plan.color,
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
                  color: '#ffc107'
                }}
              >
                🏛️ 지역구 독점 정책
              </Typography>
              <Typography sx={{ lineHeight: 1.6 }}>
                동일 지역구 내에는 1인만 서비스를 이용할 수 있습니다.
                <br />
                선착순으로 지역구를 확보하여 독점적인 디지털 우위를 점하세요.
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