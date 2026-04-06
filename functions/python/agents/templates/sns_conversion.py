"""
SNS 플랫폼별 변환 프롬프트 빌더.
Node.js `prompts/builders/sns-conversion.js`의 Python 포팅 버전이다.

주의:
- Facebook/Instagram은 단일 게시물, X/Threads는 타래 형식을 사용한다.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict

# 예시 원고(사용자 제공) 기반 X 평균 길이(공백 제외) 정책값
X_TARGET_AVG_NON_SPACE = 111
X_MIN_NON_SPACE = 60
THREADS_MIN_NON_SPACE = 120

# SNS 플랫폼별 제한사항
SNS_LIMITS: Dict[str, Dict[str, Any]] = {
    "facebook-instagram": {
        "minLength": 300,
        "maxLength": 1000,
        "hashtagLimit": 5,
        "charsPerLine": 22,
        "previewLimit": 125,
        "name": "Facebook/Instagram",
        "isThread": False,
    },
    "x": {
        "maxLengthPerPost": X_TARGET_AVG_NON_SPACE,
        "minLengthPerPost": X_MIN_NON_SPACE,
        "recommendedMinLength": X_TARGET_AVG_NON_SPACE,
        "hashtagLimit": 2,
        "charsPerLine": 32,
        "name": "X(Twitter)",
        "isThread": True,
        "minPosts": 1,
        "maxPosts": 1,
    },
    "threads": {
        "maxLengthPerPost": 350,
        "minLengthPerPost": THREADS_MIN_NON_SPACE,
        "recommendedMinLength": 250,
        "hashtagLimit": 3,
        "charsPerLine": 27,
        "name": "Threads",
        "isThread": True,
        "minPosts": 2,
        "maxPosts": 5,
    },
}


def build_sns_natural_tone_guide() -> str:
    return """
<natural_tone_guide description="자연스러운 문체 - LLM 말투 금지">
  <rule type="must-not">"결론적으로", "요약하면", "~것 같습니다", "~할 필요가 있습니다"</rule>
  <rule type="must">핵심부터 시작, 단정형 종결(~입니다), 행동형 문장(~하겠습니다)</rule>
</natural_tone_guide>
""".strip()


def clean_html_content(original_content: str) -> str:
    text = original_content or ""
    text = re.sub(r"</?(h[1-6]|p|div|br|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_topic_and_title_block(options: Dict[str, Any]) -> str:
    topic = (options or {}).get("topic", "")
    title = (options or {}).get("title", "")
    topic_block = (
        f'\n<core_topic priority="highest">\n'
        f'  <message>{topic}</message>\n'
        f'  <instruction>이 주제의 핵심 메시지와 CTA를 반드시 보존하세요.</instruction>\n'
        f'</core_topic>\n'
        if topic
        else ""
    )
    title_block = f"<source_title>{title}</source_title>\n" if title else ""
    return f"{topic_block}{title_block}"


def _resolve_source_label(options: Dict[str, Any]) -> str:
    source_type = str((options or {}).get("sourceType") or "").strip().lower()
    if source_type in {"position_statement", "statement", "stance", "facebook_post", "facebook", "fb"}:
        return "내 입장문/페이스북 글"
    return "블로그 원고"


def build_facebook_instagram_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Dict[str, Any] | None = None,
) -> str:
    options = options or {}
    min_len = int(platform_config.get("minLength", 300))
    max_len = int(platform_config.get("maxLength", 1000))
    hashtag_limit = int(platform_config.get("hashtagLimit", 5))
    chars_per_line = int(platform_config.get("charsPerLine", 22))
    quality_issues = options.get("qualityIssues", [])
    natural_tone_guide = build_sns_natural_tone_guide()
    extra_context = _build_topic_and_title_block(options)
    source_label = _resolve_source_label(options)

    remediation_block = ""
    if isinstance(quality_issues, list) and quality_issues:
        remediation = "\n".join(f"  <issue>{item}</issue>" for item in quality_issues if str(item).strip())
        if remediation:
            remediation_block = f"""
