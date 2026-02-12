# handlers/pipeline_start.py
"""
Pipeline Start Handler - POST /pipeline/start

파이프라인을 시작하고 job_id를 발급합니다.
첫 번째 단계를 Cloud Tasks로 트리거합니다.
"""

import json
import logging
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def handle_start(req: https_fn.Request) -> https_fn.Response:
    """
    파이프라인 시작 - job_id 발급 및 첫 단계 트리거
    
    Request Body:
        {
            "topic": "주제 (필수)",
            "category": "activity-report",
            "keywords": ["키워드1", "키워드2"],
            "user": { ... },
            "instructions": "...",
            "newsContext": "...",
            "pipeline": "modular"
        }
    
    Response (202 Accepted):
        {
            "success": true,
            "jobId": "uuid",
            "status": "running",
            "message": "..."
        }
    """

    try:
        # Lazy imports for faster cold start
        import asyncio
        from services.job_manager import JobManager
        from services.task_trigger import create_step_task
        from services.news_fetcher import fetch_naver_news, compress_news_with_ai, format_news_for_prompt, should_fetch_news
        # RAG & Style
        from rag_manager import LightRAGManager
        from agents.common.style_analyzer import extract_style_from_text
        from agents.common.gemini_client import get_client

        data = req.get_json(silent=True) or {}
        
        # 입력 검증
        topic = data.get("topic")
        if not topic:
            return https_fn.Response(
                json.dumps({"error": "topic is required", "code": "INVALID_INPUT"}),
                status=400,
                mimetype="application/json"
            )

        # 🛡️ [Security] 권한 및 사용량 체크
        # Node.js: checkGenerationPermission(uid)
        uid = data.get("uid") or user_profile.get("uid")
        if not uid:
             return https_fn.Response(
                json.dumps({"error": "User ID is required", "code": "UNAUTHENTICATED"}),
                status=401,
                mimetype="application/json"
            )
            
        try:
            from firebase_admin import firestore
            from services.access_control import check_generation_permission
            
            db = firestore.client()
            perm_result = check_generation_permission(uid, db)
            
            if not perm_result["allowed"]:
                return https_fn.Response(
                    json.dumps({
                        "error": perm_result.get("message", "권한이 없습니다."),
                        "code": "PERMISSION_DENIED",
                        "reason": perm_result.get("reason"),
                        "suggestion": perm_result.get("suggestion")
                    }),
                    status=403,
                    mimetype="application/json"
                )
                
            logger.info(f"✅ Permission granted for {uid}: {perm_result['reason']} (remaining: {perm_result.get('remaining', 'N/A')})")
            
        except Exception as e:
            logger.error(f"Permission check error: {e}")
            return https_fn.Response(
                json.dumps({"error": "권한 확인 중 오류가 발생했습니다.", "code": "INTERNAL_ERROR"}),
                status=500,
                mimetype="application/json"
            )

        category = data.get("category", "activity-report")
        user_profile = data.get("user", {})

        # --- Async Context Preparation Helper ---
        async def prepare_additional_context():
            results = {
                "newsContext": data.get("newsContext", ""),
                "ragContext": "",
                "styleHints": {}, # style_analyzer output
            }
            
            tasks = []
            
            # 1. News Fetching
            # 이미 newsContext가 있거나, newsDataText(사용자 입력)가 있으면 스킵할 수도 있음
            # 하지만 Node.js 로직에 따라 shouldFetchNews가 true이면 가져오는 것이 일반적
            # 여기선 newsContext가 없을 때만 가져오도록 설정
            if not results["newsContext"] and should_fetch_news(category):
                async def fetch_news_task():
                    try:
                        # topic이 없으면 뉴스 검색 불가
                        if not topic: return ""
                        news_items = await fetch_naver_news(topic) # Changed from fetch_news to fetch_naver_news to match original import
                        if news_items:
                            return await compress_news_with_ai(news_items)
                    except Exception as e:
                        logger.error(f"News fetch error: {e}")
                    return ""
                tasks.append(asyncio.create_task(fetch_news_task()))
                
            # 2. Style Analysis
            bio = user_profile.get("bio", "")
            if bio and len(bio) > 50:
                async def style_task():
                    try:
                        # 간단한 스타일 분석 시뮬레이션 (실제로는 style_analyzer.py 사용)
                        from services.style_analyzer import analyze_style_from_bio
                        return await analyze_style_from_bio(bio)
                    except Exception as e:
                        logger.error(f"Style analysis error: {e}")
                        return {}
                tasks.append(asyncio.create_task(style_task()))

            # 3. Topic Classification (Auto)
            if category in ["auto", "general", "activity-report"] and topic:
                async def classify_task():
                    try:
                        from services.topic_classifier import classify_topic
                        result = await classify_topic(topic)
                        return result.get("writingMethod")
                    except Exception as e:
                        logger.error(f"Topic classification error: {e}")
                        return None
                tasks.append(asyncio.create_task(classify_task()))
                
            if not tasks: return results
            
            # Wait for all tasks
            done_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Map results back (순서 중요: News -> Style -> Classify)
            task_index = 0
            
            if not results["newsContext"] and should_fetch_news(category):
                if not isinstance(done_results[task_index], Exception):
                    results["newsContext"] = done_results[task_index]
                task_index += 1
                
            if bio and len(bio) > 50:
                if not isinstance(done_results[task_index], Exception):
                    results["styleHints"] = done_results[task_index]
                task_index += 1
                
            if category in ["auto", "general", "activity-report"] and topic:
                if not isinstance(done_results[task_index], Exception) and done_results[task_index]:
                    results["classifiedCategory"] = done_results[task_index]
                task_index += 1

            return results

        # Run Async Preparation (News, RAG, Style, Auto-Classification)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            additional_context = loop.run_until_complete(prepare_additional_context(topic, category, user_profile, data))
            loop.close()
        except Exception as e:
            logger.error(f"Context preparation failed: {e}")
            additional_context = {}
        
        # 주제 분류 결과가 있으면 카테고리 업데이트
        if additional_context.get("classifiedCategory"):
            category = additional_context["classifiedCategory"]
            logger.info(f"🤖 Category auto-classified to: {category}")
            
        context = {
            "topic": topic,
            "category": category,
            "keywords": data.get("keywords", []),
            "userProfile": user_profile,
            "newsContext": additional_context.get("newsContext", ""),
            "ragContext": additional_context.get("ragContext", ""),
            "styleHints": additional_context.get("styleHints", {}),
            "styleFingerprint": additional_context.get("styleFingerprint", {}),
        }

        # 입력 데이터 구성
        input_data = {
            "topic": topic,
            "category": category,
            "keywords": data.get("keywords", []),
            "userProfile": user_profile,
            "instructions": data.get("instructions", ""),
            "stanceText": data.get("stanceText", ""),      # 🔑 [NEW] 입장문 (심층 주제)
            "newsDataText": data.get("newsDataText", ""),  # 🔑 [NEW] 사용자 제공 뉴스/데이터
            "newsContext": additional_context.get("newsContext", data.get("newsContext", "")),
            "styleHints": additional_context.get("styleHints", {}), # 🔑 [NEW] 스타일 분석 결과
            "ragContext": additional_context.get("ragContext", ""), # 🔑 [NEW] RAG 결과
            "background": data.get("background", ""),
            "references": data.get("references", []),
            "targetWordCount": data.get("targetWordCount", 2000),
        }
        
        pipeline = data.get("pipeline", "modular")
        
        logger.info(f"Starting pipeline '{pipeline}' for topic: {topic[:50]}...")
        
        # Job 생성
        job_manager = JobManager()
        job_id = job_manager.create_job(input_data, pipeline)
        
        # 첫 번째 단계 트리거 (Cloud Tasks)
        task_name = create_step_task(job_id, step_index=0)
        logger.info(f"Triggered first step for job {job_id}: {task_name}")
        
        return https_fn.Response(
            json.dumps({
                "success": True,
                "jobId": job_id,
                "status": "running",
                "message": "파이프라인이 시작되었습니다."
            }),
            status=202,  # Accepted
            mimetype="application/json"
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Pipeline start failed: {e}")
        traceback.print_exc()
        
        return https_fn.Response(
            json.dumps({
                "error": str(e),
                "code": "INTERNAL_ERROR"
            }),
            status=500,
            mimetype="application/json"
        )
