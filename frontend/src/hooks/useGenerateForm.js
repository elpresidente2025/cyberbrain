// frontend/src/hooks/useGenerateForm.js (수정된 최종 버전)

import { useState, useCallback, useMemo } from 'react';

// 폼의 초기 상태를 정의합니다.
const initialState = {
  category: '',
  subCategory: '',
  topic: '', // ✅ 수정: 'prompt' 대신 'topic'을 기본으로 사용
  instructions: '',
  keywords: '',
};

export const useGenerateForm = () => {
  // 폼 데이터를 관리하는 상태
  const [formData, setFormData] = useState(initialState);

  /**
   * 폼 데이터의 일부를 업데이트하는 함수.
   * useCallback을 사용하여 함수가 불필요하게 재생성되는 것을 방지합니다.
   * @param {object} updates - 변경할 필드와 값. 예: { topic: '새로운 주제' }
   */
  const updateForm = useCallback((updates) => {
    setFormData(prev => ({ ...prev, ...updates }));
  }, []);

  /**
   * 폼 데이터를 초기 상태로 리셋하는 함수.
   */
  const resetForm = useCallback(() => {
    setFormData(initialState);
  }, []);

  /**
   * 폼 데이터가 유효한지 검사하는 함수.
   * @returns {{isValid: boolean, error: string|null}}
   */
  const validateForm = useCallback(() => {
    // ✅ 수정: 'prompt' 대신 'topic' 필드가 비어있는지 확인합니다.
    if (!formData.topic || formData.topic.trim() === '') {
      return { isValid: false, error: '주제를 입력해주세요.' };
    }
    if (!formData.category) {
      return { isValid: false, error: '카테고리를 선택해주세요.' };
    }
    return { isValid: true, error: null };
  }, [formData.topic, formData.category]);

  /**
   * '생성하기' 버튼의 활성화 여부를 결정하는 변수.
   * useMemo를 사용하여 formData가 변경될 때만 재계산합니다.
   */
  const canGenerate = useMemo(() => {
    // ✅ 수정: 'prompt' 대신 'topic' 필드를 기준으로 판단합니다.
    return !!formData.topic && !!formData.category;
  }, [formData.topic, formData.category]);

  // 훅이 외부로 제공하는 상태와 함수들
  return {
    formData,
    updateForm,
    resetForm,
    validateForm,
    canGenerate
  };
};