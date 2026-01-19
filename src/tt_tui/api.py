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
    """A Traefik router (summary)."""

    name: str
    provider: str
    status: str
    rule: str
    service: str
    entry_points: list[str]
    middlewares: list[str] | None = None
    tls: bool = False
    priority: int = 0


@dataclass
class RouterDetail:
    """Detailed Traefik router information."""

    name: str
    provider: str
    status: str
    rule: str
    service: str
    entry_points: list[str]
    middlewares: list[str] | None = None
    tls: dict | None = None
    priority: int = 0
    using: list[str] | None = None
    error: list[str] | None = None
    # Raw data for any extra fields
    raw: dict | None = None


@dataclass
class Service:
    """A Traefik service (summary)."""

    name: str
    provider: str
    status: str
    type: str
    servers_status: dict[str, str] | None = None


@dataclass
class ServiceDetail:
    """Detailed Traefik service information."""

    name: str
    provider: str
    status: str
    type: str
    servers_status: dict[str, str] | None = None
    load_balancer: dict | None = None
    weighted: dict | None = None
    mirroring: dict | None = None
    failover: dict | None = None
    using: list[str] | None = None
    used_by: list[str] | None = None
    error: list[str] | None = None
    # Raw data for any extra fields
    raw: dict | None = None


@dataclass
class Entrypoint:
    """A Traefik entrypoint (summary)."""

    name: str
    address: str
    protocol: str | None = None


@dataclass
class EntrypointDetail:
    """Detailed Traefik entrypoint information."""

    name: str
    address: str
    protocol: str | None = None
    transport: dict | None = None
    forwarded_headers: dict | None = None
    http: dict | None = None
    udp: dict | None = None
    # Raw data for any extra fields
    raw: dict | None = None


@dataclass
class Middleware:
    """A Traefik middleware (summary)."""

    name: str
    provider: str
    status: str
    type: str | None = None


