// functions/templates/guidelines/editorial.js - 편집 기준 및 작성 규칙

'use strict';

// ============================================================================
// SEO 최적화 규칙 (네이버 기준)
// ============================================================================

const SEO_RULES = {
  // 분량 규칙
  wordCount: {
    min: 1500,
    max: 2300,
    target: 2050,
    description: '네이버 SEO 최적화를 위한 권장 분량',
    rationale: '1500자 미만은 콘텐츠 부족, 2300자 초과는 가독성 저하'
  },
  
  // 키워드 배치 전략
  keywordPlacement: {
    title: {
      count: 1,
      position: 'natural',
      length: {
        min: 30,
        max: 40,
        description: '제목 권장 길이 30-40자'
      },
      description: '제목에 핵심 키워드 1회, 자연스럽게 배치'
    },
    body: {
      interval: 400,
      method: 'contextual',
      description: '본문 400자당 1회, 맥락에 맞게 자연스럽게 포함',
      avoidance: '키워드 스터핑 금지, 강제 삽입 금지'
    },
    density: {
      optimal: '1.5-2.5%',
      maximum: '3%',
      warning: '3% 초과 시 스팸으로 분류 위험'
    }
  },
  
  // 구조 최적화
  structure: {
    headings: {
      h1: { count: 1, rule: '제목으로만 사용' },
      h2: { count: '2-3개', rule: '주요 섹션 구분' },
      h3: { count: '3-5개', rule: '세부 내용 구조화' },
      h4: { count: '필요시', rule: '상세 분류용' }
    },
    paragraphs: {
      count: '10-15개',
      length: '150-250자',
      rule: '한 문단 하나의 주제'
    },
    lists: {
      usage: '정보 나열 시 적극 활용',
      format: 'HTML ul/ol 태그 사용'
    }
  },
  
  // 검색 최적화 전략
  searchOptimization: {
    titleStrategy: [
      '핵심 키워드 앞쪽 배치',
      '구체적이고 명확한 표현',
      '감정적 어필 요소 포함',
      '지역명/날짜 등 구체 정보 활용',
      '30-40자 길이 준수'
    ],
    contentStrategy: [
      '첫 문단에 주제 명확히 제시',
      '중요 정보는 앞쪽에 배치',
      '관련 키워드 자연스럽게 포함',
      '구체적 수치와 사실 제시'
    ],
    metaStrategy: [
      '읽기 쉬운 문장 구조',
      '전문 용어 최소화',
      '지역 특화 정보 강조'
    ]
  }
};

// ============================================================================
// 콘텐츠 작성 규칙
// ============================================================================

