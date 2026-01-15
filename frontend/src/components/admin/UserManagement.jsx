import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert,
  Tooltip,
  useTheme,
  TablePagination,
  InputAdornment
} from '@mui/material';
import { LoadingSpinner } from '../loading';
import {
  Person,
  Block,
  Delete,
  Refresh,
  Search,
  Science,
  VerifiedUser,
  CheckCircle
} from '@mui/icons-material';
import HongKongNeonCard from '../HongKongNeonCard';
import { callFunction } from '../../services/firebaseService';
import { NotificationSnackbar, useNotification } from '../ui';

const UserManagement = () => {
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteDialog, setDeleteDialog] = useState({ open: false, user: null });
  const [deactivateDialog, setDeactivateDialog] = useState({ open: false, user: null });

  // 페이지네이션 상태
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [statusFilter, setStatusFilter] = useState('all');

  // cleanup을 위한 ref
  const isMountedRef = useRef(true);

  // 검색어 입력 ref (포커스 관리)
  const searchInputRef = useRef(null);

  // 사용자 목록 로드 함수
  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await callFunction('getAllUsers');

      if (!isMountedRef.current) return;

      if (response?.success) {
        setUsers(response.users || []);
      } else {
        setUsers([]);
        showNotification('사용자 목록 데이터 형식이 올바르지 않습니다.', 'warning');
      }
    } catch (error) {
      console.error('사용자 목록 로드 실패:', error);

      if (!isMountedRef.current) return;

      let errorMessage = '사용자 목록을 불러오는 중 오류가 발생했습니다.';
      if (error.code === 'functions/permission-denied') {
        errorMessage = '관리자 권한이 필요합니다.';
      } else if (error.code === 'functions/unauthenticated') {
        errorMessage = '로그인이 필요합니다.';
      }

      showNotification(errorMessage, 'error');
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [showNotification]);

  // 컴포넌트 마운트/언마운트 처리
  useEffect(() => {
    isMountedRef.current = true;
    loadUsers();

    return () => {
      isMountedRef.current = false;
    };
  }, [loadUsers]);

  // 계정 비활성화 핸들러
  const handleDeactivateUser = useCallback(async () => {
    if (!deactivateDialog.user) return;

    try {
      const response = await callFunction('deactivateUser', {
        userId: deactivateDialog.user.uid
      });

      if (response.success) {
        showNotification(`${deactivateDialog.user.name || '사용자'} 계정이 비활성화되었습니다.`, 'success');
        loadUsers();
      }
    } catch (error) {
      console.error('계정 비활성화 실패:', error);
      showNotification('계정 비활성화 중 오류가 발생했습니다.', 'error');
    } finally {
      setDeactivateDialog({ open: false, user: null });
    }
  }, [deactivateDialog.user, loadUsers, showNotification]);

  // 계정 재활성화 핸들러
  const handleReactivateUser = useCallback(async (user) => {
    try {
      const response = await callFunction('reactivateUser', {
        userId: user.uid
      });

      if (response.success) {
        showNotification(`${user.name || '사용자'} 계정이 재활성화되었습니다.`, 'success');
        loadUsers();
      }
    } catch (error) {
      console.error('계정 재활성화 실패:', error);
      showNotification('계정 재활성화 중 오류가 발생했습니다.', 'error');
    }
  }, [loadUsers, showNotification]);

  // 계정 삭제 핸들러
  const handleDeleteUser = useCallback(async () => {
    if (!deleteDialog.user) return;

    try {
      const response = await callFunction('deleteUser', {
        userId: deleteDialog.user.uid
      });

      if (response.success) {
        showNotification(`${deleteDialog.user.name || '사용자'} 계정이 완전히 삭제되었습니다.`, 'success');
        loadUsers();
      }
    } catch (error) {
      console.error('계정 삭제 실패:', error);
      showNotification('계정 삭제 중 오류가 발생했습니다.', 'error');
    } finally {
      setDeleteDialog({ open: false, user: null });
    }
  }, [deleteDialog.user, loadUsers, showNotification]);

  // 사용량 초기화 핸들러
  const handleResetUsage = useCallback(async (user) => {
    if (!window.confirm(`${user.name || '사용자'}님의 이번 달 사용량을 초기화하시겠습니까?\n\n포스트는 유지되지만, 게이지에서 카운트되지 않습니다.`)) {
      return;
    }

    try {
      const response = await callFunction('resetUserUsage', {
        targetUserId: user.uid
      });

      if (response.success) {
        showNotification(response.message || '사용량이 초기화되었습니다.', 'success');
      }
    } catch (error) {
      console.error('사용량 초기화 실패:', error);
      showNotification('사용량 초기화 중 오류가 발생했습니다.', 'error');
    }
  }, [showNotification]);

  // 테스터 권한 토글 핸들러
  const handleToggleTester = useCallback(async (user) => {
    const action = user.isTester ? '해제' : '부여';
    if (!window.confirm(`${user.name || '사용자'}님에게 테스터 권한을 ${action}하시겠습니까?\n\n테스터는 관리자와 동일하게 90회 생성이 가능합니다.`)) {
      return;
    }

    try {
      const response = await callFunction('toggleTester', {
        targetUserId: user.uid
      });

      if (response.success) {
        showNotification(response.message, 'success');
        loadUsers();
      }
    } catch (error) {
      console.error('테스터 권한 변경 실패:', error);
      showNotification('테스터 권한 변경 중 오류가 발생했습니다.', 'error');
    }
  }, [loadUsers, showNotification]);

  // 대면 인증 토글 핸들러
  const handleToggleFaceVerified = useCallback(async (user) => {
    const action = user.faceVerified ? '해제' : '부여';
    if (!window.confirm(`${user.name || '사용자'}님에게 대면 인증을 ${action}하시겠습니까?\n\n대면 인증이 부여되면 당적 인증(당적증명서/당비납부내역서 업로드)을 영구적으로 건너뛸 수 있습니다.`)) {
      return;
    }

    try {
      const response = await callFunction('toggleFaceVerified', {
        targetUserId: user.uid
      });

      if (response.success) {
        showNotification(response.message, 'success');
        loadUsers();
      }
    } catch (error) {
      console.error('대면 인증 변경 실패:', error);
      showNotification('대면 인증 변경 중 오류가 발생했습니다.', 'error');
    }
  }, [loadUsers, showNotification]);

  // 필터링된 사용자 목록 (메모이제이션)
  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const matchesSearch =
        user.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.electoralDistrict?.toLowerCase().includes(searchTerm.toLowerCase());

      if (!matchesSearch) return false;

      switch (statusFilter) {
        case 'active':
          return user.isActive;
        case 'inactive':
          return !user.isActive;
        case 'tester':
          return user.isTester;
        case 'faceVerified':
          return user.faceVerified;
        case 'admin':
          return user.isAdmin;
        default:
          return true;
      }
    });
  }, [users, searchTerm, statusFilter]);

  // 날짜 포맷 함수 (메모이제이션)
  const formatDate = useCallback((timestamp) => {
    if (!timestamp) return '-';

    try {
      let date;
      if (timestamp.toDate) {
        date = timestamp.toDate();
      } else if (typeof timestamp === 'string') {
        date = new Date(timestamp);
      } else if (typeof timestamp === 'number') {
        date = new Date(timestamp);
      } else {
        date = timestamp;
      }

      if (isNaN(date.getTime())) {
        return '-';
      }

      return date.toLocaleDateString('ko-KR');
    } catch {
      return '-';
    }
  }, []);

  // 검색어 변경 핸들러
  const handleSearchChange = useCallback((e) => {
    setSearchTerm(e.target.value);
    setPage(0);
  }, []);

  // 필터 변경 핸들러
  const handleFilterChange = useCallback((e) => {
    setStatusFilter(e.target.value);
    setPage(0);
  }, []);

  // 페이지 변경 핸들러
  const handlePageChange = useCallback((event, newPage) => {
    setPage(newPage);
  }, []);

  // 행 수 변경 핸들러
  const handleRowsPerPageChange = useCallback((event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  }, []);

  return (
    <HongKongNeonCard sx={{ p: { xs: 2, sm: 3 } }}>
      {/* 헤더 영역 */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          alignItems: { xs: 'flex-start', sm: 'center' },
          justifyContent: 'space-between',
          gap: 2,
          mb: 3
        }}
      >
        <Typography
          variant="h6"
          component="h2"
          id="user-management-heading"
          sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.primary' }}
        >
          <Person aria-hidden="true" />
          사용자 관리
        </Typography>
        <Button
          variant="contained"
          startIcon={<Refresh aria-hidden="true" />}
          onClick={loadUsers}
          disabled={loading}
          aria-label="사용자 목록 새로고침"
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
            },
            '&:focus-visible': {
              outline: '2px solid #152484',
              outlineOffset: '2px'
            }
          }}
        >
          새로고침
        </Button>
      </Box>

      {/* 검색 및 필터 영역 */}
      <Box
        sx={{ mb: 3, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 2 }}
        role="search"
        aria-label="사용자 검색"
      >
        <TextField
          fullWidth
          placeholder="이름, 선거구로 검색..."
          value={searchTerm}
          onChange={handleSearchChange}
          inputRef={searchInputRef}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search aria-hidden="true" sx={{ color: 'text.secondary' }} />
              </InputAdornment>
            )
          }}
          inputProps={{
            'aria-label': '사용자 검색',
            'aria-describedby': 'search-help-text'
          }}
          sx={{
            flex: 1,
            '& .MuiOutlinedInput-root:focus-within': {
              outline: '2px solid #152484',
              outlineOffset: '1px'
            }
          }}
        />
        <TextField
          select
          value={statusFilter}
          onChange={handleFilterChange}
          SelectProps={{
            native: true,
          }}
          inputProps={{
            'aria-label': '상태 필터'
          }}
          sx={{ width: { xs: '100%', sm: 150 } }}
        >
          <option value="all">전체 상태</option>
          <option value="active">활성</option>
          <option value="inactive">비활성</option>
          <option value="tester">테스터</option>
          <option value="faceVerified">대면인증</option>
          <option value="admin">관리자</option>
        </TextField>
      </Box>

      {loading ? (
        <Box aria-busy="true" aria-label="사용자 목록 로딩 중">
          <LoadingSpinner message="사용자 목록 로딩 중..." fullHeight={true} />
        </Box>
      ) : (
        <>
          <TableContainer
            sx={{
              overflowX: 'auto',
              '& .MuiTable-root': {
                minWidth: { xs: 600, md: 'auto' }
              }
            }}
          >
            <Table aria-labelledby="user-management-heading">
              <TableHead>
                <TableRow>
                  <TableCell scope="col" sx={{ color: 'text.primary', width: 60 }}>No.</TableCell>
                  <TableCell scope="col" sx={{ color: 'text.primary' }}>이름</TableCell>
                  <TableCell scope="col" sx={{ color: 'text.primary', display: { xs: 'none', md: 'table-cell' } }}>직책</TableCell>
                  <TableCell scope="col" sx={{ color: 'text.primary' }}>선거구</TableCell>
                  <TableCell scope="col" sx={{ color: 'text.primary', display: { xs: 'none', sm: 'table-cell' } }}>가입일</TableCell>
                  <TableCell scope="col" align="center" sx={{ color: 'text.primary' }}>작업</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredUsers
                  .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                  .map((user, index) => (
                    <TableRow key={user.uid} hover>
                      <TableCell sx={{ color: 'text.secondary' }}>
                        {page * rowsPerPage + index + 1}
                      </TableCell>
                      <TableCell sx={{ color: 'text.primary' }}>{user.name || '-'}</TableCell>
                      <TableCell sx={{ color: 'text.primary', display: { xs: 'none', md: 'table-cell' } }}>{user.position || '-'}</TableCell>
                      <TableCell sx={{ color: 'text.primary' }}>{user.electoralDistrict || '-'}</TableCell>
                      <TableCell sx={{ color: 'text.secondary', display: { xs: 'none', sm: 'table-cell' } }}>{formatDate(user.createdAt)}</TableCell>
                      <TableCell align="center">
                        <Box
                          sx={{ display: 'flex', gap: 0.5, justifyContent: 'center', flexWrap: 'wrap' }}
                          role="group"
                          aria-label={`${user.name || '사용자'} 작업`}
                        >
                          {user.isActive ? (
                            <Tooltip title="현재 활성 (클릭하여 비활성화)">
                              <IconButton
                                size="small"
                                color="success"
                                onClick={() => setDeactivateDialog({ open: true, user })}
                                aria-label={`${user.name || '사용자'} 비활성화`}
                                sx={{
                                  '&:focus-visible': {
                                    outline: '2px solid #2e7d32',
                                    outlineOffset: '2px'
                                  }
                                }}
                              >
                                <CheckCircle aria-hidden="true" />
                              </IconButton>
                            </Tooltip>
                          ) : (
                            <Tooltip title="현재 비활성 (클릭하여 재활성화)">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => handleReactivateUser(user)}
                                aria-label={`${user.name || '사용자'} 재활성화`}
                                sx={{
                                  '&:focus-visible': {
                                    outline: '2px solid #d32f2f',
                                    outlineOffset: '2px'
                                  }
                                }}
                              >
                                <Block aria-hidden="true" />
                              </IconButton>
                            </Tooltip>
                          )}
                          <Tooltip title={user.isTester ? '테스터 권한 해제' : '테스터 권한 부여'}>
                            <IconButton
                              size="small"
                              color={user.isTester ? 'secondary' : 'default'}
                              onClick={() => handleToggleTester(user)}
                              aria-label={`${user.name || '사용자'} ${user.isTester ? '테스터 권한 해제' : '테스터 권한 부여'}`}
                              aria-pressed={user.isTester}
                              sx={{
                                '&:focus-visible': {
                                  outline: '2px solid #9c27b0',
                                  outlineOffset: '2px'
                                }
                              }}
                            >
                              <Science aria-hidden="true" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={user.faceVerified ? '대면 인증 해제' : '대면 인증 부여'}>
                            <IconButton
                              size="small"
                              color={user.faceVerified ? 'info' : 'default'}
                              onClick={() => handleToggleFaceVerified(user)}
                              aria-label={`${user.name || '사용자'} ${user.faceVerified ? '대면 인증 해제' : '대면 인증 부여'}`}
                              aria-pressed={user.faceVerified}
                              sx={{
                                '&:focus-visible': {
                                  outline: '2px solid #0288d1',
                                  outlineOffset: '2px'
                                }
                              }}
                            >
                              <VerifiedUser aria-hidden="true" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="사용량 초기화">
                            <IconButton
                              size="small"
                              color="info"
                              onClick={() => handleResetUsage(user)}
                              aria-label={`${user.name || '사용자'} 사용량 초기화`}
                              sx={{
                                '&:focus-visible': {
                                  outline: '2px solid #0288d1',
                                  outlineOffset: '2px'
                                }
                              }}
                            >
                              <Refresh aria-hidden="true" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="계정 삭제">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => setDeleteDialog({ open: true, user })}
                              aria-label={`${user.name || '사용자'} 계정 삭제`}
                              sx={{
                                '&:focus-visible': {
                                  outline: '2px solid #d32f2f',
                                  outlineOffset: '2px'
                                }
                              }}
                            >
                              <Delete aria-hidden="true" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="nav"
            aria-label="테이블 페이지네이션"
            count={filteredUsers.length}
            page={page}
            onPageChange={handlePageChange}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={handleRowsPerPageChange}
            labelRowsPerPage="페이지당 행:"
            labelDisplayedRows={({ from, to, count }) => `${from}-${to} / 전체 ${count}`}
            sx={{
              '& .MuiTablePagination-actions button:focus-visible': {
                outline: '2px solid #152484',
                outlineOffset: '2px'
              }
            }}
          />
        </>
      )}

      {/* 검색 결과 없음 */}
      {filteredUsers.length === 0 && !loading && (
        <Box
          sx={{ textAlign: 'center', py: 4 }}
          role="status"
          aria-live="polite"
        >
          <Typography sx={{ color: 'text.secondary' }}>
            {searchTerm ? '검색 결과가 없습니다.' : '등록된 사용자가 없습니다.'}
          </Typography>
        </Box>
      )}

      {/* 계정 비활성화 확인 다이얼로그 */}
      <Dialog
        open={deactivateDialog.open}
        onClose={() => setDeactivateDialog({ open: false, user: null })}
        aria-labelledby="deactivate-dialog-title"
        aria-describedby="deactivate-dialog-description"
      >
        <DialogTitle id="deactivate-dialog-title">계정 비활성화 확인</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }} role="alert">
            계정을 비활성화하면 해당 사용자는 로그인할 수 없게 됩니다.
          </Alert>
          <Typography id="deactivate-dialog-description">
            <strong>{deactivateDialog.user?.name || '사용자'}</strong> 계정을 비활성화하시겠습니까?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDeactivateDialog({ open: false, user: null })}
            sx={{
              '&:focus-visible': {
                outline: '2px solid #152484',
                outlineOffset: '2px'
              }
            }}
          >
            취소
          </Button>
          <Button
            onClick={handleDeactivateUser}
            color="warning"
            variant="contained"
            sx={{
              '&:focus-visible': {
                outline: '2px solid #ed6c02',
                outlineOffset: '2px'
              }
            }}
          >
            비활성화
          </Button>
        </DialogActions>
      </Dialog>

      {/* 계정 삭제 확인 다이얼로그 */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, user: null })}
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
      >
        <DialogTitle id="delete-dialog-title">계정 삭제 확인</DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }} role="alert">
            이 작업은 되돌릴 수 없습니다. 계정과 관련된 모든 데이터가 영구적으로 삭제됩니다.
          </Alert>
          <Typography id="delete-dialog-description" sx={{ mb: 2 }}>
            <strong>{deleteDialog.user?.name || '사용자'}</strong> 계정을 완전히 삭제하시겠습니까?
          </Typography>
          <Typography variant="body2" color="text.secondary">
            삭제될 데이터: 프로필 정보, 생성된 게시물, 결제 정보, 활동 기록 등
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDeleteDialog({ open: false, user: null })}
            sx={{
              '&:focus-visible': {
                outline: '2px solid #152484',
                outlineOffset: '2px'
              }
            }}
          >
            취소
          </Button>
          <Button
            onClick={handleDeleteUser}
            color="error"
            variant="contained"
            sx={{
              '&:focus-visible': {
                outline: '2px solid #d32f2f',
                outlineOffset: '2px'
              }
            }}
          >
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