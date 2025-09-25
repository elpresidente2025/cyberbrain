import React from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import { CheckCircleOutline, List as ListIcon } from '@mui/icons-material';

const ManagementGuide = () => {
  const features = [
    {
      title: '원고 목록에서',
      items: [
        '날짜순 정렬: 최신 글부터 확인',
        '카테고리 필터: 종류별로 분류해서 보기',
        '검색 기능: 제목이나 내용으로 찾기'
      ]
    },
    {
      title: '개별 원고 관리',
      items: [
        '수정: 내용을 직접 편집 가능',
        '복사: 클립보드로 복사해서 SNS 게시',
        '삭제: 불필요한 원고 정리'
      ]
    }
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <ListIcon sx={{ color: '#55207D', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          원고 관리
        </Typography>
      </Box>

      {features.map((feature, index) => (
        <Box key={index} sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1, color: '#55207D' }}>
            {feature.title}
          </Typography>
          <List dense>
            {feature.items.map((item, itemIndex) => (
              <ListItem key={itemIndex} sx={{ py: 0.5 }}>
                <ListItemIcon sx={{ minWidth: 24 }}>
                  <CheckCircleOutline sx={{ fontSize: 16, color: '#55207D' }} />
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

export default ManagementGuide;