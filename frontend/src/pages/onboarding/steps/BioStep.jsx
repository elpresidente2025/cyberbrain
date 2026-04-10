import React, { useState } from 'react';
import {
  Box,
  Typography,
  TextField,
  LinearProgress,
  Collapse,
  Button,
  Stack,
} from '@mui/material';
import { ExpandMore, ExpandLess, Lightbulb } from '@mui/icons-material';
import { MIN_BIO_LENGTH } from '../hooks/useOnboardingFlow';

const HINT_SECTIONS = [
  { title: '정치 철학', description: '정치 활동의 근간이 되는 가치관과 신념을 적어주세요.' },
  { title: '핵심 공약', description: '유권자에게 약속하는 주요 정책이나 실천 과제를 정리해주세요.' },
  { title: '주요 경력', description: '의정·공공 활동, 주요 직책, 수상 경력 등을 간결하게 적어주세요.' },
  { title: '지역구 비전', description: '활동 지역에서 달성하고자 하는 구체적인 목표를 서술해주세요.' },
  { title: '개인적 신념', description: '삶의 가치관과 시민들에게 전하고 싶은 메시지를 담아주세요.' },
];

const RECOMMENDED_LENGTH = 200;

const BioStep = ({ value, onChange }) => {
  const [hintOpen, setHintOpen] = useState(false);
  const text = typeof value === 'string' ? value : '';
  const length = text.trim().length;

  const progressValue = Math.min(100, Math.round((length / RECOMMENDED_LENGTH) * 100));
  const progressColor = length < MIN_BIO_LENGTH
    ? 'error'
    : length < RECOMMENDED_LENGTH
      ? 'warning'
      : 'success';

  const statusMessage = length < MIN_BIO_LENGTH
    ? `최소 ${MIN_BIO_LENGTH}자 이상 필요합니다. (현재 ${length}자)`
    : length < RECOMMENDED_LENGTH
      ? `양호합니다. 더 구체적으로 작성하면 원고 품질이 향상됩니다. (${length}자)`
      : `충분합니다. (${length}자)`;

  return (
    <Box>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
        자기소개를 작성해주세요
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        입력하신 내용을 바탕으로 맞춤 원고를 생성합니다.
      </Typography>

      <Button
        startIcon={<Lightbulb />}
        endIcon={hintOpen ? <ExpandLess /> : <ExpandMore />}
        onClick={() => setHintOpen((v) => !v)}
        size="small"
        sx={{ mb: 2 }}
      >
        작성 가이드 보기
      </Button>

      <Collapse in={hintOpen}>
        <Box
          sx={{
            p: 2,
            mb: 2,
            bgcolor: 'action.hover',
            borderRadius: 2,
          }}
        >
          <Stack spacing={1.5}>
            {HINT_SECTIONS.map((hint) => (
              <Box key={hint.title}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                  {hint.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {hint.description}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      </Collapse>

      <TextField
        fullWidth
        multiline
        rows={10}
        value={text}
        onChange={(e) => onChange(e.target.value)}
        placeholder="자신의 정치 철학, 핵심 공약, 주요 경력 등을 자유롭게 작성해주세요. (최소 50자)"
        sx={{ mb: 2 }}
      />

      <Box sx={{ mb: 1 }}>
        <LinearProgress
          variant="determinate"
          value={progressValue}
          color={progressColor}
          sx={{ height: 8, borderRadius: 4 }}
        />
      </Box>
      <Typography variant="caption" color={`${progressColor}.main`}>
        {statusMessage}
      </Typography>
    </Box>
  );
};

export default BioStep;
