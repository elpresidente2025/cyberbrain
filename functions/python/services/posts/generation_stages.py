"""원고 생성 진행 단계 정의.

Node.js `functions/services/posts/generation-stages.js` 포팅.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class Stage:
    step: int
    id: str
    message: str
    detail: str
    icon: str
    estimated_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "id": self.id,
            "message": self.message,
            "detail": self.detail,
            "icon": self.icon,
            "estimatedSeconds": self.estimated_seconds,
        }


GENERATION_STAGES: Dict[str, Dict[str, Any]] = {
    "DRAFTING": Stage(
        step=1,
        id="DRAFTING",
        message="초안을 작성하고 있습니다...",
        detail="전뇌비서관이 주제에 맞는 원고를 구상 중입니다",
        icon="✍️",
        estimated_seconds=10,
    ).to_dict(),
    "BASIC_CHECK": Stage(
        step=2,
        id="BASIC_CHECK",
        message="기본 검수를 진행 중입니다...",
        detail="선거법 준수 여부와 문장 반복을 확인합니다",
        icon="🔍",
        estimated_seconds=2,
    ).to_dict(),
    "EDITOR_REVIEW": Stage(
        step=3,
        id="EDITOR_REVIEW",
        message="전뇌 편집장이 원고를 정밀 검토 중입니다...",
        detail="팩트 확인, 정무적 적합성, 유권자 관점을 종합 검토합니다",
        icon="👔",
        estimated_seconds=8,
    ).to_dict(),
    "CORRECTING": Stage(
        step=4,
        id="CORRECTING",
        message="피드백을 반영하여 원고를 다듬고 있습니다...",
        detail="지적된 사항을 수정하여 품질을 높입니다",
        icon="✨",
        estimated_seconds=8,
    ).to_dict(),
    "FINALIZING": Stage(
        step=5,
        id="FINALIZING",
        message="최종 검수 후 완성합니다...",
        detail="마지막 품질 확인을 진행합니다",
        icon="✅",
        estimated_seconds=2,
    ).to_dict(),
    "COMPLETED": Stage(
        step=6,
        id="COMPLETED",
        message="원고가 완성되었습니다!",
        detail="",
        icon="🎉",
        estimated_seconds=0,
    ).to_dict(),
    "ERROR": Stage(
        step=-1,
        id="ERROR",
        message="원고 생성 중 문제가 발생했습니다",
        detail="다시 시도해 주세요",
        icon="❌",
        estimated_seconds=0,
    ).to_dict(),
}


TOTAL_ESTIMATED_SECONDS = sum(
    stage["estimatedSeconds"]
    for stage in GENERATION_STAGES.values()
    if stage["step"] > 0
)


def get_stage_by_id(stage_id: str) -> Dict[str, Any]:
    return GENERATION_STAGES.get(stage_id, GENERATION_STAGES["ERROR"])


def get_stage_by_step(step: int) -> Dict[str, Any]:
    for stage in GENERATION_STAGES.values():
        if stage["step"] == step:
            return stage
    return GENERATION_STAGES["ERROR"]


def calculate_progress(current_stage_id: str) -> int:
    stage = GENERATION_STAGES.get(current_stage_id)
    if not stage or stage["step"] <= 0:
        return 0
    if stage["id"] == "COMPLETED":
        return 100
    total_steps = 5  # COMPLETED 제외
    return round((stage["step"] / total_steps) * 100)


def calculate_remaining_time(current_stage_id: str) -> int:
    stage = GENERATION_STAGES.get(current_stage_id)
    if not stage or stage["step"] <= 0:
        return 0
    return sum(
        s["estimatedSeconds"]
        for s in GENERATION_STAGES.values()
        if s["step"] >= stage["step"] and s["step"] > 0
    )


def create_progress_state(stage_id: str, additional_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stage = get_stage_by_id(stage_id)
    payload = {
        "stage": stage["id"],
        "step": stage["step"],
        "message": stage["message"],
        "detail": stage["detail"],
        "icon": stage["icon"],
        "progress": calculate_progress(stage_id),
        "estimatedSecondsRemaining": calculate_remaining_time(stage_id),
    }
    if additional_info:
        payload.update(additional_info)
    return payload


def create_retry_message(attempt: int, max_attempts: int, score: int) -> Dict[str, str]:
    if attempt == 1:
        return {
            "message": "전뇌 편집장이 원고를 정밀 검토 중입니다...",
            "detail": "팩트 확인, 정무적 적합성, 유권자 관점을 종합 검토합니다",
        }
    return {
        "message": f"원고 품질 개선 중입니다... ({attempt}/{max_attempts})",
        "detail": f"현재 품질 점수: {score}점 - 더 좋은 결과를 위해 다듬고 있습니다",
    }


# JS 호환 별칭
getStageById = get_stage_by_id
getStageByStep = get_stage_by_step
calculateProgress = calculate_progress
createProgressState = create_progress_state
calculateRemainingTime = calculate_remaining_time
createRetryMessage = create_retry_message


__all__ = [
    "GENERATION_STAGES",
    "TOTAL_ESTIMATED_SECONDS",
    "get_stage_by_id",
    "get_stage_by_step",
    "calculate_progress",
    "create_progress_state",
    "calculate_remaining_time",
    "create_retry_message",
    "getStageById",
    "getStageByStep",
    "calculateProgress",
    "createProgressState",
    "calculateRemainingTime",
    "createRetryMessage",
]

