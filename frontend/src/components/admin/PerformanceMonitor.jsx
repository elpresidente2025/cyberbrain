import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip
} from '@mui/material';
import { 
  Close, 
  Refresh, 
  Speed, 
  Memory, 
  NetworkCheck,
  Timer,
  TrendingUp,
  Computer,
  Cloud
} from '@mui/icons-material';
import { usePerformanceMonitoring } from '../../hooks/usePerformanceMonitoring';

const PerformanceMonitor = ({ open, onClose }) => {
  const { 
    metrics, 
    browserMetrics, 
    loading, 
    error, 
    fetchPerformanceMetrics,
    startRealTimeMonitoring 
  } = usePerformanceMonitoring();

  const [autoRefresh, setAutoRefresh] = useState(false);

  useEffect(() => {
    if (open) {
      fetchPerformanceMetrics();
    }
  }, [open, fetchPerformanceMetrics]);

  useEffect(() => {
    if (autoRefresh && open) {
      const cleanup = startRealTimeMonitoring(30000); // 30초마다 갱신
      return cleanup;
    }
  }, [autoRefresh, open, startRealTimeMonitoring]);

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 MB';
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(1)} MB`;
  };

  const formatTime = (ms) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const getStatusColor = (value, thresholds) => {
    if (value <= thresholds.good) return '#006261';
    if (value <= thresholds.warning) return '#55207D';
    return '#152484';
  };

  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="xl" 
      fullWidth
      PaperProps={{
        sx: { height: '90vh' }
      }}
    >
      <DialogTitle sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        borderBottom: '2px solid #152484'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Speed sx={{ color: '#152484' }} />
          <Typography variant="h5" sx={{ color: '#152484', fontWeight: 600 }}>
            성능 모니터링
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title={autoRefresh ? "자동 갱신 중" : "수동 갱신"}>
            <Button
              variant={autoRefresh ? "contained" : "outlined"}
              size="small"
              onClick={() => setAutoRefresh(!autoRefresh)}
              sx={{ 
                bgcolor: autoRefresh ? '#006261' : 'transparent',
                borderColor: '#006261',
                color: autoRefresh ? 'white' : '#006261',
                '&:hover': {
                  bgcolor: autoRefresh ? '#003A87' : 'rgba(0, 98, 97, 0.1)'
                }
              }}
            >
              {autoRefresh ? '자동 갱신' : '수동 갱신'}
            </Button>
          </Tooltip>
          <IconButton 
            onClick={fetchPerformanceMetrics} 
            disabled={loading}
            sx={{ color: '#152484' }}
          >
            <Refresh />
          </IconButton>
          <IconButton onClick={onClose} sx={{ color: '#152484' }}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ p: 3, overflow: 'auto' }}>
        {loading && !metrics && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {error && (
          <Alert severity="warning" sx={{ mb: 3 }}>
            {error}
            {metrics && " (브라우저 메트릭만 표시됩니다)"}
          </Alert>
        )}

        {metrics && (
          <Grid container spacing={3}>
            {/* 시스템 개요 */}
            <Grid item xs={12}>
              <Typography variant="h6" sx={{ color: '#152484', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Cloud />
                시스템 개요
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Memory sx={{ fontSize: 40, color: '#152484', mb: 1 }} />
                      <Typography variant="h4" sx={{ color: getStatusColor(metrics.system?.memoryUsage || 0, { good: 70, warning: 85 }) }}>
                        {metrics.system?.memoryUsage || 0}%
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        메모리 사용률
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Timer sx={{ fontSize: 40, color: '#006261', mb: 1 }} />
                      <Typography variant="h4" sx={{ color: getStatusColor(metrics.system?.avgResponseTime || 0, { good: 200, warning: 500 }) }}>
                        {metrics.system?.avgResponseTime || 0}ms
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        평균 응답시간
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center' }}>
                      <NetworkCheck sx={{ fontSize: 40, color: '#55207D', mb: 1 }} />
                      <Typography variant="h4" sx={{ color: metrics.system?.activeUsers > 0 ? '#006261' : '#55207D' }}>
                        {metrics.system?.activeUsers || 0}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        활성 사용자
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center' }}>
                      <TrendingUp sx={{ fontSize: 40, color: '#003A87', mb: 1 }} />
                      <Typography variant="h4" sx={{ color: getStatusColor(metrics.system?.errorRate || 0, { good: 1, warning: 5 }) }}>
                        {metrics.system?.errorRate || 0}%
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        에러율
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Grid>

            {/* 브라우저 성능 */}
            <Grid item xs={12} md={6}>
              <Typography variant="h6" sx={{ color: '#152484', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Computer />
                브라우저 성능
              </Typography>
              <Card>
                <CardContent>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary" gutterBottom>
                      페이지 로드 시간
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={Math.min((metrics.browser?.pageLoad || 0) / 50, 100)} 
                        sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                      />
                      <Typography variant="h6">
                        {formatTime(metrics.browser?.pageLoad || 0)}
                      </Typography>
                    </Box>
                  </Box>

                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary" gutterBottom>
                      메모리 사용량
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={Math.min(((metrics.browser?.memoryUsage?.used || 0) / (metrics.browser?.memoryUsage?.limit || 100)) * 100, 100)}
                        sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                      />
                      <Typography variant="body2">
                        {formatBytes(metrics.browser?.memoryUsage?.used || 0)} / {formatBytes(metrics.browser?.memoryUsage?.limit || 0)}
                      </Typography>
                    </Box>
                  </Box>

                  {metrics.browser?.connection && (
                    <Box>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        네트워크 연결
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <Chip 
                          label={metrics.browser.connection.effectiveType} 
                          size="small" 
                          color="primary"
                        />
                        <Chip 
                          label={`${metrics.browser.connection.downlink} Mbps`} 
                          size="small" 
                          variant="outlined"
                        />
                        <Chip 
                          label={`RTT: ${metrics.browser.connection.rtt}ms`} 
                          size="small" 
                          variant="outlined"
                        />
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* API 성능 */}
            <Grid item xs={12} md={6}>
              <Typography variant="h6" sx={{ color: '#152484', mb: 2 }}>
                상위 API 엔드포인트
              </Typography>
              <Card>
                <CardContent>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>엔드포인트</TableCell>
                          <TableCell align="right">호출 수</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {metrics.apiMetrics?.topEndpoints?.map((endpoint, index) => (
                          <TableRow key={index}>
                            <TableCell sx={{ fontSize: '0.75rem' }}>
                              {endpoint.endpoint}
                            </TableCell>
                            <TableCell align="right">
                              <Chip 
                                label={endpoint.count} 
                                size="small" 
                                color="primary" 
                                variant="outlined"
                              />
                            </TableCell>
                          </TableRow>
                        )) || (
                          <TableRow>
                            <TableCell colSpan={2} align="center">
                              <Typography variant="body2" color="textSecondary">
                                데이터가 없습니다
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* 성능 상세 */}
            <Grid item xs={12}>
              <Typography variant="h6" sx={{ color: '#152484', mb: 2 }}>
                성능 상세 정보
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <Card>
                    <CardContent>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        처리량 (분당 요청)
                      </Typography>
                      <Typography variant="h5" sx={{ color: '#006261' }}>
                        {metrics.performance?.throughput || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                
                <Grid item xs={12} sm={4}>
                  <Card>
                    <CardContent>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        동시 접속자
                      </Typography>
                      <Typography variant="h5" sx={{ color: '#55207D' }}>
                        {metrics.performance?.concurrency || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={4}>
                  <Card>
                    <CardContent>
                      <Typography variant="body2" color="textSecondary" gutterBottom>
                        시스템 가동시간
                      </Typography>
                      <Typography variant="h5" sx={{ color: '#006261' }}>
                        {metrics.system?.uptime || 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Grid>
          </Grid>
        )}
      </DialogContent>

      <DialogActions sx={{ p: 3, borderTop: '1px solid #e0e0e0' }}>
        <Typography variant="caption" color="textSecondary" sx={{ flexGrow: 1 }}>
          마지막 업데이트: {metrics ? new Date(metrics.timestamp).toLocaleTimeString() : '-'}
        </Typography>
        <Button onClick={onClose} variant="outlined">
          닫기
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PerformanceMonitor;