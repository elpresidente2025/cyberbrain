// frontend/src/pages/profile/components/BioPerformanceSection.jsx
// 추가 정보 (정책/공약 등) 카드형 섹션

import React, { useState } from 'react';
import {
    Grid,
    Box,
    Typography,
    TextField,
    IconButton,
    Tooltip,
    Card,
    CardContent,
    CardActions,
    Chip,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    FormControlLabel,
    Checkbox,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
    Button,
} from '@mui/material';
import { Add, Remove } from '@mui/icons-material';
import { BIO_ENTRY_TYPES, BIO_CATEGORIES, VALIDATION_RULES } from '../../../constants/bio-types';

const ONGOING_TYPES = new Set(['policy', 'legislation']);

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

const BioPerformanceSection = ({
    entries,
    bioEntries,
    onEntryChange,
    onAdd,
    onRemove,
    disabled,
    totalEntries
}) => {
    const [pendingUncheckIndex, setPendingUncheckIndex] = useState(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [suppressWarning, setSuppressWarning] = useState(false);

    const handleOngoingChange = (globalIndex, checked) => {
        if (checked) {
            onEntryChange(globalIndex, 'isOngoing', true);
        } else if (suppressWarning) {
            onEntryChange(globalIndex, 'isOngoing', false);
        } else {
            setPendingUncheckIndex(globalIndex);
            setDialogOpen(true);
        }
    };

    const handleDialogConfirm = () => {
        onEntryChange(pendingUncheckIndex, 'isOngoing', false);
        setDialogOpen(false);
        setPendingUncheckIndex(null);
    };

    const handleDialogSuppress = () => {
        onEntryChange(pendingUncheckIndex, 'isOngoing', false);
        setSuppressWarning(true);
        setDialogOpen(false);
        setPendingUncheckIndex(null);
    };

    return (
    <Box sx={{ mb: 'var(--spacing-xl)' }}>
        <Box sx={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', mb: 'var(--spacing-md)'
        }}>
            <Typography variant="h6" sx={{
                color: 'var(--color-primary)',
                fontWeight: 600
            }}>
                📋 추가 정보
            </Typography>
            <Tooltip title="추가 정보 항목 추가">
                <IconButton
                    size="small"
                    onClick={() => onAdd('PERFORMANCE')}
                    disabled={disabled || totalEntries >= VALIDATION_RULES.maxEntries}
                    sx={iconButtonSx}
                >
                    <Add fontSize="small" />
                </IconButton>
            </Tooltip>
        </Box>

        <Grid container spacing={2}>
            {entries.map((entry) => {
                const index = bioEntries.findIndex(e => e.id === entry.id);
                const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === entry.type)
                    || BIO_ENTRY_TYPES.POLICY;

                return (
                    <Grid item xs={12} sm={6} md={4} key={entry.id}>
                        <Card elevation={0} sx={{
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column'
                        }}>
                            <CardContent sx={{ flex: 1 }}>
                                <Box sx={{ mb: 'var(--spacing-md)' }}>
                                    <Chip
                                        label={typeConfig.name}
                                        size="small"
                                        sx={{
                                            bgcolor: typeConfig.color,
                                            color: 'white',
                                            fontWeight: 600
                                        }}
                                    />
                                </Box>

                                <FormControl fullWidth sx={{ mb: 'var(--spacing-md)' }}>
                                    <InputLabel>유형 선택</InputLabel>
                                    <Select
                                        value={entry.type}
                                        label="유형 선택"
                                        onChange={(e) => onEntryChange(index, 'type', e.target.value)}
                                        disabled={disabled}
                                        size="small"
                                    >
                                        {BIO_CATEGORIES.PERFORMANCE.types.map((type) => (
                                            <MenuItem key={type.id} value={type.id}>
                                                {type.name}
                                            </MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>

                                {ONGOING_TYPES.has(entry.type) && (
                                    <FormControlLabel
                                        sx={{ mb: 'var(--spacing-sm)' }}
                                        control={
                                            <Checkbox
                                                size="small"
                                                checked={entry.isOngoing !== false}
                                                onChange={(e) => handleOngoingChange(index, e.target.checked)}
                                                disabled={disabled}
                                            />
                                        }
                                        label={
                                            <Typography variant="caption" sx={{ color: 'var(--color-text-secondary)' }}>
                                                진행 중
                                            </Typography>
                                        }
                                    />
                                )}

                                <TextField
                                    fullWidth
                                    multiline
                                    rows={4}
                                    label="내용"
                                    value={entry.content}
                                    onChange={(e) => onEntryChange(index, 'content', e.target.value)}
                                    disabled={disabled}
                                    placeholder={typeConfig.placeholder}
                                    inputProps={{ maxLength: typeConfig.maxLength }}
                                    size="small"
                                />
                            </CardContent>

                            <CardActions sx={{
                                justifyContent: 'space-between',
                                px: 'var(--spacing-md)',
                                pb: 'var(--spacing-md)'
                            }}>
                                <Typography variant="caption" sx={{ color: 'var(--color-text-secondary)' }}>
                                    {entry.content?.length || 0}/{typeConfig.maxLength}자
                                </Typography>
                                <Tooltip title="이 항목 삭제">
                                    <IconButton
                                        size="small"
                                        onClick={() => onRemove(index)}
                                        disabled={disabled}
                                        sx={iconButtonSx}
                                    >
                                        <Remove />
                                    </IconButton>
                                </Tooltip>
                            </CardActions>
                        </Card>
                    </Grid>
                );
            })}
        </Grid>

        <Dialog open={dialogOpen} onClose={handleDialogConfirm}>
            <DialogTitle>유형 변경 안내</DialogTitle>
            <DialogContent>
                <DialogContentText>
                    입법·집행 완료 시 반드시 유형을 <strong>성과/실적</strong>으로 바꾸어 주세요.
                </DialogContentText>
            </DialogContent>
            <DialogActions>
                <Button onClick={handleDialogSuppress} color="inherit" size="small">
                    이번에 다시 보지 않기
                </Button>
                <Button onClick={handleDialogConfirm} variant="contained" size="small" disableElevation>
                    확인
                </Button>
            </DialogActions>
        </Dialog>
    </Box>
    );
};

export default BioPerformanceSection;
