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
  Close,
  Refresh
} from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';
import { convertToSNS, getSNSUsage, testSNS } from '../services/firebaseService';
import { useAuth } from '../hooks/useAuth';
import { hasAdminOrTesterAccess } from '../utils/authz';
import { containsKnownShortUrl, replaceKnownShortUrls } from '../config/branding';

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
    maxLengthPerPost: 250,
    recommendedLength: 250,
    isThread: true
  },
  threads: {
    name: 'Threads',
    iconSrc: '/icons/icon-threads.png',
    color: '#000000',
    maxLengthPerPost: 250,
    recommendedLength: 250,
    isThread: true
  }
};

const BLOG_CTA_ONLY_PATTERN = /^\s*(?:더\s*자세한\s*내용은\s*블로그에서\s*확인해(?:주세요|보세요)|자세한\s*내용은\s*블로그에서\s*확인해(?:주세요|보세요)|블로그\s*링크)\s*[:：]?\s*$/;

function replaceShortUrlWithOriginal(text, originalUrl) {
  if (!text || !originalUrl) return text;
  return replaceKnownShortUrls(text, originalUrl);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripThreadBlogUrlArtifacts(text, originalUrl) {
  const normalizedUrl = String(originalUrl || '').trim();
  const urlPattern = normalizedUrl ? new RegExp(escapeRegExp(normalizedUrl), 'g') : null;

  const lines = String(text || '')
    .split('\n')
    .map((line) => {
      let cleaned = String(line || '');
      if (urlPattern) {
        cleaned = cleaned.replace(urlPattern, '');
      }
      cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
      if (!cleaned) return '';
      if (BLOG_CTA_ONLY_PATTERN.test(cleaned)) return '';
      return cleaned;
    })
    .filter(Boolean);

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function normalizeThreadPosts(posts, originalUrl) {
  const normalizedUrl = String(originalUrl || '').trim();
  if (!Array.isArray(posts) || posts.length === 0) return posts;

  const cleanedPosts = posts.map((post) => {
    const replaced = replaceShortUrlWithOriginal(post?.content || '', normalizedUrl);
    const content = stripThreadBlogUrlArtifacts(replaced, normalizedUrl);
    return {
      ...post,
      content,
      wordCount: countWithoutSpace(content)
    };
  });

  if (!normalizedUrl) {
    return cleanedPosts;
  }

  const lastIndex = cleanedPosts.length - 1;
  const lastPost = cleanedPosts[lastIndex] || {};
  const nextContent = [String(lastPost.content || '').trim(), normalizedUrl]
    .filter(Boolean)
    .join('\n');

  cleanedPosts[lastIndex] = {
    ...lastPost,
    content: nextContent,
    wordCount: countWithoutSpace(nextContent)
  };

  return cleanedPosts;
}

function normalizeSnsResultUrls(result, originalUrl) {
  if (!result || !originalUrl) return result;

  if (result.isThread && Array.isArray(result.posts)) {
    const posts = normalizeThreadPosts(result.posts, originalUrl);
    return {
      ...result,
      posts,
      totalWordCount: posts.reduce((sum, post) => sum + countWithoutSpace(post.content), 0)
    };
  }

  if (typeof result.content === 'string') {
    const replaced = replaceShortUrlWithOriginal(result.content, originalUrl);
    const stripped = stripThreadBlogUrlArtifacts(replaced, originalUrl);
    const hasShortUrl = containsKnownShortUrl(result.content || '');
    const shouldAppendUrl = Boolean(
      originalUrl && (
        replaced.includes(originalUrl) || hasShortUrl
      )
    );
    const content = shouldAppendUrl
      ? [stripped, originalUrl].filter(Boolean).join('\n')
      : stripped;
    return {
      ...result,
      content,
      wordCount: countWithoutSpace(content)
    };
  }

  return result;
}

function normalizeSnsResults(results, originalUrl) {
  if (!results || !originalUrl) return results || {};

  return Object.fromEntries(
    Object.entries(results).map(([platform, result]) => [
      platform,
      normalizeSnsResultUrls(result, originalUrl)
    ])
  );
}

// 타래 게시물 렌더링 컴포넌트
const ThreadPostsDisplay = ({ posts, hashtags, onCopy }) => {
  const theme = useTheme();
  const highlightedPostBg = alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.2 : 0.08);
  const defaultPostBg = theme.palette.mode === 'dark'
    ? alpha(theme.palette.common.white, 0.04)
    : theme.palette.background.paper;
  const badgeBg = theme.palette.mode === 'dark'
    ? alpha(theme.palette.common.white, 0.16)
    : theme.palette.grey[700];

  // 전체 타래 복사용 텍스트 생성
  const getFullThreadText = () => {
    const postsText = posts.map((post, idx) => `[${idx + 1}/${posts.length}]\n${post.content}`).join('\n\n');
    const hashtagText = hashtags?.length > 0 ? '\n\n' + hashtags.join(' ') : '';
    return postsText + hashtagText;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      {posts.map((post, index) => (
        <Box
          key={index}
          sx={{
            p: 1.5,
            border: '1px solid',
            borderColor: index === 0 ? 'primary.main' : 'divider',
            borderRadius: 1,
            backgroundColor: index === 0 ? highlightedPostBg : defaultPostBg,
            position: 'relative',
            minWidth: 0,
            overflow: 'hidden'
          }}
        >
          {/* 게시물 번호 뱃지 (게시물이 2개 이상일 때만 표시) */}
          {posts.length > 1 && (
            <Box
              sx={{
                position: 'absolute',
                top: -8,
                left: 8,
                backgroundColor: index === 0 ? 'primary.main' : badgeBg,
                color: theme.palette.common.white,
                px: 1,
                py: 0.25,
                borderRadius: 4,
                fontSize: '0.75rem',
                fontWeight: 'bold',
                boxShadow: 1
              }}
            >
              {index + 1}/{posts.length}
            </Box>
          )}

          {/* 게시물 내용 */}
          <Typography
            variant="body2"
            sx={{
              mt: 1,
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
              lineHeight: 1.6,
              fontSize: '0.85rem',
              color: 'text.primary'
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
  const theme = useTheme();
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [usage, setUsage] = useState(null);
  const [copySuccess, setCopySuccess] = useState('');
  const [regenerating, setRegenerating] = useState({}); // { platform: boolean }

  const { user } = useAuth();
  const isAdminOrTester = hasAdminOrTesterAccess(user);
  // DEBUG: Role check
  useEffect(() => {
    console.log('🔍 [SNSModal] User Role Check:', {
      role: user?.role,
      isAdmin: user?.isAdmin,
      isTester: user?.isTester,
      computedAccess: isAdminOrTester
    });
  }, [isAdminOrTester, user]);

  // DEBUG: Role check logic preserved but log kept
  // const isAdminOrTester = true; // Reverted for security
  // 🆕 모달이 열릴 때 기존 SNS 변환 결과 불러오기
  useEffect(() => {
    if (open) {
      fetchUsage();
      // 기존 변환 결과가 있으면 불러오기
      if (post?.snsConversions && Object.keys(post.snsConversions).length > 0) {
        console.log('📦 기존 SNS 변환 결과 불러오기:', Object.keys(post.snsConversions));
        setResults(normalizeSnsResults(post.snsConversions, post?.publishUrl));
      } else {
        setResults({});
      }
    }
  }, [open, post?.snsConversions]);

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

      setResults(normalizeSnsResults(result.results, post?.publishUrl));

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

  const handleRegenerate = async (platform) => {
    if (!post?.id) return;

    setRegenerating(prev => ({ ...prev, [platform]: true }));
    setError('');

    try {
      console.log(`🔄 ${platform} 재생성 시작...`);
      const result = await convertToSNS(post.id, platform);

      if (result.results && result.results[platform]) {
        console.log(`✅ ${platform} 재생성 완료`);
        setResults(prev => ({
          ...prev,
          [platform]: normalizeSnsResultUrls(result.results[platform], post?.publishUrl)
        }));
        await fetchUsage();
      }
    } catch (err) {
      console.error(`${platform} 재생성 실패:`, err);
      setError(`${platform} 재생성 실패: ${err.message}`);
    } finally {
      setRegenerating(prev => ({ ...prev, [platform]: false }));
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
  const loadingOverlayBg = alpha(theme.palette.background.paper, theme.palette.mode === 'dark' ? 0.9 : 0.94);
  const contentBoxBg = theme.palette.mode === 'dark'
    ? alpha(theme.palette.common.white, 0.04)
    : theme.palette.background.paper;
  const contentBoxBorder = theme.palette.mode === 'dark'
    ? alpha(theme.palette.common.white, 0.12)
    : theme.palette.divider;
  const mutedLinkColor = theme.palette.text.secondary;

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

      <DialogContent sx={{ position: 'relative' }}>
        {/* 로딩 오버레이 */}
        {loading && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: loadingOverlayBg,
              zIndex: 10,
              gap: 2
            }}
          >
            <CircularProgress size={40} />
            <Typography variant="body1" color="text.secondary" fontWeight="medium">
              모든 SNS 플랫폼에 최적화된 원고를 생성하고 있습니다...
            </Typography>
            <Typography variant="caption" color="text.disabled">
              (약 10-20초 소요됩니다)
            </Typography>
          </Box>
        )}

        {/* 🆕 저장된 원고가 없을 때 안내 문구 */}
        {!hasResults && !loading && (
          <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: 300,
            color: 'text.secondary'
          }}>
            <Transform sx={{ fontSize: 64, mb: 2, opacity: 0.5 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              저장된 원고가 없습니다.
            </Typography>
            <Typography variant="body2" color="text.secondary">
              아래 버튼을 눌러 SNS 원고를 생성해보세요.
            </Typography>
          </Box>
        )}

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

                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {isAdminOrTester && (
                      <Tooltip title="이 플랫폼만 재생성 (관리자 전용)">
                        <IconButton
                          size="small"
                          onClick={() => handleRegenerate('facebook-instagram')}
                          disabled={regenerating['facebook-instagram']}
                        >
                          {regenerating['facebook-instagram'] ? <CircularProgress size={20} /> : <Refresh fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                    )}
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
                </Box>
                <Box sx={{
                  maxHeight: '200px',
                  overflowY: 'auto',
                  p: 1.5,
                  border: '1px solid',
                  borderColor: contentBoxBorder,
                  borderRadius: 1,
                  backgroundColor: contentBoxBg,
                  mb: 1
                }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, color: 'text.primary' }}>
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
                <Paper sx={{ p: 2, border: '1px solid', borderColor: 'divider', minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <SNSIcon src={PLATFORMS.x.iconSrc} alt="X" size={20} />
                      <Typography variant="subtitle1" fontWeight="bold">X 타래</Typography>
                      {results.x.postCount && (
                        <Chip label={`${results.x.postCount}개`} size="small" color="primary" sx={{ fontSize: '0.7rem' }} />
                      )}
                    </Box>

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {isAdminOrTester && (
                        <Tooltip title="이 플랫폼만 재생성 (관리자 전용)">
                          <IconButton
                            size="small"
                            onClick={() => handleRegenerate('x')}
                            disabled={regenerating['x']}
                          >
                            {regenerating['x'] ? <CircularProgress size={20} /> : <Refresh fontSize="small" />}
                          </IconButton>
                        </Tooltip>
                      )}
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
                  </Box>
                  <Box sx={{ maxHeight: '400px', overflowY: 'auto', overflowX: 'hidden', minWidth: 0 }}>
                    {results.x.posts ? (
                      <ThreadPostsDisplay posts={results.x.posts} hashtags={results.x.hashtags} onCopy={handleCopy} />
                    ) : (
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', wordBreak: 'break-word', color: 'text.primary' }}>
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
                <Paper sx={{ p: 2, border: '1px solid', borderColor: 'divider', minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <SNSIcon src={PLATFORMS.threads.iconSrc} alt="Threads" size={20} />
                      <Typography variant="subtitle1" fontWeight="bold">Threads 타래</Typography>
                      {results.threads.postCount && (
                        <Chip label={`${results.threads.postCount}개`} size="small" color="primary" sx={{ fontSize: '0.7rem' }} />
                      )}
                    </Box>

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {isAdminOrTester && (
                        <Tooltip title="이 플랫폼만 재생성 (관리자 전용)">
                          <IconButton
                            size="small"
                            onClick={() => handleRegenerate('threads')}
                            disabled={regenerating['threads']}
                          >
                            {regenerating['threads'] ? <CircularProgress size={20} /> : <Refresh fontSize="small" />}
                          </IconButton>
                        </Tooltip>
                      )}
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
                  </Box>
                  <Box sx={{ maxHeight: '400px', overflowY: 'auto', overflowX: 'hidden', minWidth: 0 }}>
                    {results.threads.posts ? (
                      <ThreadPostsDisplay posts={results.threads.posts} hashtags={results.threads.hashtags} onCopy={handleCopy} />
                    ) : (
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', wordBreak: 'break-word', color: 'text.primary' }}>
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
                    color: mutedLinkColor,
                    textDecoration: 'none'
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
            startIcon={<Transform />}
          >
            {loading ? '모든 플랫폼 변환 중...' : '모든 SNS 플랫폼으로 변환'}
          </Button>
        )}
      </DialogActions>
    </Dialog >
  );
}

export default SNSConversionModal;
