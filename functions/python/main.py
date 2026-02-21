import os
import json
import asyncio
from firebase_functions import https_fn, options
from firebase_admin import initialize_app


# Initialize Firebase Admin
initialize_app()

# Set LangSmith Configuration
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "ai-secretary-trace"


# ============================================================
# Step Functions Pattern - Pipeline Endpoints
# ============================================================

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=30,
    secrets=["GEMINI_API_KEY", "LANGCHAIN_API_KEY"]
)
def pipeline_start(req: https_fn.Request) -> https_fn.Response:
    """파이프라인 시작 - job_id 발급 및 첫 단계 트리거"""
    from handlers.pipeline_start import handle_start
    return handle_start(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.GB_2,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY", "LANGCHAIN_API_KEY"]
)
def pipeline_step(req: https_fn.Request) -> https_fn.Response:
    """개별 에이전트 단계 실행"""
    from handlers.pipeline_step import handle_step
    return handle_step(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=10
)
def pipeline_status(req: https_fn.Request) -> https_fn.Response:
    """파이프라인 진행 상태 조회"""
    from handlers.pipeline_status import handle_status
    return handle_status(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.GB_2,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY", "LANGCHAIN_API_KEY"]
)
def pipeline_retry(req: https_fn.Request) -> https_fn.Response:
    """실패한 단계 재시도"""
    from handlers.pipeline_retry import handle_retry
    return handle_retry(req)


# ============================================================
# Save Post Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def py_saveSelectedPost(req: https_fn.CallableRequest) -> dict:
    """선택된 원고 저장 (onCall, 프런트 호환 함수명)"""
    from handlers.save_handler import handle_save_selected_post_call
    return handle_save_selected_post_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def saveSelectedPost(req: https_fn.CallableRequest) -> dict:
    """선택된 원고 저장 (legacy callable 함수명 호환)"""
    from handlers.save_handler import handle_save_selected_post_call
    return handle_save_selected_post_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY", "LANGCHAIN_API_KEY"]
)
def generatePosts(req: https_fn.CallableRequest) -> dict:
    """원고 생성 (onCall, JS generatePosts 대체)."""
    from handlers.generate_posts import handle_generate_posts
    return handle_generate_posts(req)


# ============================================================
# Posts CRUD / Usage / Indexing Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def getUserPosts(req: https_fn.CallableRequest) -> dict:
    """Get user posts (legacy callable compatibility)."""
    from handlers.posts import handle_get_user_posts_call
    return handle_get_user_posts_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def getPost(req: https_fn.CallableRequest) -> dict:
    """Get a single post (legacy callable compatibility)."""
    from handlers.posts import handle_get_post_call
    return handle_get_post_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def updatePost(req: https_fn.CallableRequest) -> dict:
    """Update a post (legacy callable compatibility)."""
    from handlers.posts import handle_update_post_call
    return handle_update_post_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def deletePost(req: https_fn.CallableRequest) -> dict:
    """Delete a post (legacy callable compatibility)."""
    from handlers.posts import handle_delete_post_call
    return handle_delete_post_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def checkUsageLimit(req: https_fn.CallableRequest) -> dict:
    """Check monthly usage limit (legacy callable compatibility)."""
    from handlers.posts import handle_check_usage_limit_call
    return handle_check_usage_limit_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY"]
)
def indexPastPosts(req: https_fn.CallableRequest) -> dict:
    """Index past posts for RAG (legacy callable compatibility)."""
    from handlers.posts import handle_index_past_posts_call
    return handle_index_past_posts_call(req)
# ============================================================
# Profile Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def getUserProfile(req: https_fn.CallableRequest) -> dict:
    """Get current user profile (legacy callable compatibility)."""
    from handlers.profile import handle_get_user_profile_call
    return handle_get_user_profile_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def updateProfile(req: https_fn.CallableRequest) -> dict:
    """Update current user profile (legacy callable compatibility)."""
    from handlers.profile import handle_update_profile_call
    return handle_update_profile_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def checkDistrictAvailability(req: https_fn.CallableRequest) -> dict:
    """Check district availability (legacy callable compatibility)."""
    from handlers.profile import handle_check_district_availability_call
    return handle_check_district_availability_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def registerWithDistrictCheck(req: https_fn.CallableRequest) -> dict:
    """Register with district check (legacy callable compatibility)."""
    from handlers.profile import handle_register_with_district_check_call
    return handle_register_with_district_check_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def checkBonusEligibility(req: https_fn.CallableRequest) -> dict:
    """Check bonus eligibility (legacy callable compatibility)."""
    from handlers.publishing_bonus import handle_check_bonus_eligibility_call
    return handle_check_bonus_eligibility_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def useBonusGeneration(req: https_fn.CallableRequest) -> dict:
    """Consume one bonus generation (legacy callable compatibility)."""
    from handlers.publishing_bonus import handle_use_bonus_generation_call
    return handle_use_bonus_generation_call(req)


