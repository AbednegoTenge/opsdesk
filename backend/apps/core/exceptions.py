"""Uniform error envelope: {"error": {"code", "message", "details"}}."""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A required service is temporarily unavailable. Try again shortly."
    default_code = "service_unavailable"


def api_exception_handler(exc, context):
    # Mirror DRF's own conversion so the error code is right for Django exceptions.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Request validation failed."
        details = response.data
    else:
        detail = getattr(exc, "detail", None)
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        if isinstance(response.data, dict) and "detail" in response.data:
            message = str(response.data["detail"])
            details = {k: v for k, v in response.data.items() if k != "detail"} or None
        else:
            message = str(getattr(exc, "default_detail", "Error"))
            details = response.data

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
