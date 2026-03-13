"""SSH tunnel management for remote Traefik connections.

Uses the system ssh command via subprocess to ensure full compatibility
with SSH config (Include, Match, ProxyCommand, CertificateFile, etc.).
"""

import asyncio
import socket

from .models import SSHTunnel, TunnelStatus


class SSHTunnelError(Exception):
    """Exception raised for SSH tunnel errors."""

    pass


class SSHTunnelManager:
    """Manages SSH tunnel connections for profiles using the system ssh command."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._local_ports: dict[str, int] = {}
        self._configs: dict[str, SSHTunnel] = {}
        self._lock = asyncio.Lock()

    def _find_free_port(self) -> int:
        """Find a free local port for the tunnel."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _is_connection_alive(self, profile_name: str) -> bool:
        """Check if an existing SSH process is still running."""
        if profile_name not in self._processes:
            return False
        proc = self._processes[profile_name]
        return proc.returncode is None

    def _config_changed(self, profile_name: str, config: SSHTunnel) -> bool:
        """Check if the tunnel configuration has changed."""
        if profile_name not in self._configs:
            return True
        old = self._configs[profile_name]
        return (
            old.host != config.host
            or old.remote_host != config.remote_host
            or old.remote_port != config.remote_port
            or (config.local_port > 0 and old.local_port != config.local_port)
        )

    async def _wait_for_port(self, port: int, timeout: float = 10.0) -> bool:
        """Wait for a local port to become connectable."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", port), timeout=1.0
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.1)
        return False

    async def open_tunnel(
        self, profile_name: str, config: SSHTunnel
    ) -> tuple[TunnelStatus, int | None, str | None]:
        """Open an SSH tunnel for a profile, reusing existing connection if available."""
        async with self._lock:
            if not config.enabled:
                await self._close_tunnel_internal(profile_name)
                return TunnelStatus.CLOSED, None, None

            if not config.host:
                return TunnelStatus.ERROR, None, "SSH host is required"

            # Check if we can reuse the existing tunnel
            if (
                profile_name in self._processes
                and self._is_connection_alive(profile_name)
                and not self._config_changed(profile_name, config)
            ):
                local_port = self._local_ports.get(profile_name)
                return TunnelStatus.OPEN, local_port, None

            # Need to create a new tunnel - close any existing one first
            await self._close_tunnel_internal(profile_name)

            try:
                local_port = config.local_port if config.local_port > 0 else self._find_free_port()

                # Build ssh command: ssh -N -L local:remote_host:remote_port host
                cmd = [
                    "ssh",
                    "-N",  # No remote command
                    "-o", "ExitOnForwardFailure=yes",
                    "-o", "ServerAliveInterval=15",
                    "-o", "ServerAliveCountMax=3",
                    "-L", f"127.0.0.1:{local_port}:{config.remote_host}:{config.remote_port}",
                    config.host,
                ]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Wait for the tunnel port to become available
                port_ready = await self._wait_for_port(local_port, timeout=15.0)

                if not port_ready:
                    # Collect stderr for diagnostics
                    stderr_text = ""
                    if proc.stderr:
                        try:
                            stderr_bytes = await asyncio.wait_for(
                                proc.stderr.read(), timeout=2.0
                            )
                            stderr_text = stderr_bytes.decode().strip()
                        except asyncio.TimeoutError:
                            pass

                    # Check if process died
                    if proc.returncode is not None:
                        error_msg = stderr_text or f"SSH exited with code {proc.returncode}"
                        return TunnelStatus.ERROR, None, error_msg
                    # Process running but port not ready - kill it
                    proc.terminate()
                    await proc.wait()
                    error_msg = stderr_text or "Tunnel port did not become ready"
                    return TunnelStatus.ERROR, None, error_msg

                self._processes[profile_name] = proc
                self._local_ports[profile_name] = local_port
                self._configs[profile_name] = config

                return TunnelStatus.OPEN, local_port, None

            except FileNotFoundError:
                return TunnelStatus.ERROR, None, "ssh command not found"
            except Exception as e:
                return TunnelStatus.ERROR, None, str(e)

    async def _close_tunnel_internal(self, profile_name: str) -> None:
        """Close tunnel without acquiring lock (internal use only)."""
        if profile_name in self._processes:
            proc = self._processes[profile_name]
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            del self._processes[profile_name]

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
            for profile_name in list(self._processes.keys()):
                await self._close_tunnel_internal(profile_name)

    def get_local_port(self, profile_name: str) -> int | None:
        """Get the local port for a profile's tunnel."""
        return self._local_ports.get(profile_name)

    def is_tunnel_open(self, profile_name: str) -> bool:
        """Check if a tunnel is open for a profile."""
        return profile_name in self._processes and self._is_connection_alive(profile_name)

    def get_effective_url(
        self, profile_name: str, original_url: str, config: SSHTunnel | None
    ) -> str:
        """Get the effective URL for connecting to Traefik.

        If SSH tunnel is enabled and open, returns localhost URL with forwarded port.
        Otherwise returns the original URL.
        """
        if config and config.enabled and profile_name in self._local_ports:
            local_port = self._local_ports[profile_name]
            return f"http://127.0.0.1:{local_port}"
        return original_url


# Global tunnel manager instance
tunnel_manager = SSHTunnelManager()
