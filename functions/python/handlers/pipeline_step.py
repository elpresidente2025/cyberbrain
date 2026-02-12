# handlers/pipeline_step.py
"""
Pipeline Step Handler - POST /pipeline/step

개별 에이전트 단계를 실행합니다.
Cloud Tasks에서 호출되거나 직접 호출될 수 있습니다.
"""

import json
import uuid
import logging
from datetime import datetime
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def handle_step(req: https_fn.Request) -> https_fn.Response:
    """
    개별 에이전트 단계 실행
    
    Request Body:
        {
            "jobId": "uuid",
            "stepIndex": 0
        }
    
    Response:
        {
            "success": true,
            "step": "StructureAgent",
            "duration": 45000,
            "nextStep": 1
        }
    """
    instance_id = str(uuid.uuid4())[:8]  # 이 인스턴스의 고유 ID
    job_id = None
    step_info = None
    job_manager = None
    
    try:
        # Lazy imports
        from services.job_manager import JobManager
        from services.step_executor import StepExecutor
        from services.task_trigger import create_step_task
        
        data = req.get_json(silent=True) or {}
        job_id = data.get("jobId")
        step_index = data.get("stepIndex", 0)
        
        if not job_id:
            return https_fn.Response(
                json.dumps({"error": "jobId required", "code": "INVALID_INPUT"}),
                status=400,
                mimetype="application/json"
            )
        
        logger.info(f"[{instance_id}] Processing job {job_id} step {step_index}")
        
        job_manager = JobManager()
        executor = StepExecutor()
        
        # 1. Job 데이터 로드
        job_data = job_manager.get_job(job_id)
        if not job_data:
            return https_fn.Response(
                json.dumps({"error": "Job not found", "code": "NOT_FOUND"}),
                status=404,
                mimetype="application/json"
            )
        
        # 이미 완료/실패한 job인지 확인
        if job_data["status"] in ["completed", "failed"]:
            logger.warning(f"Job {job_id} already {job_data['status']}")
            return https_fn.Response(
                json.dumps({
                    "error": f"Job already {job_data['status']}",
                    "code": "INVALID_STATE"
                }),
                status=400,
                mimetype="application/json"
            )
        
        # 2. 동시성 락 획득
        if not job_manager.acquire_lock(job_id, instance_id):
            logger.warning(f"Job {job_id} is locked by another process")
            return https_fn.Response(
                json.dumps({
                    "error": "Job is locked by another process",
                    "code": "CONFLICT"
                }),
                status=409,  # Conflict
                mimetype="application/json"
            )
        
        try:
            # 3. 현재 단계 정보
            pipeline = job_data.get("pipeline", "modular")
            step_info = executor.get_step_info(pipeline, step_index)
            
            if not step_info:
                # 모든 단계 완료
                logger.info(f"Job {job_id} all steps completed")
                job_manager.complete_job(job_id, job_data["context"])
                return https_fn.Response(
                    json.dumps({"success": True, "status": "completed"}),
                    status=200,
                    mimetype="application/json"
                )
            
            agent_name = step_info["name"]
            
            # 4. 단계 시작 표시
            job_manager.update_step_status(
                job_id, step_index, "running",
                startedAt=datetime.utcnow()
            )
            
            # 5. 에이전트 실행
            context = job_data["context"]
            result, duration_ms = executor.run_sync(step_info, context)
            
            # 6. 결과 저장 (context 병합)
            updated_context = context
            if result:
                updated_context = {**context, **result}
                
                # 특수 케이스: StructureAgent/WriterAgent의 content 결과
                if result.get("content") and agent_name in ["StructureAgent", "WriterAgent"]:
                    updated_context["content"] = result["content"]
                
                job_manager.save_context(job_id, updated_context)
            
            job_manager.update_step_status(
                job_id, step_index, "completed",
                duration=duration_ms,
                completedAt=datetime.utcnow()
            )
            
            logger.info(f"Job {job_id} step {step_index} ({agent_name}) completed in {duration_ms}ms")
            
            # 7. 다음 단계 트리거
            next_step = step_index + 1
            total_steps = executor.get_total_steps(pipeline)
            
            if next_step < total_steps:
                create_step_task(job_id, next_step)
                logger.info(f"Job {job_id} triggered step {next_step}")
            else:
                # 모든 단계 완료
                # 🧹 [Cleanup] 최종 결과물 후처리 (HTML 정리, 비문 수정, 요약문 이동)
                if updated_context.get("content"):
                    try:
                        from services.posts.content_processor import cleanup_post_content
                        
                        logger.info("Starting content cleanup...")
                        original_len = len(updated_context["content"])
                        cleaned_content = cleanup_post_content(updated_context["content"])
                        
                        updated_context["content"] = cleaned_content
                        logger.info(f"Context cleanup completed: {original_len} -> {len(cleaned_content)} chars")
                        
                    except Exception as e:
                        logger.error(f"Context cleanup failed: {e}")
                        # 실패해도 원본으로 진행

                job_manager.complete_job(job_id, updated_context)
                logger.info(f"Job {job_id} pipeline completed")
            
            return https_fn.Response(
                json.dumps({
                    "success": True,
                    "step": agent_name,
                    "stepIndex": step_index,
                    "duration": duration_ms,
                    "nextStep": next_step if next_step < total_steps else None
                }),
                status=200,
                mimetype="application/json"
            )
            
        finally:
            # 락 해제
            if job_manager:
                job_manager.release_lock(job_id)
            
    except Exception as e:
        import traceback
        logger.error(f"Step execution failed: {e}")
        traceback.print_exc()
        
        # 에러 시 Job 실패 처리
        if job_id and job_manager:
            try:
                job_manager.fail_job(job_id, {
                    "step": step_info["name"] if step_info else "unknown",
                    "message": str(e),
                    "stepIndex": data.get("stepIndex", 0) if 'data' in dir() else 0
                })
            except Exception as fail_err:
                logger.error(f"Failed to mark job as failed: {fail_err}")
        
        return https_fn.Response(
            json.dumps({
                "error": str(e),
                "code": "EXECUTION_ERROR"
            }),
            status=500,
            mimetype="application/json"
        )
