import time
from typing import Dict, Any
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

class TelemetryTracker:
    def __init__(self):
        self.active_streams = 0
        self.total_requests = 0

    def start_stream(self) -> float:
        self.active_streams += 1
        self.total_requests += 1
        return time.time()

    def end_stream(self, start_time: float, status: str = "success"):
        self.active_streams -= 1
        duration = time.time() - start_time
        logger.info(f"Stream ended", duration=duration, status=status, active_streams=self.active_streams)

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "active_streams": self.active_streams,
            "total_requests": self.total_requests
        }

telemetry = TelemetryTracker()
