import re
from .daily_communication import EMOTIONAL_ARCHETYPES, NARRATIVE_FRAMES, VOCABULARY_MODULES as DAILY_VOCAB
from .activity_report import DECLARATIVE_STRUCTURES, RHETORICAL_TACTICS, VOCABULARY_MODULES as ACTIVITY_VOCAB
from .policy_proposal import LOGICAL_STRUCTURES, ARGUMENTATION_TACTICS, VOCABULARY_MODULES as POLICY_VOCAB
from .current_affairs import CRITICAL_STRUCTURES, OFFENSIVE_TACTICS, VOCABULARY_MODULES as AFFAIRS_VOCAB
from .local_issues import ANALYTICAL_STRUCTURES, EXPLANATORY_TACTICS, VOCABULARY_MODULES as LOCAL_VOCAB

# ============================================================================
# 일상 소통형 (daily-communication) 지능형 선택기
# ============================================================================

def select_emotional_archetype(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"도와|지지|응원|함께|힘|부탁|죄송|미안|반성|성찰", text):
        return EMOTIONAL_ARCHETYPES["PLEA_AND_PETITION"].id
    
    if re.search(r"만났습니다|들었습니다|사연|이야기|주민|상인|학부모|어르신|청년|아이|가족", text):
        return EMOTIONAL_ARCHETYPES["STORYTELLING_PERSUASION"].id
    
    if re.search(r"우리|함께|모두|다함께|연대|단결|화합|하나|공동체", text):
        return EMOTIONAL_ARCHETYPES["COMMUNITY_APPEAL"].id
    
    if re.search(r"봄|여름|가을|겨울|꽃|나무|하늘|바람|비|눈|아침|저녁|밤|별|달", text):
        return EMOTIONAL_ARCHETYPES["POETIC_LYRICISM"].id
    
    if re.search(r"분노|억울|슬픔|기쁨|희망|두려움|불안|걱정|안타까움|기대", text):
        return EMOTIONAL_ARCHETYPES["EMOTIONAL_INTERPRETATION"].id
    
    return EMOTIONAL_ARCHETYPES["PERSONAL_NARRATIVE"].id

def select_narrative_frame(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"청년|젊은|20대|30대|청춘|미래세대|다음세대", text):
        return NARRATIVE_FRAMES["YOUTH_REPRESENTATIVE"].id
    
    if re.search(r"어려움|힘들|고난|역경|극복|이겨내|헤쳐나가|도전|시련", text):
        return NARRATIVE_FRAMES["OVERCOMING_HARDSHIP"].id
    
    if re.search(r"투쟁|싸움|맞서|저항|개혁|변화|바꾸|혁신|불의|부조리|특권|기득권", text):
        return NARRATIVE_FRAMES["RELENTLESS_FIGHTER"].id
    
    return NARRATIVE_FRAMES["SERVANT_LEADER"].id

def select_daily_vocabulary(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"죄송|미안|부족|반성|도와|지지|응원|함께해|힘", text):
        return DAILY_VOCAB["SINCERITY_AND_APPEAL"].id
    
    if re.search(r"약속|책임|다짐|반드시|꼭|결단|의지|실천|지키겠", text):
        return DAILY_VOCAB["RESPONSIBILITY_AND_PLEDGE"].id
    
    if re.search(r"개혁|변화|투쟁|싸움|맞서|저항|바꾸|혁신|특권|기득권|불의|부조리", text):
        return DAILY_VOCAB["REFORM_AND_STRUGGLE"].id
    
    if re.search(r"가족|어머니|아버지|부모|자식|어려움|힘들|고난|극복|헌신|희생", text):
        return DAILY_VOCAB["HARDSHIP_AND_FAMILY"].id
    
    return DAILY_VOCAB["SOLIDARITY_AND_PEOPLE"].id

# ============================================================================
# 활동 보고형 (activity-report) 지능형 선택기
# ============================================================================

