// frontend/src/pages/profile/components/DonationSection.jsx
// 후원 안내 입력 섹션

import React from 'react';
import {
    Box,
    Typography,
    TextField,
    Paper,
    FormControlLabel,
    Checkbox
} from '@mui/material';

const DonationSection = ({ donationInfo, donationEnabled, onChange, disabled }) => (
    <Box sx={{ mb: 'var(--spacing-xl)' }}>
        <Typography variant="h6" sx={{
            color: 'var(--color-success)',
            fontWeight: 600,
            mb: 'var(--spacing-md)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--spacing-xs)'
        }}>
            💰 후원 안내 (선택)
        </Typography>

        <Paper elevation={0} sx={{ p: 'var(--spacing-md)' }}>
            <FormControlLabel
                control={
                    <Checkbox
                        checked={donationEnabled}
                        onChange={(e) => onChange('donationEnabled', e.target.checked)}
                        disabled={disabled}
                        sx={{
                            color: 'var(--color-primary)',
                            '&.Mui-checked': { color: 'var(--color-primary)' }
                        }}
                    />
                }
                label="원고 끝에 후원 안내 자동 삽입"
                sx={{ mb: 'var(--spacing-md)' }}
            />

            <TextField
                fullWidth
                multiline
                rows={4}
                label="후원 안내"
                value={donationInfo}
                onChange={(e) => onChange('donationInfo', e.target.value)}
                disabled={disabled || !donationEnabled}
                placeholder={`예시:\n후원계좌: 국민은행 000-000000-00-000 (예금주: 홍길동)\n후원링크: https://example.com/donate`}
                inputProps={{ maxLength: 500 }}
                helperText={`${donationInfo?.length || 0}/500자 · 슬로건 위에 삽입됩니다`}
                FormHelperTextProps={{ sx: { color: 'var(--color-text-secondary)' } }}
            />
        </Paper>
    </Box>
);

export default DonationSection;
