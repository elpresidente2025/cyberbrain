import React from 'react';
import {
  Box,
  Typography,
} from '@mui/material';
import { LightbulbOutlined } from '@mui/icons-material';

const TipsGuide = () => {
  const categories = [
    {
      title: '주제 정할 때',
      tips: [
        { label: '시의성 있게', examples: ['"추석 연휴 교통 대책"', '"겨울철 한파 대비 점검"'] },
        { label: '지역 맞춤형', examples: ['"○○시장 상인회와의 간담회"', '"우리 동네 놀이터 안전점검"'] },
        { label: '구체적인 숫자', examples: ['"어린이집 3곳 추가 건립"', '"버스노선 12번 연장 요청"'] }
      ]
    },
    {
      title: '참고자료 활용',
      tips: [
        { label: '뉴스', examples: ['핵심 내용 2-3줄만 복사'] },
        { label: '통계', examples: ['"전년 대비 30% 증가" 같은 수치'] },
        { label: '현장', examples: ['"주민 40여명과 간담회" 구체적 상황'] }
      ]
    },
    {
      title: '상태별 주의사항',
      tips: [
        { label: '예비', examples: ['공직 관련 표현 자제 ("의원으로서" 사용 금지)'] },
        { label: '후보', examples: ['선거운동 기간 확인 후 활동'] },
        { label: '현역', examples: ['구체적인 의정활동 성과 중심'] }
      ]
    }
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <LightbulbOutlined sx={{ color: '#f57c00', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          더 좋은 글을 위한 팁
        </Typography>
      </Box>

      {categories.map((category, index) => (
        <Box key={index} sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, color: '#f57c00' }}>
            {category.title}
          </Typography>
          {category.tips.map((tip, tipIndex) => (
            <Box key={tipIndex} sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                {tip.label}
              </Typography>
              {tip.examples && (
                <Box sx={{ ml: 2 }}>
                  {tip.examples.map((example, exIndex) => (
                    <Typography key={exIndex} variant="body2" sx={{ 
                      color: '#666',
                      fontStyle: 'italic',
                      mb: 0.5
                    }}>
                      • {example}
                    </Typography>
                  ))}
                </Box>
              )}
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  );
};

export default TipsGuide;