<remediation_instructions reason="이전 결과 보정">
  <instruction>이전 결과에서 아래 문제가 확인되었습니다. 반드시 모두 해결하세요.</instruction>
{remediation}
</remediation_instructions>
"""

    return f"""
<task type="SNS 변환" platform="facebook-instagram" mode="공용 단일 게시물" system="전자두뇌비서관">
  <source_info>
    <author_name>{user_info.get('name', '정치인')}</author_name>
    <author_role>{user_info.get('position', '의원')}</author_role>
    <instruction>{source_label}을 Facebook 게시물과 Instagram 캡션에 모두 사용할 수 있는 단일 SNS 원고로 변환하라.</instruction>
  </source_info>

{extra_context}

  <source_content>
{clean_content}
  </source_content>

{natural_tone_guide}

  <transformation_policy priority="critical">
    <rule>변환 목적은 신규 원고 작성이 아니라 원문을 SNS용 단일 게시물로 압축/재배열하는 것이다.</rule>
    <rule>원문의 핵심 표현, 고유명사, 숫자, 정책명을 최대한 재사용한다.</rule>
    <rule>원문에 없는 주장, 수치, 사례, 구호를 새로 만들지 않는다.</rule>
    <rule>원문 핵심어(고유명사/숫자/정책명) 3개 이상을 본문에 그대로 유지한다.</rule>
  </transformation_policy>

  <platform_strategy>
    <description>Facebook과 Instagram에서 모두 자연스럽게 읽히는 단일 게시물이어야 한다.</description>
    <rule>첫 2~3줄 안에 핵심 메시지와 맥락을 배치해 두 플랫폼의 미리보기 구간에서도 의미가 전달되게 한다.</rule>
    <rule>모바일 가독성을 위해 한 줄을 {chars_per_line}자 내외로 유지한다.</rule>
    <rule>Instagram식 해시태그 과다 사용과 Facebook식 장문 서론을 모두 피하고 균형을 맞춘다.</rule>
    <rule>해시태그는 본문 하단에 최대 {hashtag_limit}개만 배치한다.</rule>
  </platform_strategy>

  <content_structure>
    <section order="1" name="훅">첫 문장은 독자가 바로 핵심 이슈를 이해할 수 있게 작성</section>
    <section order="2" name="핵심 요약">바쁜 독자를 위한 2~4줄 요약</section>
    <section order="3" name="상세 설명">배경, 정책 내용, 수치, 기대효과를 해설형으로 설명</section>
    <section order="4" name="마무리">개인적 소회, 책임감, 다짐 중 하나로 정리</section>
    <section order="5" name="짧은 CTA">댓글/공감/공유를 유도하되 1문장 이내로 유지</section>
    <section order="6" name="해시태그">최대 {hashtag_limit}개</section>
  </content_structure>

  <writing_rules>
    <rule>길이는 {min_len}~{max_len}자(공백 포함) 범위에서 작성한다.</rule>
    <rule>요약보다 해설형에 가깝게 작성하되, 불필요한 군더더기는 줄인다.</rule>
    <rule>원문 문장 또는 원문 어절을 직접 재사용한 구문을 1개 이상 포함한다.</rule>
    <rule>원문의 정치적 입장과 논조를 완전 보존한다.</rule>
    <rule>원문에 없는 사실/수치/사례 추가 금지</rule>
    <rule>이모지는 0~3개만 사용하고, 없어도 무방하다.</rule>
    <rule>Facebook에서도 어색하지 않도록 인스타 전용 SEO 문구나 과도한 해시태그 반복을 금지한다.</rule>
  </writing_rules>

  <anti_patterns priority="critical">
    <item>"자세한 내용은 블로그에서" 같은 저품질 CTA 문구</item>
    <item>Instagram 전용 밈/해시태그를 과도하게 나열해 Facebook 문맥에서 어색해지는 결과</item>
    <item>원문에 없는 정책/수치/사례 창작</item>
    <item>문단마다 느낌표/감탄사를 남발하는 과장형 문체</item>
    <item>타래처럼 번호를 붙이거나 게시물을 여러 개로 나누는 형식</item>
  </anti_patterns>

