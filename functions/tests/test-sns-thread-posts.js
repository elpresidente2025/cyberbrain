const assert = require('assert');
const {
  enforceThreadBlogUrlAtEnd,
  stripBlogUrlArtifacts,
} = require('../utils/sns-thread-posts');

function testStripBlogUrlArtifactsRemovesStandaloneCtaLine() {
  const blogUrl = 'https://blog.naver.com/example/123';
  const text = [
    '핵심 메시지를 먼저 전합니다.',
    `더 자세한 내용은 블로그에서 확인해주세요: ${blogUrl}`,
    '추가 설명입니다.',
  ].join('\n');

  const cleaned = stripBlogUrlArtifacts(text, blogUrl);

  assert.strictEqual(
    cleaned,
    ['핵심 메시지를 먼저 전합니다.', '추가 설명입니다.'].join('\n')
  );
}

function testEnforceThreadBlogUrlAtEndKeepsSingleFinalUrl() {
  const blogUrl = 'https://blog.naver.com/example/123';
  const posts = [
    { order: 1, content: `첫 게시물입니다.\n${blogUrl}` },
    { order: 2, content: `마무리 설명입니다.\n더 자세한 내용은 블로그에서 확인해주세요: ${blogUrl}` },
  ];

  const normalized = enforceThreadBlogUrlAtEnd(posts, blogUrl);

  assert.strictEqual(normalized[0].content.includes(blogUrl), false);
  assert.strictEqual(normalized[1].content, `마무리 설명입니다.\n${blogUrl}`);
  assert.strictEqual(
    normalized.reduce((sum, post) => sum + (post.content.match(new RegExp(blogUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length, 0),
    1
  );
}

function testEnforceThreadBlogUrlAtEndRemovesShortUrlArtifacts() {
  const blogUrl = 'https://blog.naver.com/example/123';
  const shortUrl = 'https://ai-secretary-6e9c8.web.app/s/abc123';
  const posts = [
    { order: 1, content: `첫 게시물입니다.\n${shortUrl}` },
    { order: 2, content: '마무리 설명입니다.' },
  ];

  const normalized = enforceThreadBlogUrlAtEnd(posts, blogUrl);

  assert.strictEqual(normalized[0].content.includes(shortUrl), false);
  assert.strictEqual(normalized[1].content.endsWith(blogUrl), true);
}

function run() {
  testStripBlogUrlArtifactsRemovesStandaloneCtaLine();
  testEnforceThreadBlogUrlAtEndKeepsSingleFinalUrl();
  testEnforceThreadBlogUrlAtEndRemovesShortUrlArtifacts();
  console.log('PASS test-sns-thread-posts');
}

run();
