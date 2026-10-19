import logging
import re

import structlog

# Third-party APIs take keys in query strings (apiKey=..., key=...); exception
# text and URLs can carry them into logs. Mask before rendering.
_SECRET_QS = re.compile(r'((?:api_?key|apikey|key|token|access_token|client_secret|password)=)[^&\s"\']+', re.IGNORECASE)
_BEARER = re.compile(r'(Bearer\s+)[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE)


def _mask(value):
    if isinstance(value, str) and ("=" in value or "Bearer" in value or "bearer" in value):
        return _BEARER.sub(r"\1***", _SECRET_QS.sub(r"\1***", value))
    return value


def _mask_secrets(_, __, event_dict):
    return {k: _mask(v) for k, v in event_dict.items()}

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _mask_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )

def get_logger(name: str):
    return structlog.get_logger(name)
