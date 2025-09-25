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
  Snackbar,
  Alert,
  Dialog,
  DialogTitle,
  useTheme,
  DialogContent,
  DialogActions,
  Button,
  Divider,
  TextField,
} from '@mui/material';
import { ContentCopy, DeleteOutline, Assignment, Publish, Link, Share } from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import SNSConversionModal from '../components/SNSConversionModal';
import { LoadingSpinner } from '../components/loading';
import PostViewerModal from '../components/PostViewerModal';
import { useAuth } from '../hooks/useAuth';
import { callFunctionWithNaverAuth } from '../services/firebaseService';

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

// 怨듬갚 ?쒖쇅 湲?먯닔 怨꾩궛 (Java 肄붾뱶? ?숈씪??濡쒖쭅)
function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i++) {
    if (!/\s/.test(str.charAt(i))) { // 怨듬갚 臾몄옄媛 ?꾨땶 寃쎌슦
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
  const [snack, setSnack] = useState({ open: false, message: '', severity: 'success' });
  const [error, setError] = useState('');
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerPost, setViewerPost] = useState(null);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishPost, setPublishPost] = useState(null);
  const [publishUrl, setPublishUrl] = useState('');
  const [snsModalOpen, setSnsModalOpen] = useState(false);
  const [snsPost, setSnsPost] = useState(null);

  // ?붾쾭源?濡쒓렇
  console.log('?뵇 user:', user);
  console.log('?뵇 user?.uid:', user?.uid);
  console.log('?뵇 authLoading:', authLoading);

  // Network functions - ?ㅼ씠踰??몄쬆 ?쒖뒪???ъ슜

  useEffect(() => {
    let mounted = true;
    console.log('?뱥 PostsListPage useEffect ?ㅽ뻾 以?..', { user: !!user, uid: user?.uid });
    (async () => {
      try {
        console.log('?봽 getUserPosts ?몄텧 ?쒖옉...');
        setLoading(true);
        if (!user?.uid) {
          console.log('???ъ슜??UID ?놁쓬');
          setError('?ъ슜???뺣낫瑜?遺덈윭?????놁뒿?덈떎. ?ㅼ떆 濡쒓렇?명빐二쇱꽭??');
          return;
        }
        
        console.log('?? Firebase Functions ?몄텧:', { uid: user.uid });
        const res = await callFunctionWithNaverAuth('getUserPosts');
        console.log('??getUserPosts ?묐떟:', res);
        const list = res?.posts || [];
        console.log('?뱷 泥섎━??posts 紐⑸줉:', list);
        console.log('?뱷 posts 媛쒖닔:', list.length);
        console.log('?뱷 泥?踰덉㎏ post:', list[0]);
        if (!mounted) return;
        setPosts(list);
        
        // URL 荑쇰━ ?뚮씪誘명꽣?먯꽌 openPost ?뺤씤?섍퀬 ?먮룞?쇰줈 Modal ?닿린
        const urlParams = new URLSearchParams(location.search);
        const openPostId = urlParams.get('openPost');
        if (openPostId && list.length > 0) {
          const postToOpen = list.find(post => post.id === openPostId);
          if (postToOpen) {
            console.log('?뵇 ?먮룞?쇰줈 ???먭퀬 李얠쓬:', postToOpen);
            setViewerPost(postToOpen);
            setViewerOpen(true);
            // URL?먯꽌 荑쇰━ ?뚮씪誘명꽣 ?쒓굅 (源붾걫?섍쾶)
            navigate('/posts', { replace: true });
          }
        }
      } catch (e) {
        console.error('??getUserPosts ?먮윭:', e);
        console.error('???먮윭 ?몃??ы빆:', {
          message: e.message,
          code: e.code,
          stack: e.stack
        });
        setError('紐⑸줉??遺덈윭?ㅼ? 紐삵뻽?듬땲?? ' + e.message);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [user?.uid]);

  const handleCopy = (content, e) => {
    if (e) e.stopPropagation();
    try {
      const text = stripHtml(content);
      navigator.clipboard.writeText(text);
      setSnack({ open: true, message: '?대┰蹂대뱶??蹂듭궗?섏뿀?듬땲??', severity: 'success' });
    } catch (err) {
      console.error(err);
      setSnack({ open: true, message: '蹂듭궗???ㅽ뙣?덉뒿?덈떎.', severity: 'error' });
    }
  };

  const handleDelete = async (postId, e) => {
    if (e) e.stopPropagation();
    if (!postId) return;
    const ok = window.confirm('?뺣쭚 ???먭퀬瑜???젣?섏떆寃좎뒿?덇퉴? ???묒뾽? ?섎룎由????놁뒿?덈떎.');
    if (!ok) return;
    try {
      // ?ㅼ씠踰??몄쬆 ?쒖뒪???ъ슜
      const { callHttpFunction } = await import('../services/firebaseService');
      await callHttpFunction('deletePost', { postId });
      
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      setSnack({ open: true, message: '??젣?섏뿀?듬땲??', severity: 'info' });
      if (viewerPost?.id === postId) {
        setViewerOpen(false);
        setViewerPost(null);
      }
    } catch (err) {
      console.error(err);
      setSnack({ open: true, message: err.message || '??젣???ㅽ뙣?덉뒿?덈떎.', severity: 'error' });
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
      setSnack({ open: true, message: '諛쒗뻾 URL???낅젰?댁＜?몄슂.', severity: 'error' });
      return;
    }

    try {
      await callFunctionWithNaverAuth('publishPost', { 
        postId: publishPost.id, 
        publishUrl: publishUrl.trim() 
      });
      
      // 濡쒖뺄 ?곹깭 ?낅뜲?댄듃
      setPosts(prev => prev.map(p => 
        p.id === publishPost.id 
          ? { ...p, publishUrl: publishUrl.trim(), publishedAt: new Date().toISOString() }
          : p
      ));
      
      setPublishDialogOpen(false);
      setPublishPost(null);
      setPublishUrl('');
      setSnack({ open: true, message: '諛쒗뻾 ?꾨즺! 寃뚯씠誘명뵾耳?댁뀡 ?ъ씤?몃? ?띾뱷?덉뒿?덈떎.', severity: 'success' });
    } catch (err) {
      console.error(err);
      setSnack({ open: true, message: '諛쒗뻾 ?깅줉???ㅽ뙣?덉뒿?덈떎.', severity: 'error' });
    }
  };

  const closePublishDialog = () => {
    setPublishDialogOpen(false);
    setPublishPost(null);
    setPublishUrl('');
  };

  if (authLoading) {
    return (
      <DashboardLayout title="?ъ뒪??紐⑸줉">
        <Container maxWidth="xl" sx={{ mt: 2 }}>
          <LoadingSpinner message="寃뚯떆湲 紐⑸줉 濡쒕뵫 以?.." fullHeight={true} />
        </Container>
      </DashboardLayout>
    );
  }

  if (!user?.uid) {
    return (
      <DashboardLayout title="?ъ뒪??紐⑸줉">
        <Container maxWidth="xl" sx={{ mt: 2 }}>
          <Alert severity="error">?ъ슜???뺣낫瑜?遺덈윭?????놁뒿?덈떎. ?ㅼ떆 濡쒓렇?명빐二쇱꽭??</Alert>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="?ъ뒪??紐⑸줉">
      <Container maxWidth="xl" sx={{ py: 4, px: { xs: 1, sm: 2 } }}>
        {/* ?섏씠吏 ?ㅻ뜑 */}
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
            ???먭퀬 紐⑸줉
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="body1" color="text.secondary">
              ?앹꽦???먭퀬瑜?愿由ы븯怨?蹂듭궗?????덉뒿?덈떎
            </Typography>
            <Chip 
              label={`${posts.length}개`} 
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
            ???붾㈃? ?쎄린 ?꾩슜?낅땲?? 移대뱶瑜??곗튂/?대┃?섎㈃ ?먭퀬媛 ?대┰?덈떎. 蹂듭궗 ??硫붾え?????몃? ?몄쭛湲곗뿉??吏곸젒 ?섏젙?섏꽭??
          </Typography>

          {loading ? (
            <LoadingSpinner message="寃뚯떆湲 紐⑸줉 濡쒕뵫 以?.." fullHeight={true} />
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : posts.length === 0 ? (
            <Alert severity="warning">??λ맂 ?먭퀬媛 ?놁뒿?덈떎.</Alert>
          ) : (
            <Grid container spacing={2}>
              {posts.map((p) => {
                const preview = stripHtml(p.content || '');
                const wordCount = countWithoutSpace(preview); // 怨듬갚 ?쒖쇅 湲?먯닔濡?怨꾩궛
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
                            title={p.title || '?쒕ぉ ?놁쓬'}
                          >
                            {p.title || '?쒕ぉ ?놁쓬'}
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
                            {preview || '?댁슜 誘몃━蹂닿린媛 ?놁뒿?덈떎.'}
                          </Typography>

                          <Divider sx={{ my: 1.5 }} />

                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="caption" sx={{ color: '#000000 !important' }}>
                              湲?먯닔: {wordCount} (怨듬갚 ?쒖쇅)
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#000000 !important' }}>
                              ?앹꽦??{formatDate(p.createdAt)}
                            </Typography>
                          </Box>
                        </CardContent>
                      </CardActionArea>

                      <CardActions sx={{ justifyContent: 'space-between', pt: 0 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          {p.publishUrl && (
                            <Chip 
                              size="small" 
                              label="諛쒗뻾?꾨즺" 
                              color="primary" 
                              variant="outlined"
                              icon={<Publish />}
                              sx={{ fontSize: '0.7rem' }}
                            />
                          )}
                        </Box>
                        <Box>
                          <Tooltip title="SNS 변환">
                            <IconButton 
                              size="small" 
                              onClick={(e) => handleSNSConvert(p, e)}
                              sx={{ color: '#d22730' }}
                            >
                              <Share fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="諛쒗뻾">
                            <IconButton 
                              size="small" 
                              onClick={(e) => handlePublish(p, e)}
                              sx={{ color: p.publishUrl ? '#006261' : '#152484' }}
                            >
                              <Publish fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="蹂듭궗">
                            <IconButton size="small" onClick={(e) => handleCopy(p.content, e)}>
                              <ContentCopy fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="??젣">
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

        {/* ?먭퀬 蹂닿린 紐⑤떖 */}
        <PostViewerModal
          open={viewerOpen}
          onClose={closeViewer}
          post={viewerPost}
          onDelete={handleDelete}
        />

        {/* 諛쒗뻾 URL ?낅젰 ?ㅼ씠?쇰줈洹?*/}
        <Dialog open={publishDialogOpen} onClose={closePublishDialog} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Publish sx={{ color: '#152484' }} />
            ?먭퀬 諛쒗뻾 ?깅줉
          </DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              ?ㅼ젣 諛쒗뻾??釉붾줈洹?SNS 二쇱냼瑜??낅젰?섏뿬 寃뚯씠誘명뵾耳?댁뀡 ?ъ씤?몃? ?띾뱷?섏꽭??
            </Typography>
            <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
              "{publishPost?.title || '?먭퀬 ?쒕ぉ'}"
            </Typography>
            <TextField
              autoFocus
              margin="dense"
              label="諛쒗뻾 URL"
              placeholder="https://blog.example.com/my-post"
              fullWidth
              variant="outlined"
              value={publishUrl}
              onChange={(e) => setPublishUrl(e.target.value)}
              InputProps={{
                startAdornment: <Link sx={{ color: 'text.secondary', mr: 1 }} />,
              }}
              helperText="?ㅼ씠踰?釉붾줈洹? ?곗뒪?좊━, 釉뚮윴移? ?몄뒪?洹몃옩 ???ㅼ젣 諛쒗뻾??二쇱냼瑜??낅젰?섏꽭??"
              FormHelperTextProps={{ sx: { color: 'black' } }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={closePublishDialog} color="inherit">
              痍⑥냼
            </Button>
            <Button 
              onClick={handlePublishSubmit} 
              variant="contained"
              sx={{ 
                bgcolor: '#152484',
                '&:hover': { bgcolor: '#003A87' }
              }}
            >
              諛쒗뻾 ?꾨즺
            </Button>
          </DialogActions>
        </Dialog>

        <Snackbar
          open={snack.open}
          autoHideDuration={4000}
          onClose={() => setSnack((s) => ({ ...s, open: false }))}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert
            onClose={() => setSnack((s) => ({ ...s, open: false }))}
            severity={snack.severity}
            sx={{ width: '100%' }}
          >
            {snack.message}
          </Alert>
        </Snackbar>

        {/* SNS 蹂??紐⑤떖 */}
        <SNSConversionModal
          open={snsModalOpen}
          onClose={() => setSnsModalOpen(false)}
          post={snsPost}
        />

      </Container>
    </DashboardLayout>
  );
}







