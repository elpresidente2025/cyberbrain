// frontend/src/components/admin/UsersSection.jsx
import React, { useState, useEffect } from 'react';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  InputAdornment,
  Box,
  Chip,
  Button,
  Typography,
  Skeleton,
  Alert,
  MenuItem,
  Select,
  FormControl,
  InputLabel
} from '@mui/material';
import { Search, Visibility } from '@mui/icons-material';
import { useAuth } from '../../hooks/useAuth';
import { callFunctionWithRetry } from '../../services/firebaseService';
import UserDetailDialog from './UserDetailDialog';

function UsersSection() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedUser, setSelectedUser] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    if (user?.role !== 'admin') return;

    const fetchUsers = async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await callFunctionWithRetry('getAllUsers');

        if (result?.users) {
          setUsers(result.users);
          setFilteredUsers(result.users);
        }
      } catch (err) {
        console.error('사용자 목록 조회 실패:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, [user]);

  // 검색 및 필터링
  useEffect(() => {
    let filtered = users;

    // 텍스트 검색
    if (searchTerm) {
      filtered = filtered.filter(user =>
        user.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.position?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // 상태 필터
    if (statusFilter !== 'all') {
      filtered = filtered.filter(user => {
        if (statusFilter === 'active') return user.isActive;
        if (statusFilter === 'inactive') return !user.isActive;
        if (statusFilter === 'admin') return user.role === 'admin';
        return true;
      });
    }

    setFilteredUsers(filtered);
    setPage(0); // 필터 변경 시 첫 페이지로
  }, [users, searchTerm, statusFilter]);

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleUserDetail = (userData) => {
    setSelectedUser(userData);
    setDialogOpen(true);
  };

  if (user?.role !== 'admin') {
    return (
      <Alert severity="error">
        관리자 권한이 필요합니다.
      </Alert>
    );
  }

  if (loading) {
    return (
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>사용자 관리</Typography>
        <Box sx={{ mb: 2 }}>
          <Skeleton variant="rectangular" height={56} />
        </Box>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>이름</TableCell>
                <TableCell>이메일</TableCell>
                <TableCell>직책</TableCell>
                <TableCell>지역</TableCell>
                <TableCell>상태</TableCell>
                <TableCell>작업</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton /></TableCell>
                  <TableCell><Skeleton /></TableCell>
                  <TableCell><Skeleton /></TableCell>
                  <TableCell><Skeleton /></TableCell>
                  <TableCell><Skeleton /></TableCell>
                  <TableCell><Skeleton /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        사용자 목록을 불러오는데 실패했습니다: {error}
      </Alert>
    );
  }

  const displayUsers = filteredUsers.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        사용자 관리 ({filteredUsers.length}명)
      </Typography>

      {/* 검색 및 필터 */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <TextField
          placeholder="이름, 이메일, 직책으로 검색..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 300, flexGrow: 1 }}
          size="small"
        />

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>상태</InputLabel>
          <Select
            value={statusFilter}
            label="상태"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="all">전체</MenuItem>
            <MenuItem value="active">활성</MenuItem>
            <MenuItem value="inactive">비활성</MenuItem>
            <MenuItem value="admin">관리자</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>이름</TableCell>
              <TableCell>이메일</TableCell>
              <TableCell>직책</TableCell>
              <TableCell>지역</TableCell>
              <TableCell>상태</TableCell>
              <TableCell>작업</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {displayUsers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography color="text.secondary">
                    표시할 사용자가 없습니다.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              displayUsers.map((userData) => (
                <TableRow key={userData.id || userData.email} hover>
                  <TableCell>
                    <Box>
                      <Typography variant="body2" fontWeight="medium">
                        {userData.name || '-'}
                      </Typography>
                      {userData.role === 'admin' && (
                        <Chip label="관리자" size="small" color="primary" />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                    {userData.email || '-'}
                  </TableCell>
                  <TableCell>{userData.position || '-'}</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {[userData.regionMetro, userData.regionLocal, userData.electoralDistrict]
                        .filter(Boolean)
                        .join(' > ') || '-'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={userData.isActive ? '활성' : '비활성'}
                      color={userData.isActive ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      startIcon={<Visibility />}
                      size="small"
                      onClick={() => handleUserDetail(userData)}
                    >
                      상세
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        rowsPerPageOptions={[5, 10, 25, 50]}
        component="div"
        count={filteredUsers.length}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        labelRowsPerPage="페이지당 행:"
        labelDisplayedRows={({ from, to, count }) =>
          `${from}-${to} / 총 ${count !== -1 ? count : `${to}개 이상`}`
        }
      />

      {/* 사용자 상세 다이얼로그 */}
      <UserDetailDialog
        user={selectedUser}
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          setSelectedUser(null);
        }}
      />
    </Paper>
  );
}

export default UsersSection;