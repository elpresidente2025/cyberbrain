
import re
import json
import logging
from typing import Dict, Any, List, Set, Optional

logger = logging.getLogger(__name__)

SINGLE_DIGIT_VALUES = {'1', '2', '3', '4', '5', '6', '7', '8', '9'}
URL_PATTERN = r'https?:\/\/\S+'

COMMON_KNOWLEDGE = {
    '2024', '2025', '2026', '2027', '2028',
    '5100만', '5000만', '1300만', '950만', '1000만',
    '340만', '330만', '300만', '290만', '250만', '240만', '150만', '145만',
    '100%', '50%', '0%',
    '1위', '2위', '3위', '10위', '10위권', '20위권', '100위권',
    '1년', '2년', '3년', '5년', '10년',
    '1개월', '3개월', '6개월', '12개월',
    '2배', '3배', '10배', '100배',
    '절반', '1/2', '1/3', '1/4'
}

NUMBER_UNIT_TOKENS = [
    '%', '퍼센트', '프로', '%p', 'p', 'pt', '포인트',
    '명', '인', '개', '개사', '개소', '곳', '건', '위', '대', '호',
    '가구', '세대', '회', '차',
    '년', '월', '일', '주', '시', '분', '초',
    'km', 'kg', '㎡', '평', 'm', 'cm', 'mm',
    '원', '만원', '억원', '조원', '조', '억', '만', '천',
    '배'
]

# Sort by length desc to match longest first (e.g., '만원' before '원')
NUMBER_UNIT_TOKENS.sort(key=len, reverse=True)
UNIT_PATTERN = '|'.join(map(re.escape, NUMBER_UNIT_TOKENS))

NUMBER_TOKEN_REGEX = re.compile(
    rf'\d+(?:,\d{{3}})*(?:\.\d+)?\s*(?:{UNIT_PATTERN})?',
    re.IGNORECASE
)

KOREAN_DIGIT_MAP = {
    '영': 0, '공': 0, '零': 0,
    '일': 1, '하나': 1, '한': 1, '壹': 1,
    '이': 2, '둘': 2, '두': 2, '貳': 2,
    '삼': 3, '셋': 3, '세': 3, '參': 3,
    '사': 4, '넷': 4, '네': 4, '四': 4,
    '오': 5, '다섯': 5, '五': 5,
    '육': 6, '여섯': 6, '六': 6,
    '칠': 7, '일곱': 7, '七': 7,
    '팔': 8, '여덟': 8, '八': 8,
    '구': 9, '아홉': 9, '九': 9,
    '십': 10, '열': 10, '十': 10,
    '백': 100, '百': 100,
    '천': 1000, '千': 1000,
    '만': 10000, '萬': 10000,
    '억': 100000000, '億': 100000000,
    '조': 1000000000000, '兆': 1000000000000
}

RISK_LEVELS = {
    'ALLOWED': 0,
    'DERIVED': 1,
    'COMMON': 1,
    'GOAL': 2,
    'UNKNOWN': 2,
    'HALLUCINATION': 3
}

def normalize_numeric_token(token: str) -> str:
    if not token:
        return ''
    normalized = str(token).strip()
    if not normalized:
        return ''
    normalized = re.sub(r'\s+', '', normalized)
    normalized = normalized.replace(',', '')
    normalized = normalized.replace('％', '%')
    normalized = re.sub(r'퍼센트|프로', '%', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'포인트', 'p', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'%p', 'p', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'pt$', 'p', normalized, flags=re.IGNORECASE)
    return normalized

def split_numeric_token(token: str):
    normalized = normalize_numeric_token(token)
    if not normalized:
        return '', ''
    match = re.match(r'^(\d+(?:\.\d+)?)(.*)$', normalized)
    if not match:
        return '', ''
    return match.group(1), match.group(2) or ''

def normalize_numeric_spacing(text: str) -> str:
    if not text:
        return ''
    normalized = str(text)
    normalized = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', normalized)
    normalized = re.sub(r'(\d)\s*,\s*(\d)', r'\1,\2', normalized)
    # This regex needs careful construction from unit tokens
    units_regex = '|'.join(map(re.escape, ['%', '퍼센트', '포인트', '%p', 'p', 'pt', '명', '개', '곳', '가구', '억', '조', '원', '만원', '억원', '조원', 'km', 'kg', 'm', 'cm', 'mm', '배']))
    normalized = re.sub(rf'(\d)\s*({units_regex})', r'\1\2', normalized, flags=re.IGNORECASE)
    return normalized

