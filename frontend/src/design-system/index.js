// design-system/index.js
// 디자인 시스템 통합 진입점

// CSS 토큰 불러오기 (이 파일을 import하면 자동으로 CSS가 로드됨)
import './tokens.css';

// 컴포넌트 내보내기
export { Button } from './components/Button';
export { Card, CardHeader, CardContent, CardFooter } from './components/Card';
export { Input, TextArea, FormField } from './components/Input';
export { Typography, SectionTitle, GradientText } from './components/Typography';

// 토큰 내보내기 (JS에서 사용 시)
export { tokens, rawTokens } from './tokens';
