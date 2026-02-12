# services/job_manager.py
"""
Firestore Job Manager for Pipeline State Management
"""

from datetime import datetime, timedelta
from firebase_admin import firestore
from typing import Dict, Any, Optional, List
import uuid
import logging

logger = logging.getLogger(__name__)

COLLECTION = "pipeline_jobs"
LOCK_TIMEOUT_SECONDS = 300  # 5분


class JobManager:
    """파이프라인 Job 상태 관리"""
    
    def __init__(self):
        self.db = firestore.client()
    
    def create_job(self, input_data: Dict[str, Any], pipeline: str = "modular") -> str:
        """새 파이프라인 Job 생성"""
        job_id = str(uuid.uuid4())
        
        steps_config = self._get_pipeline_steps(pipeline)
        # Firestore는 배열 요소 개별 업데이트가 안되므로 Map 구조 사용
        steps = {
            str(i): {
                "name": s["name"], 
                "status": "pending", 
                "duration": None,
                "startedAt": None,
                "completedAt": None
            }
            for i, s in enumerate(steps_config)
        }
        
        job_data = {
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "status": "running",
            "currentStep": 0,
            "totalSteps": len(steps_config),
            "input": input_data,
            "pipeline": pipeline,
            "steps": steps,
            "context": self._create_initial_context(input_data),
            "result": None,
            "error": None,
            "lockedBy": None,
            "lockedAt": None
        }
        
        self.db.collection(COLLECTION).document(job_id).set(job_data)
        logger.info(f"Created job {job_id} with pipeline '{pipeline}'")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job 조회"""
        doc = self.db.collection(COLLECTION).document(job_id).get()
        return doc.to_dict() if doc.exists else None
    
    def acquire_lock(self, job_id: str, instance_id: str) -> bool:
        """
        동시성 제어를 위한 락 획득
        트랜잭션 사용하여 race condition 방지
        """
        job_ref = self.db.collection(COLLECTION).document(job_id)
        
        @firestore.transactional
        def update_in_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            
            data = snapshot.to_dict()
            locked_at = data.get("lockedAt")
            
            # 락이 없거나 타임아웃된 경우
            if locked_at is None:
                can_lock = True
            else:
                # Firestore timestamp를 datetime으로 변환
                if hasattr(locked_at, 'replace'):
                    lock_time = locked_at.replace(tzinfo=None)
                else:
                    lock_time = locked_at
                
                elapsed = datetime.utcnow() - lock_time
                can_lock = elapsed > timedelta(seconds=LOCK_TIMEOUT_SECONDS)
            
            if can_lock:
                transaction.update(ref, {
                    "lockedBy": instance_id,
                    "lockedAt": datetime.utcnow()
                })
                return True
            return False
        
        try:
            transaction = self.db.transaction()
            return update_in_transaction(transaction, job_ref)
        except Exception as e:
            logger.error(f"Failed to acquire lock for {job_id}: {e}")
            return False
    
    def release_lock(self, job_id: str):
        """락 해제"""
        try:
            self.db.collection(COLLECTION).document(job_id).update({
                "lockedBy": None,
                "lockedAt": None
            })
        except Exception as e:
            logger.warning(f"Failed to release lock for {job_id}: {e}")
    
    def update_step_status(self, job_id: str, step_index: int, status: str, **kwargs):
        """단계 상태 업데이트"""
        updates = {
            f"steps.{step_index}.status": status,
            "currentStep": step_index,
            "updatedAt": datetime.utcnow()
        }
        
        for key, value in kwargs.items():
            updates[f"steps.{step_index}.{key}"] = value
        
        self.db.collection(COLLECTION).document(job_id).update(updates)
        logger.info(f"Job {job_id} step {step_index} -> {status}")
    
    def save_context(self, job_id: str, context: Dict[str, Any]):
        """context 저장"""
        self.db.collection(COLLECTION).document(job_id).update({
            "context": context,
            "updatedAt": datetime.utcnow()
        })
    
    def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Job 완료 처리"""
        self.db.collection(COLLECTION).document(job_id).update({
            "status": "completed",
            "result": result,
            "updatedAt": datetime.utcnow(),
            "lockedBy": None,
            "lockedAt": None
        })
        logger.info(f"Job {job_id} completed")
    
    def fail_job(self, job_id: str, error: Dict[str, Any]):
        """Job 실패 처리"""
        self.db.collection(COLLECTION).document(job_id).update({
            "status": "failed",
            "error": error,
            "updatedAt": datetime.utcnow(),
            "lockedBy": None,
            "lockedAt": None
        })
        logger.error(f"Job {job_id} failed: {error}")
    
    def _get_pipeline_steps(self, pipeline: str) -> List[Dict[str, str]]:
        """파이프라인별 단계 목록"""
        pipelines = {
            "modular": [
                {"name": "StructureAgent", "module": "agents.core.structure_agent", "class": "StructureAgent"},
                {"name": "KeywordInjectorAgent", "module": "agents.core.keyword_injector_agent", "class": "KeywordInjectorAgent"},
                {"name": "StyleAgent", "module": "agents.core.style_agent", "class": "StyleAgent"},
                {"name": "ComplianceAgent", "module": "agents.core.compliance_agent", "class": "ComplianceAgent"},
                {"name": "SEOAgent", "module": "agents.core.seo_agent", "class": "SEOAgent"},
                {"name": "TitleAgent", "module": "agents.core.title_agent", "class": "TitleAgent"},
            ],
            "standard": [
                {"name": "WriterAgent", "module": "agents.core.writer_agent", "class": "WriterAgent"},
                {"name": "SEOAgent", "module": "agents.core.seo_agent", "class": "SEOAgent"},
            ]
        }
        return pipelines.get(pipeline, pipelines["modular"])
    
    def _create_initial_context(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """초기 context 생성"""
        user_profile = input_data.get("userProfile", {})
        return {
            "topic": input_data.get("topic"),
            "category": input_data.get("category", "activity-report"),
            "keywords": input_data.get("keywords", []),
            "userKeywords": input_data.get("keywords", []),
            "userProfile": user_profile,
            "author": user_profile,  # 일부 에이전트는 'author' 키 사용
            "status": user_profile.get("status", "active"),
            "instructions": input_data.get("instructions", ""),
            "newsContext": input_data.get("newsContext", ""),
            "background": input_data.get("background", ""),
            "references": input_data.get("references", []),
            "targetWordCount": input_data.get("targetWordCount", 2000)
        }
