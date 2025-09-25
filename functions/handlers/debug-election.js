/**
 * functions/handlers/debug-election.js
 * 선거일정 디버깅 전용 핸들러
 */

const { onCall } = require('firebase-functions/v2/https');

/**
 * 간단한 선거일정 디버깅
 */
const debugElection = onCall({ 
  region: 'asia-northeast3',
  cors: true 
}, async (request) => {
  try {
    console.log('🔍 디버깅 시작');
    
    // 1. 기본 폴백 데이터 테스트
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    
    const testElections = [
      {
        date: '2026-06-03',
        name: '제9회 전국동시지방선거',
        type: 'LOCAL_GOVERNMENT'
      },
      {
        date: '2028-04-12',
        name: '제23대 국회의원선거', 
        type: 'NATIONAL_ASSEMBLY'
      }
    ];
    
    console.log('📅 오늘:', todayStr);
    console.log('🗳️ 테스트 선거 목록:');
    testElections.forEach(election => {
      const isUpcoming = election.date >= todayStr;
      console.log(`  - ${election.name}: ${election.date} (미래: ${isUpcoming})`);
    });
    
    const upcomingElections = testElections.filter(e => e.date >= todayStr);
    const nextElection = upcomingElections.length > 0 ? upcomingElections[0] : null;
    
    console.log('🎯 다음 선거:', nextElection?.name || 'null');
    
    return {
      success: true,
      debug: {
        today: todayStr,
        totalElections: testElections.length,
        upcomingElections: upcomingElections.length,
        nextElection: nextElection,
        allElections: testElections
      },
      message: '디버깅 완료'
    };
    
  } catch (error) {
    console.error('❌ 디버깅 오류:', error);
    return {
      success: false,
      error: error.message,
      stack: error.stack
    };
  }
});

module.exports = {
  debugElection
};