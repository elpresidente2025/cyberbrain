/**
 * 사용자 호칭 유틸리티: 직책/지역/상태(현역/예비/후보)에 맞는 인사말용 호칭 생성 및 보조 함수
 */

import { hasAdminAccess } from './authz';

const norm = (v) => (v ?? '').toString().trim();

export const getUserDisplayTitle = (user) => {
  if (!user) return '';

  const position = norm(user.position);
  const regionMetro = norm(user.regionMetro);
  const regionLocal = norm(user.regionLocal);
  const status = norm(user.status);

  if (!position) return '';

  let baseTitle = '';
  switch (position) {
    case '국회의원':
      baseTitle = '국회의원';
      break;
    case '광역의원': {
      if (regionMetro.endsWith('도')) baseTitle = '도의원';
      else if (regionMetro.endsWith('시')) baseTitle = '시의원';
      else baseTitle = '광역의원';
      break;
    }
    case '기초의원': {
      if (regionLocal.endsWith('구')) baseTitle = '구의원';
      else if (regionLocal.endsWith('군')) baseTitle = '군의원';
      else if (regionLocal.endsWith('시')) baseTitle = '시의원';
      else baseTitle = '기초의원';
      break;
    }
    case '광역자치단체장': {
      // 광역자치단체장: 시장, 도지사 등
      if (regionMetro.endsWith('시')) baseTitle = '시장';
      else if (regionMetro.endsWith('도')) baseTitle = '도지사';
      else baseTitle = '광역자치단체장';
      break;
    }
    case '기초자치단체장': {
      // 기초자치단체장: 시장, 구청장, 군수 등
      if (regionLocal.endsWith('시')) baseTitle = '시장';
      else if (regionLocal.endsWith('구')) baseTitle = '구청장';
      else if (regionLocal.endsWith('군')) baseTitle = '군수';
      else baseTitle = '기초자치단체장';
      break;
    }
    default:
      baseTitle = position;
  }

  if (status === '예비') return `${baseTitle} 예비후보님`;
  if (status === '후보') return `${baseTitle} 후보님`;
  return `${baseTitle}님`;
};

export const getUserFullTitle = (user) => {
  if (!user) return '사용자님';
  const name = norm(user.name) || norm(user.displayName) || '사용자';
  const displayTitle = getUserDisplayTitle(user);
  return displayTitle ? `${name} ${displayTitle}` : `${name}님`;
};

export const getUserRegionInfo = (user) => {
  if (!user) return '';
  const parts = [norm(user.regionMetro), norm(user.regionLocal), norm(user.electoralDistrict)].filter(Boolean);
  return parts.length ? parts.join(' > ') : '';
};

export const getUserPositionColor = (user) => {
  const position = norm(user?.position);
  switch (position) {
    case '국회의원':
      return 'primary';
    case '광역의원':
      return 'secondary';
    case '기초의원':
      return 'success';
    default:
      return 'default';
  }
};

export const getUserStatusIcon = (user) => {
  if (!user) return '👤';
  if (hasAdminAccess(user)) return '⭐';
  const position = norm(user.position);
  const status = norm(user.status);
  if (status === '예비') return '⏳';
  switch (position) {
    case '국회의원':
      return '🏛️';
    case '광역의원':
      return '🏙️';
    case '기초의원':
      return '🏘️';
    default:
      return '👤';
  }
};

