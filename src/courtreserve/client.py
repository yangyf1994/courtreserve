from __future__ import annotations

import email.utils
import logging
import time
from datetime import date
from typing import Any

import httpx

from .errors import NotFoundError, UpstreamError
from .models import EventDetails, EventSummary, OrganizationContext
from .parsers import (
    extract_details_api_url,
    loads_json,
    parse_calendar_response,
    parse_detail_api,
    parse_detail_page,
    parse_organization_page,
)
from .request_builder import build_calendar_payload, split_by_month

logger = logging.getLogger("courtreserve")


class CourtReserveClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        app_base_url: str = "https://app.courtreserve.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_base_url = app_base_url.rstrip("/")
        self.http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": "courtreserve-cli/0.1 (+read-only public calendar client)"},
        )

    def __enter__(self) -> CourtReserveClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.http.close()

    def bootstrap_organization(self, org_id: int) -> OrganizationContext:
        url = f"{self.app_base_url}/Online/Calendar/Events/{org_id}/Month"
        response = self._request("GET", url)
        return parse_organization_page(response.text, org_id, self.app_base_url)

    def list_events(
        self, context: OrganizationContext, start: date, end: date
    ) -> list[EventSummary]:
        events: dict[str, EventSummary] = {}
        url = (
            f"{context.app_base_url}/Online/Calendar/ReadCalendarEvents/"
            f"{context.org_id}"
        )
        for chunk_start, chunk_end in split_by_month(start, end):
            response = self._request(
                "POST",
                url,
                data=build_calendar_payload(context, chunk_start, chunk_end),
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            payload = loads_json(response.text)
            if not isinstance(payload, dict):
                raise UpstreamError("CourtReserve calendar response was not an object")
            for event in parse_calendar_response(payload, context):
                if start <= event.start.date() <= end:
                    events[event.uq_id] = event
        return list(events.values())

    def get_event_details(
        self, context: OrganizationContext, number: str
    ) -> tuple[EventDetails, bool]:
        page_url = (
            f"{context.app_base_url}/Online/Events/Details/"
            f"{context.org_id}/{number}"
        )
        page_response = self._request("GET", page_url)
        fallback = parse_detail_page(page_response.text, context.org_id, number, page_url)
        api_url = extract_details_api_url(page_response.text, page_url)
        if not api_url:
            return fallback, True
        try:
            api_response = self._request("GET", api_url)
            payload: Any = loads_json(api_response.text)
            return parse_detail_api(payload, fallback, context.timezone), False
        except UpstreamError:
            return fallback, True

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            started = time.monotonic()
            try:
                response = self.http.request(method, url, **kwargs)
                elapsed = time.monotonic() - started
                logger.info(
                    "%s %s -> %s (%.2fs)",
                    method,
                    response.url.path,
                    response.status_code,
                    elapsed,
                )
                if response.status_code == 404:
                    raise NotFoundError(f"CourtReserve resource not found: {response.url.path}")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        time.sleep(self._retry_delay(response, attempt))
                        continue
                response.raise_for_status()
                return response
            except NotFoundError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.25 * (2 ** (attempt - 1)))
                    continue
        raise UpstreamError(
            f"CourtReserve request failed after 3 attempts: {method} {url}"
        ) from last_error

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return float(min(float(value), 10.0))
            except ValueError:
                parsed = email.utils.parsedate_to_datetime(value)
                return max(0.0, min(parsed.timestamp() - time.time(), 10.0))
        return float(0.25 * (2 ** (attempt - 1)))
