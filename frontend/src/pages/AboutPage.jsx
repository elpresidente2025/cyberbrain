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
import { useTheme } from '@mui/material/styles';


// Section components
import HeroSection from "./AboutPage/sections/HeroSection";
import StatsSection from "./AboutPage/sections/StatsSection";
import FeaturesSection from "./AboutPage/sections/FeaturesSection";
import FAQSection from "./AboutPage/sections/FAQSection";
import GlobalCasesSection from "./AboutPage/sections/GlobalCasesSection";

// Styled components and utilities
import {
  Page,
  Section,
  CTAButton,
  OutlineButton,
  CardSoft,
  CardEmphasis,
  StatBadge,
  ContentContainer
} from "./AboutPage/components/StyledComponents";
import InViewFade from "./AboutPage/components/InViewFade";
import SampleSpeechModal from "./AboutPage/components/SampleSpeechModal";

// Data constants
import { SAFETY_FEATURES } from "./AboutPage/data";

// SAFETY_FEATURES is imported from data, other constants removed

// -----------------------------
// Main AboutPage Component
// -----------------------------

const AboutPage = ({ showDemo: showDemoProp }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const theme = useTheme();
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

      {/* 로그인 화면 이동 버튼 */}
      <Box sx={{ position: 'fixed', right: 16, top: 16, zIndex: 10 }}>
        <Button
          onClick={() => navigate('/login')}
          sx={{
            color: 'rgba(255,255,255,0.9)',
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

      {/* Demo switch (only in dev or with ?demo=1) */}
      {showDemoSwitch && (
        <Box sx={{ position: 'fixed', right: 16, top: 56, zIndex: 10 }}>
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

      {/* Hero Section */}
      <HeroSection demoMode={demoMode} handlePrimaryCTA={handlePrimaryCTA} />

      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* Stats Section */}
      <StatsSection />

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

      {/* 섹션 구분선 */}
      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* 3단계 사용법 섹션 */}
      <Section sx={{ py: { xs: 8, md: 12 } }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 800,
              mb: 2,
              textAlign: 'center'
            }}>
              3단계면 끝, 누구나 쉽게
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 400,
              color: 'rgba(255,255,255,0.7)'
            }}>
              복잡한 설정 없이 바로 시작하세요
            </Typography>
          </InViewFade>

          <Grid container spacing={4} sx={{ justifyContent: 'center' }}>
            {/* 1단계 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={600}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  position: 'relative',
                  border: '2px solid rgba(0, 212, 255, 0.3)'
                }}>
                  <Box sx={{
                    position: 'absolute',
                    top: -20,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    backgroundColor: '#00d4ff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 900,
                    fontSize: '1.5rem',
                    color: '#000'
                  }}>
                    1
                  </Box>
                  <CardContent sx={{ p: 4, pt: 5 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      말씀하세요
                    </Typography>
                    <Typography variant="body1" sx={{
                      lineHeight: 1.8,
                      color: 'rgba(255,255,255,0.9)'
                    }}>
                      정책, 지역 이슈, 활동 내역을<br />
                      간단히 입력하세요
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>

            {/* 2단계 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={700}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  position: 'relative',
                  border: '2px solid rgba(0, 212, 255, 0.3)'
                }}>
                  <Box sx={{
                    position: 'absolute',
                    top: -20,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    backgroundColor: '#00d4ff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 900,
                    fontSize: '1.5rem',
                    color: '#000'
                  }}>
                    2
                  </Box>
                  <CardContent sx={{ p: 4, pt: 5 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      완성됩니다
                    </Typography>
                    <Typography variant="body1" sx={{
                      lineHeight: 1.8,
                      color: 'rgba(255,255,255,0.9)'
                    }}>
                      AI가 자동으로 생성한<br />
                      품격 있는 원고를 확인하세요
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>

            {/* 3단계 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={800}>
                <CardSoft sx={{
                  height: '100%',
                  textAlign: 'center',
                  position: 'relative',
                  border: '2px solid rgba(0, 212, 255, 0.3)'
                }}>
                  <Box sx={{
                    position: 'absolute',
                    top: -20,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    backgroundColor: '#00d4ff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 900,
                    fontSize: '1.5rem',
                    color: '#000'
                  }}>
                    3
                  </Box>
                  <CardContent sx={{ p: 4, pt: 5 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      발전됩니다
                    </Typography>
                    <Typography variant="body1" sx={{
                      lineHeight: 1.8,
                      color: 'rgba(255,255,255,0.9)'
                    }}>
                      스타일을 학습하여<br />
                      점점 더 나아집니다
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>
          </Grid>
        </ContentContainer>
      </Section>

      {/* Features Section */}
      <FeaturesSection />

      {/* 섹션 구분선 */}
      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* 개인화 시스템 섹션 */}
      <Section sx={{ backgroundColor: 'rgba(0,0,0,0.02)', py: { xs: 8, md: 12 } }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 800,
              mb: 2,
              textAlign: 'center'
            }}>
              당신만의 전뇌비서관이 기억합니다
            </Typography>
            <Typography variant="h6" sx={{
              mb: 6,
              textAlign: 'center',
              fontWeight: 400,
              color: 'rgba(255,255,255,0.7)'
            }}>
              3가지 핵심 요소로 당신의 정치 활동을 완벽하게 지원합니다
            </Typography>
          </InViewFade>

          <Grid container spacing={4}>
            {/* 정책 이력 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={600}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      📋 정책 이력
                    </Typography>
                    <Typography variant="body2" sx={{
                      lineHeight: 1.6,
                      color: 'rgba(255,255,255,0.7)'
                    }}>
                      과거에 발표했던 정책, 공약, 활동 내역을 AI가 학습하여 일관성 있는 메시지를 전달합니다
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>

            {/* 지역 맥락 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={700}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      🏘️ 지역 맥락
                    </Typography>
                    <Typography variant="body2" sx={{
                      lineHeight: 1.6,
                      color: 'rgba(255,255,255,0.7)'
                    }}>
                      지역 현안, 주민 관심사, 특성을 반영하여 지역 밀착형 콘텐츠를 생성합니다
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>

            {/* 개인 스타일 */}
            <Grid item xs={12} md={4}>
              <InViewFade timeout={800}>
                <CardSoft sx={{ height: '100%', textAlign: 'center' }}>
                  <CardContent sx={{ p: 4 }}>
                    <Typography variant="h5" sx={{
                      fontWeight: 700,
                      mb: 2,
                      color: '#00d4ff'
                    }}>
                      ✍️ 개인 스타일
                    </Typography>
                    <Typography variant="body2" sx={{
                      lineHeight: 1.6,
                      color: 'rgba(255,255,255,0.7)'
                    }}>
                      글쓰기 스타일, 선호하는 표현, 톤앤매너를 학습하여 점점 더 '나다운' 콘텐츠를 만들어냅니다
                    </Typography>
                  </CardContent>
                </CardSoft>
              </InViewFade>
            </Grid>
          </Grid>
        </ContentContainer>
      </Section>

      {/* 섹션 구분선 */}
      <Box sx={{
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #00d4ff 20%, #00d4ff 80%, transparent 100%)',
        opacity: 0.3
      }} />

      {/* Global Cases Section */}
      <GlobalCasesSection />

      {/* 두 번째 섹션: 이미 증명된 전략 */}
      <Section sx={{
        backgroundColor: 'rgba(0,0,0,0.02)',
        py: { xs: 6, md: 10 }
      }}>
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography variant="h4" sx={{
              fontWeight: 700,
              mb: 6,
              textAlign: 'center'
            }}>
              이미 증명된 전략
            </Typography>
          </InViewFade>

          <InViewFade>
            <Grid container spacing={4} sx={{ justifyContent: 'center' }}>
              <Grid item xs={12} md={8}>
                <CardSoft sx={{ height: { xs: '80%', md: '100%' } }}>
                  <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                    <Grid container spacing={{ xs: 2, md: 4 }} alignItems="center">
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

      {/* FAQ Section */}
      <FAQSection expandedFaq={expandedFaq} handleAccordionChange={handleAccordionChange} />

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