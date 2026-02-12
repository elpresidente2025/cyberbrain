// frontend/src/pages/dashboard/components/RecentPostsCard.jsx
// 최근 생성한 글 목록 카드

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
import { Article } from '@mui/icons-material';
import EmptyState from '../../../components/ui/feedback/EmptyState';
import { CATEGORIES } from '../../../constants/formConstants';

/**
 * 최근 생성한 글 목록 카드
 */
const RecentPostsCard = ({
    posts = [],
    maxItems = 5,
    onViewPost,
    onCopyPost,
    onDeletePost,
    onSNSConvert,
    onViewAll
}) => {
    // 유틸리티 함수들
    const formatDate = (iso) => {
        if (!iso) return '';
        const date = new Date(iso);
        const now = new Date();
        const diffTime = Math.abs(now - date);
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return '오늘';
        } else if (diffDays === 1) {
            return '어제';
        } else if (diffDays < 7) {
            return `${diffDays}일 전`;
        } else {
            return date.toLocaleDateString('ko-KR', {
                month: 'short',
                day: 'numeric'
            });
        }
    };

    const stripHtml = (html = '') => {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        return doc.body.textContent || '';
    };

    const getCategoryLabel = (categoryValue) => {
        const category = Object.values(CATEGORIES).flat().find(c => c.value === categoryValue);
        return category?.label || categoryValue || '미분류';
    };

    const displayedPosts = posts.slice(0, maxItems);
    const hasMore = posts.length > maxItems;

    if (posts.length === 0) {
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
                        <Article sx={{ mr: 1, color: 'var(--color-primary)' }} />
                        최근 생성한 글
                    </Typography>
                </Box>
                <EmptyState
                    icon={Article}
                    message="아직 생성한 글이 없습니다"
                    py={4}
                />
            </Paper>
        );
    }

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
            <Box sx={{ p: 2, borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography
                    variant="h6"
                    sx={{
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        color: 'var(--color-text-primary)'
                    }}
                >
                    <Article sx={{ mr: 1, color: 'var(--color-primary)' }} />
                    최근 생성한 글
                </Typography>
                {onViewAll && (
                    <Button
                        size="small"
                        sx={{ color: 'var(--color-primary)' }}
                        onClick={onViewAll}
                    >
                        전체 보기
                    </Button>
                )}
            </Box>

            {/* 글 목록 */}
            <List sx={{ p: 0 }}>
                {displayedPosts.map((post, index) => (
                    <React.Fragment key={post.id || index}>
                        <ListItem
                            sx={{
                                px: 2,
                                py: 1.5,
                                cursor: 'pointer',
                                transition: 'all var(--transition-fast)',
                                '&:hover': {
                                    bgcolor: 'var(--color-primary-lighter)'
                                }
                            }}
                            onClick={() => onViewPost?.(post.id)}
                        >
                            <ListItemText
                                primary={
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                        <Typography
                                            variant="subtitle2"
                                            sx={{
                                                fontWeight: 600,
                                                color: 'var(--color-text-primary)',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                                flex: 1
                                            }}
                                        >
                                            {post.title || '제목 없음'}
                                        </Typography>
                                        <Chip
                                            label={getCategoryLabel(post.category)}
                                            size="small"
                                            sx={{
                                                height: 20,
                                                fontSize: '0.7rem',
                                                bgcolor: 'var(--color-primary-light)',
                                                color: 'var(--color-primary)'
                                            }}
                                        />
                                    </Box>
                                }
                                secondary={
                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <Typography
                                            variant="body2"
                                            sx={{
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                                color: 'var(--color-text-secondary)',
                                                maxWidth: '60%'
                                            }}
                                        >
                                            {stripHtml(post.content).substring(0, 50)}...
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)' }}>
                                            {formatDate(post.createdAt)}
                                        </Typography>
                                    </Box>
                                }
                            />

                        </ListItem>
                        {index < displayedPosts.length - 1 && <Divider />}
                    </React.Fragment>
                ))}
            </List>

            {/* 더보기 */}
            {hasMore && (
                <Box sx={{ p: 2, textAlign: 'center', borderTop: '1px solid var(--color-border)' }}>
                    <Button
                        variant="text"
                        size="small"
                        onClick={onViewAll}
                        sx={{ color: 'var(--color-primary)' }}
                    >
                        더 보기 ({posts.length - maxItems}개 더)
                    </Button>
                </Box>
            )}
        </Paper>
    );
};

export default RecentPostsCard;
