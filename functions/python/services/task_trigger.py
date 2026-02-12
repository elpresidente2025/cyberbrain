# services/task_trigger.py
"""
Cloud Tasks Trigger for Pipeline Step Chaining

NOTE: Cloud Tasks 사용을 위해서는 다음 사전 설정이 필요합니다:
1. gcloud tasks queues create pipeline-steps --location=asia-northeast3
2. 서비스 계정에 Cloud Tasks Enqueuer 권한 부여
"""

import os
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 환경 설정
PROJECT_ID = os.environ.get("GCLOUD_PROJECT", "ai-secretary-6e9c8")
LOCATION = os.environ.get("FUNCTION_REGION", "asia-northeast3")
QUEUE_NAME = os.environ.get("TASKS_QUEUE_NAME", "pipeline-steps")

# Cloud Tasks 사용 여부 (로컬 테스트 시 False)
USE_CLOUD_TASKS = os.environ.get("USE_CLOUD_TASKS", "true").lower() == "true"


def create_step_task(job_id: str, step_index: int, delay_seconds: int = 0) -> Optional[str]:
    """
    Cloud Tasks로 다음 단계 예약
    
    Args:
        job_id: 파이프라인 Job ID
        step_index: 실행할 단계 인덱스
        delay_seconds: 지연 시간 (초)
    
    Returns:
        Task 이름 또는 None (로컬 모드)
    """
    
    if not USE_CLOUD_TASKS:
        logger.info(f"[Local Mode] Would trigger step {step_index} for job {job_id}")
        # 로컬 테스트 시 직접 HTTP 호출로 대체
        return _trigger_local(job_id, step_index)
    
    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
        
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(PROJECT_ID, LOCATION, QUEUE_NAME)
        
        # 타겟 URL
        url = f"https://{LOCATION}-{PROJECT_ID}.cloudfunctions.net/pipeline_step"
        
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "jobId": job_id,
                    "stepIndex": step_index
                }).encode(),
                # OIDC 토큰으로 인증
                "oidc_token": {
                    "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
                }
            }
        }
        
        # 지연 실행 설정
        if delay_seconds > 0:
            scheduled_time = timestamp_pb2.Timestamp()
            scheduled_time.FromSeconds(int(time.time()) + delay_seconds)
            task["schedule_time"] = scheduled_time
        
        response = client.create_task(parent=parent, task=task)
        logger.info(f"Created task: {response.name} for job {job_id} step {step_index}")
        return response.name
        
    except ImportError:
        logger.warning("google-cloud-tasks not installed, falling back to local trigger")
        return _trigger_local(job_id, step_index)
    except Exception as e:
        logger.error(f"Failed to create Cloud Task: {e}")
        # 폴백: 직접 트리거 시도
        return _trigger_local(job_id, step_index)


def _trigger_local(job_id: str, step_index: int) -> Optional[str]:
    """
    로컬 테스트용 직접 HTTP 호출 (fire-and-forget)
    
    NOTE: 프로덕션에서는 Cloud Tasks 사용 권장
    """
    import threading
    import requests
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    
    def _do_trigger():
        try:
            # 로컬 또는 프로덕션 URL
            base_url = os.environ.get(
                "PIPELINE_STEP_URL",
                f"https://{LOCATION}-{PROJECT_ID}.cloudfunctions.net/pipeline_step"
            )
            
            # OIDC 토큰 발급 시도 (Cloud Functions 인증용)
            headers = {"Content-Type": "application/json"}
            try:
                auth_req = Request()
                # Cloud Functions URL을 타겟으로 토큰 요청
                token = id_token.fetch_id_token(auth_req, base_url)
                headers["Authorization"] = f"Bearer {token}"
                logger.info("Added OIDC token to local trigger request")
            except Exception as auth_err:
                logger.warning(f"Failed to fetch OIDC token for local trigger: {auth_err}")
                # 로컬 에뮬레이터 환경 등에서는 토큰 없이 진행할 수 있음
            
            response = requests.post(
                base_url,
                json={"jobId": job_id, "stepIndex": step_index},
                headers=headers,
                timeout=10  # 트리거만 하고 응답 기다리지 않음
            )
            logger.info(f"Local trigger response: {response.status_code}")
        except requests.exceptions.Timeout:
            logger.info(f"Local trigger for job {job_id} step {step_index} sent (timeout expected)")
        except Exception as e:
            logger.warning(f"Local trigger failed: {e}")
    
    thread = threading.Thread(target=_do_trigger, daemon=True)
    thread.start()
    return f"local-trigger-{job_id}-{step_index}"
