"""Web research through the official Exa SDK.

The sales analyst only knows what the till recorded. Some questions — a supplier's
recall notice, a competitor's pricing, a licensing change — need the open web, so
those are answered with sources rather than guesswork. Every result keeps Exa's
highlight sentences so a report can cite the page the claim came from.
"""

from exa_py import Exa
from exa_py.errors import ExaTimeoutError
from fastapi import HTTPException

from .config import EXA_API_KEY, EXA_NUM_RESULTS, EXA_TIMEOUT_SECONDS


def web_search_configuration() -> dict:
    return {
        "configured": bool(EXA_API_KEY),
        "provider": "exa",
        "default_results": EXA_NUM_RESULTS,
    }


def _client() -> Exa:
    if not EXA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Web search is not configured on the server. Add EXA_API_KEY to the "
                "API environment, then restart it."
            ),
        )
    return Exa(api_key=EXA_API_KEY, timeout=EXA_TIMEOUT_SECONDS)


def search_web(query: str, num_results: int | None = None) -> dict:
    """Return the top Exa results for ``query`` with relevance highlights."""
    limit = num_results or EXA_NUM_RESULTS

    try:
        response = _client().search(
            query.strip(),
            type="auto",
            num_results=limit,
            contents={"highlights": True},
        )
    except ExaTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The web search timed out. Try a shorter query or try again.",
        )
    except ValueError as error:
        # The SDK raises ValueError for any non-2xx Exa response, including a bad key.
        raise HTTPException(
            status_code=502,
            detail=f"The web search service returned an error ({error}).",
        )

    results = [
        {
            "title": result.title,
            "url": result.url,
            "published_date": result.published_date,
            "author": result.author,
            "highlights": result.highlights or [],
        }
        for result in response.results
    ]
    return {
        "query": query.strip(),
        "results": results,
        "count": len(results),
        "search_type": response.resolved_search_type,
    }
