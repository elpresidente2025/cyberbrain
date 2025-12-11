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
      description: '대시보드에서 "새 원고 생성" 버튼을 클릭하세요.',
      examples: [
        { bad: '❌ 나쁜 예: "교통 문제"', color: '#d22730' },
        { good: '⭐ 좋은 예: "○○동 스쿨존 신호등 설치 건의"', color: '#4caf50' },
        { good: '⭐ 좋은 예: "청년 월세 지원 조례 발의 계획"', color: '#4caf50' }
      ]
    },
    {
      title: '2. 카테고리 선택',
      description: '글의 목적에 맞게 선택하세요',
      categories: [
        '일상 소통: 인사말, 안부 전하기',
        '정책 제안: 새로운 정책이나 법안 제안',
        '의정활동 보고: 현장 방문, 회의 참석 후기',
        '시사 분석: 뉴스나 사회 이슈에 대한 의견',
        '지역 현안: 우리 지역 문제 해결방안'
      ]
    },
    {
      title: '3. 참고자료 추가 (선택)',
      description: '더 정확한 글을 원한다면',
      tips: [
        '관련 뉴스 기사 링크나 내용',
        '정부 발표자료, 통계 수치',
        '현장에서 확인한 내용',
        '주민 건의사항'
      ]
    },
    {
      title: '4. 생성 완료',
      description: '1-2분 후 완성된 원고를 확인하세요',
      features: [
        '마음에 들지 않으면 재생성 가능 (최대 3회)',
        '복사하기로 SNS에 바로 사용'
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