import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Chip,
  Box
} from '@mui/material';
import { SAMPLE_SPEECH } from '../data/samples';

function SampleSpeechModal({ open, onClose }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      aria-labelledby="sample-speech-title"
      aria-describedby="sample-speech-desc"
      PaperProps={{
        sx: {
          backgroundColor: 'rgba(0,0,0,0.9)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: 2
        }
      }}
    >
      <DialogTitle id="sample-speech-title" sx={{ fontWeight: 800, color: '#fff' }}>
        {SAMPLE_SPEECH.title}
      </DialogTitle>
      <DialogContent dividers id="sample-speech-desc" sx={{ position: 'relative', color: '#fff' }}>
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Chip size="small" label="데모 샘플" sx={{ backgroundColor: 'rgba(255,255,255,0.1)', color: '#fff' }} />
          <Chip size="small" label={SAMPLE_SPEECH.source} sx={{ backgroundColor: 'rgba(0,212,255,0.2)', color: '#00d4ff' }} />
          <Chip size="small" label="전문 비공개" sx={{ backgroundColor: 'rgba(255,255,255,0.1)', color: '#fff' }} />
        </Stack>
        <Typography variant="caption" sx={{ opacity: 0.7, display: 'block', mb: 2, color: '#fff' }}>
          {SAMPLE_SPEECH.disclaimer}
        </Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.7, color: '#fff' }}>
          {SAMPLE_SPEECH.body}
        </Typography>
        <Box sx={{
          position: 'absolute',
          right: 12,
          bottom: 12,
          px: 1,
          py: 0.25,
          border: '1px solid rgba(255,255,255,0.25)',
          borderRadius: 1,
          fontSize: 12,
          opacity: 0.8,
          color: '#fff'
        }}>DEMO</Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} variant="contained" sx={{ backgroundColor: '#00d4ff', color: '#041120' }}>
          닫기
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default SampleSpeechModal;
