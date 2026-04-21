// frontend/src/pages/AboutPage.jsx

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ThemeProvider } from '@mui/material/styles';
import createCustomTheme from '../theme';
import {
  Box,
  Container,
  Typography,
  Button,
  Grid,
  Card,
  CardContent,
  Dialog,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme,
  useMediaQuery
} from '@mui/material';
import {
  ExpandMore,
  Gavel,
  Fingerprint,
  AccountTree,
  EditNote,
  TrendingUp,
  Share,
  FactCheck,
  Security
} from '@mui/icons-material';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine
} from 'recharts';
import { BRANDING } from '../config/branding';

// MUI 레벨에서도 라이트 모드 강제
const lightTheme = createCustomTheme(false);

// Brand-tinted shadows
const brandShadow = '0 4px 16px rgba(21, 36, 132, 0.07)';
const brandShadowLg = '0 8px 32px rgba(21, 36, 132, 0.12)';

// Spring easing for hover transitions
const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

const AboutPage = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // CSS 변수를 라이트 모드로 강제
  useEffect(() => {
    const wasDarkMode = document.body.classList.contains('dark-mode');
    document.body.classList.remove('dark-mode');
    return () => {
      if (wasDarkMode) {
        document.body.classList.add('dark-mode');
      }
    };
  }, []);

  const [showAllFAQs, setShowAllFAQs] = useState(false);
  const [expandedFAQ, setExpandedFAQ] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState(null);

  // ── 성과 데이터 ───────────────────────────────────────────────
  const rawViewData = [
    { month: '25.03', total: 238, isAfterLaunch: false },
    { month: '25.04', total: 317, isAfterLaunch: false },
    { month: '25.05', total: 435, isAfterLaunch: false },
    { month: '25.06', total: 403, isAfterLaunch: false },
    { month: '25.07', total: 259, isAfterLaunch: false },
    { month: '25.08', total: 267, isAfterLaunch: false },
    { month: '25.09', total: 281, isAfterLaunch: false },
    { month: '25.10', total: 217, isAfterLaunch: false },
    { month: '25.11', total: 180, isAfterLaunch: false },
    { month: '25.12', total: 991, isAfterLaunch: true },
    { month: '26.01', total: 1500, isAfterLaunch: true },
    { month: '26.02', total: 1862, isAfterLaunch: true },
    { month: '26.03', total: 2061, isAfterLaunch: true }
  ];

  // 12월(after 첫 지점)을 before에도 브릿지 포인트로 넣어 회색 선이 11→12월까지 연결
  const chartData = rawViewData.map((item, idx, arr) => {
    const isFirstAfter = item.isAfterLaunch && idx > 0 && !arr[idx - 1].isAfterLaunch;
    return {
      month: item.month,
      before: !item.isAfterLaunch || isFirstAfter ? item.total : undefined,
      after: item.isAfterLaunch ? item.total : undefined
    };
  });

  const preLaunchData = rawViewData.filter((d) => !d.isAfterLaunch);
  const postLaunchData = rawViewData.filter((d) => d.isAfterLaunch);
  const preLaunchAverage = Math.round(
    preLaunchData.reduce((sum, d) => sum + d.total, 0) / preLaunchData.length
  );
  const postLaunchAverage = Math.round(
    postLaunchData.reduce((sum, d) => sum + d.total, 0) / postLaunchData.length
  );
  const growthMultiple = (postLaunchAverage / preLaunchAverage).toFixed(2);
  const postLaunchPeak = postLaunchData.reduce(
    (peak, d) => (d.total > peak.total ? d : peak),
    postLaunchData[0]
  );

  // ── FAQ ────────────────────────────────────────────────────────
  const handleFAQChange = (panel) => (event, isExpanded) => {
    setExpandedFAQ(isExpanded ? panel : false);
  };

  const handleCardKeyDown = (event, value) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setSelectedFeature(value);
    }
  };

  // ── 섹션 A: 정치인 전용 차별점 3개 ────────────────────────────
  const differentiators = [
    {
      icon: <Gavel aria-hidden="true" />,
      ariaLabel: '준법 가드레일 기능',
      title: '준법 가드레일',
      description: '허위사실·비방·기부행위 표현 자동 차단',
      modalTitle: '형사 리스크가 되는 표현을 AI가 미리 걸러냅니다.',
      details: `정치인의 온라인 콘텐츠에서 가장 위험한 것은
허위사실 공표, 후보자 비방, 기부행위 암시입니다.

${BRANDING.serviceName}은 글을 생성할 때부터 이런 표현을 회피하도록 설계되어 있고,
생성 후에도 출처 없는 수치, 간접 전언("~라는 소문"), 금품 제공 암시 등을
자동으로 탐지하여 수정합니다.

제목, 본문, SNS 변환본까지 전부 검사합니다.

의원님은 내용에만 집중하십시오.
법률 리스크는 AI가 먼저 잡아냅니다.`
    },
    {
      icon: <Fingerprint aria-hidden="true" />,
      ariaLabel: '문체 지문 학습 기능',
      title: '문체 지문 학습',
      description: '의원님의 글쓰기 패턴을 6차원 분석',
      modalTitle: '의원님이 쓴 글 몇 편이면 충분합니다. 문장의 결까지 AI가 따라 씁니다.',
      details: `평균 문장 길이, 격식의 정도, 자주 쓰는 전환 표현,
선호하는 종결 어미, 강조할 때의 수사법, 인사와 마무리 습관.

6개 차원의 문체 통계를 추출하고,
AI가 이를 해석하여 생성 제약조건으로 주입합니다.

쓸수록 정밀해집니다.
보좌진도 직접 쓴 글과 구분하기 어려워집니다.`
    },
    {
      icon: <AccountTree aria-hidden="true" />,
      ariaLabel: '장르별 구조 자동 선택 기능',
      title: '장르별 글 구조 자동 선택',
      description: '의정보고·정책제안·시사논평, 각각 다른 구조',
      modalTitle: '의정보고서와 축사는 다른 글입니다.\nAI가 주제를 인식하고 최적의 구조를 고릅니다.',
      details: `의정보고, 정책제안, 지역현안, 시사논평, 일상소통, 현장활동, 협치.
9개 장르 템플릿, 각 장르마다 4가지 이상의 서술 구조.

주제만 입력하면 AI가 장르를 자동 분류하고,
해당 장르에서 가장 효과적인 논리 전개와 수사 전략을 선택합니다.

같은 AI에서 나온 글이라도
의정보고서는 보고서답게, 논평은 논평답게 나옵니다.`
    }
  ];

  // ── 섹션 B: 기본기 2개 ────────────────────────────────────────
  const basics = [
    {
      icon: <EditNote aria-hidden="true" />,
      ariaLabel: '원고 생성 기능',
      title: '월 90회 원고 생성',
      description: '하루 3편, 쉬지 않는 콘텐츠',
      modalTitle: '한 달 90편. 매일 유권자와 만납니다.',
      details: `하루 3편. 일주일이면 21편. 한 달이면 90편.

침묵하는 동안, 상대 후보는 매일 유권자와 대화하고 있습니다.
"오늘 뭘 올리지?" 고민은 끝났습니다.

매일, 쉬지 않고. ${BRANDING.serviceShortName}은 24시간 대기 중입니다.`
    },
    {
      icon: <TrendingUp aria-hidden="true" />,
      ariaLabel: '검색·SNS 최적화 기능',
      title: '검색·SNS 5채널 최적화',
      description: '네이버 검색 + 인스타·페이스북·X·스레드',
      modalTitle: '블로그 하나로 다섯 채널.\n각 채널이 좋아하는 형태로 맞춰 줍니다.',
      details: `"우리 동네 의정활동"을 검색할 때,
가장 먼저 뜨는 이름은 누구입니까.

네이버 검색에 노출될 확률을 비약적으로 높여 줍니다.
제목·본문을 검색 알고리즘이 좋아하는 형태로 맞추고,
검색 노출 점수가 기준 이하면 AI가 알아서 고쳐서 내보냅니다.

블로그 원고 하나면 인스타그램, 페이스북, X, 스레드까지 자동 변환.
각 플랫폼의 글자 수 제한, 해시태그 규칙, 어투 차이를
AI가 이미 학습하고 있습니다.

승인 버튼만 누르면 됩니다.`
    }
  ];

  // ── FAQ ────────────────────────────────────────────────────────
  const allFAQs = [
    {
      id: 'faq-0',
      question: 'AI도 많은데 굳이 이걸 써야 하나요?',
      answer: '일반 AI는 빈 화면에서 글을 만들려 합니다. 전뇌비서관은 의원님이 직접 쓴 원문을 블로그·SNS 4채널에 맞게 다시 씁니다. 준법 가드레일, 의원님 문체 학습, 장르별 구조 선택, 채널별 노출 최적화까지 정치인 원문을 다루는 데 필요한 기능만 모았습니다.'
    },
    {
      id: 'faq-1',
      question: '지지 정당이 다른 사용자도 쓸 수 있나요?',
      answer: '현재는 더불어민주당 당원 전용 서비스로 운영됩니다. 서비스 이용에는 당원 인증(당적증명서, 당비납부 영수증)이 필요합니다.'
    },
    {
      id: 'faq-2',
      question: 'AI로 쓴 글을 선거 기간에 올려도 되나요?',
      answer: '생성된 원고는 초안이며, 최종 검수와 게시는 의원님 또는 보좌진의 판단입니다. 선거법 민감 표현은 AI가 1차 필터링하지만, 법적 책임은 게시자에게 있으므로 반드시 최종 확인 후 게시하시기 바랍니다.'
    },
    {
      id: 'faq-3',
      question: '월 90회면 충분한가요?',
      answer: '하루 3편 꼴로, 블로그와 SNS 포함하면 주 5~6일 꾸준히 포스팅 가능한 분량입니다.'
    },
    {
      id: 'faq-4',
      question: '검색 최적화는 어떻게 되나요?',
      answer: '네이버 검색에서 의원님 글이 노출될 확률을 비약적으로 높이고, SNS 변환 시에도 각 채널의 알고리즘·포맷에 맞춰 자동으로 최적화합니다. 기준 점수를 못 넘기면 AI가 알아서 고쳐서 내보냅니다.'
    },
    {
      id: 'faq-5',
      question: '내 데이터가 다른 사용자에게 공유되나요?',
      answer: '아닙니다. 문체 프로필, 생성 원고, 프로필 정보 모두 사용자별로 완전히 격리되어 저장됩니다. 다른 의원님의 AI와 섞이지 않습니다.'
    }
  ];

  const topFAQs = allFAQs.slice(0, 3);
  const moreFAQs = allFAQs.slice(3);
  const displayedFAQs = showAllFAQs ? allFAQs : topFAQs;

  // ── 숫자 표시용 스타일 ────────────────────────────────────────
  const numericStyle = { fontVariantNumeric: 'tabular-nums' };

  return (
    <ThemeProvider theme={lightTheme}>
      <Box sx={{ minHeight: '100dvh', bgcolor: 'var(--color-background)', position: 'relative' }}>

        {/* 상단 헤더 바 */}
        <Box component="nav" sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 300,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          px: { xs: 2, md: 4 },
          py: 2,
          bgcolor: 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(8px)',
          borderBottom: '1px solid var(--color-border)'
        }}>
          <Typography sx={{
            fontWeight: 700,
            fontSize: { xs: '1rem', md: '1.2rem' },
            color: 'var(--color-text-primary)'
          }}>
            {BRANDING.serviceName}
          </Typography>
          <Button
            onClick={() => navigate('/login')}
            sx={{
              color: 'var(--color-primary)',
              fontSize: '1rem',
              fontWeight: 600,
              textTransform: 'none',
              px: 3,
              py: 1,
              transition: springTransition,
              '&:hover': { bgcolor: 'var(--color-primary-lighter)' }
            }}
          >
            로그인
          </Button>
        </Box>

        <Box component="main">

          {/* ════════════════════════════════════════════════════════
              Hero Section
              ════════════════════════════════════════════════════════ */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <Box sx={{ position: 'relative', overflow: 'hidden' }}>
              {/* Decorative gradient blobs */}
              <Box sx={{
                position: 'absolute', top: '15%', right: '-5%',
                width: '45vw', height: '45vw', maxWidth: 550, maxHeight: 550,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(21,36,132,0.05) 0%, transparent 70%)',
                pointerEvents: 'none'
              }} />
              <Box sx={{
                position: 'absolute', bottom: '10%', left: '-8%',
                width: '35vw', height: '35vw', maxWidth: 400, maxHeight: 400,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(21,36,132,0.03) 0%, transparent 70%)',
                pointerEvents: 'none'
              }} />

              <Container
                maxWidth="md"
                sx={{
                  minHeight: '100dvh',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  alignItems: 'center',
                  textAlign: 'center',
                  py: 8,
                  pt: 12,
                  position: 'relative',
                  zIndex: 1
                }}
              >
                <Typography
                  sx={{
                    fontSize: { xs: '0.95rem', md: '1.15rem' },
                    fontWeight: 600,
                    color: 'var(--color-primary)',
                    mb: 3,
                    letterSpacing: '0.05em'
                  }}
                >
                  정치인이 직접 쓴 글, 다섯 채널로 퍼지게
                </Typography>

                <Typography
                  variant="h1"
                  sx={{
                    fontWeight: 700,
                    fontSize: { xs: '2.5rem', md: '4.5rem' },
                    mb: 4,
                    color: 'var(--color-text-primary)',
                    letterSpacing: '-0.02em',
                    lineHeight: 1.1,
                    wordBreak: 'keep-all',
                    textWrap: 'balance'
                  }}
                >
                  "의원님 덕분에<br />살기 좋은 동네가 됐어요."
                </Typography>

                <Typography
                  variant="h5"
                  sx={{
                    mb: 3,
                    color: 'var(--color-text-secondary)',
                    fontWeight: 400,
                    fontSize: { xs: '1.5rem', md: '2rem' },
                    lineHeight: 1.6,
                    wordBreak: 'keep-all',
                    textWrap: 'balance'
                  }}
                >
                  한 채널에만 올리면<br />이런 칭찬은 한 번밖에 못 듣습니다.
                </Typography>

                <Typography
                  sx={{
                    mb: 5,
                    color: 'var(--color-text-secondary)',
                    fontSize: { xs: '1rem', md: '1.2rem' },
                    lineHeight: 1.6,
                    wordBreak: 'keep-all'
                  }}
                >
                  의원님이 직접 쓴 주력 SNS 원문을
                  블로그·인스타·페이스북·X·스레드에 맞게 다시 써 드립니다.
                </Typography>

                {/* 가격 배지 */}
                <Box
                  sx={{
                    mb: 6,
                    px: { xs: 2.5, md: 3.5 },
                    py: { xs: 1.25, md: 1.75 },
                    borderRadius: 'var(--radius-md)',
                    border: '1.5px solid var(--color-primary)',
                    bgcolor: 'var(--color-primary-lighter)',
                    display: 'inline-flex',
                    flexWrap: 'wrap',
                    justifyContent: 'center',
                    alignItems: 'center',
                    gap: { xs: 1, md: 1.5 },
                    color: 'var(--color-primary)',
                    fontSize: { xs: '0.9rem', md: '1rem' },
                    fontWeight: 700,
                    ...numericStyle
                  }}
                >
                  <Box component="span">월 50,000원 (VAT 별도)</Box>
                  <Box component="span" sx={{ opacity: 0.45 }}>·</Box>
                  <Box component="span">월 90회 생성</Box>
                  <Box component="span" sx={{ opacity: 0.45 }}>·</Box>
                  <Box component="span">5채널 변환 무료</Box>
                </Box>

                <Box sx={{ display: 'flex', gap: 3, justifyContent: 'center', flexWrap: 'wrap' }}>
                  <Button
                    variant="contained"
                    size="large"
                    onClick={() => navigate('/login')}
                    sx={{
                      bgcolor: 'var(--color-primary)',
                      color: 'var(--color-text-inverse)',
                      fontSize: { xs: '1.1rem', sm: '1.3rem', md: '1.75rem' },
                      fontWeight: 700,
                      px: { xs: 4, sm: 6, md: 8 },
                      py: { xs: 2, sm: 2.5, md: 3 },
                      borderRadius: 'var(--radius-md)',
                      boxShadow: 'var(--shadow-md)',
                      textTransform: 'none',
                      transition: springTransition,
                      '&:hover': {
                        bgcolor: 'var(--color-primary-hover)',
                        boxShadow: 'var(--shadow-glow-primary)',
                        transform: 'scale(1.02)'
                      },
                      '&:active': { transform: 'scale(0.98)' },
                      '&:focus-visible': {
                        outline: '2px solid var(--color-text-inverse)',
                        outlineOffset: '2px'
                      }
                    }}
                  >
                    서비스 시작
                  </Button>

                  <Button
                    variant="outlined"
                    size="large"
                    onClick={() => window.scrollTo({ top: window.innerHeight, behavior: 'smooth' })}
                    sx={{
                      color: 'var(--color-primary)',
                      borderColor: 'var(--color-primary)',
                      borderWidth: 2,
                      fontSize: { xs: '1rem', sm: '1.2rem', md: '1.5rem' },
                      fontWeight: 600,
                      px: { xs: 3, sm: 4, md: 6 },
                      py: { xs: 1.5, sm: 2, md: 3 },
                      borderRadius: 'var(--radius-md)',
                      boxShadow: 'var(--shadow-sm)',
                      textTransform: 'none',
                      transition: springTransition,
                      '&:hover': {
                        borderWidth: 2,
                        borderColor: 'var(--color-primary)',
                        bgcolor: 'var(--color-primary-lighter)',
                        boxShadow: 'var(--shadow-md)'
                      },
                      '&:active': { transform: 'scale(0.98)' },
                      '&:focus-visible': {
                        outline: '2px solid var(--color-primary)',
                        outlineOffset: '2px'
                      }
                    }}
                  >
                    자세히 보기
                  </Button>
                </Box>
              </Container>
            </Box>
          </motion.div>

          {/* ════════════════════════════════════════════════════════
              문제 제기 섹션 — 채널별 재배포의 고통
              ════════════════════════════════════════════════════════ */}
          <Box sx={{ bgcolor: 'var(--color-surface)' }}>
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
            >
              <Container maxWidth="md" sx={{ py: { xs: 10, md: 14 } }}>
                <Typography
                  variant="h2"
                  sx={{
                    fontWeight: 700,
                    mb: 2,
                    textAlign: 'center',
                    color: 'var(--color-text-primary)',
                    fontSize: { xs: '2rem', md: '2.8rem' },
                    letterSpacing: '-0.02em',
                    wordBreak: 'keep-all',
                    textWrap: 'balance'
                  }}
                >
                  이미 쓰고 계십니다.<br />문제는 그다음입니다.
                </Typography>
                <Typography sx={{
                  mb: 6,
                  textAlign: 'center',
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', md: '1.125rem' },
                  lineHeight: 1.7,
                  wordBreak: 'keep-all'
                }}>
                  주력 SNS에는 직접 쓰십니다. 그런데 같은 메시지를 다른 채널에 올리는 일이 매번 일입니다.
                </Typography>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {[
                    '페이스북에 올린 긴 글, 블로그에 옮기기엔 구조가 맞지 않습니다.',
                    'X 길이에 맞추면 맥락이 잘리고, 블로그 길이에 맞추면 늘어집니다.',
                    '인스타는 문장 리듬과 감정 포인트가 다른 채널과 다릅니다.',
                    '같은 표현도 채널에 따라 더 공격적으로 읽힐 수 있습니다.'
                  ].map((text, index) => (
                    <Box
                      key={index}
                      sx={{
                        p: { xs: 2.5, md: 3 },
                        borderRadius: 'var(--radius-md)',
                        bgcolor: 'var(--color-background)',
                        border: '1px solid var(--color-border)',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 2
                      }}
                    >
                      <Box sx={{
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        bgcolor: 'var(--color-primary-lighter)',
                        color: 'var(--color-primary)',
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        fontSize: '0.95rem',
                        fontWeight: 700,
                        flexShrink: 0,
                        ...numericStyle
                      }}>
                        {index + 1}
                      </Box>
                      <Typography sx={{
                        color: 'var(--color-text-primary)',
                        fontSize: { xs: '1rem', md: '1.125rem' },
                        lineHeight: 1.7,
                        wordBreak: 'keep-all',
                        pt: 0.25
                      }}>
                        {text}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              해결 방식 섹션 — 변환(Converter) 흐름
              ════════════════════════════════════════════════════════ */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6 }}
          >
            <Container maxWidth="lg" sx={{ py: { xs: 10, md: 14 } }}>
              <Typography
                variant="h2"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  textAlign: 'center',
                  color: 'var(--color-text-primary)',
                  fontSize: { xs: '2rem', md: '2.8rem' },
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all',
                  textWrap: 'balance'
                }}
              >
                {BRANDING.serviceName}은 생각을 만들지 않습니다.
              </Typography>
              <Typography sx={{
                mb: 8,
                textAlign: 'center',
                color: 'var(--color-text-secondary)',
                fontSize: { xs: '1rem', md: '1.125rem' },
                lineHeight: 1.7,
                wordBreak: 'keep-all'
              }}>
                의원님이 직접 쓴 한 편을 받아, 다섯 채널에 맞게 다시 씁니다.
              </Typography>

              <Grid container spacing={3}>
                {[
                  {
                    icon: <EditNote aria-hidden="true" />,
                    step: '01',
                    title: '직접 쓴 원문 입력',
                    description: '주력 SNS에 올린 입장문·페이스북 글을 그대로 붙여넣습니다.'
                  },
                  {
                    icon: <Fingerprint aria-hidden="true" />,
                    step: '02',
                    title: '문체 지문 학습',
                    description: '의원님이 써 오신 문장의 결·어미·수사 습관을 6차원으로 분석합니다.'
                  },
                  {
                    icon: <Share aria-hidden="true" />,
                    step: '03',
                    title: '채널별 길이·리듬 변환',
                    description: '블로그는 늘리고, X는 압축하고, 인스타는 리듬을 맞춥니다.'
                  },
                  {
                    icon: <FactCheck aria-hidden="true" />,
                    step: '04',
                    title: '위험 표현 1차 점검',
                    description: '허위사실·비방·기부행위 암시를 채널별로 미리 걸러냅니다.'
                  }
                ].map((item, index) => (
                  <Grid item xs={12} sm={6} md={3} key={index}>
                    <motion.div
                      initial={{ opacity: 0, y: 24 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.5, delay: index * 0.1 }}
                      style={{ height: '100%' }}
                    >
                      <Box sx={{
                        p: { xs: 3, md: 3.5 },
                        height: '100%',
                        borderRadius: 'var(--radius-lg)',
                        bgcolor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        boxShadow: brandShadow
                      }}>
                        <Typography sx={{
                          color: 'var(--color-primary)',
                          fontSize: '0.85rem',
                          fontWeight: 700,
                          letterSpacing: '0.08em',
                          mb: 1.5,
                          ...numericStyle
                        }}>
                          STEP {item.step}
                        </Typography>
                        <Box sx={{
                          mb: 2,
                          '& .MuiSvgIcon-root': {
                            color: 'var(--color-primary)',
                            fontSize: 40
                          }
                        }}>
                          {item.icon}
                        </Box>
                        <Typography sx={{
                          fontWeight: 700,
                          mb: 1,
                          color: 'var(--color-text-primary)',
                          fontSize: { xs: '1.1rem', md: '1.2rem' },
                          wordBreak: 'keep-all'
                        }}>
                          {item.title}
                        </Typography>
                        <Typography sx={{
                          color: 'var(--color-text-secondary)',
                          fontSize: { xs: '0.95rem', md: '1rem' },
                          lineHeight: 1.65,
                          wordBreak: 'keep-all'
                        }}>
                          {item.description}
                        </Typography>
                      </Box>
                    </motion.div>
                  </Grid>
                ))}
              </Grid>
            </Container>
          </motion.div>

          {/* ════════════════════════════════════════════════════════
              산출물 섹션 — 입력 1건 → 5개 채널 결과물
              ════════════════════════════════════════════════════════ */}
          <Box sx={{ bgcolor: 'var(--color-surface)', borderTop: '1px solid var(--color-border)' }}>
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
            >
              <Container maxWidth="lg" sx={{ py: { xs: 10, md: 14 } }}>
                <Typography
                  variant="h2"
                  sx={{
                    fontWeight: 700,
                    mb: 2,
                    textAlign: 'center',
                    color: 'var(--color-text-primary)',
                    fontSize: { xs: '2rem', md: '2.8rem' },
                    letterSpacing: '-0.02em',
                    wordBreak: 'keep-all',
                    textWrap: 'balance'
                  }}
                >
                  입력 하나, 다섯 채널
                </Typography>
                <Typography sx={{
                  mb: 8,
                  textAlign: 'center',
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', md: '1.125rem' },
                  lineHeight: 1.7,
                  wordBreak: 'keep-all'
                }}>
                  직접 쓴 원문 하나를 넣으면, 다음 결과물이 한 번에 나옵니다.
                </Typography>

                <Grid container spacing={3} alignItems="stretch">
                  {/* 입력 카드 */}
                  <Grid item xs={12} md={4}>
                    <Box sx={{
                      p: { xs: 3, md: 4 },
                      height: '100%',
                      borderRadius: 'var(--radius-lg)',
                      bgcolor: 'var(--color-background)',
                      border: '2px dashed var(--color-primary)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center',
                      textAlign: 'center'
                    }}>
                      <Typography sx={{
                        color: 'var(--color-primary)',
                        fontSize: '0.85rem',
                        fontWeight: 700,
                        letterSpacing: '0.08em',
                        mb: 2
                      }}>
                        INPUT
                      </Typography>
                      <Typography sx={{
                        fontWeight: 700,
                        color: 'var(--color-text-primary)',
                        fontSize: { xs: '1.25rem', md: '1.4rem' },
                        mb: 1.5,
                        wordBreak: 'keep-all'
                      }}>
                        의원님이 직접 쓴<br />주력 SNS 원문 1건
                      </Typography>
                      <Typography sx={{
                        color: 'var(--color-text-secondary)',
                        fontSize: { xs: '0.95rem', md: '1rem' },
                        lineHeight: 1.7,
                        wordBreak: 'keep-all'
                      }}>
                        입장문, 페이스북 글,
                        현장 메모 어느 것이든 괜찮습니다.
                      </Typography>
                    </Box>
                  </Grid>

                  {/* 출력 카드 5개 */}
                  <Grid item xs={12} md={8}>
                    <Grid container spacing={2}>
                      {[
                        { label: '블로그', description: '구조를 갖춘 긴 호흡의 확장본' },
                        { label: '페이스북', description: '스크롤을 잡는 정리본' },
                        { label: '인스타그램', description: '캡션 리듬에 맞춘 짧은 변환' },
                        { label: 'X', description: '맥락을 지키면서 압축된 버전' },
                        { label: '스레드', description: '흐름형 연재에 맞춘 구성' },
                        { label: '위험 표현 점검', description: '채널별 선거법·표현 리스크 1차 필터' }
                      ].map((item, index) => (
                        <Grid item xs={12} sm={6} key={index}>
                          <Box sx={{
                            p: { xs: 2, md: 2.5 },
                            height: '100%',
                            borderRadius: 'var(--radius-md)',
                            bgcolor: 'var(--color-background)',
                            border: '1px solid var(--color-border)',
                            transition: springTransition,
                            '&:hover': {
                              borderColor: 'var(--color-primary)',
                              boxShadow: brandShadow
                            }
                          }}>
                            <Typography sx={{
                              fontWeight: 700,
                              color: 'var(--color-primary)',
                              fontSize: { xs: '0.95rem', md: '1rem' },
                              mb: 0.5
                            }}>
                              {item.label}
                            </Typography>
                            <Typography sx={{
                              color: 'var(--color-text-secondary)',
                              fontSize: { xs: '0.85rem', md: '0.9rem' },
                              lineHeight: 1.6,
                              wordBreak: 'keep-all'
                            }}>
                              {item.description}
                            </Typography>
                          </Box>
                        </Grid>
                      ))}
                    </Grid>
                  </Grid>
                </Grid>

                <Typography sx={{
                  mt: 4,
                  textAlign: 'center',
                  color: 'var(--color-text-secondary)',
                  fontSize: '0.9rem',
                  wordBreak: 'keep-all'
                }}>
                  월 90회 원고 생성 1회당 블로그 + SNS 4채널이 함께 제공됩니다. SNS 변환은 회차를 소진하지 않습니다.
                </Typography>
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              성과 그래프 섹션 — surface 배경
              ════════════════════════════════════════════════════════ */}
          <Box sx={{ bgcolor: 'var(--color-surface)' }}>
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
            >
              <Container maxWidth="lg" sx={{ py: { xs: 10, md: 14 } }}>
                <Box sx={{
                  p: { xs: 3, sm: 4, md: 6 },
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--color-border)',
                  bgcolor: 'var(--color-background)',
                  boxShadow: brandShadow
                }}>
                  <Box sx={{ mb: { xs: 4, md: 5 }, textAlign: 'center' }}>
                    <Typography
                      variant="h2"
                      sx={{
                        fontWeight: 700,
                        color: 'var(--color-text-primary)',
                        mb: 2,
                        fontSize: { xs: '2rem', md: '2.8rem' },
                        letterSpacing: '-0.02em',
                        wordBreak: 'keep-all',
                        textWrap: 'balance'
                      }}
                    >
                      도입 사례: 블로그 조회수 추이
                    </Typography>
                    <Typography sx={{
                      color: 'var(--color-text-secondary)',
                      fontSize: { xs: '1rem', md: '1.125rem' },
                      lineHeight: 1.7,
                      wordBreak: 'keep-all'
                    }}>
                      {BRANDING.serviceName}을 도입한 후보자 1인의 13개월 네이버 블로그 조회수 리포트입니다.
                    </Typography>
                    <Typography sx={{
                      mt: 0.75,
                      color: 'var(--color-text-secondary)',
                      fontSize: { xs: '0.9rem', md: '0.95rem' },
                      lineHeight: 1.6,
                      wordBreak: 'keep-all'
                    }}>
                      주제·지역·직위에 따라 결과는 달라질 수 있습니다.
                    </Typography>
                  </Box>

                  <Grid container spacing={3}>
                    <Grid item xs={12} md={8}>
                      <Box sx={{
                        height: { xs: 280, md: 360 },
                        p: { xs: 1.5, md: 2 },
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--color-border)',
                        bgcolor: 'var(--color-surface)'
                      }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={chartData} margin={{ top: 24, right: 12, left: 0, bottom: 8 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                            <XAxis
                              dataKey="month"
                              tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--color-border)' }}
                              interval={isMobile ? 1 : 0}
                            />
                            <YAxis
                              tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--color-border)' }}
                              tickFormatter={(value) => `${Math.round(value / 100) * 100}`}
                            />
                            <Tooltip
                              formatter={(value) => [`${Number(value).toLocaleString()}회`, '조회수']}
                              labelFormatter={(label) => `${label}`}
                              contentStyle={{
                                borderRadius: 'var(--radius-lg)',
                                border: '1px solid var(--color-border)',
                                backgroundColor: 'var(--color-surface)',
                                color: 'var(--color-text-primary)'
                              }}
                            />
                            <ReferenceLine
                              x="25.12"
                              stroke="var(--color-primary)"
                              strokeDasharray="4 4"
                              label={{
                                value: '도입 시점',
                                fill: 'var(--color-primary)',
                                position: 'insideTopRight',
                                fontSize: 12
                              }}
                            />
                            <Line
                              type="monotone"
                              dataKey="before"
                              stroke="var(--color-text-tertiary)"
                              strokeWidth={2}
                              dot={{ r: 3, fill: 'var(--color-text-tertiary)' }}
                              activeDot={{ r: 5, fill: 'var(--color-text-tertiary)' }}
                              connectNulls={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="after"
                              stroke="var(--color-primary)"
                              strokeWidth={3}
                              dot={{ r: 4, fill: 'var(--color-primary)' }}
                              activeDot={{ r: 6, fill: 'var(--color-primary)' }}
                              connectNulls={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </Box>
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <Grid container spacing={2}>
                        <Grid item xs={6} md={12}>
                          <Card elevation={0} sx={{
                            p: 2.5,
                            borderRadius: 'var(--radius-md)',
                            border: '1px dashed var(--color-border)',
                            bgcolor: 'var(--color-surface)',
                            minHeight: 132
                          }}>
                            <Typography sx={{ color: 'var(--color-text-secondary)', mb: 1, fontSize: '0.95rem' }}>
                              도입 전 월 평균
                            </Typography>
                            <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '1.55rem', fontWeight: 600, ...numericStyle }}>
                              {preLaunchAverage.toLocaleString()}회
                            </Typography>
                            <Typography sx={{ color: 'var(--color-text-secondary)', mt: 0.75, fontSize: '0.85rem' }}>
                              기준 구간 9개월
                            </Typography>
                          </Card>
                        </Grid>
                        <Grid item xs={6} md={12}>
                          <Card elevation={0} sx={{
                            p: 2.5,
                            borderRadius: 'var(--radius-md)',
                            border: '2px solid var(--color-primary)',
                            bgcolor: 'var(--color-surface)',
                            background: 'linear-gradient(135deg, var(--color-primary-lighter) 0%, var(--color-surface) 72%)',
                            boxShadow: 'var(--shadow-glow-primary)',
                            minHeight: 132
                          }}>
                            <Typography sx={{ color: 'var(--color-primary)', mb: 1, fontSize: '0.95rem', fontWeight: 700 }}>
                              도입 후 월 평균
                            </Typography>
                            <Typography sx={{
                              color: 'var(--color-primary)',
                              fontSize: { xs: '2.15rem', md: '2.55rem' },
                              fontWeight: 800,
                              lineHeight: 1,
                              ...numericStyle
                            }}>
                              {postLaunchAverage.toLocaleString()}회
                            </Typography>
                            <Typography sx={{ color: 'var(--color-text-secondary)', mt: 0.75, fontSize: '0.85rem' }}>
                              도입 후 4개월 평균
                            </Typography>
                          </Card>
                        </Grid>
                        <Grid item xs={12}>
                          <Card elevation={0} sx={{
                            p: 2.5,
                            borderRadius: 'var(--radius-md)',
                            border: '1px solid var(--color-primary)',
                            bgcolor: 'var(--color-primary-lighter)'
                          }}>
                            <Typography sx={{ color: 'var(--color-text-secondary)', mb: 1, fontSize: '0.95rem' }}>
                              도입 후 4개월 성과 (사례 기준)
                            </Typography>
                            <Typography sx={{
                              color: 'var(--color-primary)',
                              fontSize: { xs: '1.9rem', md: '2.2rem' },
                              fontWeight: 800,
                              lineHeight: 1.2,
                              ...numericStyle
                            }}>
                              월 평균 {growthMultiple}배
                            </Typography>
                            <Typography sx={{ color: 'var(--color-text-secondary)', mt: 1, fontSize: '0.95rem', ...numericStyle }}>
                              최고 {postLaunchPeak.total.toLocaleString()}회{' '}
                              <Typography component="span" sx={{ fontSize: '0.82em', color: 'var(--color-text-secondary)' }}>
                                ({postLaunchPeak.month})
                              </Typography>
                            </Typography>
                          </Card>
                        </Grid>
                      </Grid>
                    </Grid>
                  </Grid>

                  <Typography sx={{
                    mt: 3,
                    color: 'var(--color-text-secondary)',
                    fontSize: '0.9rem',
                    textAlign: 'right'
                  }}>
                    데이터 기준: 실 사용자 네이버 블로그 조회수 월간 리포트 (2025.03~2026.03)
                  </Typography>
                </Box>
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              섹션 A: 정치인 글쓰기는 다릅니다 — 3열 카드
              ════════════════════════════════════════════════════════ */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6 }}
          >
            <Container maxWidth="lg" sx={{ py: { xs: 10, md: 14 } }}>
              <Typography
                variant="h2"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  textAlign: 'center',
                  color: 'var(--color-text-primary)',
                  fontSize: { xs: '2rem', md: '2.8rem' },
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all',
                  textWrap: 'balance'
                }}
              >
                정치인 원문을 다루는 법은 다릅니다
              </Typography>
              <Typography sx={{
                mb: 8,
                textAlign: 'center',
                color: 'var(--color-text-secondary)',
                fontSize: { xs: '1rem', md: '1.125rem' },
                lineHeight: 1.7,
                wordBreak: 'keep-all'
              }}>
                일반 AI에는 없는, 정치 콘텐츠 변환에 특화된 설계.
              </Typography>

              <Grid container spacing={4}>
                {differentiators.map((value, index) => (
                  <Grid item xs={12} sm={4} key={index}>
                    <motion.div
                      initial={{ opacity: 0, y: 24 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.5, delay: index * 0.15 }}
                      style={{ height: '100%' }}
                    >
                      <Card
                        elevation={0}
                        onClick={() => setSelectedFeature(value)}
                        onKeyDown={(e) => handleCardKeyDown(e, value)}
                        tabIndex={0}
                        role="button"
                        aria-label={`${value.title} - ${value.description}. 클릭하여 자세히 보기`}
                        sx={{
                          textAlign: 'center',
                          p: { xs: 2, sm: 3, md: 4 },
                          height: '100%',
                          borderRadius: 'var(--radius-lg)',
                          bgcolor: 'var(--color-surface)',
                          border: '2px solid var(--color-border)',
                          boxShadow: brandShadow,
                          cursor: 'pointer',
                          transition: springTransition,
                          '&:hover, &:focus': {
                            borderColor: 'var(--color-primary)',
                            transform: 'translateY(-4px)',
                            boxShadow: brandShadowLg
                          },
                          '&:focus-visible': {
                            outline: '2px solid var(--color-primary)',
                            outlineOffset: '2px'
                          }
                        }}
                      >
                        <CardContent>
                          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                            <Box sx={{
                              width: { xs: 50, sm: 60, md: 80 },
                              height: { xs: 50, sm: 60, md: 80 },
                              display: 'flex',
                              justifyContent: 'center',
                              alignItems: 'center',
                              '& .MuiSvgIcon-root': {
                                color: 'var(--color-primary)',
                                fontSize: { xs: 40, sm: 50, md: 64 }
                              }
                            }}>
                              {value.icon}
                            </Box>
                          </Box>
                          <Typography
                            variant="h4"
                            sx={{
                              fontWeight: 700,
                              mb: 1.5,
                              color: 'var(--color-text-primary)',
                              fontSize: { xs: '1.1rem', sm: '1.4rem', md: '1.8rem', lg: '2rem' },
                              lineHeight: 1.3,
                              wordBreak: 'keep-all'
                            }}
                          >
                            {value.title}
                          </Typography>
                          <Typography
                            variant="body1"
                            sx={{
                              color: 'var(--color-text-secondary)',
                              fontSize: { xs: '0.85rem', sm: '0.95rem', md: '1.05rem', lg: '1.15rem' },
                              fontWeight: 400,
                              lineHeight: 1.5,
                              wordBreak: 'keep-all'
                            }}
                          >
                            {value.description}
                          </Typography>
                        </CardContent>
                      </Card>
                    </motion.div>
                  </Grid>
                ))}
              </Grid>
            </Container>
          </motion.div>

          {/* ════════════════════════════════════════════════════════
              섹션 B: 기본기도 탄탄합니다 — surface 배경
              ════════════════════════════════════════════════════════ */}
          <Box sx={{ bgcolor: 'var(--color-surface)' }}>
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
            >
              <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
                <Typography
                  variant="h2"
                  sx={{
                    fontWeight: 700,
                    mb: 2,
                    textAlign: 'center',
                    color: 'var(--color-text-primary)',
                    fontSize: { xs: '2rem', md: '2.8rem' },
                    letterSpacing: '-0.02em',
                    wordBreak: 'keep-all',
                    textWrap: 'balance'
                  }}
                >
                  기본기도 탄탄합니다
                </Typography>
                <Typography sx={{
                  mb: 8,
                  textAlign: 'center',
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', md: '1.125rem' },
                  lineHeight: 1.7,
                  wordBreak: 'keep-all'
                }}>
                  매일의 콘텐츠 운영을 지탱하는 실무 기능.
                </Typography>
                <Grid container spacing={3} justifyContent="center">
                  {basics.map((value, index) => (
                    <Grid item xs={6} key={index}>
                      <motion.div
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.5, delay: index * 0.12 }}
                        style={{ height: '100%' }}
                      >
                        <Card
                          elevation={0}
                          onClick={() => setSelectedFeature(value)}
                          onKeyDown={(e) => handleCardKeyDown(e, value)}
                          tabIndex={0}
                          role="button"
                          aria-label={`${value.title} - ${value.description}. 클릭하여 자세히 보기`}
                          sx={{
                            textAlign: 'center',
                            p: { xs: 1, sm: 1.5, md: 3 },
                            height: '100%',
                            borderRadius: 'var(--radius-lg)',
                            bgcolor: 'var(--color-background)',
                            border: '1px solid var(--color-border)',
                            boxShadow: brandShadow,
                            transition: springTransition,
                            cursor: 'pointer',
                            '&:hover, &:focus': {
                              borderColor: 'var(--color-primary)',
                              transform: 'translateY(-4px)',
                              boxShadow: brandShadowLg
                            },
                            '&:focus-visible': {
                              outline: '2px solid var(--color-primary)',
                              outlineOffset: '2px'
                            }
                          }}
                        >
                          <CardContent>
                            <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                              <Box sx={{
                                width: 64,
                                height: 64,
                                display: 'flex',
                                justifyContent: 'center',
                                alignItems: 'center',
                                '& .MuiSvgIcon-root': {
                                  color: 'var(--color-primary)',
                                  fontSize: 48
                                }
                              }}>
                                {value.icon}
                              </Box>
                            </Box>
                            <Typography
                              variant="h4"
                              sx={{
                                fontWeight: 700,
                                mb: 1.5,
                                color: 'var(--color-text-primary)',
                                fontSize: { xs: '1rem', sm: '1.2rem', md: '1.5rem', lg: '1.6rem' },
                                lineHeight: 1.3,
                                wordBreak: 'keep-all'
                              }}
                            >
                              {value.title}
                            </Typography>
                            <Typography
                              variant="body1"
                              sx={{
                                color: 'var(--color-text-secondary)',
                                fontSize: { xs: '0.8rem', sm: '0.9rem', md: '1rem' },
                                fontWeight: 400,
                                lineHeight: 1.5,
                                wordBreak: 'keep-all'
                              }}
                            >
                              {value.description}
                            </Typography>
                          </CardContent>
                        </Card>
                      </motion.div>
                    </Grid>
                  ))}
                </Grid>
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              섹션 C: 안심 설계
              ════════════════════════════════════════════════════════ */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6 }}
          >
            <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
              <Grid container spacing={4}>
                <Grid item xs={12} md={6}>
                  <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.5 }}
                    style={{ height: '100%' }}
                  >
                    <Box sx={{
                      p: { xs: 3, md: 4 },
                      borderRadius: 'var(--radius-lg)',
                      border: '1px solid var(--color-border)',
                      bgcolor: 'var(--color-surface)',
                      boxShadow: brandShadow,
                      height: '100%',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 2.5
                    }}>
                      <FactCheck sx={{ color: 'var(--color-primary)', fontSize: 36, flexShrink: 0, mt: 0.5 }} />
                      <Box>
                        <Typography sx={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--color-text-primary)', mb: 1 }}>
                          10단계 품질 검수
                        </Typography>
                        <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '0.95rem', lineHeight: 1.7 }}>
                          의원님 문체로 쓰고, 법률 위험 표현을 걸러내고,
                          검색·SNS 노출까지. 문제가 있으면 AI가 직접 고칩니다.
                        </Typography>
                      </Box>
                    </Box>
                  </motion.div>
                </Grid>
                <Grid item xs={12} md={6}>
                  <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.5, delay: 0.12 }}
                    style={{ height: '100%' }}
                  >
                    <Box sx={{
                      p: { xs: 3, md: 4 },
                      borderRadius: 'var(--radius-lg)',
                      border: '1px solid var(--color-border)',
                      bgcolor: 'var(--color-surface)',
                      boxShadow: brandShadow,
                      height: '100%',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 2.5
                    }}>
                      <Security sx={{ color: 'var(--color-primary)', fontSize: 36, flexShrink: 0, mt: 0.5 }} />
                      <Box>
                        <Typography sx={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--color-text-primary)', mb: 1 }}>
                          데이터 완전 격리
                        </Typography>
                        <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '0.95rem', lineHeight: 1.7 }}>
                          문체 프로필, 생성 원고, 프로필 정보 모두 사용자별 별도 저장.
                          다른 의원님의 AI와 절대 섞이지 않습니다.
                        </Typography>
                      </Box>
                    </Box>
                  </motion.div>
                </Grid>
              </Grid>
            </Container>
          </motion.div>

          {/* 기능 상세 모달 */}
          <Dialog
            open={!!selectedFeature}
            onClose={() => setSelectedFeature(null)}
            maxWidth="sm"
            fullWidth
            aria-labelledby="feature-dialog-title"
            aria-describedby="feature-dialog-description"
            sx={{ '& .MuiDialog-paper': { borderRadius: 'var(--radius-lg)', p: 2 } }}
          >
            {selectedFeature && (
              <>
                <Box sx={{ p: 3, textAlign: 'center' }}>
                  <Box sx={{ mb: 3, display: 'flex', justifyContent: 'center' }}>
                    {React.cloneElement(selectedFeature.icon, {
                      sx: { fontSize: 80, color: 'var(--color-primary)' }
                    })}
                  </Box>
                  <Typography
                    id="feature-dialog-title"
                    variant="h5"
                    sx={{
                      fontWeight: 700,
                      mb: 3,
                      color: 'var(--color-text-primary)',
                      wordBreak: 'keep-all',
                      whiteSpace: 'pre-line'
                    }}
                  >
                    {selectedFeature.modalTitle}
                  </Typography>
                  <Typography
                    id="feature-dialog-description"
                    variant="body1"
                    sx={{
                      color: 'var(--color-text-secondary)',
                      lineHeight: 1.8,
                      whiteSpace: 'pre-line',
                      wordBreak: 'keep-all',
                      fontSize: '1.1rem'
                    }}
                  >
                    {selectedFeature.details}
                  </Typography>
                </Box>
                <Box sx={{ p: 2, pt: 0, textAlign: 'center' }}>
                  <Button
                    onClick={() => setSelectedFeature(null)}
                    variant="outlined"
                    size="large"
                    sx={{
                      color: 'var(--color-primary)',
                      borderColor: 'var(--color-primary)',
                      borderRadius: 'var(--radius-md)',
                      px: 4,
                      transition: springTransition,
                      '&:hover': {
                        borderColor: 'var(--color-primary)',
                        bgcolor: 'var(--color-primary-lighter)'
                      }
                    }}
                  >
                    닫기
                  </Button>
                </Box>
              </>
            )}
          </Dialog>

          {/* ════════════════════════════════════════════════════════
              FAQ 섹션 — surface 배경
              ════════════════════════════════════════════════════════ */}
          <Box sx={{ bgcolor: 'var(--color-surface)' }}>
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
            >
              <Container maxWidth="md" sx={{ py: 20 }}>
                <Typography
                  variant="h2"
                  sx={{
                    fontWeight: 700,
                    mb: 8,
                    textAlign: 'center',
                    color: 'var(--color-text-primary)',
                    fontSize: { xs: '2.5rem', md: '3rem' },
                    letterSpacing: '-0.02em',
                    textWrap: 'balance'
                  }}
                >
                  자주 묻는 질문
                </Typography>

                {displayedFAQs.map((faq, index) => (
                  <motion.div
                    key={faq.id}
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.4, delay: index * 0.08 }}
                  >
                    <Accordion
                      expanded={expandedFAQ === faq.id}
                      onChange={handleFAQChange(faq.id)}
                      elevation={0}
                      sx={{
                        mb: 2,
                        borderRadius: 'var(--radius-md)',
                        bgcolor: 'var(--color-background)',
                        border: '1px solid var(--color-border)',
                        borderTop: expandedFAQ === faq.id ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                        boxShadow: 'none',
                        transition: 'all var(--transition-normal)',
                        '&:before': { display: 'none' },
                        '&:first-of-type': { borderRadius: 'var(--radius-md)' },
                        '&:last-of-type': { borderRadius: 'var(--radius-md)' },
                        '&.Mui-expanded': { margin: '0 0 16px 0' },
                        '&:hover': { borderColor: 'var(--color-primary)' }
                      }}
                    >
                      <AccordionSummary
                        expandIcon={<ExpandMore sx={{ color: 'var(--color-primary)' }} />}
                        sx={{ py: 3, px: 4 }}
                      >
                        <Typography sx={{ fontWeight: 600, fontSize: '1.25rem', color: 'var(--color-text-primary)' }}>
                          {faq.question}
                        </Typography>
                      </AccordionSummary>
                      <AccordionDetails sx={{ px: 4, py: 3, bgcolor: 'var(--color-background)' }}>
                        <Typography sx={{
                          color: 'var(--color-text-secondary)',
                          fontSize: '1.125rem',
                          lineHeight: 1.8
                        }}>
                          {faq.answer}
                        </Typography>
                      </AccordionDetails>
                    </Accordion>
                  </motion.div>
                ))}

                {moreFAQs.length > 0 && (
                  <Box sx={{ textAlign: 'center', mt: 8 }}>
                    <Button
                      variant="outlined"
                      size="large"
                      onClick={() => setShowAllFAQs(!showAllFAQs)}
                      sx={{
                        color: 'var(--color-primary)',
                        borderColor: 'var(--color-primary)',
                        borderWidth: 2,
                        fontSize: '1.125rem',
                        fontWeight: 600,
                        px: 6,
                        py: 2,
                        borderRadius: 'var(--radius-md)',
                        textTransform: 'none',
                        transition: springTransition,
                        '&:hover': {
                          borderWidth: 2,
                          borderColor: 'var(--color-primary)',
                          bgcolor: 'var(--color-primary-lighter)'
                        },
                        '&:focus-visible': {
                          outline: '2px solid var(--color-primary)',
                          outlineOffset: '2px'
                        }
                      }}
                      aria-expanded={showAllFAQs}
                      aria-controls="faq-list"
                    >
                      {showAllFAQs ? '질문 접기' : `더 많은 질문 보기 (${moreFAQs.length}개)`}
                    </Button>
                  </Box>
                )}
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              가격 섹션
              ════════════════════════════════════════════════════════ */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6 }}
          >
            <Container maxWidth="sm" sx={{ py: 20 }}>
              <Typography
                variant="h2"
                sx={{
                  fontWeight: 700,
                  mb: 2,
                  textAlign: 'center',
                  color: 'var(--color-text-primary)',
                  fontSize: { xs: '1.75rem', md: '2.4rem' },
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all',
                  textWrap: 'balance'
                }}
              >
                생각은 직접 쓰고,<br />확산은 {BRANDING.serviceName}으로.
              </Typography>
              <Typography sx={{
                mb: 6,
                textAlign: 'center',
                color: 'var(--color-text-secondary)',
                fontSize: { xs: '1rem', md: '1.125rem' },
                lineHeight: 1.7,
                wordBreak: 'keep-all'
              }}>
                주력 SNS에 올린 원문 한 편을 다섯 채널에 맞게 다시 씁니다. 위험 표현은 미리 점검합니다.
              </Typography>

              <Card
                elevation={0}
                sx={{
                  textAlign: 'center',
                  p: { xs: 4, sm: 6, md: 8 },
                  borderRadius: 'var(--radius-lg)',
                  bgcolor: 'var(--color-background)',
                  border: '3px solid var(--color-primary)',
                  boxShadow: brandShadowLg
                }}
              >
                <CardContent>
                  <Box sx={{ mb: 5 }}>
                    <Typography
                      variant="h1"
                      component="div"
                      sx={{
                        fontWeight: 700,
                        color: 'var(--color-text-tertiary)',
                        fontSize: 'clamp(1.6rem, 7vw, 3.5rem)',
                        letterSpacing: '-0.03em',
                        lineHeight: 1,
                        mb: 1,
                        whiteSpace: 'nowrap',
                        textDecoration: 'line-through',
                        ...numericStyle
                      }}
                    >
                      월 50,000원
                    </Typography>
                    <Typography sx={{
                      color: 'var(--color-text-tertiary)',
                      fontSize: '1rem',
                      fontWeight: 400,
                      textDecoration: 'line-through',
                      mb: 3
                    }}>
                      (VAT 별도)
                    </Typography>
                    <Typography
                      variant="h2"
                      component="div"
                      sx={{
                        fontWeight: 800,
                        color: 'var(--color-primary)',
                        fontSize: 'clamp(1.8rem, 8vw, 3.5rem)',
                        letterSpacing: '-0.02em',
                        lineHeight: 1.2,
                        wordBreak: 'keep-all',
                        mb: 3
                      }}
                    >
                      무료 체험 기간
                    </Typography>

                    <Box sx={{
                      mt: 3,
                      textAlign: 'left',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 1.25,
                      maxWidth: 360,
                      mx: 'auto'
                    }}>
                      {[
                        '월 90회 원고 생성',
                        '블로그 + SNS 4채널 변환 무료',
                        '위험 표현 1차 점검',
                        '의원님 문체 학습 및 유지'
                      ].map((feature, index) => (
                        <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                          <Box sx={{
                            width: 20,
                            height: 20,
                            borderRadius: '50%',
                            bgcolor: 'var(--color-primary-lighter)',
                            color: 'var(--color-primary)',
                            display: 'flex',
                            justifyContent: 'center',
                            alignItems: 'center',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            flexShrink: 0
                          }}>
                            ✓
                          </Box>
                          <Typography sx={{
                            color: 'var(--color-text-primary)',
                            fontSize: { xs: '0.95rem', md: '1rem' },
                            lineHeight: 1.6,
                            wordBreak: 'keep-all'
                          }}>
                            {feature}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </Box>
                  <Button
                    variant="contained"
                    size="large"
                    fullWidth
                    onClick={() => navigate('/login')}
                    sx={{
                      bgcolor: 'var(--color-primary)',
                      color: 'var(--color-text-inverse)',
                      fontSize: { xs: '1rem', sm: '1.2rem', md: '1.5rem' },
                      fontWeight: 700,
                      py: { xs: 2, sm: 2.5, md: 3 },
                      borderRadius: 'var(--radius-md)',
                      boxShadow: 'var(--shadow-md)',
                      textTransform: 'none',
                      transition: springTransition,
                      '&:hover': {
                        bgcolor: 'var(--color-primary-hover)',
                        boxShadow: 'var(--shadow-glow-primary)',
                        transform: 'scale(1.02)'
                      },
                      '&:active': { transform: 'scale(0.98)' },
                      '&:focus-visible': {
                        outline: '2px solid var(--color-text-inverse)',
                        outlineOffset: '2px'
                      }
                    }}
                  >
                    서비스 신청
                  </Button>
                </CardContent>
              </Card>
            </Container>
          </motion.div>

        </Box>

        {/* Footer */}
        <Box
          component="footer"
          sx={{
            py: 6,
            px: 2,
            bgcolor: 'var(--color-surface)',
            color: 'var(--color-text-secondary)',
            textAlign: 'center',
            mt: 12,
            borderTop: '1px solid var(--color-border)'
          }}
        >
          <Typography variant="body2" sx={{ lineHeight: 2, fontSize: '0.95rem' }}>
            {BRANDING.companyNameKo} | 사업자등록번호: 256-24-02174 | 통신판매업신고번호: (비움)<br />
            대표: 강정구 | 인천광역시 계양구 용종로 124, 학마을한진아파트 139동 1504호 | 대표번호: 010-4885-6206<br />
            Copyright 2025. {BRANDING.companyNameEn}. All Rights Reserved.
          </Typography>
        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default AboutPage;
