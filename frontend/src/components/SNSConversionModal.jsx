// frontend/src/components/SNSConversionModal.jsx
import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Box,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  Paper,
  Tabs,
  Tab,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  ContentCopy,
  Transform,
  Close
} from '@mui/icons-material';
import { convertToSNS, getSNSUsage, testSNS } from '../services/firebaseService';

// SNS 아이콘 컴포넌트 (이미지 사용)
const SNSIcon = ({ src, alt, size = 20 }) => (
  <img 
    src={src} 
    alt={alt}
    style={{ 
      width: size, 
      height: size, 
      objectFit: 'contain'
    }}
  />
);

// HTML을 평범한 텍스트로 변환하는 유틸리티 함수
function convertHtmlToFormattedText(html = '') {
  try {
    if (!html) return '';
    
    // 임시 div 엘리먼트 생성
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    
    // HTML 태그를 텍스트로 변환하면서 formatting 보존
    let text = tempDiv.innerHTML;
    
    // 블록 요소들을 줄바꿈으로 변환
    text = text.replace(/<\/?(h[1-6]|p|div|br|li)[^>]*>/gi, '\n');
    text = text.replace(/<\/?(ul|ol)[^>]*>/gi, '\n\n');
    
    // 나머지 HTML 태그 제거
    text = text.replace(/<[^>]*>/g, '');
    
    // HTML 엔티티 변환
    text = text.replace(/&nbsp;/g, ' ');
    text = text.replace(/&amp;/g, '&');
    text = text.replace(/&lt;/g, '<');
    text = text.replace(/&gt;/g, '>');
    text = text.replace(/&quot;/g, '"');
    
    // 연속된 줄바꿈을 정리 (3개 이상을 2개로)
    text = text.replace(/\n{3,}/g, '\n\n');
    
    // 앞뒤 공백 제거
    return text.trim();
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

const PLATFORMS = {
  'facebook-instagram': {
    name: 'Facebook + Instagram',
    iconSrc: '/icons/icon-facebook.png',
    instagramIconSrc: '/icons/icon-instagram.png',
    color: '#1877f2',
    maxLength: 1500,
    recommendedLength: 1500,
    isThread: false
  },
  x: {
    name: 'X',
    iconSrc: '/icons/icon-X.png',
    color: '#000000',
    maxLengthPerPost: 150,
    recommendedLength: 150,
    isThread: true
  },
  threads: {
    name: 'Threads',
    iconSrc: '/icons/icon-threads.png',
    color: '#000000',
    maxLengthPerPost: 150,
    recommendedLength: 150,
    isThread: true
  }
};

// 타래 게시물 렌더링 컴포넌트
const ThreadPostsDisplay = ({ posts, hashtags, onCopy }) => {
  // 전체 타래 복사용 텍스트 생성
  const getFullThreadText = () => {
    const postsText = posts.map((post, idx) => `[${idx + 1}/${posts.length}]\n${post.content}`).join('\n\n');
    const hashtagText = hashtags?.length > 0 ? '\n\n' + hashtags.join(' ') : '';
    return postsText + hashtagText;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {posts.map((post, index) => (
        <Box
          key={index}
          sx={{
            p: 1.5,
            border: '1px solid',
            borderColor: index === 0 ? 'primary.main' : 'divider',
            borderRadius: 1,
            backgroundColor: index === 0 ? 'primary.50' : 'white',
            position: 'relative'
          }}
        >
          {/* 게시물 번호 뱃지 */}
          <Box
            sx={{
              position: 'absolute',
              top: -8,
              left: 8,
              backgroundColor: index === 0 ? 'primary.main' : 'grey.500',
              color: 'white',
              px: 1,
              py: 0.25,
              borderRadius: 1,
              fontSize: '0.7rem',
              fontWeight: 'bold'
            }}
          >
            {index === 0 ? '훅' : `${index + 1}번`}
          </Box>

          {/* 게시물 내용 */}
          <Typography
            variant="body2"
            sx={{
              mt: 1,
              whiteSpace: 'pre-wrap',
              lineHeight: 1.6,
              fontSize: '0.85rem',
              color: '#000000'
            }}
          >
            {post.content}
          </Typography>

          {/* 글자수 */}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', textAlign: 'right', mt: 0.5 }}
          >
            {countWithoutSpace(post.content)}자
          </Typography>
        </Box>
      ))}

      {/* 해시태그 */}
      {hashtags && hashtags.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
          {hashtags.map((hashtag, index) => (
            <Chip
              key={index}
              label={hashtag}
              size="small"
              color="primary"
              variant="outlined"
              sx={{ fontSize: '0.7rem', height: 24 }}
            />
          ))}
        </Box>
      )}
    </Box>
  );
};


function SNSConversionModal({ open, onClose, post }) {
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [usage, setUsage] = useState(null);
  const [copySuccess, setCopySuccess] = useState('');

  // 사용량 정보 조회
  useEffect(() => {
    if (open) {
      fetchUsage();
    }
  }, [open]);

  const fetchUsage = async () => {
    try {
      const result = await getSNSUsage();
      setUsage(result);
    } catch (err) {
      console.error('SNS 사용량 조회 실패:', err);
    }
  };

  const handleConvert = async () => {
    if (!post?.id) {
      setError('원고 정보가 없습니다.');
      return;
    }

    setLoading(true);
    setError('');
    setResults({});

    try {
      console.log('🔍 post 객체 전체:', post);
      console.log('🔍 post.id:', post.id, 'typeof:', typeof post.id);
      
      if (!post || !post.id) {
        throw new Error(`post 또는 post.id가 없습니다: ${JSON.stringify(post)}`);
      }
      
      // testSNS 함수 먼저 테스트
      console.log('🧪 testSNS 함수 테스트 중...');
      try {
        const testResult = await testSNS();
        console.log('✅ testSNS 성공:', testResult);
      } catch (testError) {
        console.error('❌ testSNS 실패:', testError);
        throw new Error(`SNS 함수 테스트 실패: ${testError.message}`);
      }
      
      const result = await convertToSNS(post.id);
      
      console.log('🔍 SNS 변환 결과:', result);
      console.log('🔍 result.results:', result.results);
      console.log('🔍 결과 키들:', Object.keys(result.results || {}));
      
      // 각 플랫폼 결과 상세 확인
      Object.entries(result.results || {}).forEach(([platform, data]) => {
        console.log(`📱 ${platform}:`, {
          content: data?.content || 'EMPTY',
          contentLength: data?.content?.length || 0,
          hashtags: data?.hashtags || [],
          hashtagCount: data?.hashtags?.length || 0
        });
      });
      
      setResults(result.results);
      
      // 사용량 정보 갱신
      await fetchUsage();
      
    } catch (err) {
      console.error('SNS 변환 실패:', err);
      setError(err.message || 'SNS 변환에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopySuccess('복사되었습니다!');
      setTimeout(() => setCopySuccess(''), 2000);
    } catch (err) {
      console.error('복사 실패:', err);
    }
  };

  const handleClose = () => {
    setResults({});
    setError('');
    setCopySuccess('');
    onClose();
  };

  const canConvert = usage?.isActive;
  const hasResults = Object.keys(results).length > 0;

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      slotProps={{ backdrop: { 'aria-hidden': false } }}
      PaperProps={{
        sx: { minHeight: '600px' }
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Transform color="primary" />
          <Typography variant="h6">SNS 변환</Typography>
        </Box>
        <IconButton onClick={handleClose} size="small">
          <Close />
        </IconButton>
      </DialogTitle>

      <DialogContent>
        {/* 접근 권한 정보 */}
        {usage && (
          <Alert 
            severity={canConvert ? "success" : "warning"} 
            sx={{ mb: 2 }}
          >
            <Typography variant="body2">
              <strong>SNS 변환 사용 가능</strong>
            </Typography>
          </Alert>
        )}

        {/* 원본 원고 미리보기 */}
        <Typography variant="h6" sx={{ mb: 1 }}>원본 원고</Typography>
        <Paper sx={{ p: 2, mb: 3, maxHeight: '150px', overflow: 'auto', bgcolor: 'white' }}>
          <Typography variant="body2" style={{ color: '#000000' }}>
            {post?.title && <><strong>제목: {post.title}</strong><br /><br /></>}
          </Typography>
          <Typography
            variant="body2"
            style={{ color: '#000000' }}
            sx={{
              mt: 1,
              whiteSpace: 'pre-wrap',
              lineHeight: 1.6
            }}
          >
            {convertHtmlToFormattedText(post?.content)?.substring(0, 300)}
            {convertHtmlToFormattedText(post?.content)?.length > 300 && '...'}
          </Typography>
        </Paper>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* SNS 변환 결과 */}
        {hasResults && (
          <Box>
            {/* Facebook/Instagram 단일 게시물 */}
            {results['facebook-instagram'] && (
              <Paper sx={{ p: 2, mb: 3, border: '1px solid', borderColor: 'divider' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <SNSIcon src={PLATFORMS['facebook-instagram'].iconSrc} alt="Facebook" size={18} />
                    <SNSIcon src={PLATFORMS['facebook-instagram'].instagramIconSrc} alt="Instagram" size={18} />
                    <Typography variant="subtitle1" fontWeight="bold">
                      Facebook + Instagram
                    </Typography>
                  </Box>
                  <Tooltip title="전체 복사하기">
                    <IconButton
                      size="small"
                      onClick={() => {
                        const r = results['facebook-instagram'];
                        const text = r.content + (r.hashtags?.length > 0 ? '\n\n' + r.hashtags.join(' ') : '');
                        handleCopy(text);
                      }}
                    >
                      <ContentCopy fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                <Box sx={{
                  maxHeight: '200px',
                  overflowY: 'auto',
                  p: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                  backgroundColor: 'white',
                  mb: 1
                }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, color: '#000000' }}>
                    {results['facebook-instagram'].content}
                  </Typography>
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'right', mb: 1 }}>
                  {countWithoutSpace(results['facebook-instagram'].content)}자 (공백 제외)
                </Typography>
                {results['facebook-instagram'].hashtags?.length > 0 && (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {results['facebook-instagram'].hashtags.map((tag, idx) => (
                      <Chip key={idx} label={tag} size="small" color="primary" variant="outlined" sx={{ fontSize: '0.7rem' }} />
                    ))}
                  </Box>
                )}
              </Paper>
            )}

            {/* X와 Threads 타래 - 2열 그리드 */}
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2, mb: 2 }}>
              {/* X 타래 */}
              {results.x && (
                <Paper sx={{ p: 2, border: '1px solid', borderColor: 'divider' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <SNSIcon src={PLATFORMS.x.iconSrc} alt="X" size={20} />
                      <Typography variant="subtitle1" fontWeight="bold">X 타래</Typography>
                      {results.x.postCount && (
                        <Chip label={`${results.x.postCount}개`} size="small" color="primary" sx={{ fontSize: '0.7rem' }} />
                      )}
                    </Box>
                    <Tooltip title="전체 타래 복사">
                      <IconButton
                        size="small"
                        onClick={() => {
                          const r = results.x;
                          if (r.posts) {
                            const text = r.posts.map((p, i) => `[${i + 1}/${r.posts.length}]\n${p.content}`).join('\n\n');
                            const hashtagText = r.hashtags?.length > 0 ? '\n\n' + r.hashtags.join(' ') : '';
                            handleCopy(text + hashtagText);
                          }
                        }}
                      >
                        <ContentCopy fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                  <Box sx={{ maxHeight: '400px', overflowY: 'auto' }}>
                    {results.x.posts ? (
                      <ThreadPostsDisplay posts={results.x.posts} hashtags={results.x.hashtags} onCopy={handleCopy} />
                    ) : (
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', color: '#000000' }}>
                        {results.x.content}
                      </Typography>
                    )}
                  </Box>
                  {results.x.totalWordCount && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'right', mt: 1 }}>
                      총 {results.x.totalWordCount}자 (공백 제외)
                    </Typography>
                  )}
                </Paper>
              )}

              {/* Threads 타래 */}
              {results.threads && (
                <Paper sx={{ p: 2, border: '1px solid', borderColor: 'divider' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <SNSIcon src={PLATFORMS.threads.iconSrc} alt="Threads" size={20} />
                      <Typography variant="subtitle1" fontWeight="bold">Threads 타래</Typography>
                      {results.threads.postCount && (
                        <Chip label={`${results.threads.postCount}개`} size="small" color="primary" sx={{ fontSize: '0.7rem' }} />
                      )}
                    </Box>
                    <Tooltip title="전체 타래 복사">
                      <IconButton
                        size="small"
                        onClick={() => {
                          const r = results.threads;
                          if (r.posts) {
                            const text = r.posts.map((p, i) => `[${i + 1}/${r.posts.length}]\n${p.content}`).join('\n\n');
                            const hashtagText = r.hashtags?.length > 0 ? '\n\n' + r.hashtags.join(' ') : '';
                            handleCopy(text + hashtagText);
                          }
                        }}
                      >
                        <ContentCopy fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                  <Box sx={{ maxHeight: '400px', overflowY: 'auto' }}>
                    {results.threads.posts ? (
                      <ThreadPostsDisplay posts={results.threads.posts} hashtags={results.threads.hashtags} onCopy={handleCopy} />
                    ) : (
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', color: '#000000' }}>
                        {results.threads.content}
                      </Typography>
                    )}
                  </Box>
                  {results.threads.totalWordCount && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'right', mt: 1 }}>
                      총 {results.threads.totalWordCount}자 (공백 제외)
                    </Typography>
                  )}
                </Paper>
              )}
            </Box>

            {copySuccess && (
              <Alert severity="success" sx={{ mt: 2 }}>
                {copySuccess}
              </Alert>
            )}

            {/* 아이콘 출처 표시 */}
            <Box sx={{ mt: 3, textAlign: 'center', borderTop: '1px solid', borderColor: 'divider', pt: 2 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                SNS 아이콘 ⓒ{' '}
                <a 
                  href="https://www.flaticon.com/kr/free-icons/" 
                  title="SNS 아이콘"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ 
                    color: '#666', 
                    textDecoration: 'none',
                    '&:hover': {
                      textDecoration: 'underline'
                    }
                  }}
                >
                  Freepik - Flaticon
                </a>
              </Typography>
            </Box>
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ p: 2 }}>
        <Button onClick={handleClose}>닫기</Button>
        {!hasResults && (
          <Button
            variant="contained"
            onClick={handleConvert}
            disabled={loading || !canConvert}
            startIcon={loading ? <CircularProgress size={20} /> : <Transform />}
          >
            {loading ? '모든 플랫폼 변환 중...' : '모든 SNS 플랫폼으로 변환'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

export default SNSConversionModal;