const CONTENT_RULES = {
  // 기본 톤앤매너
  tone: {
    style: {
      formality: '존댓말 사용',
      warmth: '서민적이고 친근한 어조',
      authority: '전문성 있되 권위적이지 않게',
      empathy: '공감대 형성과 포용적 자세'
    },
    voice: {
      firstPerson: {
        basic: '"저는", "제가"',
        guideline: '전체 문장의 30% 이하로 제한',
        alternatives: [
          '명사형 종결로 주어 생략: "이번 정책은 ~한 의미를 갖습니다"',
          '수동태 활용: "이 문제는 반드시 해결되어야 합니다"',
          '주체 전환: "우리 지역구민들께서는", "계양구는", "이번 정책은"',
          '무주어 문장: "더욱 발전된 모습을 보여드리겠습니다"'
        ],
        prohibition: '"저는"으로 연속된 문장 시작 금지'
      },
      secondPerson: '"여러분", "주민 여러분"',
      avoid: ['나는', '당신', '너희']
    },
    prohibitions: [
      '직접 지시/명령 톤 금지',
      '상하관계 암시 표현 금지',
      '일방적 주장 톤 금지'
    ]
  },

  // 문서 구조 가이드
  structure: {
    opening: {
      greeting: '인사말로 시작',
      introduction: '주제 간략 소개',
      connection: '독자와의 접점 마련'
    },
    body: {
      logical: '논리적 순서로 전개',
      evidence: '근거와 사례 제시',
      balance: '다양한 관점 고려'
    },
    closing: {
      summary: '핵심 내용 요약',
      commitment: '향후 계획이나 다짐',
      invitation: '소통 지속 의지 표현'
    }
  },

  // 표현 스타일 가이드
  expression: {
    positive: {
      preferred: [
        '"함께 만들어가겠습니다"',
        '"더 나은 방향으로 발전시키겠습니다"',
        '"주민 여러분과 소통하겠습니다"'
      ],
      tone: '희망적이고 건설적인 메시지'
    },
    inclusive: {
      preferred: [
        '"모든 주민이 함께"',
        '"다양한 의견을 수렴하여"',
        '"포용적 관점에서"'
      ],
      avoid: ['특정 계층만', '일부만', '선별적으로']
    },
    humble: {
      balanced: {
        appropriate: [
          '"더 많이 배우고 노력하겠습니다"',
          '"여러분의 지혜를 모아"',
          '"함께 만들어가겠습니다"'
        ],
        limit: '과도한 자기비하 지양 (사과성 표현 최대 2회)',
        avoidExcessive: [
          '❌ "저의 부족함으로 죄송합니다"',
          '❌ "미흡하지만 용서해주십시오"',
          '❌ "제가 할 수 있을지 모르겠지만"'
        ]
      },
      leadership: {
        preferred: [
          '"제가 책임지겠습니다"',
          '"반드시 추진하겠습니다"',
          '"변화를 이끌겠습니다"',
          '"앞장서서 해결하겠습니다"'
        ],
        tone: '정중하되 확신 있는 어조, 책임감과 결단력 표현',
        allowConfidence: ['확신합니다', '자신있게', '반드시']
      }
    }
  },

  // 문체 품질 기준 (클로바 AI 분석 기반)
  writingStyle: {
    sentenceVariety: {
      principle: '주어와 문장 구조를 다양화하여 글의 흐름 개선',
      firstPersonLimit: {
        ratio: '전체 문장의 30% 이하',
        calculation: '"저는"으로 시작하는 문장 수 / 전체 문장 수',
        warning: '30% 초과 시 단조롭고 자기중심적 인상'
      },
      alternatives: [
        '명사형 종결: "이번 정책은 중요한 의미를 갖습니다"',
        '수동태 활용: "이 문제는 반드시 해결되어야 합니다"',
        '주체 전환: "우리 지역구민들께서는", "계양구는", "이번 행사는"',
        '무주어 문장: "더욱 발전된 모습을 보여드리겠습니다"',
        '도치 구문: "중요한 것은 실천입니다"'
      ],
      prohibitions: [
        '❌ "저는"으로 연속 3문장 이상 시작 금지',
        '❌ 동일 문장 구조 5회 이상 반복 금지'
      ]
    },
    repetitionAvoidance: {
      principle: '같은 표현의 과도한 반복은 글의 품질을 저하시킴',
      rules: [
        '동일 단어: 한 문단 내 3회 이하 (조사, 접속사 제외)',
        '유사 구문: 연속된 문장에서 같은 패턴 반복 금지',
        '접속어: "그리고", "또한" 등 남용 지양'
      ],
      alternatives: '다양한 어휘와 문장 구조로 같은 의미 표현'
    },
    leadershipTone: {
      principle: '과도한 겸손과 적절한 자신감의 균형',
      balanced: {
        responsibility: [
          '"제가 책임지겠습니다"',
          '"반드시 해결하겠습니다"',
          '"앞장서서 추진하겠습니다"'
        ],
        confidence: [
          '"확신을 갖고 말씀드립니다"',
          '"반드시 성과를 내겠습니다"',
          '"자신있게 약속드립니다"'
        ],
        humilityLimit: '사과나 자기비하는 전체 원고에서 최대 2회'
      },
      avoidWeak: [
        '❌ "제가 할 수 있을지 모르겠지만"',
        '❌ "부족하지만 용서해주십시오"',
        '❌ "감히 말씀드리기 어렵지만"'
      ],
      preferStrong: [
        '✅ "최선을 다해 추진하겠습니다"',
        '✅ "책임감을 갖고 임하겠습니다"',
        '✅ "변화를 만들어가겠습니다"'
      ]
    },
    consistency: {
      tone: '전체 원고에서 일관된 톤앤매너 유지',
      perspective: '1인칭 관점 일관성',
      tense: '시제 혼용 방지 (과거-현재 명확히 구분)'
    }
  },

  // 경험 활용 가이드
  experienceIntegration: {
    required: '작성자 자기소개 내용 필수 반영',
    format: [
      '"제가 [구체적 활동/경험]을 통해 느낀 점은..."',
      '"[경험] 과정에서 확인한 바로는..."',
      '"직접 경험해보니..."'
    ],
    purpose: '개인 경험으로 설득력과 진정성 확보',
    balance: '과도한 자기PR 지양, 교훈과 통찰 중심'
  },

  // 호칭 및 정체성 규칙
  identity: {
    audienceAddress: {
      withRegion: '"○○ 주민 여러분"',
      withoutRegion: '"여러분"',
      formal: '"시민 여러분"',
      intimate: '"이웃 여러분"'
    },
    selfReference: {
      incumbent: '"의원으로서"',
      candidate: '"후보로서"',
      preliminary: '"예비후보로서"',
      public: '"한 사람의 시민으로서"'
    },
    statusConsistency: {
      incumbent: '현역 의원은 경험과 성과 기반 발언',
      candidate: '후보는 정책과 공약 중심 발언',
      preliminary: '예비후보는 비전과 계획 중심 발언',
      prohibition: '후보/예비후보가 현역 의원처럼 발언 금지'
    }
  },

  // 인명 및 호칭 규칙 (한국 정치 문화 기반)
  properNouns: {
    principle: '블로그/SNS는 신문 기사가 아님. 반드시 존칭 "님" 사용하여 정치적 예의 준수',

    personalNames: {
      // 국회의원
      nationalAssembly: {
        formats: [
          {
            pattern: '[선거구] [이름] 의원님',
            examples: [
              '✅ "부평구 갑 박성민 의원님"',
              '✅ "계양구 을 강정구 의원님"',
              '✅ "서울 종로구 이영희 의원님"'
            ]
          },
          {
            pattern: '[이름] 의원님([선거구])',
            examples: [
              '✅ "박성민 의원님(부평구 갑)"',
              '✅ "강정구 의원님(계양구 을)"'
            ]
          },
          {
            pattern: '[당명] [이름] 의원님',
            examples: [
              '✅ "더불어민주당 박성민 의원님"',
              '✅ "국민의힘 이영희 의원님"'
            ]
          }
        ],

        electoralDistrict: {
          rule: '선거구는 반드시 "갑/을/병/정" 표기 (법률 문서체 사용 금지)',
          examples: [
            '✅ "부평구 갑", "계양구 을", "강남구 병"',
            '❌ "부평구 제1선거구" (법률 문서체)'
          ]
        },

        prohibited: [
          '❌ "부평구 국회의원 박성민" (영어식 번역투, 어순 부자연)',
          '❌ "국회의원 박성민" (지나치게 격식적)',
          '❌ "박성민 국회의원" (신문 기사체, 님 누락)',
          '❌ "박성민 의원" (님 누락 - 무례함, 항의 위험)'
        ],

        critical: '반드시 "의원님"으로 표기. "의원"만 사용 시 정치적 결례'
      },

      // 지방자치단체장
      localOfficials: {
        formats: [
          {
            pattern: '[이름] [지역명][직책]님',
            examples: [
              '✅ "김철수 계양구청장님"',
              '✅ "박영희 인천시장님"',
              '✅ "이영수 경기도지사님"'
            ]
          },
          {
            pattern: '[지역명] [이름] [직책]님',
            examples: [
              '✅ "계양구 김철수 구청장님"',
              '✅ "인천시 박영희 시장님"'
            ]
          }
        ],

        prohibited: [
          '❌ "계양구청장 김철수" (신문 기사체, 무례함)',
          '❌ "김철수 계양구청장" (님 누락 - 항의 위험)',
          '❌ "계양구 구청장 김철수" (어색한 어순)'
        ],

        critical: '구청장/시장급은 반드시 "님" 필수 - 누락 시 본인 또는 보좌진으로부터 항의 가능성 매우 높음'
      },

      // 정당 직책자
      partyOfficials: {
        formats: [
          {
            pattern: '[당명] [직책] [이름]',
            examples: [
              '✅ "더불어민주당 청년위원장 강정구 위원장님"',
              '✅ "국민의힘 원내대표 이영희 대표님"'
            ]
          },
          {
            pattern: '[이름] [당명] [직책]',
            examples: [
              '✅ "강정구 더불어민주당 청년위원장님"'
            ]
          }
        ],

        note: '직책에 따라 "대표님", "위원장님", "사무총장님" 등 적절한 존칭 사용'
      },

      // 장관급
      ministers: {
        formats: [
          {
            pattern: '[이름] [부처명] 장관님',
            examples: [
              '✅ "이영희 교육부 장관님"',
              '✅ "박철수 국방부 장관님"'
            ]
          },
          {
            pattern: '[부처명] [이름] 장관님',
            examples: [
              '✅ "교육부 이영희 장관님"'
            ]
          }
        ]
      },

      // 대통령 (예외)
      president: {
        format: '[이름] 대통령 / [이름] 전 대통령',
        examples: [
          '✅ "윤석열 대통령"',
          '✅ "문재인 전 대통령"',
          '✅ "박근혜 전 대통령"'
        ],
        exception: '대통령은 직함 자체가 최고 존칭이므로 "님" 생략',
        prohibited: [
          '△ "윤석열 대통령님" (과잉 존칭, 어색함 - 사용 가능하나 권장하지 않음)'
        ]
      },

      // 총리
      primeMinister: {
        format: '[이름] 국무총리',
        examples: [
          '✅ "한덕수 국무총리"',
          '✅ "김부겸 전 국무총리"'
        ],
        note: '총리도 대통령과 마찬가지로 "님" 생략 가능'
      },

      // 일반 시민
      civilians: {
        format: '[이름] 씨',
        examples: [
          '✅ "박영수 씨"',
          '✅ "주민 김철수 씨"',
          '✅ "시민 이영희 씨"'
        ],
        prohibited: [
          '❌ "박영수" (존칭 누락)',
          '❌ "영수씨" (성 누락)'
        ]
      }
    },

    // 후속 언급 규칙
    subsequentMentions: {
      firstMention: '반드시 완전한 형태로 소개 (선거구/당명/부처 + 이름 + 직함 + 님)',
      laterMentions: {
        preferred: [
          '✅ "[이름] [직함]님" (예: "박성민 의원님", "김철수 구청장님")',
          '✅ "[직함]님" (맥락상 명확할 때만)'
        ],
        prohibited: [
          '❌ "[이름]" 단독 사용 (존칭 생략 절대 금지)',
          '❌ "[직함]" 만 (님 누락)'
        ]
      }
    },

    // 이름 인식 휴리스틱
    nameRecognition: {
      heuristics: [
        '2-4음절로 구성된 고유명사는 인명일 가능성 높음',
        '"의원", "구청장", "시장", "장관" 등 공직명 앞뒤의 단어는 인명',
        '조사 "씨", "님" 앞의 단어는 인명',
        '"~구 갑/을", "~시", "~도" + 이름 + 직함 패턴'
      ],

      contextClues: [
        '"참석", "발언", "말했다", "주장", "강조" 등의 동사 주어는 인명 가능성',
        '"함께", "비롯해", "포함" 등 나열 맥락의 단어들은 인명 리스트 가능성'
      ],

      segmentationProhibition: {
        rule: '한국어 인명(2-3글자)을 절대 분절하지 말 것',
        examples: [
          '❌ "박성(朴姓)과 민(民)을 대표하여" (인명을 한자로 분해)',
          '❌ "이영희로운" (인명을 형용사로 오해)',
          '✅ "박성민 의원님"',
          '✅ "이영희 구청장님"'
        ],
        critical: '인명은 항상 하나의 단위로 취급. 성과 이름을 분리하거나 한자 의미로 해석 절대 금지'
      }
    },

    // 검증 체크리스트
    verification: {
      checklist: [
        '✅ 모든 공직자 인명에 "님" 존칭 포함 확인 (대통령/총리 제외)',
        '✅ 의원은 "의원님", 구청장/시장은 "[직책]님" 확인',
        '✅ 선거구 표기는 "갑/을/병" 형식 확인',
        '✅ 어순: "[선거구] [이름] [직함]님" 또는 "[이름] [직함]님" 확인',
        '✅ 인명이 분절되거나 한자로 해석되지 않았는지 확인',
        '✅ 첫 언급 시 완전한 형태, 후속 언급에도 존칭 유지 확인',
        '✅ "국회의원", "구청장" 등 직함 단독 사용이 아닌 "이름 + 직함님" 형태 확인'
      ]
    },

    // 맥락 기반 예외 규칙
    contextBasedExceptions: {
      principle: '원고의 성격(비판 vs 협력)에 따라 존칭 사용 규칙을 유연하게 적용',

      // 비판적 논평 (critical_writing)
      criticalWriting: {
        principle: '비판적 논평에서는 존칭 사용이 비판의 강도를 약화시킴',

        applicableCategories: [
          'critical_writing (시사 비평)',
          '정책 비판',
          '정부/여당 비판',
          '의혹 제기'
        ],

        politicalOpponents: {
          rule: '정치적 반대편 인사는 "님" 생략 가능 (단, 직함은 반드시 명시)',
          examples: [
            '✅ "윤석열 대통령은 공약을 저버렸습니다" (야당 입장에서 비판)',
            '✅ "국민의힘 이영희 의원은 이중잣대를 보였습니다" (야당 입장)',
            '✅ "더불어민주당 박성민 의원은 위선적입니다" (여당 입장)',
            '✅ "한덕수 국무총리는 책임을 회피하고 있습니다"'
          ],
          prohibited: [
            '❌ "윤석열은" (직함 생략 - 인신공격으로 간주)',
            '❌ "이영희 의원 따위가" (비하 표현)',
            '❌ "박성민이" (직함 생략)'
          ],
          critical: '직함은 반드시 명시하여 최소한의 예의 유지. 법적 리스크 방지'
        },

        governmentOfficials: {
          rule: '비판 대상 정부 고위직은 "님" 생략',
          examples: [
            '✅ "한덕수 국무총리는 무능을 드러냈습니다"',
            '✅ "이영희 교육부 장관은 현장을 모릅니다"',
            '✅ "박철수 행안부 장관은 실패했습니다"'
          ],
          note: '대통령/총리는 원래 "님" 생략 원칙이므로 비판 맥락에서도 동일'
        },

        controversy: {
          rule: '불법/비리 의혹 제기 시 "님" 생략',
          examples: [
            '✅ "김철수 구청장은 비리 의혹에 휘말렸습니다"',
            '✅ "박영수 의원은 허위 사실을 유포했습니다"',
            '✅ "이영희 시장은 특혜 의혹을 받고 있습니다"'
          ],
          legalWarning: '명예훼손 리스크 주의. 사실 기반 비판만 허용, 추측성 표현 금지'
        },

        prohibitions: [
          '❌ 인신공격성 비하 표현 절대 금지',
          '❌ 직함 생략 금지 (예: "윤석열은" → "윤석열 대통령은")',
          '❌ 비속어나 조롱성 표현 금지',
          '❌ "~따위", "~주제에" 등 격하 표현 금지'
        ],

        balance: '비판은 강하되, 최소한의 예의(직함 사용)는 유지하여 법적 리스크 방지'
      },

      // 협력적/우호적 맥락
      cooperativeWriting: {
        principle: '우호적/협력적 맥락에서는 정파 관계없이 모든 인사에 "님" 필수',

        applicableCategories: [
          'emotional_writing (일상 소통)',
          'direct_writing (활동 보고)',
          '행사 참석 보고',
          '협력 사례 소개',
          '감사 인사'
        ],

        crossPartyCooperation: {
          rule: '야당 의원이라도 협력/참석 맥락에서는 "님" 필수',
          examples: [
            '✅ "국민의힘 이영희 의원님도 함께하셨습니다" (야당이지만 행사 참석)',
            '✅ "부평구 갑 박성민 의원님과 협력했습니다" (타 지역 의원)',
            '✅ "여야 의원님들께서 모두 참석해주셨습니다"'
          ],
          note: '정치적 입장 차이와 무관하게, 협력/참석 사실을 보고할 때는 존칭 필수'
        },

        localOfficials: {
          rule: '지방자치단체장은 정파 관계없이 항상 "님" 필수',
          examples: [
            '✅ "김철수 계양구청장님께서 함께하셨습니다"',
            '✅ "박영희 인천시장님의 지원을 받았습니다"'
          ],
          critical: '구청장/시장급은 협력 관계 유지가 중요하므로 비판 맥락에서도 신중 필요'
        },

        gratitude: {
          rule: '감사 인사는 반드시 "님" 사용',
          examples: [
            '✅ "참석해주신 박성민 의원님께 감사드립니다"',
            '✅ "도움을 주신 김철수 구청장님께 감사의 말씀을 전합니다"'
          ]
        }
      },

      // 중립적 보도/보고
      neutralReporting: {
        principle: '중립적 보도/사실 보고에서는 기본 존칭 규칙 준수',

        rule: '비판도 협력도 아닌 단순 사실 전달 시 "님" 사용',
        examples: [
          '✅ "윤석열 대통령이 발표했습니다" (대통령은 원래 님 생략)',
          '✅ "이영희 의원님이 발언했습니다"',
          '✅ "김철수 구청장님께서 참석하셨습니다"'
        ]
      },

      // 의사결정 가이드
      decisionGuide: {
        question: '이 원고는 어떤 맥락인가?',

        flowchart: [
          '1. 비판/공격 대상인가? → YES: "님" 생략 (단, 직함 필수)',
          '2. 협력/감사 대상인가? → YES: "님" 필수',
          '3. 중립적 보도인가? → YES: 기본 규칙 적용 ("님" 사용)',
          '4. 불확실한가? → 보수적으로 "님" 사용 (안전)'
        ],

        exampleScenarios: [
          {
            scenario: '행사 보고 원고에 야당 의원 참석',
            decision: '협력 맥락 → "국민의힘 이영희 의원님께서 참석하셨습니다" ✅'
          },
          {
            scenario: '정부 정책 비판 원고',
            decision: '비판 맥락 → "윤석열 대통령은 공약을 저버렸습니다" ✅'
          },
          {
            scenario: '타 지역 구청장 비리 의혹 제기',
            decision: '비판 맥락 → "김철수 구청장은 비리 의혹을 받고 있습니다" ✅'
          },
          {
            scenario: '타 지역 의원과 공동 정책 발표',
            decision: '협력 맥락 → "부평구 갑 박성민 의원님과 함께 발표했습니다" ✅'
          }
        ]
      }
    }
  }
};

