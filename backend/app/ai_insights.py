"""AI sales analyst.

The model never sees the database and never invents figures: it receives a compact
snapshot of already-computed report facts and is asked to explain them. Every response
returns those same facts so the UI can show the numbers behind the prose.
"""

import json
from datetime import date

import requests
from fastapi import HTTPException

from .config import (
    AI_API_KEY,
    AI_BASE_URL,
    AI_DAILY_LIMIT,
    AI_TIMEOUT_SECONDS,
    STORE_CURRENCY,
    STORE_NAME,
    resolved_ai_model,
)
from .reports import build_briefing, report_facts

_usage: dict[str, int] = {}

SYSTEM_PROMPT = (
    f"You are the sales analyst for {STORE_NAME}, a retail liquor store. "
    "You receive a JSON snapshot of point-of-sale metrics for one period. "
    "Rules: use only the numbers in the snapshot, never invent or extrapolate figures; "
    f"quote money in {STORE_CURRENCY}; be concise and practical; prioritise restocking, "
    "margin, staffing and basket-size actions; if the data is insufficient for a question, "
    "say so plainly. Answer in at most 150 words, using short paragraphs or dashes."
)


def ai_configuration() -> dict:
    provider = "z.ai" if "z.ai" in AI_BASE_URL else "openai-compatible"
    return {
        "configured": bool(AI_API_KEY),
        "model": resolved_ai_model(),
        "provider": provider,
        "daily_limit": AI_DAILY_LIMIT,
        "base_url": AI_BASE_URL,
    }


def _usage_key(username: str) -> str:
    return f"{username}:{date.today().isoformat()}"


def remaining_questions(username: str) -> int:
    return max(AI_DAILY_LIMIT - _usage.get(_usage_key(username), 0), 0)


def ask_insight(report: dict, question: str, username: str) -> dict:
    if not AI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI insights are not configured on the server. Add ZAI_API_KEY and "
                "ZAI_API_BASE to the API environment, then restart it. The rules-based "
                "briefing works without a key."
            ),
        )

    key = _usage_key(username)
    if _usage.get(key, 0) >= AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI limit reached ({AI_DAILY_LIMIT} questions per account).",
        )

    facts = report_facts(report)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "POS metrics snapshot:\n"
                f"{json.dumps(facts, ensure_ascii=False)}\n\n"
                f"Question: {question.strip()}"
            ),
        },
    ]

    try:
        response = requests.post(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": resolved_ai_model(),
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=AI_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail="The AI service could not be reached. Check the API server's network and key.",
        )

    if response.status_code == 401 or response.status_code == 403:
        raise HTTPException(
            status_code=502,
            detail="The AI service rejected the API key. Update ZAI_API_KEY on the server.",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"The AI service returned an error ({response.status_code}).",
        )

    try:
        payload = response.json()
        answer = payload["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, AttributeError):
        raise HTTPException(
            status_code=502,
            detail="The AI service returned an unexpected response.",
        )

    _usage[key] = _usage.get(key, 0) + 1
    return {
        "answer": answer,
        "model": resolved_ai_model(),
        "facts": facts,
        "remaining": max(AI_DAILY_LIMIT - _usage[key], 0),
        "briefing": build_briefing(report),
        "generated_at": report["end"],
    }
