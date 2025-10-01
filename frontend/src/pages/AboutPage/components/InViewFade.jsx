import React from 'react';
import { Box, Fade, useMediaQuery } from '@mui/material';

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

export default InViewFade;
