import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  IconButton,
  Box,
} from '@mui/material';
import { Close } from '@mui/icons-material';

const HelpModal = ({ open, onClose, title, children }) => {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 2,
          maxHeight: '80vh',
        }
      }}
    >
      <DialogTitle sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        pb: 1,
        borderBottom: '1px solid #ddd'
      }}>
        <Box sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {title}
        </Box>
        <IconButton
          onClick={onClose}
          size="small"
          sx={{ color: '#666' }}
        >
          <Close />
        </IconButton>
      </DialogTitle>
      
      <DialogContent sx={{ p: 3, overflow: 'auto' }}>
        {children}
      </DialogContent>
      
      <DialogActions sx={{ p: 2, borderTop: '1px solid #ddd' }}>
        <Button 
          onClick={onClose} 
          variant="contained" 
          sx={{ 
            bgcolor: '#003A87',
            '&:hover': { bgcolor: '#002868' }
          }}
        >
          확인
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default HelpModal;