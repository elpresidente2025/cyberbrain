// frontend/src/hooks/useGenerateAPI.js - 보안 및 성능 개선된 버전

import { useState, useCallback, useEffect } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { callFunctionWithNaverAuth, callGeneratePostsViaCloudRun } from '../services/firebaseService';
import { useAuth } from './useAuth';
import { handleHttpError } from '../utils/errorHandler';
import { sanitizeHtml, stripHtmlTags, getTextLength, isSeoOptimized } from '../utils/contentSanitizer';
import { CONFIG } from '../config/constants';
import { db } from '../services/firebase';

export function useGenerateAPI() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [attempts, setAttempts] = useState(0);
  const [progress, setProgress] = useState(null); // { step, progress, message }

  // 🆕 생성 세션 관리
  const [sessionId, setSessionId] = useState(null);
  const [sessionAttempts, setSessionAttempts] = useState(0);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [canRegenerate, setCanRegenerate] = useState(false);
  const sessionStoragePrefix = user?.uid ? `draft_session_${user.uid}_` : null;

  const getSessionStorageKey = useCallback((id) => {
    if (!id || !user?.uid) return null;
    return `draft_session_${user.uid}_${id}`;
  }, [user?.uid]);

  // 📌 메모리 누수 방지: 최대 개수 제한
  const addDraft = useCallback((newDraft) => {
    setDrafts(prev => [
      ...prev.slice(-(CONFIG.MAX_DRAFTS_STORAGE - 1)),
      newDraft
    ]);
  }, []);

  // 🆕 페이지 로드 시 세션 복원
  useEffect(() => {
    if (!user?.uid) return;

    try {
      // localStorage에서 모든 세션 찾기
      const allKeys = Object.keys(localStorage);
      const sessionKeys = allKeys.filter(key => sessionStoragePrefix && key.startsWith(sessionStoragePrefix));

      if (sessionKeys.length === 0) {
        console.log('📭 복원할 세션 없음');
        return;
      }

      // 가장 최근 세션 찾기
      let latestSession = null;
      let latestTime = 0;

      sessionKeys.forEach(key => {
        try {
          const dataStr = localStorage.getItem(key);
          const data = JSON.parse(dataStr);
          if (data.savedAt > latestTime) {
            latestTime = data.savedAt;
            latestSession = { key, data };
          }
        } catch (e) {
          console.warn('⚠️ 세션 파싱 실패:', key, e);
        }
      });

      if (!latestSession) {
        console.log('📭 유효한 세션 없음');
        return;
      }

      // 30분 체크 (1800000ms)
      const SESSION_TIMEOUT = 30 * 60 * 1000;
      const age = Date.now() - latestSession.data.savedAt;

      if (age > SESSION_TIMEOUT) {
        console.log('🕒 세션 만료 (30분 초과) - 삭제:', {
          sessionId: latestSession.data.sessionId,
          age: Math.floor(age / 1000 / 60) + '분'
        });
        localStorage.removeItem(latestSession.key);
        return;
      }

      // 세션 복원
      const { sessionId, attempts, maxAttempts, canRegenerate, drafts } = latestSession.data;

      console.log('✨ 세션 복원:', {
        sessionId,
        attempts,
        draftCount: drafts.length,
        age: Math.floor(age / 1000 / 60) + '분'
      });

      setSessionId(sessionId);
      setSessionAttempts(attempts);
      setMaxAttempts(maxAttempts);
      setCanRegenerate(canRegenerate);
      setDrafts(drafts);

    } catch (error) {
      console.error('❌ 세션 복원 실패:', error);
    }
  }, [user?.uid, sessionStoragePrefix]);

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
    // 세션 기반 제한 체크: 재생성 시 세션 한도 확인
    if (sessionId && !canRegenerate) {
      return { success: false, error: '재생성 한도에 도달했습니다. 새로운 원고를 생성해주세요.' };
    }

    setLoading(true);
    setError(null);
    setProgress({ step: 0, progress: 0, message: '시작 중...' });

    // Firestore 리스너 등록을 위한 변수
    let unsubscribe = null;

    try {
      console.log('🔥 generatePosts 호출 시작');

      // 📌 보안 개선: localStorage 값 검증 및 잘못된 모델명 수정
      let modelName = localStorage.getItem('gemini_model');

      // 허용된 모델만 통과, 나머지는 기본값으로 교체
      const ALLOWED_MODELS = ['gemini-2.5-flash', 'gemini-2.5-flash-lite'];
      if (!modelName || !ALLOWED_MODELS.includes(modelName)) {
        console.warn('⚠️ 잘못된 모델명 감지:', modelName, '→ 기본값으로 수정');
        modelName = CONFIG.DEFAULT_AI_MODEL;
        localStorage.setItem('gemini_model', modelName);
      }

      // 🔧 진행 상황 추적용 세션 ID (프론트엔드에서 생성하여 백엔드로 전달)
      const progressSessionId = `${user.uid}_${Date.now()}`;
      const instructionEntries = Array.isArray(formData.instructions)
        ? formData.instructions
        : [formData.instructions];
      const normalizedInstructions = instructionEntries
        .map((item) => String(item || '').trim())
        .filter((item) => item.length > 0);

      const stanceText = String(
        formData.stanceText || normalizedInstructions[0] || ''
      ).trim();
      const newsDataText = String(
        formData.newsDataText || normalizedInstructions.slice(1).join('\n\n') || ''
      ).trim();
      const normalizedKeywords = String(formData.keywords || '')
        .split(',')
        .map((keyword) => keyword.trim())
        .filter((keyword) => keyword.length > 0)
        .slice(0, 2)
        .join(', ');

      const requestData = {
        ...formData,
        instructions: normalizedInstructions,
        stanceText,
        newsDataText,
        keywords: normalizedKeywords,
        prompt: formData.topic || formData.prompt,
        generateSingle: true,
        useBonus: useBonus,
        modelName: modelName,
        applyEditorialRules: true,
        sessionId: sessionId, // 🆕 재생성 시 세션 ID 전달
        progressSessionId: progressSessionId // 🔧 진행 상황 추적용 세션 ID
      };

      delete requestData.topic;

      console.log('📝 요청 데이터:', requestData);

      // Firestore 진행 상황 리스너 먼저 등록 (백엔드 응답 전에 업데이트 수신)
      // 🔧 progressSessionId를 사용하여 백엔드와 동일한 문서 참조
      const progressDocRef = doc(db, 'generation_progress', progressSessionId);
      unsubscribe = onSnapshot(
        progressDocRef,
        (docSnapshot) => {
          if (docSnapshot.exists()) {
            const data = docSnapshot.data();
            console.log('📊 진행 상황 업데이트:', data);
            setProgress({
              step: data.step,
              progress: data.progress,
              message: data.message
            });
          }
        },
        (error) => {
          console.error('⚠️ 진행 상황 리스너 에러:', error);
        }
      );

      // Cloud Run 직접 호출 (Cloud Functions 게이트웨이 60초 타임아웃 우회)
      const result = await callGeneratePostsViaCloudRun(
        requestData,
        { timeoutMs: CONFIG.GENERATE_TIMEOUT_MS }
      );
      console.log('✅ generatePosts 응답 수신:', result);

      // HTTP 응답 구조 확인 및 처리
      const responseData = result?.data ? result.data : result;
      console.log('🔍 백엔드 응답 전체 구조:', responseData);

      // 백엔드가 drafts 객체로 응답 (단일 draft)
      const draftData = responseData?.drafts;

      if (!draftData || !draftData.content) {
        console.error('⚠️ 유효하지 않은 응답 구조:', result);
        console.error('⚠️ responseData:', responseData);
        throw new Error('AI 응답에서 유효한 원고 데이터를 찾을 수 없습니다.');
      }

      const content = draftData.content;
      console.log('👍 원고 콘텐츠 추출 성공:', content.substring(0, 100) + '...');

      // 📌 개선: 안전한 콘텐츠 처리 및 정확한 길이 계산
      const sanitizedContent = sanitizeHtml(content);
      const plainTextContent = stripHtmlTags(content);
      const actualWordCount = getTextLength(content);

      const newDraft = {
        id: draftData.id || Date.now(),
        title: draftData.title || formData.topic || formData.prompt || '새로운 원고',
        topic: draftData.topic || formData.topic || formData.prompt || '',
        stanceText: stanceText,
        newsDataText: newsDataText,
        content: content,

        // 📌 보안 개선: DOMPurify 사용
        htmlContent: sanitizedContent,
        plainText: plainTextContent,

        category: draftData.category || formData.category || '일반',
        subCategory: draftData.subCategory || formData.subCategory || '',
        keywords: draftData.keywords || formData.keywords || '',
        generatedAt: draftData.generatedAt || new Date().toISOString(),
        wordCount: draftData.wordCount || actualWordCount,

        // 메타데이터
        style: formData.style,
        type: formData.type,
        sourceInput:
          draftData.sourceInput ||
          formData.sourceInput ||
          formData.originalContent ||
          formData.inputContent ||
          formData.rawContent ||
          formData.prompt ||
          content,
        sourceType:
          draftData.sourceType ||
          formData.sourceType ||
          formData.inputType ||
          formData.contentType ||
          formData.writingSource ||
          'blog_draft',

        // 📌 개선: 설정 기반 SEO 최적화 판단
        aiGeneratedVariations: 1,
        selectedVariationIndex: 0,
        seoOptimized: isSeoOptimized(content),

        // 🤖 Multi-Agent 메타데이터 (관리자/테스터용)
        multiAgent: responseData.metadata?.multiAgent || null,

        // 🔑 검색어 검증 결과 (백엔드 판정 기준)
        keywordValidation:
          responseData.metadata?.multiAgent?.keywordValidation ||
          responseData.metadata?.seo?.keywordValidation ||
          null
      };

      // 📌 메모리 누수 방지: 제한된 개수로 추가
      addDraft(newDraft);
      setAttempts(prev => prev + 1);

      // 🆕 세션 정보 업데이트
      if (responseData.sessionId) {
        const newSessionId = responseData.sessionId;
        const newAttempts = responseData.attempts || 1;
        const newMaxAttempts = responseData.maxAttempts || 3;
        const newCanRegenerate = responseData.canRegenerate || false;

        setSessionId(newSessionId);
        setSessionAttempts(newAttempts);
        setMaxAttempts(newMaxAttempts);
        setCanRegenerate(newCanRegenerate);

        console.log('✅ 세션 정보 업데이트:', {
          sessionId: newSessionId,
          attempts: newAttempts,
          maxAttempts: newMaxAttempts,
          canRegenerate: newCanRegenerate
        });

        // 🆕 localStorage에 세션 및 원고 저장 (누적)
        try {
          // 기존 세션 데이터 불러오기 (재생성 시 누적)
          const storageKey = getSessionStorageKey(newSessionId);
          if (!storageKey) {
            throw new Error('세션 저장 키를 생성할 수 없습니다.');
          }

          const existingDataStr = localStorage.getItem(storageKey);
          const existingData = existingDataStr ? JSON.parse(existingDataStr) : null;
          const existingDrafts = existingData?.drafts || [];

          const sessionData = {
            userId: user.uid,
            sessionId: newSessionId,
            attempts: newAttempts,
            maxAttempts: newMaxAttempts,
            canRegenerate: newCanRegenerate,
            drafts: [...existingDrafts, newDraft], // 누적 저장
            savedAt: Date.now(),
            formData: formData
          };
          localStorage.setItem(storageKey, JSON.stringify(sessionData));
          console.log('💾 localStorage에 세션 저장 (누적):', {
            sessionId: newSessionId,
            draftCount: sessionData.drafts.length
          });
        } catch (storageError) {
          console.warn('⚠️ localStorage 저장 실패:', storageError.message);
        }
      }

      // 🆕 메타데이터 수집 (비동기, 에러 무시)
      collectMetadata(newDraft).catch(console.warn);

      console.log('✅ 원고 생성 완료:', {
        title: newDraft.title,
        wordCount: newDraft.wordCount,
        seoOptimized: newDraft.seoOptimized
      });

      const message = useBonus
        ? `보너스 원고가 성공적으로 생성되었습니다!`
        : `AI 원고가 성공적으로 생성되었습니다!`;

      return {
        success: true,
        message: message,
        topicInferred: responseData.metadata?.classification?.topicInferred || false,
      };

    } catch (err) {
      console.error('❌ generatePosts 호출 실패:', err);

      // 📌 개선: 중앙화된 에러 처리
      const errorMessage = handleHttpError(err);

      setError(errorMessage);
      setProgress({ step: -1, progress: 0, message: `오류: ${errorMessage}` });
      return { success: false, error: errorMessage };

    } finally {
      setLoading(false);

      // 리스너 정리
      if (unsubscribe) {
        setTimeout(() => {
          unsubscribe();
          console.log('🔌 진행 상황 리스너 해제');
        }, 2000); // 2초 후 해제 (완료 메시지 표시 시간 확보)
      }
    }
  }, [sessionId, canRegenerate, addDraft, collectMetadata, user, getSessionStorageKey]);

  // 초안 저장 함수
  const save = useCallback(async (draft) => {
    try {
      console.log('💾 saveSelectedPost 호출 시작:', draft.title);

      const result = await callFunctionWithNaverAuth(CONFIG.FUNCTIONS.SAVE_POST, {
        title: draft.title,
        topic: draft.topic,
        stanceText: draft.stanceText,
        newsDataText: draft.newsDataText,
        content: draft.content,
        htmlContent: draft.htmlContent,
        plainText: draft.plainText,
        category: draft.category,
        subCategory: draft.subCategory,
        keywords: draft.keywords,
        wordCount: draft.wordCount,
        style: draft.style,
        type: draft.type,
        sourceInput: draft.sourceInput,
        sourceType: draft.sourceType,
        meta: draft.meta,
        sessionId: sessionId,
        appliedStrategy: draft.multiAgent?.appliedStrategy || null
      });

      console.log('✅ saveSelectedPost 응답 수신:', result);
      console.log('🔍 응답 타입:', typeof result);
      console.log('🔍 응답 success 필드:', result?.success);

      if (result?.success) {
        // 저장 시 메타데이터 수집
        collectMetadata({
          ...draft,
          savedAt: new Date().toISOString()
        }).catch(console.warn);

        // 🆕 저장 완료 시 localStorage 세션 삭제
        if (sessionId) {
          try {
            const storageKey = getSessionStorageKey(sessionId);
            if (storageKey) {
              localStorage.removeItem(storageKey);
            }
            console.log('🗑️ 저장 완료 - localStorage 세션 삭제:', sessionId);
          } catch (e) {
            console.warn('⚠️ localStorage 삭제 실패:', e);
          }
        }

        return {
          success: true,
          message: result.message || '원고가 성공적으로 저장되었습니다.'
        };
      } else {
        throw new Error(result?.error || '저장에 실패했습니다.');
      }

    } catch (err) {
      console.error('❌ saveSelectedPost 호출 실패:', err);

      // 📌 개선: 중앙화된 에러 처리
      const errorMessage = handleHttpError(err);

      return { success: false, error: errorMessage };
    }
  }, [collectMetadata, sessionId, getSessionStorageKey]);

  // 상태 초기화 함수
  const reset = useCallback(() => {
    setDrafts([]);
    setAttempts(0);
    setError(null);
    setProgress(null);

    // 🆕 세션 초기화 및 localStorage 정리
    if (sessionId) {
      try {
        const storageKey = getSessionStorageKey(sessionId);
        if (storageKey) {
          localStorage.removeItem(storageKey);
        }
        console.log('🗑️ localStorage 세션 삭제:', sessionId);
      } catch (e) {
        console.warn('⚠️ localStorage 삭제 실패:', e);
      }
    }

    setSessionId(null);
    setSessionAttempts(0);
    setCanRegenerate(false);
  }, [sessionId, getSessionStorageKey]);

  return {
    loading,
    error,
    drafts,
    setDrafts,
    attempts,
    maxAttempts: CONFIG.MAX_GENERATION_ATTEMPTS,
    progress, // 진행 상황 추가
    generate,
    save,
    reset,
    // 🆕 세션 정보
    sessionId,
    sessionAttempts,
    maxSessionAttempts: maxAttempts,
    canRegenerate,
    // 📌 개선: 유틸리티 함수들은 직접 import해서 사용
    // stripHtmlTags, sanitizeHtml 제거됨 - utils/contentSanitizer에서 직접 import
  };
};
