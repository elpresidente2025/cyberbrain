// frontend/src/components/admin/ErrorsMiniTable.jsx
import React, { useState, useEffect } from 'react';
import {
  Typography,
  Box,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Chip,
  Tooltip,
  useTheme
} from '@mui/material';
import { LoadingSkeleton } from '../loading';
import { Download, Warning, Error, Refresh } from '@mui/icons-material';
import HongKongNeonCard from '../HongKongNeonCard';
import { useAuth } from '../../hooks/useAuth';
import { getErrorLogs } from '../../services/firebaseService';

function ErrorsMiniTable() {
  const theme = useTheme();
  const { user } = useAuth();
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRecentErrors = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // HTTP getErrorLogs 함수 호출
      const result = await getErrorLogs();
      
      console.log('🔍 에러 로그 조회 결과:', result);
      
      // 응답 구조 확인 및 처리
      if (result.success && result.data && result.data.errors) {
        setErrors(result.data.errors);
      } else if (result.errors) {
        setErrors(result.errors);
      } else if (Array.isArray(result)) {
        setErrors(result);
      } else {
        console.warn('예상과 다른 응답 구조:', result);
        setErrors([]);
      }
    } catch (err) {
      console.error('에러 로그 조회 실패:', err);
      setError(err.message);
      setErrors([]); // 에러 시 빈 배열로 설정
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.isAdmin) {
      fetchRecentErrors();
    }
  }, [user]);

  const exportErrorsCsv = async () => {
    try {
      console.log('📊 에러 로그 CSV 내보내기...');
      
      // 전체 에러 데이터 가져오기 - HTTP getErrorLogs 호출
      const result = await getErrorLogs();

      console.log('📊 CSV 내보내기용 데이터:', result);

      let errorData = [];
      
      // 응답 구조에 따라 데이터 추출
      if (result.success && result.data && result.data.errors) {
        errorData = result.data.errors;
      } else if (result.errors) {
        errorData = result.errors;
      } else if (Array.isArray(result)) {
        errorData = result;
      }
      
      if (errorData.length === 0) {
        alert('내보낼 에러 데이터가 없습니다.');
        return;
      }

      // CSV 헤더
      const headers = ['타임스탬프', '사용자', '함수명', '에러 메시지', '스택 트레이스'];
      
      // CSV 데이터 변환
      const csvRows = errorData.map(error => {
        const timestamp = error.timestamp || '';
        const user = error.userId || error.userEmail || '-';
        const functionName = error.functionName || '-';
        const message = (error.message || '').replace(/"/g, '""').replace(/\n/g, ' ');
        const stack = (error.stack || '').replace(/"/g, '""').replace(/\n/g, ' ');
        
        return [timestamp, user, functionName, message, stack]
          .map(field => `"${field}"`)
          .join(',');
      });

      // CSV 파일 생성
      const csvContent = [headers.join(','), ...csvRows].join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      
      const a = document.createElement('a');
      a.href = url;
      a.download = `errors_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      alert(`✅ 에러 로그 ${errorData.length}건이 CSV로 다운로드되었습니다.`);
      
    } catch (error) {
      console.error('❌ CSV 내보내기 실패:', error);
      alert('❌ CSV 내보내기 실패: ' + error.message);
    }
  };

  const getErrorSeverity = (error) => {
    const message = (error.message || '').toLowerCase();
    if (message.includes('fatal') || message.includes('critical')) return 'error';
    if (message.includes('warning') || message.includes('warn')) return 'warning';
    return 'info';
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '-';
    
    try {
      // 이미 ISO 문자열 형태로 변환되어 있음
      const date = new Date(timestamp);
      
      return date.toLocaleString('ko-KR', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return '-';
    }
  };

  if (!user?.isAdmin) {
    return null;
  }

  return (
    <HongKongNeonCard sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Warning sx={{ color: '#55207D' }} />
          <Typography variant="h6" sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}>
            최근 에러 로그
          </Typography>
          <Chip 
            label={`${errors.length}건`} 
            size="small" 
            color={errors.length > 0 ? 'warning' : 'success'}
          />
        </Box>
        
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            size="small"
            variant="contained"
            startIcon={<Download />}
            onClick={exportErrorsCsv}
            sx={{ 
              bgcolor: '#55207D',
              color: 'white',
              '&:hover': { 
                bgcolor: '#6d2b93',
                transform: 'translateY(-1px)',
                boxShadow: '0 4px 12px rgba(85, 32, 125, 0.3)'
              }
            }}
          >
            CSV 다운로드
          </Button>
          <Button
            size="small"
            variant="contained"
            startIcon={<Refresh />}
            onClick={fetchRecentErrors}
            sx={{ 
              bgcolor: theme.palette.ui?.header || '#152484',
              color: 'white',
              '&:hover': { 
                bgcolor: '#1e2d9f',
                transform: 'translateY(-1px)',
                boxShadow: '0 4px 12px rgba(21, 36, 132, 0.3)'
              }
            }}
          >
            새로고침
          </Button>
        </Box>
      </Box>

      {loading ? (
        <LoadingSkeleton 
          type="table" 
          rows={5} 
          columns={4}
          headers={['시간', '메시지', '사용자', '함수']}
        />
      ) : error ? (
        <Alert severity="error">
          에러 로그를 불러오는데 실패했습니다: {error}
        </Alert>
      ) : (
        <TableContainer sx={{ maxHeight: 400 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell sx={{ minWidth: 80, color: 'text.primary' }}>시간</TableCell>
                <TableCell sx={{ minWidth: 300, color: 'text.primary' }}>메시지</TableCell>
                <TableCell sx={{ minWidth: 120, color: 'text.primary' }}>사용자</TableCell>
                <TableCell sx={{ minWidth: 100, color: 'text.primary' }}>함수</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {errors.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center">
                    <Box sx={{ py: 3 }}>
                      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                        🎉 최근 에러가 없습니다!
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : (
                errors.map((error, index) => (
                  <TableRow key={error.id || index} hover>
                    <TableCell sx={{ fontSize: '0.75rem', color: 'text.primary' }}>
                      {formatTimestamp(error.timestamp)}
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Error 
                          fontSize="small" 
                          color={getErrorSeverity(error)} 
                        />
                        <Tooltip title={error.message || '-'} arrow>
                          <Typography
                            variant="body2"
                            sx={{
                              maxWidth: 350,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              cursor: 'help',
                              color: 'text.primary'
                            }}
                          >
                            {error.message || '-'}
                          </Typography>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'text.primary' }}>
                      {error.userId || error.userEmail || '-'}
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'text.primary' }}>
                      {error.functionName || '-'}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      
      {errors.length > 0 && (
        <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
          💡 최근 50건만 표시됩니다. 전체 분석은 CSV 다운로드를 이용하세요.
        </Typography>
      )}
    </HongKongNeonCard>
  );
}

export default ErrorsMiniTable;