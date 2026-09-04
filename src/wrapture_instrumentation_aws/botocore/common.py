"""The capture policy and the outcome helpers shared by the seam.

api_params never records wholesale: it carries payloads, items,
message bodies and sometimes credentials, so the capture policy
reduces it to a value count and everything else to its type, the
identifiers services.py names being the only values lifted out, by
known parameter name. The outcome helpers read what ResponseMetadata
carries, off a successful response or off the response a ClientError
hands back.
"""

from __future__ import annotations

from typing import Any


def captured_argument(name: str | None, value: Any) -> Any:
    """The capture policy for the call's arguments: the operation name
    passes as the scalar it is, api_params reduces to how many
    parameters it held, and anything else reduces to its type."""

    if name == "api_params" and isinstance(value, dict):
        return len(value)

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    return f"<{type(value).__name__}>"


def outcome(response: Any) -> dict[str, Any]:
    """The keys ResponseMetadata carries: the HTTP status, the request
    id AWS support correlates by, and the retry count when the call
    retried, folding the retries into the one event."""

    metadata = response.get("ResponseMetadata") if isinstance(response, dict) else None
    if not isinstance(metadata, dict):
        return {}

    data: dict[str, Any] = {}

    status = metadata.get("HTTPStatusCode")
    if status is not None:
        data["status"] = status

    request_id = metadata.get("RequestId")
    if request_id:
        data["request_id"] = request_id

    retries = metadata.get("RetryAttempts")
    if retries:
        data["retries"] = retries

    return data


def error_code(error: Any) -> str | None:
    """The AWS error code a ClientError carries (NoSuchKey,
    ResourceNotFoundException), from the response it holds."""

    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None

    info = response.get("Error")
    if not isinstance(info, dict):
        return None

    return info.get("Code")
