"""Authoritative parent-change schedule enrichment."""

import logging
from collections.abc import Callable

from helix.config import ENRICH_CHANGE_SCHEDULES
from helix.mapper import HelixTaskMapper
from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)


class ChangeScheduleEnricher:
    def __init__(
        self,
        fetch_parents: Callable[[list[str]], dict[str, dict]],
        mapper: HelixTaskMapper,
    ):
        self.fetch_parents = fetch_parents
        self.mapper = mapper

    def enrich(self, records: list[ChangeRecord]) -> None:
        if not ENRICH_CHANGE_SCHEDULES:
            return
        changes = [record for record in records if record.is_change]
        if not changes:
            return
        parents = self.fetch_parents(
            [record.request_id for record in changes]
        )
        starts_updated = 0
        ends_updated = 0
        for record in changes:
            values = parents.get(record.request_id.upper())
            if not values:
                continue
            scheduled_start, scheduled_end = self.mapper.change_schedule(values)
            if scheduled_start is not None:
                record.scheduled_start = scheduled_start
                starts_updated += 1
            if scheduled_end is not None:
                record.scheduled_end = scheduled_end
                ends_updated += 1
        logger.info(
            "Helix CHG schedule enrichment | crqs=%d parents=%d starts=%d ends=%d",
            len(changes),
            len(parents),
            starts_updated,
            ends_updated,
        )
