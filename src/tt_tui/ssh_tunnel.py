"""SSH tunnel management for remote Traefik connections."""

import asyncio
import socket
from pathlib import Path

import asyncssh

from .models import SSHTunnel, TunnelStatus


class SSHTunnelError(Exception):
    """Exception raised for SSH tunnel errors."""

    pass


class SSHTunnelManager:
    """Manages SSH tunnel connections for profiles."""

    def __init__(self) -> None:
        self._tunnels: dict[str, asyncssh.SSHClientConnection] = {}
        self._listeners: dict[str, asyncssh.SSHListener] = {}
        self._local_ports: dict[str, int] = {}
        self._configs: dict[str, SSHTunnel] = {}  # Store config to detect changes
        self._lock = asyncio.Lock()

    def _find_free_port(self) -> int:
        """Find a free local port for the tunnel."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _is_connection_alive(self, profile_name: str) -> bool:
        """Check if an existing SSH connection is still alive."""
        if profile_name not in self._tunnels:
            return False
        conn = self._tunnels[profile_name]
        # Check if connection is still open
        try:
            return conn.is_connected() if hasattr(conn, "is_connected") else not conn.is_closed()
        except Exception:
            return False

    def _config_changed(self, profile_name: str, config: SSHTunnel) -> bool:
        """Check if the tunnel configuration has changed."""
        if profile_name not in self._configs:
            return True
        old = self._configs[profile_name]
        return (
            old.host != config.host
            or old.port != config.port
            or old.username != config.username
            or old.identity_file != config.identity_file
            or old.password != config.password
            or old.remote_host != config.remote_host
            or old.remote_port != config.remote_port
            or (config.local_port > 0 and old.local_port != config.local_port)
        )

    async def open_tunnel(
        self, profile_name: str, config: SSHTunnel
    ) -> tuple[TunnelStatus, int | None, str | None]:
        """
        Open an SSH tunnel for a profile, reusing existing connection if available.

        Returns:
            Tuple of (status, local_port, error_message)
        """
        async with self._lock:
            if not config.enabled:
                await self._close_tunnel_internal(profile_name)
                return TunnelStatus.CLOSED, None, None

            if not config.host:
                return TunnelStatus.ERROR, None, "SSH host is required"

            # Check if we can reuse the existing tunnel
            if (
                profile_name in self._tunnels
                and self._is_connection_alive(profile_name)
                and not self._config_changed(profile_name, config)
            ):
                # Reuse existing tunnel
                local_port = self._local_ports.get(profile_name)
                return TunnelStatus.OPEN, local_port, None

            # Need to create a new tunnel - close any existing one first
            await self._close_tunnel_internal(profile_name)

            try:
                # Build connection kwargs - only include values if explicitly set
                # Use config=True to read from ~/.ssh/config for host aliases, user, port, etc.
                connect_kwargs: dict = {
                    "host": config.host,
                    "known_hosts": None,  # Accept any host key
                    "config": True,  # Read ~/.ssh/config for host settings
                }

                # Only specify port if not using default (lets SSH config take precedence)
                if config.port and config.port != 22:
                    connect_kwargs["port"] = config.port

                # Only specify username if explicitly provided
                if config.username:
                    connect_kwargs["username"] = config.username

                # Prefer identity file if provided
                if config.identity_file:
                    key_path = Path(config.identity_file).expanduser()
                    if not key_path.exists():
                        return (
                            TunnelStatus.ERROR,
                            None,
                            f"Key file not found: {config.identity_file}",
                        )
                    connect_kwargs["client_keys"] = [str(key_path)]
                elif config.password:
                    connect_kwargs["password"] = config.password
                else:
                    # Try default SSH agent / keys
                    pass

                # Establish SSH connection
                conn = await asyncssh.connect(**connect_kwargs)
                self._tunnels[profile_name] = conn

                # Determine local port
                local_port = config.local_port if config.local_port > 0 else self._find_free_port()

                # Create the port forward
                listener = await conn.forward_local_port(
                    "127.0.0.1",
                    local_port,
                    config.remote_host,
                    config.remote_port,
                )
                self._listeners[profile_name] = listener
                self._local_ports[profile_name] = local_port
                self._configs[profile_name] = config  # Store config for comparison

                return TunnelStatus.OPEN, local_port, None

            except asyncssh.DisconnectError as e:
                return TunnelStatus.ERROR, None, f"SSH disconnected: {e.reason}"
            except asyncssh.PermissionDenied:
                return TunnelStatus.ERROR, None, "SSH authentication failed"
            except asyncssh.HostKeyNotVerifiable:
                return TunnelStatus.ERROR, None, "SSH host key verification failed"
            except OSError as e:
                return TunnelStatus.ERROR, None, f"Connection failed: {e}"
            except Exception as e:
                return TunnelStatus.ERROR, None, str(e)

    async def _close_tunnel_internal(self, profile_name: str) -> None:
        """Close tunnel without acquiring lock (internal use only)."""
        if profile_name in self._listeners:
            try:
                self._listeners[profile_name].close()
            except Exception:
                pass
            del self._listeners[profile_name]

        if profile_name in self._tunnels:
            try:
                self._tunnels[profile_name].close()
            except Exception:
                pass
            del self._tunnels[profile_name]

        if profile_name in self._local_ports:
            del self._local_ports[profile_name]

        if profile_name in self._configs:
            del self._configs[profile_name]

    async def close_tunnel(self, profile_name: str) -> None:
        """Close an SSH tunnel for a profile."""
        async with self._lock:
            await self._close_tunnel_internal(profile_name)

    async def close_all(self) -> None:
        """Close all SSH tunnels."""
        async with self._lock:
            for profile_name in list(self._tunnels.keys()):
                await self._close_tunnel_internal(profile_name)

    def get_local_port(self, profile_name: str) -> int | None:
        """Get the local port for a profile's tunnel."""
        return self._local_ports.get(profile_name)

    def is_tunnel_open(self, profile_name: str) -> bool:
        """Check if a tunnel is open for a profile."""
        return profile_name in self._tunnels and profile_name in self._listeners

    def get_effective_url(
        self, profile_name: str, original_url: str, config: SSHTunnel | None
    ) -> str:
        """
        Get the effective URL for connecting to Traefik.

        If SSH tunnel is enabled and open, returns localhost URL with forwarded port.
        Otherwise returns the original URL.
        """
        if config and config.enabled and profile_name in self._local_ports:
            local_port = self._local_ports[profile_name]
            return f"http://127.0.0.1:{local_port}"
        return original_url


# Global tunnel manager instance
tunnel_manager = SSHTunnelManager()