{remediation_block}

  <output_contract format="json">
{{
  "content": "Facebook/Instagram 공용 단일 게시물 텍스트",
  "hashtags": ["#태그1", "#태그2", "#태그3"],
  "wordCount": 780
}}
  </output_contract>

  <final_checklist>
    <item>단일 게시물 JSON 형식(content, hashtags, wordCount)인가?</item>
    <item>첫 2~3줄 안에 핵심 메시지와 맥락이 들어갔는가?</item>
    <item>원문 고유명사/숫자/정책명을 3개 이상 반영했는가?</item>
    <item>Facebook과 Instagram 모두에서 자연스러운 어조인가?</item>
    <item>해시태그가 {hashtag_limit}개 이하인가?</item>
  </final_checklist>
</task>
""".strip()


def build_x_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Dict[str, Any] | None = None,
) -> str:
    options = options or {}
    hashtag_limit = platform_config.get("hashtagLimit", 2)
    min_len = platform_config.get("minLengthPerPost", X_MIN_NON_SPACE)
    recommended_len = platform_config.get("recommendedMinLength", X_TARGET_AVG_NON_SPACE)
    max_len = platform_config.get("maxLengthPerPost", X_TARGET_AVG_NON_SPACE)
    blog_url = options.get("blogUrl", "")
    category = options.get("category", "")
    sub_category = options.get("subCategory", "")
    quality_issues = options.get("qualityIssues", [])
    natural_tone_guide = build_sns_natural_tone_guide()
    extra_context = _build_topic_and_title_block(options)
    source_label = _resolve_source_label(options)

    # Node 로직과 유사한 분기
    is_friendly_style = category in {"일상 소통", "daily-communication"} or (
        category in {"지역 현안 및 활동", "local-issues"} and sub_category in {"봉사 후기", "volunteer-review"}
    )
    style_name = "친근한 리더 (이재명 스타일)" if is_friendly_style else "공식적 리더 (김민석 스타일)"

    style_guide = (
        """
<style_profile id="friendly_leader" name="친근한 리더 (이재명 스타일)">
  <trait>비격식체, 친근한 어조</trait>
  <trait>이모지 허용: ^^, ㅎㅎ, 😁 (과도 사용 금지)</trait>
  <trait>유머/밈/신조어 제한적 허용</trait>
  <trait>인간적 에피소드와 공감형 훅</trait>
  <trait>멘션(@) 활용 가능</trait>
</style_profile>
""".strip()
        if is_friendly_style
        else """
<style_profile id="official_leader" name="공식적 리더 (김민석 스타일)">
  <trait>격식체, 공식적 어조</trait>
  <trait>이모지 금지</trait>
  <trait>차분하고 신뢰감 있는 표현</trait>
  <trait>느낌표 절제</trait>
  <trait>역사적/제도적 맥락 강조</trait>
</style_profile>
""".strip()
    )

    remediation_block = ""
    if isinstance(quality_issues, list) and quality_issues:
        remediation = "\n".join(f"  <issue>{item}</issue>" for item in quality_issues if str(item).strip())
        if remediation:
            remediation_block = f"""
<remediation_instructions reason="이전 결과 보정">
  <instruction>이전 결과에서 아래 문제가 확인되었습니다. 반드시 모두 해결하세요.</instruction>
{remediation}
</remediation_instructions>
"""

    blog_line = f"- 블로그 링크: {blog_url}" if blog_url else "- 블로그 링크: https://..."
    link_hint = blog_url or "https://..."

    return f"""
<task type="SNS 변환" platform="x" mode="임팩트 헤드라인" system="전자두뇌비서관">
  <source_info>
    <author_name>{user_info.get('name', '정치인')}</author_name>
    <author_role>{user_info.get('position', '의원')}</author_role>
    <instruction>{source_label}을 X 게시물 1개로 변환하라.</instruction>
  </source_info>

{extra_context}

  <source_content>
{clean_content}
  </source_content>

