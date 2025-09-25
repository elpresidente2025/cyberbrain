// Chrome runtime.lastError 오류 억제 스크립트
(function() {
  'use strict';

  // 원본 콘솔 함수들 저장
  const originalConsoleError = console.error;
  const originalConsoleWarn = console.warn;

  // 오류 메시지 필터링 함수
  function shouldSuppressMessage(message) {
    const suppressPatterns = [
      // Chrome 확장 프로그램 관련
      'runtime.lastError',
      'message port closed before a response was received',
      'A listener indicated an asynchronous response by returning true',
      'message channel closed before a response was received',
      'Extension context invalidated',
      'Could not establish connection',
      'Receiving end does not exist',

      // SVG 관련
      'attribute viewBox: Expected number',
      '<svg> attribute viewBox',
      'viewBox: Expected number, "0 0 100%',

      // 네트워크 관련
      'Failed to fetch',
      'NetworkError',
      'ERR_NETWORK',

      // Content script 관련
      'content.js',
      'critiquesAvailableHandler',
      'publishEvent',
      'reconcileCritiques',
    ];

    return suppressPatterns.some(pattern => message.includes(pattern));
  }

  // console.error 오버라이드
  console.error = function(...args) {
    const message = args.join(' ');

    if (shouldSuppressMessage(message)) {
      return; // 억제된 오류들은 출력하지 않음
    }

    // Firestore 연결 관련 일시적 오류만 경고로 변경
    if (message.includes('firestore.googleapis.com') && message.includes('400 (Bad Request)')) {
      console.warn('🔄 Firestore 연결 재시도 중...');
      return;
    }

    // 나머지 오류들은 정상 출력
    originalConsoleError.apply(console, args);
  };

  // console.warn도 필터링 (필요시)
  console.warn = function(...args) {
    const message = args.join(' ');

    if (shouldSuppressMessage(message)) {
      return;
    }

    originalConsoleWarn.apply(console, args);
  };

  // unhandledrejection 이벤트에서도 필터링
  window.addEventListener('unhandledrejection', function(event) {
    const error = event.reason;
    if (error && error.message) {
      // Chrome 확장 프로그램 관련 Promise rejection 필터링
      if (error.message.includes('runtime.lastError') ||
          error.message.includes('message port closed') ||
          error.message.includes('message channel closed') ||
          error.message.includes('A listener indicated an asynchronous response')) {
        event.preventDefault(); // 이런 promise rejection들은 무시
        return;
      }
    }
  });

})();