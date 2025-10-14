/**
 * 향상된 메타데이터 힌트 생성기
 * extractedMetadata를 활용하여 더 개인화된 힌트 생성
 */

function generateEnhancedMetadataHints(userMetadata, category) {
  if (!userMetadata?.extractedMetadata) {
    return '';
  }

  const meta = userMetadata.extractedMetadata;
  const hints = [];

  // 어조/톤 힌트
  if (meta.tone) {
    hints.push(`어조: ${meta.tone}`);
  }

  // 소통 방식 힌트
  if (meta.communicationStyle) {
    const commStyle = typeof meta.communicationStyle === 'object'
      ? `${meta.communicationStyle.tone || ''} ${meta.communicationStyle.approach || ''}`.trim()
      : meta.communicationStyle;
    if (commStyle) hints.push(`소통: ${commStyle}`);
  }

  // 자주 쓰는 표현 (상위 3개)
  if (meta.preferredPhrasing && meta.preferredPhrasing.length > 0) {
    const topPhrases = meta.preferredPhrasing.slice(0, 3);
    hints.push(`특징 표현: "${topPhrases.join('", "')}"`);
  }

  // 정치적 가치관
  if (meta.politicalValues && meta.politicalValues.length > 0) {
    hints.push(`핵심 가치: ${meta.politicalValues.slice(0, 2).join(', ')}`);
  }

  // 주요 독자층
  if (meta.targetAudience) {
    hints.push(`독자층: ${meta.targetAudience}`);
  }

  // 카테고리별 특화 표현
  if (userMetadata.typeMetadata?.keyPhrases && userMetadata.typeMetadata.keyPhrases.length > 0) {
    const typePhrases = userMetadata.typeMetadata.keyPhrases.slice(0, 2);
    hints.push(`"${category}" 특화: "${typePhrases.join('", "')}"`);
  }

  // 최적화 힌트
  if (userMetadata.hints && Array.isArray(userMetadata.hints) && userMetadata.hints.length > 0) {
    hints.push(...userMetadata.hints.slice(0, 2));
  }

  return hints.length > 0 ? hints.join(' | ') : '';
}

module.exports = {
  generateEnhancedMetadataHints
};