// ============================================================================
// 출력 및 형식 규칙
// ============================================================================

const FORMAT_RULES = {
  // JSON 출력 규격
  outputStructure: {
    required: {
      title: 'string - 매력적이고 SEO 최적화된 제목',
      content: 'string - HTML 형식의 본문 내용',
      wordCount: 'number - 실제 글자 수',
      style: 'string - 작성 스타일 식별자'
    },
    optional: {
      summary: 'string - 한 줄 요약 (필요시)',
      tags: 'array - 관련 태그 (필요시)',
      category: 'string - 분류 정보'
    },
    restrictions: [
      'JSON 외 추가 설명 금지',
      'code-fence(```) 사용 금지',
      '마크다운 형식 금지'
    ]
  },

  // HTML 형식 가이드
  htmlGuidelines: {
    structure: [
      '<p> 태그로 문단 구성',
      '<h2>, <h3> 태그로 소제목',
      '<ul>, <ol> 태그로 목록',
      '<strong> 태그로 강조'
    ],
    semantics: [
      '의미에 맞는 태그 사용',
      '접근성 고려한 구조',
      '검색엔진 친화적 마크업'
    ],
    prohibitions: [
      'CSS 스타일 속성 사용 금지',
      '인라인 스타일 금지',
      '불필요한 div 태그 금지'
    ]
  },

  // 품질 기준
  qualityStandards: {
    readability: {
      sentenceLength: '평균 25-40자',
      paragraphLength: '3-5문장',
      complexWords: '전문용어 최소화',
      grammarCheck: '문장 완결성 및 조사 누락 방지'
    },
    coherence: {
      logicalFlow: '논리적 연결성',
      topicConsistency: '주제 일관성',
      transitionSmoothness: '자연스러운 전환'
    },
    engagement: {
      personalTouch: '개인적 경험 포함',
      emotionalConnection: '감정적 공감대',
      actionOriented: '구체적 행동 제시'
    }
  }
};

