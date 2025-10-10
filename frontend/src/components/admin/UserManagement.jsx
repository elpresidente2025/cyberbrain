import React, { useState, useEffect } from 'react';
import {
  Typography,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert,
  Tooltip,
  useTheme
} from '@mui/material';
import { LoadingSpinner } from '../loading';
import {
  Person,
  Block,
  Delete,
  Edit,
  Refresh,
  Search
} from '@mui/icons-material';
import HongKongNeonCard from '../HongKongNeonCard';
import { callFunctionWithNaverAuth } from '../../services/firebaseService';
import { NotificationSnackbar, useNotification } from '../ui';

const UserManagement = () => {
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteDialog, setDeleteDialog] = useState({ open: false, user: null });
  const [deactivateDialog, setDeactivateDialog] = useState({ open: false, user: null });

  // Firebase Functions 호출을 네이버 인증 방식으로 변경

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      console.log('🔍 사용자 목록 로드 시작...');
      const response = await callFunctionWithNaverAuth('getAllUsers');
      console.log('🔍 getAllUsers 응답:', response);
      
      if (response?.success) {
        console.log('✅ 사용자 데이터:', response.users);
        setUsers(response.users || []);
      } else {
        console.warn('⚠️ 응답 구조가 예상과 다름:', response);
        setUsers([]);
        showNotification('사용자 목록 데이터 형식이 올바르지 않습니다.', 'warning');
      }
    } catch (error) {
      console.error('❌ 사용자 목록 로드 실패:', error);
      console.error('❌ 에러 상세:', {
        message: error.message,
        code: error.code,
        details: error.details,
        stack: error.stack
      });

      let errorMessage = '사용자 목록을 불러오는 중 오류가 발생했습니다.';
      if (error.code === 'functions/permission-denied') {
        errorMessage = '관리자 권한이 필요합니다.';
      } else if (error.code === 'functions/unauthenticated') {
        errorMessage = '로그인이 필요합니다.';
      }

      showNotification(errorMessage, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeactivateUser = async () => {
    if (!deactivateDialog.user) return;

    try {
      const response = await callFunctionWithNaverAuth('deactivateUser', {
        userId: deactivateDialog.user.uid
      });

      if (response.success) {
        showNotification(`${deactivateDialog.user.name || '사용자'} 계정이 비활성화되었습니다.`, 'success');
        loadUsers(); // 목록 새로고침
      }
    } catch (error) {
      console.error('계정 비활성화 실패:', error);
      showNotification('계정 비활성화 중 오류가 발생했습니다.', 'error');
    } finally {
      setDeactivateDialog({ open: false, user: null });
    }
  };

  const handleReactivateUser = async (user) => {
    try {
      const response = await callFunctionWithNaverAuth('reactivateUser', {
        userId: user.uid
      });

      if (response.success) {
        showNotification(`${user.name || '사용자'} 계정이 재활성화되었습니다.`, 'success');
        loadUsers(); // 목록 새로고침
      }
    } catch (error) {
      console.error('계정 재활성화 실패:', error);
      showNotification('계정 재활성화 중 오류가 발생했습니다.', 'error');
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteDialog.user) return;

    try {
      const response = await callFunctionWithNaverAuth('deleteUser', {
        userId: deleteDialog.user.uid
      });

      if (response.success) {
        showNotification(`${deleteDialog.user.name || '사용자'} 계정이 완전히 삭제되었습니다.`, 'success');
        loadUsers(); // 목록 새로고침
      }
    } catch (error) {
      console.error('계정 삭제 실패:', error);
      showNotification('계정 삭제 중 오류가 발생했습니다.', 'error');
    } finally {
      setDeleteDialog({ open: false, user: null });
    }
  };

  const filteredUsers = users.filter(user => 
    user.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.electoralDistrict?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatDate = (timestamp) => {
    if (!timestamp) return '-';
    
    try {
      let date;
      if (timestamp.toDate) {
        // Firestore Timestamp 객체
        date = timestamp.toDate();
      } else if (typeof timestamp === 'string') {
        // ISO 문자열
        date = new Date(timestamp);
      } else if (typeof timestamp === 'number') {
        // Unix timestamp
        date = new Date(timestamp);
      } else {
        // 이미 Date 객체
        date = timestamp;
      }
      
      // Invalid Date 체크
      if (isNaN(date.getTime())) {
        console.warn('Invalid date:', timestamp);
        return '-';
      }
      
      return date.toLocaleDateString('ko-KR');
    } catch (error) {
      console.error('Date formatting error:', error, timestamp);
      return '-';
    }
  };

  return (
    <HongKongNeonCard sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.primary' }}>
          <Person />
          사용자 관리
        </Typography>
        <Button
          variant="contained"
          startIcon={<Refresh />}
          onClick={loadUsers}
          disabled={loading}
          sx={{
            bgcolor: theme.palette.ui?.header || '#152484',
            color: 'white',
            '&:hover': {
              bgcolor: '#1e2d9f',
              transform: 'translateY(-1px)',
              boxShadow: '0 4px 12px rgba(21, 36, 132, 0.3)'
            },
            '&:disabled': {
              bgcolor: 'rgba(21, 36, 132, 0.3)',
              color: 'rgba(255, 255, 255, 0.7)'
            }
          }}
        >
          새로고침
        </Button>
      </Box>

      <Box sx={{ mb: 3 }}>
        <TextField
          fullWidth
          placeholder="이름, 선거구로 검색..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
          }}
        />
      </Box>

      {loading ? (
        <LoadingSpinner message="사용자 목록 로딩 중..." fullHeight={true} />
      ) : (
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell sx={{ color: 'text.primary' }}>이름</TableCell>
                <TableCell sx={{ color: 'text.primary' }}>직책</TableCell>
                <TableCell sx={{ color: 'text.primary' }}>선거구</TableCell>
                <TableCell sx={{ color: 'text.primary' }}>상태</TableCell>
                <TableCell sx={{ color: 'text.primary' }}>가입일</TableCell>
                <TableCell align="center" sx={{ color: 'text.primary' }}>작업</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredUsers.map((user) => (
                <TableRow key={user.uid}>
                  <TableCell sx={{ color: 'text.primary' }}>{user.name || '-'}</TableCell>
                  <TableCell sx={{ color: 'text.primary' }}>{user.position || '-'}</TableCell>
                  <TableCell sx={{ color: 'text.primary' }}>{user.electoralDistrict || '-'}</TableCell>
                  <TableCell>
                    <Chip
                      label={user.isActive ? '활성' : '비활성'}
                      color={user.isActive ? 'success' : 'error'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell sx={{ color: 'text.secondary' }}>{formatDate(user.createdAt)}</TableCell>
                  <TableCell align="center">
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      {user.isActive ? (
                        <Tooltip title="계정 비활성화">
                          <IconButton
                            size="small"
                            color="warning"
                            onClick={() => setDeactivateDialog({ open: true, user })}
                          >
                            <Block />
                          </IconButton>
                        </Tooltip>
                      ) : (
                        <Tooltip title="계정 재활성화">
                          <IconButton
                            size="small"
                            color="success"
                            onClick={() => handleReactivateUser(user)}
                          >
                            <Person />
                          </IconButton>
                        </Tooltip>
                      )}
                      <Tooltip title="계정 삭제">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => setDeleteDialog({ open: true, user })}
                        >
                          <Delete />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {filteredUsers.length === 0 && !loading && (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <Typography sx={{ color: 'text.secondary' }}>
            {searchTerm ? '검색 결과가 없습니다.' : '등록된 사용자가 없습니다.'}
          </Typography>
        </Box>
      )}

      {/* 계정 비활성화 확인 다이얼로그 */}
      <Dialog
        open={deactivateDialog.open}
        onClose={() => setDeactivateDialog({ open: false, user: null })}
      >
        <DialogTitle>계정 비활성화 확인</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            계정을 비활성화하면 해당 사용자는 로그인할 수 없게 됩니다.
          </Alert>
          <Typography>
            <strong>{deactivateDialog.user?.name || '사용자'}</strong> 계정을 비활성화하시겠습니까?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeactivateDialog({ open: false, user: null })}>
            취소
          </Button>
          <Button onClick={handleDeactivateUser} color="warning" variant="contained">
            비활성화
          </Button>
        </DialogActions>
      </Dialog>

      {/* 계정 삭제 확인 다이얼로그 */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, user: null })}
      >
        <DialogTitle>계정 삭제 확인</DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            이 작업은 되돌릴 수 없습니다. 계정과 관련된 모든 데이터가 영구적으로 삭제됩니다.
          </Alert>
          <Typography sx={{ mb: 2 }}>
            <strong>{deleteDialog.user?.name || '사용자'}</strong> 계정을 완전히 삭제하시겠습니까?
          </Typography>
          <Typography variant="body2" color="text.secondary">
            삭제될 데이터: 프로필 정보, 생성된 게시물, 결제 정보, 활동 기록 등
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, user: null })}>
            취소
          </Button>
          <Button onClick={handleDeleteUser} color="error" variant="contained">
            영구 삭제
          </Button>
        </DialogActions>
      </Dialog>

      {/* 알림 메시지 */}
      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
        autoHideDuration={6000}
      />
    </HongKongNeonCard>
  );
};

export default UserManagement;