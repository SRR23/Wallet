"""
Consistent API error response shape.

{
  "error": "<short code or message>",
  "detail": <string or field errors>
}
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    error = "request_failed"

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        error = "validation_error"
    elif response.status_code == status.HTTP_401_UNAUTHORIZED:
        error = "authentication_failed"
    elif response.status_code == status.HTTP_403_FORBIDDEN:
        error = "permission_denied"
    elif response.status_code == status.HTTP_404_NOT_FOUND:
        error = "not_found"

    # DRF often wraps the message as {"detail": "..."}.
    if isinstance(detail, dict) and set(detail.keys()) == {"detail"}:
        detail = detail["detail"]

    response.data = {
        "error": error,
        "detail": detail,
    }
    return response
