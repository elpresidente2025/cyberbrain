/**
 * functions/handlers/multimodal.js
 * 멀티모달 콘텐츠 생성 API (테스터 전용)
 * 
 * - 카드뉴스 생성
 * - 숏폼 스토리보드 생성
 */

'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { isAdminUser } = require('../common/rbac');
const { db } = require('../utils/firebaseAdmin');

// Python RAG 서비스 URL
const PYTHON_RAG_URL = process.env.PYTHON_RAG_URL;

/**
 * 테스터 여부 확인
 */
async function checkTesterAccess(uid) {
    const userDoc = await db.collection('users').doc(uid).get();
    if (!userDoc.exists) {
        throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const isTester = userData.isTester === true;
    const isAdmin = isAdminUser(userData);

    if (!isTester && !isAdmin) {
        throw new HttpsError('permission-denied', '테스터 전용 기능입니다.');
    }

    return { isTester, isAdmin, userData };
}

/**
 * 카드뉴스 생성 API
 * 
 * Request Body:
 * {
 *   topic: string,      // 주제
 *   numCards?: number   // 카드 수 (기본: 5)
 * }
 */
exports.generateCardNews = async (req, res) => {
    try {
        const uid = req.user?.uid;
        if (!uid) {
            return res.status(401).json({ error: '인증이 필요합니다.' });
        }

        // 테스터 권한 확인
        await checkTesterAccess(uid);

        const { topic, numCards = 5 } = req.body;

        if (!topic) {
            return res.status(400).json({ error: 'topic은 필수입니다.' });
        }

        if (!PYTHON_RAG_URL) {
            return res.status(503).json({ error: 'Python RAG 서비스가 설정되지 않았습니다.' });
        }

        console.log(`🎴 카드뉴스 생성 요청: uid=${uid}, topic="${topic}", cards=${numCards}`);

        // Python RAG 서비스 호출
        const response = await fetch(`${PYTHON_RAG_URL.replace('/rag_search', '/generate_cardnews')}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: uid,
                topic: topic,
                num_cards: numCards
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ Python 서비스 오류:', errorText);
            return res.status(500).json({ error: '카드뉴스 생성 실패' });
        }

        const data = await response.json();

        console.log(`✅ 카드뉴스 생성 완료: ${data.cards?.length || 0}장`);

        return res.json({
            success: true,
            topic,
            ...data
        });

    } catch (error) {
        console.error('❌ 카드뉴스 생성 오류:', error);

        if (error.code) {
            return res.status(error.httpErrorCode?.status || 500).json({ error: error.message });
        }

        return res.status(500).json({ error: error.message });
    }
};

/**
 * 숏폼 스토리보드 생성 API
 * 
 * Request Body:
 * {
 *   script: string,        // 원고 텍스트
 *   duration?: number      // 목표 시간 (초, 기본: 60)
 * }
 */
exports.generateShortformStoryboard = async (req, res) => {
    try {
        const uid = req.user?.uid;
        if (!uid) {
            return res.status(401).json({ error: '인증이 필요합니다.' });
        }

        // 테스터 권한 확인
        await checkTesterAccess(uid);

        const { script, duration = 60 } = req.body;

        if (!script) {
            return res.status(400).json({ error: 'script는 필수입니다.' });
        }

        console.log(`🎬 숏폼 스토리보드 생성 요청: uid=${uid}, duration=${duration}s`);

        // 장면 분할 (간단한 규칙 기반)
        const scenes = splitScriptToScenes(script, duration);

        // 각 장면에 대한 비주얼 프롬프트 생성
        const storyboard = scenes.map((scene, index) => ({
            scene_id: index + 1,
            start_time: scene.startTime,
            end_time: scene.endTime,
            narration: scene.text,
            visual_prompt: generateVisualPrompt(scene.text),
            b_roll_suggestion: suggestBRoll(scene.text)
        }));

        console.log(`✅ 스토리보드 생성 완료: ${storyboard.length}장면`);

        return res.json({
            success: true,
            total_duration: duration,
            scene_count: storyboard.length,
            storyboard
        });

    } catch (error) {
        console.error('❌ 스토리보드 생성 오류:', error);

        if (error.code) {
            return res.status(error.httpErrorCode?.status || 500).json({ error: error.message });
        }

        return res.status(500).json({ error: error.message });
    }
};

/**
 * 스크립트를 장면으로 분할
 */
function splitScriptToScenes(script, totalDuration) {
    // 문장 단위로 분할
    const sentences = script
        .split(/(?<=[.!?。？！])\s+/)
        .filter(s => s.trim().length > 0);

    if (sentences.length === 0) {
        return [{
            text: script,
            startTime: 0,
            endTime: totalDuration
        }];
    }

    // 문장을 장면으로 그룹화 (약 10-15초 단위)
    const targetSceneCount = Math.ceil(totalDuration / 12);
    const sentencesPerScene = Math.ceil(sentences.length / targetSceneCount);

    const scenes = [];
    let currentScene = [];
    const sceneDuration = totalDuration / Math.min(targetSceneCount, Math.ceil(sentences.length / sentencesPerScene));

    sentences.forEach((sentence, index) => {
        currentScene.push(sentence);

        if (currentScene.length >= sentencesPerScene || index === sentences.length - 1) {
            const sceneIndex = scenes.length;
            scenes.push({
                text: currentScene.join(' '),
                startTime: Math.round(sceneIndex * sceneDuration),
                endTime: Math.round((sceneIndex + 1) * sceneDuration)
            });
            currentScene = [];
        }
    });

    return scenes;
}

/**
 * 텍스트로부터 비주얼 프롬프트 생성
 */
function generateVisualPrompt(text) {
    // 키워드 추출 (간단한 규칙 기반)
    const keywords = [];

    if (text.includes('교통') || text.includes('도로')) keywords.push('transportation', 'road');
    if (text.includes('환경') || text.includes('공원')) keywords.push('environment', 'park', 'nature');
    if (text.includes('교육') || text.includes('학교')) keywords.push('education', 'school', 'students');
    if (text.includes('경제') || text.includes('일자리')) keywords.push('economy', 'jobs', 'business');
    if (text.includes('복지') || text.includes('노인')) keywords.push('welfare', 'elderly', 'care');
    if (text.includes('청년') || text.includes('젊은')) keywords.push('youth', 'young people');
    if (text.includes('안전') || text.includes('범죄')) keywords.push('safety', 'security');
    if (text.includes('문화') || text.includes('예술')) keywords.push('culture', 'art');

    if (keywords.length === 0) {
        keywords.push('professional', 'politician', 'city');
    }

    return `A professional photograph showing: ${keywords.join(', ')}. Clean, modern, optimistic mood.`;
}

/**
 * B-roll 영상 제안
 */
function suggestBRoll(text) {
    if (text.includes('교통') || text.includes('도로')) return '도로 주행 영상, 대중교통 이용 장면';
    if (text.includes('환경') || text.includes('공원')) return '공원 전경, 녹지 항공 촬영';
    if (text.includes('교육') || text.includes('학교')) return '학교 외관, 수업 장면';
    if (text.includes('경제') || text.includes('일자리')) return '사무실, 공장 가동 장면';
    if (text.includes('복지') || text.includes('노인')) return '복지관, 돌봄 서비스 장면';
    if (text.includes('청년')) return '청년 활동, 스타트업 장면';

    return '지역 전경, 시민 일상 장면';
}

/**
 * 지식 그래프 인덱싱 API (테스터 전용)
 * Bio 엔트리를 Python 지식 그래프에 인덱싱
 */
exports.indexToKnowledgeGraph = async (req, res) => {
    try {
        const uid = req.user?.uid;
        if (!uid) {
            return res.status(401).json({ error: '인증이 필요합니다.' });
        }

        // 테스터 권한 확인
        await checkTesterAccess(uid);

        if (!PYTHON_RAG_URL) {
            return res.status(503).json({ error: 'Python RAG 서비스가 설정되지 않았습니다.' });
        }

        // Bio 데이터 조회
        const bioDoc = await db.collection('bios').doc(uid).get();
        if (!bioDoc.exists) {
            return res.status(404).json({ error: 'Bio 데이터가 없습니다.' });
        }

        const bioData = bioDoc.data();
        const entries = bioData.entries || [];

        if (entries.length === 0) {
            return res.status(400).json({ error: '인덱싱할 엔트리가 없습니다.' });
        }

        console.log(`🔍 지식 그래프 인덱싱 요청: uid=${uid}, entries=${entries.length}`);

        // Python RAG 서비스 호출
        const response = await fetch(`${PYTHON_RAG_URL.replace('/rag_search', '/rag_index')}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: uid,
                entries: entries.map(e => ({
                    type: e.type,
                    title: e.title || '',
                    content: e.content || ''
                }))
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ Python 서비스 오류:', errorText);
            return res.status(500).json({ error: '인덱싱 실패' });
        }

        const data = await response.json();

        console.log(`✅ 지식 그래프 인덱싱 완료: ${data.indexed}개`);

        return res.json({
            success: true,
            ...data
        });

    } catch (error) {
        console.error('❌ 인덱싱 오류:', error);
        return res.status(500).json({ error: error.message });
    }
};
