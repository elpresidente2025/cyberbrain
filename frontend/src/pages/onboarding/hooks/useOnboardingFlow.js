import { useCallback, useEffect, useRef, useState } from 'react';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';
import { normalizeAuthUser } from '../../../utils/authz';
import { getRequiredRegionFields } from '../../../components/OnboardingGuard';

export const MIN_BIO_LENGTH = 50;

const INITIAL_DATA = {
  position: '',
  regionMetro: '',
  regionLocal: '',
  electoralDistrict: '',
  bio: '',
};

export function validateRegion(data) {
  const required = getRequiredRegionFields(data.position);
  for (const key of required) {
    if (!data[key]) return `${fieldLabel(key)}을(를) 선택해주세요.`;
  }
  return null;
}

export function validateBio(bio) {
  const text = typeof bio === 'string' ? bio.trim() : '';
  if (text.length < MIN_BIO_LENGTH) {
    return `자기소개는 최소 ${MIN_BIO_LENGTH}자 이상 입력해주세요. (현재 ${text.length}자)`;
  }
  return null;
}

function fieldLabel(key) {
  switch (key) {
    case 'regionMetro': return '광역자치단체';
    case 'regionLocal': return '기초자치단체';
    case 'electoralDistrict': return '선거구';
    default: return key;
  }
}

export function useOnboardingFlow() {
  const [data, setData] = useState(INITIAL_DATA);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    (async () => {
      try {
        const res = await callFunctionWithNaverAuth('getUserProfile');
        const profile = res?.profile || res || {};
        if (!mountedRef.current) return;
        setData({
          position: profile.position || '',
          regionMetro: profile.regionMetro || '',
          regionLocal: profile.regionLocal || '',
          electoralDistrict: profile.electoralDistrict || '',
          bio: profile.bio || '',
        });
      } catch (e) {
        console.error('[useOnboardingFlow] 프로필 로드 실패:', e);
        if (mountedRef.current) setError('프로필을 불러오지 못했습니다. 다시 시도해주세요.');
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
    return () => { mountedRef.current = false; };
  }, []);

  const updateField = useCallback((name, value) => {
    setError('');
    setData((prev) => {
      const next = { ...prev, [name]: value };
      // position이 바뀌면 지역 필드 중 불필요한 값 초기화 원칙은 유지하지 않음(덮어쓰기 주의)
      // 단, position 변경 시 기존 선택값은 참고용으로 남겨두고 사용자가 재확인하게 한다.
      return next;
    });
  }, []);

  const savePartial = useCallback(async (partial) => {
    setSaving(true);
    setError('');
    try {
      await callFunctionWithNaverAuth('updateProfile', partial);

      // localStorage 및 useAuth 상태 동기화
      try {
        const current = JSON.parse(localStorage.getItem('currentUser') || '{}');
        const merged = normalizeAuthUser({ ...current, ...partial });
        localStorage.setItem('currentUser', JSON.stringify(merged));
        window.dispatchEvent(new CustomEvent('userProfileUpdated', { detail: merged }));
      } catch (_) {}

      return true;
    } catch (e) {
      console.error('[useOnboardingFlow] savePartial 실패:', e);
      setError(e?.message || '저장에 실패했습니다. 다시 시도해주세요.');
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  return {
    data,
    loading,
    saving,
    error,
    setError,
    updateField,
    savePartial,
  };
}
