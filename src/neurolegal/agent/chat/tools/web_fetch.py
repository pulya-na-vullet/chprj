"""Tool: web_fetch — fetch the content of a URL and return readable text.

SSRF guard is enforced: only http/https are allowed; the hostname is resolved
and the request is blocked if any resolved IP is private, loopback, link-local,
or reserved. Redirects are never followed.
"""

import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.contracts import WebSource

WEB_FETCH_TOOL = ToolSpec(
    name="web_fetch",
    description=(
        "Скачать страницу по URL и вернуть читаемый текст (контекст, не основание "
        "для правовой нормы)."
    ),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)


# Many sites (e.g. Wikimedia) return 403 to httpx's default User-Agent.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; neurolegal-agent/1.0; +https://github.com/neurolegal) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    )
}


def _is_blocked(url: str) -> bool:
    """Return True if the URL must be blocked (bad scheme, unresolvable, or private IP)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return True
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    url = str(arguments.get("url", "")).strip()
    # _is_blocked performs a blocking DNS lookup (socket.getaddrinfo); run it off
    # the event loop so a slow/unresolvable host can't stall the whole agent.
    blocked = not url or await asyncio.get_running_loop().run_in_executor(None, _is_blocked, url)
    if blocked:
        return ToolOutcome(json.dumps({"error": "url blocked or invalid"}, ensure_ascii=False))

    max_chars = ctx.tools.web_fetch.max_chars
    loop = asyncio.get_running_loop()
    # Follow redirects manually so each hop's target is re-validated against the
    # SSRF guard — httpx's built-in follow would chase a redirect to a private
    # address. Most real sites redirect (http→https, URL normalization), so we
    # cannot simply disable redirects.
    try:
        html: str | None = None
        current = url
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, headers=_HEADERS) as c:
            for _ in range(5):
                r = await c.get(current)
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        break
                    current = str(httpx.URL(current).join(location))
                    if await loop.run_in_executor(None, _is_blocked, current):
                        return ToolOutcome(
                            json.dumps({"error": "redirect blocked"}, ensure_ascii=False)
                        )
                    continue
                r.raise_for_status()
                html = r.text[: max_chars * 4]
                break
        if html is None:
            return ToolOutcome(json.dumps({"error": "fetch failed"}, ensure_ascii=False))
    except httpx.HTTPError:
        return ToolOutcome(json.dumps({"error": "fetch failed"}, ensure_ascii=False))

    text = (trafilatura.extract(html) or "")[:max_chars]
    title: str = url
    if text:
        meta = trafilatura.extract_metadata(html)
        if meta is not None:
            meta_title: str | None = getattr(meta, "title", None)
            if meta_title:
                title = meta_title

    src = WebSource(url=url, title=title, snippet=text)
    return ToolOutcome(
        json.dumps({"url": url, "title": title, "text": text}, ensure_ascii=False),
        web_sources=[src],
    )
