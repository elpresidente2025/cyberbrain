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
  useMediaQuery,
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
  // 오늘 날짜를 기본값으로 설정
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${today.getMonth() + 1}-${today.getDate()}`;
  const [selectedDate, setSelectedDate] = useState(todayKey);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay = new Date(year, month, 1).getDay(); // 0: 일요일

  // 날짜별 포스트 그룹핑
  const postsByDate = posts.reduce((acc, post) => {
    const d = new Date(post.createdAt);
    const key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
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
            <Grid item xs={12 / 7} key={`empty-${i}`}>
              <Box sx={{ minHeight: 60, aspectRatio: '3 / 2' }} />
            </Grid>
          ))}

          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const dateKey = `${year}-${month + 1}-${day}`;
            const dayPosts = postsByDate[dateKey] || [];
            const todayObj = new Date();
            const isToday = day === todayObj.getDate() && month === todayObj.getMonth() && year === todayObj.getFullYear();
            const isSelected = selectedDate === dateKey;

            return (
              <Grid item xs={12 / 7} key={day}>
                <Box
                  onClick={() => {
                    setSelectedDate(isSelected ? null : dateKey);
                  }}
                  sx={{
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 1,
                    p: 0.5,
                    aspectRatio: '3 / 2',
                    minHeight: 60,
                    bgcolor: isToday ? 'primary.main' : isSelected ? 'primary.light' : 'background.paper',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 0.5,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    '&:hover': {
                      bgcolor: isToday ? 'primary.main' : 'action.hover'
                    }
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

                  {/* 포스트 개수 표시용 점 표시 */}
                  {dayPosts.length > 0 && (
                    <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5, mt: 0.5 }}>
                      {dayPosts.slice(0, 3).map((_, idx) => (
                        <Box
                          key={idx}
                          sx={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            bgcolor: isToday ? 'primary.contrastText' : 'primary.main'
                          }}
                        />
                      ))}
                      {dayPosts.length > 3 && (
                        <Typography variant="caption" sx={{ fontSize: '0.65rem', ml: 0.5 }}>
                          +{dayPosts.length - 3}
                        </Typography>
                      )}
                    </Box>
                  )}
                </Box>
              </Grid>
            );
          })}
        </Grid>
      </Paper>

      {/* 선택된 날짜의 포스트 카드 표시 */}
      {selectedDate && (() => {
        const selectedPosts = postsByDate[selectedDate] || [];
        const [y, m, d] = selectedDate.split('-');

        // 원고가 없는 경우 메시지 표시
        if (selectedPosts.length === 0) {
          return (
            <Box sx={{ mt: 3 }}>
              <Alert severity="info" sx={{ justifyContent: 'center' }}>
                {parseInt(m, 10)}월 {parseInt(d, 10)}일의 원고가 없습니다.
              </Alert>
            </Box>
          );
        }
        const formattedDate = `${y}.${String(m).padStart(2, '0')}.${String(d).padStart(2, '0')}`;

        return (
          <Box sx={{ mt: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                {formattedDate}
              </Typography>
              <Button size="small" onClick={() => setSelectedDate(null)}>
                닫기
              </Button>
            </Box>
            <Grid container spacing={2} justifyContent="center">
              {selectedPosts.map(post => {
                const preview = stripHtml(post.content || '');
                const wordCount = countWithoutSpace(preview);
                const status = post.status || 'draft';
                const statusLabel = status === 'published' ? '발행 완료' : status === 'scheduled' ? '대기 중' : status;
                const statusColor = status === 'published' ? 'success' : status === 'scheduled' ? 'warning' : 'default';
                const statusBgColor = status === 'published' ? '#2E7D32' : status === 'scheduled' ? '#F57C00' : undefined;

                // 개수에 따른 열 배치: 1개=12(전체), 2개=6(반반), 3개=4(1/3씩)
                const gridSize = selectedPosts.length === 1 ? 12 : selectedPosts.length === 2 ? 6 : 4;

                return (
                  <Grid item xs={12} sm={gridSize} key={post.id}>
                    <Card elevation={2}>
                      <CardActionArea onClick={() => onPostClick(post)}>
                        <CardContent>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                            <Chip size="small" label={statusLabel} color={statusColor} sx={{ color: 'white', backgroundColor: statusBgColor }} />
                            <Typography variant="caption" color="text.secondary">{formatDate(post.createdAt)}</Typography>
                          </Box>
                          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1, wordBreak: 'break-word' }}>
                            {post.title || '제목 없음'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 60 }}>
                            {preview || '내용 없음'}
                          </Typography>
                          <Divider sx={{ my: 1.5 }} />
                          <Typography variant="caption">글자수: {wordCount}</Typography>
                        </CardContent>
                      </CardActionArea>
                      <CardActions sx={{ justifyContent: 'space-between', pt: 0, pb: 2, px: 2 }}>
                        {/* 🆕 안내 문구 추가 */}
                        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                          클릭 시 원고 전문을 확인하실 수 있습니다.
                        </Typography>

                        <IconButton size="small" onClick={(e) => { e.stopPropagation(); onDelete(post.id, e); }}><DeleteOutline /></IconButton>
                      </CardActions>
                    </Card>
                  </Grid>
                );
              })}
            </Grid>
          </Box>
        );
      })()}
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
            <Typography variant="body2" sx={{ mb: `${spacing.md}px`, color: 'grey.100', fontStyle: 'italic', textAlign: 'center' }}>
              날짜를 클릭/터치하면 달력 하단에 원고가 나옵니다.
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

        {/* 원고 보기 모달 (자체 포함형: 복사/SNS/발행 기능 내장) */}
        <PostViewerModal
          open={viewerOpen}
          onClose={closeViewer}
          post={viewerPost}
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
              disabled={!isNaverBlogUrl(publishUrl)}
              sx={{
                bgcolor: isNaverBlogUrl(publishUrl)
                  ? (theme.palette.ui?.header || colors.brand.primary)
                  : 'action.disabledBackground',
                '&:hover': isNaverBlogUrl(publishUrl)
                  ? { bgcolor: theme.palette.ui?.headerHover || colors.brand.primaryHover }
                  : {},
                color: isNaverBlogUrl(publishUrl) ? 'white' : 'action.disabled'
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
