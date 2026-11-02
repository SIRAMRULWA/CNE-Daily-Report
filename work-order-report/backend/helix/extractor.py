"""
helix/extractor.py
==================
BMC Helix REST API extractor for WOI:WorkOrder.

Produces canonical WorkOrderRecord batches so API ingestion uses the same
transform and load path as Excel/CSV ingestion.
"""

import logging
import os
import time
from datetime import date, datetime
from typing import Callable, Generator, List, Optional

from helix.client import HelixClient
from helix.config import (
    BATCH_SIZE,
    DATE_FIELD,
    DEFAULT_STATUSES,
    HELIX_FIELD_MAP,
    INCLUDE_YESTERDAY_COMPLETIONS,
    MAX_RECORDS,
    PAGE_SIZE,
    REQUEST_SLEEP_SECONDS,
)
from helix.mapper import HelixWorkOrderMapper, requester_name
from helix.query import HelixQueryBuilder
from pipeline.division_groups import load_target_groups
from pipeline.models import WorkOrderRecord

logger = logging.getLogger(__name__)

# Canonical names a custom report may return (requester is derived).
RAW_REPORT_FIELDS = [
    name for name in HELIX_FIELD_MAP.values()
    if name not in ("requester_first_name", "requester_last_name")
] + ["requester"]


def _clean_list(values: Optional[list[str]]) -> list[str]:
    return list(dict.fromkeys(
        value.strip() for value in (values or []) if value and value.strip()
    ))


