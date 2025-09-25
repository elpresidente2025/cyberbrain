import { useState, useCallback } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';

// 1회당 1개 생성, 최대 3회, 새 글은 앞에 추가(최대 3개 유지)
export function usePostGenerator() {
  const [attempts, setAttempts] = useState(0);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const generate = useCallback(async (formData) => {
    if (attempts >= 3) return;
    setLoading(true);
    setError(null);
    try {
      // generatePosts 함수 사용 (실제 AI 생성)
      const generatePostFn = httpsCallable(functions, 'generatePosts');
      const { data } = await generatePostFn(formData);
      const newDraft = data?.drafts ?? data;
      if (!newDraft) throw new Error('Invalid response from generatePosts');
      setDrafts(prev => [newDraft, ...prev].slice(0, 3));
      setAttempts(prev => prev + 1);
      return newDraft;
    } catch (e) {
      setError(e);
      throw e;
    } finally {
      setLoading(false);
    }
  }, [attempts]);

  const reset = useCallback(() => {
    setAttempts(0);
    setDrafts([]);
    setError(null);
  }, []);

  return { attempts, drafts, loading, error, generate, reset, canGenerate: attempts < 3 };
}