def convert_korean_to_number(korean_str: str) -> str:
    if not korean_str:
        return korean_str

    total = 0
    current = 0
    big_unit = 0

    chars = list(korean_str)
    
    for char in chars:
        value = KOREAN_DIGIT_MAP.get(char)
        if value is None:
            continue
            
        if value >= 100000000: # 억
             if current == 0: current = 1
             big_unit += (current + (0 if big_unit > 0 else total)) * value
             total = 0
             current = 0
        elif value >= 10000: # 만
             if current == 0: current = 1
             total += current * value
             current = 0
        elif value >= 10: # 십, 백, 천
             if current == 0: current = 1
             current *= value
        else: # 1-9
             current = current * 10 + value
             
    total += current + big_unit
    
    if total == 0: return korean_str
    return str(total)

def normalize_korean_number(text: str) -> str:
    if not text: return text
    
    # Simple pattern for continuous korean numbers
    # Note: Regex for Korean numbers is complex, simplifying here to match JS logic concept
    complex_pattern = r'([일이삼사오육칠팔구십백천만억조]+)'
    
    def replacer(match):
        return convert_korean_to_number(match.group(0))
        
    return re.sub(complex_pattern, replacer, str(text))

def extract_numeric_tokens(text: str) -> List[str]:
    if not text:
        return []
        
    normalized_text = normalize_korean_number(text)
    
    plain_text = normalize_numeric_spacing(str(normalized_text))
    plain_text = re.sub(URL_PATTERN, ' ', plain_text)
    plain_text = re.sub(r'<[^>]*>', ' ', plain_text)
    
    matches = NUMBER_TOKEN_REGEX.findall(plain_text)
    tokens = [normalize_numeric_token(m) for m in matches]
    return list(set(filter(None, tokens)))

def is_within_tolerance(value: str, allowed_values: List[str], tolerance: float = 0.05) -> bool:
    try:
        num = float(value)
    except ValueError:
        return False
        
    for allowed in allowed_values:
        try:
            allowed_num = float(allowed)
            if allowed_num == 0: continue
            
            diff = abs(num - allowed_num) / abs(allowed_num)
            if diff <= tolerance:
                return True
        except ValueError:
            continue
            
    return False

def build_derived_values(allowlist: Dict[str, Any]) -> Dict[str, Any]:
    tokens = allowlist.get('tokens', [])
    derived_sums = set()
    derived_diffs = set()
    derived_ratios = set()
    
    numbers = []
    for token in tokens:
        value, unit = split_numeric_token(token)
        try:
            num = float(value)
            if num > 0:
                numbers.append({'num': num, 'unit': unit, 'original': token})
        except ValueError:
            pass
            
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            a = numbers[i]
            b = numbers[j]
            
            if a['unit'] == b['unit']:
                s = a['num'] + b['num']
                d = abs(a['num'] - b['num'])
                
                # Check if integer to avoid .0
                s_str = str(int(s)) if s.is_integer() else str(s)
                d_str = str(int(d)) if d.is_integer() else str(d)
                
                derived_sums.add(f"{s_str}{a['unit']}")
                if d > 0:
                    derived_diffs.add(f"{d_str}{a['unit']}")
            
            if b['num'] != 0:
                ratio = (a['num'] - b['num']) / b['num'] * 100
                if abs(ratio) <= 1000:
                    derived_ratios.add(f"{round(ratio)}%")
                    derived_ratios.add(f"{abs(round(ratio))}%")
            
            if a['num'] != 0:
                ratio = (b['num'] - a['num']) / a['num'] * 100
                if abs(ratio) <= 1000:
                    derived_ratios.add(f"{round(ratio)}%")
                    derived_ratios.add(f"{abs(round(ratio))}%")
                    
    return {
        'sums': list(derived_sums),
        'diffs': list(derived_diffs),
        'ratios': list(derived_ratios),
        'all': list(derived_sums) + list(derived_diffs) + list(derived_ratios)
    }

