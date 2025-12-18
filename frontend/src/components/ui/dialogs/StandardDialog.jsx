import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Typography,
  Box,
  Button
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { transitions } from '../../../theme/tokens';

/**
 * StandardDialog - 재사용 가능한 표준 다이얼로그 컴포넌트
 *
 * @param {boolean} open - 다이얼로그 열림 상태
 * @param {function} onClose - 닫기 핸들러
 * @param {string} title - 다이얼로그 제목
 * @param {ReactNode} children - 다이얼로그 내용
 * @param {Array} actions - 액션 버튼 배열 [{ label, onClick, variant, color, disabled, loading }]
 * @param {string} maxWidth - 최대 너비 (xs, sm, md, lg, xl)
 * @param {boolean} fullWidth - 전체 너비 사용 여부
 * @param {string|number} minHeight - 최소 높이
 * @param {boolean} showCloseIcon - 닫기 아이콘 표시 여부
 * @param {boolean} dividers - DialogContent dividers 사용 여부
 * @param {ReactNode} titleIcon - 제목 옆 아이콘
 */
const StandardDialog = ({
  open,
  onClose,
  title,
  children,
  actions = [],
  maxWidth = 'md',
  fullWidth = true,
  minHeight,
  showCloseIcon = true,
  dividers = false,
  titleIcon,
  ...props
}) => {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      // 포커스 관리 문제 방지 - aria-hidden 충돌 해결
      slotProps={{
        backdrop: {
          'aria-hidden': false
        }
      }}
      PaperProps={{
        sx: {
          ...(minHeight ? { minHeight } : {}),
          transition: `transform ${transitions.normal} ${transitions.easing.easeOut}, opacity ${transitions.normal} ${transitions.easing.easeOut}`
        }
      }}
      {...props}
    >
      <DialogTitle sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {titleIcon}
          <Typography variant="h6">{title}</Typography>
        </Box>
        {showCloseIcon && (
          <IconButton onClick={onClose} size="small">
            <Close />
          </IconButton>
        )}
      </DialogTitle>

      <DialogContent dividers={dividers}>
        {children}
      </DialogContent>

      {actions.length > 0 && (
        <DialogActions>
          {actions.map((action, index) => (
            <Button
              key={index}
              onClick={action.onClick}
              variant={action.variant || 'text'}
              color={action.color || 'primary'}
              disabled={action.disabled || action.loading}
              {...action.buttonProps}
            >
              {action.loading ? '처리 중...' : action.label}
            </Button>
          ))}
        </DialogActions>
      )}
    </Dialog>
  );
};

export default StandardDialog;
