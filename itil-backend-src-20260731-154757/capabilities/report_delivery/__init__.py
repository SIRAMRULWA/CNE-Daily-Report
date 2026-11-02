"""Daily Report subscription and delivery capability."""

from functools import lru_cache

from capabilities.report_delivery.repository import ReportDeliveryRepository
from capabilities.report_delivery.service import ReportDeliveryService


@lru_cache(maxsize=1)
def get_report_delivery_service() -> ReportDeliveryService:
    return ReportDeliveryService(ReportDeliveryRepository())


__all__ = [
    "ReportDeliveryRepository",
    "ReportDeliveryService",
    "get_report_delivery_service",
]

