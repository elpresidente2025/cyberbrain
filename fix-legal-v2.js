const fs = require('fs');
const path = 'functions/prompts/guidelines/legal.js';

let content = fs.readFileSync(path, 'utf8');

const replacementsToAdd = `
      // 🔧 추가 공약성 표현 치환
      '만들어나가겠습니다': '을 위해 노력 중입니다',
      '이끌어나가겠습니다': '을 위해 노력 중입니다',
      '노력하겠습니다': '을 위해 노력 중입니다',
      '최선을 다하겠습니다': '을 위해 노력 중입니다',
      '모든 역량을 다하겠습니다': '을 위해 노력 중입니다',
      '역량을 다하겠습니다': '을 위해 노력 중입니다',
      '쏟아붓겠습니다': '을 위해 노력 중입니다',
      '헌신하겠습니다': '을 위해 노력 중입니다',
      // '약속' 패턴 추가
      '약속드립니다': '을 제안합니다',
      '지키겠습니다': '을 위해 노력하겠습니다',
      // 🔧 지지 호소 표현 추가
      '지지와 성원을 부탁': '관심을 부탁',
      '지지와 성원': '관심과 응원',
      '성원을 부탁': '관심을 부탁',
      '성원 부탁': '관심 부탁',
      '지지를 부탁': '관심을 부탁',
      '지지 부탁': '관심 부탁',
      '지지가 필요': '관심이 필요',`;

// 삽입 지점 (이전에 추가되지 않았는지 확인)
const insertPoint = "'변화시키겠습니다': '이 필요합니다',";
if (content.includes(insertPoint) && !content.includes("'지지와 성원을 부탁'")) {
    content = content.replace(insertPoint, insertPoint + replacementsToAdd);
    fs.writeFileSync(path, content, 'utf8');
    console.log('✅ legal.js: 지지 호소 필터 추가 완료');
} else {
    console.log('⚠️ 이미 추가되었거나 삽입 지점이 다릅니다.');
}