// ============================================================================
// 통합 편집 가이드라인
// ============================================================================

const EDITORIAL_WORKFLOW = {
  // 작성 프로세스
  writingProcess: {
    planning: [
      '1. 주제 분석 및 키워드 추출',
      '2. 독자층 파악 및 톤 설정',
      '3. 구조 설계 (제목, 소제목, 흐름)',
      '4. 핵심 메시지 및 call-to-action 결정'
    ],
    drafting: [
      '1. 매력적인 제목 작성 (키워드 포함)',
      '2. 인사말과 주제 소개',
      '3. 본문 전개 (논리적 순서)',
      '4. 개인 경험 자연스럽게 삽입',
      '5. 결론 및 다짐으로 마무리'
    ],
    revision: [
      '1. SEO 최적화 점검 (분량, 키워드 배치)',
      '2. 법적 위험 요소 검토',
      '3. 톤앤매너 일관성 확인',
      '4. 가독성 및 흐름 개선',
      '5. JSON 형식 최종 확인'
    ]
  },

  // 품질 체크리스트
  qualityChecklist: {
    content: [
      '✅ 주제 관련성 확보',
      '✅ 개인 경험 적절히 반영',
      '✅ 건설적이고 미래지향적 메시지',
      '✅ 독자와의 공감대 형성'
    ],
    seo: [
      '✅ 1500-2300자 분량 준수 (공백 제외)',
      '✅ 키워드 자연스러운 배치',
      '✅ 제목 매력도 및 검색 최적화 (30-40자)',
      '✅ 구조화된 소제목 활용'
    ],
    format: [
      '✅ JSON 형식 정확성',
      '✅ HTML 마크업 적절성',
      '✅ 가독성 확보',
      '✅ 일관된 톤앤매너',
      '✅ 문장 완결성 검증',
      '✅ 조사/어미 누락 확인'
    ],
    safety: [
      '✅ 법적 위험 요소 없음',
      '✅ 차별적 표현 없음',
      '✅ 사실 기반 내용',
      '✅ 출처 표기 완료'
    ]
  },

  // 개선 권장사항
  improvementTips: {
    engagement: [
      '구체적 수치와 사례 활용',
      '지역 특화 정보 포함',
      '시각적 구조화 (목록, 소제목)',
      '감정적 어필과 이성적 근거 균형'
    ],
    differentiation: [
      '개인만의 경험과 시각 강조',
      '지역 특성 반영',
      '실용적 정보 제공',
      '독자 참여 유도'
    ]
  }
};

