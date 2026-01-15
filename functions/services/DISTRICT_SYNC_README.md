# 선거구 데이터 동기화 시스템

중앙선거관리위원회 API를 통해 선거구 데이터를 자동으로 동기화하는 시스템입니다.

## 개요

### 목적
- 2026년 지방선거 등 미래 선거구 데이터를 자동으로 가져옴
- 수동으로 선거구 데이터를 관리하는 번거로움 제거
- 선거구 변경사항(예: 인천 검단구 신설) 자동 반영

### 현재 상태
- ✅ API 키 발급 완료 및 승인됨
- ✅ 시스템 구현 완료
- ⏳ 2026년 선거 데이터는 아직 API에 미등록 (추후 자동 감지)
- 📊 현재 제공 데이터: 1992~2015년 선거 (181개)

## 아키텍처

### 파일 구조
```
functions/
├── services/
│   └── district-sync.js           # 핵심 동기화 로직
├── handlers/
│   └── district-sync-handler.js   # Cloud Functions 핸들러
├── .env                            # API 키 저장
└── test-district-sync.js          # 테스트 스크립트
```

### 데이터 흐름
```
중앙선거관리위원회 API
    ↓
district-sync.js (월 1회 자동 실행)
    ↓
Firestore: electoral_districts 컬렉션
    ↓
프론트엔드: UserInfoForm.jsx (목표 선거 필드)
```

## API 정보

### 엔드포인트
- **Base URL**: `http://apis.data.go.kr/9760000/CommonCodeService`
- **API 키**: `functions/.env`에 `NEC_API_KEY`로 저장됨

### 제공 API
1. **선거코드 조회** (`getCommonSgCodeList`)
   - 선거 ID, 선거명, 선거일자 제공
   - 예: 20220309 (제20대 대통령선거)

2. **구시군코드 조회** (`getCommonGusigunCodeList`)
   - 선거별 구시군 목록 제공
   - 예: 서울특별시, 종로구, 중구 등

3. **선거구코드 조회** (`getCommonSggCodeList`)
   - 선거별 선거구 상세 정보 제공
   - 예: 종로구가선거구, 중구나선거구 등
   - 포함 정보: 선거구명, 시도명, 구시군명, 선출정수

## 사용법

### 1. 자동 동기화 (월간 스케줄)
- **실행 시각**: 매월 1일 새벽 3시 (KST)
- **Cloud Function**: `scheduledDistrictSync`
- **작동 방식**: 자동으로 2020년 이후 선거 데이터 확인 및 동기화

### 2. 수동 동기화 (관리자)

#### 프론트엔드에서 호출
```javascript
import { getFunctions, httpsCallable } from 'firebase/functions';

const functions = getFunctions();
const syncElectoralDistricts = httpsCallable(functions, 'syncElectoralDistricts');

// 전체 미래 선거 동기화
const result = await syncElectoralDistricts();

// 특정 선거만 동기화
const result = await syncElectoralDistricts({ sgId: '20260603' });
```

#### 로컬 테스트
```bash
cd functions
node test-district-sync.js
```

### 3. 선거 목록 조회
```javascript
const getElectionList = httpsCallable(functions, 'getElectionList');
const result = await getElectionList();

console.log(result.data.elections);
// [
//   { id: '20260603', name: '제8회 전국동시지방선거', date: '20260603', type: '0' },
//   ...
// ]
```

## Firestore 데이터 구조

### 컬렉션: `electoral_districts`

#### 문서 ID 형식
```
{sgId}_{sgTypecode}_{sggName}
예: 20260603_6_종로구가선거구
```

#### 문서 필드
```javascript
{
  electionId: '20260603',           // 선거ID
  electionType: '6',                 // 선거종류코드 (6: 기초의원)
  position: '기초의원',             // 직책명
  electoralDistrict: '종로구가선거구', // 선거구명
  regionMetro: '서울특별시',         // 광역자치단체
  regionLocal: '종로구',             // 기초자치단체
  selectedCount: 2,                  // 선출정수
  order: 1,                          // 순서
  source: 'NEC_API',                 // 데이터 출처
  syncedAt: Timestamp,               // 동기화 시각
  createdAt: Timestamp               // 생성 시각
}
```

## 선거종류코드 매핑

