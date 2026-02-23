# functions/python/agents/common/h2_guide.py
"""AEO+SEO 최적화 H2 소제목 작성 가이드 (few-shot 예시 포함)"""


def build_h2_examples() -> str:
    """H2 소제목 few-shot 예시 XML 블록을 반환한다."""
    return """
<h2_examples name="소제목 교정 예시 (bad → good)">
  <type name="질문형" strength="AEO 최강">
    <good>청년 기본소득, 신청 방법은 무엇인가요?</good>
    <good>분당구 주차장, 어디에 새로 생기나요?</good>
    <good>보육료 지원, 얼마까지 받을 수 있나요?</good>
    <good>전세 사기 피해, 어떻게 보상받나요?</good>
    <good>2025년 예산안, 무엇이 달라졌나요?</good>
    <correction before="청년 기본소득에 대한 상세한 설명" after="청년 기본소득, 신청 방법은?"/>
    <correction before="이것을 꼭 알아야 합니다" after="보육료 지원 자격, 확인 방법은?"/>
    <correction before="청년 지원 정책에 관한 모든 것을 알려드립니다" after="청년 기본소득, 어떻게 신청하나요?"/>
  </type>

  <type name="명사형" strength="SEO 기본">
    <good>청년 기본소득 신청 자격 조건</good>
    <good>분당구 정자동 주차장 신설 위치</good>
    <good>2025년 상반기 예산 집행 현황</good>
    <good>청년 창업 지원 정책 상세 안내</good>
    <good>민원 처리 평균 소요 기간</good>
    <correction before="정책" after="청년 기본소득 신청 자격"/>
    <correction before="우리 지역의 발전을 위한 노력" after="분당구 주차장 50면 추가 건설"/>
    <correction before="여러 가지 사업들" after="청년 일자리·주거 지원 사업"/>
  </type>

  <type name="데이터" strength="신뢰성">
    <good>2025년 상반기 5대 주요 성과</good>
    <good>청년 일자리 274명 창출 방법</good>
    <good>민원 처리 14일→3일 단축 과정</good>
    <good>국비 120억 확보 세부 내역</good>
    <good>교통 사고율 40% 감소 요인 분석</good>
    <correction before="좋은 성과를 냈습니다" after="청년 일자리 274명 창출 성과"/>
    <correction before="예산을 많이 확보했어요" after="국비 120억 확보 성공"/>
    <correction before="개선되었습니다" after="민원 처리 14일→3일 개선"/>
  </type>

  <type name="절차" strength="실용성">
    <good>청년 기본소득 신청 3단계 절차</good>
    <good>온라인 민원 신청 필수 서류 목록</good>
    <good>보육료 지원금 수령까지 소요 기간</good>
    <good>주차장 건설 추진 일정 및 완공일</good>
    <good>전세 사기 피해 신고 방법 안내</good>
    <correction before="신청하는 방법" after="청년 기본소득 신청 3단계"/>
    <correction before="이렇게 하면 됩니다" after="온라인 민원 신청 필수 서류"/>
    <correction before="준비 사항에 대하여" after="청년 창업 지원 신청 준비 서류"/>
  </type>

  <type name="비교" strength="차별화">
    <good>청년 기본소득 vs 청년 수당 차이점</good>
    <good>2024년 vs 2025년 예산 변화 분석</good>
    <good>기존 정책 대비 개선된 3가지</good>
    <good>온라인 vs 오프라인 신청 장단점</good>
    <good>타 지역 대비 분당구만의 특징</good>
    <correction before="비교해 보겠습니다" after="청년 기본소득 vs 청년수당 비교"/>
    <correction before="다른 정책들과의 차이" after="기존 정책 대비 개선된 5가지"/>
    <correction before="장점과 단점" after="온라인 vs 오프라인 신청 비교"/>
  </type>

  <checklist>
    <must>12~30자 범위 (네이버 최적 15~22자)</must>
    <must>핵심 키워드를 앞 1/3에 배치</must>
    <must>질문형 또는 명확한 명사형 구조</must>
    <must>H2 바로 아래 첫 문장(40~60자)은 직접 답변</must>
    <ban>8자 미만 또는 30자 초과</ban>
    <ban>"이것", "그것", "관련" 등 모호한 지시어</ban>
    <ban>"최고", "혁명적", "놀라운" 등 과장 표현</ban>
    <ban>키워드 없는 추상적 표현 ("노력", "열심히")</ban>
    <ban>"~에 대한", "~관련" 등 불필요한 접속사</ban>
  </checklist>
</h2_examples>
"""
