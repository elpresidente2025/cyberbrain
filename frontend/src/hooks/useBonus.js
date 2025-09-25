import { useState, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';
import { useAuth } from './useAuth';
import { callFunctionWithNaverAuth } from '../services/firebaseService';

export const useBonus = () => {
  const { user } = useAuth();
  const [bonusStats, setBonusStats] = useState({
    hasBonus: false,
    availableBonus: 0,
    totalBonusGenerated: 0,
    bonusUsed: 0
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const callCheckBonusEligibility = httpsCallable(functions, 'checkBonusEligibility');
  const callUseBonusGeneration = httpsCallable(functions, 'useBonusGeneration');

  // 보너스 상태 조회
  const fetchBonusStats = async () => {
    if (!user?.uid) return;

    try {
      setLoading(true);
      setError(null);
      const response = await callFunctionWithNaverAuth('checkBonusEligibility');
      setBonusStats(response.data || {
        hasBonus: false,
        availableBonus: 0,
        totalBonusGenerated: 0,
        bonusUsed: 0
      });
    } catch (err) {
      console.error('Failed to fetch bonus stats:', err);
      setError(err.message);
      // 에러 시 기본값 설정
      setBonusStats({
        hasBonus: false,
        availableBonus: 0,
        totalBonusGenerated: 0,
        bonusUsed: 0
      });
    } finally {
      setLoading(false);
    }
  };

  // 보너스 사용
  const useBonus = async () => {
    if (!bonusStats.hasBonus) {
      throw new Error('사용 가능한 보너스가 없습니다.');
    }

    try {
      await callFunctionWithNaverAuth('useBonusGeneration');
      // 사용 후 다시 조회하여 업데이트
      await fetchBonusStats();
      return true;
    } catch (err) {
      console.error('Failed to use bonus:', err);
      throw err;
    }
  };

  useEffect(() => {
    if (user?.uid) {
      fetchBonusStats();
    }
  }, [user?.uid]);

  return {
    bonusStats,
    loading,
    error,
    fetchBonusStats,
    useBonus
  };
};