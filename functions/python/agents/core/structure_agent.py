
import re
import json
import logging
import time
from typing import Dict, Any, Optional, List

# API Call Timeout (seconds)
LLM_CALL_TIMEOUT = 120  # 2분 타임아웃
CONTEXT_ANALYZER_TIMEOUT = 60  # 1분 타임아웃

# Local imports
from ..common.classifier import classify_topic
from ..common.warnings import generate_non_lawmaker_warning, generate_family_status_warning
from ..common.theminjoo import get_party_stance
from ..common.election_rules import get_election_stage, get_prompt_instruction
from ..common.seo import build_seo_instruction
from ..common.constants import resolve_writing_method

# Template Builders
from ..templates.daily_communication import build_daily_communication_prompt
from ..templates.activity_report import build_activity_report_prompt
from ..templates.policy_proposal import build_policy_proposal_prompt
from ..templates.current_affairs import build_critical_writing_prompt, build_diagnosis_writing_prompt
from ..templates.local_issues import build_local_issues_prompt

# Template Builders Mapping
TEMPLATE_BUILDERS = {
    'emotional_writing': build_daily_communication_prompt,
    'logical_writing': build_policy_proposal_prompt, # Mapped buildLogicalWritingPrompt to policy proposal
    'direct_writing': build_activity_report_prompt,
    'critical_writing': build_critical_writing_prompt,
    'diagnostic_writing': build_diagnosis_writing_prompt,
    'analytical_writing': build_local_issues_prompt
}

logger = logging.getLogger(__name__)

def strip_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]*>', '', text)
    return re.sub(r'\s+', '', text).strip()

def normalize_artifacts(text: str) -> str:
    if not text:
        return ''
    cleaned = text.strip()
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned).strip()
    cleaned = re.sub(r'^\s*\\"', '', cleaned)
    cleaned = re.sub(r'\\"?\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*["“]', '', cleaned)
    cleaned = re.sub(r'["”]\s*$', '', cleaned)
    
    # Remove metadata lines if any (Robust Regex)
    # Catch '카테고리:', '검색어...', '생성 시간:' and everything after them until end of string
    # We use [\s\S]* to match all characters including newlines
    cleaned = re.sub(r'(\**카테고리\**|\**검색어 삽입 횟수\**|\**생성 시간\**):[\s\S]*$', '', cleaned).strip()
    
    cleaned = re.sub(r'"content"\s*:\s*', '', cleaned)
    
    return cleaned.strip()

from ..base_agent import Agent