def select_declarative_structure(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"조례|법안|개정|발의|통과|입법|법률|조항", text):
        return DECLARATIVE_STRUCTURES["LEGISLATIVE_REPORT"].id
    
    if re.search(r"예산|확보|배정|억원|조원|만원|사업비|재원|지원금", text):
        return DECLARATIVE_STRUCTURES["BUDGET_REPORT"].id
    
    if re.search(r"성과|결과|해냈습니다|이뤘습니다|완료|달성|실현|결실", text):
        return DECLARATIVE_STRUCTURES["PERFORMANCE_SHOWCASE_REPORT"].id
    
    if re.search(r"원칙|철학|신념|가치|소신|믿음|지향", text):
        return DECLARATIVE_STRUCTURES["PRINCIPLE_DECLARATION"].id
    
    return DECLARATIVE_STRUCTURES["GENERAL_ACTIVITY_REPORT"].id

def select_rhetorical_tactic(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"약속|다짐|반드시|꼭|실천|지키겠습니다", text):
        return RHETORICAL_TACTICS["PLEDGE_EMPHASIS"].id
    
    if re.search(r"해냈습니다|이뤘습니다|성과|결실|완료|달성", text):
        return RHETORICAL_TACTICS["CREDIT_TAKING"].id
    
    if re.search(r"주민|시민|이웃|우리 동네|아이들|어르신|가족|생활|일상", text):
        return RHETORICAL_TACTICS["RELATING_TO_RESIDENTS"].id
    
    return RHETORICAL_TACTICS["FACTS_AND_EVIDENCE"].id

def select_activity_vocabulary(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"반드시|원칙|책임|결단|약속|확고", text):
        return ACTIVITY_VOCAB["RESOLUTE_AND_FIRM"].id
    
    if re.search(r"지역|동네|골목|마을|공동체|이웃|주민", text):
        return ACTIVITY_VOCAB["LOCAL_AND_COMMUNITY"].id
    
    if re.search(r"성과|해결|추진|확보|성공|개선|결실|이뤄냈", text):
        return ACTIVITY_VOCAB["RELIABLE_AND_COMPETENT"].id
    
    return ACTIVITY_VOCAB["FORMAL_AND_REPORTING"].id

# ============================================================================
# 정책 제안형 (policy-proposal) 지능형 선택기
# ============================================================================

def select_logical_structure(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"타지역|다른 지역|비교|우리는|우리 지역은|반면", text):
        return LOGICAL_STRUCTURES["COMPREHENSIVE"].id
    
    if re.search(r"단계|1단계|2단계|로드맵|계획|일정|순서대로|먼저|다음|마지막", text):
         return LOGICAL_STRUCTURES["STEP_BY_STEP"].id
    
    if re.search(r"원인|이유|때문에|결과|따라서|그래서|그러므로", text):
        return LOGICAL_STRUCTURES["PROBLEM_SOLUTION"].id

    if re.search(r"원칙|기준|가치|철학|법치|헌법|책임", text):
        return LOGICAL_STRUCTURES["PRINCIPLE_BASED"].id

    return LOGICAL_STRUCTURES["PROBLEM_SOLUTION"].id

def select_argumentation_tactic(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"효과|변화|개선|긍정|혜택|도움|이익", text):
        return ARGUMENTATION_TACTICS["BENEFIT_EMPHASIS"].id
    
    if re.search(r"과거|역사|사례|비슷|마찬가지|다른|선진국", text):
        return ARGUMENTATION_TACTICS["ANALOGY"].id
    
    return ARGUMENTATION_TACTICS["EVIDENCE_CITATION"].id

def select_policy_vocabulary(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"미래|희망|비전|꿈|새로운|발전", text):
        return POLICY_VOCAB["VISION_AND_HOPE"].id
    
    if re.search(r"행동|동참|참여|함께|지금|바로|나섭시다", text):
        return POLICY_VOCAB["ACTION_URGING"].id
    
    if re.search(r"분석|통계|데이터|체계|합리|장기적", text):
        return POLICY_VOCAB["POLICY_ANALYSIS"].id
    
    return POLICY_VOCAB["RATIONAL_PERSUASION"].id

