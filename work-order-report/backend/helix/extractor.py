"""
helix/extractor.py
==================
BMC Helix REST API extractor.

Produces canonical ChangeRecord batches so API ingestion uses the same
transform and load path as Excel/CSV ingestion.
"""

import logging
import os
import time
from datetime import date, datetime
from typing import Generator, List, Optional

from config.mappings import OPEN_STATUSES
from helix.client import HelixClient
from helix.config import (
    BATCH_SIZE,
    CHANGE_FIELD_MAP,
    CHANGE_FORM,
    CHANGE_LOOKUP_BATCH_SIZE,
    DATE_FIELD,
    DEFAULT_STATUSES,
    ENRICH_CHANGE_SCHEDULES,
    HELIX_BASE_URL,
    HELIX_FIELD_MAP,
    HELIX_PASSWORD,
    HELIX_RAW_REPORT_DATE_FIELDS,
    HELIX_USERNAME,
    INCLUDE_YESTERDAY_SUCCESS_CLOSURES,
    MAX_RECORDS,
    PAGE_SIZE,
    PIPELINE_SCHEDULE_HOUR,
    REQUEST_SLEEP_SECONDS,
    USE_FIELD_SELECTION,
    VERIFY_SSL,
    WORKSPACE_TIMEZONE,
)
from helix.datetime_utils import (
    format_helix_timestamp,
    naive_workspace_datetime,
)
from helix.enrichment import ChangeScheduleEnricher
from helix.mapper import HelixTaskMapper
from helix.query import HelixQueryBuilder
from pipeline.division_groups import load_target_groups
from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)

def _naive_datetime(value: datetime) -> datetime:
    """Normalize Helix datetimes to workspace-local naive pipeline values."""
    return naive_workspace_datetime(value)


