"""HTTP plumbing shared by the providers and the feed reader."""

import urllib.error
import urllib.request

from xgenerateposts.config import MAX_RESPONSE_BYTES


class InsecureRedirectError(urllib.error.URLError):
    """An HTTPS request was redirected to a non-HTTPS URL."""


class NoDowngradeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects, except from HTTPS to anything that is not HTTPS.

    A downgraded feed can be altered in transit, and urllib would carry an
    Authorization header across the redirect.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.full_url.lower().startswith("https://") and not newurl.lower().startswith(
            "https://"
        ):
            raise InsecureRedirectError(f"refused redirect from HTTPS to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


HTTP_OPENER = urllib.request.build_opener(NoDowngradeRedirectHandler)


def read_capped(response, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    """Read at most `limit` bytes; anything larger is refused, not truncated."""
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError(f"response is larger than {limit:,} bytes")
    return body


def redact(text: str, *secrets: str) -> str:
    """Remove secret values from text that is about to be shown or logged."""
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[redacted]")
    return text
