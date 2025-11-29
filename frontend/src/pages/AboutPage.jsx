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
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme,
  useMediaQuery
} from '@mui/material';
import {
  ExpandMore,
  AttachMoney,
  TrendingUp,
  AccountBalance
} from '@mui/icons-material';

const AboutPage = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [showAllFAQs, setShowAllFAQs] = useState(false);
  const [expandedFAQ, setExpandedFAQ] = useState(false);

  const handleFAQChange = (panel) => (event, isExpanded) => {
    setExpandedFAQ(isExpanded ? panel : false);
  };

  // 핵심 가치 3개
  const coreValues = [
    {
      icon: <AttachMoney sx={{ fontSize: 48, color: theme.palette.brand.primary }} />,
      title: '월 90회 원고 생성',
      description: '충분한 분량'
    },
    {
      icon: <TrendingUp sx={{ fontSize: 48, color: theme.palette.brand.primary }} />,
      title: '검색 최적화',
      description: '네이버 상위노출'
    },
    {
      icon: <AccountBalance sx={{ fontSize: 48, color: theme.palette.brand.primary }} />,
      title: '선거구 독점',
      description: '경쟁자 차단'
    }
  ];

  // FAQ 데이터
  const allFAQs = [
    // Top 3
    {
      id: 'faq-1',
      question: '더불어민주당 당원만 사용 가능한가요?',
      answer: '네, 당원 인증이 필요합니다. 당적증명서 또는 당비납부 영수증을 제출해주세요.'
    },
    {
      id: 'faq-2',
      question: '원고 생성에 시간이 얼마나 걸리나요?',
      answer: '주제 입력 후 약 2~3분이면 완성됩니다. 같은 주제로 최대 3번까지 재생성할 수 있습니다.'
    },
    {
      id: 'faq-3',
      question: '선거구 독점은 어떻게 확인하나요?',
      answer: '가입 시 선거구를 선택하시면 실시간으로 사용 가능 여부를 확인할 수 있습니다.'
    },
    // More 6
    {
      id: 'faq-4',
      question: '월 90회면 충분한가요?',
      answer: '하루 3개 꼴로, 블로그+SNS 포함하면 주 5~6일 꾸준히 포스팅 가능한 분량입니다.'
    },
    {
      id: 'faq-5',
      question: '블로그 외에 SNS용 원고도 만들 수 있나요?',
      answer: '네, 블로그 원고를 페이스북, 인스타그램용으로 자동 변환해드립니다.'
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
    },
    {
      id: 'faq-9',
      question: '원고 품질은 어느 정도인가요?',
      answer: '프로필 정보를 학습하여 점점 더 \'나다운\' 글을 작성합니다. 최대 3번까지 재생성 가능합니다.'
    }
  ];

  const topFAQs = allFAQs.slice(0, 3);
  const moreFAQs = allFAQs.slice(3, 9);
  const displayedFAQs = showAllFAQs ? allFAQs : topFAQs;

  return (
    <Box sx={{
      minHeight: '100vh',
      bgcolor: theme.palette.mode === 'dark' ? '#1A1A1A' : '#F8F9FA'
    }}>
      {/* 로그인 버튼 */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <Box sx={{ position: 'fixed', right: 16, top: 16, zIndex: 10 }}>
          <Button
            onClick={() => navigate('/login')}
            sx={{
              color: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.9)' : '#152484',
              fontSize: '0.95rem',
              fontWeight: 500,
              textTransform: 'none',
              '&:hover': {
                color: theme.palette.brand.primary,
                bgcolor: 'transparent'
              }
            }}
          >
            로그인 화면으로 이동
          </Button>
        </Box>
      </motion.div>

      {/* Hero Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <Container maxWidth="md" sx={{ pt: { xs: 12, md: 16 }, pb: 8, textAlign: 'center' }}>
          <Typography
            variant="h2"
            sx={{
              fontWeight: 800,
              fontSize: { xs: '2rem', md: '3rem' },
              mb: 2,
              color: theme.palette.mode === 'dark' ? 'white' : '#152484'
            }}
          >
            AI 정치 콘텐츠, 3분이면 끝
          </Typography>

          <Typography
            variant="h5"
            sx={{
              mb: 4,
              color: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.6)',
              fontWeight: 400,
              fontSize: { xs: '1.1rem', md: '1.5rem' }
            }}
          >
            검색 노출부터 유권자 소통까지
          </Typography>

          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/login')}
              sx={{
                bgcolor: theme.palette.brand.primary,
                color: 'white',
                fontSize: '1.2rem',
                fontWeight: 700,
                px: 4,
                py: 1.5,
                borderRadius: 2,
                boxShadow: '0 8px 24px rgba(21, 36, 132, 0.3)',
                '&:hover': {
                  bgcolor: '#0f1f5c',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 12px 32px rgba(21, 36, 132, 0.4)'
                }
              }}
            >
              💳 월 55,000원으로 시작하기
            </Button>

            <Button
              variant="outlined"
              size="large"
              onClick={() => window.scrollTo({ top: window.innerHeight, behavior: 'smooth' })}
              sx={{
                color: theme.palette.brand.primary,
                borderColor: theme.palette.brand.primary,
                fontSize: '1.1rem',
                fontWeight: 600,
                px: 4,
                py: 1.5,
                borderRadius: 2,
                '&:hover': {
                  borderColor: theme.palette.brand.primary,
                  bgcolor: 'rgba(21, 36, 132, 0.05)'
                }
              }}
            >
              📖 자세히 보기
            </Button>
          </Box>
        </Container>
      </motion.div>

      {/* 핵심 가치 3개 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
      >
        <Container maxWidth="lg" sx={{ py: 8 }}>
          <Grid container spacing={4}>
            {coreValues.map((value, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card
                  elevation={0}
                  sx={{
                    textAlign: 'center',
                    p: 4,
                    height: '100%',
                    borderRadius: 3,
                    bgcolor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'white',
                    border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'}`,
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      transform: 'translateY(-8px)',
                      boxShadow: '0 12px 40px rgba(21, 36, 132, 0.15)'
                    }
                  }}
                >
                  <CardContent>
                    <Box sx={{ mb: 2 }}>
                      {value.icon}
                    </Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
                      {value.title}
                    </Typography>
                    <Typography variant="body1" color="text.secondary">
                      {value.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </motion.div>

      {/* 가격 섹션 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
      >
        <Container maxWidth="sm" sx={{ py: 8 }}>
          <Card
            elevation={0}
            sx={{
              textAlign: 'center',
              p: 5,
              borderRadius: 3,
              bgcolor: theme.palette.mode === 'dark' ? 'rgba(21, 36, 132, 0.2)' : 'rgba(21, 36, 132, 0.05)',
              border: `2px solid ${theme.palette.brand.primary}`
            }}
          >
            <CardContent>
              <Typography variant="h4" sx={{ fontWeight: 700, mb: 2 }}>
                스탠다드 플랜 하나뿐
              </Typography>
              <Typography variant="h3" sx={{ fontWeight: 800, color: theme.palette.brand.primary, mb: 1 }}>
                월 55,000원
              </Typography>
              <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
                VAT 포함 · 월 90회 원고 생성
              </Typography>
              <Button
                variant="contained"
                size="large"
                fullWidth
                onClick={() => navigate('/login')}
                sx={{
                  bgcolor: theme.palette.brand.primary,
                  color: 'white',
                  fontSize: '1.2rem',
                  fontWeight: 700,
                  py: 1.5,
                  borderRadius: 2,
                  '&:hover': {
                    bgcolor: '#0f1f5c'
                  }
                }}
              >
                💳 지금 시작하기
              </Button>
            </CardContent>
          </Card>
        </Container>
      </motion.div>

      {/* FAQ 섹션 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        <Container maxWidth="md" sx={{ py: 8 }}>
          <Typography
            variant="h4"
            sx={{
              fontWeight: 700,
              mb: 4,
              textAlign: 'center',
              color: theme.palette.mode === 'dark' ? 'white' : '#152484'
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
                borderRadius: 2,
                bgcolor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'white',
                border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'}`,
                '&:before': { display: 'none' },
                '&.Mui-expanded': {
                  margin: '0 0 16px 0'
                }
              }}
            >
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography sx={{ fontWeight: 600 }}>
                  {faq.question}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography color="text.secondary">
                  {faq.answer}
                </Typography>
              </AccordionDetails>
            </Accordion>
          ))}

          <Box sx={{ textAlign: 'center', mt: 4 }}>
            <Button
              variant="outlined"
              size="large"
              onClick={() => setShowAllFAQs(!showAllFAQs)}
              sx={{
                color: theme.palette.brand.primary,
                borderColor: theme.palette.brand.primary,
                fontSize: '1rem',
                fontWeight: 600,
                px: 4,
                py: 1.5,
                borderRadius: 2,
                '&:hover': {
                  borderColor: theme.palette.brand.primary,
                  bgcolor: 'rgba(21, 36, 132, 0.05)'
                }
              }}
            >
              {showAllFAQs ? '➖ 질문 접기' : '➕ 더 많은 질문 보기 (6개)'}
            </Button>
          </Box>
        </Container>
      </motion.div>

      {/* Footer */}
      <Box
        component="footer"
        sx={{
          py: 4,
          px: 2,
          bgcolor: theme.palette.brand.primary,
          color: 'white',
          textAlign: 'center',
          mt: 8
        }}
      >
        <Typography variant="caption" sx={{ lineHeight: 1.6 }}>
          사이버브레인 | 사업자등록번호: 870-55-00786 | 통신판매업신고번호: (비움)<br />
          대표: 차서영 | 인천광역시 계양구 용종로 124, 학마을한진아파트 139동 1504호 | 대표번호: 010-4885-6206<br />
          Copyright 2025. CyberBrain. All Rights Reserved.
        </Typography>
      </Box>
    </Box>
  );
};

export default AboutPage;