{natural_tone_guide}

  <transformation_policy priority="critical">
    <rule>변환 목적은 신규 원고 작성이 아니라 원문 압축/재배열입니다.</rule>
    <rule>원문의 핵심 표현을 최대한 재사용하고, 길이 제약으로 인한 축약만 허용합니다.</rule>
    <rule>원문에 없는 구호/슬로건/브랜딩 문구를 새로 만들지 않습니다.</rule>
    <rule>원문 핵심어(고유명사/숫자/정책명) 3개 이상을 본문에 그대로 포함합니다.</rule>
  </transformation_policy>

  <platform_strategy>
    <description>X는 훑어보는 플랫폼이므로 1개 게시물에 핵심 메시지와 임팩트 요소를 동시에 담아야 한다.</description>
    <selected_style>{style_name}</selected_style>
{style_guide}
  </platform_strategy>

  <extraction_steps>
    <step order="1">
      <item>고유명사/상징: 장소명, 이벤트명, 인물명</item>
      <item>차별화 포인트: 최초/유일/혁신 등 독보 가치</item>
      <item>수치/규모: 퍼센트, 예산, 건수, 일자리 등 숫자</item>
      <item>실질적 혜택: 누구에게 어떤 변화가 있는지</item>
      <item>감성적 훅: 질문, 공감, 기억 환기</item>
      <item>서사적 대비: 출신↔현재, 위기↔비전, 숫자↔숫자</item>
    </step>
    <step order="2">
      <item>감성 훅 또는 핵심 메시지로 시작</item>
      <item>원본의 임팩트 요소 1~2개 포함</item>
      <item>구체적 정책/활동 1개 언급</item>
      <item>길이: 권장 {recommended_len}자 내외, 최대 {max_len}자 (공백 제외)</item>
      <item>블로그 링크는 게시물 마지막 줄에 URL만 1회 배치</item>
      <item>해시태그: 최대 {hashtag_limit}개</item>
      <item>{blog_line}</item>
    </step>
  </extraction_steps>

  <writing_rules>
    <rule>최대 {max_len}자 이내(공백 제외)로 작성하고, 분량을 억지로 채우지 않습니다.</rule>
    <rule>줄바꿈 카드형 구성(2~5줄)으로 가독성 확보</rule>
    <rule>원본 고유명사/핵심 수치/핵심 주장 최소 1개 이상 포함</rule>
    <rule>원문 문장 또는 원문 어절을 직접 재사용한 구문을 1개 이상 포함</rule>
    <rule>인사/서론 금지, 핵심부터 시작</rule>
    <rule>원본에 없는 사실/수치 추가 금지</rule>
    <rule>원문에 없는 가치판단/수식어 확장 최소화</rule>
    <rule>정치적 입장과 논조 보존</rule>
  </writing_rules>

  <anti_patterns priority="critical">
    <item>"자세한 내용은 블로그에서 확인하세요" 같은 저품질 CTA 문구</item>
    <item>링크 앞 장황한 안내 문구</item>
    <item>블로그 링크를 중간에 넣거나 두 번 이상 반복</item>
    <item>원본 키워드 없는 일반 요약</item>
    <item>원문에 없는 새로운 구호/캐치프레이즈 창작</item>
    <item>느낌표/감탄사 남발</item>
  </anti_patterns>

  <style_hints type="few_shot">
    <hint>첫 줄 훅 + 줄바꿈 카드형 + 구체적 사실 + 링크 + 해시태그의 순서를 우선</hint>
    <hint>길이를 줄이려면 형용사보다 고유명사/숫자를 남긴다</hint>
    <hint>신뢰감이 필요한 이슈에서는 차분한 단정형 종결을 사용한다</hint>
  </style_hints>

{remediation_block}

  <output_contract format="json">
{{
  "posts": [
    {{
      "order": 1,
      "content": "[훅/핵심 메시지]\\n\\n[임팩트 요소 + 정책]\\n\\n#태그1 #태그2\\n{link_hint}",
      "wordCount": 148
    }}
  ],
  "hashtags": ["#태그1", "#태그2"],
  "totalWordCount": 148,
  "postCount": 1
}}
  </output_contract>

  <final_checklist>
    <item>{max_len}자 이하인가?</item>
    <item>원본의 고유명사/수치/핵심 주장을 1개 이상 반영했는가?</item>
    <item>원문 어절/문장을 재사용한 구문이 포함되었는가?</item>
    <item>저품질 CTA 문구가 없는가?</item>
    <item>블로그 링크가 본문에 포함되어 있는가?</item>
  </final_checklist>
