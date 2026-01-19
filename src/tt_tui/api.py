"""Traefik API client library."""

from dataclasses import dataclass

import httpx

from .models import BasicAuth


@dataclass
class TraefikVersion:
    """Traefik version information."""

    version: str
    codename: str | None = None


@dataclass
class Router:
    """A Traefik router."""

    name: str
    provider: str
    status: str
    rule: str
    service: str
    entry_points: list[str]
    middlewares: list[str] | None = None
    tls: bool = False
    priority: int = 0


class TraefikAPIError(Exception):
    """Base exception for Traefik API errors."""

    pass


class TraefikConnectionError(TraefikAPIError):
    """Connection error."""

    pass


class TraefikTimeoutError(TraefikAPIError):
    """Timeout error."""

    pass


class TraefikHTTPError(TraefikAPIError):
    """HTTP error response."""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}")


class TraefikAPI:
    """Async client for the Traefik API."""

    def __init__(
        self,
        base_url: str,
        basic_auth: BasicAuth | None = None,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._auth = None
        if basic_auth and basic_auth.username:
            self._auth = httpx.BasicAuth(basic_auth.username, basic_auth.password)

    async def _request(self, method: str, path: str) -> dict | list:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, auth=self._auth)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            raise TraefikTimeoutError("Connection timed out") from e
        except httpx.ConnectError as e:
            raise TraefikConnectionError("Unable to connect") from e
        except httpx.HTTPStatusError as e:
            raise TraefikHTTPError(e.response.status_code) from e

    async def _get(self, path: str) -> dict | list:
        """Make a GET request."""
        return await self._request("GET", path)

    async def get_version(self) -> TraefikVersion:
        """Get Traefik version information."""
        data = await self._get("/api/version")
        return TraefikVersion(
            version=data.get("Version", "unknown"),
            codename=data.get("Codename"),
        )

    async def get_http_routers(self) -> list[Router]:
        """Get all HTTP routers."""
        data = await self._get("/api/http/routers")
        return [self._parse_router(r) for r in data]

    async def get_tcp_routers(self) -> list[Router]:
        """Get all TCP routers."""
        data = await self._get("/api/tcp/routers")
        return [self._parse_router(r) for r in data]

    async def get_udp_routers(self) -> list[Router]:
        """Get all UDP routers."""
        data = await self._get("/api/udp/routers")
        return [self._parse_router(r) for r in data]

    def _parse_router(self, data: dict) -> Router:
        """Parse router data from API response."""
        return Router(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            rule=data.get("rule", ""),
            service=data.get("service", ""),
            entry_points=data.get("entryPoints", []),
            middlewares=data.get("middlewares"),
            tls=data.get("tls") is not None,
            priority=data.get("priority", 0),
        )
