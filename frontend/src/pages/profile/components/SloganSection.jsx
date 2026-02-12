// frontend/src/pages/profile/components/SloganSection.jsx
// 슬로건 입력 섹션

import React from 'react';
import {
    Box,
    Typography,
    TextField,
    Paper,
    FormControlLabel,
    Checkbox
} from '@mui/material';

const SloganSection = ({ slogan, sloganEnabled, onChange, disabled }) => (
    <Box sx={{ mb: 'var(--spacing-xl)' }}>
        <Typography variant="h6" sx={{
            color: 'var(--color-warning)',
            fontWeight: 600,
            mb: 'var(--spacing-md)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--spacing-xs)'
        }}>
            🎯 슬로건 (선택)
        </Typography>

        <Paper elevation={0} sx={{ p: 'var(--spacing-md)' }}>
            <FormControlLabel
                control={
                    <Checkbox
                        checked={sloganEnabled}
                        onChange={(e) => onChange('sloganEnabled', e.target.checked)}
                        disabled={disabled}
                        sx={{
                            color: 'var(--color-primary)',
                            '&.Mui-checked': { color: 'var(--color-primary)' }
                        }}
                    />
                }
                label="원고 끝에 슬로건 자동 삽입"
                sx={{ mb: 'var(--spacing-md)' }}
            />

            <TextField
                fullWidth
                multiline
                rows={3}
                label="슬로건"
                value={slogan}
                onChange={(e) => onChange('slogan', e.target.value)}
                disabled={disabled || !sloganEnabled}
                placeholder={`예시:\n부산의 준비된 신상품\n부산경제는 홍길동`}
                inputProps={{ maxLength: 200 }}
                helperText={`${slogan?.length || 0}/200자 · 원고 마지막에 "감사합니다" 앞에 삽입됩니다`}
                FormHelperTextProps={{ sx: { color: 'var(--color-text-secondary)' } }}
            />
        </Paper>
    </Box>
);

export default SloganSection;
