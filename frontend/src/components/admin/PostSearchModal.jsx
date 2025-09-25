// frontend/src/components/admin/PostSearchModal.jsx
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
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material';
import { 
  Search, 
  Close, 
  Visibility, 
  Download, 
  ExpandMore,
  Article,
  Person,
  CalendarToday 
} from '@mui/icons-material';
import { callFunctionWithRetry } from '../../services/firebaseService';

function PostSearchModal({ open, onClose }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // 고급 필터 상태
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateRange, setDateRange] = useState('all');

  const handleSearch = async () => {
    if (!searchTerm.trim()) {
      setError('검색어를 입력해주세요.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const searchParams = {
        query: searchTerm.trim(),
        limit: 30
      };

      // 고급 필터 적용
      if (statusFilter !== 'all') {
        searchParams.status = statusFilter;
      }
      
      if (dateRange !== 'all') {
        const now = new Date();
        const daysAgo = {
          '7d': 7,
          '30d': 30,
          '90d': 90
        }[dateRange];
        
        if (daysAgo) {
          const startDate = new Date(now.getTime() - (daysAgo * 24 * 60 * 60 * 1000));
          searchParams.startDate = startDate.toISOString();
        }
      }

      const result = await callFunctionWithRetry('searchPosts', searchParams);

      setSearchResults(result?.posts || []);
      
      if (result?.posts?.length === 0) {
        setError('검색 결과가 없습니다.');
      }
    } catch (err) {
      console.error('원고 검색 실패:', err);
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

    const headers = ['제목', '작성자', '상태', '생성일', '내용 미리보기'];
    const csvRows = searchResults.map(post => [
      post.title || '-',
      post.userEmail || post.userId || '-',
      post.status || '-',
      post.createdAt ? new Date(post.createdAt).toLocaleDateString() : '-',
      (post.content || '').substring(0, 100).replace(/\n/g, ' ') + (post.content?.length > 100 ? '...' : '')
    ].map(field => `"${field.replace(/"/g, '""')}"`).join(','));

    const csvContent = [headers.join(','), ...csvRows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `post_search_${searchTerm}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'success';
      case 'generating': return 'warning';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'completed': return '완료';
      case 'generating': return '생성중';
      case 'failed': return '실패';
      default: return '알 수 없음';
    }
  };

  const handleClose = () => {
    setSearchTerm('');
    setSearchResults([]);
    setError(null);
    setStatusFilter('all');
    setDateRange('all');
    setAdvancedExpanded(false);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6" sx={{ color: '#152484', fontWeight: 600 }}>
            원고 검색
          </Typography>
          <IconButton onClick={handleClose}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent>
        {/* 기본 검색 영역 */}
        <Box sx={{ mb: 2 }}>
          <TextField
            fullWidth
            placeholder="제목, 내용, 작성자로 검색..."
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
                    sx={{ backgroundColor: '#152484' }}
                  >
                    {loading ? <CircularProgress size={20} /> : '검색'}
                  </Button>
                </InputAdornment>
              )
            }}
          />
        </Box>

        {/* 고급 필터 */}
        <Accordion 
          expanded={advancedExpanded} 
          onChange={() => setAdvancedExpanded(!advancedExpanded)}
          sx={{ mb: 2 }}
        >
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="body2" color="text.secondary">
              고급 검색 옵션
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>상태</InputLabel>
                <Select
                  value={statusFilter}
                  label="상태"
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <MenuItem value="all">전체</MenuItem>
                  <MenuItem value="completed">완료</MenuItem>
                  <MenuItem value="generating">생성중</MenuItem>
                  <MenuItem value="failed">실패</MenuItem>
                </Select>
              </FormControl>
              
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>기간</InputLabel>
                <Select
                  value={dateRange}
                  label="기간"
                  onChange={(e) => setDateRange(e.target.value)}
                >
                  <MenuItem value="all">전체</MenuItem>
                  <MenuItem value="7d">최근 7일</MenuItem>
                  <MenuItem value="30d">최근 30일</MenuItem>
                  <MenuItem value="90d">최근 90일</MenuItem>
                </Select>
              </FormControl>
            </Box>
          </AccordionDetails>
        </Accordion>

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
                검색 결과 ({searchResults.length}개)
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

            <List sx={{ maxHeight: 500, overflow: 'auto' }}>
              {searchResults.map((post, index) => (
                <React.Fragment key={post.id || index}>
                  <ListItem alignItems="flex-start">
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Article fontSize="small" color="action" />
                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            {post.title || '제목 없음'}
                          </Typography>
                          <Chip 
                            label={getStatusText(post.status)} 
                            size="small" 
                            color={getStatusColor(post.status)}
                          />
                        </Box>
                      }
                      secondary={
                        <Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Person fontSize="small" color="action" />
                              <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                                {post.userEmail || post.userId || '-'}
                              </Typography>
                            </Box>
                            {post.createdAt && (
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                <CalendarToday fontSize="small" color="action" />
                                <Typography variant="body2" color="text.secondary">
                                  {new Date(post.createdAt).toLocaleDateString()}
                                </Typography>
                              </Box>
                            )}
                          </Box>
                          
                          {post.content && (
                            <Typography 
                              variant="body2" 
                              color="text.secondary"
                              sx={{
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                lineHeight: 1.4
                              }}
                            >
                              {post.content}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton 
                        edge="end"
                        onClick={() => {
                          // 원고 상세 보기 (새 탭으로 열기 등)
                          if (post.id) {
                            window.open(`/post/${post.id}`, '_blank');
                          }
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
              📄
            </Typography>
            <Typography variant="body1" color="text.secondary">
              검색 결과가 없습니다
            </Typography>
            <Typography variant="body2" color="text.secondary">
              다른 검색어나 필터를 시도해보세요
            </Typography>
          </Box>
        )}

        {/* 초기 상태 */}
        {!searchTerm && searchResults.length === 0 && !loading && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              📝
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              원고를 검색해보세요
            </Typography>
            <Typography variant="body2" color="text.secondary">
              제목, 내용 또는 작성자로 검색할 수 있습니다
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default PostSearchModal;