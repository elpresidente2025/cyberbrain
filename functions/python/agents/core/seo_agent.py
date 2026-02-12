
import logging
import re
from typing import Dict, Any, List, Optional
from ..base_agent import Agent
from ..common.seo import build_seo_instruction, SEO_RULES

logger = logging.getLogger(__name__)

class SEOAgent(Agent):
    def __init__(self, name: str = 'SEOAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        SEO validation and optimization.
        """
        content = context.get('optimizedContent') or context.get('content') or ''
        title = context.get('title', '')
        user_keywords = context.get('keywords', [])
        
        # 1. Optimize Title (Length & Keyword)
        # Assuming TitleAgent already did a good job, but SEO agent double checks and truncates if strictly needed
        optimized_title = self.optimize_title(title, user_keywords)
        
        # 2. Keyword Density & Spam Check
        keyword_result = self.validate_user_keywords(content, user_keywords)
        
        # 3. Structure & Readability Check
        structure_result = self.validate_structure(content)
        
        # 4. Anti-Repetition Check
        repetition_result = self.check_anti_repetition(content)
        
        # 5. Final SEO Score/Pass
        passed = (
            keyword_result['passed'] and
            structure_result['passed'] and
            repetition_result['passed']
        )
        
        return {
            'content': content, # SEO agent usually validates, maybe optimizes meta description.
            'title': optimized_title,
            'seoPassed': passed,
            'details': {
                'keywords': keyword_result,
                'structure': structure_result,
                'repetition': repetition_result
            }
        }

    def optimize_title(self, title: str, keywords: List[str]) -> str:
        if not title: return ''
        
        normalized = title.strip()
        limit = 25
        
        # 1. Basic length check
        if len(normalized) <= limit:
            return normalized
            
        # 2. Tail trimming (remove suffix like | Name)
        normalized = re.sub(r'[-–—|]+.*$', '', normalized).strip()
        if len(normalized) <= limit:
            return normalized
            
        # 3. Punctuation split
        parts = re.split(r'[-–—|.:]', normalized)
        if parts:
             head = parts[0].strip()
             if len(head) <= limit and len(head) > 5:
                  return head
        
        # 4. Keyword fallback (extreme case)
        if keywords and len(keywords[0]) < limit:
             # Construct a simple title
             return f"{keywords[0]} 관련 소식"
             
        # 5. Hard truncate
        return normalized[:limit]

    def validate_user_keywords(self, content: str, keywords: List[str]) -> Dict[str, Any]:
        if not keywords:
            return {'passed': True, 'issues': []}
            
        plain_text = re.sub(r'<[^>]*>', ' ', content)
        actual_length = len(re.sub(r'\s+', '', plain_text)) # Chars without spaces

        # 키워드 2개 기준: 각 3~4회, 총합 7~8회 (15문단 기준 약 2문단당 1회)
        kw_count = len(keywords) if keywords else 1
        min_allowed = 3 if kw_count >= 2 else 5
        max_allowed = min_allowed + 1  # 3→4, 5→6
        ideal_count = min_allowed
        
        issues = []
        
        for kw in keywords:
            count = plain_text.count(kw)
            if count < min_allowed:
                issues.append(f'키워드 "{kw}" 부족 (현재 {count}회, 권장 {min_allowed}회 이상)')
            elif count > max_allowed:
                 issues.append(f'키워드 "{kw}" 과다 (현재 {count}회, 권장 {max_allowed}회 이하)')
                 
        return {
            'passed': len(issues) == 0,
            'issues': issues,
            'stats': {'wordCount': actual_length, 'idealCurrent': ideal_count}
        }

    def validate_structure(self, content: str) -> Dict[str, Any]:
        issues = []
        
        # Check headings
        h1_count = len(re.findall(r'<h1', content, re.IGNORECASE))
        h2_count = len(re.findall(r'<h2', content, re.IGNORECASE))
        h3_count = len(re.findall(r'<h3', content, re.IGNORECASE))
        
        if h1_count > 1:
            issues.append('H1 태그가 2개 이상입니다 (1개 권장)')
        if h2_count < 2:
            issues.append('H2 태그가 너무 적습니다 (소제목 구분 필요)')
            
        # Paragraph length
        paragraphs = re.findall(r'<p>(.*?)</p>', content, re.IGNORECASE | re.DOTALL)
        long_paragraphs = [p for p in paragraphs if len(re.sub(r'<[^>]*>', '', p).strip()) > 300]
        
        if long_paragraphs:
             issues.append(f'너무 긴 문단이 {len(long_paragraphs)}개 감지됨 (300자 이내 권장)')
             
        return {
            'passed': len(issues) == 0,
            'issues': issues,
            'stats': {'h1': h1_count, 'h2': h2_count, 'p': len(paragraphs)}
        }

    def check_anti_repetition(self, content: str) -> Dict[str, Any]:
        issues = []

        # Check repeated sentences
        plain_text = re.sub(r'<[^>]*>', ' ', content)
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        sentences = re.split(r'(?<=[.!?])\s+', plain_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

        seen = set()
        repeated = set()
        for s in sentences:
            normalized = re.sub(r'\s+', '', s).lower()
            if normalized in seen:
                repeated.add(s[:50])
            seen.add(normalized)

        if repeated:
            issues.append(f'반복된 문장 발견 ({len(repeated)}개)')

        # 3어절 이상 구문 반복 검출 (3회 이상 등장 시 위반)
        words = plain_text.split()
        phrase_count = {}
        for n in range(3, 7):
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i + n])
                if len(phrase) < 10:
                    continue
                phrase_count[phrase] = phrase_count.get(phrase, 0) + 1

        over_limit = sorted(
            [(p, c) for p, c in phrase_count.items() if c >= 3],
            key=lambda x: -len(x[0])
        )
        already_covered = []
        for phrase, count in over_limit:
            if any(phrase in existing for existing in already_covered):
                continue
            already_covered.append(phrase)
            issues.append(f'구문 반복: "{phrase[:40]}" ({count}회)')

        # Jaccard 유사도 기반 유사 문장 검출 (60% 이상)
        long_sentences = [s for s in sentences if len(s) > 25]
        word_sets = []
        for s in long_sentences:
            ws = set(w for w in re.sub(r'[.?!,]', '', s).split() if len(w) >= 2)
            word_sets.append(ws)

        similar_pairs = []
        for i in range(len(long_sentences)):
            for j in range(i + 1, len(long_sentences)):
                set_a, set_b = word_sets[i], word_sets[j]
                if len(set_a) < 3 or len(set_b) < 3:
                    continue
                intersection = len(set_a & set_b)
                union = len(set_a | set_b)
                similarity = intersection / union if union > 0 else 0
                if 0.6 <= similarity < 0.95:
                    similar_pairs.append((
                        long_sentences[i][:50],
                        long_sentences[j][:50],
                        round(similarity * 100)
                    ))

        if similar_pairs:
            pair_summaries = [f'"{a}" ≈ "{b}" ({sim}%)' for a, b, sim in similar_pairs[:3]]
            issues.append(f'유사 문장 감지: {", ".join(pair_summaries)}')

        return {
            'passed': len(issues) == 0,
            'issues': issues
        }
