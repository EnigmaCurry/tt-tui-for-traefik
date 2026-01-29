"""Connection monitor for polling Traefik API."""

from .api import TraefikAPI, TraefikConnectionError, TraefikHTTPError, TraefikTimeoutError
from .models import BasicAuth, ConnectionStatus, ProfileRuntime, SSHTunnel, TunnelStatus
from .ssh_tunnel import tunnel_manager


async def check_connection(
    url: str,
    basic_auth: BasicAuth | None = None,
    timeout: float = 5.0,
    profile_name: str | None = None,
    ssh_tunnel: SSHTunnel | None = None,
) -> ProfileRuntime:
    """Check connection to a Traefik instance and return runtime state.

    If SSH tunnel is configured and enabled, it will be established first,
    and the connection will be made through the tunnel.
    """
    runtime = ProfileRuntime(status=ConnectionStatus.CONNECTING)

    # Handle SSH tunnel if configured
    effective_url = url
    if profile_name and ssh_tunnel and ssh_tunnel.enabled:
        runtime.tunnel_status = TunnelStatus.CONNECTING

        tunnel_status, local_port, tunnel_error = await tunnel_manager.open_tunnel(
            profile_name, ssh_tunnel
        )

        runtime.tunnel_status = tunnel_status
        runtime.tunnel_error = tunnel_error
        runtime.tunnel_local_port = local_port

        if tunnel_status == TunnelStatus.ERROR:
            runtime.status = ConnectionStatus.ERROR
            runtime.error = f"SSH tunnel: {tunnel_error}"
            return runtime

        if tunnel_status == TunnelStatus.OPEN and local_port:
            effective_url = f"http://127.0.0.1:{local_port}"

    try:
        api = TraefikAPI(effective_url, basic_auth, timeout)
        version_info = await api.get_version()
        runtime.status = ConnectionStatus.CONNECTED
        runtime.version = version_info.version

    except TraefikTimeoutError:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = "Connection timed out"
    except TraefikConnectionError:
        runtime.status = ConnectionStatus.DISCONNECTED
        # Provide more helpful error message when using SSH tunnel
        if ssh_tunnel and ssh_tunnel.enabled:
            runtime.error = (
                f"Tunnel OK, but can't reach {ssh_tunnel.remote_host}:{ssh_tunnel.remote_port}"
            )
        else:
            runtime.error = "Unable to connect"
    except TraefikHTTPError as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = f"HTTP {e.status_code}"
    except Exception as e:
        runtime.status = ConnectionStatus.ERROR
        runtime.error = str(e)

    return runtime


async def close_tunnel(profile_name: str) -> None:
    """Close the SSH tunnel for a profile."""
    await tunnel_manager.close_tunnel(profile_name)


async def close_all_tunnels() -> None:
    """Close all SSH tunnels."""
    await tunnel_manager.close_all()


def get_effective_url(profile_name: str, url: str, ssh_tunnel: SSHTunnel | None) -> str:
    """Get the effective URL for API calls, considering SSH tunnel."""
    return tunnel_manager.get_effective_url(profile_name, url, ssh_tunnel)


async def ensure_tunnel_and_get_url(
    profile_name: str, url: str, ssh_tunnel: SSHTunnel | None
) -> str:
    """Ensure SSH tunnel is open (if configured) and return the effective URL.

    This async function should be used by data refresh methods to ensure the tunnel
    is established before making API calls.
    """
    if ssh_tunnel and ssh_tunnel.enabled:
        # Ensure tunnel is open
        tunnel_status, local_port, _ = await tunnel_manager.open_tunnel(profile_name, ssh_tunnel)
        if tunnel_status == TunnelStatus.OPEN and local_port:
            return f"http://127.0.0.1:{local_port}"
        # If tunnel failed to open, fall through to return original URL
        # (the API call will fail, but that's expected)
    return url
