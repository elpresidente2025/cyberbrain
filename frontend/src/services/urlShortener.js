import { callFunctionWithNaverAuth } from './firebaseService';

/**
 * URL 단축 서비스
 * 
 * @param {string} originalUrl - 원본 URL
 * @param {Object} options - 추가 옵션
 * @param {string} options.postId - 관련 게시물 ID (선택)
 * @param {string} options.platform - 플랫폼 (x, facebook, threads 등) (선택)
 * @returns {Promise<{shortCode: string, shortUrlPath: string}>}
 */
export const createShortUrl = async (originalUrl, options = {}) => {
    const { postId, platform } = options;
    return await callFunctionWithNaverAuth('createShortUrl', { originalUrl, postId, platform });
};
