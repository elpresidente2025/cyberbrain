// frontend/src/pages/profile/components/CommitteeEditor.jsx
// 소속 위원회 편집 컴포넌트

import React from 'react';
import {
    Grid,
    Box,
    Typography,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    TextField,
    IconButton,
    Tooltip,
    Paper,
    Stack
} from '@mui/material';
import { Add, Remove } from '@mui/icons-material';

const COMMITTEES = [
    '교육위원회', '보건복지위원회', '국토교통위원회', '기획재정위원회',
    '행정안전위원회', '문화체육관광위원회', '농림축산식품해양수산위원회',
    '산업통상자원중소벤처기업위원회', '환경노동위원회', '정무위원회',
    '법제사법위원회', '국방위원회', '외교통일위원회', '정보위원회',
    '여성가족위원회', '과학기술정보방송통신위원회', '도시계획위원회',
    '경제위원회', '복지위원회',
];

const iconButtonSx = {
    width: 24, height: 24,
    backgroundColor: 'var(--color-primary)',
    color: 'white',
    border: '1px solid var(--color-primary)',
    '&:hover': {
        backgroundColor: 'var(--color-primary-hover)',
        borderColor: 'var(--color-primary-hover)'
    },
    '&:disabled': {
        backgroundColor: 'grey.50',
        borderColor: 'grey.200',
        color: 'grey.400'
    }
};

const CommitteeEditor = ({ committees, customCommittees, onChange, disabled }) => {
    const addCommittee = () => {
        onChange('committees', [...committees, '']);
    };

    const updateCommittee = (index, value) => {
        const updated = [...committees];
        updated[index] = value;
        onChange('committees', updated);
    };

    const removeCommittee = (index) => {
        const filtered = committees.filter((_, i) => i !== index);
        onChange('committees', filtered.length ? filtered : ['']);
    };

    const updateCustomCommittee = (index, value) => {
        const updated = [...(customCommittees || [])];
        updated[index] = value;
        onChange('customCommittees', updated);
    };

    return (
        <Grid item xs={12}>
            <Box sx={{ mb: 'var(--spacing-lg)' }}>
                <Box sx={{
                    display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between', mb: 'var(--spacing-md)'
                }}>
                    <Typography variant="h6" sx={{
                        color: 'var(--color-primary)',
                        fontWeight: 600
                    }}>
                        🏛️ 소속 위원회
                    </Typography>
                    <Tooltip title="위원회 추가">
                        <IconButton
                            size="small"
                            onClick={addCommittee}
                            disabled={disabled || committees.length >= 5}
                            sx={iconButtonSx}
                        >
                            <Add sx={{ fontSize: 14 }} />
                        </IconButton>
                    </Tooltip>
                </Box>

                <Stack spacing={2}>
                    {committees.map((committee, index) => (
                        <Paper key={index} elevation={0} sx={{ p: 'var(--spacing-md)' }}>
                            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--spacing-md)' }}>
                                <Box sx={{ flex: 1 }}>
                                    <FormControl fullWidth>
                                        <InputLabel>위원회 선택</InputLabel>
                                        <Select
                                            value={committee}
                                            label="위원회 선택"
                                            onChange={(e) => updateCommittee(index, e.target.value)}
                                            disabled={disabled}
                                        >
                                            <MenuItem value="">선택 안함</MenuItem>
                                            {COMMITTEES.map(c => (
                                                <MenuItem key={c} value={c}>{c}</MenuItem>
                                            ))}
                                            <MenuItem value="기타">기타 (직접 입력)</MenuItem>
                                        </Select>
                                    </FormControl>

                                    {committee === '기타' && (
                                        <TextField
                                            fullWidth
                                            label="위원회명 직접 입력"
                                            value={customCommittees?.[index] || ''}
                                            onChange={(e) => updateCustomCommittee(index, e.target.value)}
                                            disabled={disabled}
                                            placeholder="예: 특별위원회, 소위원회명 등"
                                            sx={{ mt: 'var(--spacing-xs)' }}
                                        />
                                    )}
                                </Box>

                                <IconButton
                                    size="small"
                                    onClick={() => removeCommittee(index)}
                                    disabled={disabled}
                                    sx={{
                                        color: 'var(--color-error)',
                                        '&:hover': { bgcolor: 'var(--color-error-light)' }
                                    }}
                                >
                                    <Remove />
                                </IconButton>
                            </Box>
                        </Paper>
                    ))}
                </Stack>
            </Box>
        </Grid>
    );
};

export default CommitteeEditor;
