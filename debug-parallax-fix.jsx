// Debug version of ParallaxUrgencySection with enhanced logging and fixes
// This addresses the critical issue where all 3 cards show instead of one

const ParallaxUrgencySection = ({ onCTAClick }) => {
  const [activeCard, setActiveCard] = React.useState(0);
  const [scrollProgress, setScrollProgress] = React.useState(0);
  const sectionRef = React.useRef(null);
  const scrollTicking = React.useRef(false);
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const isMobile = useMediaQuery((theme) => theme.breakpoints.down('md'));

  // Enhanced debug state
  const [debugInfo, setDebugInfo] = React.useState({
    renderCount: 0,
    visibleCards: [],
    lastUpdate: Date.now()
  });

  const cards = [
    {
      title: "이재명의 성공 공식",
      content: "성남시장 시절부터 블로그와 SNS를 적극 활용하며 전국적 인지도를 쌓았습니다.",
      image: "/sns/leejm_x.png",
      imageAlt: "이재명 SNS 활동 사례"
    },
    {
      title: "트럼프의 트위터 정치학",
      content: "전통 미디어를 우회해 트위터 하나로 미국 정치를 흔들었습니다.",
      image: "/sns/trump_x.png",
      imageAlt: "트럼프 트위터 정치학 사례"
    },
    {
      title: "정청래의 경고",
      content: "\"SNS 활동지수\"를 공천에 반영. 온라인 영향력이 없으면 공천도 없습니다.",
      image: "/sns/jeongcr_news.png",
      imageAlt: "정청래 SNS 활동지수 발언 사례"
    }
  ];

  // FIXED: Remove activeCard dependency to prevent unnecessary re-renders
  const updateScrollProgress = React.useCallback(() => {
    if (!sectionRef.current) return;

    const rect = sectionRef.current.getBoundingClientRect();
    const sectionHeight = sectionRef.current.offsetHeight;
    const viewportHeight = window.innerHeight;

    const sectionTop = rect.top;
    const sectionBottom = rect.bottom;

    let progress = 0;

    if (sectionBottom > 0 && sectionTop < viewportHeight) {
      const scrolledDistance = viewportHeight - sectionTop;
      const totalScrollDistance = sectionHeight + viewportHeight;
      progress = Math.max(0, Math.min(1, scrolledDistance / totalScrollDistance));
    }

    setScrollProgress(progress);

    // FIXED: Simplified card transition logic
    let newActiveCard = 0;
    if (progress >= 0.33 && progress < 0.66) {
      newActiveCard = 1;
    } else if (progress >= 0.66) {
      newActiveCard = 2;
    }

    // CRITICAL FIX: Only update if actually changed
    setActiveCard(prevActive => {
      if (prevActive !== newActiveCard) {
        console.log('🔄 Card transition:', {
          from: prevActive,
          to: newActiveCard,
          progress: Math.round(progress * 1000) / 1000,
          timestamp: Date.now()
        });
        return newActiveCard;
      }
      return prevActive;
    });

    scrollTicking.current = false;
  }, []); // FIXED: No dependencies to prevent re-creation

  const handleScroll = React.useCallback(() => {
    if (!scrollTicking.current) {
      requestAnimationFrame(updateScrollProgress);
      scrollTicking.current = true;
    }
  }, [updateScrollProgress]);

  React.useEffect(() => {
    if (prefersReducedMotion && !isMobile) return;

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleScroll, { passive: true });

    // Initial calculation
    setTimeout(() => {
      updateScrollProgress();
    }, 200);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleScroll);
    };
  }, [handleScroll, prefersReducedMotion, isMobile]);

  // DEBUG: Track render cycles
  React.useEffect(() => {
    setDebugInfo(prev => ({
      ...prev,
      renderCount: prev.renderCount + 1,
      lastUpdate: Date.now()
    }));
  });

  return (
    <Box
      ref={sectionRef}
      component="section"
      aria-labelledby="urgency-heading"
      sx={{
        height: { xs: 'auto', md: '300vh' },
        minHeight: { xs: '100vh', md: '300vh' },
        position: 'relative',
        scrollSnapAlign: 'start',
        scrollSnapStop: 'always',
        borderBottom: '1px solid rgba(0, 212, 255, 0.10)',
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        [theme => theme.breakpoints.down('md')]: {
          height: 'auto',
          minHeight: 'auto',
          padding: theme => theme.spacing(8, 0),
          scrollSnapAlign: 'none',
          scrollSnapStop: 'normal',
        },
      }}
    >
      {/* Left Side - Scrolling Cards */}
      <Box
        sx={{
          flex: '1 1 50%',
          position: { xs: 'static', md: 'sticky' },
          top: { xs: 'auto', md: 0 },
          height: { xs: 'auto', md: '100vh' },
          display: 'flex',
          alignItems: { xs: 'flex-start', md: 'center' },
          justifyContent: 'center',
          backgroundColor: 'rgba(255,255,255,0.02)',
          overflow: 'hidden',
          p: { xs: 4, md: 4 },
          pt: { xs: 6, md: 4 },
        }}
      >
        <Box
          sx={{
            width: '100%',
            maxWidth: 420,
            display: 'flex',
            flexDirection: 'column',
            gap: { xs: 3, md: 0 },
            position: 'relative',
          }}
        >
          {cards.map((card, index) => {
            const isActive = activeCard === index;

            // CRITICAL DEBUG: Log what should be visible
            console.log(`🎴 Card ${index} (${card.title.split(' ')[0]}):`, {
              isActive,
              isMobile,
              shouldShow: isMobile || isActive,
              willReturn: (!isMobile && !isActive) ? 'null' : 'component'
            });

            // FIXED: More explicit conditional rendering
            const shouldRender = isMobile || isActive;
            if (!shouldRender) {
              console.log(`❌ Card ${index} NOT RENDERING`);
              return null;
            }

            console.log(`✅ Card ${index} RENDERING`);

            return (
              <Fade
                key={index}
                in={true}
                timeout={{
                  enter: prefersReducedMotion ? 0 : 600,
                  exit: prefersReducedMotion ? 0 : 400,
                }}
              >
                <Box
                  sx={{
                    // FIXED: Ensure proper positioning
                    position: { xs: 'static', md: 'absolute' },
                    top: { xs: 'auto', md: '50%' },
                    left: { xs: 'auto', md: 0 },
                    right: { xs: 'auto', md: 0 },
                    transform: {
                      xs: 'none',
                      md: 'translateY(-50%)'
                    },
                    // CRITICAL FIX: Ensure active card is fully visible
                    opacity: isActive ? 1 : (isMobile ? 1 : 0),
                    visibility: isActive ? 'visible' : (isMobile ? 'visible' : 'hidden'),
                    transition: prefersReducedMotion
                      ? 'none'
                      : 'opacity 0.6s ease, visibility 0.6s ease',
                    zIndex: isActive ? 10 : 1,
                    mb: { xs: 3, md: 0 },
                    // DEBUG: Add border to see card boundaries
                    border: process.env.NODE_ENV === 'development'
                      ? `2px solid ${isActive ? '#00ff00' : '#ff0000'}`
                      : 'none',
                  }}
                >
                  <CardEmphasis
                    sx={{
                      border: `1px solid rgba(255, 107, 107, ${isActive ? 0.6 : 0.3})`,
                      boxShadow: isActive
                        ? '0 8px 32px rgba(255, 107, 107, 0.25)'
                        : '0 4px 16px rgba(255, 107, 107, 0.1)',
                      transition: prefersReducedMotion
                        ? 'none'
                        : 'border-color 0.6s ease, box-shadow 0.6s ease',
                    }}
                  >
                    <CardContent sx={{ p: 3 }}>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, color: '#ff6b6b' }}>
                        {card.title}
                      </Typography>

                      <Box
                        sx={{
                          width: '100%',
                          height: 200,
                          mb: 2,
                          borderRadius: 2,
                          overflow: 'hidden',
                          backgroundColor: 'rgba(255,255,255,0.05)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                      >
                        <img
                          src={card.image}
                          alt={card.imageAlt}
                          style={{
                            width: '100%',
                            height: '100%',
                            objectFit: 'contain',
                            objectPosition: 'center'
                          }}
                          loading="lazy"
                        />
                      </Box>

                      <Typography sx={{ color: 'rgba(255,255,255,0.85)', lineHeight: 1.6 }}>
                        {card.content}
                      </Typography>
                    </CardContent>
                  </CardEmphasis>
                </Box>
              </Fade>
            );
          })}
        </Box>

        {/* Enhanced Debug Info */}
        {process.env.NODE_ENV === 'development' && (
          <Box
            sx={{
              position: 'absolute',
              right: 16,
              top: 16,
              padding: 2,
              backgroundColor: 'rgba(0, 0, 0, 0.8)',
              borderRadius: 1,
              fontSize: 11,
              color: '#00d4ff',
              fontFamily: 'monospace',
              zIndex: 100,
              maxWidth: 200,
            }}
          >
            <div>🎯 Active: {activeCard + 1}/3</div>
            <div>📱 Mobile: {isMobile ? 'Yes' : 'No'}</div>
            <div>📊 Progress: {Math.round(scrollProgress * 100)}%</div>
            <div>🔄 Renders: {debugInfo.renderCount}</div>
            <div>⏰ Last: {new Date(debugInfo.lastUpdate).toLocaleTimeString()}</div>
            <div style={{ marginTop: 8, fontSize: 10 }}>
              Should show: {cards.map((_, i) =>
                (isMobile || activeCard === i) ? (i + 1) : ''
              ).filter(Boolean).join(', ') || 'None'}
            </div>
          </Box>
        )}
      </Box>

      {/* Right Side - Fixed Content */}
      <Box
        sx={{
          flex: '1 1 50%',
          position: { xs: 'static', md: 'sticky' },
          top: { xs: 'auto', md: 0 },
          height: { xs: 'auto', md: '100vh' },
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          flexDirection: 'column',
          pt: { xs: 4, md: 1 },
          pb: { xs: 4, md: 6 },
          px: 0,
        }}
      >
        <ContentContainer maxWidth="lg">
          <InViewFade>
            <Typography id="urgency-heading" variant="h4" sx={{ fontWeight: 800, mb: 4, color: '#ff6b6b' }}>
              온라인 영향력은 곧 정치 생존입니다
            </Typography>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#00d4ff' }}>
              패러다임이 바뀌었습니다
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.85)', mb: 3, lineHeight: 1.7, fontSize: '1.1rem' }}>
              과거에는 지역 현안만 잘 챙기면 재선이 보장되었습니다. 하지만 이제는 다릅니다.
              유권자들은 검색으로 후보를 판단합니다.
            </Typography>

            <Box sx={{
              p: 3,
              borderLeft: '4px solid #ff6b6b',
              backgroundColor: 'rgba(255, 107, 107, 0.1)',
              borderRadius: '0 8px 8px 0',
              mb: 4
            }}>
              <Typography sx={{
                color: '#ff6b6b',
                fontWeight: 600,
                fontStyle: 'italic',
                lineHeight: 1.6,
                fontSize: '1.1rem'
              }}>
                "검색되지 않는 정치인은 정치적으로 존재하지 않는다"
              </Typography>
              <Typography sx={{
                color: 'rgba(255,255,255,0.7)',
                fontSize: '0.9rem',
                mt: 1
              }}>
                - 디지털 정치학의 새로운 법칙
              </Typography>
            </Box>

            <InViewFade>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
                <CTAButton aria-label="지금 시작하기" onClick={onCTAClick}>
                  지금 시작하기
                </CTAButton>
              </Stack>
            </InViewFade>
          </InViewFade>
        </ContentContainer>
      </Box>
    </Box>
  );
};

// Additional fixes for better card display:

// 1. CSS Override for absolute positioning conflicts
const additionalCSS = `
/* Ensure only one card shows on desktop */
@media (min-width: 900px) {
  .parallax-cards-container .card-wrapper:not(.active) {
    opacity: 0 !important;
    visibility: hidden !important;
    pointer-events: none !important;
  }

  .parallax-cards-container .card-wrapper.active {
    opacity: 1 !important;
    visibility: visible !important;
    pointer-events: auto !important;
  }
}
`;

export { ParallaxUrgencySection, additionalCSS };