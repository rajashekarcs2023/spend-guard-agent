"""Deterministic risk detector.

This runs on the RAW, UNTRUSTED request body — never on LLM output. That is the
whole point: prompt injection cannot disable the detector, because the detector
does not ask an LLM anything. It pattern-matches the original text.

The flags it emits correspond to `blocked_risk_flags` in policy.json:
    prompt_injection
    secret_exfiltration_request
    credential_forwarding_request
    external_attacker_destination
    print_env_request
"""

from __future__ import annotations

import re

from .models import RiskFlag

# Each rule: (flag, human reason, list of regex patterns). Case-insensitive.
_RULES: list[tuple[str, str, list[str]]] = [
    (
        "prompt_injection",
        "prompt injection detected",
        [
            r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
            r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
            r"forget\s+(all\s+)?(previous|prior)\s+instructions",
            r"you\s+are\s+now\s+",
            r"new\s+instructions\s*:",
            r"system\s+prompt",
        ],
    ),
    (
        "secret_exfiltration_request",
        "secret exfiltration request detected",
        [
            r"print\s+(your\s+|the\s+)?\w*secret",
            r"print\s+(your\s+|the\s+)?\w*key",
            r"reveal\s+(your\s+|the\s+)?\w*(secret|key|credential|token)",
            r"show\s+(me\s+)?(your\s+|the\s+)?\w*(secret|key|credential|token)",
            r"output\s+(your\s+|the\s+)?\w*(secret|key|credential|token)",
            r"what\s+is\s+(your\s+|the\s+)?(secret|api[\s_-]?key|stripe[\s_-]?\w*key)",
            r"stripe[\s_-]?secret[\s_-]?key",
            r"send\s+(me\s+)?(your\s+|the\s+)?\w*(secret|api[\s_-]?key)",
        ],
    ),
    (
        "credential_forwarding_request",
        "credential forwarding request detected",
        [
            r"forward\s+(all\s+)?[\w\s]{0,40}?credentials?",
            r"forward\s+(all\s+)?[\w\s]{0,40}?(secret|key|token)s?",
            r"send\s+(all\s+)?[\w\s]{0,40}?credentials?\s+to",
            r"email\s+(all\s+)?[\w\s]{0,40}?(credential|secret|key)s?",
            r"copy\s+[\w\s]{0,40}?(credential|secret|key)s?\s+to",
        ],
    ),
    (
        "external_attacker_destination",
        "credential/payment directed to an external destination",
        [
            r"attacker@",
            r"forward.*@(?!snackhub|eventsuppliesco|goodbites)\w+",
            r"send\s+(all\s+)?(payment\s+)?credentials?\s+to\s+\S+@",
            r"\bevil\w*\b",
            r"send\s+\$?\d+.*\bto\b.*\b(llc|inc|ltd|corp)\b",
        ],
    ),
    (
        "print_env_request",
        "environment / secret dump request detected",
        [
            r"print\s*env",
            r"printenv",
            r"\benv\s*\|",
            r"dump\s+(the\s+)?env",
            r"echo\s+\$\{?\w*(secret|key|token)",
            r"os\.environ",
            r"cat\s+\.env",
        ],
    ),
]


def detect_risks(text: str) -> list[RiskFlag]:
    """Return the list of risk flags found in the untrusted text."""
    flags: list[RiskFlag] = []
    seen: set[str] = set()
    for flag, reason, patterns in _RULES:
        if flag in seen:
            continue
        for pat in patterns:
            match = re.search(pat, text, flags=re.IGNORECASE)
            if match:
                flags.append(
                    RiskFlag(
                        flag=flag,
                        reason=reason,
                        evidence=_snippet(text, match),
                    )
                )
                seen.add(flag)
                break
    return flags


def _snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 10)
    end = min(len(text), match.end() + 10)
    frag = text[start:end].strip().replace("\n", " ")
    return f"...{frag}..." if frag else ""