</task>
""".strip()


def build_threads_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Dict[str, Any] | None = None,
) -> str:
    options = options or {}
    hashtag_limit = platform_config.get("hashtagLimit", 3)
    min_posts = platform_config.get("minPosts", 2)
    max_posts = platform_config.get("maxPosts", 5)
    min_len = platform_config.get("minLengthPerPost", THREADS_MIN_NON_SPACE)
    max_len = platform_config.get("maxLengthPerPost", 350)
    recommended_len = platform_config.get("recommendedMinLength", 250)
    target_post_count = options.get("targetPostCount")
    blog_url = options.get("blogUrl", "")
    quality_issues = options.get("qualityIssues", [])
    natural_tone_guide = build_sns_natural_tone_guide()
    extra_context = _build_topic_and_title_block(options)
    source_label = _resolve_source_label(options)

    post_count_guidance = (
        f"게시물 수는 {target_post_count}개로 맞춰주세요."
        if target_post_count
        else f"게시물 수는 원문 분량에 맞게 {min_posts}~{max_posts}개에서 선택하세요."
    )
    blog_line = f"- 블로그 링크 포함: {blog_url}" if blog_url else "- 블로그 링크 포함 가능"
    link_hint = blog_url or "https://..."

    remediation_block = ""
    if isinstance(quality_issues, list) and quality_issues:
        remediation = "\n".join(f"  <issue>{item}</issue>" for item in quality_issues if str(item).strip())
        if remediation:
            remediation_block = f"""
<remediation_instructions reason="이전 결과 보정">
  <instruction>이전 결과에서 아래 문제가 확인되었습니다. 반드시 모두 해결하세요.</instruction>
{remediation}
</remediation_instructions>
"""

    return f"""
<task type="SNS 변환" platform="threads" mode="맥락 설명 타래" system="전자두뇌비서관">
  <source_info>
    <author_name>{user_info.get('name', '정치인')}</author_name>
    <author_role>{user_info.get('position', '의원')}</author_role>
    <instruction>{source_label}을 Threads 타래로 변환하라.</instruction>
  </source_info>

{extra_context}

  <source_content>
{clean_content}
  </source_content>

