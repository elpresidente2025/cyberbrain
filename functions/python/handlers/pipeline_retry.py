# handlers/pipeline_retry.py
"""
Pipeline Retry Handler - POST /pipeline/retry

실패한 파이프라인 단계를 재시도합니다.
"""

import json
import logging
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def handle_retry(req: https_fn.Request) -> https_fn.Response:
    """
    실패한 단계 재시도
    
    Request Body:
        {
            "jobId": "uuid",
            "stepIndex": 3  // 선택적 - 없으면 실패한 단계부터
        }
    
    Response:
        {
            "success": true,
            "jobId": "uuid",
            "retryFromStep": 3,
            "message": "..."
        }
    """
    try:
        # Lazy imports
        from services.job_manager import JobManager
        from services.task_trigger import create_step_task
        from datetime import datetime
        
        data = req.get_json(silent=True) or {}
        job_id = data.get("jobId")
        
        if not job_id:
            return https_fn.Response(
                json.dumps({"error": "jobId required", "code": "INVALID_INPUT"}),
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
        
        # 재시도 가능한 상태인지 확인
        if job_data["status"] == "running":
            return https_fn.Response(
                json.dumps({
                    "error": "Job is still running",
                    "code": "INVALID_STATE"
                }),
                status=400,
                mimetype="application/json"
            )
        
        if job_data["status"] == "completed":
            return https_fn.Response(
                json.dumps({
                    "error": "Job already completed",
                    "code": "INVALID_STATE"
                }),
                status=400,
                mimetype="application/json"
            )
        
        # 재시도할 단계 결정
        retry_from_step = data.get("stepIndex")
        
        if retry_from_step is None:
            # 실패한 단계 찾기
            error_info = job_data.get("error", {})
            retry_from_step = error_info.get("stepIndex", job_data["currentStep"])
        
        # 유효한 단계인지 확인
        if retry_from_step < 0 or retry_from_step >= job_data["totalSteps"]:
            return https_fn.Response(
                json.dumps({
                    "error": f"Invalid step index: {retry_from_step}",
                    "code": "INVALID_INPUT"
                }),
                status=400,
                mimetype="application/json"
            )
        
        logger.info(f"Retrying job {job_id} from step {retry_from_step}")
        
        # Job 상태 리셋
        # 실패한 단계와 그 이후 단계들을 pending으로 초기화
        steps = job_data["steps"]
        for i in range(retry_from_step, job_data["totalSteps"]):
            step_key = str(i)
            if step_key in steps:
                steps[step_key]["status"] = "pending"
                steps[step_key]["duration"] = None
                steps[step_key]["startedAt"] = None
                steps[step_key]["completedAt"] = None
        
        # Firestore 업데이트
        job_manager.db.collection("pipeline_jobs").document(job_id).update({
            "status": "running",
            "currentStep": retry_from_step,
            "steps": steps,
            "error": None,
            "updatedAt": datetime.utcnow(),
            "lockedBy": None,
            "lockedAt": None
        })
        
        # 단계 트리거
        task_name = create_step_task(job_id, retry_from_step)
        logger.info(f"Triggered retry for job {job_id} step {retry_from_step}: {task_name}")
        
        return https_fn.Response(
            json.dumps({
                "success": True,
                "jobId": job_id,
                "retryFromStep": retry_from_step,
                "message": f"재시도가 시작되었습니다. 단계 {retry_from_step}부터 다시 실행합니다."
            }),
            status=202,
            mimetype="application/json"
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Retry failed: {e}")
        traceback.print_exc()
        
        return https_fn.Response(
            json.dumps({"error": str(e), "code": "INTERNAL_ERROR"}),
            status=500,
            mimetype="application/json"
        )
