// frontend/src/pages/billing/components/AuthDialog.jsx
// 당원 인증서 제출 다이얼로그

import React from 'react';
import {
    Box, Button, Typography, Alert,
    Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { AttachFile } from '@mui/icons-material';

const AuthDialog = ({
    open,
    onClose,
    selectedCertFile,
    onCertFileChange,
    selectedReceiptFile,
    onReceiptFileChange,
    uploading,
    onSubmit,
}) => {
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth slotProps={{ backdrop: { 'aria-hidden': false } }}>
            <DialogTitle>당원 인증서 제출</DialogTitle>
            <DialogContent>
                <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                        1. 당적증명서
                    </Typography>
                    <Button
                        variant="contained"
                        component="label"
                        startIcon={<AttachFile />}
                        fullWidth
                        sx={{
                            mb: 1,
                            bgcolor: 'var(--color-primary)',
                            '&:hover': { bgcolor: 'var(--color-primary-dark)' },
                        }}
                    >
                        당적증명서 업로드
                        <input type="file" hidden accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => onCertFileChange(e.target.files[0])} />
                    </Button>
                    {selectedCertFile && (
                        <Alert severity="success" sx={{ mb: 2 }}>선택된 파일: {selectedCertFile.name}</Alert>
                    )}

                    <Typography variant="subtitle2" sx={{ mb: 1, mt: 2, fontWeight: 700 }}>
                        2. 당비납부 영수증
                    </Typography>
                    <Button
                        variant="contained"
                        component="label"
                        startIcon={<AttachFile />}
                        fullWidth
                        sx={{
                            mb: 1,
                            bgcolor: 'var(--color-primary)',
                            '&:hover': { bgcolor: 'var(--color-primary-dark)' },
                        }}
                    >
                        당비납부 영수증 업로드
                        <input type="file" hidden accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => onReceiptFileChange(e.target.files[0])} />
                    </Button>
                    {selectedReceiptFile && (
                        <Alert severity="success">선택된 파일: {selectedReceiptFile.name}</Alert>
                    )}
                </Box>

                <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)', mt: 2, display: 'block' }}>
                    * 지원 파일 형식: PDF, JPG, PNG<br />
                    * 개인정보는 인증 완료 후 즉시 삭제됩니다
                </Typography>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={uploading}>취소</Button>
                <Button
                    onClick={onSubmit}
                    variant="contained"
                    disabled={uploading || (!selectedCertFile && !selectedReceiptFile)}
                >
                    {uploading ? '처리중...' : '제출'}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default AuthDialog;
