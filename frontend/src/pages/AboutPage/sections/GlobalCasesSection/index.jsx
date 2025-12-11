// E:\ai-secretary\frontend\src\pages\AboutPage\sections\GlobalCasesSection\index.jsx
// Global cases section - showcase of successful digital communication cases

import React from 'react';
import { Box, Typography, Grid } from '@mui/material';
import { ContentContainer } from '../../components/StyledComponents';
import { GLOBAL_AUTHORITY_CASES } from '../../data';

// GlobalAuthorityCaseContainer 컴포넌트 - 2행 이미지 레이아웃
const GlobalAuthorityCaseContainer = () => {
  return (
    <Box
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
               borderRadius: 1,
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
               borderRadius: 1,
               border: '1px solid rgba(255,255,255,0.1)',
               objectFit: 'contain'
             }} />
      </Box>
    </Box>
  );
};

// 글로벌 사례 섹션
function GlobalCasesSection() {
  return (
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
                    borderRadius: 1,
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
                        borderRadius: 1,
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
                    borderRadius: 1,
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
                        borderRadius: 1,
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
                fontSize: { xs: '0.9rem', md: '1.0rem', lg: '1rem' }
              }}>
                검색 노출부터 유권자 소통까지, 전략적 블로그 콘텐츠로 정치인의 인지도와 영향력을 높이세요.
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </ContentContainer>
    </Box>
  );
}

export default GlobalCasesSection;
export { GlobalAuthorityCaseContainer };
