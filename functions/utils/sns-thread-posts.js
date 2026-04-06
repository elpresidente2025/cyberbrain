const SHORT_URL_PATTERN = /https:\/\/ai-secretary-6e9c8\.web\.app\/s\/[0-9A-Za-z]+/g;
const BLOG_CTA_ONLY_PATTERN = /^\s*(?:더\s*자세한\s*내용은\s*블로그에서\s*확인해(?:주세요|보세요)|자세한\s*내용은\s*블로그에서\s*확인해(?:주세요|보세요)|블로그\s*링크)\s*[:：]?\s*$/;

function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i += 1) {
    if (!/\s/.test(str.charAt(i))) {
      count += 1;
    }
  }
  return count;
}

function normalizeBlogUrl(url) {
  if (!url) return '';
  const trimmed = String(url).trim();
  if (!trimmed || trimmed === 'undefined' || trimmed === 'null') return '';
  return trimmed;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripBlogUrlArtifacts(text, blogUrl) {
  const normalizedUrl = normalizeBlogUrl(blogUrl);
  const urlPattern = normalizedUrl ? new RegExp(escapeRegExp(normalizedUrl), 'g') : null;

  const lines = String(text || '')
    .split('\n')
    .map((line) => {
      let cleaned = String(line || '').replace(SHORT_URL_PATTERN, '');
      if (urlPattern) {
        cleaned = cleaned.replace(urlPattern, '');
      }
      cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
      if (!cleaned) return '';
      if (BLOG_CTA_ONLY_PATTERN.test(cleaned)) return '';
      return cleaned;
    })
    .filter(Boolean);

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function enforceThreadBlogUrlAtEnd(posts, blogUrl) {
  const normalizedUrl = normalizeBlogUrl(blogUrl);
  if (!normalizedUrl || !Array.isArray(posts) || posts.length === 0) return posts;

  const normalizedPosts = posts.map((post) => {
    const content = stripBlogUrlArtifacts(post?.content || '', normalizedUrl);
    return {
      ...post,
      content,
      wordCount: countWithoutSpace(content)
    };
  });

  const lastIndex = normalizedPosts.length - 1;
  const lastPost = normalizedPosts[lastIndex] || {};
  const lastContent = String(lastPost.content || '').trim();
  const nextContent = [lastContent, normalizedUrl].filter(Boolean).join('\n');

  normalizedPosts[lastIndex] = {
    ...lastPost,
    content: nextContent,
    wordCount: countWithoutSpace(nextContent)
  };

  return normalizedPosts;
}

module.exports = {
  normalizeBlogUrl,
  stripBlogUrlArtifacts,
  enforceThreadBlogUrlAtEnd,
  countWithoutSpace
};
