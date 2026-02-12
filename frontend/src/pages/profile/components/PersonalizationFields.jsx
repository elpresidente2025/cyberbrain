// frontend/src/pages/profile/components/PersonalizationFields.jsx
// 개인화 정보 입력 필드들 (연령대, 성별, 가족, 경력, 지역연고, 정치경험)

import React from 'react';
import {
    Grid,
    Typography,
    FormControl,
    InputLabel,
    Select,
    MenuItem
} from '@mui/material';
import { AutoAwesome } from '@mui/icons-material';

const FIELDS = [
    {
        name: 'ageDecade', label: '연령대', grid: { xs: 12, sm: 6, md: 2 },
        options: ['20대', '30대', '40대', '50대', '60대', '70대 이상'],
    },
    {
        name: 'ageDetail', label: '세부 연령', grid: { xs: 12, sm: 6, md: 2 },
        options: ['초반', '중반', '후반'],
        disabledWhen: (profile) => !profile.ageDecade,
    },
    {
        name: 'gender', label: '성별', grid: { xs: 12, sm: 6, md: 4 },
        options: ['남성', '여성'],
    },
    {
        name: 'familyStatus', label: '가족 상황', grid: { xs: 12, sm: 6, md: 4 },
        options: ['미혼', '기혼(자녀 있음)', '기혼(자녀 없음)', '한부모'],
    },
    {
        name: 'backgroundCareer', label: '주요 배경', grid: { xs: 12, sm: 6, md: 4 },
        options: ['교육자', '사업가', '공무원', '시민운동가', '법조인', '의료인', '기타'],
    },
    {
        name: 'localConnection', label: '지역 연고', grid: { xs: 12, sm: 6, md: 4 },
        options: ['토박이', '오래 거주 (10년 이상)', '이주민', '귀향'],
    },
    {
        name: 'politicalExperience', label: '정치 경험', grid: { xs: 12, sm: 6, md: 4 },
        options: ['초선', '재선', '3선 이상', '정치 신인'],
    },
];

const PersonalizationFields = ({ profile, onChange, disabled }) => (
    <>
        <Grid item xs={12}>
            <Typography variant="h6" sx={{
                display: 'flex', alignItems: 'center',
                mb: 'var(--spacing-md)', mt: 'var(--spacing-lg)'
            }}>
                <AutoAwesome sx={{ mr: 'var(--spacing-xs)', color: 'var(--color-primary)' }} />
                개인화 정보 (선택사항)
            </Typography>
            <Typography variant="body2" sx={{
                color: 'var(--color-text-secondary)',
                mb: 'var(--spacing-lg)'
            }}>
                더 개인화되고 진정성 있는 원고 생성을 위한 선택 정보입니다. 입력하지 않아도 서비스 이용에 문제없습니다.
            </Typography>
        </Grid>

        {FIELDS.map(({ name, label, grid, options, disabledWhen }) => (
            <Grid item key={name} {...grid}>
                <FormControl fullWidth>
                    <InputLabel>{label}</InputLabel>
                    <Select
                        name={name}
                        value={profile[name] || ''}
                        label={label}
                        onChange={(e) => onChange(name, e.target.value)}
                        disabled={disabled || (disabledWhen && disabledWhen(profile))}
                    >
                        <MenuItem value="">선택 안함</MenuItem>
                        {options.map(opt => (
                            <MenuItem key={opt} value={opt}>{opt}</MenuItem>
                        ))}
                    </Select>
                </FormControl>
            </Grid>
        ))}
    </>
);

export default PersonalizationFields;