# ============================================================================
# 시사 비평형 (current-affairs) 지능형 선택기
# ============================================================================

def select_critical_structure(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"문제|심각|우려|위험|부정|비리|특혜|부당|불법", text):
        # I only defined SOLUTION_FIRST, MEDIA_FRAME, FACT_CHECK, PROBLEM_FIRST, POLICY_FAILURE, OFFICIAL_MISCONDUCT in current_affairs.py
        return CRITICAL_STRUCTURES["OFFICIAL_MISCONDUCT_CRITICISM"].id # Approximate mapping
    
    if re.search(r"장점|단점|긍정|부정|한편|반면|그러나|하지만", text):
        return CRITICAL_STRUCTURES["SOLUTION_FIRST_CRITICISM"].id # Fallback
    
    if re.search(r"역사|과거|전통|유래|~년|~시대|당시|그때", text):
        return CRITICAL_STRUCTURES["PROBLEM_FIRST_CRITICISM"].id # Fallback

    return CRITICAL_STRUCTURES["SOLUTION_FIRST_CRITICISM"].id # Default for diagnose situation

def select_offensive_tactic(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    # defined offensive tactics: METAPHORICAL_STRIKE, INDIRECT_CRITICISM_BY_SHARING, SATIRE_AND_PARODY, EXPOSING_CONTRADICTION

    if re.search(r"대안|방안|해법|해결책|제안|개선|바꿔야", text):
        return OFFENSIVE_TACTICS["EXPOSING_CONTRADICTION"].id # Fallback/Approx
    
    if re.search(r"모순|말과 행동|겉과 속|이중|다르다|불일치", text):
        return OFFENSIVE_TACTICS["EXPOSING_CONTRADICTION"].id
    
    return OFFENSIVE_TACTICS["METAPHORICAL_STRIKE"].id # Fallback for deep questioning

def select_affairs_vocabulary(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    if re.search(r"문제|심각|우려|위험|경고|비판|부정|잘못", text):
        # defined: AGGRESSIVE_ATTACK, LEGAL_FACTUAL, SARCASTIC_IRONIC, FORMAL_OFFICIAL
        return AFFAIRS_VOCAB["AGGRESSIVE_ATTACK"].id # Approximate mapping
    
    if re.search(r"분석|평가|진단|고찰|검토|판단|추정", text):
        return AFFAIRS_VOCAB["LEGAL_FACTUAL"].id 
    
    return AFFAIRS_VOCAB["FORMAL_OFFICIAL"].id

# ============================================================================
# 지역 현안형 (local-issues) 지능형 선택기
# ============================================================================

def select_analytical_structure(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    # defined: ISSUE_ANALYSIS, BUDGET_PERFORMANCE, LEGISLATIVE_BASIS, DATA_COMPARATIVE, PERFORMANCE_EVALUATION, TRANSPARENCY, CUSTOMIZED_POLICY

    if re.search(r"현장|방문|직접|둘러|다녀왔습니다|가보니|찾아가", text):
        return ANALYTICAL_STRUCTURES["CUSTOMIZED_POLICY_PROPOSAL"].id # Approx
    
    if re.search(r"타지역|다른|비교|우리는|반면|차이|격차", text):
        return ANALYTICAL_STRUCTURES["DATA_COMPARATIVE_ANALYSIS"].id
    
    if re.search(r"역사|전통|과거|옛날|유래|~년|~시대", text):
        return ANALYTICAL_STRUCTURES["ISSUE_ANALYSIS"].id # Fallback
    
    return ANALYTICAL_STRUCTURES["ISSUE_ANALYSIS"].id

def select_explanatory_tactic(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()

    # defined: FACTS_AND_FIGURES, DETAILED_ENUMERATION, ROOT_CAUSE_ANALYSIS, TRANSPARENCY_EMPHASIS

    if re.search(r"주민|의견|목소리|요구|바람|민원|건의|청원", text):
        return EXPLANATORY_TACTICS["TRANSPARENCY_EMPHASIS"].id # Approx
    
    if re.search(r"통계|수치|순위|비율|퍼센트|위|명|건|억원|데이터", text):
        return EXPLANATORY_TACTICS["FACTS_AND_FIGURES"].id
    
    return EXPLANATORY_TACTICS["ROOT_CAUSE_ANALYSIS"].id # Fallback for field observation

def select_local_vocabulary(topic="", instructions=""):
    text = f"{topic} {instructions}".lower()
    
    # defined: DATA_DRIVEN_OBJECTIVE, LEGISLATIVE_AND_FORMAL, LOCAL_AND_CONCRETE, PROBLEM_SOLVING_ORIENTED, COMMUNICATIVE_AND_FRIENDLY

    if re.search(r"자랑|긍지|소중|아름다운|훌륭|특별|유일", text):
        return LOCAL_VOCAB["LOCAL_AND_CONCRETE"].id # Approx
    
    if re.search(r"위기|심각|급박|시급|절박|당장|더이상|한계", text):
        return LOCAL_VOCAB["PROBLEM_SOLVING_ORIENTED"].id # Approx
    
    return LOCAL_VOCAB["LOCAL_AND_CONCRETE"].id

# ============================================================================
# 통합 선택 함수 (Main Entry Point)
# ============================================================================

def select_prompt_parameters(category: str, topic: str, instructions: str = "") -> dict:
    safe_topic = str(topic or "")
    # print(f"🎯 지능형 파라미터 선택 시작 - 카테고리: {category}, 주제: {safe_topic[:50]}...")

    selected_params = {}

    if category == 'daily-communication':
        selected_params = {
            'emotionalArchetypeId': select_emotional_archetype(topic, instructions),
            'narrativeFrameId': select_narrative_frame(topic, instructions),
            'vocabularyModuleId': select_daily_vocabulary(topic, instructions)
        }
    
    elif category == 'activity-report':
        selected_params = {
            'declarativeStructureId': select_declarative_structure(topic, instructions),
            'rhetoricalTacticId': select_rhetorical_tactic(topic, instructions),
            'vocabularyModuleId': select_activity_vocabulary(topic, instructions)
        }
    
    elif category == 'policy-proposal':
        selected_params = {
            'logicalStructureId': select_logical_structure(topic, instructions),
            'argumentationTacticId': select_argumentation_tactic(topic, instructions),
            'vocabularyModuleId': select_policy_vocabulary(topic, instructions)
        }

    elif category == 'educational-content':
        selected_params = {
            'logicalStructureId': select_logical_structure(topic, instructions),
            'argumentationTacticId': select_argumentation_tactic(topic, instructions),
            'vocabularyModuleId': select_policy_vocabulary(topic, instructions)
        }
    
    elif category == 'current-affairs':
        selected_params = {
            'criticalStructureId': select_critical_structure(topic, instructions),
            'offensiveTacticId': select_offensive_tactic(topic, instructions),
            'vocabularyModuleId': select_affairs_vocabulary(topic, instructions)
        }
    
    elif category == 'local-issues':
        selected_params = {
            'analyticalStructureId': select_analytical_structure(topic, instructions),
            'explanatoryTacticId': select_explanatory_tactic(topic, instructions),
            'vocabularyModuleId': select_local_vocabulary(topic, instructions)
        }
    
    else:
        # Default fallback
        selected_params = {
            'emotionalArchetypeId': EMOTIONAL_ARCHETYPES["PERSONAL_NARRATIVE"].id,
            'narrativeFrameId': NARRATIVE_FRAMES["SERVANT_LEADER"].id,
            'vocabularyModuleId': DAILY_VOCAB["SOLIDARITY_AND_PEOPLE"].id
        }
    
    return selected_params
