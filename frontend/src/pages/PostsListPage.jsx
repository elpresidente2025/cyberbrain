// frontend/src/pages/PostsListPage.jsx
import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
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
  useTheme,
  Button,
  IconButton,
  Divider,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  ToggleButton,
  ToggleButtonGroup,
  Stack,
} from '@mui/material';
import {
  DeleteOutline,
  Assignment,
  Publish,
  Link,
  Transform,
  AddLink,
  ViewList,
  CalendarToday,
  ChevronLeft,
  ChevronRight
} from '@mui/icons-material';
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
import { colors, spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';

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

function isNaverBlogUrl(value = '') {
  const trimmed = String(value || '').trim();
  if (!trimmed) return false;
  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.toLowerCase();
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    return hostname === 'blog.naver.com' || hostname.endsWith('.blog.naver.com');
  } catch {
    return false;
  }
}

// 🗓️ 캘린더 뷰 컴포넌트
function CalendarView({ posts, onPostClick, theme, onDelete, onSNS, onPublish }) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedPost, setSelectedPost] = useState(null); // 카드 팝업용

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay = new Date(year, month, 1).getDay(); // 0: 일요일

  // 날짜별 포스트 그룹핑
  const postsByDate = posts.reduce((acc, post) => {
    const d = new Date(post.createdAt);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(post);
    return acc;
  }, {});

  const handlePrev = () => setCurrentDate(new Date(year, month - 1, 1));
  const handleNext = () => setCurrentDate(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentDate(new Date());

  const weekDays = ['일', '월', '화', '수', '목', '금', '토'];

  return (
    <>
      <Paper elevation={0} sx={{ p: 3, mb: 3, border: `1px solid ${theme.palette.divider}` }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h5" fontWeight="bold">
              {year}년 {month + 1}월
            </Typography>
            <Button size="small" onClick={handleToday} sx={{ ml: 1, minWidth: 'auto', px: 1 }}>
              오늘
            </Button>
          </Box>
          <Box>
            <IconButton onClick={handlePrev}><ChevronLeft /></IconButton>
            <IconButton onClick={handleNext}><ChevronRight /></IconButton>
          </Box>
        </Box>

        <Grid container sx={{ mb: 1 }}>
          {weekDays.map((day, idx) => (
            <Grid item xs={12 / 7} key={day} sx={{ textAlign: 'center', fontWeight: 'bold', color: idx === 0 ? 'error.main' : idx === 6 ? 'primary.main' : 'text.secondary' }}>
              {day}
            </Grid>
          ))}
        </Grid>

        <Grid container spacing={1}>
          {Array.from({ length: firstDay }).map((_, i) => (
            <Grid item xs={12 / 7} key={`empty-${i}`} sx={{ minHeight: 150 }} />
          ))}

          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const dateKey = `${year}-${month}-${day}`;
            const dayPosts = postsByDate[dateKey] || [];
            const todayObj = new Date();
            const isToday = day === todayObj.getDate() && month === todayObj.getMonth() && year === todayObj.getFullYear();

            return (
              <Grid item xs={12 / 7} key={day}>
                <Box
                  sx={{
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 1,
                    p: 0.5,
                    height: '100%',
                    minHeight: 150,
                    bgcolor: isToday ? 'primary.main' : 'background.paper',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 0.5
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 'bold',
                      textAlign: 'center',
                      display: 'block',
                      mb: 0.5,
                      color: isToday ? 'primary.contrastText' : 'text.primary'
                    }}
                    style={isToday ? { color: '#ffffff' } : {}}
                  >
                    {day}
                  </Typography>

                  {/* 배지 목록 (높이 1/3, 줄바꿈 허용) */}
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, flex: 1 }}>
                    {dayPosts.map(post => (
                      <Box
                        key={post.id}
                        onClick={() => setSelectedPost(post)}
                        sx={{
                          bgcolor: post.status === 'published' ? 'success.light' : 'primary.light',
                          color: 'white',
                          borderRadius: '1px',
                          p: '2px 4px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          textAlign: 'left',
                          lineHeight: 1.3,
                          wordBreak: 'keep-all',
                          width: '100%',
                          transition: 'all 0.2s',
                          '&:hover': { opacity: 0.9, transform: 'translateY(-1px)' }
                        }}
                      >
                        {post.title || '제목 없음'}
                      </Box>
                    ))}
                    {/* 빈 공간 채우기 (칸 높이 유지용) */}
                    {Array.from({ length: Math.max(0, 3 - dayPosts.length) }).map((_, idx) => (
                      <Box key={`empty-fill-${idx}`} sx={{ flex: 1 }} />
                    ))}
                  </Box>
                </Box>
              </Grid>
            );
          })}
        </Grid>
      </Paper>

      {/* 카드 팝업 */}
      <Dialog
        open={!!selectedPost}
        onClose={() => setSelectedPost(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogContent sx={{ p: 0 }}>
          {selectedPost && (() => {
            const p = selectedPost;
            const preview = stripHtml(p.content || '');
            const wordCount = countWithoutSpace(preview);
            const status = p.status || 'draft';
            const statusLabel = status === 'published' ? '발행 완료' : status === 'scheduled' ? '대기 중' : status;
            const statusColor = status === 'published' ? 'success' : status === 'scheduled' ? 'warning' : 'default';
            const statusBgColor = status === 'published' ? '#2E7D32' : status === 'scheduled' ? '#F57C00' : undefined;

            return (
              <Card elevation={0}>
                <CardActionArea onClick={() => { setSelectedPost(null); onPostClick(p); }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                      <Chip size="small" label={statusLabel} color={statusColor} sx={{ color: 'white', backgroundColor: statusBgColor }} />
                      <Typography variant="caption" color="text.secondary">{formatDate(p.createdAt)}</Typography>
                    </Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1, wordBreak: 'break-word' }}>
                      {p.title || '제목 없음'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 60 }}>
                      {preview || '내용 없음'}
                    </Typography>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="caption">글자수: {wordCount}</Typography>
                  </CardContent>
                </CardActionArea>
                <CardActions sx={{ justifyContent: 'flex-end', pt: 0, gap: 1, pb: 2, px: 2 }}>
                  <Button size="small" variant="contained" onClick={(e) => onSNS(p, e)} startIcon={<Transform />}>SNS</Button>
                  <IconButton size="small" onClick={(e) => onDelete(p.id, e)}><DeleteOutline /></IconButton>
                </CardActions>
              </Card>
            );
          })()}
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function PostsListPage() {
  const { user, loading: authLoading } = useAuth();
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [posts, setPosts] = useState([]);
  const [error, setError] = useState('');

  const { notification, showNotification, hideNotification } = useNotification();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerPost, setViewerPost] = useState(null);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishPost, setPublishPost] = useState(null);
  const [publishUrl, setPublishUrl] = useState('');
  const [snsModalOpen, setSnsModalOpen] = useState(false);
  const [snsPost, setSnsPost] = useState(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        if (!user?.uid) {
          setError('사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.');
          return;
        }
        const res = await callFunctionWithNaverAuth('getUserPosts');
        const list = res?.posts || [];
        if (!mounted) return;
        setPosts(list);

        const urlParams = new URLSearchParams(location.search);
        const openPostId = urlParams.get('openPost');
        if (openPostId && list.length > 0) {
          const postToOpen = list.find(post => post.id === openPostId);
          if (postToOpen) {
            setViewerPost(postToOpen);
            setViewerOpen(true);
            navigate('/posts', { replace: true });
          }
        }
      } catch (e) {
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
    const ok = window.confirm('정말 이 원고를 삭제하시겠습니까?');
    if (!ok) return;
    try {
      await callFunctionWithNaverAuth('deletePost', { postId });
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      showNotification('삭제되었습니다.', 'info');
      if (viewerPost?.id === postId) {
        setViewerOpen(false);
        setViewerPost(null);
      }
    } catch (err) {
      showNotification(err.message || '삭제 실패', 'error');
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
    const normalizedUrl = publishUrl.trim();
    if (!publishPost || !normalizedUrl) {
      showNotification('발행 URL을 입력해주세요.', 'error');
      return;
    }
    if (!isNaverBlogUrl(normalizedUrl)) {
      showNotification('네이버 블로그 URL만 입력할 수 있습니다.', 'error');
      return;
    }
    try {
      await callFunctionWithNaverAuth('publishPost', {
        postId: publishPost.id,
        publishUrl: normalizedUrl
      });
      setPosts(prev => prev.map(p =>
        p.id === publishPost.id
          ? { ...p, publishUrl: normalizedUrl, publishedAt: new Date().toISOString(), status: 'published' }
          : p
      ));
      setPublishDialogOpen(false);
      setPublishPost(null);
      showNotification('발행 등록이 완료되었습니다.', 'success');
    } catch (err) {
      showNotification('발행 등록에 실패했습니다.', 'error');
    }
  };

  const closePublishDialog = () => {
    setPublishDialogOpen(false);
    setPublishPost(null);
  };

  if (authLoading) {
    return (
      <DashboardLayout title="포스트 목록">
        <Container maxWidth="xl" sx={{ mt: `${spacing.md}px` }}>
          <LoadingSpinner message="게시글 목록 로딩 중..." fullHeight={true} />
        </Container>
      </DashboardLayout>
    );
  }

  if (!user?.uid) {
    return (
      <DashboardLayout title="포스트 목록">
        <Container maxWidth="xl" sx={{ mt: `${spacing.md}px` }}>
          <Alert severity="error">사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.</Alert>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="포스트 목록">
      <Container maxWidth="xl" sx={{ py: `${spacing.xl}px`, px: { xs: 1, sm: 2 } }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
            <Typography variant="h4" sx={{
              fontWeight: 'bold',
              mb: `${spacing.xs}px`,
              color: theme.palette.mode === 'dark' ? 'white' : 'black',
              display: 'flex',
              alignItems: 'center',
              gap: `${spacing.xs}px`
            }}>
              <Assignment sx={{ color: theme.palette.mode === 'dark' ? 'white' : 'black' }} />
              내 원고 목록
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.md}px`, flexWrap: 'wrap' }}>
              <Typography variant="body1" sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}>
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
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Paper elevation={0} sx={{ p: { xs: 2, sm: 3 } }}>
            <Typography variant="body2" sx={{ mb: `${spacing.md}px`, color: 'grey.100', fontStyle: 'italic' }}>
              이 화면은 읽기 전용입니다. 카드를 터치/클릭하면 원고가 열립니다.
            </Typography>

            {loading ? (
              <LoadingSpinner message="게시글 목록 로딩 중..." fullHeight={true} />
            ) : error ? (
              <Alert severity="error">{error}</Alert>
            ) : posts.length === 0 ? (
              <Alert severity="warning">저장된 원고가 없습니다.</Alert>
            ) : (
              <CalendarView
                posts={posts}
                onPostClick={openViewer}
                theme={theme}
                onDelete={handleDelete}
                onSNS={handleSNSConvert}
                onPublish={handlePublish}
              />
            )}
          </Paper>
        </motion.div>

        <PostViewerModal
          open={viewerOpen}
          onClose={closeViewer}
          post={viewerPost}
          onDelete={handleDelete}
        />

        <Dialog open={publishDialogOpen} onClose={closePublishDialog} maxWidth="sm" fullWidth slotProps={{ backdrop: { 'aria-hidden': false } }}>
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.xs}px` }}>
            <Publish sx={{ color: theme.palette.ui?.header || colors.brand.primary }} />
            원고 발행 등록
          </DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.md}px` }}>
              실제 발행한 네이버 블로그 주소를 입력해주세요.
            </Typography>
            <Typography variant="h6" sx={{ mb: `${spacing.xs}px`, fontWeight: 600 }}>
              "{publishPost?.title || '원고 제목'}"
            </Typography>
            <TextField
              autoFocus
              margin="dense"
              label="발행 URL"
              placeholder="https://blog.naver.com/아이디/게시글"
              fullWidth
              variant="outlined"
              value={publishUrl}
              onChange={(e) => setPublishUrl(e.target.value)}
              InputProps={{ startAdornment: <Link sx={{ color: 'text.secondary', mr: `${spacing.xs}px` }} /> }}
              helperText="네이버 블로그 URL만 입력할 수 있습니다."
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={closePublishDialog} color="inherit">취소</Button>
            <Button
              onClick={handlePublishSubmit}
              variant="contained"
              sx={{
                bgcolor: theme.palette.ui?.header || colors.brand.primary,
                '&:hover': { bgcolor: theme.palette.ui?.headerHover || colors.brand.primaryHover }
              }}
            >
              발행 완료
            </Button>
          </DialogActions>
        </Dialog>

        <NotificationSnackbar open={notification.open} onClose={hideNotification} message={notification.message} severity={notification.severity} />
        <SNSConversionModal open={snsModalOpen} onClose={() => setSnsModalOpen(false)} post={snsPost} />
      </Container>
    </DashboardLayout>
  );
}
