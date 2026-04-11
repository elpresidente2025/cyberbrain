// frontend/src/pages/AboutPage.jsx
// Minimal Landing Page

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
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
  EditNote,
  TrendingUp,
  Speed,
  Share,
  Psychology,
  AutoAwesome
} from '@mui/icons-material';
import {
  ResponsiveContainer,
  AreaChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine
} from 'recharts';
import { BRANDING } from '../config/branding';

const AboutPage = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [showAllFAQs, setShowAllFAQs] = useState(false);
  const [expandedFAQ, setExpandedFAQ] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState(null); // 모달 상태 추가

  const monthlyViewData = [
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

  const preLaunchData = monthlyViewData.filter((item) => !item.isAfterLaunch);
  const postLaunchData = monthlyViewData.filter((item) => item.isAfterLaunch);

  const preLaunchAverage = Math.round(
    preLaunchData.reduce((sum, item) => sum + item.total, 0) / preLaunchData.length
  );
  const postLaunchAverage = Math.round(
    postLaunchData.reduce((sum, item) => sum + item.total, 0) / postLaunchData.length
  );
  const growthMultiple = (postLaunchAverage / preLaunchAverage).toFixed(2);
  const postLaunchPeak = postLaunchData.reduce(
    (peak, item) => (item.total > peak.total ? item : peak),
    postLaunchData[0]
  );

  const handleFAQChange = (panel) => (event, isExpanded) => {
    setExpandedFAQ(isExpanded ? panel : false);
  };

  // 카드 키보드 핸들러
  const handleCardKeyDown = (event, value) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setSelectedFeature(value);
    }
  };

  // 핵심 가치 6개
  const coreValues = [
    {
      icon: <EditNote aria-hidden="true" />,
      ariaLabel: '원고 생성 기능',
      title: '월 90회 원고 생성',
      description: '충분한 분량',
      modalTitle: '🔥 한 달 90개. 경쟁자는 뒤에서 구경만 합니다.',
      details: `하루 3개. 일주일이면 21개. 한 달이면 90개.

침묵하는 동안, 상대 후보는 매일 유권자와 대화하고 있습니다.
이제 '오늘 뭘 올리지?' 고민은 끝났습니다.
매일, 쉬지 않고, 지치지 않고. 비서관은 24시간 대기 중입니다.`
    },
    {
      icon: <TrendingUp aria-hidden="true" />,
      ariaLabel: '검색 최적화 기능',
      title: '검색 최적화',
      description: '네이버 상위노출',
      modalTitle: '🎯 네이버 1페이지. 현수막보다 강력합니다.',
      details: `'우리 동네 의정활동'을 검색할 때,
가장 먼저 뜨는 이름은 누구일까요?

네이버 알고리즘이 좋아하는 키워드 배치, 소제목 구조, 본문 길이.
알아서 맞춰 드립니다. 검색 결과 1페이지,
그건 돈 주고도 못 사는 노출입니다.`
    },
    {
      icon: <Speed aria-hidden="true" />,
      ariaLabel: '빠른 생성 기능',
      title: '2~3분 빠른 생성',
      description: '바쁜 의원님께 딱',
      modalTitle: '⚡ 3시간 → 3분. 보좌진도 놀랍니다.',
      details: `긴급 성명서. 축사. 해명 자료.
정치에서 '타이밍'은 생명입니다.

보좌관이 밤새 쓰던 초안, 이제 커피 한 잔 마시는 사이에 완성됩니다.
골든타임을 놓치지 않는 빠른 대응. 그게 경쟁력입니다.`
    },
    {
      icon: <Share aria-hidden="true" />,
      ariaLabel: 'SNS 변환 기능',
      title: '블로그+SNS 자동 변환',
      description: '한 번에 다채널',
      modalTitle: '📱 한 번 쓰고, 네 번 씁니다.',
      details: `블로그 원고 하나면 충분합니다.
버튼 하나로 인스타그램, 페이스북, X(트위터), 스레드까지.

각 플랫폼 문법에 맞게 자동 변환.
해시태그, 글자 수, 어투까지 알아서 맞춥니다.
'승인' 버튼만 누르면 끝.`
    },
    {
      icon: <Psychology aria-hidden="true" />,
      ariaLabel: 'AI 학습 기능',
      title: '점점 나다워지는 AI',
      description: '프로필 학습으로 진화',
      modalTitle: `🧠 쓸수록 닮아갑니다. 나만의 ${BRANDING.serviceShortName}.`,
      details: `처음엔 조금 어색할 수 있습니다.
하지만 걱정 마세요.

과거 글, 자주 쓰는 표현, 말투 습관.
AI가 학습합니다. 점점 닮아갑니다.
나중엔 보좌진도 구분 못 합니다.
'이거 직접 쓰신 거 아니에요?'`
    },
    {
      icon: <AutoAwesome aria-hidden="true" />,
      ariaLabel: '고품질 글쓰기 기능',
      title: '읽히는 글, 살아있는 글',
      description: '끝까지 읽게 만드는 힘',
      modalTitle: '✨ AI 티 안 나는 글. 사람 냄새 나는 글.',
      details: `정보 나열? 그건 ChatGPT도 합니다.

전자두뇌비서관은 다릅니다.
서론의 훅(Hook), 본론의 논리 전개, 결론의 여운.
베테랑 정치 칼럼니스트의 작법을 학습했습니다.
읽는 사람이 끝까지 읽게 만드는 힘.
그게 진짜 글쓰기입니다.`
    }
  ];

  // FAQ 데이터
  const allFAQs = [
    // Top 3
    {
      id: 'faq-0',
      question: 'AI도 많은데 굳이 이걸 써야 하나요?',
      answer: '일반 AI와 달리 정치 콘텐츠에 특화되어 있으며, 네이버 검색 최적화가 적용됩니다.'
    },
    {
      id: 'faq-1',
      question: '더불어민주당 당원만 사용 가능한가요?',
      answer: '네, 당원 인증이 필요합니다. 당적증명서와 당비납부 영수증을 제출해주세요.'
    },
    // More 4
    {
      id: 'faq-4',
      question: '월 90회면 충분한가요?',
      answer: '하루 3개 꼴로, 블로그+SNS 포함하면 주 5~6일 꾸준히 포스팅 가능한 분량입니다.'
    },
    {
      id: 'faq-6',
      question: '검색 최적화는 어떻게 되나요?',
      answer: '네이버 검색 알고리즘에 최적화된 키워드와 구조로 자동 작성됩니다.'
    },
    {
      id: 'faq-7',
      question: '어떤 내용으로 원고를 만들 수 있나요?',
      answer: '지역 현안, 정책 설명, 활동 보고 등 정치 콘텐츠 전반을 생성할 수 있습니다.'
    },
    {
      id: 'faq-8',
      question: '당원 인증은 얼마나 걸리나요?',
      answer: '서류 제출 후 영업일 기준 1~2일 내 승인됩니다. 승인 즉시 이용 가능합니다.'
    }
  ];

  const topFAQs = allFAQs.slice(0, 3);
  const moreFAQs = allFAQs.slice(3, 10);
  const displayedFAQs = showAllFAQs ? allFAQs : topFAQs;

  return (
    <Box sx={{
      minHeight: '100vh',
      bgcolor: 'var(--color-background)',
      position: 'relative'
    }}>
      {/* 로그인 버튼 */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <Box sx={{ position: 'fixed', right: 24, top: 24, zIndex: 10 }}>
          <Button
            onClick={() => navigate('/login')}
            sx={{
              color: 'var(--color-primary)',
              fontSize: '1rem',
              fontWeight: 600,
              textTransform: 'none',
              px: 3,
              py: 1,
              '&:hover': {
                bgcolor: 'var(--color-primary-lighter)'
              }
            }}
          >
            로그인
          </Button>
        </Box>
      </motion.div>

      {/* Hero Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <Container
          maxWidth="md"
          sx={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            textAlign: 'center',
            py: 8
          }}
        >
          <Typography
            variant="h1"
            sx={{
              fontWeight: 700,
              fontSize: { xs: '2.5rem', md: '4.5rem' },
              mb: 4,
              color: 'var(--color-text-primary)',
              letterSpacing: '-0.02em',
              lineHeight: 1.1,
              wordBreak: 'keep-all'
            }}
          >
            "의원님 덕분에<br />살기 좋은 동네가 됐어요!"
          </Typography>

          <Typography
            variant="h5"
            sx={{
              mb: 8,
              color: 'var(--color-text-secondary)',
              fontWeight: 400,
              fontSize: { xs: '1.5rem', md: '2rem' },
              lineHeight: 1.6,
              wordBreak: 'keep-all'
            }}
          >
            홍보하지 않으면<br />이런 말도 못 듣습니다.
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
                transition: 'all var(--transition-normal)',
                '&:hover': {
                  bgcolor: 'var(--color-primary-hover)',
                  boxShadow: 'var(--shadow-glow-primary)'
                },
                '&:active': {
                  transform: 'scale(0.98)'
                },
                '&:focus-visible': {
                  outline: '2px solid var(--color-text-inverse)',
                  outlineOffset: '2px'
                }
              }}
            >
              네이버 현수막? 지금 시작
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
                transition: 'all var(--transition-normal)',
                '&:hover': {
                  borderWidth: 2,
                  borderColor: 'var(--color-primary)',
                  bgcolor: 'var(--color-primary-lighter)',
                  boxShadow: 'var(--shadow-md)'
                },
                '&:active': {
                  transform: 'scale(0.98)'
                },
                '&:focus-visible': {
                  outline: '2px solid var(--color-primary)',
                  outlineOffset: '2px'
                }
              }}
            >
              📖 자세히 보기
            </Button>
          </Box>
        </Container>
      </motion.div>

      {/* 도입 성과 그래프 섹션 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.15 }}
      >
        <Container
          maxWidth="lg"
          sx={{
            py: { xs: 10, md: 14 }
          }}
        >
          <Box
            sx={{
              p: { xs: 3, sm: 4, md: 6 },
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--color-border)',
              bgcolor: 'var(--color-surface)',
              boxShadow: 'var(--shadow-lg)'
            }}
          >
            <Box sx={{ mb: { xs: 4, md: 5 }, textAlign: 'center' }}>
              <Typography
                variant="h2"
                sx={{
                  fontWeight: 700,
                  color: 'var(--color-text-primary)',
                  mb: 2,
                  fontSize: { xs: '2rem', md: '2.8rem' },
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all'
                }}
              >
                의정 성과, 이제는 읽히게 만듭니다
              </Typography>
              <Typography
                sx={{
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', md: '1.125rem' },
                  lineHeight: 1.7,
                  wordBreak: 'keep-all'
                }}
              >
                {BRANDING.serviceName} 도입 후 월 평균 조회수 289회 → 1,451회 (5.03배)
              </Typography>
              <Typography
                sx={{
                  mt: 0.75,
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '0.9rem', md: '0.95rem' },
                  lineHeight: 1.6,
                  wordBreak: 'keep-all'
                }}
              >
                도입 이후 기간(2025.12~2026.02) 기준
              </Typography>
            </Box>

            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Box
                  sx={{
                    height: { xs: 280, md: 360 },
                    p: { xs: 1.5, md: 2 },
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--color-border)',
                    bgcolor: 'var(--color-background)'
                  }}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={monthlyViewData} margin={{ top: 24, right: 12, left: 0, bottom: 8 }}>
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
                        dataKey="total"
                        stroke="var(--color-primary)"
                        strokeWidth={3}
                        dot={{ r: 4, fill: 'var(--color-primary)' }}
                        activeDot={{ r: 6, fill: 'var(--color-primary)' }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </Box>
              </Grid>

              <Grid item xs={12} md={4}>
                <Grid container spacing={2}>
                  <Grid item xs={6} md={12}>
                    <Card
                      elevation={0}
                      sx={{
                        p: 2.5,
                        borderRadius: 'var(--radius-md)',
                        border: '1px dashed var(--color-border)',
                        bgcolor: 'var(--color-background)',
                        minHeight: 132
                      }}
                    >
                      <Typography sx={{ color: 'var(--color-text-secondary)', mb: 1, fontSize: '0.95rem' }}>
                        도입 전 월 평균
                      </Typography>
                      <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '1.55rem', fontWeight: 600 }}>
                        {preLaunchAverage.toLocaleString()}회
                      </Typography>
                      <Typography sx={{ color: 'var(--color-text-secondary)', mt: 0.75, fontSize: '0.85rem' }}>
                        기준 구간 9개월
                      </Typography>
                    </Card>
                  </Grid>
                  <Grid item xs={6} md={12}>
                    <Card
                      elevation={0}
                      sx={{
                        p: 2.5,
                        borderRadius: 'var(--radius-md)',
                        border: '2px solid var(--color-primary)',
                        bgcolor: 'var(--color-surface)',
                        background: 'linear-gradient(135deg, var(--color-primary-lighter) 0%, var(--color-surface) 72%)',
                        boxShadow: 'var(--shadow-glow-primary)',
                        minHeight: 132
                      }}
                    >
                      <Typography sx={{ color: 'var(--color-primary)', mb: 1, fontSize: '0.95rem', fontWeight: 700 }}>
                        도입 후 월 평균
                      </Typography>
                      <Typography
                        sx={{
                          color: 'var(--color-primary)',
                          fontSize: { xs: '2.15rem', md: '2.55rem' },
                          fontWeight: 800,
                          lineHeight: 1
                        }}
                      >
                        {postLaunchAverage.toLocaleString()}회
                      </Typography>
                      <Typography sx={{ color: 'var(--color-text-secondary)', mt: 0.75, fontSize: '0.85rem' }}>
                        도입 후 3개월 평균
                      </Typography>
                    </Card>
                  </Grid>
                  <Grid item xs={12}>
                    <Card
                      elevation={0}
                      sx={{
                        p: 2.5,
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--color-primary)',
                        bgcolor: 'var(--color-primary-lighter)'
                      }}
                    >
                      <Typography sx={{ color: 'var(--color-text-secondary)', mb: 1, fontSize: '0.95rem' }}>
                        도입 후 3개월 성과
                      </Typography>
                      <Typography
                        sx={{
                          color: 'var(--color-primary)',
                          fontSize: { xs: '1.9rem', md: '2.2rem' },
                          fontWeight: 800,
                          lineHeight: 1.2
                        }}
                      >
                        월 평균 {growthMultiple}배
                      </Typography>
                      <Typography sx={{ color: 'var(--color-text-secondary)', mt: 1, fontSize: '0.95rem' }}>
                        최고 {postLaunchPeak.total.toLocaleString()}회{' '}
                        <Typography
                          component="span"
                          sx={{
                            fontSize: '0.82em',
                            color: 'var(--color-text-secondary)'
                          }}
                        >
                          ({postLaunchPeak.month})
                        </Typography>
                      </Typography>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>

            <Typography
              sx={{
                mt: 3,
                color: 'var(--color-text-secondary)',
                fontSize: '0.9rem',
                textAlign: 'right'
              }}
            >
              데이터 기준: 제9회 동시지방선거 이재성 부산광역시장 예비후보 네이버 블로그 조회수 월간 리포트 (2025.03~2026.02)
            </Typography>
          </Box>
        </Container>
      </motion.div>

      {/* 핵심 가치 6개 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
      >
        <Container
          maxWidth="lg"
          sx={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            py: 8
          }}
        >
          <Grid container spacing={4}>
            {coreValues.map((value, index) => (
              <Grid item xs={6} md={4} key={index}>
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
                    bgcolor: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'none',
                    transition: 'all var(--transition-normal)',
                    cursor: 'pointer',
                    '&:hover, &:focus': {
                      borderColor: 'var(--color-primary)',
                      transform: 'translateY(-4px)',
                      boxShadow: 'var(--shadow-lg)'
                    },
                    '&:focus-visible': {
                      outline: '2px solid var(--color-primary)',
                      outlineOffset: '2px'
                    }
                  }}
                >
                  <CardContent>
                    <Box sx={{
                      mb: 2,
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center'
                    }}>
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
                        fontSize: { xs: '1rem', sm: '1.3rem', md: '1.8rem', lg: '2rem' },
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
                        fontSize: { xs: '0.8rem', sm: '0.9rem', md: '1rem', lg: '1.1rem' },
                        fontWeight: 400,
                        lineHeight: 1.5,
                        wordBreak: 'keep-all'
                      }}
                    >
                      {value.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
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
        sx={{
          '& .MuiDialog-paper': {
            borderRadius: 'var(--radius-lg)',
            p: 2
          }
        }}
      >
        {selectedFeature && (
          <>
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Box sx={{
                mb: 3,
                display: 'flex',
                justifyContent: 'center'
              }}>
                {/* 아이콘 재사용 (크기 키움) */}
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

      {/* FAQ 섹션 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
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
              letterSpacing: '-0.02em'
            }}
          >
            자주 묻는 질문
          </Typography>

          {displayedFAQs.map((faq) => (
            <Accordion
              key={faq.id}
              expanded={expandedFAQ === faq.id}
              onChange={handleFAQChange(faq.id)}
              elevation={0}
              sx={{
                mb: 2,
                borderRadius: 'var(--radius-md)',
                bgcolor: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderTop: expandedFAQ === faq.id ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                boxShadow: 'none',
                transition: 'all var(--transition-normal)',
                '&:before': { display: 'none' },
                '&:first-of-type': {
                  borderRadius: 'var(--radius-md)'
                },
                '&:last-of-type': {
                  borderRadius: 'var(--radius-md)'
                },
                '&.Mui-expanded': {
                  margin: '0 0 16px 0'
                },
                '&:hover': {
                  borderColor: 'var(--color-primary)'
                }
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
              <AccordionDetails sx={{ px: 4, py: 3, bgcolor: 'var(--color-surface)' }}>
                <Typography sx={{
                  color: 'var(--color-text-secondary)',
                  fontSize: '1.125rem',
                  lineHeight: 1.8
                }}>
                  {faq.answer}
                </Typography>
              </AccordionDetails>
            </Accordion>
          ))}

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
                transition: 'all var(--transition-normal)',
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
              {showAllFAQs ? '질문 접기' : '더 많은 질문 보기 (4개)'}
            </Button>
          </Box>
        </Container>
      </motion.div>

      {/* 가격 섹션 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        <Container maxWidth="sm" sx={{ py: 20 }}>
          <Card
            elevation={0}
            sx={{
              textAlign: 'center',
              p: { xs: 4, sm: 6, md: 8 },
              borderRadius: 'var(--radius-lg)',
              bgcolor: 'var(--color-surface)',
              border: '3px solid var(--color-primary)',
              boxShadow: 'var(--shadow-lg)'
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
                    fontSize: { xs: '2.5rem', sm: '3.5rem', md: '5rem', lg: '6rem' },
                    letterSpacing: '-0.03em',
                    lineHeight: 1,
                    mb: 2
                  }}
                >
                  월 50,000원
                </Typography>
                <Typography
                  sx={{
                    color: 'var(--color-text-secondary)',
                    fontSize: '1.25rem',
                    fontWeight: 400
                  }}
                >
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
                  transition: 'all var(--transition-normal)',
                  '&:hover': {
                    bgcolor: 'var(--color-primary-hover)',
                    boxShadow: 'var(--shadow-glow-primary)'
                  },
                  '&:active': {
                    transform: 'scale(0.98)'
                  },
                  '&:focus-visible': {
                    outline: '2px solid var(--color-text-inverse)',
                    outlineOffset: '2px'
                  }
                }}
              >
                내 선거구 비어있나? 지금 확인
              </Button>
            </CardContent>
          </Card>
        </Container>
      </motion.div>

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
  );
};

export default AboutPage;
