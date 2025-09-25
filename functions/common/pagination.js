'use strict';

/**
 * 커서 토큰 생성
 */
exports.makeCursorToken = (timestamp, id) => {
  if (!timestamp || !id) return null;
  
  try {
    const data = {
      timestamp: timestamp.toDate ? timestamp.toDate().getTime() : timestamp,
      id: id
    };
    return Buffer.from(JSON.stringify(data)).toString('base64');
  } catch (error) {
    console.warn('커서 토큰 생성 실패:', error);
    return null;
  }
};

/**
 * 커서 토큰 파싱
 */
exports.parseCursorToken = (token) => {
  if (!token) return null;
  
  try {
    const decoded = Buffer.from(token, 'base64').toString('utf8');
    const data = JSON.parse(decoded);
    
    return {
      timestamp: new Date(data.timestamp),
      id: data.id
    };
  } catch (error) {
    console.warn('커서 토큰 파싱 실패:', error);
    return null;
  }
};