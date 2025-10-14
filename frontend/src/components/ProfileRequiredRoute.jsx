import React from 'react';
import { Navigate } from 'react-router-dom';
import { 
  Box, 
  Container, 
  Paper, 
  Typography, 
  Alert, 
  Button,
  LinearProgress,
  useTheme
} from '@mui/material';
import { AccountCircle, Edit } from '@mui/icons-material';
import { useAuth } from '../hooks/useAuth';

const ProfileRequiredRoute = ({ children }) => {
  const theme = useTheme();
  const { user, loading } = useAuth();

  console.log('🔒 ProfileRequiredRoute 상태:', { 
    user: !!user, 
    loading, 
    bio: user?.bio,
    hasProfile: !!(user?.bio && user.bio.trim().length > 0)
  });

  // 로딩 중
  if (loading) {
    return (
      <Box sx={{ width: '100%', mt: 2 }}>
        <LinearProgress />
      </Box>
    );
  }

  // 인증되지 않은 사용자는 로그인 페이지로
  if (!user) {
    return <Navigate to="/" replace />;
  }

  // 관리자는 프로필 체크 제외
  if (user.isAdmin || user.role === 'admin') {
    return children;
  }

  // 자기소개가 없거나 비어있는 경우
  const hasBio = user.bio && user.bio.trim().length > 0;
  if (!hasBio) {
    return (
      <Box sx={{ 
        minHeight: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        bgcolor: '#f5f5f5'
      }}>
        <Container maxWidth="sm">
          <Paper sx={{ p: 4, textAlign: 'center' }}>
            <Box sx={{ mb: 3 }}>
              <AccountCircle sx={{ fontSize: 80, color: theme.palette.ui?.header || '#152484', mb: 2 }} />
              <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1, color: theme.palette.ui?.header || '#152484' }}>
                프로필 설정이 필요합니다
              </Typography>
              <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
                전자두뇌비서관 서비스를 이용하기 위해서는 자기소개 작성이 필요합니다.
              </Typography>
            </Box>

            <Alert severity="info" sx={{ mb: 3, textAlign: 'left' }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>자기소개가 필요한 이유:</strong>
              </Typography>
              <Typography variant="body2" component="ul" sx={{ ml: 2 }}>
                <li>개인화된 원고 생성을 위해</li>
                <li>정치적 성향과 지역 특성 반영</li>
                <li>더 적합한 콘텐츠 제공</li>
              </Typography>
            </Alert>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Button
                variant="contained"
                size="large"
                startIcon={<Edit />}
                onClick={() => window.location.href = '/profile'}
                sx={{
                  bgcolor: theme.palette.ui?.header || '#152484',
                  py: 1.5,
                  '&:hover': { bgcolor: '#003A87' }
                }}
              >
                프로필 설정하기
              </Button>
              
              <Button
                variant="outlined"
                onClick={() => window.location.href = '/dashboard'}
                sx={{
                  color: theme.palette.ui?.header || '#152484',
                  borderColor: theme.palette.ui?.header || '#152484',
                  '&:hover': { 
                    borderColor: '#003A87',
                    bgcolor: 'rgba(21, 36, 132, 0.04)'
                  }
                }}
              >
                대시보드로 돌아가기
              </Button>
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 3 }}>
              💡 자기소개는 언제든지 프로필 설정에서 수정할 수 있습니다.
            </Typography>
          </Paper>
        </Container>
      </Box>
    );
  }

  // 프로필이 완성된 경우 정상 렌더링
  return children;
};

export default ProfileRequiredRoute;