class StructureAgent(Agent):
    def __init__(self, name: str = 'StructureAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)

        # 공통 Gemini 클라이언트 사용 (새 google-genai SDK)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = DEFAULT_MODEL

        # 클라이언트 초기화 확인
        client = get_client()
        if client:
            print(f"🤖 [StructureAgent] 모델: {self.model_name}")
        else:
            print(f"⚠️ [StructureAgent] Gemini 클라이언트 초기화 실패")

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        topic = context.get('topic', '')
        user_profile = context.get('userProfile', {})
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}
        category = context.get('category', '')
        sub_category = context.get('subCategory', '')
        instructions = context.get('instructions', '')
        news_context = context.get('newsContext', '')
        # 🔑 [NEW] 입장문과 뉴스/데이터 분리
        stance_text = context.get('stanceText', '')
        news_data_text = context.get('newsDataText', '')
        target_word_count = context.get('targetWordCount', 2000)
        user_keywords = context.get('userKeywords', [])
        memory_context = context.get('memoryContext', '')

        print(f"🚀 [StructureAgent] 시작 - 카테고리: {category or '(자동)'}, 주제: {topic}")
        print(f"📊 [StructureAgent] 입장문: {len(stance_text)}자, 뉴스/데이터: {len(news_data_text)}자")

        # 1. Determine Writing Method
        writing_method = ''
        if category and category != 'auto':
            writing_method = resolve_writing_method(category, sub_category)
            print(f"✍️ [StructureAgent] 작법 선택 (카테고리 기반): {writing_method}")
        else:
            classification = await classify_topic(topic)
            writing_method = classification['writingMethod']
            print(f"🤖 [StructureAgent] 작법 자동 추론: {writing_method} (신뢰도: {classification.get('confidence')}, 소스: {classification.get('source')})")

        # 2. Build Author Bio
        author_bio, author_name = self.build_author_bio(user_profile)

        # 3. Get Party Stance
        party_stance_guide = None
        try:
             party_stance_guide = get_party_stance(topic)
        except Exception as e:
             print(f"⚠️ [StructureAgent] 당론 조회 실패: {str(e)}")

        # 4. ContextAnalyzer (입장문/뉴스 분리 처리)
        context_analysis = await self.run_context_analyzer(
            stance_text or instructions,  # 입장문 우선, 없으면 기존 instructions 사용
            news_data_text or news_context,  # 뉴스 데이터 우선, 없으면 기존 newsContext 사용
            author_name
        )

        # 5. Build Prompt
        prompt = self.build_prompt({
            'topic': topic,
            'category': category,
            'writingMethod': writing_method,
            'authorName': author_name,
            'authorBio': author_bio,
            'instructions': instructions,
            'newsContext': news_context,
            'targetWordCount': target_word_count,
            'partyStanceGuide': party_stance_guide,
            'contextAnalysis': context_analysis,
            'userProfile': user_profile,
            'memoryContext': memory_context,
            'userKeywords': user_keywords
        })

        print(f"📝 [StructureAgent] 프롬프트 생성 완료 ({len(prompt)}자)")

        # 6. Retry Loop (검증 로직 엄격하게 복구, 대신 프롬프트를 강화하여 성공률 제고)
        max_retries = 2
        attempt = 0
        feedback = ''
        validation = {}
        last_error = None  # 마지막 예외 추적

        while attempt <= max_retries:
            attempt += 1
            print(f"🔄 [StructureAgent] 생성 시도 {attempt}/{max_retries + 1}")

            current_prompt = prompt
            if feedback:
                current_prompt += f"\n\n🚨 [중요 - 재작성 지시] 이전 작성본이 다음 이유로 반려되었습니다:\n\"{feedback}\"\n\n특히 **분량 부족**이 문제라면, 각 본론 섹션의 **사례와 근거**를 대폭 보강하여 무조건 **지정된 분량(2000자 이상)**을 넘기십시오. 요약하지 말고 상세히 서술하십시오."

            try:
                response = await self.call_llm(current_prompt)
                print(f"📥 [StructureAgent] LLM 원본 응답 ({len(response)}자)")

                structured = self.parse_response(response)
                content = normalize_artifacts(structured['content'])
                title = normalize_artifacts(structured['title'])

                content = normalize_artifacts(structured['content'])
                title = normalize_artifacts(structured['title'])

                validation = self.validate_output(content, target_word_count)

                if validation['passed']:
                    print(f"✅ [StructureAgent] 검증 통과: {len(strip_html(content))}자")

                    if not title.strip():
                        title = topic[:20] if topic else '새 원고'

                    return {
                        'content': content,
                        'title': title,
                        'writingMethod': writing_method,
                        'contextAnalysis': context_analysis
                    }

                print(f"⚠️ [StructureAgent] 검증 실패: {validation['reason']}")
                feedback = validation['feedback']
                last_error = None  # 검증 실패는 예외가 아님

            except Exception as e:
                error_msg = str(e)
                print(f"❌ [StructureAgent] 에러 발생: {error_msg}")
                feedback = error_msg
                last_error = error_msg  # 예외 메시지 저장

            if attempt > max_retries:
                # 마지막 에러가 예외면 그 메시지 사용, 아니면 검증 실패 이유 사용
                final_reason = last_error or validation.get('reason', '알 수 없는 오류')
                raise Exception(f"StructureAgent 실패 ({max_retries}회 재시도 후): {final_reason}")

    async def call_llm(self, prompt: str) -> str:
        from ..common.gemini_client import generate_content_async

        print(f"📤 [StructureAgent] LLM 호출 시작")
        start_time = time.time()

        try:
            response_text = await generate_content_async(
                prompt,
                model_name=self.model_name,
                temperature=0.25,  # Node.js parity: 0.25 for strict instruction adherence
                max_output_tokens=8192
            )

            elapsed = time.time() - start_time
            print(f"✅ [StructureAgent] LLM 응답 완료 ({elapsed:.1f}초)")

            return response_text

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"❌ [StructureAgent] LLM 호출 실패 ({elapsed:.1f}초): {error_msg}")

            # 타임아웃 관련 에러 메시지 개선
            if 'timeout' in error_msg.lower() or 'deadline' in error_msg.lower():
                raise Exception(f"LLM 호출 타임아웃 ({elapsed:.1f}초). Gemini API가 응답하지 않습니다.")
            raise

    async def run_context_analyzer(self, stance_text: str, news_data_text: str, author_name: str) -> Optional[Dict]:
        from ..common.gemini_client import generate_content_async

        # 입장문이 없으면 분석 스킵
        if len(stance_text) < 50:
            print(f"⚠️ [StructureAgent] 입장문이 너무 짧음 ({len(stance_text)}자) - ContextAnalyzer 스킵")
            return None

        print(f'🔍 [StructureAgent] ContextAnalyzer 실행... (입장문: {len(stance_text)}자, 뉴스: {len(news_data_text)}자)')
        start_time = time.time()

        if not news_data_text:
            # Fallback Logic: 뉴스 데이터 없을 때 - 그냥 진행
            # (user_profile이 이 함수 scope에 없어서 fallback 로직 비활성화)
            print(f"⚠️ [StructureAgent] 뉴스 데이터 없음 - 입장문만으로 분석 진행")

        context_prompt = f"""당신은 정치 콘텐츠 전략가입니다. 아래 입장문을 분석하여 블로그 콘텐츠 전략을 수립하세요.

[입장문 원문]
{stance_text[:2500]}

[뉴스/데이터 (있으면)]
{news_data_text[:2000] if news_data_text else '(없음)'}

## 분석 과제

### 1. 글의 핵심 의도 (Intent)
아래 중 가장 적합한 것 하나를 선택:
- "donation_request": 후원 요청 (계좌, 연락처 포함)
- "policy_promotion": 정책/비전 홍보
- "event_announcement": 일정/행사 안내
- "activity_report": 활동 보고
- "personal_message": 개인 소통/인사

### 2. 콘텐츠 전략 (ContentStrategy)
이 글을 2000자 블로그로 확장할 때:
- tone: 어떤 톤앤매너? ("감성 호소", "논리적 설득", "정보 전달", "친근한 소통")
- structure: 어떤 구조? ("스토리텔링 → 비전 → CTA", "문제 → 해법 → 효과", "일정 → 내용 → 참여방법")
- emphasis: 무엇을 강조? (리스트로)

### 3. 핵심 주장 추출 (MustIncludeFromStance)
글쓴이({author_name})의 핵심 주장 최대 3개, 각각에 대해:
- topic: 핵심 주장 (간결한 문장)
- expansion_why: 이 주장이 필요한 배경
- expansion_how: 구체적 실현 방안
- expansion_effect: 기대되는 효과

### 4. 필수 보존 정보 (MustPreserve) ⚠️ 중요
원문에서 **절대 누락되면 안 되는 구체적 정보**를 추출:
- bankName: 은행명 (없으면 null)
- accountNumber: 계좌번호 (없으면 null)
- accountHolder: 예금주 (없으면 null)
- contactNumber: 연락처 (없으면 null)
- instruction: 안내 문구 (없으면 null)
- eventDate: 일시 (없으면 null)
- eventLocation: 장소 (없으면 null)
- ctaPhrase: CTA 문구, 예: "함께해 주십시오" (없으면 null)

반드시 아래 JSON 포맷으로 응답:
{{
  "intent": "donation_request",
  "contentStrategy": {{
    "tone": "감성 호소",
    "structure": "스토리텔링 → 비전 → CTA",
    "emphasis": ["후원 동참 유도", "진정성 전달"]
  }},
  "mustIncludeFromStance": [
    {{
      "topic": "핵심 주장 1",
      "expansion_why": "배경...",
      "expansion_how": "방안...",
      "expansion_effect": "효과..."
    }}
  ],
  "mustIncludeFacts": [],
  "mustPreserve": {{
    "bankName": "신한은행",
    "accountNumber": "140016005619",
    "accountHolder": "이재성 후원회",
    "contactNumber": "01097262663",
    "instruction": "입금 후 성함 문자 → 영수증 발급",
    "eventDate": null,
    "eventLocation": null,
    "ctaPhrase": "지금 바로 함께할 수 있습니다"
  }}
}}"""

        try:
            response_text = await generate_content_async(
                context_prompt,
                model_name=self.model_name,
                temperature=0.0,  # 분석은 정확도 우선
                response_mime_type='application/json'
            )

            analysis = json.loads(response_text)

            elapsed = time.time() - start_time
            print(f"✅ [StructureAgent] ContextAnalyzer 완료 ({elapsed:.1f}초)")

            # Filter phrases
            if 'mustIncludeFromStance' in analysis and isinstance(analysis['mustIncludeFromStance'], list):
                filtered_list = []
                for item in analysis['mustIncludeFromStance']:
                    # 기존 문자열 호환성 (string이면 그대로 사용)
                    if isinstance(item, str) and len(item.strip()) >= 5:
                         filtered_list.append({'topic': item, 'expansion_why': '', 'expansion_how': '', 'expansion_effect': ''})
                    # 딕셔너리 구조 필터링
                    elif isinstance(item, dict) and item.get('topic'):
                        topic = item.get('topic', '').strip()
                        if len(topic) >= 2 and not topic.startswith('⚠️'):
                            filtered_list.append(item)
                analysis['mustIncludeFromStance'] = filtered_list

            return analysis
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"⚠️ [StructureAgent] ContextAnalyzer 실패 ({elapsed:.1f}초): {error_msg} - 건너뜀")
            return None

    def build_prompt(self, params: Dict[str, Any]) -> str:
        # Extract params
        writing_method = params.get('writingMethod')
        template_builder = TEMPLATE_BUILDERS.get(writing_method, build_daily_communication_prompt)

        # userProfile 방어 코드 - list로 전달되는 경우 방어
        user_profile = params.get('userProfile', {})
        if not isinstance(user_profile, dict):
            user_profile = {}

        # Build base template prompt
        template_prompt = template_builder({
            'topic': params.get('topic'),
            'authorBio': params.get('authorBio'),
            'authorName': params.get('authorName'),
            'instructions': params.get('instructions'),
            'keywords': params.get('userKeywords'),
            'targetWordCount': params.get('targetWordCount'),
            'personalizedHints': params.get('memoryContext'),
            'newsContext': params.get('newsContext'),
            'isCurrentLawmaker': self.is_current_lawmaker(user_profile),
            'politicalExperience': user_profile.get('politicalExperience', '정치 신인'),
            'familyStatus': user_profile.get('familyStatus', '')
        })

        # Reference Materials Section
        source_text = "\n\n---\n\n".join(filter(None, [params.get('instructions'), params.get('newsContext')]))
        ref_section = ""
        if source_text.strip():
            ref_section = f"""
╔═══════════════════════════════════════════════════════════════╗
║  📚 [1차 자료] 참고자료 - 원고의 핵심 소스                     ║
╚═══════════════════════════════════════════════════════════════╝

⚠️ **[CRITICAL] 아래 참고자료가 이 원고의 1차 자료(Primary Source)입니다.**
- 첫 번째 자료: 작성자의 입장문/페이스북 글 (핵심 논조와 주장)
- 이후 자료: 뉴스/데이터 (근거, 팩트, 배경 정보)

**[참고자료 원문]**
{source_text[:6000]}

🚨 **[자료 처리 규칙 - 중요]**
1. **정보 추출**: 참고자료에서 핵심 팩트, 수치, 논점만 추출하세요.
2. **재작성 필수 (CRITICAL)**: 추출한 정보를 **반드시 새로운 문장으로 다시 작성**하세요. 참고자료의 문장을 그대로 복사하지 마세요.
3. **구어체 → 문어체 변환**: 인터뷰/대화체 자료의 경우, 구어체 표현("그래서요", "거예요", "~하거든요" 등)을 문어체로 변환하세요.
4. **창작 금지**: 참고자료에 없는 팩트, 수치를 창작하지 마세요.
5. **주제 유지**: 참고자료의 주제를 벗어나지 마세요.
6. **보조 자료**: 사용자 프로필(Bio)은 화자 정체성과 어조 참고용이며, 분량이 부족할 때만 활용하세요.

❌ **금지 예시**:
- 참고자료: "정확하게 얘기를 하면 그래서 창의적이고 정말 압도적인..."
- ❌ 잘못된 사용: "정확하게 얘기를 하면 그래서 창의적이고..." (복붙)
- ✅ 올바른 사용: "창의적이고 압도적인 콘텐츠 기반 전략이 핵심입니다." (재작성)
"""
            print(f"📚 [StructureAgent] 참고자료 주입 완료: {len(source_text)}자")
        else:
            print("⚠️ [StructureAgent] 참고자료 없음 - 사용자 프로필만으로 생성")

        # Context Injection
        context_injection = ""
        context_analysis = params.get('contextAnalysis')
        if context_analysis:
            stance_list = context_analysis.get('mustIncludeFromStance', [])
            
            # 구조화된 stance 처리
            formatted_stances = []
            for i, p in enumerate(stance_list):
                if isinstance(p, dict):
                    topic = p.get('topic', '')
                    why_txt = p.get('expansion_why', '')
                    how_txt = p.get('expansion_how', '')
                    eff_txt = p.get('expansion_effect', '')
                    
                    block = f"""
{i+1}. **{topic}** (본론 {i+1} 주제)
   - [Why/배경]: {why_txt}
   - [How/해법]: {how_txt}
   - [Effect/효과]: {eff_txt}"""
                    formatted_stances.append(block.strip())
                else:
                    # Fallback for string (legacy)
                    formatted_stances.append(f"{i+1}. {p}")

            stance_phrases = "\n\n".join(formatted_stances)
            stance_count = len(stance_list)
            
            if stance_count > 0:
                context_injection = f"""
╔═══════════════════════════════════════════════════════════════╗
║  🔴 [MANDATORY] 본론 섹션별 확장 설계도 (Deep Expansion)       ║
╚═══════════════════════════════════════════════════════════════╝

아래 **{stance_count}개 설계도**에 따라 각 본론 섹션을 작성하십시오.
단순히 주제만 언급하지 말고, 함께 제공된 [Why-How-Effect] 논리를 문단 구성에 반드시 반영해야 합니다.

{stance_phrases}

📌 **작성 지침**:
1. 위 {stance_count}개 주제를 각각 **별도의 본론 섹션(H2)**으로 구성하십시오.
2. 각 섹션 작성 시, 위에서 설계된 [Why], [How], [Effect] 내용을 빠짐없이 서술하여 분량을 확보하고 논리를 완성하십시오.
3. **[How] 단계**에서 당신의 Bio(경력)를 근거로 활용하여 전문성을 드러내십시오.
"""

            # 🔴 [NEW] contentStrategy 주입
            content_strategy = context_analysis.get('contentStrategy', {})
            if content_strategy:
                tone = content_strategy.get('tone', '')
                structure = content_strategy.get('structure', '')
                emphasis = content_strategy.get('emphasis', [])
                
                if tone or structure:
                    emphasis_str = ", ".join(emphasis) if emphasis else "없음"
                    context_injection += f"""
╔═══════════════════════════════════════════════════════════════╗
║  🎯 [STRATEGY] 콘텐츠 전략 가이드                              ║
╚═══════════════════════════════════════════════════════════════╝

**[톤앤매너]**: {tone}
**[구조]**: {structure}
**[강조점]**: {emphasis_str}

위 전략에 맞춰 글을 작성하십시오.
"""
                    print(f"🎯 [StructureAgent] 콘텐츠 전략 주입: {tone} / {structure}")

            # 🔴 [NEW] mustPreserve 기반 CTA 정보 주입
            must_preserve = context_analysis.get('mustPreserve', {})
            intent = context_analysis.get('intent', '')
            
            if must_preserve and intent == 'donation_request':
                bank_name = must_preserve.get('bankName')
                account_number = must_preserve.get('accountNumber')
                account_holder = must_preserve.get('accountHolder')
                contact_number = must_preserve.get('contactNumber')
                instruction = must_preserve.get('instruction')
                cta_phrase = must_preserve.get('ctaPhrase')
                
                # 유효한 정보가 있으면 주입
                if account_number or contact_number:
                    cta_parts = []
                    if bank_name and account_number:
                        cta_parts.append(f"- 후원계좌: {bank_name} {account_number}")
                    if account_holder:
                        cta_parts.append(f"- 예금주: {account_holder}")
                    if contact_number and instruction:
                        cta_parts.append(f"- 연락처: {contact_number} ({instruction})")
                    elif contact_number:
                        cta_parts.append(f"- 연락처: {contact_number}")
                    if cta_phrase:
                        cta_parts.append(f"- CTA 문구: \"{cta_phrase}\"")
                    
                    cta_text = "\n".join(cta_parts)
                    
                    context_injection += f"""
╔═══════════════════════════════════════════════════════════════╗
║  💰 [CRITICAL] 후원 정보 - 결론부에 반드시 포함               ║
╚═══════════════════════════════════════════════════════════════╝

이 글의 핵심 목적은 **후원 요청**입니다. 
결론부에서 아래 후원 정보를 **자연스럽게 안내**하십시오.

**[후원 안내 정보]**
{cta_text}

📌 **작성 지침**:
1. 결론부에서 후원 참여를 자연스럽게 요청하십시오.
2. 후원 계좌와 연락처 정보를 명시적으로 포함하십시오.
3. CTA 문구("{cta_phrase or '함께해 주십시오'}")를 사용하십시오.
4. 후원금 영수증 발급 안내가 있다면 언급하십시오.
"""
                    print(f"💰 [StructureAgent] 후원 정보 주입: {bank_name} {account_number} / {contact_number}")

            # 🔴 [NEW] 행사 안내 정보 주입
            elif must_preserve and intent == 'event_announcement':
                event_date = must_preserve.get('eventDate')
                event_location = must_preserve.get('eventLocation')
                contact_number = must_preserve.get('contactNumber')
                cta_phrase = must_preserve.get('ctaPhrase')
                
                if event_date or event_location:
                    event_parts = []
                    if event_date:
                        event_parts.append(f"- 일시: {event_date}")
                    if event_location:
                        event_parts.append(f"- 장소: {event_location}")
                    if contact_number:
                        event_parts.append(f"- 문의: {contact_number}")
                    
                    event_text = "\n".join(event_parts)
                    
                    context_injection += f"""
╔═══════════════════════════════════════════════════════════════╗
║  📅 [CRITICAL] 행사 정보 - 본문에 반드시 포함                 ║
╚═══════════════════════════════════════════════════════════════╝

**[행사 안내 정보]**
{event_text}

📌 위 정보를 본문과 결론부에 명확히 포함하십시오.
"""
                    print(f"📅 [StructureAgent] 행사 정보 주입: {event_date} / {event_location}")

        # Warning Generation
        bio_warning = ""
        non_lawmaker_warn = generate_non_lawmaker_warning(
            self.is_current_lawmaker(user_profile),
            user_profile.get('politicalExperience'),
            params.get('authorBio')
        )
        if non_lawmaker_warn:
            bio_warning += non_lawmaker_warn + "\n\n"
        
        if params.get('authorBio') and '"' in params.get('authorBio', ''):
            bio_warning += """
🚨 [BIO 인용 규칙 - 절대 준수]
- Bio에 있는 **큰따옴표(" ")로 묶인 문장**은 사용자의 핵심 서사입니다.
- 이 문장은 **한 글자도 수정하지 말고 원문 그대로** 인용하십시오.
- 특히 AI가 임의로 **사람 이름으로 단어를 대체**하는 것은 절대 금지입니다.
  - ❌ 잘못된 예: "벌써 국회의원 했을 텐데" → "벌써 홍길동 했을 텐데"
  - ✅ 올바른 예: "벌써 국회의원 했을 텐데" (원문 그대로)
"""

        # Modified Structure Enforcement: Dynamic based on stance_count
        stance_count = 0
        if context_analysis:
            stance_count = len(context_analysis.get('mustIncludeFromStance', []))

        # 본론 섹션 수 결정: 무조건 3개로 고정 (사용자 요청 5단 구조 준수: 도입-본론1-본론2-본론3-결론)
        # 내용이 많아도 3개로 압축해야 분량(2000~2500자)을 맞출 수 있음.
        body_section_count = 3
        total_section_count = body_section_count + 2  # 도입부 + 결론부
        min_total_chars = total_section_count * 350  # 섹션당 최소 350자
        max_total_chars = total_section_count * 450  # 섹션당 최대 450자
        
        # 동적 본론 구조 문자열 생성
        body_structure_lines = []
        for i in range(1, body_section_count + 1):
            body_structure_lines.append(f"{i+1}. 본론 {i} (1섹션, 3문단, 350~450자) - HTML <h2> 소제목 필수")
        body_structure_str = "\\n".join(body_structure_lines)
        
        # 지역 정보 추출 - 범용성 확보 및 동적 변수
        region_metro = user_profile.get('regionMetro', '')
        region_district = user_profile.get('regionDistrict', '')
        user_region = f"{region_metro} {region_district}".strip()
        if not user_region:
            user_region = "지역 사회"
            
        structure_enforcement = f"""
<structure_guide mode="strict">
  <strategy>E-A-T (전문성-권위-신뢰) 전략으로 작성</strategy>

  <volume warning="위반 시 시스템 오류">
    <per_section min="350" max="450" recommended="400"/>
    <paragraphs_per_section>3개 문단, 문단당 3~4문장</paragraphs_per_section>
    <total sections="{total_section_count}" min="{min_total_chars}" max="{max_total_chars}"/>
    <caution>내용이 아무리 좋아도 섹션당 450자 초과 금지. 길어지면 과감히 요약.</caution>
  </volume>

  <expansion_guide name="섹션별 작성 4단계">
    각 본론 섹션을 아래 흐름으로 전개하되, 각 단계를 1~2문장으로 짧게 작성 (장황한 서술 금지)
    <step name="Why" sentences="1">시민 고충 진단</step>
    <step name="How+Expertise" sentences="2">해결책 + Bio 인용 [전문성]</step>
    <step name="Authority" sentences="1">실행 능력 증명 [권위]</step>
    <step name="Effect+Trust" sentences="2">변화될 {user_region}의 모습 + 진정성 [신뢰]</step>
  </expansion_guide>

  <sections total="{total_section_count}">
    <intro paragraphs="3" chars="400" heading="없음">
      <p>1문단: 인삿말 (&lt;p&gt;안녕하세요, OOO입니다.&lt;/p&gt;)</p>
      <p>2문단: 주제 도입 및 배경 설명</p>
      <p>3문단: 글의 방향성 제시</p>
    </intro>
    {body_structure_str}
    <conclusion order="{total_section_count}" paragraphs="3" chars="400" heading="h2 필수"/>
  </sections>

  <h2_strategy name="소제목 작성 전략 (AEO+SEO)">
    <type name="질문형" strength="AEO 최강">청년 기본소득, 신청 방법은?</type>
    <type name="명사형" strength="SEO 기본">분당구 정자동 주차장 신설 위치</type>
    <type name="데이터" strength="신뢰성">2025년 상반기 5대 주요 성과</type>
    <type name="절차" strength="실용성">청년 기본소득 신청 3단계 절차</type>
    <type name="비교" strength="차별화">기존 정책 대비 개선된 3가지</type>
    <banned>추상적 표현("노력", "열전", "마음"), 모호한 제목("정책 안내", "소개"), 서술어 포함("~에 대한 설명")</banned>
  </h2_strategy>

  <mandatory_rules>
    <rule id="html_tags">소제목은 &lt;h2&gt;, 문단은 &lt;p&gt; 태그만 사용 (마크다운 ** 금지)</rule>
    <rule id="no_slogan_repeat" severity="critical">입장문의 맺음말/슬로건을 각 섹션 끝마다 반복 금지. 모든 호소와 다짐은 맨 마지막 결론부에만.</rule>
    <rule id="sentence_completion">문장은 올바른 종결 어미(~입니다, ~합니다, ~시오)로 끝내야 함. 고의적 오타/잘린 문장 금지.</rule>
    <rule id="keyword_per_section">각 섹션마다 키워드 1개 이상 포함</rule>
    <rule id="separate_pledges">본론 1, 2, 3은 각각 다른 주제/공약을 다룰 것</rule>
    <rule id="verb_diversity" severity="critical">같은 동사(예: "던지면서")를 원고 전체에서 3회 이상 사용 금지. 동의어 교체: 제시하며, 약속하며, 열며, 보여드리며 등.</rule>
    <rule id="slogan_once">캐치프레이즈("청년이 돌아오는 부산")나 비유("아시아의 싱가포르")는 결론부 1회만. 다른 섹션에서는 변형 사용.</rule>
    <rule id="natural_keyword">키워드만으로 구성된 단독 문장 금지. 앞 문단과 연결어로 이어서 자연스럽게 배치.</rule>
    <rule id="causal_clarity">성과 언급 시 본인의 구체적 역할/직책 명시. "40% 득표율을 이끌어냈다" → "시당위원장으로서 지역 조직을 총괄하며 40% 득표율 달성에 기여했습니다"</rule>
  </mandatory_rules>

  <constraints warning="위반 시 자동 반려">
    <max_chars>{max_total_chars}</max_chars>
    <min_chars>{min_total_chars}</min_chars>
    <no_repeat>같은 문장, 같은 표현 반복 금지 (특히 "~바랍니다" 반복 금지)</no_repeat>
    <html>문단은 &lt;p&gt;...&lt;/p&gt;, 소제목은 &lt;h2&gt;...&lt;/h2&gt;만 사용</html>
    <separate_pledges>서로 다른 공약/정책은 하나의 본론에 합치지 말 것</separate_pledges>
  </constraints>

  <output_format>템플릿에서 지시한 XML 태그(title, content, hashtags)만 출력. output 래퍼나 마크다운 코드블록 금지.</output_format>
</structure_guide>
"""

        # SEO 지침 생성
        seo_instruction = build_seo_instruction({
            'keywords': params.get('userKeywords', []),
            'targetWordCount': params.get('targetWordCount', 2000)
        })

        # 선거법 준수 지침 생성
        user_status = user_profile.get('status', '준비')
        election_instruction = get_prompt_instruction(user_status)

        return f"""
{template_prompt}

{params.get('partyStanceGuide') or ''}

{seo_instruction}

{election_instruction}

{ref_section}

{context_injection}

{bio_warning}

{structure_enforcement}
""".strip()

    def build_author_bio(self, user_profile: Dict) -> tuple[str, str]:
        # 방어 코드 - list로 전달되는 경우 방어
        if not isinstance(user_profile, dict):
            user_profile = {}

        name = user_profile.get('name', '사용자')
        party_name = user_profile.get('partyName', '')
        current_title = user_profile.get('customTitle') or user_profile.get('position', '')
        basic_bio = " ".join(filter(None, [party_name, current_title, name]))

        career = user_profile.get('careerSummary') or user_profile.get('bio', '')
        slogan = f'"{user_profile.get("slogan")}"' if user_profile.get('slogan') else ''
        donation = f'[후원 안내] {user_profile.get("donationInfo")}' if user_profile.get('donationInfo') else ''

        return f"{basic_bio}\n{career}\n{slogan}\n{donation}".strip(), name

    def is_current_lawmaker(self, user_profile: Dict) -> bool:
        # 방어 코드 - list로 전달되거나 None인 경우 방어
        if not user_profile or not isinstance(user_profile, dict):
            return False
        status = user_profile.get('status', '')
        position = user_profile.get('position', '')
        title = user_profile.get('customTitle', '')

        elected_keywords = ['의원', '구청장', '군수', '시장', '도지사', '교육감']
        text_to_check = status + position + title
        return any(k in text_to_check for k in elected_keywords)

    def parse_response(self, response: str) -> Dict[str, str]:
        if not response:
            return {'content': '', 'title': ''}
        
        # XML Tag Extraction
        try:
            # Title extraction
            title_match = re.search(r'<title>(.*?)</title>', response, re.DOTALL | re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ''
            
            # Content extraction
            content_match = re.search(r'<content>(.*?)</content>', response, re.DOTALL | re.IGNORECASE)
            content = content_match.group(1).strip() if content_match else ''
            
            if not content:
                # Fallback: try to find just HTML tags if XML tags are missing
                print('⚠️ [StructureAgent] XML 태그 누락, HTML 직접 추출 시도')
                html_block_match = re.search(r'<(?:p|h[23])[^>]*>[\s\S]*<\/(?:p|h[23])>', response, re.IGNORECASE)
                if html_block_match:
                    content = html_block_match.group(0)
                else:
                    content = response # 최후단: 전체 텍스트
            
            print(f"✅ [StructureAgent] 파싱 성공: content={len(content)}자")
            return {'content': content, 'title': title}
            
        except Exception as e:
            print(f"⚠️ [StructureAgent] 파싱 에러: {str(e)}")
            return {'content': response, 'title': ''}

    def validate_output(self, content: str, target_word_count: int) -> Dict:
        if not content:
            return {'passed': False, 'reason': '내용 없음', 'feedback': '내용이 비어있습니다.'}
        
        plain_length = len(strip_html(content))
        
        # 분량 규칙: 5~7섹션 × (350~450)자 = 1750~3150자
        # 동적 구조에 맞춰 여유있게 설정
        min_length = 1750  # 5섹션 × 350자
        max_length = 3150  # 7섹션 × 450자

        if plain_length < min_length:
            deficit = min_length - plain_length
            return {
                'passed': False,
                'reason': f"분량 부족 ({plain_length}자 < {min_length}자)",
                'feedback': f"현재 분량({plain_length}자)이 최소 기준({min_length}자)보다 {deficit}자 부족합니다. 각 섹션을 400자 안팎으로 작성하고, 문단당 120~150자를 유지하십시오."
            }
        
        if plain_length > max_length:
            excess = plain_length - max_length
            return {
                'passed': False,
                'reason': f"분량 초과 ({plain_length}자 > {max_length}자)",
                'feedback': f"현재 분량({plain_length}자)이 최대 기준({max_length}자)을 {excess}자 초과했습니다. 각 섹션을 400자 안팎으로 압축하고, 불필요한 반복이나 사족을 제거하십시오. 7개 섹션을 넘기지 마십시오."
            }
        
        h2_count = len(re.findall(r'<h2>', content, re.IGNORECASE))
        if h2_count < 4:
            return {
                'passed': False,
                'reason': f"소제목 부족 (현재 {h2_count}개)",
                'feedback': "소제목(<h2>)이 부족합니다. 반드시 4개 이상의 소제목(본론 3개 + 결론 1개 등)을 포함해야 합니다."
            }
        
        if h2_count > 6:
            return {
                'passed': False,
                'reason': f"소제목 과다 (현재 {h2_count}개)",
                'feedback': "소제목(<h2>)이 너무 많습니다. 최대 6개(본론 5개 + 결론 1개)를 넘기지 마십시오."
            }

        p_count = len(re.findall(r'<p>', content, re.IGNORECASE))
        expected_min_p = (h2_count + 1) * 3  # 도입부 포함, 섹션당 3문단
        expected_max_p = (h2_count + 1) * 4  # 여유분
        
        if p_count < expected_min_p:
             return {
                'passed': False,
                'reason': f"문단 수 부족 (현재 {p_count}개, 필요 {expected_min_p}개 이상)",
                'feedback': f"문단 수가 너무 적습니다. {h2_count + 1}개 섹션에 대해 섹션당 3개 문단씩 총 {expected_min_p}개 이상 필요합니다."
            }

        return {'passed': True}