// ============================================================================
// 수사학 전략 (Rhetoric Strategies) - 유권자 감정 자극 및 설득 강화
// ============================================================================

/**
 * 수사학 전략 정의
 *
 * 목적: 단순한 정보 전달을 넘어, 유권자의 감정을 자극하고 행동을 유도하는 글쓰기 전략
 * 적용: 주제/키워드 매칭 및 사용자 프로필 조건에 따라 동적 적용
 */
const RHETORIC_STRATEGIES = {
  // 1. 고통의 시각화 (Pain Point Visualization)
  // 유권자가 일상에서 겪는 불편함을 생생하게 묘사하여 공감대 형성
  PAIN_TRIGGER: {
    id: 'pain_trigger',
    name: '고통 시각화 전략',
    keywords: ['교통', '의료', '주차', '쓰레기', '소음', '지연', '대기', '불편', '민원', '고통', '어려움'],
    instruction: `
[수사학 전략: 고통의 시각화]
- 서두를 "존경하는 구민 여러분" 같은 형식적 인사로 시작하지 마라.
- 유권자가 실제로 겪는 '불편한 순간'을 구체적으로 묘사하며 시작하라.
- 시간, 장소, 상황을 특정하여 생생함을 더하라.
- 예시: "퇴근길 꽉 막힌 도로에서 30분을 허비해본 적 있으십니까?"
- 예시: "아픈 아이를 안고 응급실에서 2시간을 기다려본 적 있으십니까?"
- 예시: "새벽 5시, 서울행 KTX에 몸을 싣는 환자들의 뒷모습을 보셨습니까?"
`
  },

  // 2. 위기와 굴욕 프레이밍 (Crisis & Humiliation Framing)
  // 객관적 수치를 '지역의 자존심 문제'로 전환하여 변화의 당위성 부여
  CRISIS_AMPLIFIER: {
    id: 'crisis_amplifier',
    name: '위기 증폭 전략',
    keywords: ['순위', '하락', '유출', '격차', '소외', '박탈', '뒤처', '낙후', '감소', '이탈', '유출'],
    instruction: `
[수사학 전략: 위기와 굴욕 프레이밍]
- 이 문제를 단순한 '불편'이 아닌 '우리 지역의 위기'로 규정하라.
- "왜 우리는 서울보다, 다른 구보다 뒤처지는가?"라는 박탈감을 자극하라.
- 수치는 건조하게 나열하지 말고, 자존심을 건드리는 도구로 활용하라.
- 예시: "27위, 이것이 우리 부산 의료의 현주소입니다. 굴욕입니다."
- 예시: "서울은 10개, 우리 구는 고작 1개. 이게 공정한 겁니까?"
- 프레이밍 키워드: '굴욕', '위기', '추락', '참담', '수치', '방치'
`
  },

  // 3. 게임체인저 비전 (Game Changer Vision)
  // '따라잡기'가 아닌 '판을 뒤집는' 차별화된 비전 제시
  GAME_CHANGER: {
    id: 'game_changer',
    name: '게임체인저 비전 전략',
    keywords: ['혁신', '미래', '선도', '최초', '유일', 'AI', '스마트', '플랫폼', '클러스터', '허브'],
    instruction: `
[수사학 전략: 게임체인저 비전]
- '예산 따오겠다', '시설 유치하겠다'는 식의 뻔한 해법은 피하라.
- 경쟁자들이 따라올 수 없는 '새로운 판'을 제시하라.
- 서울/수도권을 '따라잡는' 것이 아니라, '추월하는' 비전을 그려라.
- 예시: "서울이 '현재의 1등'이라면, 우리는 '미래의 세계 1등'이 되겠습니다."
- 예시: "서울에도 없는 기술, 부산에서 세계 최초로 실현하겠습니다."
- 차별화 키워드: '초격차', '세계 최초', '아시아 유일', '미래 선도'
`
  },

  // 4. 전문가 권위 (Technocratic Authority)
  // IT/기업/전문직 출신의 경우, 전문성을 무기로 활용
  TECH_SAVIOR: {
    id: 'tech_savior',
    name: '전문가 권위 전략',
    // 키워드가 아닌 프로필 조건으로 발동
    profileCondition: (profile) => {
      if (!profile || !profile.career) return false;
      const career = profile.career.toLowerCase();
      return career.includes('it') ||
             career.includes('기업') ||
             career.includes('대표') ||
             career.includes('ceo') ||
             career.includes('개발') ||
             career.includes('엔지니어') ||
             career.includes('박사') ||
             career.includes('연구');
    },
    instruction: `
[수사학 전략: 전문가 권위]
- 후보자의 전문 경력을 '시스템적 해법'의 근거로 활용하라.
- 기존 정치인들이 제시하지 못하는 '기술적/경영적 관점'을 부각하라.
- 단순 시설 확충이 아닌 '데이터 기반', 'AI 활용', '플랫폼 구축' 등의 해법을 제시하라.
- 예시: "제가 IT 기업을 경영하며 배운 것은, 문제는 시스템으로 풀어야 한다는 것입니다."
- 예시: "데이터가 없으면 정책도 없습니다. 저는 데이터로 말하겠습니다."
`
  },

  // 5. 서민 연대 (Grassroots Solidarity)
  // 엘리트 이미지를 탈피하고 서민과의 공감대 형성
  GRASSROOTS: {
    id: 'grassroots',
    name: '서민 연대 전략',
    keywords: ['서민', '소상공인', '자영업', '임대료', '월세', '생계', '일자리', '실업', '폐업'],
    instruction: `
[수사학 전략: 서민 연대]
- 정책 용어보다 '삶의 언어'로 말하라.
- 숫자보다 사람의 이야기를 앞세워라.
- 예시: "통계로는 경기가 회복됐다고 합니다. 하지만 시장 골목 상인들 표정은 여전히 어둡습니다."
- 예시: "월세 올려달라는 말에 밤잠을 설치는 분들, 저는 압니다."
`
  }
};

