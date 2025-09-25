// frontend/src/components/admin/UserDetailDialog.jsx
import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Typography,
  Box,
  Grid,
  Chip,
  CircularProgress,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { callFunctionWithRetry } from '../../services/firebaseService';

function UserDetailDialog({ user, open, onClose }) {
  const [loading, setLoading] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !user?.email) {
      setDetailData(null);
      return;
    }

    const fetchUserDetail = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const result = await callFunctionWithRetry('getUserDetail', {
          userEmail: user.email
        });
        
        setDetailData(result);
      } catch (err) {
        console.error('사용자 상세 정보 조회 실패:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchUserDetail();
  }, [open, user?.email]);

  if (!user) return null;

  return (
    <Dialog 
      open={open && !!user} 
      onClose={onClose}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          사용자 상세 정보
          <IconButton onClick={onClose}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>
      
      <DialogContent dividers>
        {loading ? (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error">
            {error}
          </Alert>
        ) : detailData ? (
          <Box sx={{ space: 3 }}>
            {/* 기본 정보 */}
            <Typography variant="h6" gutterBottom>
              기본 정보
            </Typography>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">이름</Typography>
                <Typography variant="body1">{detailData.base?.name || '-'}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">이메일</Typography>
                <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                  {detailData.base?.email || '-'}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">직책</Typography>
                <Typography variant="body1">{detailData.base?.position || '-'}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">지역</Typography>
                <Typography variant="body1">
                  {[detailData.base?.regionMetro, detailData.base?.regionLocal, detailData.base?.electoralDistrict]
                    .filter(Boolean)
                    .join(' > ') || '-'}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">가입일</Typography>
                <Typography variant="body1">
                  {detailData.base?.createdAt ? new Date(detailData.base.createdAt).toLocaleString() : '-'}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">상태</Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Chip
                    label={detailData.base?.isActive ? '활성' : '비활성'}
                    color={detailData.base?.isActive ? 'success' : 'default'}
                    size="small"
                  />
                  {detailData.base?.isAdmin && (
                    <Chip label="관리자" color="primary" size="small" />
                  )}
                </Box>
              </Grid>
            </Grid>

            {/* 사용 통계 */}
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              사용 통계
            </Typography>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={3}>
                <Typography variant="body2" color="text.secondary">총 원고 수</Typography>
                <Typography variant="h6">{detailData.stats?.totalPosts || 0}</Typography>
              </Grid>
              <Grid item xs={3}>
                <Typography variant="body2" color="text.secondary">이번 주</Typography>
                <Typography variant="h6">{detailData.stats?.weeklyPosts || 0}</Typography>
              </Grid>
              <Grid item xs={3}>
                <Typography variant="body2" color="text.secondary">이번 달</Typography>
                <Typography variant="h6">{detailData.stats?.monthlyPosts || 0}</Typography>
              </Grid>
              <Grid item xs={3}>
                <Typography variant="body2" color="text.secondary">마지막 활동</Typography>
                <Typography variant="body2">
                  {detailData.stats?.lastActivity ? 
                    new Date(detailData.stats.lastActivity).toLocaleDateString() : '-'}
                </Typography>
              </Grid>
            </Grid>

            {/* 최근 원고 목록 */}
            {detailData.recentPosts && detailData.recentPosts.length > 0 && (
              <>
                <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
                  최근 원고 ({detailData.recentPosts.length}개)
                </Typography>
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>제목</TableCell>
                        <TableCell>작성일</TableCell>
                        <TableCell>상태</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {detailData.recentPosts.map((post, index) => (
                        <TableRow key={post.id || index}>
                          <TableCell>
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                maxWidth: 300,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}
                              title={post.title}
                            >
                              {post.title || '-'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {post.createdAt ? 
                                new Date(post.createdAt).toLocaleDateString() : '-'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={post.status === 'completed' ? '완료' : '진행중'}
                              color={post.status === 'completed' ? 'success' : 'warning'}
                              size="small"
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            )}
          </Box>
        ) : (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              📊
            </Typography>
            <Typography variant="body1" color="text.secondary">
              사용자 정보를 불러오는 중입니다...
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default UserDetailDialog;