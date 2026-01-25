const { StructureAgent } = require('./functions/services/agents/structure-agent');
const { KeywordInjectorAgent } = require('./functions/services/agents/keyword-injector-agent');
const { cleanupPostContent } = require('./functions/services/posts/content-processor');
const assert = require('assert');

// Mock utilities
const originalCallGenerativeModel = require('./functions/services/agents/structure-agent').callGenerativeModel;

async function runTests() {
    console.log('🧪 Starting Strict Pipeline Verification...\n');

    // Test 1: Content Processor Artifact Removal
    console.log('Test 1: Content Processor Artifact Removal');
    const dirtyContent = '"존경하는 시민 여러분...\" \n\n카테고리: 일상\n검색어 삽입 횟수: ...';
    const cleaned = cleanupPostContent(dirtyContent);
    assert(!cleaned.includes('"존경하는'), 'Leading quote not removed');
    assert(!cleaned.includes('카테고리:'), 'Metadata not removed');
    console.log('✅ Artifact removal passed\n');

    // Test 2: Structure Agent Validation
    console.log('Test 2: Structure Agent Validation');

    const structureAgent = new StructureAgent();

    // Case A: Short content
    const res1 = structureAgent.validateOutput('<p>Short</p>', 2000);
    console.log('DEBUG res1:', res1);
    assert.strictEqual(res1.passed, false, 'Short content should fail validation');
    assert.ok(res1.reason.includes('길이 부족'), 'Reason should be length');

    // Case B: JSON Leakage (Long enough, has HTML structure, but IS JSON)
    const longJson = '{ "content": "<p>' + 'A'.repeat(2000) + '</p><h2>Title</h2>" }';
    const res2 = structureAgent.validateOutput(longJson, 2000);
    console.log('DEBUG res2:', res2);
    assert.strictEqual(res2.passed, false, 'JSON artifact should fail');
    assert.ok(res2.reason.includes('JSON 문자열'), `Reason should be JSON, got: "${res2.reason}"`);

    console.log('✅ StructureAgent validation logic passed\n');


    // Test 3: Keyword Agent Validation
    console.log('Test 3: Keyword Agent Validation');
    const keywordAgent = new KeywordInjectorAgent();
    const keywords = ['A', 'B'];
    const countsFail = { 'A': 1, 'B': 4 };
    const res3 = keywordAgent.validateInjection(keywords, countsFail);
    assert.strictEqual(res3.passed, false, 'Missing keywords should fail');
    assert.ok(res3.reason.includes('미달'), 'Reason should be missing');

    const countsPass = { 'A': 4, 'B': 5 };
    const res4 = keywordAgent.validateInjection(keywords, countsPass);
    assert.strictEqual(res4.passed, true, 'Sufficient keywords should pass');

    console.log('✅ KeywordAgent validation logic passed\n');

    console.log('🎉 All logic verifications passed!');
}

runTests().catch(console.error);
