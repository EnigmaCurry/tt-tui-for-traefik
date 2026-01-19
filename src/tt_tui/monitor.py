"""Connection monitor for polling Traefik API."""

from .api import TraefikAPI, TraefikConnectionError, TraefikHTTPError, TraefikTimeoutError
from .models import BasicAuth, ConnectionStatus, ProfileRuntime


async def check_connection(
    url: str, basic_auth: BasicAuth | None = None, timeout: float = 5.0
) -> ProfileRuntime:
    """Check connection to a Traefik instance and return runtime state."""
    runtime = ProfileRuntime(status=ConnectionStatus.CONNECTING)

    try:
        api = TraefikAPI(url, basic_auth, timeout)
        version_info = await api.get_version()
        runtime.status = ConnectionStatus.CONNECTED
        runtime.version = version_info.version

    except TraefikTimeoutError:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = "Connection timed out"
    except TraefikConnectionError:
        runtime.status = ConnectionStatus.DISCONNECTED
        runtime.error = "Unable to connect"
    except TraefikHTTPError as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = f"HTTP {e.status_code}"
    except Exception as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = str(e)

    return runtime
