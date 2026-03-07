# functions/python/agents/common/seo.py

from .editorial import SEO_RULES, KEYWORD_SPEC, QUALITY_SPEC

def calculate_min_insertions(keyword_count=1):
    """
    ???? ?? ?? ?? ??
    ??? 2? ??: ? 3~4?, ?? 7~8? (15?? ?? ? 2??? 1?)
    """
    if keyword_count >= 2:
        return KEYWORD_SPEC['perKeywordMin']
    return KEYWORD_SPEC['singleKeywordMin']
def calculate_max_insertions(keyword_count=1):
    if keyword_count >= 2:
        return KEYWORD_SPEC['perKeywordMax']
    return KEYWORD_SPEC['singleKeywordMax']

def calculate_distribution(per_keyword):
    """
    ?ㅼ썙??諛곗튂 援ш컙 怨꾩궛 (15臾몃떒 湲곗?, 2臾몃떒??1媛?瑗?
    """
    if per_keyword <= KEYWORD_SPEC['perKeywordMin']:
        return {'intro': 1, 'body': 1, 'conclusion': 1}
    return {
        'intro': 1,
        'body': max(1, per_keyword - 2),
        'conclusion': 1
    }

def build_seo_instruction(params):
    """
    SEO 理쒖쟻??吏移??앹꽦 (XML ?뺤떇)
    """
    keywords = params.get('keywords', [])
    target_word_count = params.get('targetWordCount') or SEO_RULES['wordCount']['target']

    min_len = SEO_RULES['wordCount']['min']
    max_len = SEO_RULES['wordCount']['max']

    kw_count = len(keywords) if keywords else 0
    min_insertions = calculate_min_insertions(kw_count)
    if kw_count >= 2:
        max_per_keyword = KEYWORD_SPEC['perKeywordMax']
    else:
        max_per_keyword = KEYWORD_SPEC['singleKeywordMax']
    distribution = calculate_distribution(min_insertions)
    if kw_count >= 2:
        total_insertions = KEYWORD_SPEC['totalMin']
        total_max_insertions = KEYWORD_SPEC['totalMax']
    else:
        total_insertions = min_insertions * kw_count
        total_max_insertions = max_per_keyword * kw_count

    keyword_section = ''
    if keywords:
        keyword_items = '\n'.join([f'    <keyword text="{kw}" min_count="{min_insertions}" max_count="{max_per_keyword}"/>' for kw in keywords])
        first_kw = keywords[0]

        keyword_section = f"""
  <keywords>
{keyword_items}
    <total_target min="{total_insertions}" max="{total_max_insertions}" note="?ㅼ썙??{kw_count}媛?횞 媛?{min_insertions}~{max_per_keyword}??= 珥?{total_insertions}~{total_max_insertions}??/>
    <distribution intro="{distribution['intro']}" body="{distribution['body']}" conclusion="{distribution['conclusion']}" note="15臾몃떒 湲곗? ??2臾몃떒??1媛?瑗대줈 諛곗튂"/>
    <insertion_method>
      <exact_match severity="critical">?ㅼ썙???먮Ц????湲?먮룄 諛붽씀吏 留먭퀬 ?뺥솗??洹몃?濡??쎌엯??寃? 議곗궗(???/????瑜? 異붽? 湲덉?, ?댁닚 蹂寃?湲덉?, ?꾩뼱?곌린 蹂寃?湲덉?.</exact_match>
      <good>"?대쾲 ?됱궗?먯꽌 {first_kw} 愿???깃낵瑜?怨듭쑀?덉뒿?덈떎." (?ㅼ썙???먮Ц 洹몃?濡?</good>
      <good>"吏??寃쎌젣瑜??대━湲??꾪븳 {first_kw} ?꾨왂??二쇰ぉ諛쏄퀬 ?덉뒿?덈떎." (?ㅼ썙???먮Ц 洹몃?濡?</good>
      <bad>"{first_kw}???깃낵濡?.." ??議곗궗 "?? ?쎌엯?쇰줈 ?ㅼ썙??蹂?뺣맖</bad>
      <bad>"{first_kw}?(??..." ??議곗궗 異붽?濡??ㅼ썙??蹂?뺣맖</bad>
      <bad>?숈씪 臾몃떒??媛숈? ?ㅼ썙??2???댁긽 諛섎났</bad>
      <bad>?ㅼ썙?쒕쭔 ?섏뿴?섎뒗 ?ㅽ꽣??/bad>
      <bad>媛숈? ?ㅼ썙?쒕? ?곗냽 臾몃떒??諛곗튂 (理쒖냼 1臾몃떒 媛꾧꺽 ?좎?)</bad>
    </insertion_method>
  </keywords>
  <keyword_quality severity="critical">
    <bad>?ㅼ썙?쒕쭔?쇰줈 援ъ꽦???낅┰ 臾몄옣: "OO 怨듭빟? ~???꾪븳 ?쎌냽?낅땲??"</bad>
    <bad>臾몃㎘怨?臾닿????ㅼ썙???쎌엯: "OO 愿???꾪솴??諛섎뱶???대쨪??寃껋엯?덈떎."</bad>
    <good>??臾몃떒怨??곌껐???대윭?? ?댁쿂??濡??댁뼱吏???먯뿰?ㅻ윭??臾몄옣 ??諛곗튂</good>
    <good>援ъ껜???뺣낫(?섏튂, ?щ?)? ?④퍡 ?ㅼ썙?쒓? ?깆옣?섎뒗 臾몄옣</good>
    <test>???ㅼ썙?쒕? 鍮쇰룄 臾몄옣???깅┰?섎뒗媛? ??NO硫??먯뿰 ?쎌엯 ?깃났</test>
  </keyword_quality>"""

    checklist_keywords = ''
    if keywords:
        checklist_keywords = f"""
    <item>媛??ㅼ썙?쒕? {min_insertions}~{max_per_keyword}?뚯뵫, 珥?{total_insertions}~{total_max_insertions}???먯뿰?ㅻ읇寃?諛곗튂</item>
    <item>?ㅼ썙?쒓? ?꾩엯遺/蹂몃줎/寃곕줎??怨좊Ⅴ寃?遺꾩궛 (??2臾몃떒??1媛?瑗?</item>
    <item>媛숈? ?ㅼ썙?쒕? ?곗냽 臾몃떒???ｌ? ?딄린 (理쒖냼 1臾몃떒 媛꾧꺽)</item>"""

    return f"""
<seo_rules priority="highest" warning="?꾨컲 ???먭퀬 ?먭린">
  <word_count min="{min_len}" max="{max_len}"/>
{keyword_section}
  <checklist>
    <item>湲?먯닔 {min_len}~{max_len}??踰붿쐞 以??/item>{checklist_keywords}
    <item>?꾩엯-蹂몃줎-寃곕줎 援ъ“濡??댁슜 援ъ꽦</item>
  </checklist>
</seo_rules>
"""