/**
 * 주제와 프로필을 분석하여 적용할 수사학 전략들을 반환
 * @param {string} topic - 글의 주제
 * @param {string} instructions - 추가 지시사항
 * @param {Object} userProfile - 사용자 프로필
 * @returns {Object} { strategies: Array, promptInjection: string }
 */
function getActiveStrategies(topic, instructions = '', userProfile = {}) {
  const text = `${topic} ${instructions}`.toLowerCase();
  const activeStrategies = [];
  const injections = [];

  // 키워드 기반 전략 매칭
  for (const [key, strategy] of Object.entries(RHETORIC_STRATEGIES)) {
    // 프로필 조건 체크 (TECH_SAVIOR 등)
    if (strategy.profileCondition) {
      if (strategy.profileCondition(userProfile)) {
        activeStrategies.push(strategy.id);
        injections.push(strategy.instruction);
      }
      continue;
    }

    // 키워드 매칭
    if (strategy.keywords && strategy.keywords.some(kw => text.includes(kw))) {
      activeStrategies.push(strategy.id);
      injections.push(strategy.instruction);
    }
  }

  // 기본 전략 (아무것도 매칭되지 않을 경우)
  if (injections.length === 0) {
    injections.push(`
[수사학 전략: 기본]
- 유권자의 감정에 호소하는 진정성 있는 어조를 유지하라.
- 구체적인 수치와 사례를 활용하여 신뢰성을 확보하라.
- 희망적이고 건설적인 비전으로 마무리하라.
`);
  }

  return {
    strategies: activeStrategies,
    promptInjection: injections.join('\n\n')
  };
}

/**
 * 시도 번호(attemptNumber)에 따라 다른 수사학 전략을 선택
 * 사용자 선호도 가중치를 반영하여 전략 풀에서 선택
 *
 * @param {number} attemptNumber - 현재 시도 번호 (0, 1, 2)
 * @param {string} topic - 글의 주제
 * @param {string} instructions - 추가 지시사항
 * @param {Object} userProfile - 사용자 프로필
 * @param {Object} preferences - 사용자 전략 선호도 { strategyId: count }
 * @returns {Object} { strategyId: string, strategyName: string, promptInjection: string }
 */
