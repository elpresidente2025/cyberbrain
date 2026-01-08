const fs = require('fs');
const path = 'functions/prompts/guidelines/legal.js';

let content = fs.readFileSync(path, 'utf8');

const missingReplacements = `
      '지지를 부탁': '관심을 부탁',
      '지지 부탁': '관심 부탁',
      '지지가 필요': '관심이 필요',`;

const insertPoint = "'성원 부탁': '관심 부탁',";

if (content.includes(insertPoint) && !content.includes("'지지를 부탁'")) {
    content = content.replace(insertPoint, insertPoint + missingReplacements);
    fs.writeFileSync(path, content, 'utf8');
    console.log('✅ legal.js: 남은 지지 표현 추가 완료');
} else {
    console.log('⚠️ 삽입 실패');
}
