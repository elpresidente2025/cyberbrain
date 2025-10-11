// frontend/src/components/PostViewerModal.jsx
import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  useTheme
} from '@mui/material';
import { ContentCopy, DeleteOutline } from '@mui/icons-material';
import { NotificationSnackbar, useNotification } from './ui';
import { transitions } from '../theme/tokens';

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

export default function PostViewerModal({
  open,
  onClose,
  post,
  onDelete,
  showDeleteButton = true
}) {
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();

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

  const handleDelete = (e) => {
    if (e) e.stopPropagation();
    if (onDelete && post?.id) {
      onDelete(post.id, e);
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
            {/* 제목을 텍스트박스 안에 포함 */}
            <Typography
              variant="h6"
              sx={{
                fontWeight: 700,
                color: '#000000 !important',
                marginBottom: '1rem',
                paddingBottom: '0.5rem',
                borderBottom: '2px solid',
                borderColor: 'primary.main',
                '&, & *': {
                  color: '#000000 !important'
                }
              }}
            >
              제목: {post?.title || '제목 없음'}
            </Typography>
            
            <Box dangerouslySetInnerHTML={{ __html: post?.content || '<p>내용이 없습니다.</p>' }} />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={handleCopy} 
            startIcon={<ContentCopy />}
            sx={{ 
              bgcolor: theme.palette.ui?.header || '#152484',
              color: 'white',
              '&:hover': { bgcolor: '#003A87' }
            }}
          >
            복사
          </Button>
          {showDeleteButton && (
            <Button 
              onClick={handleDelete} 
              color="error" 
              startIcon={<DeleteOutline />}
            >
              삭제
            </Button>
          )}
          <Button 
            onClick={onClose} 
            variant="contained"
            sx={{ 
              bgcolor: theme.palette.ui?.header || '#152484',
              '&:hover': { bgcolor: '#003A87' }
            }}
          >
            닫기
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