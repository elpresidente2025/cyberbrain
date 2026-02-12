# handlers/pipeline_status.py
"""
Pipeline Status Handler - GET /pipeline/status

파이프라인 진행 상태를 조회합니다.
"""

import json
import logging
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def handle_status(req: https_fn.Request) -> https_fn.Response:
    """
    파이프라인 진행 상태 조회
    
    Query Parameters:
        jobId: 조회할 Job ID
    
    Response:
        {
            "jobId": "uuid",
            "status": "running",
            "currentStep": 2,
            "totalSteps": 6,
            "steps": { ... },
            "createdAt": "...",
            "updatedAt": "...",
            "result": null,  // 완료 시
            "error": null    // 실패 시
        }
    """
    try:
        # Lazy import
        from services.job_manager import JobManager
        
        # URL 쿼리에서 job_id 추출
        job_id = req.args.get("jobId")
        
        # 또는 path에서 추출: /pipeline/status/{job_id}
        if not job_id and "/" in req.path:
            parts = req.path.rstrip("/").split("/")
            # 마지막 부분이 UUID 형태인지 확인
            if len(parts) > 0 and len(parts[-1]) == 36 and "-" in parts[-1]:
                job_id = parts[-1]
        
        if not job_id:
            return https_fn.Response(
                json.dumps({
                    "error": "jobId required (use ?jobId=xxx or /status/{jobId})",
                    "code": "INVALID_INPUT"
                }),
                status=400,
                mimetype="application/json"
            )
        
        job_manager = JobManager()
        job_data = job_manager.get_job(job_id)
        
        if not job_data:
            return https_fn.Response(
                json.dumps({"error": "Job not found", "code": "NOT_FOUND"}),
                status=404,
                mimetype="application/json"
            )
        
        # 응답 구성
        response = {
            "jobId": job_id,
            "status": job_data["status"],
            "currentStep": job_data["currentStep"],
            "totalSteps": job_data["totalSteps"],
            "steps": job_data["steps"],
            "pipeline": job_data.get("pipeline", "modular"),
            "createdAt": _format_timestamp(job_data.get("createdAt")),
            "updatedAt": _format_timestamp(job_data.get("updatedAt")),
        }
        
        # 진행률 계산
        completed_steps = sum(
            1 for s in job_data["steps"].values() 
            if isinstance(s, dict) and s.get("status") == "completed"
        )
        response["progress"] = {
            "completed": completed_steps,
            "total": job_data["totalSteps"],
            "percentage": round(completed_steps / job_data["totalSteps"] * 100, 1)
        }
        
        # 현재 실행 중인 단계 이름
        current_step_key = str(job_data["currentStep"])
        if current_step_key in job_data["steps"]:
            response["currentStepName"] = job_data["steps"][current_step_key].get("name", "Unknown")
        
        # 완료된 경우 결과 포함
        if job_data["status"] == "completed":
            response["result"] = job_data.get("result")
        
        # 실패한 경우 에러 포함
        if job_data["status"] == "failed":
            response["error"] = job_data.get("error")
        
        return https_fn.Response(
            json.dumps(response, ensure_ascii=False, default=str),
            status=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Status query failed: {e}")
        traceback.print_exc()
        
        return https_fn.Response(
            json.dumps({"error": str(e), "code": "INTERNAL_ERROR"}),
            status=500,
            mimetype="application/json"
        )


def _format_timestamp(ts) -> str:
    """Firestore Timestamp를 ISO 문자열로 변환"""
    if ts is None:
        return None
    
    try:
        # Firestore Timestamp
        if hasattr(ts, 'isoformat'):
            return ts.isoformat()
        # datetime
        if hasattr(ts, 'strftime'):
            return ts.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        return str(ts)
    except:
        return str(ts)