def build_fact_allowlist(source_texts: List[str]) -> Dict[str, Any]:
    tokens = set()
    values = set()
    
    for source_text in source_texts:
        if not source_text: continue
        extracted = extract_numeric_tokens(source_text)
        for token in extracted:
            tokens.add(token)
            val, unit = split_numeric_token(token)
            if val and not unit:
                values.add(val)
                
    base_allowlist = {
        'tokens': list(tokens),
        'values': list(values)
    }
    
    derived = build_derived_values(base_allowlist)
    
    return {
        'tokens': list(tokens),
        'values': list(values),
        'derived': derived['all'],
        '_meta': {
            'sourceCount': len(source_texts),
            'tokenCount': len(tokens),
            'derivedCount': len(derived['all'])
        }
    }

def find_unsupported_numeric_tokens(content: str, allowlist: Dict[str, Any] = {}, options: Dict[str, Any] = {}) -> Dict[str, Any]:
    tolerance_enabled = options.get('toleranceEnabled', True)
    tolerance = options.get('tolerance', 0.05)
    common_knowledge_enabled = options.get('commonKnowledgeEnabled', True)
    
    extracted = extract_numeric_tokens(content)
    allowed_tokens = set(allowlist.get('tokens', []))
    allowed_values = set(allowlist.get('values', []))
    derived_tokens = set(allowlist.get('derived', []))
    
    results = []
    
    for token in extracted:
        val, unit = split_numeric_token(token)
        if not val: continue
        
        # 1. Single digit exception
        if not unit and val in SINGLE_DIGIT_VALUES:
            results.append({'token': token, 'status': 'ALLOWED', 'reason': '단일 숫자 예외'})
            continue
            
        # 2. Direct match
        if token in allowed_tokens:
            results.append({'token': token, 'status': 'ALLOWED', 'reason': '출처 확인'})
            continue
        if not unit and val in allowed_values:
             results.append({'token': token, 'status': 'ALLOWED', 'reason': '출처 확인 (값)'})
             continue
             
        # 3. Derived match
        if token in derived_tokens:
            results.append({'token': token, 'status': 'DERIVED', 'reason': '계산된 수치'})
            continue
            
        # 4. Common knowledge
        if common_knowledge_enabled and token in COMMON_KNOWLEDGE:
            results.append({'token': token, 'status': 'COMMON', 'reason': '일반 상식'})
            continue
            
        # 5. Tolerance
        if tolerance_enabled and unit:
            all_values = []
            for t in list(allowed_tokens) + list(derived_tokens):
                v, u = split_numeric_token(t)
                if u == unit:
                    all_values.append(v)
            
            if is_within_tolerance(val, all_values, tolerance):
                results.append({'token': token, 'status': 'DERIVED', 'reason': f'{tolerance * 100}% 오차 범위 내'})
                continue

        results.append({'token': token, 'status': 'UNSUPPORTED', 'reason': '출처 미확인'})
        
    unsupported = [r['token'] for r in results if r['status'] == 'UNSUPPORTED']
    derived = [r['token'] for r in results if r['status'] == 'DERIVED']
    common = [r['token'] for r in results if r['status'] == 'COMMON']
    
    return {
        'passed': len(unsupported) == 0,
        'tokens': extracted,
        'unsupported': unsupported,
        'derived': derived,
        'common': common,
        'details': results
    }

async def validate_numeric_context(sentence: str, token: str, allowlist: Dict[str, Any], model_name: str = "gemini-2.5-flash"):
    from .gemini_client import generate_content_async, get_client

    allowed_tokens_str = ', '.join((allowlist.get('tokens', []) or [])[:20]) or '(없음)'

    if not get_client():
        return {'type': 'UNKNOWN', 'confidence': 0, 'reason': 'API Key fail'}

    prompt = f"""당신은 팩트체크 전문가입니다. 문장에서 사용된 수치가 적절한지 판단하세요.

[검증 대상 문장]
"{sentence}"

[검증 대상 수치]
{token}

[출처에서 확인된 수치 목록]
{allowed_tokens_str}

[판단 기준]
1. ALLOWED - 출처 목록에서 직접 인용한 수치
2. DERIVED - 출처 목록의 수치들로 계산/추론 가능 (합계, 차이, 비율 등)
3. COMMON - 일반 상식 수치 (현재 연도, 공식 인구통계, 일반적 표현)
4. GOAL - 미래 목표/계획 수치 (출처 없어도 허용 가능)
5. HALLUCINATION - 출처 없는 구체적 수치 (위험)

반드시 다음 JSON 형식으로만 응답:
{{"type": "ALLOWED|DERIVED|COMMON|GOAL|HALLUCINATION", "confidence": 0.0-1.0, "reason": "판단 근거"}}"""

    try:
        response_text = await generate_content_async(
            prompt,
            model_name=model_name,
            response_mime_type='application/json'
        )
        # Clean markdown
        text = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', response_text).strip()
        data = json.loads(text)
        return data
    except Exception as e:
        logger.warning(f"⚠️ [FactGuard] LLM 검증 실패: {e}")
        return {'type': 'UNKNOWN', 'confidence': 0, 'reason': str(e)}

