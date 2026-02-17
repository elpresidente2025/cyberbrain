# handlers/pipeline_step.py
"""
Pipeline Step Handler - POST /pipeline_step

Executes a single pipeline step and schedules the next one.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime

from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def _json_response(payload: dict, status: int) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False, default=str),
        status=status,
        mimetype="application/json",
    )


def handle_step(req: https_fn.Request) -> https_fn.Response:
    """
    Execute one step.

    Request Body:
        {
            "jobId": "uuid",
            "stepIndex": 0
        }
    """
    instance_id = str(uuid.uuid4())[:8]
    job_id = None
    step_info = None
    job_manager = None
    data = {}

    try:
        from services.job_manager import JobManager
        from services.step_executor import StepExecutor
        from services.task_trigger import create_step_task

        data = req.get_json(silent=True) or {}
        if not isinstance(data, dict):
            data = {}

        job_id = data.get("jobId")
        step_index = int(data.get("stepIndex", 0) or 0)

        if not job_id:
            return _json_response({"error": "jobId required", "code": "INVALID_INPUT"}, 400)

        logger.info("[%s] Processing job %s step %s", instance_id, job_id, step_index)

        job_manager = JobManager()
        executor = StepExecutor()

        # 1) Load job
        job_data = job_manager.get_job(job_id)
        if not job_data:
            return _json_response({"error": "Job not found", "code": "NOT_FOUND"}, 404)

        # 2) Skip if job already terminal
        if job_data.get("status") in ["completed", "failed"]:
            return _json_response(
                {
                    "error": f"Job already {job_data.get('status')}",
                    "code": "INVALID_STATE",
                },
                400,
            )

        # 3) Lock
        if not job_manager.acquire_lock(job_id, instance_id):
            return _json_response(
                {
                    "error": "Job is locked by another process",
                    "code": "CONFLICT",
                },
                409,
            )

        try:
            pipeline = str(job_data.get("pipeline") or "modular")
            step_info = executor.get_step_info(pipeline, step_index)

            if not step_info:
                logger.info("Job %s has no more steps; completing.", job_id)
                job_manager.complete_job(job_id, job_data.get("context") or {})
                return _json_response({"success": True, "status": "completed"}, 200)

            agent_name = step_info["name"]
            job_manager.update_step_status(
                job_id,
                step_index,
                "running",
                startedAt=datetime.utcnow(),
            )

            context = job_data.get("context") or {}
            result, duration_ms = executor.run_sync(step_info, context)

            # 4) Merge context
            updated_context = context
            if result:
                updated_context = {**context, **result}

                # Keep explicit content field for downstream steps.
                if result.get("content") and agent_name in ["StructureAgent", "WriterAgent"]:
                    updated_context["content"] = result["content"]

                job_manager.save_context(job_id, updated_context)

            # 5) Mark step completed
            job_manager.update_step_status(
                job_id,
                step_index,
                "completed",
                duration=duration_ms,
                completedAt=datetime.utcnow(),
            )

            logger.info(
                "Job %s step %s (%s) completed in %sms",
                job_id,
                step_index,
                agent_name,
                duration_ms,
            )

            # 6) Trigger next step or finalize
            next_step = step_index + 1
            total_steps = executor.get_total_steps(pipeline)

            if next_step < total_steps:
                create_step_task(job_id, next_step)
                logger.info("Job %s triggered step %s", job_id, next_step)
            else:
                # Final cleanup
                if updated_context.get("content"):
                    try:
                        from services.posts.content_processor import cleanup_post_content

                        original_len = len(updated_context["content"])
                        cleaned_content = cleanup_post_content(updated_context["content"])
                        updated_context["content"] = cleaned_content
                        logger.info(
                            "Context cleanup completed: %s -> %s chars",
                            original_len,
                            len(cleaned_content),
                        )
                    except Exception as exc:
                        logger.warning("Context cleanup failed (non-fatal): %s", exc)

                # Attach keyword validation metadata for Python-only consumers.
                if updated_context.get("content"):
                    try:
                        from services.posts.validation import (
                            validate_keyword_insertion,
                        )

                        user_keywords = updated_context.get("userKeywords") or updated_context.get("keywords") or []
                        auto_keywords = updated_context.get("autoKeywords") or []
                        if not isinstance(user_keywords, list):
                            user_keywords = []
                        if not isinstance(auto_keywords, list):
                            auto_keywords = []

                        keyword_result = validate_keyword_insertion(
                            updated_context.get("content", ""),
                            user_keywords,
                            auto_keywords,
                            updated_context.get("targetWordCount"),
                        )
                        updated_context["keywordResult"] = keyword_result

                        keyword_details = (keyword_result.get("details") or {}).get("keywords") or {}
                        if isinstance(keyword_details, dict):
                            updated_context["keywordCounts"] = {
                                keyword: int((info or {}).get("coverage") or (info or {}).get("count") or 0)
                                for keyword, info in keyword_details.items()
                                if isinstance(info, dict)
                            }

                        if not keyword_result.get("valid", True):
                            logger.warning(
                                "Keyword requirements still not satisfied after enforcement: %s",
                                keyword_result,
                            )
                    except Exception as exc:
                        logger.warning("Keyword validation failed (non-fatal): %s", exc)

                # Final output formatting (Python-native):
                # - strip generated slogan artifacts
                # - trim diagnostic tails / content after closing
                # - NOTE: 슬로건/후원 안내는 generate_posts 최종 응답 직전에만 부착
                # - expose wordCount + keywordValidation in final result
                if updated_context.get("content"):
                    try:
                        from services.posts.output_formatter import (
                            build_keyword_validation,
                            count_without_space,
                            finalize_output,
                        )
                        from services.posts.validation import (
                            enforce_repetition_requirements,
                            validate_keyword_insertion,
                        )

                        category = str(updated_context.get("category") or "")
                        sub_category = str(updated_context.get("subCategory") or "")
                        allow_diagnostic_tail = (
                            category == "current-affairs"
                            and sub_category == "current_affairs_diagnosis"
                        )

                        pre_finalize_content = str(updated_context.get("content") or "")
                        pre_finalize_word_count = int(count_without_space(pre_finalize_content))
                        context_analysis = (
                            updated_context.get("contextAnalysis")
                            if isinstance(updated_context.get("contextAnalysis"), dict)
                            else {}
                        )
                        must_preserve = (
                            context_analysis.get("mustPreserve")
                            if isinstance(context_analysis.get("mustPreserve"), dict)
                            else {}
                        )

                        final_result = finalize_output(
                            pre_finalize_content,
                            slogan="",
                            slogan_enabled=False,
                            donation_info="",
                            donation_enabled=False,
                            allow_diagnostic_tail=allow_diagnostic_tail,
                            keyword_result=updated_context.get("keywordResult"),
                            topic=str(updated_context.get("topic") or ""),
                            book_title_hint=str(must_preserve.get("bookTitle") or ""),
                            context_analysis=context_analysis,
                            full_name=str(updated_context.get("fullName") or ""),
                            target_word_count=updated_context.get("targetWordCount"),
                        )

                        post_finalize_content = str(final_result.get("content") or pre_finalize_content)
                        post_finalize_word_count = int(count_without_space(post_finalize_content))
                        if (
                            pre_finalize_word_count >= 1600
                            and post_finalize_word_count < int(pre_finalize_word_count * 0.75)
                        ):
                            ratio = (
                                post_finalize_word_count / pre_finalize_word_count
                                if pre_finalize_word_count
                                else 0.0
                            )
                            logger.warning(
                                "Finalize shrink guard triggered: pre=%s post=%s ratio=%.3f. "
                                "Rollback to pre-finalize content.",
                                pre_finalize_word_count,
                                post_finalize_word_count,
                                ratio,
                            )
                            post_finalize_content = pre_finalize_content
                            post_finalize_word_count = pre_finalize_word_count

                        logger.info(
                            "Final formatting length trace: pre=%s post=%s",
                            pre_finalize_word_count,
                            post_finalize_word_count,
                        )

                        updated_context["content"] = post_finalize_content

                        repetition_fix_result = enforce_repetition_requirements(updated_context["content"])
                        if repetition_fix_result.get("edited"):
                            repetition_candidate = str(
                                repetition_fix_result.get("content") or updated_context["content"]
                            )
                            repetition_candidate_word_count = int(count_without_space(repetition_candidate))
                            if (
                                post_finalize_word_count >= 1600
                                and repetition_candidate_word_count < int(post_finalize_word_count * 0.75)
                            ):
                                ratio = (
                                    repetition_candidate_word_count / post_finalize_word_count
                                    if post_finalize_word_count
                                    else 0.0
                                )
                                logger.warning(
                                    "Repetition shrink guard triggered: pre=%s post=%s ratio=%.3f. "
                                    "Skip repetition auto-fix content replacement.",
                                    post_finalize_word_count,
                                    repetition_candidate_word_count,
                                    ratio,
                                )
                            else:
                                updated_context["content"] = repetition_candidate
                                post_finalize_word_count = repetition_candidate_word_count
                                logger.info(
                                    "Repetition auto-fix applied before final validation: actions=%s, "
                                    "wordCount=%s",
                                    repetition_fix_result.get("actions"),
                                    post_finalize_word_count,
                                )
                        user_keywords = updated_context.get("userKeywords") or updated_context.get("keywords") or []
                        auto_keywords = updated_context.get("autoKeywords") or []
                        if not isinstance(user_keywords, list):
                            user_keywords = []
                        if not isinstance(auto_keywords, list):
                            auto_keywords = []

                        final_keyword_result = validate_keyword_insertion(
                            updated_context["content"],
                            user_keywords,
                            auto_keywords,
                            updated_context.get("targetWordCount"),
                        )
                        updated_context["keywordResult"] = final_keyword_result
                        updated_context["keywordValidation"] = build_keyword_validation(final_keyword_result)
                        updated_context["wordCount"] = int(count_without_space(updated_context["content"]))
                        logger.info(
                            "Python final output formatting completed: wordCount=%s, keywordValidation=%s",
                            updated_context["wordCount"],
                            len(updated_context["keywordValidation"]),
                        )
                    except Exception as exc:
                        logger.warning("Python final output formatting failed (non-fatal): %s", exc)
                        try:
                            plain = re.sub(r"\s", "", re.sub(r"<[^>]*>", "", str(updated_context.get("content") or "")))
                            updated_context["wordCount"] = len(plain)
                        except Exception:
                            pass

                job_manager.complete_job(job_id, updated_context)
                logger.info("Job %s pipeline completed", job_id)

            return _json_response(
                {
                    "success": True,
                    "step": agent_name,
                    "stepIndex": step_index,
                    "duration": duration_ms,
                    "nextStep": next_step if next_step < total_steps else None,
                },
                200,
            )

        finally:
            if job_manager:
                job_manager.release_lock(job_id)

    except Exception as exc:
        import traceback

        logger.error("Step execution failed: %s", exc)
        traceback.print_exc()

        if job_id and job_manager:
            try:
                job_manager.fail_job(
                    job_id,
                    {
                        "step": step_info["name"] if step_info else "unknown",
                        "message": str(exc),
                        "stepIndex": data.get("stepIndex", 0) if isinstance(data, dict) else 0,
                    },
                )
            except Exception as fail_err:
                logger.error("Failed to mark job as failed: %s", fail_err)

        return _json_response({"error": str(exc), "code": "EXECUTION_ERROR"}, 500)
