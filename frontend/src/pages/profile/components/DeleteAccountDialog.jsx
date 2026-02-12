// frontend/src/pages/profile/components/DeleteAccountDialog.jsx
// 회원탈퇴 확인 다이얼로그

import React from 'react';
import {
    Box,
    Typography,
    TextField,
    Button,
    Alert,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions
} from '@mui/material';
import { Warning, DeleteForever } from '@mui/icons-material';
import { LoadingButton } from '../../../components/loading';

const DeleteAccountDialog = ({
    open,
    onClose,
    confirmText,
    onConfirmTextChange,
    onDelete,
    deleting
}) => (
    <Dialog
        open={open}
        onClose={onClose}
        maxWidth="sm"
        fullWidth
        slotProps={{ backdrop: { 'aria-hidden': false } }}
    >
        <DialogTitle>
            <Box display="flex" alignItems="center" gap="var(--spacing-xs)">
                <Warning color="error" />
                <Typography variant="h6" component="span">
                    회원탈퇴 확인
                </Typography>
            </Box>
        </DialogTitle>

        <DialogContent>
            <Alert severity="error" sx={{ mb: 'var(--spacing-lg)' }}>
                <Typography variant="body1" sx={{ fontWeight: 600, mb: 'var(--spacing-xs)' }}>
                    회원탈퇴 시 다음 데이터가 영구적으로 삭제됩니다:
                </Typography>
                <Typography component="div">
                    &bull; 모든 게시물 및 댓글<br />
                    &bull; 프로필 정보 및 Bio 데이터<br />
                    &bull; 선거구 점유 정보<br />
                    &bull; 계정 정보 (복구 불가능)
                </Typography>
            </Alert>

            <Typography variant="body1" sx={{ mb: 'var(--spacing-md)' }}>
                정말로 회원탈퇴를 진행하시겠습니까?
            </Typography>

            <Typography variant="body2" sx={{
                color: 'var(--color-text-secondary)',
                mb: 'var(--spacing-md)'
            }}>
                탈퇴를 확인하려면 아래에 <strong>"회원탈퇴"</strong>를 정확히 입력해주세요.
            </Typography>

            <TextField
                fullWidth
                label="확인 문구 입력"
                value={confirmText}
                onChange={(e) => onConfirmTextChange(e.target.value)}
                placeholder="회원탈퇴"
                disabled={deleting}
                error={confirmText !== '' && confirmText !== '회원탈퇴'}
                helperText={
                    confirmText !== '' && confirmText !== '회원탈퇴'
                        ? '정확히 "회원탈퇴"를 입력해주세요.'
                        : ''
                }
            />
        </DialogContent>

        <DialogActions>
            <Button onClick={onClose} disabled={deleting}>
                취소
            </Button>
            <LoadingButton
                onClick={onDelete}
                color="error"
                variant="contained"
                disabled={confirmText !== '회원탈퇴'}
                loading={deleting}
                loadingText="탈퇴 처리 중..."
                startIcon={<DeleteForever />}
            >
                회원탈퇴
            </LoadingButton>
        </DialogActions>
    </Dialog>
);

export default DeleteAccountDialog;
