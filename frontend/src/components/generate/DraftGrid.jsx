// frontend/src/components/generate/DraftGrid.jsx
import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardActions,
  Button,
  Divider,
  Paper,
  Chip,
  Tooltip,
  useTheme
} from '@mui/material';
import { AutoAwesome, Save, CheckCircle, Warning, Speed } from '@mui/icons-material';

export default function DraftGrid({
  items = [],
  onSelect,
  onSave,
  maxAttempts = 3,
  isMobile = false,
  user = null  // 🆕 사용자 정보 추가
}) {
  const theme = useTheme();
  if (items.length === 0) {
    return (
      <Paper elevation={0} sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>
        <AutoAwesome sx={{ fontSize: 64, mb: 2, color: theme.palette.ui?.header || '#152484' }} />
        <Typography variant="h6" gutterBottom sx={{ color: 'black' }}>
          AI 원고 생성을 시작해보세요
        </Typography>
        <Typography variant="body2" sx={{ color: 'black' }}>
          상단 폼을 작성하고 "원고 생성 시도" 버튼을 클릭하세요.<br />
          한 번의 생성에서 최대 {maxAttempts}회까지 시도할 수 있습니다.
        </Typography>
      </Paper>
    );
  }

  // 모바일: 세로 배치, 데스크톱: 가로 배치
  const containerStyle = isMobile ? {
    display: 'flex',
    flexDirection: 'column',
    gap: 2
  } : {
    display: 'flex',
    justifyContent: 'center',
    gap: 2
  };

  // 카드 크기 계산
  const getCardWidth = () => {
    if (isMobile) return '100%';
    if (items.length === 1) return '600px';
    if (items.length === 2) return '400px';
    return '350px';
  };

  const getContentHeight = () => {
    if (isMobile) return 400;
    if (items.length === 1) return 400;
    if (items.length === 2) return 300;
    return 200;
  };

  const getFontSize = () => {
    if (isMobile) return '0.875rem';
    return items.length === 1 ? '0.95rem' : '0.875rem';
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {isMobile ? "미리보기 카드 리스트" : "미리보기"}
      </Typography>
      
      <Box sx={containerStyle}>
        {items.map((draft, index) => (
          <Card 
            key={draft.id || index} 
            elevation={0}
            sx={{ 
              width: getCardWidth(),
              maxWidth: '100%',
              bgcolor: ['#003a87', '#55207d', '#006261'][index] || '#003a87',
              color: 'white',
              display: 'flex', 
              flexDirection: 'column',
              cursor: 'pointer',
              transition: 'transform 0.2s ease-in-out',
              '&:hover': {
                transform: isMobile ? 'none' : 'translateY(-4px)',
                boxShadow: 3
              }
            }}
            onClick={() => onSelect?.(draft)}
          >
            <CardContent sx={{ flexGrow: 1 }}>
              <Typography
                variant="h6"
                component="div"
                gutterBottom
                sx={{
                  color: '#ffffff !important',
                  textAlign: 'center',
                  fontWeight: 'bold'
                }}
              >
                초안 {index + 1}
              </Typography>
              
              <Box sx={{
                bgcolor: '#f5f5f5',
                p: 2,
                borderRadius: 1,
                mt: 1,
                // 모든 텍스트 강제로 검정색
                '& *': {
                  color: '#000000 !important'
                }
              }}>
                <Typography variant="subtitle1" sx={{
                  color: '#000000 !important',
                  fontWeight: 'bold',
                  mb: 1,
                  '&, & *': {
                    color: '#000000 !important'
                  }
                }}>
                  제목: {draft.title || `${draft.category} - ${draft.subCategory || '일반'}`}
                </Typography>
                
                <Divider sx={{ my: 1, borderColor: 'rgba(0,0,0,0.1)' }} />
                
                <Typography variant="body2" sx={{
                  maxHeight: getContentHeight(),
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  color: '#000000 !important',
                  lineHeight: 1.6,
                  fontSize: getFontSize()
                }}>
                  {draft.content ? 
                    draft.content.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ')
                    : '원고 내용이 없습니다.'
                  }
                </Typography>
              </Box>
            </CardContent>
            
            {/* 🤖 Multi-Agent 메타데이터 (관리자/테스터만) */}
            {(user?.isAdmin || user?.isTester) && draft.multiAgent?.enabled && (
              <Box sx={{
                px: 2,
                py: 1,
                display: 'flex',
                gap: 0.5,
                flexWrap: 'wrap',
                borderTop: '1px solid rgba(255,255,255,0.2)'
              }}>
                {/* SEO 통과 여부 */}
                {draft.multiAgent.seoPassed != null && (
                  <Tooltip title="네이버 SEO 통과 여부">
                    <Chip
                      icon={<Speed sx={{ fontSize: 14 }} />}
                      label={draft.multiAgent.seoPassed ? 'SEO 통과' : 'SEO 실패'}
                      size="small"
                      sx={{
                        height: 20,
                        fontSize: '0.7rem',
                        bgcolor: draft.multiAgent.seoPassed ? 'success.main' : 'error.main',
                        color: 'white',
                        '& .MuiChip-icon': { color: 'white' }
                      }}
                    />
                  </Tooltip>
                )}

                {/* 선거법 검수 */}
                {draft.multiAgent.compliancePassed != null && (
                  <Tooltip title={draft.multiAgent.compliancePassed ? '선거법 검수 통과' : `선거법 주의사항 ${draft.multiAgent.complianceIssues || 0}개`}>
                    <Chip
                      icon={draft.multiAgent.compliancePassed ?
                        <CheckCircle sx={{ fontSize: 14 }} /> :
                        <Warning sx={{ fontSize: 14 }} />
                      }
                      label={draft.multiAgent.compliancePassed ? '검수통과' : `주의 ${draft.multiAgent.complianceIssues || 0}`}
                      size="small"
                      sx={{
                        height: 20,
                        fontSize: '0.7rem',
                        bgcolor: draft.multiAgent.compliancePassed ? 'success.main' : 'warning.main',
                        color: 'white',
                        '& .MuiChip-icon': { color: 'white' }
                      }}
                    />
                  </Tooltip>
                )}

                {/* 생성 시간 */}
                {draft.multiAgent.duration && (
                  <Tooltip title="AI 생성 소요시간">
                    <Chip
                      label={`${Math.round(draft.multiAgent.duration / 1000)}초`}
                      size="small"
                      sx={{
                        height: 20,
                        fontSize: '0.7rem',
                        bgcolor: 'rgba(255,255,255,0.2)',
                        color: 'white'
                      }}
                    />
                  </Tooltip>
                )}
              </Box>
            )}

            <CardActions sx={{ justifyContent: 'space-between', px: 2, pb: 2, flexWrap: 'wrap' }}>
              <Typography variant="caption" sx={{ color: '#ffffff !important' }}>
                {draft.generatedAt ?
                  new Date(draft.generatedAt).toLocaleString() :
                  new Date().toLocaleString()
                }
              </Typography>

              <Button
                size="small"
                startIcon={<Save />}
                onClick={(e) => {
                  e.stopPropagation();
                  onSave?.(draft);
                }}
                sx={{
                  color: 'white',
                  borderColor: 'white',
                  '&:hover': {
                    borderColor: 'rgba(255,255,255,0.8)',
                    backgroundColor: 'rgba(255,255,255,0.1)'
                  }
                }}
                variant="outlined"
              >
                저장
              </Button>
            </CardActions>
          </Card>
        ))}
      </Box>
    </Box>
  );
}
