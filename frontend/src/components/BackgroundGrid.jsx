import React from 'react';
import { Box, useTheme } from '@mui/material';

// Optimized background grid using Canvas for better performance
// Reduced from 37+ DOM elements to a single canvas element
const BackgroundGrid = () => {
  const theme = useTheme();
  const horizontalLineColor = theme.palette.ui.gridLineHorizontal || 'rgba(28, 161, 82, 0.9)';
  const verticalLineColor = theme.palette.ui.gridLineVertical || 'rgba(28, 161, 82, 0.8)';
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // Set canvas size
    const updateSize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      draw();
    };

    const draw = () => {
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;

      ctx.clearRect(0, 0, width, height);

      // Center point (horizon at 50vh)
      const centerX = width / 2;
      const centerY = height / 2;

      // Draw horizontal lines (perspective grid)
      ctx.strokeStyle = horizontalLineColor;
      ctx.lineWidth = 1;
      const horizontalOffsets = [5, 12, 20, 29, 39, 51, 65, 82, 102, 126, 155, 190, 232, 282, 342, 415, 500, 600, 720, 860];

      horizontalOffsets.forEach(offset => {
        ctx.beginPath();
        ctx.moveTo(0, centerY + offset);
        ctx.lineTo(width, centerY + offset);
        ctx.stroke();
      });

      // Draw vertical lines (radial from center)
      ctx.strokeStyle = verticalLineColor;
      const angles = [
        0, -20, -35, -45, -52, -58, -63, -67, -70, -73, -75, -77, -79, -81, -83, -85, -87, -88, -89, -90,
        20, 35, 45, 52, 58, 63, 67, 70, 73, 75, 77, 79, 81, 83, 85, 87, 88, 89, 90
      ];

      angles.forEach(angle => {
        const rad = (angle * Math.PI) / 180;
        const length = Math.max(width, height) * 2;

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + Math.sin(rad) * length,
          centerY + Math.cos(rad) * length
        );
        ctx.stroke();
      });
    };

    updateSize();
    window.addEventListener('resize', updateSize);

    return () => window.removeEventListener('resize', updateSize);
  }, [horizontalLineColor, verticalLineColor]);

  return (
    <Box
      component="canvas"
      ref={canvasRef}
      aria-hidden
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100vh',
        zIndex: -2,
        pointerEvents: 'none',
      }}
    />
  );
};

export default BackgroundGrid;