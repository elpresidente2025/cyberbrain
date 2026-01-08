const fs = require('fs');
const path = 'functions/services/agents/orchestrator.js';

let content = fs.readFileSync(path, 'utf8');

// 1. Import 추가
if (!content.includes("require('./title-agent')")) {
    content = content.replace(
        "const { WriterAgent } = require('./writer-agent');",
        "const { WriterAgent } = require('./writer-agent');\nconst { TitleAgent } = require('./title-agent');"
    );
}

// 2. Standard Pipeline 추가
if (!content.includes("{ agent: TitleAgent, name: 'TitleAgent', required: true }")) {
    content = content.replace(
        "{ agent: WriterAgent, name: 'WriterAgent', required: true },",
        "{ agent: WriterAgent, name: 'WriterAgent', required: true },\n    { agent: TitleAgent, name: 'TitleAgent', required: true },"
    );
}

// 3. enrichContext 추가 (TitleAgent는 WriterAgent의 content가 필요)
// enrichContext 메서드 내 switch case 추가
const enrichCase = `
      case 'TitleAgent':
        // TitleAgent는 WriterAgent 결과(content) 필요 (previousResults에 포함됨)
        break;
`;

if (!content.includes("case 'TitleAgent':")) {
    content = content.replace(
        "case 'WriterAgent':",
        `case 'TitleAgent':
        // TitleAgent는 WriterAgent 결과 필요 (previousResults에 포함됨)
        break;

      case 'WriterAgent':`
    );
}

// 4. buildFinalResult 수정: TitleAgent 결과를 우선적으로 사용
// 기존 로직: SEO -> Compliance -> Writer
// 변경 로직: SEO -> Compliance -> Title -> Writer
// (단, 검수/SEO 과정에서 제목이 변경되면 그게 우선이어야 함. TitleAgent는 '초안' 제목을 만듦)
// 하지만 TitleAgent가 가장 전문적이므로, Compliance나 SEO가 TitleAgent의 결과를 덮어쓰지 않고 '계승'해야 함.

// buildFinalResult에서 finalTitle 설정 부분 수정
// 기존:
//     } else if (this.results.ComplianceAgent?.success) {
//       finalContent = this.results.ComplianceAgent.data.content;
//       // 🏷️ ComplianceAgent도 제목을 반환하므로 우선 사용 (EditorAgent로 수정된 제목 포함)
//       finalTitle = this.results.ComplianceAgent.data.title || this.results.WriterAgent?.data?.title || null;

const titleLogicOld = "finalTitle = this.results.ComplianceAgent.data.title || this.results.WriterAgent?.data?.title || null;";
const titleLogicNew = "finalTitle = this.results.ComplianceAgent.data.title || this.results.TitleAgent?.data?.title || this.results.WriterAgent?.data?.title || null;";

if (content.includes(titleLogicOld)) {
    content = content.replace(titleLogicOld, titleLogicNew);
}

// WriterAgent만 성공했을 경우의 fallback도 수정
const writerFallbackOld = "finalTitle = this.results.WriterAgent.data.title;";
const writerFallbackNew = "finalTitle = this.results.TitleAgent?.data?.title || this.results.WriterAgent.data.title;";

if (content.includes(writerFallbackOld)) {
    content = content.replace(writerFallbackOld, writerFallbackNew);
}

fs.writeFileSync(path, content, 'utf8');
console.log('✅ Orchestrator: TitleAgent 통합 완료');
