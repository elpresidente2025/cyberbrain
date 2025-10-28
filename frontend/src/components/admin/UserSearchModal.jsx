// frontend/src/components/admin/UserSearchModal.jsx
import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  Button,
  Box,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Chip,
  CircularProgress,
  Alert,
  InputAdornment,
  Divider,
  useTheme
} from '@mui/material';
import { Search, Close, Visibility, Download } from '@mui/icons-material';
import { callFunctionWithRetry } from '../../services/firebaseService';

function UserSearchModal({ open, onClose }) {
  const theme = useTheme();
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async () => {
    if (!searchTerm.trim()) {
      setError('검색어를 입력해주세요.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await callFunctionWithRetry('searchUsers', {
        query: searchTerm.trim(),
        limit: 20
      });

      setSearchResults(result?.users || []);
      
      if (result?.users?.length === 0) {
        setError('검색 결과가 없습니다.');
      }
    } catch (err) {
      console.error('사용자 검색 실패:', err);
      setError('검색 중 오류가 발생했습니다: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const exportResults = () => {
    if (searchResults.length === 0) return;

    const headers = ['이름', '이메일', '직책', '지역', '상태', '가입일'];
    const csvRows = searchResults.map(user => [
      user.name || '-',
      user.email || '-',
      user.position || '-',
      [user.regionMetro, user.regionLocal, user.electoralDistrict].filter(Boolean).join(' > ') || '-',
      user.isActive ? '활성' : '비활성',
      user.createdAt ? new Date(user.createdAt).toLocaleDateString() : '-'
    ].map(field => `"${field}"`).join(','));

    const csvContent = [headers.join(','), ...csvRows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `user_search_${searchTerm}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleClose = () => {
    setSearchTerm('');
    setSearchResults([]);
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6" sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}>
            사용자 검색
          </Typography>
          <IconButton onClick={handleClose}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent>
        {/* 검색 영역 */}
        <Box sx={{ mb: 3 }}>
          <TextField
            fullWidth
            placeholder="이름, 이메일, 직책으로 검색..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyPress={handleKeyPress}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search />
                </InputAdornment>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  <Button
                    variant="contained"
                    onClick={handleSearch}
                    disabled={loading}
                    sx={{ backgroundColor: theme.palette.ui?.header || '#152484' }}
                  >
                    {loading ? <CircularProgress size={20} /> : '검색'}
                  </Button>
                </InputAdornment>
              )
            }}
          />
        </Box>

        {/* 에러 메시지 */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* 검색 결과 */}
        {searchResults.length > 0 && (
          <>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                검색 결과 ({searchResults.length}명)
              </Typography>
              <Button
                startIcon={<Download />}
                onClick={exportResults}
                size="small"
                sx={{ color: '#55207D' }}
              >
                CSV 다운로드
              </Button>
            </Box>

            <List sx={{ maxHeight: 400, overflow: 'auto' }}>
              {searchResults.map((user, index) => (
                <React.Fragment key={user.id || user.email || index}>
                  <ListItem>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            {user.name || '-'}
                          </Typography>
                          {user.role === 'admin' && (
                            <Chip label="관리자" size="small" color="primary" />
                          )}
                          <Chip 
                            label={user.isActive ? '활성' : '비활성'} 
                            size="small" 
                            color={user.isActive ? 'success' : 'default'} 
                          />
                        </Box>
                      }
                      secondary={
                        <Box>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            📧 {user.email || '-'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            💼 {user.position || '-'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            📍 {[user.regionMetro, user.regionLocal, user.electoralDistrict]
                              .filter(Boolean).join(' > ') || '-'}
                          </Typography>
                          {user.createdAt && (
                            <Typography variant="caption" color="text.secondary">
                              가입: {new Date(user.createdAt).toLocaleDateString()}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton 
                        edge="end"
                        onClick={() => {
                          // 사용자 상세 정보를 별도 모달로 열거나 다른 액션 수행
                          console.log('사용자 상세:', user);
                        }}
                      >
                        <Visibility />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                  {index < searchResults.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          </>
        )}

        {/* 로딩 상태 */}
        {loading && searchResults.length === 0 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {/* 빈 상태 */}
        {!loading && searchResults.length === 0 && !error && searchTerm && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              🔍
            </Typography>
            <Typography variant="body1" color="text.secondary">
              검색 결과가 없습니다
            </Typography>
            <Typography variant="body2" color="text.secondary">
              다른 검색어로 시도해보세요
            </Typography>
          </Box>
        )}

        {/* 초기 상태 */}
        {!searchTerm && searchResults.length === 0 && !loading && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              👥
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              사용자를 검색해보세요
            </Typography>
            <Typography variant="body2" color="text.secondary">
              이름, 이메일 또는 직책으로 검색할 수 있습니다
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default UserSearchModal;