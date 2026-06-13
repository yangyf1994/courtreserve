class CourtReserveError(Exception):
    """Base error for expected CLI failures."""


class UpstreamError(CourtReserveError):
    """CourtReserve returned an unusable response."""


class NotFoundError(CourtReserveError):
    """The requested public resource was not found."""

