from __future__ import annotations

import email.utils
import logging
import re
import time
from datetime import date
from typing import Any

import httpx

from . import __version__
from .errors import NotFoundError, UpstreamError
from .models import EventDetails, EventSummary, OrganizationContext
from .parsers import (
    extract_details_api_url,
    loads_json,
    parse_calendar_response,
    parse_detail_api_html,
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
            headers={
                "User-Agent": f"courtreserve-cli/{__version__} (+read-only public calendar client)"
            },
        )

    def __enter__(self) -> CourtReserveClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.http.close()

    def bootstrap_organization(self, org: int | str) -> OrganizationContext:
        org_id = self.resolve_organization_id(org)
        url = f"{self.app_base_url}/Online/Calendar/Events/{org_id}/Month"
        response = self._request("GET", url)
        return parse_organization_page(response.text, org_id, self.app_base_url)

    def resolve_organization_id(self, org: int | str) -> int:
        if isinstance(org, int):
            return org
        value = org.strip()
        if not value:
            raise UpstreamError("Organization name cannot be empty")
        if value.isdigit():
            return int(value)
        candidates = self._search_organization_candidates(value)
        if not candidates:
            raise UpstreamError(f"Could not find a CourtReserve organization matching {value!r}")
        selected = self._select_organization_candidate(value, candidates)
        if selected is None:
            titles = ", ".join(title for _, title, _ in candidates[:5])
            raise UpstreamError(
                f"Could not uniquely identify a CourtReserve organization matching {value!r}; "
                f"found: {titles}"
            )
        return selected

    def _search_organization_candidates(self, value: str) -> list[tuple[int, str, str]]:
        return self._search_organization_candidates_official(value)

    def _search_organization_candidates_official(
        self, value: str
    ) -> list[tuple[int, str, str]]:
        try:
            response = self._request(
                "POST",
                "https://backend.courtreserve.com/api/public/search-organization",
                json={"searchTerm": value},
            )
        except UpstreamError as exc:
            logger.info("Official CourtReserve organization search failed: %s", exc)
            return []
        try:
            payload: Any = loads_json(response.text)
        except UpstreamError as exc:
            logger.info("Official CourtReserve organization search returned invalid JSON: %s", exc)
            return []
        return self._parse_official_organization_search(payload)

    @staticmethod
    def _parse_official_organization_search(payload: Any) -> list[tuple[int, str, str]]:
        results: list[tuple[int, str, str]] = []
        seen: set[int] = set()
        for record in CourtReserveClient._walk_search_records(payload):
            org_id = CourtReserveClient._extract_search_record_org_id(record)
            title = CourtReserveClient._extract_search_record_title(record)
            if org_id is None or not title or org_id in seen:
                continue
            seen.add(org_id)
            url = CourtReserveClient._extract_search_record_url(record, org_id)
            results.append((org_id, title, url))
        return results

    @staticmethod
    def _walk_search_records(payload: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                records.append(value)
                for key in (
                    "data",
                    "results",
                    "items",
                    "organizations",
                    "clubs",
                    "records",
                ):
                    nested = value.get(key)
                    if isinstance(nested, (dict, list)):
                        visit(nested)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(payload)
        return records

    @staticmethod
    def _extract_search_record_org_id(record: dict[str, Any]) -> int | None:
        for key in (
            "orgId",
            "organizationId",
            "organizationID",
            "OrganizationId",
            "OrganizationID",
            "id",
            "Id",
        ):
            value = record.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        for key in (
            "url",
            "Url",
            "href",
            "Href",
            "link",
            "Link",
            "portalUrl",
            "PortalUrl",
            "accountUrl",
            "AccountUrl",
            "createAccountUrl",
            "CreateAccountUrl",
        ):
            value = record.get(key)
            if isinstance(value, str):
                match = re.search(r"/(?:Online/Portal/Index|Online/Account/Register)/(\d+)", value)
                if match:
                    return int(match.group(1))
        return None

    @staticmethod
    def _extract_search_record_title(record: dict[str, Any]) -> str | None:
        for key in (
            "name",
            "Name",
            "organizationName",
            "OrganizationName",
            "displayName",
            "DisplayName",
            "title",
            "Title",
            "clubName",
            "ClubName",
        ):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_search_record_url(record: dict[str, Any], org_id: int) -> str:
        for key in (
            "url",
            "Url",
            "href",
            "Href",
            "link",
            "Link",
            "portalUrl",
            "PortalUrl",
            "accountUrl",
            "AccountUrl",
            "createAccountUrl",
            "CreateAccountUrl",
            "websiteUrl",
            "WebsiteUrl",
        ):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"https://app.courtreserve.com/Online/Portal/Index/{org_id}"

    @staticmethod
    def _select_organization_candidate(
        value: str, candidates: list[tuple[int, str, str]]
    ) -> int | None:
        query = CourtReserveClient._normalize_text(value)
        query_tokens = set(query.split())
        scored: list[tuple[int, int, int, int, int, int]] = []
        for index, (org_id, title, _) in enumerate(candidates):
            normalized = CourtReserveClient._normalize_text(title)
            title_tokens = set(normalized.split())
            overlap = len(query_tokens & title_tokens)
            exact = int(normalized == query)
            contains = int(query in normalized)
            starts = int(normalized.startswith(query))
            scored.append((overlap, exact, contains, starts, -index, org_id))
        scored.sort(reverse=True)
        best = scored[0]
        if best[0] == 0 and len(candidates) > 1:
            return None
        if len(scored) > 1 and scored[0][:4] == scored[1][:4] and scored[0][5] != scored[1][5]:
            return None
        return best[5]

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

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
            return parse_detail_api_html(api_response.text, fallback, context.timezone), False
        except NotFoundError:
            if fallback.name == "Event Details" and fallback.description is None:
                raise
            return fallback, True
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