# ============================================================
# Party Verification Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def verifyPartyCertificate(req: https_fn.CallableRequest) -> dict:
    """Verify party certificate (legacy callable compatibility)."""
    from handlers.party_verification import handle_verify_party_certificate_call
    return handle_verify_party_certificate_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def verifyPaymentReceipt(req: https_fn.CallableRequest) -> dict:
    """Verify payment receipt (legacy callable compatibility)."""
    from handlers.party_verification import handle_verify_payment_receipt_call
    return handle_verify_payment_receipt_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30,
)
def getVerificationHistory(req: https_fn.CallableRequest) -> dict:
    """Get verification history (legacy callable compatibility)."""
    from handlers.party_verification import handle_get_verification_history_call
    return handle_get_verification_history_call(req)


# ============================================================
# Keyword Analysis Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=60,
    secrets=["GEMINI_API_KEY"]
)
def requestKeywordAnalysis(req: https_fn.CallableRequest) -> dict:
    """Request keyword analysis (legacy callable compatibility)."""
    from handlers.keyword_analysis import handle_request_keyword_analysis_call
    return handle_request_keyword_analysis_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30,
)
def getKeywordAnalysisResult(req: https_fn.CallableRequest) -> dict:
    """Get keyword analysis result (legacy callable compatibility)."""
    from handlers.keyword_analysis import handle_get_keyword_analysis_result_call
    return handle_get_keyword_analysis_result_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30,
)
def getKeywordAnalysisHistory(req: https_fn.CallableRequest) -> dict:
    """Get keyword analysis history (legacy callable compatibility)."""
    from handlers.keyword_analysis import handle_get_keyword_analysis_history_call
    return handle_get_keyword_analysis_history_call(req)


@https_fn.on_request(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY"]
)
def keywordAnalysisWorker(req: https_fn.Request) -> https_fn.Response:
    """Keyword analysis worker endpoint."""
    from handlers.keyword_analysis import handle_keyword_analysis_worker
    return handle_keyword_analysis_worker(req)


