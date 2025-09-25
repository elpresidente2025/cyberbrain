import React from 'react';
import { Box } from '@mui/material';

// Centralized background grid with extreme perspective and a mid-page horizon.
// Uses CSS variables from :root defined in index.css.
const BackgroundGrid = () => {
  return (
    <Box
      aria-hidden
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100vh',
        zIndex: -2,
        pointerEvents: 'none',
        perspective: 'var(--grid-perspective)',
        transformStyle: 'preserve-3d',
        overflow: 'hidden',
      }}
    >

      {/* 원근감 가로선들 - 수렴점에서 시작해서 점점 촘촘하게 */}
      <Box sx={{ position: 'fixed', top: '50vh', left: '50%', width: '1px', height: '1px', zIndex: -1 }}>
        {/* 가로선들 - 아래로 갈수록 듬성하고 두꺼워짐 */}
        <Box sx={{ position: 'absolute', top: '5px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '12px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '20px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '29px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '39px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '51px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '65px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '82px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '102px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '126px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '155px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '190px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '232px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '282px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '342px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '415px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '500px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '600px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '720px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
        <Box sx={{ position: 'absolute', top: '860px', left: '-200vw', width: '400vw', height: '1px', background: 'rgba(0, 255, 255, 0.9)' }} />
      </Box>
      
      {/* 수학적으로 계산된 원근감 격자선들 */}
      <Box sx={{ position: 'fixed', top: '50vh', left: '50%', width: '1px', height: '1px', zIndex: -0.5 }}>
        {/* 중앙 수직선 - 푸터 위에서 끝남 */}
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(0deg)' }} />

        {/* 좌측 - 각도별 간격: 중앙에서 멀어질수록 지수적으로 촘촘 */}
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-20deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-35deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-45deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-52deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-58deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-63deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-67deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-70deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-73deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-75deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-77deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-79deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-81deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-83deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-85deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-87deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-88deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-89deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(-90deg)' }} />

        {/* 우측 - 대칭으로 배치 */}
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(20deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(35deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(45deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(52deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(58deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(63deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(67deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(70deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(73deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(75deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(77deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(79deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(81deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(83deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(85deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(87deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(88deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(89deg)' }} />
        <Box sx={{ position: 'absolute', top: 0, left: 0, width: '1px', height: '200vh', background: 'rgba(0, 200, 200, 0.8)', transformOrigin: 'top', transform: 'rotate(90deg)' }} />
      </Box>

    </Box>
  );
};

export default BackgroundGrid;