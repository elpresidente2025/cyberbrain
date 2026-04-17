// frontend/src/hooks/useGenerateForm.js (수정된 최종 버전)

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { hasAdminAccess } from '../utils/authz';

// 원고 생성 폼 입력값을 브라우저에 영속 저장하기 위한 키 prefix.
// "생성된 원고를 최종 선택(저장)"할 때까지 새로고침/재시작에도 남아 있어야 한다.
const STORAGE_KEY_PREFIX = 'generateFormDraft:';
const storageKeyFor = (uid) => (uid ? `${STORAGE_KEY_PREFIX}${uid}` : null);

// 🎯 관리자 시연용 참고자료 (2번 슬롯에 배치)
const ADMIN_DEMO_INSTRUCTIONS = `인천시, 노선 체계 재정비…"혼잡도로 개선, 고속도로 건설"
등록 2025.12.22 08:52:10

[인천=뉴시스] 함상환 기자 = 인천시는 22일 송도·청라경제자유구역 및 계양 테크노밸리(TV) 개발계획, 고속도로 건설 및 교통혼잡도로 개선사업계획 등 국가 상위계획을 반영해 광역시도 노선 체계를 재정비하여 고시한다고 22일 밝혔다.

이번 재정비를 통해 기존 68개 노선, 총연장 891km였던 광역시도 노선은 76개 노선, 931km로 확대하고, 도시 확장과 장래 개발계획에 따른 교통 수요 증가를 반영해 신규 지정 10개, 변경 13개, 폐지 2개 노선이 포함되며, 전체 연장은 40km 늘어나게 된다.

특히 송도국제도시 11공구와 계양 테크노밸리(TV), 청라·서창 등 대규모 개발이 진행 중인 지역을 중심으로 신규 노선이 다수 지정됐다.

장철배 시 교통국장은 "이번 광역시도 노선 재정비는 개발사업과 미래 교통 여건 변화를 반영해 체계적인 도로망 확충을 위한 선제적 과정"이라며, "광역축과 간선축 간 연결이 강화되어 시민 이동 편의가 더욱 개선될 것"이라고 밝혔다.`;

// 폼의 초기 상태를 정의합니다.
const initialState = {
  category: '',
  subCategory: '',
  topic: '', // ✅ 수정: 'prompt' 대신 'topic'을 기본으로 사용
  instructions: ['', ''], // 1번(입장문) + 2번(뉴스/데이터) 기본 노출
  keywords: '',
};

// 🎯 관리자용 초기 상태 (참고자료 2번 슬롯에 시연 데이터)
const adminInitialState = {
  category: '',
  subCategory: '',
  topic: '',
  instructions: ['', ADMIN_DEMO_INSTRUCTIONS], // 1번 슬롯 비움, 2번 슬롯에 시연 자료
  keywords: '',
};