{natural_tone_guide}

  <transformation_policy priority="critical">
    <rule>Threads 변환은 원문을 게시물 단위로 분해/재배열하는 작업입니다.</rule>
    <rule>각 게시물은 원문 문장(또는 절)을 압축 편집해 구성하고 새 서사를 만들지 않습니다.</rule>
    <rule>원문에 없는 새로운 주장/수치/구호를 추가하지 않습니다.</rule>
    <rule>타래 전체에서 원문 핵심어(고유명사/숫자/정책명) 5개 이상을 그대로 유지합니다.</rule>
  </transformation_policy>

  <platform_strategy>
    <description>Threads는 대화와 맥락을 쌓는 플랫폼이므로, 왜 중요한지와 무엇을 할 것인지를 단계적으로 설명한다.</description>
    <post_count_guidance>{post_count_guidance}</post_count_guidance>
    <link_guidance>{blog_line}</link_guidance>
  </platform_strategy>

  <thread_structure post_range="{min_posts}-{max_posts}" length_per_post="권장 {recommended_len}자 내외, 최대 {max_len}자">
    <rule>각 게시물은 X보다 길고 설명적으로 작성</rule>
    <post order="1" role="요약+훅">
      <item>핵심 메시지와 배경을 함께 담은 요약</item>
      <item>인사/서론 없이 핵심부터 시작</item>
      <item>이 게시물만 봐도 전체 맥락 파악 가능</item>
    </post>
    <post order="2" role="맥락 설명">
      <item>왜 이 이슈가 중요한지</item>
      <item>현황/배경/필요성 설명</item>
    </post>
    <post order="3" role="핵심 내용 또는 근거" optional="true">
      <item>정책/활동/입장의 구체적 내용</item>
      <item>수치/팩트/사례</item>
    </post>
    <post order="4-5" role="추가 설명 또는 전망" optional="true">
      <item>기대효과/향후 계획</item>
      <item>추가 근거나 사례</item>
    </post>
    <post order="last" role="마무리">
      <item>입장 정리 또는 다짐</item>
      <item>해시태그 {hashtag_limit}개 이내</item>
      <item>블로그 링크는 마지막 줄에 URL만 1회 배치</item>
    </post>
  </thread_structure>

  <writing_rules>
    <rule>각 게시물은 독립적으로도 이해 가능해야 함</rule>
    <rule>각 게시물은 필요한 정보만 담아 간결하게 작성하고, 분량을 억지로 늘리지 않습니다.</rule>
    <rule>각 게시물에 원문 표현(문장/어절) 재사용 구문을 1개 이상 포함</rule>
    <rule>게시물 간 중복 문장 최소화</rule>
    <rule>이모지 남발 금지 (필요 시 0~1개)</rule>
    <rule>원본의 정치적 입장과 논조 완전 보존</rule>
    <rule>원본에 없는 사실/수치 추가 금지</rule>
    <rule>마지막 게시물 마지막 줄에만 블로그 링크 URL을 1회 배치하고 별도 CTA는 쓰지 않는다</rule>
  </writing_rules>

  <anti_patterns priority="critical">
    <item>각 게시물이 같은 결론 문장을 반복</item>
    <item>"요약하면/결론적으로" 같은 LLM 상투어 반복</item>
    <item>링크 없는 마무리 또는 해시태그 과다 삽입</item>
  </anti_patterns>

{remediation_block}

  <output_contract format="json">
{{
  "posts": [
    {{ "order": 1, "content": "요약 + 훅", "wordCount": 280 }},
    {{ "order": 2, "content": "맥락 설명", "wordCount": 320 }},
    {{ "order": 3, "content": "핵심 내용/근거", "wordCount": 300 }},
    {{ "order": 4, "content": "마무리\\n#태그1 #태그2 #태그3\\n{link_hint}", "wordCount": 260 }}
  ],
  "hashtags": ["#태그1", "#태그2", "#태그3"],
  "totalWordCount": 1160,
  "postCount": 4
}}
  </output_contract>

  <final_checklist>
    <item>게시물 수가 {min_posts}~{max_posts}개 범위인가?</item>
    <item>각 게시물이 {max_len}자 이하인가?</item>
    <item>타래 전반에서 원문 핵심어/표현 재사용이 충분한가?</item>
    <item>마지막 게시물에 블로그 링크가 포함됐는가?</item>
    <item>게시물 간 중복 문장이 과도하지 않은가?</item>
  </final_checklist>
</task>
""".strip()


def build_sns_prompt(
    original_content: str,
    platform: str,
    platform_config: Dict[str, Any] | None = None,
    post_keywords: str = "",
    user_info: Dict[str, Any] | None = None,
    options: Dict[str, Any] | None = None,
) -> str:
    """
    SNS 변환 프롬프트 생성 메인 함수.
    """
    _ = post_keywords  # 호환 인자 유지
    user_info = user_info or {}
    options = options or {}
    platform = (platform or "").strip().lower()

    if platform_config is None:
        platform_config = SNS_LIMITS.get(platform)
    if not platform_config:
        raise ValueError(f"지원하지 않는 플랫폼입니다: {platform}")

    clean_content = clean_html_content(original_content)

    if platform == "facebook-instagram":
        return build_facebook_instagram_prompt(clean_content, platform_config, user_info, options)
    if platform == "x":
        return build_x_prompt(clean_content, platform_config, user_info, options)
    if platform == "threads":
        return build_threads_prompt(clean_content, platform_config, user_info, options)

    raise ValueError(f"지원하지 않는 플랫폼입니다: {platform}")
