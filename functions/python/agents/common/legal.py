import re
import hashlib
import time
from firebase_admin import firestore

# ============================================================================
# 정책 관리 시스템
# ============================================================================

FALLBACK_POLICY = {
    "version": 0,
    "body": """[금지] 비방/모욕, 허위·추측, 차별(지역·성별·종교), 선거 지지·반대, 불법 선거정보
[원칙] 사실기반·정책중심·미래지향 톤, 출처 명시, 불확실시 의견표현""",
    "bannedKeywords": ['빨갱이', '사기꾼', '착복', '위조', '기피', '뇌물', '추행', '전과자', '도피', '체납'],
    "patterns": [],
    "hash": 'fallback'
}

# Simple in-memory cache
_policy_cache = None
_cache_expiry = 0
CACHE_TTL = 600  # 10 minutes

def get_db():
    return firestore.client()

def load_policy_from_db():
    global _policy_cache, _cache_expiry
    
    now = time.time()
    if _policy_cache and now < _cache_expiry:
        return _policy_cache

    try:
        db = get_db()
        doc = db.document('policies/LEGAL_GUARDRAIL').get()
        if not doc.exists:
            return FALLBACK_POLICY

        data = doc.to_dict() or {}
        body = data.get('body')
        version = data.get('version')

        if not isinstance(body, str) or not isinstance(version, (int, float)):
            return FALLBACK_POLICY

        policy_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]

        policy = {
            "version": version,
            "body": body,
            "bannedKeywords": data.get('bannedKeywords', FALLBACK_POLICY['bannedKeywords']),
            "patterns": data.get('patterns', FALLBACK_POLICY['patterns']),
            "hash": policy_hash
        }

        _policy_cache = policy
        _cache_expiry = now + CACHE_TTL
        return policy
    except Exception as e:
        print(f"Error loading policy: {e}")
        return FALLBACK_POLICY

def get_policy_safe():
    return load_policy_from_db()

# ============================================================================
# 법적 가이드라인
# ============================================================================

LEGAL_GUIDELINES = {
    "dangerousPatterns": {
        "absolute": {
            "expressions": ['확실히', '틀림없이', '반드시', '절대', '100%'],
            "why": '단정적 표현은 법적 리스크 높음'
        },
        "extreme": {
            "expressions": ['모든', '전부', '절대', '완전히', '아예'],
            "why": '극단적 표현은 반박 여지 제공'
        },
        "speculative": {
            "expressions": ['들었다', '카더라', '소문에', '~것 같다', '추정하건대'],
            "why": '추측성 표현은 허위사실 유포 위험'
        },
        "inflammatory": {
            "expressions": ['당연히', '말도 안 되는', '어이없는', '한심한'],
            "why": '선동적 표현은 품위 손상'
        }
    }
}

# ============================================================================
# 정책 위반 탐지 시스템
# ============================================================================

