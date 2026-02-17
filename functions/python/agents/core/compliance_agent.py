# functions/python/agents/core/compliance_agent.py
# 콘텐츠 준법 검사 에이전트 (Node.js compliance-agent.js 완전 이식)

import logging
import re
import json
from typing import Dict, Any, List, Optional, Tuple

from ..base_agent import Agent
from ..common.fact_guard import validate_with_llm, build_fact_allowlist
from ..common.framing_rules import OVERRIDE_KEYWORDS, HIGH_RISK_KEYWORDS, POLITICAL_FRAMES
from ..common.election_rules import get_election_stage, validate_election_content, sanitize_election_content

logger = logging.getLogger(__name__)


class ComplianceAgent(Agent):
    def __init__(self, name: str = 'ComplianceAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = (options or {}).get('modelName', DEFAULT_MODEL)
        self._client = get_client()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compliance checking and sanitization.
        """
        # Defensive check: Input must be a dict
        if not isinstance(context, dict):
            logger.error(f"ComplianceAgent received invalid context type: {type(context)}")
            # Return empty/safe result if context is unusable
            return {'compliancePassed': False, 'issues': [{'type': 'SYSTEM_ERROR', 'message': 'Invalid context type'}]}

        content = context.get('optimizedContent') or context.get('content') or ''
        title = context.get('title', '')

        # userProfile이 dict인지 확인 (list로 전달되는 경우 방어)
        user_profile = context.get('userProfile', {})
        if not isinstance(user_profile, dict):
            user_profile = {}

        status = context.get('status') or user_profile.get('status', 'active')
        author_name = context.get('authorName') or user_profile.get('name', '')

        print(f"🔍 [ComplianceAgent] 검수 시작 - 상태: {status}, 저자: {author_name}")

        # 1. Fact Check
        source_texts = []
        if context.get('references'):
            source_texts.extend(context['references'])
        if context.get('background'):
            source_texts.append(context['background'])
        if context.get('instructions'):
            source_texts.append(context['instructions'])
        if context.get('newsContext'):
            source_texts.append(context['newsContext'])

        # Build allowlist from sources
        fact_allowlist = build_fact_allowlist(source_texts)

        # Validate content against allowlist
        fact_result = await validate_with_llm(
            content,
            fact_allowlist,
            options={'modelName': self.model_name}
        )
        if not isinstance(fact_result, dict):
             fact_result = {'passed': True} # Defensive fallback

        # 2. Medical/Diagnostic Neutralization
        neutralized_content, medical_fixes = self.neutralize_medical_content(content)

        # 3. Political Risk Monitor
        risk_report = await self.monitor_political_risk(neutralized_content)
        # Defensive check
        if not isinstance(risk_report, dict):
             risk_report = {'riskLevel': 'UNKNOWN', 'reason': 'System returned invalid format'}

        # 4. Election Law Validation (정규식 기반 - 새로 구현)
        election_issues = self.validate_election_laws(neutralized_content, status)

        # 5. Title Compliance
        title_issues = self.verify_title_compliance(title, status)

        # 6. 🆕 저자명 사용 횟수 검증
        author_name_issues = self.validate_author_name_usage(neutralized_content, author_name)

        # 7. 🆕 본론 미니결론 패턴 검증
        mini_conclusion_issues = self.validate_no_mini_conclusions(neutralized_content)

        # Aggregate Issues
        issues = []

        # Fact issues
        if not fact_result.get('passed', True):
            for token in fact_result.get('unsupported', []):
                issues.append({
                    'type': 'FACT_CHECK_FAIL',
                    'severity': 'high',
                    'message': f'출처 미확인 수치: {token}',
                    'location': 'content'
                })

        # Medical fixes as issues (already fixed but reported)
        for fix in medical_fixes:
            issues.append({
                'type': 'MEDICAL_TERM_FIXED',
                'severity': 'low',
                'message': f'의료법 위반 소지 표현 수정: {fix["original"]} -> {fix["replacement"]}',
                'location': 'content'
            })

        # Political risks
        if risk_report.get('riskLevel', 'LOW') not in ['LOW', 'UNKNOWN']:
            issues.append({
                'type': 'POLITICAL_RISK',
                'severity': 'high' if risk_report.get('riskLevel') in ['HIGH', 'CRITICAL'] else 'medium',
                'message': f"정치적 리스크 감지: {risk_report.get('reason')}",
                'suggestion': risk_report.get('suggestion'),
                'location': 'content'
            })

        # Election issues
        issues.extend(election_issues)

        # Title issues
        issues.extend(title_issues)

        # 🆕 저자명 이슈
        issues.extend(author_name_issues)

        # 🆕 미니결론 이슈
        issues.extend(mini_conclusion_issues)

        # Critical 이슈 개수 계산
        # Ensure i is a dict
        critical_count = len([i for i in issues if isinstance(i, dict) and i.get('severity') == 'critical'])
        high_count = len([i for i in issues if isinstance(i, dict) and i.get('severity') == 'high'])

        print(f"📊 [ComplianceAgent] 검수 완료 - 이슈: critical={critical_count}, high={high_count}, total={len(issues)}")

        return {
            'content': neutralized_content,
            'title': title,
            'issues': issues,
            'factCheck': fact_result,
            'riskReport': risk_report,
            'compliancePassed': critical_count == 0
        }

    def neutralize_medical_content(self, content: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Replace medical diagnostic terms with non-medical alternatives.
        """
        fixes = []

        # Regex mappings for medical terms to neutralize
        replacements = [
            (r'치료하다', '돕다'),
            (r'완치되다', '극복하다'),
            (r'진료하다', '상담하다'),
            (r'처방하다', '제안하다'),
            (r'예방하다', '대처하다'),
            (r'효과가 입증된', '도움이 되는'),
            (r'전문적인 치료', '세심한 케어')
        ]

        new_content = content
        for pattern, replacement in replacements:
            for match in re.finditer(pattern, new_content):
                fixes.append({
                    'original': match.group(0),
                    'replacement': replacement
                })
            new_content = re.sub(pattern, replacement, new_content)

        return new_content, fixes

    async def monitor_political_risk(self, content: str) -> Dict[str, Any]:
        """
        Check for political risks using LLM (framing analysis).
        """
        from ..common.gemini_client import generate_content_async

        if not self._client:
            return {'riskLevel': 'UNKNOWN', 'reason': 'Model not available'}

        prompt = f"""당신은 정무적 리스크 관리 전문가입니다. 다음 정치인의 글에서 '자기 파괴적'이거나 '불필요한 논란'을 유발할 수 있는 표현을 찾아내세요.

[분석 대상 텍스트]
{content[:2000]}

[체크리스트]
1. 상대 진영(정부/여당/야당)에 대한 감정적 비난이나 막말이 있는가?
2. 선거법 위반 소지(사전 선거운동, 확정되지 않은 공약 남발)가 있는가?
3. 국민 정서를 자극할 수 있는 오만한 표현이나 자기 비하가 있는가?
4. "실패했다", "망했다" 등 극단적인 부정 단어가 있는가?

반드시 다음 JSON 형식으로 응답:
{{
  "riskLevel": "CRITICAL|HIGH|MEDIUM|LOW",
  "reason": "발견된 위험 요소 설명 (없으면 공란)",
  "suggestion": "수정 제안 (없으면 공란)"
}}"""
        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                response_mime_type='application/json'
            )
            text = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', response_text).strip()
            parsed = json.loads(text)
            
            # Defense against LLM returning a list instead of a dict
            if isinstance(parsed, list):
                if parsed and isinstance(parsed[0], dict):
                    return parsed[0]
                return {'riskLevel': 'UNKNOWN', 'reason': 'LLM returned a list, expected dict'}
            
            if not isinstance(parsed, dict):
                return {'riskLevel': 'UNKNOWN', 'reason': 'LLM returned invalid type'}
                
            return parsed
            
        except Exception as e:
            logger.warning(f"[{self.name}] Risk monitor failed: {e}")
            return {'riskLevel': 'UNKNOWN', 'reason': str(e)}

    def validate_election_laws(self, content: str, status: str) -> List[Dict[str, Any]]:
        """
        선거법 위반 표현 검출 (정규식 기반)
        """
        issues = []

        # 새로운 validate_election_content 함수 사용
        validation_result = validate_election_content(content, status)

        if not validation_result['passed']:
            for violation in validation_result['violations']:
                # severity 매핑
                severity = violation.get('severity', 'high')

                # 매치된 표현들 (최대 3개만 표시)
                matches_preview = ', '.join(violation['matches'][:3])
                if len(violation['matches']) > 3:
                    matches_preview += f' 외 {len(violation["matches"]) - 3}건'

                issues.append({
                    'type': 'ELECTION_LAW_VIOLATION',
                    'severity': severity,
                    'message': f'선거법 위반 [{violation["category"]}]: "{matches_preview}"',
                    'category': violation['category'],
                    'count': violation['count'],
                    'location': 'content'
                })

        print(f"⚖️ [ComplianceAgent] 선거법 검수: {len(issues)}건 위반 감지")

        return issues

    def verify_title_compliance(self, title: str, status: str) -> List[Dict[str, Any]]:
        """
        제목 준법 검사
        """
        issues = []

        # 제목에서도 선거법 검증
        validation_result = validate_election_content(title, status)
        if not validation_result['passed']:
            for violation in validation_result['violations']:
                issues.append({
                    'type': 'ELECTION_LAW_VIOLATION',
                    'severity': violation.get('severity', 'high'),
                    'message': f'제목 선거법 위반: "{", ".join(violation["matches"][:2])}"',
                    'location': 'title'
                })

        # 제목 길이 검사
        if len(title) > 35:
            issues.append({
                'type': 'TITLE_LENGTH',
                'severity': 'medium',
                'message': f'제목이 너무 깁니다 ({len(title)}자 > 35자)',
                'location': 'title'
            })

        return issues

    def validate_author_name_usage(self, content: str, author_name: str) -> List[Dict[str, Any]]:
        """
        🆕 저자명 사용 횟수 검증

        규칙: 저자 이름은 서론 1회 + 결론 1회 = 총 2회만 허용
        """
        issues = []

        if not author_name or len(author_name) < 2:
            return issues

        # HTML 태그 제거 후 카운트
        plain_content = re.sub(r'<[^>]*>', ' ', content)

        # 저자명 등장 횟수
        name_count = plain_content.count(author_name)

        # 허용 횟수: 서론 1회 + 결론 1회 = 2회
        # 여유를 두어 3회까지는 warning, 4회 이상은 high
        if name_count > 4:
            issues.append({
                'type': 'AUTHOR_NAME_OVERUSE',
                'severity': 'high',
                'message': f'저자명 "{author_name}" 과다 사용: {name_count}회 (권장: 2회 이내)',
                'count': name_count,
                'location': 'content'
            })
        elif name_count > 2:
            issues.append({
                'type': 'AUTHOR_NAME_OVERUSE',
                'severity': 'medium',
                'message': f'저자명 "{author_name}" 다소 많음: {name_count}회 (권장: 서론/결론 각 1회)',
                'count': name_count,
                'location': 'content'
            })

        if name_count > 2:
            print(f"👤 [ComplianceAgent] 저자명 사용: {name_count}회 (권장 2회)")

        return issues

    def validate_no_mini_conclusions(self, content: str) -> List[Dict[str, Any]]:
        """
        🆕 본론 섹션별 미니결론(요약/다짐) 패턴 검증

        규칙: 본론(h2) 섹션 내에서 결론성 표현 사용 금지
        - "앞으로 ~하겠습니다"
        - "기대됩니다"
        - "노력하겠습니다"
        등의 맺음말은 오직 마지막 [결론] 섹션에만 작성
        """
        issues = []

        # h2 태그로 섹션 분리
        sections = re.split(r'(<h2[^>]*>.*?</h2>)', content, flags=re.IGNORECASE | re.DOTALL)

        # 미니결론 패턴 (본론에서 사용 금지)
        mini_conclusion_patterns = [
            r'앞으로\s+[가-힣]+하겠습니다',
            r'기대됩니다',
            r'기대가\s+됩니다',
            r'노력하겠습니다',
            r'최선을\s+다하겠습니다',
            r'약속드립니다',
            r'함께\s+만들어\s+가겠습니다',
            r'실현하겠습니다',
            r'힘쓰겠습니다',
        ]

        # 마지막 h2 이전 섹션들만 검사 (결론 제외)
        h2_indices = [i for i, s in enumerate(sections) if re.match(r'<h2', s, re.IGNORECASE)]

        if len(h2_indices) < 2:
            return issues  # h2가 2개 미만이면 검사 불필요

        # 마지막 h2 이전까지의 본론 섹션들만 검사
        last_h2_idx = h2_indices[-1]

        for i, section in enumerate(sections):
            # h2 태그 자체는 스킵
            if re.match(r'<h2', section, re.IGNORECASE):
                continue

            # 마지막 h2 이후 섹션(결론)은 스킵
            if i > last_h2_idx:
                continue

            # 도입부(첫 h2 이전)도 스킵
            if len(h2_indices) > 0 and i < h2_indices[0]:
                continue

            # 본론 섹션 내 미니결론 패턴 검사
            for pattern in mini_conclusion_patterns:
                matches = re.findall(pattern, section, re.IGNORECASE)
                if matches:
                    issues.append({
                        'type': 'MINI_CONCLUSION_IN_BODY',
                        'severity': 'medium',
                        'message': f'본론 섹션 내 미니결론 표현: "{matches[0]}" (결론부로 이동 권장)',
                        'pattern': pattern,
                        'location': 'content'
                    })

        if issues:
            print(f"📝 [ComplianceAgent] 본론 미니결론: {len(issues)}건 감지")

        return issues