| 코드 | 직책 |
|------|------|
| 1 | 대통령 |
| 2 | 국회의원 |
| 3 | 광역자치단체장 |
| 4 | 기초자치단체장 |
| 5 | 광역의원 |
| 6 | 기초의원 |
| 7 | 국회의원비례 |
| 8 | 광역의원비례 |
| 9 | 기초의원비례 |
| 10 | 교육의원 |
| 11 | 교육감 |

## 예상 시나리오

### 시나리오 1: 2026년 데이터 등록 전 (현재)
```
월간 스케줄 실행
  ↓
선거 목록 조회 (1992~2015년)
  ↓
2020년 이후 데이터 없음
  ↓
"2026년 선거 데이터가 아직 등록되지 않았습니다." 메시지
  ↓
아무 작업 없이 종료
```

### 시나리오 2: 2026년 데이터 등록 후 (추후)
```
월간 스케줄 실행
  ↓
선거 목록 조회 (1992~2026년)
  ↓
2020년 이후 데이터 발견: 20260603 (제8회 지방선거)
  ↓
선거구 데이터 조회 (국회의원, 광역의원, 기초의원)
  ↓
Firestore에 수천 개 선거구 저장
  ↓
"선거구 데이터 동기화 완료" 메시지
```

### 시나리오 3: 검단구 신설 대응
- **현재 (2026년 6월 이전)**: 인천 서구 병 지역구
- **선거 (2026년 6월 3일)**: 검단구청장 선거
- **신설 (2026년 7월 1일)**: 검단구 정식 출범

**시스템 대응:**
1. API에서 "검단구 가/나/다" 선거구 데이터 자동 수집
2. Firestore에 검단구 선거구 정보 저장
3. 프론트엔드 "목표 선거" 드롭다운에 자동 반영
4. 사용자는 "검단구"를 목표 선거구로 설정 가능

## 비용 분석

### API 호출 비용
- 공공데이터포털 API: **무료**
- 일일 트래픽 한도: 10,000회/일 (충분함)

### Cloud Functions 비용
- **월간 스케줄**: 1회/월 × 약 30초 = 0.5분/월
- **예상 비용**: 약 $0.003/월 (거의 무료)

### Firestore 비용
- **읽기**: 선거구 조회 시 (프론트엔드에서 드롭다운 로드)
- **쓰기**: 월 1회 × 약 3,000개 선거구 = 3,000회/월
- **예상 비용**: 약 $0.006/월 (무료 할당량 내)

**총 예상 비용**: **약 $0.01/월** (무시할 수준)

## 트러블슈팅

### 문제 1: API 404 오류
```
API not found
```
**원인**: 잘못된 엔드포인트 또는 API 키 미승인
**해결**: 공공데이터포털에서 API 승인 상태 확인

### 문제 2: 2026년 데이터 없음
```
2026년 선거 데이터가 아직 등록되지 않았습니다.
```
**원인**: 선관위에서 아직 2026년 선거구 데이터 미등록
**해결**: 정상 상황. 데이터 등록 시 자동으로 동기화됨

### 문제 3: Secret Manager 권한 오류
```
Permission denied on resource project ai-secretary-442305
```
**원인**: GCP Secret Manager 접근 권한 없음
**해결**: 현재는 `.env` 파일 사용 중. Secret Manager는 추후 배포 시 설정

## 향후 계획

### Phase 1: 현재 (완료)
- ✅ API 연동 완료
- ✅ 자동 동기화 시스템 구축
- ✅ 테스트 환경 구축

### Phase 2: 2026년 데이터 등록 시
- ⏳ 자동 동기화 확인
- ⏳ 프론트엔드 연동 테스트
- ⏳ 사용자 피드백 수집

### Phase 3: 확장
- ⏳ 다른 선거 데이터 추가 (2028년 총선 등)
- ⏳ 선거구 변경 히스토리 관리
- ⏳ 관리자 대시보드 추가

## 참고 자료

- [공공데이터포털](https://www.data.go.kr/)
- [중앙선거관리위원회](https://www.nec.go.kr/)
- [Firebase Cloud Functions 문서](https://firebase.google.com/docs/functions)
- [Firestore 문서](https://firebase.google.com/docs/firestore)

## 담당자

- **개발**: Claude (AI Assistant)
- **요청자**: 강정구 (대표)
- **문의**: 010-4885-6206
