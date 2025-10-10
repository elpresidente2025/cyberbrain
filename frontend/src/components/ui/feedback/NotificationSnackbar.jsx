import React from 'react';
import { Snackbar, Alert } from '@mui/material';

/**
 * NotificationSnackbar - 알림 스낵바 컴포넌트
 *
 * @param {boolean} open - 열림 상태
 * @param {function} onClose - 닫기 핸들러
 * @param {string} message - 알림 메시지
 * @param {string} severity - success, error, warning, info
 * @param {number} autoHideDuration - 자동 숨김 시간 (ms)
 * @param {object} position - 위치 { vertical, horizontal }
 */
const NotificationSnackbar = ({
  open,
  onClose,
  message,
  severity = 'success',
  autoHideDuration = 4000,
  position = { vertical: 'bottom', horizontal: 'center' },
  ...props
}) => {
  return (
    <Snackbar
      open={open}
      autoHideDuration={autoHideDuration}
      onClose={onClose}
      anchorOrigin={position}
      {...props}
    >
      <Alert
        onClose={onClose}
        severity={severity}
        sx={{ width: '100%' }}
        variant="filled"
      >
        {message}
      </Alert>
    </Snackbar>
  );
};

export default NotificationSnackbar;
