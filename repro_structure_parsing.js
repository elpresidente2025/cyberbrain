
// Mock of StructureAgent.parseResponse
function parseResponse(response) {
    if (!response) return { content: '', title: '' };

    // JSON 추출
    let parsed = null;
    try {
        // 코드블록 내 JSON
        const jsonMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/);
        if (jsonMatch) {
            parsed = JSON.parse(jsonMatch[1].trim());
        } else {
            // 직접 JSON
            const directMatch = response.match(/\{[\s\S]*\}/);
            if (directMatch) {
                parsed = JSON.parse(directMatch[0]);
            }
        }
    } catch (e) {
        console.warn('⚠️ [StructureAgent] JSON 파싱 실패:', e.message);
    }

    // 파싱 성공 시 타입 검증
    if (parsed) {
        // content 또는 html_content 키 지원
        const rawContent = parsed.content || parsed.html_content || '';
        const content = typeof rawContent === 'string' ? rawContent : '';
        let title = parsed.title;

        // 제목이 객체면 추출
        if (typeof title === 'object' && title !== null) {
            title = title.title || '';
            console.warn('⚠️ [StructureAgent] 제목이 객체로 반환됨, 추출:', title);
        }
        if (typeof title !== 'string') {
            title = '';
        }

        // 콘텐츠가 충분하면 반환
        if (content.length >= 100) {
            return { content, title };
        }
        console.warn('⚠️ [StructureAgent] 파싱된 콘텐츠 부족:', content.length, '자');
    }

    // 파싱 실패 또는 부실한 경우: HTML 태그가 있는 원본 추출 시도
    const htmlContent = response.match(/<p>[\s\S]*<\/p>/);
    if (htmlContent && htmlContent[0].length >= 100) {
        console.log('📝 [StructureAgent] HTML 콘텐츠 직접 추출:', htmlContent[0].length, '자');
        return {
            content: htmlContent[0],
            title: ''
        };
    }

    // 최종 폴백: 원본 텍스트 (코드블록 제거)
    const fallbackContent = response.replace(/```[\s\S]*?```/g, '').trim();
    console.warn('⚠️ [StructureAgent] 폴백 사용:', fallbackContent.length, '자');
    return {
        content: fallbackContent,
        title: ''
    };
}

// Test Cases
const cases = [
    {
        name: "Valid JSON Block",
        input: "```json\n{\"content\": \"This is a valid content string that is long enough to pass the check... " + ".".repeat(100) + "\"}\n```",
        expectSuccess: true
    },
    {
        name: "Broken JSON (Unescaped Quote)",
        input: "{\"content\": \"This has \"quotes\" inside and is long enough... " + ".".repeat(100) + "\"}",
        expectRawLeak: true
    },
    {
        name: "Broken JSON (Truncated)",
        input: "{\"content\": \"This is truncated and long enough... " + ".".repeat(100),
        expectRawLeak: true
    }
];

console.log("=== Starting Tests ===");
cases.forEach(c => {
    console.log(`\nTesting: ${c.name}`);
    const result = parseResponse(c.input);
    console.log("Result Content Preview:", result.content.substring(0, 50));

    if (result.content.startsWith("{") && result.content.includes("content")) {
        console.log("-> RESULT: LEAKED RAW JSON ✅ (Reproduction Confirmed)");
    } else if (result.content.startsWith("This")) {
        console.log("-> RESULT: CLEAN CONTENT");
    } else {
        console.log("-> RESULT: OTHER");
    }
});
