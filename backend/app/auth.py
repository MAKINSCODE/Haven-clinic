import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def require_api_key(
    supplied_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="API key is not configured")

    # Compare in constant time so key validation does not reveal matching prefixes.
    if supplied_key is None or not hmac.compare_digest(
        supplied_key.encode("utf-8"), expected_key.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="missing or invalid API key")
