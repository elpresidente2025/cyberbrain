import logging
from firebase_admin import firestore

COLLECTION_NAME = 'party_stances'

logger = logging.getLogger("theminjoo")

def get_db():
    return firestore.client()

def format_stance_for_prompt(stance_data):
    """Formats the stance data into a string for the LLM prompt."""
    forbidden = stance_data.get('forbidden_phrases', [])
    forbidden_str = ", ".join(forbidden)

    additional = ""
    if stance_data.get('additional_instructions'):
        additional = f"\n4. **[추가 지침]**:\n   {stance_data['additional_instructions']}"

    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🏛️ [CRITICAL] 더불어민주당 공식 당론 가이드 (자동 적용)      ║
╚═══════════════════════════════════════════════════════════════╝

**관련 이슈**: {stance_data.get('title')}

1. **[핵심 입장 - Stance]**:
   "{stance_data.get('stance')}"

2. **[필수 논리 구조 - Logic Guide]**:
   {stance_data.get('logic_guide')}

3. **[절대 금지 표현]**:
   - 금지: {forbidden_str}
   {additional}
"""

def get_party_stance(topic: str):
    """
    Retrieves the most relevant party stance based on the topic.
    Returns the formatted string or None.
    """
    if not topic:
        return None

    try:
        db = get_db()
        # Fetch all active stances
        docs = db.collection(COLLECTION_NAME).where('isActive', '==', True).stream()
        
        matched_stance = None
        max_matched_keywords = 0

        for doc in docs:
            data = doc.to_dict()
            keywords = data.get('keywords', [])
            
            match_count = 0
            for keyword in keywords:
                if keyword in topic:
                    match_count += 1
            
            if match_count > 0 and match_count > max_matched_keywords:
                max_matched_keywords = match_count
                data['id'] = doc.id
                matched_stance = data

        if matched_stance:
            logger.info(f"🏛️ [PartyStance] Found match: '{matched_stance.get('title')}' ({max_matched_keywords} keywords)")
            return format_stance_for_prompt(matched_stance)
        
        return None

    except Exception as e:
        logger.warning(f"❌ [PartyStance] Failed to fetch stances: {e}. Using fallback.")
        return format_stance_for_prompt({
            'title': '더불어민주당 일반 강령 (Fallback)',
            'stance': '민생 우선, 정의로운 대한민국',
            'logic_guide': '- 서민 경제 회복 강조\n- 민주주의 가치 수호',
            'forbidden_phrases': ['독재 타협', '부자 감세'],
            'additional_instructions': '이 내용은 DB 연결 실패 시 제공되는 기본값입니다.'
        })
