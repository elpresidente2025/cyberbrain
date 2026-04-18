// frontend/src/utils/electionExpressionCheck.js
// 선거법 금지 표현 프론트엔드 사전 검사
// ⚠️ 원본: functions/python/agents/common/election_rules.py — 패턴 추가/수정 시 양쪽 동기화 필요

/**
 * 단계별 금지 패턴.
 * - key: status 값 ('준비'|'현역' → STAGE_1, '예비' → STAGE_2, '후보' → STAGE_3)
 * - 각 항목: { pattern: RegExp, label: 사용자에게 보여줄 카테고리, suggestion: 대체 표현 안내 }
 */
const STAGE_1_PATTERNS = [
  // 신분 관련
  { pattern: /예비\s*후보/, label: '신분 표현', suggestion: '삭제하거나 다른 표현으로 대체' },
  { pattern: /출마\s*예정/, label: '신분 표현', suggestion: '"정치 활동 중인"' },
  { pattern: /[가-힣]+이\s*되겠습니다/, label: '신분 표현', suggestion: '삭제' },

  // 공약성 표현
  { pattern: /공약을?\s*(발표|제시|말씀)/, label: '공약성 표현', suggestion: '"정책 방향을 제안"' },
  { pattern: /공약\s*사항/, label: '공약성 표현', suggestion: '"정책 제안 사항"' },
  { pattern: /공약입니다/, label: '공약성 표현', suggestion: '"정책 방향입니다"' },
  { pattern: /[0-9]+\s*번째\s*공약/, label: '공약성 표현', suggestion: '"N번째 정책 제안"' },
  { pattern: /약속\s*드립니다/, label: '공약성 표현', suggestion: '"검토해 보겠습니다", "필요합니다"' },
  { pattern: /약속\s*드리겠습니다/, label: '공약성 표현', suggestion: '"검토해 보겠습니다"' },
  { pattern: /약속\s*하겠습니다/, label: '공약성 표현', suggestion: '"살펴보겠습니다"' },
  { pattern: /약속합니다/, label: '공약성 표현', suggestion: '"제안합니다"' },
  { pattern: /반드시\s*실현/, label: '공약성 표현', suggestion: '"실현될 수 있도록 노력"' },
  { pattern: /꼭\s*실현/, label: '공약성 표현', suggestion: '"실현될 수 있도록 노력"' },
  { pattern: /당선\s*되면/, label: '공약성 표현', suggestion: '"이 정책이 실현된다면"' },
  { pattern: /당선\s*후에?/, label: '공약성 표현', suggestion: '"향후"' },
  { pattern: /당선되어/, label: '공약성 표현', suggestion: '"힘을 모아"' },

  // ~하겠습니다 계열 (공약성 의지 표현)
  { pattern: /추진하겠습니다/, label: '공약성 표현', suggestion: '"추진이 필요합니다"' },
  { pattern: /추진할\s*것입니다/, label: '공약성 표현', suggestion: '"추진이 필요합니다"' },
  { pattern: /실현하겠습니다/, label: '공약성 표현', suggestion: '"실현이 필요합니다"' },
  { pattern: /만들겠습니다/, label: '공약성 표현', suggestion: '"만드는 방향을 제안합니다"' },
  { pattern: /해내겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /이루겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /제공하겠습니다/, label: '공약성 표현', suggestion: '"제공이 필요합니다"' },
  { pattern: /개선하겠습니다/, label: '공약성 표현', suggestion: '"개선이 필요합니다"' },
  { pattern: /확대하겠습니다/, label: '공약성 표현', suggestion: '"확대를 제안합니다"' },
  { pattern: /강화하겠습니다/, label: '공약성 표현', suggestion: '"강화가 필요합니다"' },
  { pattern: /구축하겠습니다/, label: '공약성 표현', suggestion: '"구축을 제안합니다"' },
  { pattern: /마련하겠습니다/, label: '공약성 표현', suggestion: '"마련이 필요합니다"' },
  { pattern: /지원하겠습니다/, label: '공약성 표현', suggestion: '"지원이 필요합니다"' },
  { pattern: /해결하겠습니다/, label: '공약성 표현', suggestion: '"해결이 필요합니다"' },
  { pattern: /바꾸겠습니다/, label: '공약성 표현', suggestion: '"변화가 필요합니다"' },
  { pattern: /유치하겠습니다/, label: '공약성 표현', suggestion: '"유치를 제안합니다"' },
  { pattern: /열겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /창출하겠습니다/, label: '공약성 표현', suggestion: '"창출이 필요합니다"' },
  { pattern: /완성하겠습니다/, label: '공약성 표현', suggestion: '"완성을 제안합니다"' },
  { pattern: /이끌겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /설립하겠습니다/, label: '공약성 표현', suggestion: '"설립을 제안합니다"' },
  { pattern: /활성화하겠습니다/, label: '공약성 표현', suggestion: '"활성화를 제안합니다"' },
  { pattern: /전개하겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /변화시키겠습니다/, label: '공약성 표현', suggestion: '"변화가 필요합니다"' },
  { pattern: /살려내겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /이뤄내겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /데려오겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /기여하겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /바치겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },
  { pattern: /쏟아붓겠습니다/, label: '공약성 표현', suggestion: '"필요합니다"' },

  // 지지 호소
  { pattern: /지지해?\s*주십시오/, label: '지지 호소', suggestion: '"관심 가져 주십시오"' },
  { pattern: /지지를?\s*부탁/, label: '지지 호소', suggestion: '"관심을 부탁"' },
  { pattern: /함께해?\s*주십시오/, label: '지지 호소', suggestion: '"함께 고민해 주십시오"' },
  { pattern: /선택해?\s*주십시오/, label: '지지 호소', suggestion: '"관심 가져 주십시오"' },
  { pattern: /투표해?\s*주십시오/, label: '지지 호소', suggestion: '"관심 가져 주십시오"' },
  { pattern: /한\s*표\s*부탁/, label: '지지 호소', suggestion: '삭제' },
  { pattern: /맡겨\s*주십시오/, label: '지지 호소', suggestion: '"관심 가져 주십시오"' },
  { pattern: /맡겨주십시오/, label: '지지 호소', suggestion: '"관심 가져 주십시오"' },

  // 선거 직접 언급
  { pattern: /다음\s*선거/, label: '선거 직접 언급', suggestion: '"앞으로"' },
  { pattern: /[0-9]{4}년\s*(지방)?선거/, label: '선거 직접 언급', suggestion: '삭제' },
  { pattern: /재선을?\s*위해/, label: '선거 직접 언급', suggestion: '"더 나은 지역을 위해"' },
  { pattern: /선거\s*준비/, label: '선거 직접 언급', suggestion: '"정책 연구"' },
  { pattern: /출마\s*준비/, label: '선거 직접 언급', suggestion: '"정책 연구"' },

  // 기부행위 금지
  { pattern: /상품권.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /선물.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /금품.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /현금.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /[0-9]+만\s*원\s*(지급|드리|제공)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /경품/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /사은품/, label: '기부행위 (형사)', suggestion: '삭제' },
];