@dataclass
class MiddlewareDetail:
    """Detailed Traefik middleware information."""

    name: str
    provider: str
    status: str
    type: str | None = None
    using: list[str] | None = None
    used_by: list[str] | None = None
    error: list[str] | None = None
    # Type-specific configuration (e.g., stripPrefix, headers, rateLimit config)
    config: dict | None = None
    # Raw data for any extra fields
    raw: dict | None = None


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

    def __init__(self, status_code: int, url: str = "", message: str = ""):
        self.status_code = status_code
        self.url = url
        if url:
            super().__init__(f"HTTP {status_code}: {url}")
        elif message:
            super().__init__(f"HTTP {status_code}: {message}")
        else:
            super().__init__(f"HTTP {status_code}")


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
        except httpx.RemoteProtocolError as e:
            raise TraefikConnectionError("Server disconnected") from e
        except httpx.HTTPStatusError as e:
            raise TraefikHTTPError(e.response.status_code, url=url) from e
        except httpx.RequestError as e:
            # Catch any other httpx request errors
            raise TraefikConnectionError(str(e)) from e

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

    async def get_http_router(self, name: str) -> RouterDetail:
        """Get details for a specific HTTP router."""
        data = await self._get(f"/api/http/routers/{name}")
        return self._parse_router_detail(data)

    async def get_tcp_router(self, name: str) -> RouterDetail:
        """Get details for a specific TCP router."""
        data = await self._get(f"/api/tcp/routers/{name}")
        return self._parse_router_detail(data)

    async def get_udp_router(self, name: str) -> RouterDetail:
        """Get details for a specific UDP router."""
        data = await self._get(f"/api/udp/routers/{name}")
        return self._parse_router_detail(data)

    async def get_http_services(self) -> list[Service]:
        """Get all HTTP services."""
        data = await self._get("/api/http/services")
        return [self._parse_service(s) for s in data]

    async def get_tcp_services(self) -> list[Service]:
        """Get all TCP services."""
        data = await self._get("/api/tcp/services")
        return [self._parse_service(s) for s in data]

    async def get_udp_services(self) -> list[Service]:
        """Get all UDP services."""
        data = await self._get("/api/udp/services")
        return [self._parse_service(s) for s in data]

    async def get_http_service(self, name: str) -> ServiceDetail:
        """Get details for a specific HTTP service."""
        data = await self._get(f"/api/http/services/{name}")
        return self._parse_service_detail(data)

    async def get_tcp_service(self, name: str) -> ServiceDetail:
        """Get details for a specific TCP service."""
        data = await self._get(f"/api/tcp/services/{name}")
        return self._parse_service_detail(data)

    async def get_udp_service(self, name: str) -> ServiceDetail:
        """Get details for a specific UDP service."""
        data = await self._get(f"/api/udp/services/{name}")
        return self._parse_service_detail(data)

    async def get_entrypoints(self) -> list[Entrypoint]:
        """Get all entrypoints."""
        data = await self._get("/api/entrypoints")
        return [self._parse_entrypoint(e) for e in data]

    async def get_entrypoint(self, name: str) -> EntrypointDetail:
        """Get details for a specific entrypoint."""
        data = await self._get(f"/api/entrypoints/{name}")
        return self._parse_entrypoint_detail(data)

    async def get_http_middlewares(self) -> list[Middleware]:
        """Get all HTTP middlewares."""
        data = await self._get("/api/http/middlewares")
        return [self._parse_middleware(m) for m in data]

    async def get_tcp_middlewares(self) -> list[Middleware]:
        """Get all TCP middlewares."""
        data = await self._get("/api/tcp/middlewares")
        return [self._parse_middleware(m) for m in data]

    async def get_http_middleware(self, name: str) -> MiddlewareDetail:
        """Get details for a specific HTTP middleware."""
        data = await self._get(f"/api/http/middlewares/{name}")
        return self._parse_middleware_detail(data)

    async def get_tcp_middleware(self, name: str) -> MiddlewareDetail:
        """Get details for a specific TCP middleware."""
        data = await self._get(f"/api/tcp/middlewares/{name}")
        return self._parse_middleware_detail(data)

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

    def _parse_router_detail(self, data: dict) -> RouterDetail:
        """Parse detailed router data from API response."""
        return RouterDetail(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            rule=data.get("rule", ""),
            service=data.get("service", ""),
            entry_points=data.get("entryPoints", []),
            middlewares=data.get("middlewares"),
            tls=data.get("tls"),
            priority=data.get("priority", 0),
            using=data.get("using"),
            error=data.get("error"),
            raw=data,
        )

    def _parse_service(self, data: dict) -> Service:
        """Parse service data from API response."""
        return Service(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            type=data.get("type", ""),
            servers_status=data.get("serverStatus"),
        )

    def _parse_service_detail(self, data: dict) -> ServiceDetail:
        """Parse detailed service data from API response."""
        return ServiceDetail(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            type=data.get("type", ""),
            servers_status=data.get("serverStatus"),
            load_balancer=data.get("loadBalancer"),
            weighted=data.get("weighted"),
            mirroring=data.get("mirroring"),
            failover=data.get("failover"),
            using=data.get("using"),
            used_by=data.get("usedBy"),
            error=data.get("error"),
            raw=data,
        )

    def _parse_entrypoint(self, data: dict) -> Entrypoint:
        """Parse entrypoint data from API response."""
        # Determine protocol from address suffix
        # Address format: ":PORT/protocol" - e.g., ":8080/tcp", ":53/udp"
        # If no suffix, it's HTTP
        address = data.get("address", "")
        if address.endswith("/tcp"):
            protocol = "tcp"
        elif address.endswith("/udp"):
            protocol = "udp"
        else:
            protocol = "http"

        return Entrypoint(
            name=data.get("name", ""),
            address=address,
            protocol=protocol,
        )

    def _parse_entrypoint_detail(self, data: dict) -> EntrypointDetail:
        """Parse detailed entrypoint data from API response."""
        # Determine protocol from address suffix
        address = data.get("address", "")
        if address.endswith("/tcp"):
            protocol = "tcp"
        elif address.endswith("/udp"):
            protocol = "udp"
        else:
            protocol = "http"

        return EntrypointDetail(
            name=data.get("name", ""),
            address=address,
            protocol=protocol,
            transport=data.get("transport"),
            forwarded_headers=data.get("forwardedHeaders"),
            http=data.get("http"),
            udp=data.get("udp"),
            raw=data,
        )

    def _parse_middleware(self, data: dict) -> Middleware:
        """Parse middleware data from API response."""
        return Middleware(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            type=data.get("type"),
        )

    def _parse_middleware_detail(self, data: dict) -> MiddlewareDetail:
        """Parse detailed middleware data from API response."""
        # Extract the type-specific configuration
        # Standard fields that are not config data
        standard_fields = {"name", "provider", "status", "type", "using", "usedBy", "error"}

        # Find the config by looking for any non-standard fields
        config = {}
        for key, value in data.items():
            if key not in standard_fields and isinstance(value, dict):
                config[key] = value

        return MiddlewareDetail(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            status=data.get("status", "unknown"),
            type=data.get("type"),
            using=data.get("using"),
            used_by=data.get("usedBy"),
            error=data.get("error"),
            config=config if config else None,
            raw=data,
        )
