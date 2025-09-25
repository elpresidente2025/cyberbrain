// 이 파일은 location 폴더 내의 모든 지역별 선거구 데이터(`locations.*.js`)를
// 자동으로 찾아 하나로 통합하여 내보내는 역할을 합니다.
// 새로운 지역 파일을 추가하기만 하면 별도의 수정 없이 바로 적용됩니다.

// 'locations.'로 시작하고 '.js'로 끝나는 모든 파일을 동적으로 즉시 로드합니다.
// (locations.index.js 파일은 패턴에 해당하지 않으므로 제외됩니다.)
const locationModules = import.meta.glob('./locations.*.js', { eager: true });

const allLocations = Object.values(locationModules).reduce((acc, module) => {
  // 각 모듈에서 'locations' export를 가져와서 하나의 객체로 병합합니다.
  if (module.locations) {
    return { ...acc, ...module.locations };
  }
  return acc;
}, {});

export default allLocations;