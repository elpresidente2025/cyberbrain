// deploy.js - 전자두뇌비서관 Firebase 전용 배포 스크립트
const { execSync } = require('child_process');
const path = require('path');

function runCommand(command, cwd = process.cwd()) {
  console.log(`🔧 실행: ${command}`);
  try {
    execSync(command, { 
      cwd, 
      stdio: 'inherit',
      encoding: 'utf8'
    });
  } catch (error) {
    console.error(`❌ 명령어 실패: ${command}`);
    throw error;
  }
}

function maybeSetupFunctionsConfig() {
  const geminiKey = process.env.GEMINI_API_KEY || '';
  const electionMode = process.env.ELECTION_MODE || 'off';
  if (!geminiKey) {
    console.log('⚠️  GEMINI_API_KEY가 환경변수에 없습니다. (Functions Config 자동 세팅 생략)');
    return;
  }
  console.log('🔐 Firebase Functions Config 세팅 중(gemini.key, election.mode)…');
  // ⚠️ 명령행 히스토리에 값이 노출될 수 있습니다. 민감하면 수동으로 설정하세요.
  runCommand(`firebase functions:config:set gemini.key="${geminiKey}" election.mode="${electionMode}"`);
}

async function deploy() {
  const mode = process.argv[2] || 'hosting-only';
  
  console.log('🚀 전자두뇌비서관 Firebase 배포 시작...');
  console.log(`📋 배포 모드: ${mode}`);
  
  try {
    // 0. (선택) Functions Config 세팅
    maybeSetupFunctionsConfig();

    // 1. 프론트엔드 빌드
    console.log('\n📦 프론트엔드 빌드 중...');
    runCommand('npm run build', './frontend');
    
    // 2. 배포 방식 선택
    if (mode === 'hosting-only') {
      console.log('\n🌐 Firebase Hosting 배포 중...');
      runCommand('firebase deploy --only hosting');
      
      console.log('\n💡 백엔드 정보:');
      console.log('   ✅ Firebase Functions 사용 중');
      console.log('   📡 Functions 업데이트: npm run deploy:functions');
      
    } else if (mode === 'full') {
      console.log('\n☁️ Firebase 전체 배포 중...');
      runCommand('firebase deploy');
      
    } else if (mode === 'functions-only') {
      console.log('\n⚡ Firebase Functions 배포 중...');
      runCommand('firebase deploy --only functions');
      
    } else if (mode === 'both') {
      console.log('\n⚡ Firebase Functions 배포 중...');
      runCommand('firebase deploy --only functions');
      console.log('\n🌐 Firebase Hosting 배포 중...');
      runCommand('firebase deploy --only hosting');
    }
    
    console.log('\n✅ 배포 완료!');
    console.log('\n🔗 확인 링크:');
    console.log('   ⚡ Functions: Firebase Console에서 확인');
    console.log('   📊 Firebase 콘솔: https://console.firebase.google.com');
    
  } catch (error) {
    console.error('\n❌ 배포 실패:', error.message);
    process.exit(1);
  }
}

// 사용법 출력
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log(`
🚀 전자두뇌비서관 Firebase 배포 스크립트

사용법:
  node deploy.js [모드]

모드:
  hosting-only   - 프론트엔드만 Firebase에 배포 (기본값)
  functions-only - Firebase Functions만 배포
  full           - 프론트엔드 + Functions 모두 배포
  both           - Functions 먼저, 그 다음 Hosting 순차 배포

예시:
  node deploy.js                 # 호스팅만 배포
  node deploy.js hosting-only    # 호스팅만 배포  
  node deploy.js functions-only  # Functions만 배포
  node deploy.js full            # 전체 배포
  node deploy.js both            # 순차 배포
  node deploy.js --help          # 도움말

환경변수(선택):
  GEMINI_API_KEY   - Gemini API Key (있으면 functions:config 자동 세팅)
  ELECTION_MODE    - on/off (민감기간 보수 모드)
`);
  process.exit(0);
}

deploy();