const STAGE_2_PATTERNS = [
  { pattern: /투표해?\s*주십시오/, label: '본후보 전용 표현', suggestion: '"관심을 부탁드립니다"' },
  { pattern: /저를\s*선택해?\s*주십시오/, label: '본후보 전용 표현', suggestion: '"의견을 부탁드립니다"' },
  { pattern: /기호\s*[0-9]+번/, label: '본후보 전용 표현', suggestion: '삭제 (아직 기호가 없습니다)' },
];

const STAGE_3_PATTERNS = [
  { pattern: /금품/, label: '불법 표현', suggestion: '삭제' },
  { pattern: /향응/, label: '불법 표현', suggestion: '삭제' },
  { pattern: /돈을?\s*드리/, label: '불법 표현', suggestion: '삭제' },
];

/**
 * status → 적용 패턴 목록 반환
 */
function getPatternsForStatus(status) {
  const s = (status || '').trim();
  if (s === '준비' || s === '현역' || s === 'active') return STAGE_1_PATTERNS;
  if (s === '예비') return STAGE_2_PATTERNS;
  if (s === '후보') return STAGE_3_PATTERNS;
  // 알 수 없는 상태 → 가장 엄격한 STAGE_1
  return STAGE_1_PATTERNS;
}

/**
 * 텍스트에서 금지 표현을 검사한다.
 *
 * @param {string} text - 검사 대상 텍스트
 * @param {string} status - 사용자 선거 단계 ('준비'|'현역'|'예비'|'후보')
 * @returns {Array<{matched: string, label: string, suggestion: string}>} 감지된 위반 목록
 */
export function checkElectionExpressions(text, status) {
  if (!text || typeof text !== 'string') return [];

  const patterns = getPatternsForStatus(status);
  const violations = [];
  const seen = new Set();

  for (const { pattern, label, suggestion } of patterns) {
    const match = text.match(pattern);
    if (match) {
      const matched = match[0];
      if (!seen.has(matched)) {
        seen.add(matched);
        violations.push({ matched, label, suggestion });
      }
    }
  }

  return violations;
}

/**
 * 금지 표현이 있는지 여부만 빠르게 확인
 */
export function hasElectionViolations(text, status) {
  if (!text || typeof text !== 'string') return false;
  const patterns = getPatternsForStatus(status);
  return patterns.some(({ pattern }) => pattern.test(text));
}
