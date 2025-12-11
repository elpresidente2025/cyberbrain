import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Grid,
  Card,
  CardContent
} from '@mui/material';

function SampleSpeechModal({ open, onClose }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      aria-labelledby="sample-speech-title"
      aria-describedby="sample-speech-desc"
      PaperProps={{
        sx: {
          backgroundColor: 'rgba(0,0,0,0.9)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: 0.5
        }
      }}
    >
      <DialogTitle id="sample-speech-title" sx={{ fontWeight: 800, textAlign: 'center' }} style={{ color: '#fff' }}>
        원고 작성 품질 비교
      </DialogTitle>
      <DialogContent dividers id="sample-speech-desc" sx={{ position: 'relative', color: '#fff', p: 4 }}>
        <Grid container spacing={4}>
          {/* Before */}
          <Grid item xs={12} md={6}>
            <Card sx={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              border: '2px solid rgba(255,255,255,0.1)',
              borderRadius: 0.5
            }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }} style={{ color: '#fff' }}>
                  Before: 직접 작성
                </Typography>
                <Box
                  sx={{
                    minHeight: 300,
                    backgroundColor: 'rgba(255,255,255,0.02)',
                    border: '2px dashed rgba(255,255,255,0.2)',
                    borderRadius: 0.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    p: 3
                  }}
                >
                  <Typography variant="body2" sx={{
                    color: 'rgba(255,255,255,0.5)',
                    textAlign: 'center',
                    fontStyle: 'italic'
                  }}>
                    스크린샷 추가 예정<br />
                    (기존 방식의 원고 예시)
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* After */}
          <Grid item xs={12} md={6}>
            <Card sx={{
              backgroundColor: 'rgba(79, 195, 247, 0.05)',
              border: '2px solid rgba(79, 195, 247, 0.3)',
              borderRadius: 0.5
            }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }} style={{ color: '#fff' }}>
                  After: AI 생성 + 검토
                </Typography>
                <Box
                  sx={{
                    minHeight: 300,
                    backgroundColor: 'rgba(79, 195, 247, 0.05)',
                    border: '2px dashed rgba(79, 195, 247, 0.3)',
                    borderRadius: 0.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    p: 3
                  }}
                >
                  <Typography variant="body2" sx={{
                    color: 'rgba(79, 195, 247, 0.7)',
                    textAlign: 'center',
                    fontStyle: 'italic'
                  }}>
                    스크린샷 추가 예정<br />
                    (AI 생성 + 검토 완료 원고 예시)
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
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
