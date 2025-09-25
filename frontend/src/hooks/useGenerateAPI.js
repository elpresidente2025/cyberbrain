// frontend/src/hooks/useGenerateAPI.js - 보안 및 성능 개선된 버전

import { useState, useCallback } from 'react';
import { callHttpFunction } from '../services/firebaseService';
import { useAuth } from './useAuth';
import { handleHttpError } from '../utils/errorHandler';
import { sanitizeHtml, stripHtmlTags, getTextLength, isSeoOptimized } from '../utils/contentSanitizer';
import { CONFIG } from '../config/constants';

export function useGenerateAPI() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [attempts, setAttempts] = useState(0);

  // 📌 메모리 누수 방지: 최대 개수 제한
  const addDraft = useCallback((newDraft) => {
    setDrafts(prev => [
      ...prev.slice(-(CONFIG.MAX_DRAFTS_STORAGE - 1)),
      newDraft
    ]);
  }, []);

  // 메타데이터 수집 함수 (향후 기능)
  const collectMetadata = useCallback(async (draft) => {
    try {
      console.log('📊 메타데이터 수집 (임시 비활성화):', draft.title);
      // 향후 구현 예정
      return null;
    } catch (error) {
      console.warn('⚠️ 메타데이터 수집 실패:', error.message);
    }
    return null;
  }, []);

  // 📌 제거됨: HTML 처리 함수들은 이제 utils/contentSanitizer.js에서 import

  // 원고 생성 함수
  const generate = useCallback(async (formData, useBonus = false) => {
    if (attempts >= CONFIG.MAX_GENERATION_ATTEMPTS) {
      return { success: false, error: '재생성 한도에 도달했습니다.' };
    }

    setLoading(true);
    setError(null);

    try {
      console.log('🔥 generatePosts 호출 시작');

      // 📌 보안 개선: localStorage 값 검증
      const modelName = localStorage.getItem('gemini_model') || CONFIG.DEFAULT_AI_MODEL;

      const requestData = {
        ...formData,
        prompt: formData.topic || formData.prompt,
        generateSingle: true,
        useBonus: useBonus,
        modelName: modelName,
        applyEditorialRules: true
      };

      delete requestData.topic;

      console.log('📝 요청 데이터:', requestData);

      // HTTP 함수 호출
      const result = await callHttpFunction(CONFIG.FUNCTIONS.GENERATE_POSTS, requestData);
      console.log('✅ generatePosts 응답 수신:', result);

      // HTTP 응답 구조 확인 및 처리
      const responseData = result?.data ? result.data : result;
      console.log('🔍 백엔드 응답 전체 구조:', responseData);

      // 서버에서 content 필드로 응답하므로 이를 사용
      const content = responseData?.content;

      if (!content) {
        console.error('⚠️ 유효하지 않은 응답 구조:', result);
        console.error('⚠️ responseData:', responseData);
        throw new Error('AI 응답에서 유효한 원고 데이터를 찾을 수 없습니다.');
      }

      console.log('👍 원고 콘텐츠 추출 성공:', content.substring(0, 100) + '...');

      // 📌 개선: 안전한 콘텐츠 처리 및 정확한 길이 계산
      const sanitizedContent = sanitizeHtml(content);
      const plainTextContent = stripHtmlTags(content);
      const actualWordCount = getTextLength(content);

      const newDraft = {
        id: Date.now(),
        title: formData.topic || formData.prompt || '새로운 원고',
        content: content,

        // 📌 보안 개선: DOMPurify 사용
        htmlContent: sanitizedContent,
        plainText: plainTextContent,

        category: formData.category || '일반',
        subCategory: formData.subCategory || '',
        keywords: formData.keywords || '',
        generatedAt: new Date().toISOString(),
        wordCount: actualWordCount,

        // 메타데이터
        style: formData.style,
        type: formData.type,

        // 📌 개선: 설정 기반 SEO 최적화 판단
        aiGeneratedVariations: 1,
        selectedVariationIndex: 0,
        seoOptimized: isSeoOptimized(content)
      };

      // 📌 메모리 누수 방지: 제한된 개수로 추가
      addDraft(newDraft);
      setAttempts(prev => prev + 1);
      
      // 🆕 메타데이터 수집 (비동기, 에러 무시)
      collectMetadata(newDraft).catch(console.warn);
      
      console.log('✅ 원고 생성 완료:', { 
        title: newDraft.title, 
        wordCount: newDraft.wordCount,
        seoOptimized: newDraft.seoOptimized 
      });
      
      const message = useBonus 
        ? `보너스 원고가 성공적으로 생성되었습니다! (${newDraft.wordCount}자)` 
        : `AI 원고가 성공적으로 생성되었습니다! (${newDraft.wordCount}자)`;

      return { 
        success: true, 
        message: message
      };

    } catch (err) {
      console.error('❌ generatePosts 호출 실패:', err);

      // 📌 개선: 중앙화된 에러 처리
      const errorMessage = handleHttpError(err);

      setError(errorMessage);
      return { success: false, error: errorMessage };
      
    } finally {
      setLoading(false);
    }
  }, [attempts, addDraft, collectMetadata]);

  // 초안 저장 함수
  const save = useCallback(async (draft) => {
    try {
      console.log('💾 savePost 호출 시작:', draft.title);

      const result = await callHttpFunction(CONFIG.FUNCTIONS.SAVE_POST, {
        title: draft.title,
        content: draft.content,
        htmlContent: draft.htmlContent,
        plainText: draft.plainText,
        category: draft.category,
        subCategory: draft.subCategory,
        keywords: draft.keywords,
        wordCount: draft.wordCount,
        style: draft.style,
        type: draft.type,
        meta: draft.meta
      });

      console.log('✅ savePost 응답 수신:', result);
      console.log('🔍 응답 타입:', typeof result);
      console.log('🔍 응답 success 필드:', result?.success);

      if (result?.success) {
        // 저장 시 메타데이터 수집
        collectMetadata({
          ...draft,
          savedAt: new Date().toISOString()
        }).catch(console.warn);
        
        return {
          success: true,
          message: result.message || '원고가 성공적으로 저장되었습니다.'
        };
      } else {
        throw new Error(result?.error || '저장에 실패했습니다.');
      }
      
    } catch (err) {
      console.error('❌ savePost 호출 실패:', err);

      // 📌 개선: 중앙화된 에러 처리
      const errorMessage = handleHttpError(err);

      return { success: false, error: errorMessage };
    }
  }, [collectMetadata]);

  // 상태 초기화 함수
  const reset = useCallback(() => {
    setDrafts([]);
    setAttempts(0);
    setError(null);
  }, []);

  return {
    loading,
    error,
    drafts,
    setDrafts,
    attempts,
    maxAttempts: CONFIG.MAX_GENERATION_ATTEMPTS,
    generate,
    save,
    reset,
    // 📌 개선: 유틸리티 함수들은 직접 import해서 사용
    // stripHtmlTags, sanitizeHtml 제거됨 - utils/contentSanitizer에서 직접 import
  };
};