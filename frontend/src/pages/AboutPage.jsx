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
  EditNote,
  TrendingUp,
  Speed,
  Share,
  Psychology
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

  // 핵심 가치 6개
  const coreValues = [
    {
      icon: <EditNote />,
      title: '월 90회 원고 생성',
      description: '충분한 분량'
    },
    {
      icon: <TrendingUp />,
      title: '검색 최적화',
      description: '네이버 상위노출'
    },
    {
      icon: <Speed />,
      title: '2~3분 빠른 생성',
      description: '바쁜 의원님께 딱'
    },
    {
      icon: <Share />,
      title: '블로그+SNS 자동 변환',
      description: '한 번에 다채널'
    },
    {
      icon: <Psychology />,
      title: '점점 나다워지는 AI',
      description: '프로필 학습으로 진화'
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
      answer: '네, 당원 인증이 필요합니다. 당적증명서 또는 당비납부 영수증을 제출해주세요.'
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
      bgcolor: '#ffffff', // 🇨🇭 스위스 화이트
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
              color: '#152484', // 🇨🇭 네이비
              fontSize: '1rem',
              fontWeight: 600,
              textTransform: 'none',
              px: 3,
              py: 1,
              '&:hover': {
                bgcolor: 'rgba(21, 36, 132, 0.04)'
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
              color: '#000000 !important', // 🇨🇭 순수 검정
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
              color: '#333333 !important', // 🇨🇭 다크 그레이
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
                // 🇨🇭 네이비 버튼
                bgcolor: '#152484',
                color: '#ffffff',
                fontSize: '1.75rem',
                fontWeight: 700,
                px: 8,
                py: 3,
                borderRadius: 0,
                boxShadow: 'none',
                textTransform: 'none',
                '&:hover': {
                  bgcolor: '#0f1a5f',
                  boxShadow: 'none'
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
                // 🇨🇭 네이비 테두리
                color: '#152484',
                borderColor: '#152484',
                borderWidth: 2,
                fontSize: '1.5rem',
                fontWeight: 600,
                px: 6,
                py: 3,
                borderRadius: 0,
                textTransform: 'none',
                '&:hover': {
                  borderWidth: 2,
                  borderColor: '#152484',
                  bgcolor: 'rgba(21, 36, 132, 0.04)'
                }
              }}
            >
              📖 자세히 보기
            </Button>
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
                  sx={{
                    textAlign: 'center',
                    p: { xs: 1, sm: 1.5, md: 3 },
                    height: '100%',
                    borderRadius: 0,
                    // 🇨🇭 화이트 카드 + 미니멀 테두리
                    bgcolor: '#ffffff',
                    border: '1px solid #e0e0e0',
                    boxShadow: 'none',
                    transition: 'all 0.2s ease',
                    '&:hover': {
                      borderColor: '#152484'
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
                        // 🇨🇭 네이비 아이콘
                        '& .MuiSvgIcon-root': {
                          color: '#152484',
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
                        color: '#000000 !important',
                        fontSize: { xs: '1.1rem', sm: '1.4rem', md: '2rem', lg: '2.25rem' },
                        lineHeight: 1.2,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}
                    >
                      {value.title}
                    </Typography>
                    <Typography
                      variant="body1"
                      sx={{
                        color: '#666666 !important',
                        fontSize: { xs: '0.75rem', sm: '0.875rem', md: '1rem', lg: '1.25rem' },
                        fontWeight: 400,
                        lineHeight: 1.4,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
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
              color: '#000000 !important', // 🇨🇭 검정
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
                borderRadius: 0,
                // 🇨🇭 화이트 배경 + 심플 테두리
                bgcolor: '#ffffff',
                border: '1px solid #e0e0e0',
                borderTop: expandedFAQ === faq.id ? '2px solid #152484' : '1px solid #e0e0e0',
                boxShadow: 'none',
                transition: 'all 0.2s ease',
                '&:before': { display: 'none' },
                '&:first-of-type': {
                  borderRadius: 0
                },
                '&:last-of-type': {
                  borderRadius: 0
                },
                '&.Mui-expanded': {
                  margin: '0 0 16px 0'
                },
                '&:hover': {
                  borderColor: '#152484'
                }
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMore sx={{ color: '#152484' }} />}
                sx={{ py: 3, px: 4 }}
              >
                <Typography sx={{ fontWeight: 600, fontSize: '1.25rem', color: '#000000 !important' }}>
                  {faq.question}
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 4, py: 3, bgcolor: '#fafafa' }}>
                <Typography sx={{
                  color: '#333333 !important',
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
                color: '#152484',
                borderColor: '#152484',
                borderWidth: 2,
                fontSize: '1.125rem',
                fontWeight: 600,
                px: 6,
                py: 2,
                borderRadius: 0,
                textTransform: 'none',
                '&:hover': {
                  borderWidth: 2,
                  borderColor: '#152484',
                  bgcolor: 'rgba(21, 36, 132, 0.04)'
                }
              }}
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
              p: 8,
              borderRadius: 0,
              // 🇨🇭 화이트 카드 + 네이비 강조
              bgcolor: '#ffffff',
              border: '3px solid #152484',
              boxShadow: 'none'
            }}
          >
            <CardContent>
              <Box sx={{ mb: 6 }}>
                <Typography
                  variant="h1"
                  component="div"
                  sx={{
                    fontWeight: 700,
                    color: '#152484 !important',
                    fontSize: { xs: '4rem', md: '6rem' },
                    letterSpacing: '-0.03em',
                    lineHeight: 1,
                    mb: 2
                  }}
                >
                  월 50,000원
                </Typography>
                <Typography
                  sx={{
                    color: '#666666 !important',
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
                  bgcolor: '#152484',
                  color: '#ffffff',
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  py: 3,
                  borderRadius: 0,
                  boxShadow: 'none',
                  textTransform: 'none',
                  '&:hover': {
                    bgcolor: '#0f1a5f',
                    boxShadow: 'none'
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
          // 🇨🇭 라이트 그레이 배경
          bgcolor: '#f5f5f5',
          color: '#666666 !important',
          textAlign: 'center',
          mt: 12,
          borderTop: '1px solid #e0e0e0'
        }}
      >
        <Typography variant="body2" sx={{ lineHeight: 2, fontSize: '0.95rem' }}>
          사이버브레인 | 사업자등록번호: 256-24-02174 | 통신판매업신고번호: (비움)<br />
          대표: 강정구 | 인천광역시 계양구 용종로 124, 학마을한진아파트 139동 1504호 | 대표번호: 010-4885-6206<br />
          Copyright 2025. CyberBrain. All Rights Reserved.
        </Typography>
      </Box>
    </Box>
  );
};

export default AboutPage;
