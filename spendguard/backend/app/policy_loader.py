"""Load the policy and seeded demo requests from disk."""

from __future__ import annotations

import json
from functools import lru_cache

from .config import get_settings
from .models import Policy, SeedRequest


@lru_cache
def load_policy() -> Policy:
    settings = get_settings()
    with open(settings.policy_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Policy(**data)


@lru_cache
def load_seed_requests() -> tuple[SeedRequest, ...]:
    settings = get_settings()
    with open(settings.seed_requests_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return tuple(SeedRequest(**item) for item in data)


def get_seed_request(request_id: str) -> SeedRequest | None:
    for req in load_seed_requests():
        if req.id == request_id:
            return req
    return None
