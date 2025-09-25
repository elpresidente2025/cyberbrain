'use strict';

// 서버 측에서 프로필로부터 표시 직함 생성
function getDisplayTitleFromProfile(p = {}) {
  const position = (p.position || '').toString().trim();
  const regionMetro = (p.regionMetro || '').toString().trim();
  const regionLocal = (p.regionLocal || '').toString().trim();
  const status = (p.status || '').toString().trim();

  let base = '';
  if (position === '국회의원') {
    base = '국회의원';
  } else if (position === '광역의원') {
    if (!regionMetro) base = '광역의원';
    else if (regionMetro.endsWith('도')) base = '도의원';
    else if (regionMetro.endsWith('시')) base = '시의원';
    else base = '광역의원';
  } else if (position === '기초의원') {
    if (!regionLocal) base = '기초의원';
    else if (regionLocal.endsWith('구')) base = '구의원';
    else if (regionLocal.endsWith('군')) base = '군의원';
    else if (regionLocal.endsWith('시')) base = '시의원';
    else base = '기초의원';
  } else {
    base = position || '';
  }

  // 서버에서는 "님"은 붙이지 않고 직함만 반환
  if (status === '예비' && base) return `${base} 후보`;
  if (status === '후보' && base) return `${base} 후보`;
  return base;
}

module.exports = { getDisplayTitleFromProfile };

