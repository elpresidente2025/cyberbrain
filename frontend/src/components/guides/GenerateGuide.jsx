import React from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  useTheme
} from '@mui/material';
import { CheckCircleOutline, Edit } from '@mui/icons-material';

const GenerateGuide = () => {
  const theme = useTheme();
  const steps = [
    {
      title: '1. 주제 입력하기',
      description: '작성하려는 원고의 핵심 내용을 한 문장으로 요약해 주세요.',
      examples: [
        { bad: '❌ 나쁜 예: "교통 문제"', color: '#d22730' },
        { good: '⭐ 좋은 예: "성수동 학교 앞 스쿨존 과속단속 카메라 설치 건의"', color: '#4caf50' }
      ]
    },
    {
      title: '2. 참고자료 입력 (필수/선택)',
      description: 'AI가 글을 쓸 때 참고할 구체적인 정보를 제공합니다.',
      tips: [
        '① 내 입장/페이스북 글: 나의 주장이나 논조가 담긴 글을 첫 번째 칸에 입력하세요.',
        '② 뉴스/데이터: 기사 링크(URL)는 분석되지 않습니다. 본문 텍스트를 직접 복사해서 붙여넣으세요.'
      ]
    },
    {
      title: '3. 노출 희망 검색어 (핵심)',
      description: '네이버 검색 상위 노출을 위해 가장 중요한 단계입니다.',
      examples: [
        { bad: '❌ 욕심 부린 예: "전현희, 성동구, 유세, 반응, 후기..." (노출 안 됨)', color: '#d22730' },
        { good: '⭐ 효과적인 예: "성수동 카페거리 유세"', color: '#4caf50' }
      ],
      tips: [
        '검색어는 최대 2개까지만 입력 가능합니다. (3개 이상 입력 시 자동 차단)',
        '지역명 + 현안 (예: "왕십리역 출구 에스컬레이터") 조합이 가장 효과적입니다.'
      ]
    },
    {
      title: '4. 생성 및 발행',
      description: '나머지는 AI 비서가 알아서 처리합니다.',
      features: [
        '생성된 원고는 반드시 사용자가 최종 검수 후 발행하세요.',
        '하루 3회 이상 발행 시 스팸으로 분류될 수 있으니 주의하세요.'
      ]
    }
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Edit sx={{ color: '#003A87', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          원고 생성하기
        </Typography>
      </Box>

      {steps.map((step, index) => (
        <Box key={index} sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1, color: '#003A87' }}>
            {step.title}
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {step.description}
          </Typography>

          {step.examples && (
            <Box sx={{ mb: 2 }}>
              {step.examples.map((example, exIndex) => (
                <Typography key={exIndex} variant="body2" sx={{
                  color: example.color,
                  fontWeight: 500,
                  mb: 0.5
                }}>
                  {example.bad || example.good}
                </Typography>
              ))}
            </Box>
          )}

          {step.categories && (
            <List dense>
              {step.categories.map((category, catIndex) => (
                <ListItem key={catIndex} sx={{ py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <CheckCircleOutline sx={{ fontSize: 16, color: '#4caf50' }} />
                  </ListItemIcon>
                  <ListItemText primary={category} primaryTypographyProps={{ variant: 'body2' }} />
                </ListItem>
              ))}
            </List>
          )}

          {step.tips && (
            <List dense>
              {step.tips.map((tip, tipIndex) => (
                <ListItem key={tipIndex} sx={{ py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <CheckCircleOutline sx={{ fontSize: 16, color: '#2196f3' }} />
                  </ListItemIcon>
                  <ListItemText primary={tip} primaryTypographyProps={{ variant: 'body2' }} />
                </ListItem>
              ))}
            </List>
          )}

          {step.features && (
            <List dense>
              {step.features.map((feature, fIndex) => (
                <ListItem key={fIndex} sx={{ py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <CheckCircleOutline sx={{
                      fontSize: 16,
                      color: theme.palette.mode === 'dark' ? '#ffab40' : '#ff9800'
                    }} />
                  </ListItemIcon>
                  <ListItemText primary={feature} primaryTypographyProps={{ variant: 'body2' }} />
                </ListItem>
              ))}
            </List>
          )}
        </Box>
      ))}

      {/* 주의사항 섹션 */}
      <Box sx={{
        mt: 4,
        p: 3,
        bgcolor: theme.palette.mode === 'dark' ? 'rgba(255, 152, 0, 0.1)' : '#fff3e0',
        borderRadius: 1,
        border: theme.palette.mode === 'dark' ? '1px solid rgba(255, 152, 0, 0.3)' : '1px solid #ffb74d'
      }}>
        <Typography variant="h6" sx={{
          fontWeight: 600,
          mb: 2,
          color: theme.palette.mode === 'dark' ? '#ffab40' : '#e65100',
          display: 'flex',
          alignItems: 'center'
        }}>
          ⚠️ 블로그 발행 시 주의사항
        </Typography>
        <List dense>
          <ListItem sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{
                fontSize: 16,
                color: theme.palette.mode === 'dark' ? '#ffab40' : '#ff9800'
              }} />
            </ListItemIcon>
            <ListItemText
              primary="하루 3회 초과 발행 시 네이버 블로그에서 스팸 블로그로 분류될 수 있습니다"
              primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
            />
          </ListItem>
          <ListItem sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{
                fontSize: 16,
                color: theme.palette.mode === 'dark' ? '#ffab40' : '#ff9800'
              }} />
            </ListItemIcon>
            <ListItemText
              primary="생성된 원고는 반드시 사용자가 최종 검수 및 수정 후 발행하세요"
              primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
            />
          </ListItem>
          <ListItem sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{
                fontSize: 16,
                color: theme.palette.mode === 'dark' ? '#ffab40' : '#ff9800'
              }} />
            </ListItemIcon>
            <ListItemText
              primary="적절한 간격(최소 3시간 이상 권장)을 두고 발행하여 자연스러운 블로그 운영을 유지하세요"
              primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
            />
          </ListItem>
        </List>
      </Box>
    </Box>
  );
};

export default GenerateGuide;