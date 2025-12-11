// frontend/src/components/admin/StatusUpdateModal.jsx
import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Alert,
  Chip,
  Grid,
  IconButton,
  CircularProgress,
  Divider,
  FormControlLabel,
  Switch,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme
} from '@mui/material';
import { 
  Close, 
  Api, 
  CheckCircle, 
  Warning, 
  Error as ErrorIcon,
  Refresh,
  ExpandMore,
  Schedule,
  ContactSupport
} from '@mui/icons-material';
import { updateSystemStatus, getSystemStatus } from '../../services/firebaseService';

function StatusUpdateModal({ open, onClose }) {
  const theme = useTheme();
  const [currentStatus, setCurrentStatus] = useState(null);
  const [newStatus, setNewStatus] = useState('');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  
  // 점검 중 페이지 관련 필드들
  const [maintenanceTitle, setMaintenanceTitle] = useState('시스템 점검 안내');
  const [maintenanceMessage, setMaintenanceMessage] = useState('');
  const [estimatedEndTime, setEstimatedEndTime] = useState('');
  const [contactInfo, setContactInfo] = useState('문의사항이 있으시면 고객센터로 연락해 주세요.');
  const [allowAdminAccess, setAllowAdminAccess] = useState(true);

  // 현재 상태 조회
  const fetchCurrentStatus = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await getSystemStatus();
      setCurrentStatus(result);
    } catch (err) {
      console.error('상태 조회 실패:', err);
      setError('현재 상태를 조회하는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchCurrentStatus();
      setNewStatus('');
      setReason('');
      setSuccess(false);
    }
  }, [open]);

  const handleStatusUpdate = async () => {
    if (!newStatus) {
      setError('새로운 상태를 선택해주세요.');
      return;
    }

    if (!reason.trim()) {
      setError('변경 사유를 입력해주세요.');
      return;
    }

    setUpdating(true);
    setError(null);

    try {
      const statusData = {
        status: newStatus,
        reason: reason.trim(),
        timestamp: new Date().toISOString()
      };

      // 점검 중인 경우 추가 정보 포함
      if (newStatus === 'maintenance') {
        statusData.maintenanceInfo = {
          title: maintenanceTitle.trim(),
          message: maintenanceMessage.trim(),
          estimatedEndTime: estimatedEndTime,
          contactInfo: contactInfo.trim(),
          allowAdminAccess: allowAdminAccess
        };
      }

      const result = await updateSystemStatus(statusData);

      if (!result.success) {
        throw new Error(result.message || '상태 업데이트 실패');
      }

      setSuccess(true);
      setCurrentStatus(prev => ({
        ...prev,
        status: newStatus,
        maintenanceInfo: statusData.maintenanceInfo || null,
        timestamp: new Date().toISOString()
      }));

      // ✅ sessionStorage 캐시도 즉시 업데이트 (App.jsx에서 캐시 사용)
      sessionStorage.setItem('systemStatusCache', JSON.stringify({
        timestamp: Date.now(),
        status: newStatus,
        maintenanceInfo: statusData.maintenanceInfo || null
      }));

      // 성공 후 잠시 대기한 뒤 모달 닫기
      setTimeout(() => {
        handleClose();
        window.location.reload(); // 전체 페이지 새로고침으로 상태 반영
      }, 1500);

    } catch (err) {
      console.error('상태 업데이트 실패:', err);
      setError('상태 업데이트에 실패했습니다: ' + err.message);
    } finally {
      setUpdating(false);
    }
  };

  const handleClose = () => {
    setNewStatus('');
    setReason('');
    setError(null);
    setSuccess(false);
    setCurrentStatus(null);
    onClose();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return 'success';
      case 'inactive': return 'error';
      case 'maintenance': return 'warning';
      default: return 'default';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'active': return '정상 운영';
      case 'inactive': return '서비스 중단';
      case 'maintenance': return '점검 중';
      default: return '알 수 없음';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'active': return <CheckCircle />;
      case 'inactive': return <ErrorIcon />;
      case 'maintenance': return <Warning />;
      default: return <Api />;
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Api sx={{ color: theme.palette.ui?.header || '#152484' }} />
            <Typography variant="h6" sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}>
              시스템 상태 관리
            </Typography>
          </Box>
          <IconButton onClick={handleClose}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* 현재 상태 표시 */}
            <Box sx={{ mb: 3, p: 2, backgroundColor: '#f5f5f5', borderRadius: 0.5 }}>
              <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
                현재 시스템 상태
              </Typography>
              
              {currentStatus?.status ? (
                <Grid container spacing={2} alignItems="center">
                  <Grid item>
                    <Chip
                      icon={getStatusIcon(currentStatus.status)}
                      label={getStatusText(currentStatus.status)}
                      color={getStatusColor(currentStatus.status)}
                    />
                  </Grid>
                  <Grid item>
                    <Button
                      size="small"
                      startIcon={<Refresh />}
                      onClick={fetchCurrentStatus}
                      sx={{ color: theme.palette.ui?.header || '#152484' }}
                    >
                      새로고침
                    </Button>
                  </Grid>
                </Grid>
              ) : (
                <Alert severity="warning">
                  현재 상태를 확인할 수 없습니다.
                </Alert>
              )}

              {currentStatus?.timestamp && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                  마지막 조회: {new Date(currentStatus.timestamp).toLocaleString()}
                </Typography>
              )}
            </Box>

            <Divider sx={{ mb: 3 }} />

            {/* 상태 변경 폼 */}
            <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
              상태 변경
            </Typography>

            <FormControl fullWidth sx={{ mb: 2 }}>
              <InputLabel>새로운 상태</InputLabel>
              <Select
                value={newStatus}
                label="새로운 상태"
                onChange={(e) => setNewStatus(e.target.value)}
              >
                <MenuItem value="active">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <CheckCircle color="success" />
                    정상 운영
                  </Box>
                </MenuItem>
                <MenuItem value="maintenance">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Warning color="warning" />
                    점검 중
                  </Box>
                </MenuItem>
                <MenuItem value="inactive">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <ErrorIcon color="error" />
                    서비스 중단
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>

            <TextField
              fullWidth
              multiline
              rows={3}
              label="변경 사유"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="상태 변경 이유를 입력해주세요..."
              sx={{ mb: 2 }}
            />

            {/* 점검 중 세부 설정 */}
            {newStatus === 'maintenance' && (
              <Accordion sx={{ mb: 2 }}>
                <AccordionSummary
                  expandIcon={<ExpandMore />}
                  aria-controls="maintenance-settings-content"
                  id="maintenance-settings-header"
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Warning color="warning" />
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                      점검 중 페이지 설정
                    </Typography>
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Grid container spacing={2}>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="점검 안내 제목"
                        value={maintenanceTitle}
                        onChange={(e) => setMaintenanceTitle(e.target.value)}
                        placeholder="시스템 점검 안내"
                      />
                    </Grid>
                    
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        multiline
                        rows={4}
                        label="점검 안내 메시지"
                        value={maintenanceMessage}
                        onChange={(e) => setMaintenanceMessage(e.target.value)}
                        placeholder="더 나은 서비스 제공을 위해 시스템 점검을 진행하고 있습니다..."
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        type="datetime-local"
                        label="예상 복구 시간"
                        value={estimatedEndTime}
                        onChange={(e) => setEstimatedEndTime(e.target.value)}
                        InputLabelProps={{
                          shrink: true,
                        }}
                        InputProps={{
                          startAdornment: <Schedule sx={{ mr: 1, color: 'action.active' }} />
                        }}
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={allowAdminAccess}
                            onChange={(e) => setAllowAdminAccess(e.target.checked)}
                            color="primary"
                          />
                        }
                        label="점검 페이지에 관리자 버튼 표시"
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                        관리자는 항상 접근 가능하며, 이 옵션은 점검 페이지에 관리자 버튼 표시 여부를 설정합니다.
                      </Typography>
                    </Grid>
                    
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        multiline
                        rows={2}
                        label="문의 안내"
                        value={contactInfo}
                        onChange={(e) => setContactInfo(e.target.value)}
                        placeholder="문의사항이 있으시면 고객센터로 연락해 주세요."
                        InputProps={{
                          startAdornment: <ContactSupport sx={{ mr: 1, color: 'action.active', alignSelf: 'flex-start', mt: 1 }} />
                        }}
                      />
                    </Grid>
                  </Grid>
                </AccordionDetails>
              </Accordion>
            )}

            {/* 예시 사유 */}
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                예시:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                {[
                  '정기 점검 완료',
                  'API 서버 재시작',
                  '긴급 패치 적용',
                  '시스템 장애 발생',
                  '점검 작업 시작'
                ].map((example) => (
                  <Chip
                    key={example}
                    label={example}
                    size="small"
                    variant="outlined"
                    onClick={() => setReason(example)}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Box>
            </Box>

            {/* 성공 메시지 */}
            {success && (
              <Alert severity="success" sx={{ mb: 2 }}>
                상태가 성공적으로 업데이트되었습니다! 잠시 후 페이지가 새로고침됩니다.
              </Alert>
            )}

            {/* 에러 메시지 */}
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={handleClose} disabled={updating}>
          취소
        </Button>
        <Button
          variant="contained"
          onClick={handleStatusUpdate}
          disabled={updating || !newStatus || !reason.trim() || success}
          sx={{ 
            backgroundColor: theme.palette.ui?.header || '#152484',
            '&:hover': { backgroundColor: '#003A87' }
          }}
        >
          {updating ? (
            <>
              <CircularProgress size={20} sx={{ mr: 1 }} />
              업데이트 중...
            </>
          ) : (
            '상태 업데이트'
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default StatusUpdateModal;