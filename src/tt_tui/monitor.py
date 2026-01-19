"""Connection monitor for polling Traefik API."""

import httpx

from .models import BasicAuth, ConnectionStatus, ProfileRuntime


async def check_connection(
    url: str, basic_auth: BasicAuth | None = None, timeout: float = 5.0
) -> ProfileRuntime:
    """Check connection to a Traefik instance and return runtime state."""
    runtime = ProfileRuntime(status=ConnectionStatus.CONNECTING)

    # Ensure URL doesn't have trailing slash
    base_url = url.rstrip("/")
    api_url = f"{base_url}/api/version"

    try:
        auth = None
        if basic_auth and basic_auth.username:
            auth = httpx.BasicAuth(basic_auth.username, basic_auth.password)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(api_url, auth=auth)
            response.raise_for_status()

            data = response.json()
            runtime.status = ConnectionStatus.CONNECTED
            runtime.version = data.get("Version", "unknown")

    except httpx.TimeoutException:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = "Connection timed out"
    except httpx.ConnectError:
        runtime.status = ConnectionStatus.DISCONNECTED
        runtime.error = "Unable to connect"
    except httpx.HTTPStatusError as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = f"HTTP {e.response.status_code}"
    except Exception as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = str(e)

    return runtime
