// frontend/src/pages/billing/components/CancelDialog.jsx
// 구독 해지 확인 다이얼로그

import React from 'react';
import {
    Box, Button, Typography, Alert, Divider,
    Dialog, DialogTitle, DialogContent, DialogActions,
    List, ListItem, ListItemIcon, ListItemText,
} from '@mui/material';
import { Warning, CheckCircle } from '@mui/icons-material';

const REFUND_ITEMS = [
    '구매일로부터 7일 이내: 전액 환불 가능',
    '원고 생성 이용 후: 미사용 횟수만큼 일할 계산하여 환불',
    '환불 요청 시 7영업일 이내 처리 완료',
];

const CancelDialog = ({ open, onClose, onConfirm }) => {
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth slotProps={{ backdrop: { 'aria-hidden': false } }}>
            <DialogTitle>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Warning sx={{ color: 'var(--color-warning)' }} />
                    구독 해지
                </Box>
            </DialogTitle>
            <DialogContent>
                <Box sx={{ mt: 2 }}>
                    <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 700 }}>
                        환불 정책
                    </Typography>
                    <List dense>
                        {REFUND_ITEMS.map((text) => (
                            <ListItem key={text}>
                                <ListItemIcon sx={{ minWidth: 32 }}>
                                    <CheckCircle sx={{ color: 'var(--color-primary)', fontSize: '1.2rem' }} />
                                </ListItemIcon>
                                <ListItemText primary={text} primaryTypographyProps={{ variant: 'body2' }} />
                            </ListItem>
                        ))}
                    </List>

                    <Divider sx={{ my: 2 }} />

                    <Alert severity="warning" sx={{ mb: 2 }}>
                        <Typography variant="body2">
                            구독을 해지하시면 즉시 서비스 이용이 중단됩니다.
                        </Typography>
                    </Alert>

                    <Typography variant="h6" sx={{ textAlign: 'center', fontWeight: 700, mt: 3 }}>
                        구독을 해지하시겠습니까?
                    </Typography>
                </Box>
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 3 }}>
                <Button
                    onClick={onClose}
                    variant="contained"
                    fullWidth
                    sx={{
                        bgcolor: 'var(--color-primary)',
                        '&:hover': { bgcolor: 'var(--color-primary-dark)' },
                    }}
                >
                    아니오
                </Button>
                <Button onClick={onConfirm} variant="contained" color="error" fullWidth>
                    예, 해지합니다
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default CancelDialog;
