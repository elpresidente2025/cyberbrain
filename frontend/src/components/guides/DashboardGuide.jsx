import React from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import { CheckCircleOutline, Dashboard } from '@mui/icons-material';

const DashboardGuide = () => {
  const sections = [
    {
      title: '인사말 카드',
      items: [
        '왼쪽: 내 정보, 플랜 현황, 이달 사용량',
        '가운데: 당원 인증 상태 (인증일, 다음 갱신일)',
        '오른쪽: 원고 생성 / 프로필 수정 바로가기'
      ]
    },
    {
      title: '선거 D-Day',
      items: [
        '다음 선거일까지 실시간 카운트',
        '현재 시기의 선거법 주의사항 안내',
        '직책에 따라 총선/지선 자동 구분'
      ]
    },
    {
      title: '공지사항',
      items: [
        '서비스 업데이트, 중요 알림사항',
        '빨간 "중요" 태그가 있으면 꼭 확인하세요'
      ]
    },
    {
      title: '최근 생성한 글',
      items: [
        '이전에 만든 원고들을 쉽게 다시 찾기',
        '제목 클릭으로 바로 확인 가능'
      ]
    }
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Dashboard sx={{ color: '#006261', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          대시보드 활용
        </Typography>
      </Box>

      {sections.map((section, index) => (
        <Box key={index} sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1, color: '#006261' }}>
            {section.title}
          </Typography>
          <List dense>
            {section.items.map((item, itemIndex) => (
              <ListItem key={itemIndex} sx={{ py: 0.5 }}>
                <ListItemIcon sx={{ minWidth: 24 }}>
                  <CheckCircleOutline sx={{ fontSize: 16, color: '#006261' }} />
                </ListItemIcon>
                <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
              </ListItem>
            ))}
          </List>
        </Box>
      ))}
    </Box>
  );
};

export default DashboardGuide;