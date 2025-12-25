// frontend/src/components/admin/UserListModal.jsx
import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  IconButton,
  TextField,
  InputAdornment,
  Pagination
} from '@mui/material';
import { 
  Close, 
  Search,
  Download,
  Visibility,
  Person,
  Email,
  LocationOn,
  CalendarToday
} from '@mui/icons-material';
import { getUsers } from '../../services/firebaseService';

function UserListModal({ open, onClose }) {
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [rowsPerPage] = useState(10);

  // 모달이 열릴 때 사용자 목록을 가져옴
  useEffect(() => {
    if (open) {
      fetchUsers();
    }
  }, [open]);

  // 검색어가 변경될 때 필터링
  useEffect(() => {
    if (!searchTerm.trim()) {
      setFilteredUsers(users);
    } else {
      const filtered = users.filter(user =>
        user.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.position?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.regionMetro?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.regionLocal?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.electoralDistrict?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.status?.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredUsers(filtered);
    }
    setPage(1); // 검색할 때 첫 페이지로 이동
  }, [searchTerm, users]);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await getUsers({
        limit: 100, // 최대 100명까지
        orderBy: 'createdAt',
        orderDirection: 'desc'
      });

      const userList = result?.users || [];
      setUsers(userList);
      setFilteredUsers(userList);
      
      if (userList.length === 0) {
        setError('등록된 사용자가 없습니다.');
      }
      
    } catch (error) {
      console.error('사용자 목록 조회 실패:', error);
      setError('사용자 목록을 불러오는데 실패했습니다.');
      setUsers([]);
      setFilteredUsers([]);
    } finally {
      setLoading(false);
    }
  };

  const exportUsersCsv = () => {
    if (filteredUsers.length === 0) {
      alert('내보낼 데이터가 없습니다.');
      return;
    }

    const headers = ['이름', '이메일', '직책', '지역', '선거구', '상태', '가입일'];
    const csvContent = [
      headers.join(','),
      ...filteredUsers.map(user => [
        user.name || '',
        user.email || '',
        user.position || '',
        [user.regionMetro, user.regionLocal].filter(Boolean).join(' ') || '',
        user.electoralDistrict || '',
        user.status || '',
        user.createdAt ? new Date(user.createdAt).toLocaleDateString('ko-KR') : ''
      ].map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `users_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleClose = () => {
    setSearchTerm('');
    setPage(1);
    setError(null);
    onClose();
  };

  // 페이지네이션을 위한 데이터 슬라이싱
  const paginatedUsers = filteredUsers.slice(
    (page - 1) * rowsPerPage,
    page * rowsPerPage
  );

  const totalPages = Math.ceil(filteredUsers.length / rowsPerPage);

  return (
    <Dialog 
      open={open} 
      onClose={handleClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: { minHeight: '70vh' }
      }}
    >
      <DialogTitle sx={{ 
        pb: 1,
        borderBottom: '1px solid #e0e0e0',
        bgcolor: '#f8f9fa'
      }}>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box display="flex" alignItems="center" gap={1}>
            <Person color="primary" />
            <Typography variant="h6" component="span">
              사용자 목록
            </Typography>
            {!loading && (
              <Chip 
                label={`${filteredUsers.length}명`}
                size="small" 
                color="primary" 
                variant="outlined"
              />
            )}
          </Box>
          <IconButton onClick={handleClose} size="small">
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ p: 0 }}>
        {/* 검색 및 액션 바 */}
        <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0', bgcolor: '#fafafa' }}>
          <Box display="flex" gap={2} alignItems="center" justifyContent="space-between">
            <TextField
              placeholder="이름, 이메일, 직책, 지역, 선거구로 검색..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              size="small"
              sx={{ flexGrow: 1, maxWidth: 400 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search color="action" />
                  </InputAdornment>
                ),
              }}
            />
            <Box display="flex" gap={1}>
              <Button
                variant="outlined"
                size="small"
                startIcon={<Download />}
                onClick={exportUsersCsv}
                disabled={filteredUsers.length === 0}
              >
                CSV 내보내기
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={fetchUsers}
                disabled={loading}
              >
                새로고침
              </Button>
            </Box>
          </Box>
        </Box>

        {/* 컨텐츠 영역 */}
        <Box sx={{ p: 2 }}>
          {loading ? (
            <Box display="flex" justifyContent="center" alignItems="center" py={4}>
              <CircularProgress />
              <Typography variant="body2" sx={{ ml: 2 }}>
                사용자 목록을 불러오는 중...
              </Typography>
            </Box>
          ) : error ? (
            <Alert severity="warning" sx={{ my: 2 }}>
              {error}
            </Alert>
          ) : filteredUsers.length === 0 ? (
            <Box display="flex" flexDirection="column" alignItems="center" py={4}>
              <Person sx={{ fontSize: 64, color: 'grey.400', mb: 2 }} />
              <Typography variant="body1" color="text.secondary">
                {searchTerm ? '검색 결과가 없습니다.' : '등록된 사용자가 없습니다.'}
              </Typography>
            </Box>
          ) : (
            <>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#f5f5f5' }}>
                      <TableCell><strong>이름</strong></TableCell>
                      <TableCell><strong>이메일</strong></TableCell>
                      <TableCell><strong>직책</strong></TableCell>
                      <TableCell><strong>지역/선거구</strong></TableCell>
                      <TableCell><strong>상태</strong></TableCell>
                      <TableCell><strong>가입일</strong></TableCell>
                      <TableCell align="center"><strong>작업</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {paginatedUsers.map((user, index) => (
                      <TableRow key={user.uid || user.id || index} hover>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Person fontSize="small" color="action" />
                            {user.name || '이름 없음'}
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Email fontSize="small" color="action" />
                            {user.email || '이메일 없음'}
                          </Box>
                        </TableCell>
                        <TableCell>
                          {user.position || '미설정'}
                        </TableCell>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <LocationOn fontSize="small" color="action" />
                            {[user.regionMetro, user.regionLocal, user.electoralDistrict].filter(Boolean).join(' ') || '미설정'}
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={user.status || '알 수 없음'}
                            size="small"
                            color={
                              user.status === '현역' ? 'primary' :
                              user.status === '예비' ? 'secondary' : 'default'
                            }
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <CalendarToday fontSize="small" color="action" />
                            {user.createdAt ? 
                              new Date(user.createdAt).toLocaleDateString('ko-KR') : 
                              '알 수 없음'
                            }
                          </Box>
                        </TableCell>
                        <TableCell align="center">
                          <IconButton 
                            size="small" 
                            title="상세 보기"
                            onClick={() => {
                              console.log('사용자 상세 정보:', user);
                              alert(`사용자 정보:\n이름: ${user.name}\n이메일: ${user.email}\n선거구: ${user.electoralDistrict}`);
                            }}
                          >
                            <Visibility fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* 페이지네이션 */}
              {totalPages > 1 && (
                <Box display="flex" justifyContent="center" mt={2}>
                  <Pagination
                    count={totalPages}
                    page={page}
                    onChange={(event, newPage) => setPage(newPage)}
                    color="primary"
                    size="small"
                  />
                </Box>
              )}
            </>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ p: 2, borderTop: '1px solid #e0e0e0', bgcolor: '#f8f9fa' }}>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
          {!loading && `총 ${filteredUsers.length}명의 사용자`}
        </Typography>
        <Button onClick={handleClose} variant="contained">
          닫기
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default UserListModal;