def build_anti_repetition_instruction():
    """
    諛섎났 湲덉? 諛??덉쭏 洹쒖튃 吏移??앹꽦 (XML ?뺤떇)
    """
    return f"""
<anti_repetition_rules severity="critical" warning="위반 시 원고 폐기">
  <rule id="no_duplicate_sentence">
    동일 문장 {QUALITY_SPEC['duplicateSentenceMax'] + 1}회 이상 반복 금지.
  </rule>
  <rule id="no_similar_paragraph">
    같은 주장을 표현만 바꿔 반복하지 않습니다. 각 문단은 새로운 정보/근거를 포함합니다.
  </rule>
  <rule id="no_verb_repeat">
    같은 동사/구문을 원고 전체에서 {QUALITY_SPEC['verbRepeatMax'] + 1}회 이상 사용 금지.
  </rule>
  <rule id="no_slogan_repeat">
    캐치프레이즈/비전 문구/벤치마크 비유는 결론부 {QUALITY_SPEC['sloganMax']}회만 사용.
  </rule>
  <rule id="no_phrase_repeat" severity="critical">
    3어절 이상 동일 구문은 원고 전체에서 {QUALITY_SPEC['phrase3wordMax']}회까지만 허용.
  </rule>
  <checklist>
    <item>동일 문장 {QUALITY_SPEC['duplicateSentenceMax'] + 1}회 이상 반복이 없는가?</item>
    <item>동일 동사/구문 {QUALITY_SPEC['verbRepeatMax'] + 1}회 이상 반복이 없는가?</item>
    <item>슬로건/비유가 결론부 {QUALITY_SPEC['sloganMax']}회로 제한되는가?</item>
    <item>3어절 이상 동일 구문이 {QUALITY_SPEC['phrase3wordMax'] + 1}회 이상 등장하지 않는가?</item>
  </checklist>
</anti_repetition_rules>
"""

