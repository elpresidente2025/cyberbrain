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
    { month: '26.02', total: 1862, isAfterLaunch: true }
  ];

  const chartData = rawViewData.map((item) => ({
    month: item.month,
    before: !item.isAfterLaunch ? item.total : undefined,
    after: item.isAfterLaunch ? item.total : undefined
  }));

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
      ariaLabel: '선거법 자동 검수 기능',
      title: '선거법 3단계 자동 검수',
      description: '예비후보·본후보·현역별 준법 검사',
      modalTitle: '예비후보·본후보·현역, 단계별로 다른 선거법. 쓰는 단어 하나까지 AI가 걸러냅니다.',
      details: `공직선거법은 선거 단계마다 허용 표현이 다릅니다.
예비후보 등록 전에 "당선되면"이라고 쓰면 사전선거운동.
본후보 등록 후에 "약속드립니다"의 범위도 달라집니다.

${BRANDING.serviceName}은 100개 이상의 위반 표현 패턴을 단계별로 구분하여 자동 검수합니다.
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
      modalTitle: '의정보고서와 축사는 다른 글입니다. AI가 주제를 인식하고 최적의 구조를 고릅니다.',
      details: `의정보고, 정책제안, 지역현안, 시사논평, 일상소통, 현장활동, 협치.
9개 장르 템플릿, 각 장르마다 4가지 이상의 서술 구조.

주제만 입력하면 AI가 장르를 자동 분류하고,
해당 장르에서 가장 효과적인 논리 전개와 수사 전략을 선택합니다.

같은 AI에서 나온 글이라도
의정보고서는 보고서답게, 논평은 논평답게 나옵니다.`
    }
  ];

  // ── 섹션 B: 기본기 3개 ────────────────────────────────────────
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
      ariaLabel: '검색 최적화 기능',
      title: '네이버 검색 최적화',
      description: '유권자가 먼저 찾아오는 구조',
      modalTitle: '검색 1페이지. 유권자가 먼저 찾아옵니다.',
      details: `"우리 동네 의정활동"을 검색할 때,
가장 먼저 뜨는 이름은 누구입니까.

네이버 검색 알고리즘이 선호하는 키워드 배치,
소제목 구조, 본문 길이를 자동으로 적용합니다.

SEO 점수 기준을 통과해야 최종 원고가 완성됩니다.`
    },
    {
      icon: <Share aria-hidden="true" />,
      ariaLabel: 'SNS 변환 기능',
      title: '블로그 → SNS 4채널 변환',
      description: '인스타·페이스북·X·스레드',
      modalTitle: '한 편의 원고로 네 개의 채널을.',
      details: `블로그 원고 하나면 충분합니다.
