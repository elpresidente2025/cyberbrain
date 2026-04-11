const DEFAULT_PROJECT_ID = 'ai-secretary-6e9c8';
const DEFAULT_FUNCTIONS_REGION = 'asia-northeast3';

const normalizeUrl = (value) => String(value || '').replace(/\/+$/, '');
const ensureLeadingSlash = (value) => (String(value || '').startsWith('/') ? String(value) : `/${value}`);
const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID || DEFAULT_PROJECT_ID;

export const BRANDING = Object.freeze({
  companyNameKo: '사이버브레인',
  companyNameEn: 'CyberBrain',
  projectName: 'CyberBrain',
  serviceName: '전자두뇌비서관',
  serviceShortName: '전뇌비서관',
  supportEmail: import.meta.env.VITE_SUPPORT_EMAIL || 'support@cyberbrain.kr'
});

export const APP_ORIGIN = normalizeUrl(import.meta.env.VITE_APP_URL || 'https://cyberbrain.kr');
export const FUNCTIONS_REGION = import.meta.env.VITE_FUNCTIONS_REGION || DEFAULT_FUNCTIONS_REGION;
export const FUNCTIONS_BASE_URL = normalizeUrl(
  import.meta.env.VITE_FUNCTIONS_BASE_URL ||
  `https://${FUNCTIONS_REGION}-${projectId}.cloudfunctions.net`
);

export const LEGACY_APP_ORIGINS = Object.freeze([
  `https://${projectId}.web.app`,
  `https://${projectId}.firebaseapp.com`
]);

export const KNOWN_APP_ORIGINS = Object.freeze([
  APP_ORIGIN,
  ...LEGACY_APP_ORIGINS
]);

export const buildFunctionsUrl = (functionName) => `${FUNCTIONS_BASE_URL}/${String(functionName || '').replace(/^\/+/, '')}`;

export const buildAppUrl = (pathname = '/') => `${APP_ORIGIN}${ensureLeadingSlash(pathname)}`;

export const buildAssetUrl = (pathname = '/') => `${APP_ORIGIN}${ensureLeadingSlash(pathname)}`;

export const createShortUrlPattern = () => {
  const originPattern = KNOWN_APP_ORIGINS
    .filter(Boolean)
    .map(escapeRegExp)
    .join('|');
  return new RegExp(`(?:${originPattern})\\/s\\/[0-9A-Za-z]+`, 'g');
};

export const replaceKnownShortUrls = (text, replacement) => String(text || '').replace(createShortUrlPattern(), replacement);

export const containsKnownShortUrl = (text) => createShortUrlPattern().test(String(text || ''));
