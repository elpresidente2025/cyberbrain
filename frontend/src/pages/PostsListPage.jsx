// frontend/src/pages/PostsListPage.jsx
import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  CardActionArea,
  Chip,
  IconButton,
  Tooltip,
  useTheme,
  Button,
  Divider,
  TextField,
} from '@mui/material';
import { DeleteOutline, Assignment, Publish, Link, Transform, AddLink } from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import SNSConversionModal from '../components/SNSConversionModal';
import { LoadingSpinner } from '../components/loading';
import PostViewerModal from '../components/PostViewerModal';
import { useAuth } from '../hooks/useAuth';
import { callFunctionWithNaverAuth } from '../services/firebaseService';
import {
  LoadingState,
  EmptyState,
  PageHeader,
  ActionButtonGroup,
  StatusChip,
  NotificationSnackbar,
  useNotification,
  StandardDialog
} from '../components/ui';

function formatDate(iso) {
  try {
    if (!iso) return '-';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '-';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${day} ${hh}:${mm}`;
  } catch {
    return '-';
  }
}


function stripHtml(html = '') {
  try {
    return html.replace(/<[^>]*>/g, '');
  } catch {
    return html || '';
  }
}

// 공백 제외 글자수 계산 (Java 코드와 동일한 로직)
function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i++) {
    if (!/\s/.test(str.charAt(i))) { // 공백 문자가 아닌 경우
      count++;
    }
  }
  return count;
}

export default function PostsListPage() {
  const { user, loading: authLoading } = useAuth();
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [posts, setPosts] = useState([]);
  const [error, setError] = useState('');

  // useNotification 훅 사용
  const { notification, showNotification, hideNotification } = useNotification();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerPost, setViewerPost] = useState(null);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishPost, setPublishPost] = useState(null);
  const [publishUrl, setPublishUrl] = useState('');
  const [snsModalOpen, setSnsModalOpen] = useState(false);
  const [snsPost, setSnsPost] = useState(null);

  // 디버깅 로그
  console.log('🔍 user:', user);
  console.log('🔍 user?.uid:', user?.uid);
  console.log('🔍 authLoading:', authLoading);

  // Network functions - 네이버 인증 시스템 사용

  useEffect(() => {
    let mounted = true;
    console.log('📋 PostsListPage useEffect 실행 중...', { user: !!user, uid: user?.uid });
    (async () => {
      try {
        console.log('🔄 getUserPosts 호출 시작...');
        setLoading(true);
        if (!user?.uid) {
          console.log('❌ 사용자 UID 없음');
          setError('사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.');
          return;
        }
        
        console.log('🚀 Firebase Functions 호출:', { uid: user.uid });
        const res = await callFunctionWithNaverAuth('getUserPosts');
        console.log('✅ getUserPosts 응답:', res);
        const list = res?.data?.posts || [];
        console.log('📝 처리된 posts 목록:', list);
        console.log('📝 posts 개수:', list.length);
        console.log('📝 첫 번째 post:', list[0]);
        if (!mounted) return;
        setPosts(list);
        
        // URL 쿼리 파라미터에서 openPost 확인하고 자동으로 Modal 열기
        const urlParams = new URLSearchParams(location.search);
        const openPostId = urlParams.get('openPost');
        if (openPostId && list.length > 0) {
          const postToOpen = list.find(post => post.id === openPostId);
          if (postToOpen) {
            console.log('🔍 자동으로 열 원고 찾음:', postToOpen);
            setViewerPost(postToOpen);
            setViewerOpen(true);
            // URL에서 쿼리 파라미터 제거 (깔끔하게)
            navigate('/posts', { replace: true });
          }
        }
      } catch (e) {
        console.error('❌ getUserPosts 에러:', e);
        console.error('❌ 에러 세부사항:', {
          message: e.message,
          code: e.code,
          stack: e.stack
        });
        setError('목록을 불러오지 못했습니다: ' + e.message);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [user?.uid]);


  const handleDelete = async (postId, e) => {
    if (e) e.stopPropagation();
    if (!postId) return;
    const ok = window.confirm('정말 이 원고를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.');
    if (!ok) return;
    try {
      // 네이버 인증 시스템 사용
      await callFunctionWithNaverAuth('deletePost', { postId });
      
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      showNotification('삭제되었습니다.', 'info');
      if (viewerPost?.id === postId) {
        setViewerOpen(false);
        setViewerPost(null);
      }
    } catch (err) {
      console.error(err);
      showNotification(err.message || '삭제에 실패했습니다.', 'error');
    }
  };

  const openViewer = (post) => {
    setViewerPost(post);
    setViewerOpen(true);
  };

  const closeViewer = () => {
    setViewerOpen(false);
    setViewerPost(null);
  };

  const handleSNSConvert = (post, e) => {
    if (e) e.stopPropagation();
    setSnsPost(post);
    setSnsModalOpen(true);
  };

  const handlePublish = (post, e) => {
    if (e) e.stopPropagation();
    setPublishPost(post);
    setPublishUrl(post.publishUrl || '');
    setPublishDialogOpen(true);
  };

  const handlePublishSubmit = async () => {
    if (!publishPost || !publishUrl.trim()) {
      showNotification('발행 URL을 입력해주세요.', 'error');
      return;
    }

    try {
      await callFunctionWithNaverAuth('publishPost', { 
        postId: publishPost.id, 
        publishUrl: publishUrl.trim() 
      });
      
      // 로컬 상태 업데이트
      setPosts(prev => prev.map(p => 
        p.id === publishPost.id 
          ? { ...p, publishUrl: publishUrl.trim(), publishedAt: new Date().toISOString() }
          : p
      ));
      
      setPublishDialogOpen(false);
      setPublishPost(null);
      setPublishUrl('');
      showNotification('발행 완료! 게이미피케이션 포인트를 획득했습니다.', 'success');
    } catch (err) {
      console.error(err);
      showNotification('발행 등록에 실패했습니다.', 'error');
    }
  };

  const closePublishDialog = () => {
    setPublishDialogOpen(false);
    setPublishPost(null);
    setPublishUrl('');
  };

  if (authLoading) {
    return (
      <DashboardLayout title="포스트 목록">
        <Container maxWidth="xl" sx={{ mt: 2 }}>
          <LoadingSpinner message="게시글 목록 로딩 중..." fullHeight={true} />
        </Container>
      </DashboardLayout>
    );
  }

  if (!user?.uid) {
    return (
      <DashboardLayout title="포스트 목록">
        <Container maxWidth="xl" sx={{ mt: 2 }}>
          <Alert severity="error">사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.</Alert>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="포스트 목록">
      <Container maxWidth="xl" sx={{ py: 4, px: { xs: 1, sm: 2 } }}>
        {/* 페이지 헤더 */}
        <Box sx={{ mb: 4 }}>
          <Typography variant="h4" sx={{ 
            fontWeight: 'bold', 
            mb: 1, 
            color: theme.palette.mode === 'dark' ? 'white' : 'black', 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1 
          }}>
            <Assignment sx={{ color: theme.palette.mode === 'dark' ? 'white' : 'black' }} />
            내 원고 목록
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body1" color="text.secondary">
              생성한 원고를 관리할 수 있습니다
            </Typography>
            <Chip 
              label={`총 ${posts.length}개`} 
              sx={{ 
                bgcolor: 'rgba(128,128,128,0.1)', 
                color: 'text.primary',
                borderColor: 'text.secondary'
              }} 
              variant="outlined" 
            />
          </Box>
        </Box>
        
        <Paper elevation={0} sx={{ 
          p: { xs: 2, sm: 3 }
        }}>

          <Typography variant="body2" sx={{ mb: 2, color: 'grey.100', fontStyle: 'italic' }}>
            이 화면은 읽기 전용입니다. 카드를 터치/클릭하면 원고가 열립니다.
          </Typography>

          {loading ? (
            <LoadingSpinner message="게시글 목록 로딩 중..." fullHeight={true} />
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : posts.length === 0 ? (
            <Alert severity="warning">저장된 원고가 없습니다.</Alert>
          ) : (
            <Grid container spacing={2}>
              {posts.map((p) => {
                const preview = stripHtml(p.content || '');
                const wordCount = countWithoutSpace(preview); // 공백 제외 글자수로 계산
                const status = p.status || 'draft';
                const statusColor =
                  status === 'published' ? 'success' : status === 'scheduled' ? 'warning' : 'default';

                return (
                  <Grid item xs={12} sm={6} md={4} key={p.id}>
                    <Card
                      elevation={0}
                      sx={{
                        height: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                      }}
                    >
                      <CardActionArea onClick={() => openViewer(p)} sx={{ flexGrow: 1 }}>
                        <CardContent>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                            <Chip size="small" label={status} color={statusColor} variant="outlined" />
                            <Typography variant="caption" color="text.secondary">
                              {formatDate(p.updatedAt) || formatDate(p.createdAt)}
                            </Typography>
                          </Box>

                          <Typography
                            variant="h6"
                            sx={{
                              fontWeight: 700,
                              mb: 1,
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                              wordBreak: 'break-word',
                            }}
                            title={p.title || '제목 없음'}
                          >
                            {p.title || '제목 없음'}
                          </Typography>

                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                              display: '-webkit-box',
                              WebkitLineClamp: 4,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                              wordBreak: 'break-word',
                              minHeight: 84,
                            }}
                          >
                            {preview || '내용 미리보기가 없습니다.'}
                          </Typography>

                          <Divider sx={{ my: 1.5 }} />

                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="caption" color="text.secondary">
                              글자수: {wordCount} (공백 제외)
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              생성일 {formatDate(p.createdAt)}
                            </Typography>
                          </Box>
                        </CardContent>
                      </CardActionArea>

                      <CardActions sx={{ justifyContent: 'space-between', pt: 0 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          {p.publishUrl && (
                            <Chip 
                              size="small" 
                              label="URL등록완료" 
                              color="primary" 
                              variant="outlined"
                              icon={<AddLink />}
                              sx={{ fontSize: '0.7rem' }}
                            />
                          )}
                        </Box>
                        <Box>
                          <Tooltip title="SNS 변환">
                            <IconButton
                              size="small"
                              onClick={(e) => handleSNSConvert(p, e)}
                              sx={{ color: theme.palette.ui?.header || '#152484' }}
                            >
                              <Transform fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="URL 등록">
                            <IconButton 
                              size="small"
                              onClick={(e) => handlePublish(p, e)}
                              sx={{ color: p.publishUrl ? '#006261' : (theme.palette.ui?.header || '#152484') }}
                            >
                              <AddLink fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="삭제">
                            <IconButton size="small" color="error" onClick={(e) => handleDelete(p.id, e)}>
                              <DeleteOutline fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </CardActions>
                    </Card>
                  </Grid>
                );
              })}
            </Grid>
          )}
        </Paper>

        {/* 원고 보기 모달 */}
        <PostViewerModal
          open={viewerOpen}
          onClose={closeViewer}
          post={viewerPost}
          onDelete={handleDelete}
        />

        {/* 발행 URL 입력 다이얼로그 */}
        <Dialog open={publishDialogOpen} onClose={closePublishDialog} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Publish sx={{ color: theme.palette.ui?.header || '#152484' }} />
            원고 발행 등록
          </DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              실제 발행한 블로그/SNS 주소를 입력하여 게이미피케이션 포인트를 획득하세요!
            </Typography>
            <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
              "{publishPost?.title || '원고 제목'}"
            </Typography>
            <TextField
              autoFocus
              margin="dense"
              label="발행 URL"
              placeholder="https://blog.example.com/my-post"
              fullWidth
              variant="outlined"
              value={publishUrl}
              onChange={(e) => setPublishUrl(e.target.value)}
              InputProps={{
                startAdornment: <Link sx={{ color: 'text.secondary', mr: 1 }} />,
              }}
              helperText="네이버 블로그, 티스토리, 브런치, 인스타그램 등 실제 발행한 주소를 입력하세요."
              FormHelperTextProps={{ sx: { color: 'black' } }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={closePublishDialog} color="inherit">
              취소
            </Button>
            <Button 
              onClick={handlePublishSubmit} 
              variant="contained"
              sx={{
                bgcolor: theme.palette.ui?.header || '#152484',
                '&:hover': { bgcolor: theme.palette.ui?.headerHover || '#003A87' }
              }}
            >
              발행 완료
            </Button>
          </DialogActions>
        </Dialog>

        {/* 알림 스낵바 */}
        <NotificationSnackbar
          open={notification.open}
          onClose={hideNotification}
          message={notification.message}
          severity={notification.severity}
        />

        {/* SNS 변환 모달 */}
        <SNSConversionModal
          open={snsModalOpen}
          onClose={() => setSnsModalOpen(false)}
          post={snsPost}
        />

      </Container>
    </DashboardLayout>
  );
}