class HelixExtractor:
    """Extracts Work Orders directly from the BMC Helix AR System REST API."""

    def __init__(self):
        self._client = HelixClient()
        self._query_builder = HelixQueryBuilder()
        self._mapper = HelixWorkOrderMapper()

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def _target_groups(self) -> list[str]:
        configured = os.getenv("HELIX_GROUPS", "").strip()
        if configured:
            return [group.strip() for group in configured.split(",") if group.strip()]
        return load_target_groups()

    def _target_statuses(self) -> list[str]:
        configured = os.getenv("HELIX_STATUSES", DEFAULT_STATUSES).strip()
        return [status.strip() for status in configured.split(",") if status.strip()]

    def _fetch_page(self, offset: int, query: str) -> list:
        return self._client.fetch_page(offset, query)

    def _pages(self, query: str, limit: int) -> Generator[dict, None, None]:
        """Yield raw entries page by page, up to ``limit`` entries."""
        offset = 0
        yielded = 0
        while yielded < limit:
            entries = self._fetch_page(offset, query)
            if not entries:
                return
            for entry in entries:
                if yielded >= limit:
                    return
                yielded += 1
                yield entry
            if len(entries) < PAGE_SIZE:
                return
            offset += len(entries)
            if REQUEST_SLEEP_SECONDS > 0:
                time.sleep(REQUEST_SLEEP_SECONDS)

    def extract_work_orders(
        self,
        since: Optional[datetime] = None,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        *,
        support_groups: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        max_records: Optional[int] = None,
        include_completions: Optional[bool] = None,
    ) -> Generator[List[WorkOrderRecord], None, None]:
        """Yield WorkOrderRecord batches: open Work Orders, then yesterday's completions."""
        if not self.is_configured():
            logger.warning("Helix extractor not configured - skipping")
            return

        limit = MAX_RECORDS if max_records is None else max_records
        if limit < 1:
            raise ValueError("max_records must be at least 1")
        groups = self._target_groups() if support_groups is None else support_groups
        include = INCLUDE_YESTERDAY_COMPLETIONS if include_completions is None else include_completions

        open_query = self._query_builder.work_order_query(
            groups=groups,
            statuses=self._target_statuses() if statuses is None else statuses,
            since=since,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("Helix open Work Order query: %s", open_query or "<none>")

        seen: set[str] = set()
        total = 0
        completed_total = 0

        def batches(query: str, on_record: Callable[[], None]):
            nonlocal total
            batch: List[WorkOrderRecord] = []
            for entry in self._pages(query, limit - total):
                record = self._mapper.record(entry)
                if record is None or record.work_order_id in seen:
                    continue
                seen.add(record.work_order_id)
                batch.append(record)
                total += 1
                on_record()
                if len(batch) >= BATCH_SIZE:
                    yield batch
                    batch = []
            if batch:
                yield batch

        yield from batches(open_query, lambda: None)

        if include and total < limit:
            query, window_start, window_end = self._query_builder.completions(groups)
            logger.info(
                "Helix completion window: %s <= Completed Date < %s",
                window_start, window_end,
            )

            def count_completed():
                nonlocal completed_total
                completed_total += 1

            yield from batches(query, count_completed)

        logger.info(
            "Helix extraction complete - %d Work Orders (%d completed yesterday)",
            total, completed_total,
        )

    def extract_raw_report(
        self,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        date_field: Optional[str] = None,
        fields: Optional[list[str]] = None,
        support_groups: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        categories: Optional[list[str]] = None,
        work_order_ids: Optional[list[str]] = None,
        calculate_sla: bool = False,
        max_records: int = 5000,
    ) -> list[dict]:
        """Return mapped WOI:WorkOrder rows for an explicit range; nothing is stored.

        Bypasses the report's group/status scope and database. When requested,
        the shared in-memory SLA rules are applied to each row.
        """
        selected = fields or RAW_REPORT_FIELDS
        unknown = sorted(set(selected) - set(RAW_REPORT_FIELDS))
        if unknown:
            raise ValueError(f"Unsupported raw report fields: {', '.join(unknown)}")
        if max_records < 1:
            raise ValueError("max_records must be at least 1")

        category_filters = {value.upper() for value in _clean_list(categories)}
        query = self._query_builder.raw_report(
            start_date=start_date,
            end_date=end_date,
            date_field=date_field or DATE_FIELD,
            groups=_clean_list(support_groups),
            assignees=_clean_list(assignees),
            statuses=_clean_list(statuses),
            work_order_ids=_clean_list(work_order_ids),
        )
        source_by_canonical = {canonical: source for source, canonical in HELIX_FIELD_MAP.items()}

        from pipeline.transform import classify_category, transform_records

        rows: list[dict] = []
        records: list[WorkOrderRecord | None] = []
        calculated_at = datetime.now()

        offset = 0
        while len(rows) < max_records:
            entries = self._fetch_page(offset, query)
            if not entries:
                break
            for entry in entries:
                values = entry.get("values", {})
                record = self._mapper.record(entry)
                if category_filters and (
                    record is None or classify_category(record).upper() not in category_filters
                ):
                    continue
                row = {}
                for name in selected:
                    if name == "requester":
                        row[name] = requester_name(
                            values.get(source_by_canonical["requester_first_name"]),
                            values.get(source_by_canonical["requester_last_name"]),
                        )
                    else:
                        row[name] = values.get(source_by_canonical[name])
                rows.append(row)
                records.append(record)
                if len(rows) >= max_records:
                    break
            if len(entries) < PAGE_SIZE:
                break
            offset += len(entries)
            if REQUEST_SLEEP_SECONDS > 0:
                time.sleep(REQUEST_SLEEP_SECONDS)

        if calculate_sla:
            mapped = [record for record in records if record is not None]
            transform_records(mapped, as_of=calculated_at)
            for row, record in zip(rows, records):
                row.update({
                    "report_category": record.report_category if record else None,
                    "sla_status": record.sla_status if record else "OUT_OF_SCOPE",
                    "hours_open": (
                        round(record.hours_open, 2)
                        if record and record.hours_open is not None else None
                    ),
                    "days_to_target": record.days_to_target if record else None,
                    "sla_calculated_at": calculated_at.isoformat(),
                })

        logger.info(
            "Helix raw report complete | date_field=%s start=%s end=%s sla=%s rows=%d",
            date_field or DATE_FIELD, start_date, end_date, calculate_sla, len(rows),
        )
        return rows