export const useGenerateForm = (user = null) => {
  const uid = user?.uid || null;

  // 🎯 관리자면 시연용 프리셋, 일반 사용자면 기본 상태
  const getInitialState = () => {
    if (hasAdminAccess(user)) {
      return adminInitialState;
    }
    return initialState;
  };

  // 폼 데이터를 관리하는 상태. 최초 렌더 시점에는 user가 아직 null일 수 있어
  // 일단 기본 상태로 초기화하고, user가 준비되면 아래 useEffect에서 localStorage를 복원한다.
  const [formData, setFormData] = useState(initialState);
  const hydratedRef = useRef(false);

  // 🗂️ user가 준비되면 localStorage에 저장된 입력값을 복원.
  //   - 저장된 값이 있으면 그대로 복원 (새로고침/재시작에도 유지)
  //   - 없으면 사용자 유형별 초기 상태(관리자 프리셋 포함) 적용
  useEffect(() => {
    if (!uid || hydratedRef.current) return;
    hydratedRef.current = true;
    try {
      const raw = localStorage.getItem(storageKeyFor(uid));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          setFormData((prev) => ({ ...prev, ...parsed }));
          return;
        }
      }
    } catch (_) { /* corrupted json → fall through to preset */ }
    setFormData(getInitialState());
  }, [uid]); // eslint-disable-line react-hooks/exhaustive-deps

  // 💾 formData 변경 시 localStorage에 동기화. hydration이 끝난 뒤에만 기록해서
  //    초기 마운트 시 빈 상태로 저장된 값을 덮어쓰지 않도록 한다.
  useEffect(() => {
    if (!uid || !hydratedRef.current) return;
    try {
      localStorage.setItem(storageKeyFor(uid), JSON.stringify(formData));
    } catch (_) { /* quota exceeded 등은 무시 */ }
  }, [uid, formData]);

  /**
   * 폼 데이터의 일부를 업데이트하는 함수.
   * useCallback을 사용하여 함수가 불필요하게 재생성되는 것을 방지합니다.
   * @param {object} updates - 변경할 필드와 값. 예: { topic: '새로운 주제' }
   */
  const updateForm = useCallback((updates) => {
    setFormData(prev => ({ ...prev, ...updates }));
  }, []);

  /**
   * localStorage에 저장된 폼 입력값을 삭제한다.
   * 원고가 최종 선택/저장되어 더 이상 임시 상태를 유지할 필요가 없을 때 호출.
   */
  const clearPersistedForm = useCallback(() => {
    const key = storageKeyFor(uid);
    if (!key) return;
    try { localStorage.removeItem(key); } catch (_) {}
  }, [uid]);

  /**
   * 폼 데이터를 초기 상태로 리셋하는 함수.
   */
  const resetForm = useCallback(() => {
    setFormData(getInitialState());
    clearPersistedForm();
  }, [user, clearPersistedForm]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 폼 데이터가 유효한지 검사하는 함수.
   * @returns {{isValid: boolean, error: string|null}}
   */
  const validateForm = useCallback(() => {
    // ✅ 수정: 'prompt' 대신 'topic' 필드가 비어있는지 확인합니다.
    if (!formData.topic || formData.topic.trim() === '') {
      return { isValid: false, error: '주제를 입력해주세요.', field: 'topic' };
    }
    // 카테고리는 AI가 자동 분류하므로 검증하지 않음
    // 내 입장문(index 0) 또는 뉴스/데이터(index >= 1) 중 하나는 채워져야 한다.
    const instructionList = Array.isArray(formData.instructions)
      ? formData.instructions
      : [formData.instructions];
    const hasStance = !!(instructionList[0] && String(instructionList[0]).trim());
    const hasNewsData = instructionList
      .slice(1)
      .some((entry) => entry && String(entry).trim());

    if (!hasStance && !hasNewsData) {
      return {
        isValid: false,
        error: '내 입장문 또는 뉴스/데이터 중 하나는 입력해주세요.',
        field: 'instructions0'
      };
    }
    return { isValid: true, error: null, field: null };
  }, [formData.topic, formData.instructions]);

  /**
   * '생성하기' 버튼의 활성화 여부를 결정하는 변수.
   * useMemo를 사용하여 formData가 변경될 때만 재계산합니다.
   */
  const canGenerate = useMemo(() => {
    // 주제 + (내 입장문 OR 뉴스/데이터 중 하나) 가 있어야 생성 가능.
    const instructionList = Array.isArray(formData.instructions)
      ? formData.instructions
      : [formData.instructions];
    const hasStance = !!(instructionList[0] && String(instructionList[0]).trim());
    const hasNewsData = instructionList
      .slice(1)
      .some((entry) => entry && String(entry).trim());
    return !!formData.topic?.trim() && (hasStance || hasNewsData);
  }, [formData.topic, formData.instructions]);

  // 훅이 외부로 제공하는 상태와 함수들
  return {
    formData,
    updateForm,
    resetForm,
    validateForm,
    canGenerate,
    clearPersistedForm,
  };
};
