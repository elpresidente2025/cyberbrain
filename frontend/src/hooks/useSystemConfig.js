// frontend/src/hooks/useSystemConfig.js
import { useState, useEffect } from 'react';
import { callFunction } from '../services/firebaseService';

export const useSystemConfig = () => {
  const [config, setConfig] = useState({
    aiKeywordRecommendationEnabled: true // 기본값
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await callFunction('getSystemConfig');
      if (result.config) {
        setConfig(result.config);
      }
    } catch (err) {
      console.error('시스템 설정 로드 실패:', err);
      setError(err);
      // 에러가 발생해도 기본값 사용
    } finally {
      setLoading(false);
    }
  };

  return { config, loading, error, reload: loadConfig };
};