인스타그램, 페이스북, X(트위터), 스레드까지 자동 변환.

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
      answer: '일반 AI와 달리 정치 콘텐츠에 특화되어 있습니다. 선거법 3단계 자동 검수, 의원님 문체 학습, 장르별 구조 선택, 네이버 검색 최적화까지 정치인에게 필요한 기능만 모았습니다.'
    },
    {
      id: 'faq-1',
      question: '지지 정당이 다른 사용자도 쓸 수 있나요?',
      answer: '현재는 더불어민주당 당원을 대상으로 먼저 서비스를 시작하고 있습니다. 타 정당 지원은 순차적으로 검토하고 있습니다. 당원 인증(당적증명서, 당비납부 영수증)이 필요합니다.'
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
      answer: '네이버 검색 알고리즘에 최적화된 키워드 배치, 소제목 구조, 본문 길이로 자동 작성됩니다. SEO 점수 기준을 통과해야 최종 원고가 완성됩니다.'
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
                  정치인 전용 블로그·SNS 원고 AI
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
                  홍보하지 않으면<br />이런 말도 못 듣습니다.
                </Typography>

                <Typography
                  sx={{
                    mb: 8,
                    color: 'var(--color-text-secondary)',
                    fontSize: { xs: '1rem', md: '1.2rem' },
                    lineHeight: 1.6,
                    wordBreak: 'keep-all'
                  }}
                >
                  블로그 한 편으로 인스타·페이스북·X·스레드까지. 월 90회 생성.
                </Typography>

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
                    서비스 시작하기
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
                      {BRANDING.serviceName}을 도입한 후보자 1인의 12개월 네이버 블로그 조회수 리포트입니다.
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
                                borderRadius: '12px',
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
                              stroke="var(--color-text-secondary)"
                              strokeWidth={2}
                              dot={{ r: 3, fill: 'var(--color-text-secondary)' }}
                              activeDot={{ r: 5, fill: 'var(--color-text-secondary)' }}
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
                              도입 후 3개월 평균
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
                              도입 후 3개월 성과 (사례 기준)
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
                    데이터 기준: 실 사용자 네이버 블로그 조회수 월간 리포트 (2025.03~2026.02)
                  </Typography>
                </Box>
              </Container>
            </motion.div>
          </Box>

          {/* ════════════════════════════════════════════════════════
              섹션 A: 정치인 글쓰기는 다릅니다 — zig-zag 레이아웃
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
                정치인 글쓰기는 다릅니다
              </Typography>
              <Typography sx={{
                mb: { xs: 6, md: 10 },
                textAlign: 'center',
                color: 'var(--color-text-secondary)',
                fontSize: { xs: '1rem', md: '1.125rem' },
                lineHeight: 1.7,
                wordBreak: 'keep-all'
              }}>
                일반 AI에는 없는, 정치 콘텐츠 전용 기능.
              </Typography>

              {differentiators.map((value, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: index * 0.15 }}
                >
                  <Box
                    onClick={() => setSelectedFeature(value)}
                    onKeyDown={(e) => handleCardKeyDown(e, value)}
                    tabIndex={0}
                    role="button"
                    aria-label={`${value.title} - ${value.description}. 클릭하여 자세히 보기`}
                    sx={{
                      mb: index < 2 ? { xs: 4, md: 6 } : 0,
                      p: { xs: 3, md: 5 },
                      borderRadius: 'var(--radius-lg)',
                      border: '1px solid var(--color-border)',
                      bgcolor: 'var(--color-surface)',
                      boxShadow: brandShadow,
                      cursor: 'pointer',
                      transition: springTransition,
                      '&:hover': {
                        borderColor: 'var(--color-primary)',
                        boxShadow: brandShadowLg,
                        transform: 'translateY(-2px)'
                      },
                      '&:focus-visible': {
                        outline: '2px solid var(--color-primary)',
                        outlineOffset: '2px'
                      }
                    }}
                  >
                    <Grid
                      container
                      spacing={{ xs: 2, md: 6 }}
                      direction={!isMobile && index % 2 === 1 ? 'row-reverse' : 'row'}
                      alignItems="center"
                    >
                      <Grid item xs={12} md={4}>
                        <Box sx={{
                          display: 'flex',
                          justifyContent: 'center',
                          alignItems: 'center',
                          py: { xs: 2, md: 4 },
                          '& .MuiSvgIcon-root': {
                            color: 'var(--color-primary)',
                            fontSize: { xs: 56, md: 80 }
                          }
                        }}>
                          {value.icon}
                        </Box>
                      </Grid>
                      <Grid item xs={12} md={8}>
                        <Typography
                          variant="h3"
                          sx={{
                            fontWeight: 700,
                            mb: 2,
                            color: 'var(--color-text-primary)',
                            fontSize: { xs: '1.3rem', md: '1.8rem' },
                            lineHeight: 1.3,
                            wordBreak: 'keep-all',
                            textAlign: { xs: 'center', md: 'left' }
                          }}
                        >
                          {value.title}
                        </Typography>
                        <Typography sx={{
                          color: 'var(--color-text-secondary)',
                          fontSize: { xs: '0.95rem', md: '1.1rem' },
                          lineHeight: 1.7,
                          wordBreak: 'keep-all',
                          mb: 2,
                          textAlign: { xs: 'center', md: 'left' }
                        }}>
                          {value.description}
                        </Typography>
                        <Typography sx={{
                          color: 'var(--color-primary)',
                          fontSize: '0.95rem',
                          fontWeight: 600,
                          textAlign: { xs: 'center', md: 'left' }
                        }}>
                          자세히 보기 →
                        </Typography>
                      </Grid>
                    </Grid>
                  </Box>
                </motion.div>
              ))}
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
                <Grid container spacing={3}>
                  {basics.map((value, index) => (
                    <Grid item xs={6} md={4} key={index}>
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
                          구조 생성, 키워드 주입, 문체 적용, 선거법 검수, SEO 검증까지.
                          문제가 발견되면 AI가 스스로 수정합니다.
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
                      wordBreak: 'keep-all'
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
                  <Box sx={{ mb: 6 }}>
                    <Typography
                      variant="h1"
                      component="div"
                      sx={{
                        fontWeight: 700,
                        color: 'var(--color-primary)',
                        fontSize: 'clamp(2.2rem, 10vw, 6rem)',
                        letterSpacing: '-0.03em',
                        lineHeight: 1,
                        mb: 2,
                        whiteSpace: 'nowrap',
                        ...numericStyle
                      }}
                    >
                      월 50,000원
                    </Typography>
                    <Typography sx={{
                      color: 'var(--color-text-secondary)',
                      fontSize: '1.25rem',
                      fontWeight: 400
                    }}>
                      (VAT 별도)
                    </Typography>
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
                    서비스 신청하기
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
