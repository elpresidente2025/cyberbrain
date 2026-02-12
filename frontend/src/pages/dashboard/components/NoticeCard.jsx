// frontend/src/pages/dashboard/components/NoticeCard.jsx
// 공지사항 카드 (모바일/데스크톱 통합)

import React from 'react';
import {
    Box,
    Paper,
    Typography,
    List,
    ListItem,
    ListItemText,
    Divider,
    Chip,
    Button
} from '@mui/material';
import { Notifications } from '@mui/icons-material';
import EmptyState from '../../../components/ui/feedback/EmptyState';

/**
 * 공지사항 카드
 * @param {Array} notices - 공지사항 배열
 * @param {number} maxItems - 최대 표시 개수 (기본: 5)
 */
const NoticeCard = ({ notices = [], maxItems = 5 }) => {
    if (notices.length === 0) {
        return (
            <Paper
                elevation={0}
                sx={{
                    bgcolor: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-lg)',
                    overflow: 'hidden'
                }}
            >
                <Box sx={{ p: 2, borderBottom: '1px solid var(--color-border)' }}>
                    <Typography
                        variant="h6"
                        sx={{
                            fontWeight: 600,
                            display: 'flex',
                            alignItems: 'center',
                            color: 'var(--color-text-primary)'
                        }}
                    >
                        <Notifications sx={{ mr: 1, color: 'var(--color-primary)' }} />
                        공지사항
                    </Typography>
                </Box>
                <EmptyState
                    icon={Notifications}
                    message="현재 공지사항이 없습니다"
                    py={3}
                />
            </Paper>
        );
    }

    const displayedNotices = notices.slice(0, maxItems);
    const hasMore = notices.length > maxItems;

    return (
        <Paper
            elevation={0}
            sx={{
                bgcolor: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-lg)',
                overflow: 'hidden'
            }}
        >
            {/* 헤더 */}
            <Box sx={{ p: 2, borderBottom: '1px solid var(--color-border)' }}>
                <Typography
                    variant="h6"
                    sx={{
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        color: 'var(--color-text-primary)'
                    }}
                >
                    <Notifications sx={{ mr: 1, color: 'var(--color-primary)' }} />
                    공지사항
                </Typography>
            </Box>

            {/* 공지 목록 */}
            <List sx={{ p: 0 }}>
                {displayedNotices.map((notice, index) => (
                    <React.Fragment key={notice.id || index}>
                        <ListItem sx={{ alignItems: 'flex-start', px: 2, py: 1.5 }}>
                            <ListItemText
                                primary={
                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            <Typography
                                                variant="subtitle2"
                                                sx={{ fontWeight: 600, color: 'var(--color-text-primary)' }}
                                            >
                                                {notice.title || '제목 없음'}
                                            </Typography>
                                            {notice.priority === 'high' && (
                                                <Chip
                                                    label="중요"
                                                    size="small"
                                                    sx={{
                                                        height: 20,
                                                        fontSize: '0.7rem',
                                                        bgcolor: 'var(--color-error-light)',
                                                        color: 'var(--color-error)'
                                                    }}
                                                />
                                            )}
                                        </Box>
                                        <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)' }}>
                                            {notice.createdAt ? new Date(notice.createdAt).toLocaleDateString('ko-KR', {
                                                month: 'short',
                                                day: 'numeric'
                                            }) : ''}
                                        </Typography>
                                    </Box>
                                }
                                secondary={
                                    <Typography
                                        variant="body2"
                                        sx={{
                                            mt: 0.5,
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            display: '-webkit-box',
                                            WebkitLineClamp: 2,
                                            WebkitBoxOrient: 'vertical',
                                            color: 'var(--color-text-secondary)'
                                        }}
                                    >
                                        {notice.content || '내용 없음'}
                                    </Typography>
                                }
                            />
                        </ListItem>
                        {index < displayedNotices.length - 1 && <Divider />}
                    </React.Fragment>
                ))}
            </List>

            {/* 더보기 버튼 */}
            {hasMore && (
                <Box sx={{ p: 2, textAlign: 'center', borderTop: '1px solid var(--color-border)' }}>
                    <Button
                        variant="text"
                        size="small"
                        sx={{ color: 'var(--color-primary)' }}
                    >
                        더 보기 ({notices.length - maxItems}개 더)
                    </Button>
                </Box>
            )}
        </Paper>
    );
};

export default NoticeCard;
