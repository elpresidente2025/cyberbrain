// frontend/src/components/admin/NoticeManager.jsx
import React, { useState, useEffect } from 'react';
import {
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Chip,
  Box,
  IconButton,
  Alert,
  Divider,
  useTheme
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Visibility,
  VisibilityOff,
  Close,
  Campaign,
  Schedule
} from '@mui/icons-material';
import HongKongNeonCard from '../HongKongNeonCard';
import { getNotices } from '../../services/firebaseService';

function NoticeManager() {
  const theme = useTheme();
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingNotice, setEditingNotice] = useState(null);
  const [formData, setFormData] = useState({
    title: '',
    content: '',
    type: 'info',
    priority: 'medium',
    isActive: true,
    expiresAt: '',
    targetUsers: 'all'
  });

  // 공지 목록 조회
  const fetchNotices = async () => {
    try {
      setLoading(true);
      const result = await getNotices();
      setNotices(result?.notices || []);
    } catch (error) {
      console.error('공지 조회 실패:', error);
      setNotices([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotices();
  }, []);

  // 공지 저장
  const handleSave = async () => {
    try {
      if (!formData.title.trim() || !formData.content.trim()) {
        alert('제목과 내용을 입력해주세요.');
        return;
      }

      const noticeData = {
        ...formData,
        expiresAt: formData.expiresAt ? new Date(formData.expiresAt).toISOString() : null
      };

      if (editingNotice) {
        await callFunctionWithRetry('updateNotice', {
          noticeId: editingNotice.id,
          ...noticeData
        });
      } else {
        await callFunctionWithRetry('createNotice', noticeData);
      }

      handleCloseDialog();
      fetchNotices();
      alert(editingNotice ? '공지가 수정되었습니다.' : '공지가 작성되었습니다.');
    } catch (error) {
      console.error('공지 저장 실패:', error);
      alert('저장 실패: ' + error.message);
    }
  };

  // 공지 삭제
  const handleDelete = async (noticeId) => {
    if (!confirm('정말로 이 공지를 삭제하시겠습니까?')) return;

    try {
      await callFunctionWithRetry('deleteNotice', { noticeId });
      fetchNotices();
      alert('공지가 삭제되었습니다.');
    } catch (error) {
      console.error('공지 삭제 실패:', error);
      alert('삭제 실패: ' + error.message);
    }
  };

  // 공지 활성화/비활성화
  const handleToggleActive = async (noticeId, isActive) => {
    try {
      await callFunctionWithRetry('updateNotice', {
        noticeId,
        isActive: !isActive
      });
      fetchNotices();
    } catch (error) {
      console.error('상태 변경 실패:', error);
      alert('상태 변경 실패: ' + error.message);
    }
  };

  // 다이얼로그 열기
  const handleOpenDialog = (notice = null) => {
    if (notice) {
      setEditingNotice(notice);
      setFormData({
        title: notice.title || '',
        content: notice.content || '',
        type: notice.type || 'info',
        priority: notice.priority || 'medium',
        isActive: notice.isActive !== false,
        expiresAt: notice.expiresAt ? new Date(notice.expiresAt).toISOString().slice(0, 16) : '',
        targetUsers: notice.targetUsers?.[0] || 'all'
      });
    } else {
      setEditingNotice(null);
      setFormData({
        title: '',
        content: '',
        type: 'info',
        priority: 'medium',
        isActive: true,
        expiresAt: '',
        targetUsers: 'all'
      });
    }
    setDialogOpen(true);
  };

  // 다이얼로그 닫기
  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingNotice(null);
  };

  // 타입별 색상
  const getTypeColor = (type) => {
    switch (type) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      case 'success': return 'success';
      case 'info':
      default: return 'info';
    }
  };

  // 우선순위별 색상
  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return 'error';
      case 'low': return 'default';
      case 'medium':
      default: return 'warning';
    }
  };

  return (
    <HongKongNeonCard sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Campaign sx={{ color: theme.palette.ui?.header || '#152484' }} />
          <Typography variant="h6" sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}>
            공지사항 관리
          </Typography>
          <Chip label={`${notices.length}개`} size="small" />
        </Box>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => handleOpenDialog()}
          sx={{ 
            backgroundColor: theme.palette.ui?.header || '#152484',
            color: 'white',
            '&:hover': { 
              backgroundColor: '#003A87',
              transform: 'translateY(-1px)',
              boxShadow: '0 4px 12px rgba(21, 36, 132, 0.3)'
            }
          }}
        >
          공지 작성
        </Button>
      </Box>

      <Typography variant="body2" sx={{ mb: 3, color: 'text.secondary' }}>
        작성된 공지사항은 모든 사용자의 대시보드에 표시됩니다.
      </Typography>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ color: 'text.primary' }}>제목</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>유형</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>우선순위</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>상태</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>작성일</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>만료일</TableCell>
              <TableCell sx={{ color: 'text.primary' }}>작업</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography sx={{ color: 'text.primary', fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif' }}>로딩 중...</Typography>
                </TableCell>
              </TableRow>
            ) : notices.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography sx={{ color: 'text.secondary' }}>
                    📢 작성된 공지사항이 없습니다.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              notices.map((notice) => (
                <TableRow key={notice.id} hover>
                  <TableCell>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.primary' }}>
                      {notice.title}
                    </Typography>
                    <Typography 
                      variant="body2" 
                      sx={{
                        maxWidth: 300,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        color: 'text.secondary'
                      }}
                    >
                      {notice.content}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={notice.type || 'info'}
                      color={getTypeColor(notice.type)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={notice.priority || 'medium'}
                      color={getPriorityColor(notice.priority)}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Chip
                        label={notice.isActive ? '활성' : '비활성'}
                        color={notice.isActive ? 'success' : 'default'}
                        size="small"
                      />
                      <IconButton
                        size="small"
                        onClick={() => handleToggleActive(notice.id, notice.isActive)}
                      >
                        {notice.isActive ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      {notice.createdAt ? 
                        new Date(notice.createdAt).toLocaleDateString() : '-'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      {notice.expiresAt ? 
                        new Date(notice.expiresAt).toLocaleDateString() : '무제한'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                      <IconButton 
                        size="small" 
                        onClick={() => handleOpenDialog(notice)}
                        color="primary"
                      >
                        <Edit />
                      </IconButton>
                      <IconButton 
                        size="small" 
                        onClick={() => handleDelete(notice.id)}
                        color="error"
                      >
                        <Delete />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 공지 작성/수정 다이얼로그 */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {editingNotice ? '공지 수정' : '공지 작성'}
            <IconButton onClick={handleCloseDialog}>
              <Close />
            </IconButton>
          </Box>
        </DialogTitle>
        
        <DialogContent dividers>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <TextField
              fullWidth
              label="제목"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="공지사항 제목을 입력하세요"
            />

            <TextField
              fullWidth
              multiline
              rows={4}
              label="내용"
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              placeholder="공지사항 내용을 입력하세요"
            />

            <Box sx={{ display: 'flex', gap: 2 }}>
              <FormControl sx={{ minWidth: 120 }}>
                <InputLabel>유형</InputLabel>
                <Select
                  value={formData.type}
                  label="유형"
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                >
                  <MenuItem value="info">정보</MenuItem>
                  <MenuItem value="warning">경고</MenuItem>
                  <MenuItem value="success">성공</MenuItem>
                  <MenuItem value="error">오류</MenuItem>
                </Select>
              </FormControl>

              <FormControl sx={{ minWidth: 120 }}>
                <InputLabel>우선순위</InputLabel>
                <Select
                  value={formData.priority}
                  label="우선순위"
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                >
                  <MenuItem value="low">낮음</MenuItem>
                  <MenuItem value="medium">보통</MenuItem>
                  <MenuItem value="high">높음</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <TextField
              fullWidth
              type="datetime-local"
              label="만료 일시 (선택사항)"
              value={formData.expiresAt}
              onChange={(e) => setFormData({ ...formData, expiresAt: e.target.value })}
              InputLabelProps={{ shrink: true }}
              helperText="설정하지 않으면 수동으로 비활성화할 때까지 표시됩니다"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.isActive}
                  onChange={(e) => setFormData({ ...formData, isActive: e.target.checked })}
                />
              }
              label="즉시 활성화"
            />
          </Box>
        </DialogContent>

        <DialogActions sx={{ p: 2 }}>
          <Button onClick={handleCloseDialog}>취소</Button>
          <Button 
            variant="contained" 
            onClick={handleSave}
            sx={{ 
              backgroundColor: theme.palette.ui?.header || '#152484',
              '&:hover': { backgroundColor: '#003A87' }
            }}
          >
            {editingNotice ? '수정' : '작성'}
          </Button>
        </DialogActions>
      </Dialog>
    </HongKongNeonCard>
  );
}

export default NoticeManager;