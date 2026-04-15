// frontend/src/components/PostViewerModal.jsx
import React, { useState, useMemo } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  TextField,
  Tooltip,
  useTheme
} from '@mui/material';
import { ContentCopy, Transform, Publish, Link } from '@mui/icons-material';
import { callFunctionWithNaverAuth } from '../services/firebaseService';
import { NotificationSnackbar, useNotification } from './ui';
import { useAuth } from '../hooks/useAuth';
import { transitions } from '../theme/tokens';
import { hasAdminOrTesterAccess } from '../utils/authz';
import SNSConversionModal from './SNSConversionModal'; // 🆕 내장형 SNS 모달

// 유틸리티 함수들
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

function convertHtmlToFormattedText(html = '') {
  try {
    if (!html) return '';
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    let text = tempDiv.innerHTML;
    text = text.replace(/<\/?(h[1-6]|p|div|br|li)[^>]*>/gi, '\n');
    text = text.replace(/<\/?(ul|ol)[^>]*>/gi, '\n\n');
    text = text.replace(/<[^>]*>/g, '');
    text = text.replace(/&nbsp;/g, ' ');
    text = text.replace(/&amp;/g, '&');
    text = text.replace(/&lt;/g, '<');
    text = text.replace(/&gt;/g, '>');
    text = text.replace(/&quot;/g, '"');
    text = text.replace(/\n{3,}/g, '\n\n');
    return text.trim();
  } catch {
    return html || '';
  }
}

/**
 * PostViewerModal - 완전 자체 포함형 원고 뷰어
 * 
 * 부모 컴포넌트는 단순히 open, onClose, post만 전달하면 됩니다.
 * 복사, SNS 변환, 발행 기능은 모두 이 컴포넌트 내부에서 처리됩니다.
 */
