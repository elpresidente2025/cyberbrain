// E:\ai-secretary\frontend\src\pages\AboutPage\sections\HeroSection\index.jsx
// Hero section - main banner with title and CTA

import React from 'react';
import { Box, Typography, Stack } from '@mui/material';
import {
  HeroRoot,
  HeroBlur,
  HeroOverlay,
  HeroContent,
  CTAButton,
  DemoWatermark
} from '../../components/StyledComponents';
import InViewFade from '../../components/InViewFade';

function HeroSection({ demoMode, handlePrimaryCTA }) {
  return (
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
              mb: { xs: 1.5, md: 2, lg: 2 },
              '@media (min-width: 768px) and (orientation: portrait)': {
                fontSize: 'clamp(40px, 5vw, 60px)',
                whiteSpace: 'normal',
              },
              whiteSpace: { xs: 'normal', md: 'normal', lg: 'nowrap' },
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
                whiteSpace: 'nowrap',
                '@media (max-width: 1500px)': {
                  whiteSpace: 'normal'
                },
                '@media (max-width: 1300px)': {
                  whiteSpace: 'normal'
                },
                '@media (max-width: 1200px)': {
                  whiteSpace: 'normal'
                },
                '@media (max-width: 1024px)': {
                  whiteSpace: 'normal'
                },
                '@media (max-width: 768px)': {
                  whiteSpace: 'normal'
                },
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
              mb: { xs: 4, md: 5, lg: 5 },
              fontSize: { xs: '1.1rem', md: '1.35rem', lg: '1.5rem' },
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
  );
}

export default HeroSection;