class HelixExtractor:
    """Extracts change tasks directly from the BMC Helix AR System REST API."""

    def __init__(self):
        self._client = HelixClient()
        self._query_builder = HelixQueryBuilder()
        self._mapper = HelixTaskMapper()
        self._schedule_enricher = ChangeScheduleEnricher(
            lambda request_ids: self._fetch_change_parents(request_ids),
            self._mapper,
        )

    def is_configured(self) -> bool:
        """Return True when the Helix URL and credentials are set."""
        return self._client.is_configured()

    def _proxies(self) -> Optional[dict[str, str]]:
        return self._client.proxies()

    def _target_groups(self) -> list[str]:
        configured = os.getenv("HELIX_GROUPS", "").strip()
        if configured:
            return [group.strip() for group in configured.split(",") if group.strip()]
        return load_target_groups()

    def _target_statuses(self) -> list[str]:
        configured = os.getenv("HELIX_STATUSES", DEFAULT_STATUSES).strip()
        if not configured:
            return []
        return [status.strip() for status in configured.split(",") if status.strip()]

    def _authenticate(self) -> str:
        """Obtain and cache an AR-JWT token from Helix."""
        return self._client.authenticate()

    def _format_helix_timestamp(self, value: datetime | date | str, end_of_day: bool = False) -> str:
        """
        Format Date/Time qualifications for AR System.

        TMS:Task date fields are queried as epoch seconds. Date-only end values
        are expanded to 23:59:59 so period filters include the whole day.
        """
        return format_helix_timestamp(value, end_of_day=end_of_day)

    def _escape_qualification_value(self, value: str) -> str:
        """Escape a string literal for an AR System qualification."""
        return self._query_builder.escape(value)

    def _equals_clause(self, field: str, value: str) -> str:
        return self._query_builder.equals(field, value)

    def _build_query(
        self,
        since: Optional[datetime] = None,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        assignee_groups: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
    ) -> str:
        groups = self._target_groups() if assignee_groups is None else assignee_groups
        selected_statuses = self._target_statuses() if statuses is None else statuses
        return self._query_builder.task_query(
            groups=groups,
            statuses=selected_statuses,
            since=since,
            start_date=start_date,
            end_date=end_date,
        )

    def _build_yesterday_closure_query(self) -> tuple[str, datetime, datetime]:
        """Build the prior scheduled 24-hour window for closures of every outcome."""
        return self._query_builder.closures(self._target_groups())

    def _build_raw_report_query(
        self,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        date_field: str = "Create Date",
        assignee_groups: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        request_ids: Optional[list[str]] = None,
        task_ids: Optional[list[str]] = None,
    ) -> str:
        """Build an unscoped time-range query for the standalone raw reporter."""
        return self._query_builder.raw_report(
            start_date=start_date,
            end_date=end_date,
            date_field=date_field,
            groups=assignee_groups,
            assignees=assignees,
            statuses=statuses,
            request_ids=request_ids,
            task_ids=task_ids,
        )

    def _fetch_page(self, offset: int, query: str) -> list:
        """Fetch one page of AR System entries."""
        return self._client.fetch_task_page(offset, query)

    def _fetch_change_parents(self, request_ids: list[str]) -> dict[str, dict]:
        """Fetch authoritative schedule dates for CRQs from the parent CHG form."""
        return self._client.fetch_change_parents(request_ids)

    def _enrich_change_schedules(self, records: list[ChangeRecord]) -> None:
        """Override CRQ task schedules with authoritative parent change dates."""
        self._schedule_enricher.enrich(records)

    def _entry_to_change_schedule(self, values: dict) -> tuple[Optional[datetime], Optional[datetime]]:
        """Parse the two authoritative schedule values returned by the CHG form."""
        return self._mapper.change_schedule(values)

    def _entry_to_record(self, entry: dict) -> Optional[ChangeRecord]:
        """Convert a Helix API entry to a ChangeRecord."""
        return self._mapper.record(entry)

    def extract_raw_report(
        self,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        date_field: str = "Create Date",
        fields: Optional[list[str]] = None,
        assignee_groups: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        categories: Optional[list[str]] = None,
        request_ids: Optional[list[str]] = None,
        task_ids: Optional[list[str]] = None,
        calculate_sla: bool = False,
        max_records: int = 5000,
    ) -> list[dict]:
        """
        Return raw mapped TMS:Task values for an explicit time range.

        This intentionally bypasses daily-report group/status qualifications,
        exclusions, database loading, and dbt models. When requested, only the
        shared in-memory SLA derivation is applied; no records are persisted.
        """
        selected = fields or list(HELIX_FIELD_MAP.values())
        unknown = sorted(set(selected) - set(HELIX_FIELD_MAP.values()))
        if unknown:
            raise ValueError(f"Unsupported raw report fields: {', '.join(unknown)}")
        if max_records < 1:
            raise ValueError("max_records must be at least 1")

        groups = list(dict.fromkeys(
            group.strip() for group in (assignee_groups or []) if group and group.strip()
        ))
        status_filters = list(dict.fromkeys(
            status.strip() for status in (statuses or []) if status and status.strip()
        ))
        assignee_filters = list(dict.fromkeys(
            assignee.strip() for assignee in (assignees or []) if assignee and assignee.strip()
        ))
        request_filters = list(dict.fromkeys(
            value.strip() for value in (request_ids or []) if value and value.strip()
        ))
        task_filters = list(dict.fromkeys(
            value.strip() for value in (task_ids or []) if value and value.strip()
        ))
        category_filters = {
            value.strip().upper() for value in (categories or []) if value and value.strip()
        }
        query = self._build_raw_report_query(
            start_date,
            end_date,
            date_field,
            assignee_groups=groups,
            assignees=assignee_filters,
            statuses=status_filters,
            request_ids=request_filters,
            task_ids=task_filters,
        )
        source_by_canonical = {canonical: source for source, canonical in HELIX_FIELD_MAP.items()}
        operational_category_labels = {
            "FAULTS": "Faults",
            "SECURITY": "Security",
            "ALARM": "Alarm",
            "CHANGE": "Change",
            "WORK ORDER": "Work Order",
            "PBI": "PBI",
        }
        rows: list[dict] = []
        row_records: list[ChangeRecord] = []
        sla_calculated_at = datetime.now() if calculate_sla else None
        offset = 0

        while len(rows) < max_records:
            entries = self._fetch_page(offset, query)
            if not entries:
                break

            for entry in entries:
                values = entry.get("values", {})
                record = None
                if category_filters or "op_cat_tier1" in selected or calculate_sla:
                    record = self._entry_to_record(entry)
                if category_filters:
                    from pipeline.transform import derive_operational_category

                    if not record or derive_operational_category(record).upper() not in category_filters:
                        continue
                row = {name: values.get(source_by_canonical[name]) for name in selected}
                if "op_cat_tier1" in selected and not str(row.get("op_cat_tier1") or "").strip():
                    # Import here to keep the normal extractor path lightweight and
                    # reuse the exact category fallback used by Daily Reports.
                    from pipeline.transform import derive_operational_category

                    if record:
                        inferred = derive_operational_category(record)
                        row["op_cat_tier1"] = operational_category_labels.get(inferred, inferred)
                rows.append(row)
                if calculate_sla:
                    # A missing RootRequestID cannot be mapped to the canonical
                    # record needed by the shared SLA engine.
                    if record is None:
                        row.update({
                            "report_category": None,
                            "sla_status": "OUT_OF_SCOPE",
                            "hours_open": None,
                            "sla_calculated_at": sla_calculated_at.isoformat(),
                        })
                    else:
                        row_records.append(record)
                        row["_sla_record_index"] = len(row_records) - 1
                if len(rows) >= max_records:
                    break

            if len(entries) < PAGE_SIZE:
                break
            offset += len(entries)
            if REQUEST_SLEEP_SECONDS > 0:
                time.sleep(REQUEST_SLEEP_SECONDS)

        if calculate_sla and row_records:
            from pipeline.transform import transform_records

            self._enrich_change_schedules(row_records)
            transform_records(row_records, as_of=sla_calculated_at)
            for row in rows:
                record_index = row.pop("_sla_record_index", None)
                if record_index is None:
                    continue
                record = row_records[record_index]
                row.update({
                    "report_category": record.report_category,
                    "sla_status": record.sla_status,
                    "hours_open": (
                        round(record.hours_open, 2)
                        if record.hours_open is not None else None
                    ),
                    "sla_calculated_at": sla_calculated_at.isoformat(),
                })

        logger.info(
            "Helix raw report complete | date_field=%s start=%s end=%s groups=%d assignees=%d statuses=%d categories=%d sla=%s rows=%d",
            date_field,
            start_date,
            end_date,
            len(groups),
            len(assignee_filters),
            len(status_filters),
            len(category_filters),
            calculate_sla,
            len(rows),
        )
        return rows

    def extract_changes(
        self,
        since: Optional[datetime] = None,
        start_date: Optional[datetime | date | str] = None,
        end_date: Optional[datetime | date | str] = None,
        *,
        assignee_groups: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        max_records: Optional[int] = None,
        include_successful_closures: Optional[bool] = None,
    ) -> Generator[List[ChangeRecord], None, None]:
        """Yield canonical, schedule-enriched ChangeRecord batches from Helix.

        Daily Report ingestion uses the environment-backed defaults. Read-only
        consumers such as task reminders may provide an explicit scope and
        disable successful-closure retrieval without changing pipeline state.
        """
        if not self.is_configured():
            logger.warning("Helix extractor not configured - skipping")
            return

        record_limit = MAX_RECORDS if max_records is None else max_records
        if record_limit < 1:
            raise ValueError("max_records must be at least 1")
        include_closures = (
            INCLUDE_YESTERDAY_SUCCESS_CLOSURES
            if include_successful_closures is None
            else include_successful_closures
        )
        query = self._build_query(
            since=since,
            start_date=start_date,
            end_date=end_date,
            assignee_groups=assignee_groups,
            statuses=statuses,
        )
        logger.info("Helix query: %s", query or "<none>")

        offset = 0
        total = 0
        batch: List[ChangeRecord] = []
        seen_keys: set[tuple[str, str]] = set()

        while total < record_limit:
            try:
                entries = self._fetch_page(offset, query)
            except Exception as exc:
                logger.error("Helix API page fetch failed (offset=%d): %s", offset, exc)
                raise

            if not entries:
                break

            for entry in entries:
                if total >= record_limit:
                    break
                record = self._entry_to_record(entry)
                if record:
                    batch.append(record)
                    seen_keys.add((record.request_id, record.task_id))
                    total += 1

                if len(batch) >= BATCH_SIZE:
                    self._enrich_change_schedules(batch)
                    yield batch
                    batch = []

            if len(entries) < PAGE_SIZE:
                break

            offset += len(entries)
            if REQUEST_SLEEP_SECONDS > 0:
                time.sleep(REQUEST_SLEEP_SECONDS)

        if batch:
            self._enrich_change_schedules(batch)
            yield batch

        closure_total = 0
        if include_closures and total < record_limit:
            closure_query, closure_window_start, closure_window_end = (
                self._build_yesterday_closure_query()
            )
            logger.info(
                "Helix closure window: %s <= Actual End Date < %s",
                closure_window_start,
                closure_window_end,
            )
            offset = 0
            closure_batch: List[ChangeRecord] = []
            while total < record_limit:
                entries = self._fetch_page(offset, closure_query)
                if not entries:
                    break
                for entry in entries:
                    if total >= record_limit:
                        break
                    record = self._entry_to_record(entry)
                    if not record:
                        continue
                    key = (record.request_id, record.task_id)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    closure_batch.append(record)
                    closure_total += 1
                    total += 1
                    if len(closure_batch) >= BATCH_SIZE:
                        self._enrich_change_schedules(closure_batch)
                        yield closure_batch
                        closure_batch = []
                if len(entries) < PAGE_SIZE:
                    break
                offset += len(entries)
                if REQUEST_SLEEP_SECONDS > 0:
                    time.sleep(REQUEST_SLEEP_SECONDS)
            if closure_batch:
                self._enrich_change_schedules(closure_batch)
                yield closure_batch

        logger.info(
            "Helix extraction complete - %d records (%d closures from yesterday)",
            total,
            closure_total,
        )