export default function PostViewerModal({
  open,
  onClose,
  post
}) {
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();
  const { user } = useAuth();

  // 🆕 내장형 SNS 모달 상태
  const [snsOpen, setSnsOpen] = useState(false);

  // 🆕 발행 다이얼로그 상태
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishUrl, setPublishUrl] = useState('');

  // 권한 체크: 관리자 또는 테스터만 SNS 사용 가능
  const canUseSNS = useMemo(() => hasAdminOrTesterAccess(user), [user]);

  // 복사 핸들러
  const handleCopy = () => {
    try {
      const title = post?.title || '제목 없음';
      const content = convertHtmlToFormattedText(post?.content || '');
      const textToCopy = `제목: ${title}\n\n${content}`;
      navigator.clipboard.writeText(textToCopy).then(() => {
        showNotification('제목과 내용이 클립보드에 복사되었습니다!', 'success');
      }).catch(() => {
        showNotification('복사에 실패했습니다.', 'error');
      });
    } catch (err) {
      console.error('복사 실패:', err);
      showNotification('복사에 실패했습니다.', 'error');
    }
  };

  // SNS 변환은 블로그 발행 URL이 있어야 활성화된다 (SNS 원고에 블로그 링크 필수).
  const hasPublishUrl = Boolean(post?.publishUrl);

  // 🆕 SNS 변환 핸들러 (내장)
  const handleSNSClick = (e) => {
    e.stopPropagation();
    if (!canUseSNS) {
      showNotification('준비 중입니다.', 'info');
      return;
    }
    if (!hasPublishUrl) {
      showNotification('먼저 블로그에 발행한 후 URL을 등록해 주세요.', 'warning');
      return;
    }
    setSnsOpen(true);
  };

  // 🆕 발행 핸들러 (내장) - 발행 URL이 있으면 링크 표시, 없으면 다이얼로그 오픈
  const handlePublishClick = (e) => {
    e.stopPropagation();
    if (post?.publishUrl) {
      window.open(post.publishUrl, '_blank');
    } else {
      setPublishUrl('');
      setPublishDialogOpen(true);
    }
  };

  // 🆕 발행 URL 제출 핸들러
  const handlePublishSubmit = async () => {
    const normalizedUrl = publishUrl.trim();
    if (!normalizedUrl) {
      showNotification('발행 URL을 입력해주세요.', 'error');
      return;
    }
    if (!isNaverBlogUrl(normalizedUrl)) {
      showNotification('네이버 블로그 URL만 입력할 수 있습니다.', 'error');
      return;
    }
    try {
      await callFunctionWithNaverAuth('publishPost', {
        postId: post.id,
        publishUrl: normalizedUrl
      });
      post.publishUrl = normalizedUrl;
      post.status = 'published';
      setPublishDialogOpen(false);
      showNotification('발행 등록이 완료되었습니다.', 'success');
    } catch (err) {
      showNotification('발행 등록에 실패했습니다.', 'error');
    }
  };

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        fullWidth
        maxWidth="md"
        PaperProps={{
          sx: {
            transition: `transform ${transitions.normal} ${transitions.easing.easeOut}, opacity ${transitions.normal} ${transitions.easing.easeOut}`
          }
        }}
      >
        <DialogTitle sx={{ pr: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            생성일 {formatDate(post?.createdAt)} · 수정일 {formatDate(post?.updatedAt)}
          </Typography>
        </DialogTitle>
        <DialogContent dividers>
          <Box
            sx={{
              '& p': { my: 1 },
              '& h1, & h2, & h3': { mt: 2, mb: 1 },
              fontSize: '0.95rem',
              lineHeight: 1.7,
              maxHeight: '70vh',
              overflow: 'auto',
              bgcolor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'grey.50',
              p: 2,
              borderRadius: 1,
              border: '1px solid',
              borderColor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'grey.200',
            }}
          >
            <Typography
              variant="h6"
              sx={{
                fontWeight: 700,
                color: 'text.primary',
                marginBottom: '1rem',
                paddingBottom: '0.5rem',
                borderBottom: '2px solid',
                borderColor: 'primary.main',
                '&, & *': {
                  color: 'text.primary',
                },
              }}
            >
              제목: {post?.title || '제목 없음'}
            </Typography>
            <Box dangerouslySetInnerHTML={{ __html: post?.content || '<p>내용이 없습니다.</p>' }} />
          </Box>
        </DialogContent>
        <Box sx={{ px: 3, py: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
          {/* 🆕 제목 길이 경고 (35자 초과 시) */}
          {post?.title && post.title.length > 35 && (
            <Typography variant="body2" color="error" sx={{ textAlign: 'left', fontWeight: 'bold', mb: 0.5, display: 'flex', alignItems: 'center', gap: 0.5 }}>
              ⚠️ 제목이 깁니다. 35자 내외로 적절히 수정해 주세요.
            </Typography>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'left' }}>
            포스팅 시 이미지는 최소 15장 이상 삽입해 주세요
          </Typography>
        </Box>
        <DialogActions sx={{ gap: 1, p: 2 }}>
          {/* 복사 버튼 */}
          <Button
            onClick={handleCopy}
            variant="contained"
            startIcon={<ContentCopy />}
            sx={{
              bgcolor: theme.palette.primary.main,
              color: 'white',
              '&:hover': { bgcolor: theme.palette.primary.dark }
            }}
          >
            복사
          </Button>

          {/* 발행 버튼 (항상 표시) */}
          <Button
            onClick={handlePublishClick}
            variant="outlined"
            startIcon={<Publish />}
          >
            발행
          </Button>

          {/* SNS 변환 버튼 — 발행 URL이 있어야 활성화 */}
          <Tooltip
            title={!hasPublishUrl ? '먼저 블로그에 발행한 후 URL을 등록해 주세요' : ''}
            arrow
          >
            <span>
              <Button
                onClick={handleSNSClick}
                disabled={!hasPublishUrl}
                variant="contained"
                sx={{
                  bgcolor: '#55207D',
                  '&:hover': { bgcolor: '#6d2b93' }
                }}
                startIcon={<Transform />}
              >
                SNS 변환
              </Button>
            </span>
          </Tooltip>

          <Button onClick={onClose} color="inherit">
            닫기
          </Button>
        </DialogActions>
      </Dialog>

      {/* 🆕 내장형 SNS 변환 모달 */}
      <SNSConversionModal
        open={snsOpen}
        onClose={() => setSnsOpen(false)}
        post={post}
      />

      {/* 🆕 발행 URL 입력 다이얼로그 */}
      <Dialog
        open={publishDialogOpen}
        onClose={() => setPublishDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Publish sx={{ color: theme.palette.primary.main }} />
          원고 발행 등록
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            실제 발행한 네이버 블로그 주소를 입력해주세요.
          </Typography>
          <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
            "{post?.title || '원고 제목'}"
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
            InputProps={{ startAdornment: <Link sx={{ color: 'text.secondary', mr: 1 }} /> }}
            helperText="네이버 블로그 URL만 입력할 수 있습니다."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPublishDialogOpen(false)} color="inherit">취소</Button>
          <Button
            onClick={handlePublishSubmit}
            variant="contained"
            disabled={!isNaverBlogUrl(publishUrl)}
          >
            발행 완료
          </Button>
        </DialogActions>
      </Dialog>

      {/* 복사 알림 스낵바 */}
      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
        autoHideDuration={3000}
      />
    </>
  );
}
