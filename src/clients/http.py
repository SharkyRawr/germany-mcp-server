"""Bounded upstream HTTP reads shared by all data clients."""

import asyncio

import httpx

from src.config import settings


class ResponseTooLarge(httpx.HTTPError):
    """The upstream body exceeded the configured byte budget."""


async def bounded_get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Read a response within a byte and time budget, including redirects.

    Request identity encoding and reject unsolicited compression so the size
    budget also bounds memory before any decompression can take place.
    """
    follow_redirects = kwargs.pop("follow_redirects", False)
    headers = httpx.Headers(kwargs.pop("headers", None))
    headers["Accept-Encoding"] = "identity"
    origin = httpx.URL(url)
    async with asyncio.timeout(settings.http_timeout):
        for _ in range(11):
            async with client.stream(
                "GET", url, headers=headers, follow_redirects=False, **kwargs
            ) as response:
                if follow_redirects and response.is_redirect and response.next_request:
                    target = response.next_request.url
                    if (target.scheme, target.host, target.port) != (
                        origin.scheme,
                        origin.host,
                        origin.port,
                    ):
                        raise httpx.HTTPError("Cross-origin redirect rejected")
                    url = str(target)
                    kwargs.pop("params", None)
                    continue
                if (
                    response.headers.get("content-encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise httpx.HTTPError("Unexpected compressed response")
                length = response.headers.get("content-length")
                if length and int(length) > settings.http_max_response_bytes:
                    raise ResponseTooLarge("Response exceeds byte limit")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > settings.http_max_response_bytes:
                        raise ResponseTooLarge("Response exceeds byte limit")
                    body.extend(chunk)
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=bytes(body),
                    request=response.request,
                )
        raise httpx.TooManyRedirects("Too many redirects")