function selectStrategyForAttempt(attemptNumber, topic, instructions = '', userProfile = {}, preferences = {}) {
  const text = `${topic} ${instructions}`.toLowerCase();

  // 1. 매칭 가능한 전략 수집
  const matchedStrategies = [];

  for (const [key, strategy] of Object.entries(RHETORIC_STRATEGIES)) {
    let matched = false;

    // 프로필 조건 체크
    if (strategy.profileCondition) {
      if (strategy.profileCondition(userProfile)) {
        matched = true;
      }
    } else if (strategy.keywords && strategy.keywords.some(kw => text.includes(kw))) {
      // 키워드 매칭
      matched = true;
    }

    if (matched) {
      matchedStrategies.push({
        id: strategy.id,
        name: strategy.name,
        instruction: strategy.instruction,
        weight: (preferences[strategy.id] || 0) + 1  // 기본 가중치 1 + 선호도
      });
    }
  }

  // 2. 매칭된 전략이 없으면 기본 전략 풀 사용
  if (matchedStrategies.length === 0) {
    // 모든 전략을 후보로 (프로필 조건 전략 제외)
    for (const [key, strategy] of Object.entries(RHETORIC_STRATEGIES)) {
      if (!strategy.profileCondition) {
        matchedStrategies.push({
          id: strategy.id,
          name: strategy.name,
          instruction: strategy.instruction,
          weight: (preferences[strategy.id] || 0) + 1
        });
      }
    }
  }

  // 3. attemptNumber에 따라 다른 전략 선택
  // - 가중치 정렬 후 attemptNumber 인덱스로 선택
  // - 선호도 높은 전략이 앞쪽에 오도록
  matchedStrategies.sort((a, b) => b.weight - a.weight);

  // 순환 선택 (전략 수보다 attempt가 많을 경우)
  const selectedIndex = attemptNumber % matchedStrategies.length;
  const selected = matchedStrategies[selectedIndex];

  // 선택된 전략이 없으면 기본 반환
  if (!selected) {
    return {
      strategyId: 'default',
      strategyName: '기본 전략',
      promptInjection: `
[수사학 전략: 기본]
- 유권자의 감정에 호소하는 진정성 있는 어조를 유지하라.
- 구체적인 수치와 사례를 활용하여 신뢰성을 확보하라.
- 희망적이고 건설적인 비전으로 마무리하라.
`
    };
  }

  console.log(`🎯 [RhetoricStrategy] 시도 ${attemptNumber}: ${selected.name} 선택 (가중치: ${selected.weight})`);

  return {
    strategyId: selected.id,
    strategyName: selected.name,
    promptInjection: selected.instruction
  };
}

// ============================================================================
// 모범 문장 예시 (Writing Examples)
// ============================================================================

/**
 * 카테고리별 모범 문장
 * - 구체적 장면 묘사, 감각적 표현, 시민 시점
 * - AI가 글 생성 시 참고할 수 있도록 Few-shot 예시로 활용
 */
