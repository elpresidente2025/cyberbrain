// frontend/src/pages/profile/components/BioPersonalSection.jsx
// 자기소개 및 출마선언문 섹션

import React from 'react';
import {
    Box,
    Typography,
    TextField,
    IconButton,
    Tooltip,
    Paper,
    Stack
} from '@mui/material';
import { Add, Remove } from '@mui/icons-material';
import { BIO_ENTRY_TYPES, VALIDATION_RULES } from '../../../constants/bio-types';

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

const BioPersonalSection = ({
    entries,
    bioEntries,
    onEntryChange,
    onAdd,
    onRemove,
    disabled,
    totalEntries
}) => (
    <Box sx={{ mb: 'var(--spacing-xl)' }} data-bio-section="personal">
        <Box sx={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', mb: 'var(--spacing-md)'
        }}>
            <Typography variant="h6" sx={{
                color: 'var(--color-info)',
                fontWeight: 600
            }}>
                👤 자기소개 및 출마선언문
            </Typography>
            <Tooltip title="자기소개 및 출마선언문 항목 추가">
                <IconButton
                    size="small"
                    onClick={() => onAdd('PERSONAL')}
                    disabled={disabled || totalEntries >= VALIDATION_RULES.maxEntries}
                    sx={iconButtonSx}
                >
                    <Add fontSize="small" />
                </IconButton>
            </Tooltip>
        </Box>

        <Stack spacing={2}>
            {entries.map((entry) => {
                const index = bioEntries.findIndex(e => e.id === entry.id);
                const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === entry.type)
                    || BIO_ENTRY_TYPES.SELF_INTRODUCTION;
                const isRequired = entry.type === 'self_introduction';

                return (
                    <Paper key={entry.id} elevation={0} sx={{ p: 'var(--spacing-md)' }}>
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--spacing-md)' }}>
                            <Box sx={{ flex: 1 }}>
                                <TextField
                                    required={isRequired}
                                    fullWidth
                                    multiline
                                    rows={isRequired ? 4 : 5}
                                    label={isRequired ? '자기소개 및 출마선언문 *필수' : '내용'}
                                    value={entry.content}
                                    onChange={(e) => onEntryChange(index, 'content', e.target.value)}
                                    disabled={disabled}
                                    placeholder={isRequired
                                        ? '본인의 정치 철학, 가치관, 지역에 대한 애정 등을 자유롭게 작성해주세요.'
                                        : '연설문, 기고문, 인터뷰 등을 자유롭게 올려 주세요.'}
                                    inputProps={{ maxLength: typeConfig.maxLength }}
                                    helperText={`${entry.content?.length || 0}/${typeConfig.maxLength}자`}
                                />
                            </Box>

                            {!isRequired && (
                                <Tooltip title="이 항목 삭제">
                                    <IconButton
                                        size="small"
                                        onClick={() => onRemove(index)}
                                        disabled={disabled}
                                        sx={{ mt: 'var(--spacing-xs)', ...iconButtonSx }}
                                    >
                                        <Remove />
                                    </IconButton>
                                </Tooltip>
                            )}
                        </Box>
                    </Paper>
                );
            })}
        </Stack>
    </Box>
);

export default BioPersonalSection;