async def validate_with_llm(content: str, allowlist: Dict[str, Any] = {}, options: Dict[str, Any] = {}):
    model_name = options.get('modelName', "models/gemini-2.5-flash")
    max_llm_calls = options.get('maxLLMCalls', 3)
    
    # 1. Rule based
    rule_result = find_unsupported_numeric_tokens(content, allowlist, options)
    
    if rule_result['passed']:
        return {**rule_result, 'llmValidated': False}
        
    # 2. LLM val
    unsupported_tokens = rule_result['unsupported'][:max_llm_calls]
    llm_results = []
    
    for token in unsupported_tokens:
        sentences = re.split(r'[.!?]', content)
        relevant_sentence = next((s for s in sentences if token in s), content[:200])
        
        llm_res = await validate_numeric_context(relevant_sentence.strip(), token, allowlist, model_name)
        
        type_ = llm_res.get('type', 'UNKNOWN')
        llm_results.append({
            'token': token,
            **llm_res,
            'riskLevel': RISK_LEVELS.get(type_, 2)
        })
        
    final_unsupported = [r['token'] for r in llm_results if r['riskLevel'] >= 3]
    warnings = [r['token'] for r in llm_results if r['riskLevel'] == 2]
    
    # If there are unsupported tokens NOT checked by LLM (due to maxLLMCalls), add them back as unsupported
    # Actually logic in JS filters by riskLevel >= 3. If something wasn't checked, it remains unsupported?
    # JS code:
    # `unsupportedTokens` are those checked.
    # What about those > max_calls?
    # JS logic implies only `unsupportedTokens` (subset) are checked. The rest are ignored?
    # Or maybe the function returns `passed` mainly based on checked ones?
    # JS: `passed: finalUnsupported.length === 0`
    # It effectively ignores unchecked tokens in `passed` calculation if they exceed limit.
    # But wait, `finalUnsupported` is derived from `llmResults`.
    # If I have 10 unsupported tokens, and check 3. If those 3 are refined to be OK, `finalUnsupported` is empty.
    # But 7 remain unchecked.
    # This seems like a flaw in JS or intended optimization. I'll follow JS logic.
    
    # Wait, `ruleBasedResult.unsupported` has ALL failures.
    # `llmResults` has checks for first 3.
    # If I check 3 and they are safe, `finalUnsupported` is empty.
    # But what about the other 7?
    # Re-reading JS:
    # `const finalUnsupported = llmResults.filter(r => r.riskLevel >= 3).map(r => r.token);`
    # It only considers checked ones.
    # So if you have 10 errors, check 3, find 0 issues, you essentially pass?
    # That sounds loose.
    # BUT, `ruleBasedResult.unsupported` is NOT returned in the final object, only `finalUnsupported`.
    # AND `tokens: ruleBasedResult.tokens` is returned.
    
    # However, if I look closely at JS `validateWithLLM`:
    # It returns `unsupported: finalUnsupported`.
    # So yes, it seems to "forgive" excess unchecked tokens or simply assumes they are effectively not "proven" hallucinations.
    # Or maybe I should include unchecked ones in `finalUnsupported`?
    # The JS implementation:
    # `unsupportedTokens` = slice(0, 3)
    # `llmResults` = loop over `unsupportedTokens`.
    # `finalUnsupported` = filter `llmResults`.
    # Returns `unsupported: finalUnsupported`.
    
    # So yes, unchecked tokens dropped from 'unsupported' list effectively.
    # I will replicate this behavior even if it seems lenient.
    
    return {
        'passed': len(final_unsupported) == 0,
        'tokens': rule_result['tokens'],
        'unsupported': final_unsupported,
        'warnings': warnings,
        'derived': rule_result['derived'],
        'common': rule_result['common'],
        'llmValidated': True,
        'llmResults': llm_results
    }
