/**
 * Bio 메타데이터를 프롬프트용 텍스트로 포맷팅
 */

function formatUserMetadataForPrompt(userMetadata, category, fullName) {
  if (!userMetadata?.extractedMetadata) {
    return '';
  }

  const meta = userMetadata.extractedMetadata;
  let guide = '\n[🎯 작성자 고유 스타일 (실제 분석 결과)]\n';
  guide += `"${fullName}"님의 글쓰기 특징을 자연스럽게 반영하세요:\n\n`;

  if (meta.tone) {
    guide += `- 어조/톤: ${meta.tone}\n`;
  }

  if (meta.communicationStyle) {
    guide += `- 소통 방식: ${meta.communicationStyle}\n`;
  }

  if (meta.preferredPhrasing && meta.preferredPhrasing.length > 0) {
    guide += `- 자주 쓰는 표현: ${meta.preferredPhrasing.slice(0, 5).join(', ')}\n`;
  }

  if (meta.politicalValues && meta.politicalValues.length > 0) {
    guide += `- 정치적 가치관: ${meta.politicalValues.slice(0, 3).join(', ')}\n`;
  }

  if (meta.targetAudience) {
    guide += `- 주요 독자층: ${meta.targetAudience}\n`;
  }

  // 카테고리별 특화 표현
  if (userMetadata.typeMetadata?.keyPhrases && userMetadata.typeMetadata.keyPhrases.length > 0) {
    guide += `- "${category}" 카테고리 특화 표현: ${userMetadata.typeMetadata.keyPhrases.slice(0, 3).join(', ')}\n`;
  }

  guide += '\n**중요**: 위 스타일을 자연스럽게 녹여내되, 과도하게 의식하거나 나열식으로 표현하지 마세요.\n\n---\n';

  return guide;
}

module.exports = {
  formatUserMetadataForPrompt
};
