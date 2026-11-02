"""Authenticated Helix AR System HTTP client."""

import logging
import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from helix.config import (
    CHANGE_FORM,
    CHANGE_LOOKUP_BATCH_SIZE,
    HELIX_BASE_URL,
    HELIX_FIELD_MAP,
    HELIX_PASSWORD,
    HELIX_USERNAME,
    PAGE_SIZE,
    REQUEST_SLEEP_SECONDS,
    USE_FIELD_SELECTION,
    VERIFY_SSL,
)
from helix.query import HelixQueryBuilder

logger = logging.getLogger(__name__)

if not VERIFY_SSL:
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class HelixClient:
    def __init__(self):
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self.query = HelixQueryBuilder()

    @staticmethod
    def is_configured() -> bool:
        return bool(HELIX_BASE_URL and HELIX_USERNAME and HELIX_PASSWORD)

    @staticmethod
    def proxies() -> dict[str, str] | None:
        proxy_url = os.getenv("HELIX_PROXY_URL")
        http_proxy = os.getenv("HELIX_HTTP_PROXY") or proxy_url
        https_proxy = os.getenv("HELIX_HTTPS_PROXY") or proxy_url
        proxies = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            if urlparse(https_proxy).scheme == "https":
                logger.warning(
                    "HELIX_HTTPS_PROXY uses https://. If Helix reports SSL "
                    "wrong-version errors, use the proxy's http:// URL."
                )
            proxies["https"] = https_proxy
        return proxies or None

    def authenticate(self) -> str:
        if (
            self._token
            and self._token_expiry
            and datetime.now() < self._token_expiry
        ):
            return self._token
        response = requests.post(
            f"{HELIX_BASE_URL.rstrip('/')}/api/jwt/login",
            data={"username": HELIX_USERNAME, "password": HELIX_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
            verify=VERIFY_SSL,
            proxies=self.proxies(),
        )
        response.raise_for_status()
        self._token = response.text.strip().strip('"')
        self._token_expiry = datetime.now() + timedelta(minutes=59)
        logger.info("Helix JWT obtained, expires at %s", self._token_expiry)
        return self._token

    def fetch_task_page(self, offset: int, qualification: str) -> list:
        params = {"q": qualification, "limit": PAGE_SIZE, "offset": offset}
        if USE_FIELD_SELECTION:
            params["fields"] = ",".join(HELIX_FIELD_MAP.keys())
        response = requests.get(
            f"{HELIX_BASE_URL.rstrip('/')}/api/arsys/v1/entry/TMS:Task",
            params=params,
            headers={
                "Authorization": f"AR-JWT {self.authenticate()}",
                "Accept": "application/json",
            },
            timeout=180,
            verify=VERIFY_SSL,
            proxies=self.proxies(),
        )
        if not response.ok:
            logger.error(
                "Helix API error response (offset=%d): %s",
                offset,
                response.text[:2000],
            )
        response.raise_for_status()
        return response.json().get("entries", [])

    def fetch_change_parents(self, request_ids: list[str]) -> dict[str, dict]:
        unique_ids = list(dict.fromkeys(
            request_id.strip()
            for request_id in request_ids
            if request_id and request_id.upper().startswith("CRQ")
        ))
        if not unique_ids:
            return {}
        headers = {
            "Authorization": f"AR-JWT {self.authenticate()}",
            "Accept": "application/json",
        }
        parents = {}
        step = max(1, CHANGE_LOOKUP_BATCH_SIZE)
        for start in range(0, len(unique_ids), step):
            batch = unique_ids[start:start + step]
            qualification = (
                f"({' OR '.join(self.query.equals('Infrastructure Change ID', item) for item in batch)})"
            )
            try:
                response = requests.get(
                    f"{HELIX_BASE_URL.rstrip('/')}/api/arsys/v1/entry/{CHANGE_FORM}",
                    params={"q": qualification, "limit": len(batch)},
                    headers=headers,
                    timeout=180,
                    verify=VERIFY_SSL,
                    proxies=self.proxies(),
                )
                if not response.ok:
                    logger.error(
                        "Helix CHG parent lookup failed: %s",
                        response.text[:2000],
                    )
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.warning(
                    "Skipping CHG schedule enrichment for %d CRQs: %s",
                    len(batch),
                    exc,
                )
                continue
            for entry in response.json().get("entries", []):
                values = entry.get("values", {})
                request_id = str(
                    values.get("Infrastructure Change ID") or ""
                ).strip()
                if request_id:
                    parents[request_id.upper()] = values
            if REQUEST_SLEEP_SECONDS > 0 and start + len(batch) < len(unique_ids):
                time.sleep(REQUEST_SLEEP_SECONDS)
        return parents

