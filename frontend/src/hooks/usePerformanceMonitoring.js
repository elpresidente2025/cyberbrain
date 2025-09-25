import { useState, useEffect, useCallback } from 'react';

export const usePerformanceMonitoring = () => {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [browserMetrics, setBrowserMetrics] = useState({});

  // 브라우저 성능 메트릭 수집
  const collectBrowserMetrics = useCallback(() => {
    if (!window.performance) {
      return {};
    }

    const navigation = performance.getEntriesByType('navigation')[0];
    const memory = performance.memory || {};
    
    return {
      pageLoad: navigation ? Math.round(navigation.loadEventEnd - navigation.fetchStart) : 0,
      domContentLoaded: navigation ? Math.round(navigation.domContentLoadedEventEnd - navigation.fetchStart) : 0,
      firstContentfulPaint: 0, // 추후 PerformanceObserver로 수집 가능
      memoryUsage: {
        used: Math.round(memory.usedJSHeapSize / 1024 / 1024) || 0, // MB
        total: Math.round(memory.totalJSHeapSize / 1024 / 1024) || 0, // MB
        limit: Math.round(memory.jsHeapSizeLimit / 1024 / 1024) || 0 // MB
      },
      connection: navigator.connection ? {
        effectiveType: navigator.connection.effectiveType,
        downlink: navigator.connection.downlink,
        rtt: navigator.connection.rtt
      } : null,
      userAgent: navigator.userAgent,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight
      },
      timestamp: Date.now()
    };
  }, []);

  // 서버 성능 메트릭 조회
  const fetchPerformanceMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // 브라우저 메트릭 수집
      const browserData = collectBrowserMetrics();
      setBrowserMetrics(browserData);

      // 서버 메트릭 조회
      const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getPerformanceMetrics', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          clientMetrics: browserData
        })
      });

      const data = await response.json();
      
      if (data.success) {
        setMetrics({
          ...data.data,
          browser: browserData
        });
      } else {
        throw new Error(data.error || '성능 메트릭 조회 실패');
      }

    } catch (err) {
      console.error('Performance metrics error:', err);
      setError(err.message);
      
      // 서버 오류 시에도 브라우저 메트릭은 표시
      setMetrics({
        browser: collectBrowserMetrics(),
        system: {
          memoryUsage: 0,
          activeUsers: 0,
          totalApiCalls: 0,
          avgResponseTime: 0,
          errorRate: 0,
          uptime: 'N/A'
        },
        apiMetrics: {
          calls: {},
          topEndpoints: []
        },
        performance: {
          responseTime: { avg: 0, min: 0, max: 0 },
          throughput: 0,
          concurrency: 0
        }
      });
    } finally {
      setLoading(false);
    }
  }, [collectBrowserMetrics]);

  // API 호출 성능 추적용 래퍼
  const trackApiCall = useCallback(async (apiCall, endpoint) => {
    const startTime = performance.now();
    let success = true;
    
    try {
      const result = await apiCall();
      return result;
    } catch (error) {
      success = false;
      throw error;
    } finally {
      const endTime = performance.now();
      const responseTime = Math.round(endTime - startTime);
      
      // 성능 로그를 위한 데이터 수집 (실제 구현 시 서버로 전송)
      console.log('API Call Performance:', {
        endpoint,
        responseTime,
        success,
        timestamp: new Date().toISOString()
      });
    }
  }, []);

  // 실시간 성능 모니터링 (자동 갱신)
  const startRealTimeMonitoring = useCallback((interval = 30000) => {
    fetchPerformanceMetrics(); // 즉시 실행
    
    const intervalId = setInterval(() => {
      fetchPerformanceMetrics();
    }, interval);

    return () => clearInterval(intervalId);
  }, [fetchPerformanceMetrics]);

  // 페이지 성능 이벤트 리스너
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        setBrowserMetrics(collectBrowserMetrics());
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [collectBrowserMetrics]);

  return {
    metrics,
    browserMetrics,
    loading,
    error,
    fetchPerformanceMetrics,
    trackApiCall,
    startRealTimeMonitoring,
    refresh: fetchPerformanceMetrics
  };
};