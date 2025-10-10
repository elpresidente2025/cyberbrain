// frontend/src/theme/components.js
// 재사용 가능한 스타일 컴포넌트

import { styled } from '@mui/material/styles';
import { Button, Box, Card, Container } from '@mui/material';
import { colors, spacing, borders, shadows, transitions } from './tokens';

/**
 * 브랜드 버튼 - 주요 CTA용
 */
export const BrandButton = styled(Button)({
  backgroundColor: colors.brand.primary,
  color: colors.text.black,
  fontWeight: 600,
  padding: `${spacing.sm}px ${spacing.lg}px`,
  borderRadius: borders.radius.md,
  transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
  '&:hover': {
    backgroundColor: colors.brand.primaryHover,
    transform: 'scale(0.98)',
  },
  '&:disabled': {
    backgroundColor: colors.ui.backgroundLight,
    color: colors.text.disabled,
  }
});

/**
 * 아웃라인 버튼 - 보조 액션용
 */
export const OutlineButton = styled(Button)({
  backgroundColor: 'transparent',
  color: colors.brand.primary,
  fontWeight: 600,
  border: `${borders.width.medium}px solid ${colors.brand.primary}`,
  borderRadius: borders.radius.md,
  transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
  '&:hover': {
    backgroundColor: colors.brand.primaryLight,
    borderColor: colors.brand.primaryHover,
    color: colors.brand.primaryHover,
  }
});

/**
 * 브랜드 카드 - 강조 콘텐츠용
 */
export const BrandCard = styled(Card)({
  backgroundColor: colors.ui.backgroundLight,
  border: `${borders.width.thin}px solid ${colors.brand.primaryBorder}`,
  borderRadius: borders.radius.lg,
  padding: spacing.lg,
  transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
  '&:hover': {
    borderColor: colors.brand.primary,
    boxShadow: shadows.glow.brand,
  }
});

/**
 * 소프트 카드 - 일반 콘텐츠용
 */
export const SoftCard = styled(Card)({
  backgroundColor: colors.ui.backgroundLight,
  borderRadius: borders.radius.lg,
  padding: spacing.lg,
  boxShadow: shadows.card,
  transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
  '&:hover': {
    boxShadow: shadows.cardHover,
  }
});

/**
 * 섹션 컨테이너 - 페이지 섹션용
 */
export const Section = styled('section')({
  padding: `${spacing.section.md}px 0`,
  borderBottom: `${borders.width.thin}px solid ${colors.ui.divider}`,
  position: 'relative',
  minHeight: '100dvh',
  scrollSnapAlign: 'start',
  display: 'flex',
  alignItems: 'center',
  '@media (max-width: 600px)': {
    padding: `${spacing.section.xs}px 0`,
    minHeight: '100dvh'
  },
  '@supports not (height: 100dvh)': {
    minHeight: '100vh'
  },
});

/**
 * 컨텐츠 컨테이너 - 중앙 정렬 래퍼
 */
export const ContentContainer = styled(Container)({
  maxWidth: '1200px',
  margin: '0 auto',
  padding: `0 ${spacing.lg}px`,
  '@media (max-width: 600px)': {
    padding: `0 ${spacing.md}px`,
  }
});

/**
 * 글로우 박스 - 강조 영역용
 */
export const GlowBox = styled(Box)({
  borderRadius: borders.radius.md,
  padding: spacing.lg,
  backgroundColor: colors.brand.primaryLight,
  border: `${borders.width.thin}px solid ${colors.brand.primaryBorder}`,
  boxShadow: shadows.glow.brand,
});

/**
 * 구분선
 */
export const Divider = styled(Box)({
  height: '2px',
  background: `linear-gradient(90deg, transparent 0%, ${colors.brand.primary} 20%, ${colors.brand.primary} 80%, transparent 100%)`,
  opacity: 0.3,
  margin: `${spacing.xl}px 0`,
});

/**
 * 배지 - 상태 표시용
 */
export const Badge = styled(Box)(({ variant = 'success' }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  padding: `${spacing.xxs}px ${spacing.sm}px`,
  borderRadius: borders.radius.round,
  fontSize: '0.875rem',
  fontWeight: 600,
  backgroundColor: colors.semantic[variant] || colors.semantic.success,
  color: variant === 'info' ? colors.text.black : colors.text.primary,
}));