const WRITING_EXAMPLES = {
  // 도입부: 첫 문장에서 관심 끌기
  도입부: [
    { text: '올 겨울 들어 가장 춥다는 날 도착한 편지.', type: '계절' },
    { text: '가을 하늘이 청명했던 토요일, 기후정의행진에 함께했습니다.', type: '계절+행사' },
    { text: '이제 금요일 밤이 되면, 자연스럽게 두터운 외투와 핫팩을 챙기게 됩니다.', type: '시간+행동' },
    { text: '한낮 35도, 한증막 같은 정류장. 앉아 있기도 힘듭니다.', type: '감각' },
    { text: '꿈을 꿨습니다. 낮에도 꼴찌인데, 꿈에서도 꼴찌를 했습니다.', type: '자조적' },
    { text: '눈이 내릴 것처럼 차가운 공기 속에서, 거리의 숨결은 유난히 따뜻합니다.', type: '계절+대비' },
    { text: '문장을 따라가다 마음이 글자보다 먼저 멈춰 섭니다.', type: '감성' }
  ],

  // 공감묘사: 시민의 고통을 구체적 장면으로
  공감묘사: [
    { text: '새벽 KTX에 아픈 몸을 싣고 서울로 향하는 환자들.', category: '의료' },
    { text: '수술을 받기 위해 여러 병원을 전전해야 하는 환자와 가족들은 매일 피눈물을 흘립니다.', category: '의료' },
    { text: '출산 가능한 병원 근처에 급하게 월세를 구하거나 친정·시댁에 몸을 의탁해야 하는 산모들.', category: '의료' },
    { text: '아이의 작은 손을 꼭 잡고 불안과 싸우셨을 시간.', category: '의료' },
    { text: '취업했다고 좋아했는데, 근로계약서도 안 써주고 4대보험도 안 들어준다고 합니다.', category: '청년' },
    { text: '수급 끊길까 봐 알바를 못 하고 있는 청년이 있습니다.', category: '청년' },
    { text: '1시간 30분 잡고 출발해도 지각입니다.', category: '교통' },
    { text: '버스 놓치면 한 시간을 기다려야 합니다.', category: '교통' },
    { text: '가장 가까운 투표소가 직선거리로 5km였습니다.', category: '인프라' },
    { text: '감기몸살이 심해서 약 하나 사 먹으려면 버스가 없어 꼼짝없이 앓아누워야 합니다.', category: '의료+교통' }
  ],

  // 전환: 문제 인식 → 해결/행동으로 넘어가는 연결
  전환: [
    { text: '더 이상 방치할 수 없습니다.', pattern: '한계선언' },
    { text: '더 이상 미룰 수 없습니다.', pattern: '한계선언' },
    { text: '더 이상 유예해서는 안 됩니다.', pattern: '행동촉구' },
    { text: '더 이상 미룰 수 없는 과제입니다.', pattern: '긴급성' },
    { text: '이제는 바꿔야 할 때입니다.', pattern: '시점강조' },
    { text: '이제는 정부가 응답할 차례입니다.', pattern: '책임전환' },
    { text: '그 희생에만 기댄 현장은 더 이상 지속될 수 없습니다.', pattern: '한계선언' },
    { text: '정의는 이겼고, 이제는 국민이 이깁니다.', pattern: '승리전환' }
  ],

  // 약속/다짐: 화자의 의지와 구체적 약속
  약속다짐: [
    { text: '어르신 한 분 한 분이 존중받고, 편안한 노후를 누릴 수 있는 사회 반드시 만들겠습니다.', category: '복지' },
    { text: '노동자 한 분 한 분의 땀과 노력이 온전히 인정받는 사회를 위해 힘쓰겠습니다.', category: '노동' },
    { text: '3년 전 못다 이룬 약속, 이번에는 꼭 지키겠습니다.', category: '스토리' },
    { text: '국민의 목소리에 귀 기울이고, 국민의 뜻을 하늘처럼 받들겠습니다.', category: '감성' },
    { text: '현실에서 체감할 수 있는 변화를 반드시 실현하겠습니다.', category: '체감' },
    { text: '땀과 수고가 정당하게 인정받는 나라를 반드시 만들겠습니다.', category: '노동' },
    { text: '더욱 촘촘한 사회안전망을 만들어가겠습니다.', category: '복지' },
    { text: '국민과 국가를 위한 헌신이 자긍심과 영예로 온전히 돌아오는 나라, 꼭 만들겠습니다.', category: '보훈' },
    { text: '더 크게 외치고, 더 단호하게 싸우겠습니다.', category: '행동' },
    { text: '분노가 아닌 기쁨이, 긴장이 아닌 여유가 가득한 평범한 주말을 하루라도 빨리 국민 여러분께 돌려드리겠습니다.', category: '대구법' },
    { text: '기억하겠습니다. 지키겠습니다.', category: '짧은리듬' },
    { text: '이제 정부가 힘이 되어드리겠습니다.', category: '역할전환' }
  ],

  // 마무리: 희망적 비전, 인상적 끝맺음
  마무리: [
    { text: '형태도 빛깔도 다른 각양각색의 빛들이 한데 모여 어두운 국회 앞을 밝혔습니다.', type: '시각적' },
    { text: '반갑게 인사하고, 함께 씩씩하게 걷고, 뜨끈한 새알 미역국을 나누고.', type: '구체장면' },
    { text: '토요일마다 거리로 나오는 걸음이 일상이 되었습니다.', type: '반복리듬' },
    { text: '글 배워 책 읽고, 학교 가서 공부하고 싶던 내 마음은 꾹꾹 식히고, 매 끼니 밥상은 식지 않게 차려냈습니다.', type: '서사' }
  ]
};

/**
 * 카테고리에 맞는 모범 문장 예시를 프롬프트용 문자열로 반환
 * @param {string} category - 글 카테고리 (local-issues, policy-proposal 등)
 * @returns {string} 프롬프트에 주입할 예시 문자열
 */
function getWritingExamples(category) {
  // 카테고리별 관련 공감묘사 필터링
  const categoryMapping = {
    'local-issues': ['의료', '교통', '인프라'],
    'policy-proposal': ['복지', '노동', '청년'],
    'current-affairs': ['의료', '청년', '교통'],
    'daily-communication': [],  // 전체 사용
    'activity-report': []  // 전체 사용
  };

  const relevantCategories = categoryMapping[category] || [];

  // 각 기능별로 2~3개씩 선택
  const selected = {
    도입부: WRITING_EXAMPLES.도입부.slice(0, 2),
    공감묘사: relevantCategories.length > 0
      ? WRITING_EXAMPLES.공감묘사.filter(e => relevantCategories.some(c => e.category.includes(c))).slice(0, 3)
      : WRITING_EXAMPLES.공감묘사.slice(0, 3),
    전환: WRITING_EXAMPLES.전환.slice(0, 2),
    약속다짐: WRITING_EXAMPLES.약속다짐.slice(0, 3),
    마무리: WRITING_EXAMPLES.마무리.slice(0, 2)
  };

  return `
[모범 문장 참고 - 구조와 톤을 참고하되 내용은 새롭게]

■ 도입부 예시 (구체적 배경으로 시작):
${selected.도입부.map(e => `• "${e.text}"`).join('\n')}

■ 공감 묘사 예시 (추상어 대신 구체적 장면):
${selected.공감묘사.map(e => `• "${e.text}"`).join('\n')}

■ 전환 예시 (문제→해결로 넘어갈 때):
${selected.전환.map(e => `• "${e.text}"`).join('\n')}

■ 약속/다짐 예시 (구체적 결과가 담긴 약속):
${selected.약속다짐.map(e => `• "${e.text}"`).join('\n')}

■ 마무리 예시 (인상적 끝맺음):
${selected.마무리.map(e => `• "${e.text}"`).join('\n')}

위 예시처럼 "의료 격차가 심각합니다" 대신 "새벽 KTX에 아픈 몸을 싣고..."처럼 구체적 장면을 묘사하세요.
`;
}

// ============================================================================
// 내보내기
// ============================================================================

module.exports = {
  // SEO 최적화
  SEO_RULES,

  // 콘텐츠 작성
  CONTENT_RULES,

  // 형식 및 출력
  FORMAT_RULES,

  // 편집 워크플로우
  EDITORIAL_WORKFLOW,

  // 수사학 전략
  RHETORIC_STRATEGIES,
  getActiveStrategies,
  selectStrategyForAttempt,  // 시도별 전략 선택 (변형 생성용)

  // 모범 문장 예시
  WRITING_EXAMPLES,
  getWritingExamples
};
