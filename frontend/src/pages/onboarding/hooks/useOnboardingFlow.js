import { useCallback, useEffect, useRef, useState } from 'react';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';
import { normalizeAuthUser } from '../../../utils/authz';
import { getRequiredRegionFields } from '../../../components/OnboardingGuard';

const INITIAL_DATA = {
  status: '',
  position: '',
  regionMetro: '',
  regionLocal: '',
  electoralDistrict: '',
  ageDecade: '',
  ageDetail: '',
  gender: '',
  familyStatus: '',
  backgroundCareer: '',
  localConnection: '',
  politicalExperience: '',
};

export function validateRegion(data) {
  const required = getRequiredRegionFields(data.position);
  for (const key of required) {
    if (!data[key]) return `${fieldLabel(key)}을(를) 선택해주세요.`;
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

export function useOnboardingFlow({ preview = false } = {}) {
  const [data, setData] = useState(INITIAL_DATA);
  const [loading, setLoading] = useState(!preview);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    if (preview) {
      setData(INITIAL_DATA);
      setLoading(false);
      return () => { mountedRef.current = false; };
    }
    (async () => {
      try {
        const res = await callFunctionWithNaverAuth('getUserProfile');
        const profile = res?.profile || res || {};
        if (!mountedRef.current) return;
        setData({
          status: profile.status || '',
          position: profile.position || '',
          regionMetro: profile.regionMetro || '',
          regionLocal: profile.regionLocal || '',
          electoralDistrict: profile.electoralDistrict || '',
          ageDecade: profile.ageDecade || '',
          ageDetail: profile.ageDetail || '',
          gender: profile.gender || '',
          familyStatus: profile.familyStatus || '',
          backgroundCareer: profile.backgroundCareer || '',
          localConnection: profile.localConnection || '',
          politicalExperience: profile.politicalExperience || '',
        });
      } catch (e) {
        console.error('[useOnboardingFlow] 프로필 로드 실패:', e);
        if (mountedRef.current) setError('프로필을 불러오지 못했습니다. 다시 시도해주세요.');
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
    return () => { mountedRef.current = false; };
  }, [preview]);

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
    if (preview) {
      return true;
    }
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
  }, [preview]);

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