class ViolationDetector:
    @staticmethod
    def check_banned_keywords(text: str):
        policy = get_policy_safe()
        violations = []
        for keyword in policy['bannedKeywords']:
            if keyword in text:
                violations.append({'type': 'banned_keyword', 'keyword': keyword})
        return violations

    @staticmethod
    def check_dangerous_patterns(text: str):
        violations = []
        for p_type, pattern in LEGAL_GUIDELINES['dangerousPatterns'].items():
            for expr in pattern['expressions']:
                if expr in text:
                    violations.append({'type': 'dangerous_pattern', 'pattern': expr, 'category': p_type})
        return violations

    @staticmethod
    def check_fact_claims(text: str):
        violations = []
        
        # 1. Number claims
        number_claims = re.findall(r'[0-9]+%|[0-9]+명|[0-9]+건|[0-9]+억|[0-9]+조', text)
        if number_claims:
            has_source = re.search(r'\[출처:|출처:|자료:', text, re.IGNORECASE)
            if not has_source:
                violations.append({
                    'type': 'false_info_risk',
                    'severity': 'HIGH',
                    'reason': f"수치 주장 발견 ({', '.join(number_claims[:3])}) - 출처 필수 (제250조 대비)",
                    'claims': number_claims
                })

        # 2. Opponent claims
        opponent_patterns = [
            r'(상대|경쟁|타)\s*후보.*?(했습니다|했다|받았|의혹)',
            r'(상대|경쟁)\s*진영.*?(했습니다|했다|받았)',
            r'○○\s*(후보|의원).*?(했습니다|했다)'
        ]
        for pattern in opponent_patterns:
            matches = re.findall(pattern, text)
            if matches:
                 violations.append({
                    'type': 'defamation_risk',
                    'severity': 'CRITICAL',
                    'reason': '상대 후보 관련 사실 주장 - 출처·증거 필수 (제250조, 제251조)',
                    'matches': matches[:3]
                })

        # 3. Indirect defamation
        indirect_patterns = [
            r'~?(라는|라고)\s*소문',
            r'~?(라는|라고)\s*말이?\s*(있|나)',
            r'~?(라고|라는)\s*알려져',
            r'들었습니다|들은\s*바'
        ]
        for pattern in indirect_patterns:
            matches = re.findall(pattern, text)
            if matches:
                violations.append({
                    'type': 'indirect_defamation',
                    'severity': 'HIGH',
                    'reason': '간접사실 적시 - 후보자비방죄 해당 가능 (제251조)',
                    'matches': matches[:3]
                })

        return violations

    @staticmethod
    def check_bribery_risk(text: str):
        violations = []
        bribery_patterns = [
            r'상품권.*?(지급|제공|드리)',
            r'선물.*?(지급|제공|드리)',
            r'[0-9]+만\s*원\s*(지급|드리|제공)',
            r'무상\s*지급',
            r'경품|사은품'
        ]
        for pattern in bribery_patterns:
            matches = re.findall(pattern, text)
            if matches:
                violations.append({
                    'type': 'bribery_risk',
                    'severity': 'CRITICAL',
                    'reason': '기부행위 금지 위반 (제85조 6항)',
                    'matches': matches[:3]
                })
        return violations

    @staticmethod
    def assess_risk(text: str):
        k_v = ViolationDetector.check_banned_keywords(text)
        p_v = ViolationDetector.check_dangerous_patterns(text)
        f_v = ViolationDetector.check_fact_claims(text)
        b_v = ViolationDetector.check_bribery_risk(text)

        all_violations = k_v + p_v + f_v + b_v
        has_critical = any(v.get('severity') == 'CRITICAL' for v in all_violations)

        risk_level = 'LOW'
        if has_critical or len(all_violations) >= 3:
            risk_level = 'HIGH'
        elif len(all_violations) >= 1:
            risk_level = 'MEDIUM'

        return {
            'level': risk_level,
            'keywordViolations': k_v,
            'patternViolations': p_v,
            'factViolations': f_v,
            'briberyViolations': b_v,
            'totalViolations': len(all_violations)
        }

def validate_content(text: str):
    risk = ViolationDetector.assess_risk(text)
    
    if risk['level'] == 'HIGH':
        return {'valid': False, 'message': '고위험 내용 감지: 법적 검토 필요', 'violations': risk}
    if risk['level'] == 'MEDIUM':
        return {'valid': True, 'warning': '중위험 내용 감지: 표현 수정 권장', 'violations': risk}
    
    return {'valid': True, 'message': '법적 리스크 낮음', 'violations': risk}

def create_fallback_draft(topic='', category=''):
    title = f"{category or '일반'}: {topic or '제목 미정'}"
    content = f"""<h2>{title}</h2>
<p>원고 생성 중 오류가 발생하여 기본 초안을 제시합니다. 주제와 관련한 사실 확인과 출처 추가가 필요합니다.</p>
<h3>핵심 요약</h3>
<ul><li>주제: {topic or '-'}</li><li>분류: {category or '-'}</li></ul>
<p>이재명 정신에 기반한 포용적 관점에서 다시 검토하여 보완하겠습니다.</p>
<p>[출처: 직접 추가 필요]</p>"""
    
    return {
        'title': title,
        'content': content,
        'wordCount': len(content) // 2,
        'style': '이재명정신_폴백'
    }
