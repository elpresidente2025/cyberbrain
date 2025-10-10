import { useState, useCallback } from 'react';

/**
 * useNotification - 알림 관리 훅
 *
 * @returns {Object} { notification, showNotification, hideNotification }
 */
export const useNotification = () => {
  const [notification, setNotification] = useState({
    open: false,
    message: '',
    severity: 'success'
  });

  const showNotification = useCallback((message, severity = 'success') => {
    setNotification({
      open: true,
      message,
      severity
    });
  }, []);

  const hideNotification = useCallback(() => {
    setNotification(prev => ({
      ...prev,
      open: false
    }));
  }, []);

  return {
    notification,
    showNotification,
    hideNotification
  };
};

export default useNotification;