# ============================================================
# Emergency Admin Endpoint
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def emergencyRestoreAdmin(req: https_fn.CallableRequest) -> dict:
    """Emergency restore admin role (legacy callable compatibility)."""
    from handlers.emergency_admin import handle_emergency_restore_admin_call
    return handle_emergency_restore_admin_call(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def save_selected_post(req: https_fn.Request) -> https_fn.Response:
    """선택된 원고 저장 (onRequest 호환 엔드포인트)"""
    from handlers.save_handler import handle_save_selected_post
    return handle_save_selected_post(req)


# ============================================================
# SNS Conversion Endpoints
# ============================================================

@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def py_convertToSNS(req: https_fn.CallableRequest) -> dict:
    """원고를 X/Threads용으로 변환 (onCall, 프런트 호환 함수명)"""
    from handlers.sns_addon import handle_convert_to_sns_call
    return handle_convert_to_sns_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def convertToSNS(req: https_fn.CallableRequest) -> dict:
    """원고를 X/Threads용으로 변환 (legacy callable 함수명 호환)"""
    from handlers.sns_addon import handle_convert_to_sns_call
    return handle_convert_to_sns_call(req)





@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def py_getSNSUsage(req: https_fn.CallableRequest) -> dict:
    """SNS 변환 사용량 조회 (onCall, 프런트 호환 함수명)"""
    from handlers.sns_addon import handle_get_sns_usage_call
    return handle_get_sns_usage_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def getSNSUsage(req: https_fn.CallableRequest) -> dict:
    """SNS 변환 사용량 조회 (legacy callable 함수명 호환)"""
    from handlers.sns_addon import handle_get_sns_usage_call
    return handle_get_sns_usage_call(req)





@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def py_testSNS(req: https_fn.CallableRequest) -> dict:
    """SNS 변환 핸들러 헬스체크 (onCall, 프런트 호환 함수명)"""
    from handlers.sns_addon import handle_test_sns_call
    return handle_test_sns_call(req)


@https_fn.on_call(
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def testSNS(req: https_fn.CallableRequest) -> dict:
    """SNS 변환 핸들러 헬스체크 (legacy callable 함수명 호환)"""
    from handlers.sns_addon import handle_test_sns_call
    return handle_test_sns_call(req)





@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    secrets=["GEMINI_API_KEY"]
)
def convert_to_sns(req: https_fn.Request) -> https_fn.Response:
    """원고를 X/Threads용으로 변환"""
    from handlers.sns_addon import handle_convert_to_sns
    return handle_convert_to_sns(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def get_sns_usage(req: https_fn.Request) -> https_fn.Response:
    """SNS 변환 사용량 조회"""
    from handlers.sns_addon import handle_get_sns_usage
    return handle_get_sns_usage(req)


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def test_sns(req: https_fn.Request) -> https_fn.Response:
    """SNS 변환 핸들러 헬스체크"""
    from handlers.sns_addon import handle_test_sns
    return handle_test_sns(req)


# ============================================================
# Legacy Single Function (하위 호환용 유지)
# ============================================================

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST", "OPTIONS"]),
    region="asia-northeast3",
    memory=options.MemoryOption.GB_2,
    timeout_sec=540,
    secrets=["GEMINI_API_KEY", "LANGCHAIN_API_KEY"]
)
def generate_post(req: https_fn.Request) -> https_fn.Response:
    """HTTP Cloud Function for generating posts using Multi-Agent Pipeline."""
    try:
        request_json = req.get_json(silent=True)
        if not request_json:
            return https_fn.Response(json.dumps({'error': 'Invalid JSON'}), status=400, mimetype='application/json')

        # Debug: Check Env Vars
        print(f"🔍 [DEBUG] Env Check:")
        print(f"  - TRACING: {os.environ.get('LANGCHAIN_TRACING_V2')}")
        print(f"  - PROJECT: {os.environ.get('LANGCHAIN_PROJECT')}")
        print(f"  - API KEY: {os.environ.get('LANGCHAIN_API_KEY')[:10]}..." if os.environ.get('LANGCHAIN_API_KEY') else "  - API KEY: None")

        # Extract inputs
        topic = request_json.get('topic')
        category = request_json.get('category', 'activity-report')
        keywords = request_json.get('keywords', [])
        user_info = request_json.get('user', {})

        if not topic:
            return https_fn.Response(json.dumps({'error': 'Topic is required'}), status=400, mimetype='application/json')

        # Construct Orchestrator context
        context = {
            'topic': topic,
            'category': category,
            'keywords': keywords,
            'userKeywords': keywords,
            'author': user_info,
            'userProfile': user_info,
            'status': user_info.get('status', 'active'),
            'background': request_json.get('background', ''),
            'references': request_json.get('references', []),
            'instructions': request_json.get('instructions', ''),
            'newsContext': request_json.get('newsContext', ''),
            'targetWordCount': request_json.get('targetWordCount', 2000),
            'config': request_json.get('config', {})
        }

        # Options for Orchestrator
        orchestrator_options = {
            'pipeline': request_json.get('pipeline', 'modular'),
            'modelName': request_json.get('modelName', 'models/gemini-2.5-flash')
        }
        
        print(f"🔍 [DEBUG] Pipeline: {orchestrator_options.get('pipeline')}")

        # Run Pipeline
        if orchestrator_options.get('pipeline') == 'langgraph':
             print("🚀 [DEBUG] Initializing GraphOrchestrator...")
             from agents.graph_orchestrator import GraphOrchestrator
             orchestrator = GraphOrchestrator(orchestrator_options)
        else:
             print("⚙️ [DEBUG] Initializing Legacy Orchestrator...")
             from agents.orchestrator import Orchestrator
             orchestrator = Orchestrator(orchestrator_options)

        # Run async code in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(orchestrator.run(context))
        loop.close()

        return https_fn.Response(json.dumps(result, ensure_ascii=False), status=200, mimetype='application/json')

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return https_fn.Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')
