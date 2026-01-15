import election2022 from '../data/election/2022_local.json';
import election2024 from '../data/election/2024_general.json';

// 데이터 캐싱을 위한 객체
const CACHE = {
    // 2022: Local Election (지방선거)
    local: {
        metro: new Set(),
        local: {}, // { "서울": Set("종로구", "중구"...) }
        districts: {} // { "서울_종로구_기초의원": [...] }
    },
    // 2024: General Election (총선)
    general: {
        metro: new Set(),
        local: {},
        districts: {}
    }
};

/**
 * 초기화: 데이터 파싱 및 구조화
 */
function initializeData() {
    if (CACHE.local.metro.size > 0) return; // 이미 로드됨

    // ==========================================
    // 1. 2022 지방선거 데이터 처리 (Local)
    // ==========================================
    const localDataTypes = ['metro_head', 'local_head', 'metro_council', 'local_council'];

    // 모든 지방선거 데이터를 순회하며 계층 구조 빌드
    localDataTypes.forEach(type => {
        const items = election2022.data[type] || [];
        items.forEach(item => {
            const metro = item.sdName;
            const local = item.wiwName;
            const district = item.sggName;

            if (!metro) return;
            CACHE.local.metro.add(metro);

            if (!CACHE.local.local[metro]) CACHE.local.local[metro] = new Set();
            if (local) CACHE.local.local[metro].add(local);

            // 선거구 저장 (직책별/지역별 키 생성)
            // type map: 
            // metro_head (광역단체장) -> Region only
            // local_head (기초단체장) -> Region only
            // metro_council (광역의원) -> District exists
            // local_council (기초의원) -> District exists

            if (type === 'metro_council' || type === 'local_council') {
                const key = `${metro}_${local || ''}_${type}`;
                if (!CACHE.local.districts[key]) CACHE.local.districts[key] = [];
                if (district) CACHE.local.districts[key].push(district);
            }
        });
    });

    // ==========================================
    // 2. 2024 총선 데이터 처리 (General)
    // ==========================================
    const generalItems = election2024.data.parliament || [];
    generalItems.forEach(item => {
        const metro = item.sdName;
        const local = item.wiwName; // 총선 데이터의 wiwName은 행정구역
        const districtKey = item.sggName; // 실제 선거구명 (예: 종로구, 중구성동구갑)

        if (!metro) return;
        CACHE.general.metro.add(metro);

        if (!CACHE.general.local[metro]) CACHE.general.local[metro] = new Set();
        if (local) CACHE.general.local[metro].add(local);

        // 총선은 '국회의원' 포지션 하나임
        // 총선 선거구는 행정구역(local)과 1:1이 아닐 수 있음 (합구/분구)
        // 따라서 Local을 선택했을 때, 그 Local이 포함된 "국회의원 선거구"를 찾아야 함.
        // 데이터 구조: wiwName(관할 구역) -> sggName(선거구)
        const key = `${metro}_${local}_parliament`;
        if (!CACHE.general.districts[key]) CACHE.general.districts[key] = [];
        if (districtKey) CACHE.general.districts[key].push(districtKey);
    });
}

// 헬퍼: 직책에 따른 선거 유형 결정
function getElectionType(position) {
    // 국회의원 및 지자체장은 총선(국회의원) 지역구 데이터를 따름 (지역위원회 기준)
    if (['국회의원', '광역자치단체장', '기초자치단체장'].includes(position)) return 'general';
    return 'local';
}

/**
 * 광역자치단체 목록 반환
 */
export function getElectionMetroList(position) {
    initializeData();
    const type = getElectionType(position);
    return Array.from(CACHE[type].metro).sort();
}

/**
 * 기초자치단체 목록 반환
 */
export function getElectionLocalList(position, metro) {
    if (!metro) return [];
    initializeData();
    const type = getElectionType(position);
    const locals = CACHE[type].local[metro];
    return locals ? Array.from(locals).sort() : [];
}

/**
 * 선거구 목록 반환
 */
export function getElectionDistrictList(position, metro, local) {
    if (!metro) return []; // 총선은 local이 필수일 수도 아닐 수도 있음 (세종 등)
    initializeData();
    const type = getElectionType(position);

    let keyStr = '';
    if (type === 'general') {
        keyStr = `${metro}_${local}_parliament`;
    } else {
        // Local
        let subType = '';
        if (position === '광역의원') subType = 'metro_council';
        else if (position === '기초의원') subType = 'local_council';
        else return []; // 단체장은 선거구가 없음 (지역 자체가 선거구)

        keyStr = `${metro}_${local}_${subType}`;
    }

    const list = CACHE[type].districts[keyStr];
    // 중복 제거 및 정렬
    return list ? Array.from(new Set(list)).sort() : [];
}
