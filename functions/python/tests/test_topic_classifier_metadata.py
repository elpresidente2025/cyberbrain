from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handlers.generate_posts_pkg import pipeline as generate_pipeline


def test_resolve_request_intent_with_meta_includes_sampling_fields() -> None:
    topic, category, sub_category, meta = generate_pipeline._resolve_request_intent_with_meta(
        {
            "topic": "부산 교통 민원 해결 방안",
            "instructions": [
                "주민들이 체감하는 교통 불편과 주차 문제를 해결하겠습니다.",
                "이후 참고자료는 분류와 무관한 보충 설명입니다.",
            ],
        }
    )

    assert topic == "부산 교통 민원 해결 방안"
    assert category == "local-issues"
    assert sub_category == ""
    assert meta["requestedCategory"] == "auto"
    assert meta["resolvedCategory"] == "local-issues"
    assert meta["hasStanceSignal"] is True
