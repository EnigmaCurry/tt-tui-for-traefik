"""SSH tunnel management for remote Traefik connections.

Uses the system ssh command to run `nc` on the remote host, proxying TCP
connections through SSH command execution. A local TCP server accepts
connections and pipes each one through `ssh <host> nc <remote_host> <port>`.
Requires `nc` on the remote host.
"""

import asyncio
import socket

from .models import SSHTunnel, TunnelStatus


class SSHTunnelError(Exception):
    """Exception raised for SSH tunnel errors."""

    pass


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Copy data from reader to writer until EOF."""
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (OSError, ConnectionResetError):
            pass


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    ssh_host: str,
    remote_host: str,
    remote_port: int,
) -> None:
    """Handle a single client connection by proxying through ssh+nc."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", ssh_host, "nc", remote_host, str(remote_port),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        if not proc.stdin or not proc.stdout:
            client_writer.close()
            await client_writer.wait_closed()
            return

        # Bidirectional pipe: client <-> ssh+nc
        await asyncio.gather(
            _pipe(client_reader, proc.stdin),
            _pipe(proc.stdout, client_writer),
        )

        # Clean up the ssh process
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    except Exception:
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except (OSError, ConnectionResetError):
            pass


class SSHTunnelManager:
    """Manages SSH tunnel connections for profiles.

    Creates a local TCP server that proxies each connection through
    `ssh <host> nc <remote_host> <remote_port>`.
    """

    def __init__(self) -> None:
        self._servers: dict[str, asyncio.Server] = {}
        self._local_ports: dict[str, int] = {}
        self._configs: dict[str, SSHTunnel] = {}
        self._lock = asyncio.Lock()

    def _find_free_port(self) -> int:
        """Find a free local port for the tunnel."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _is_connection_alive(self, profile_name: str) -> bool:
        """Check if the local proxy server is still running."""
        if profile_name not in self._servers:
            return False
        return self._servers[profile_name].is_serving()

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

    async def open_tunnel(
        self, profile_name: str, config: SSHTunnel
    ) -> tuple[TunnelStatus, int | None, str | None]:
        """Open an SSH tunnel for a profile, reusing existing if available."""
        async with self._lock:
            if not config.enabled:
                await self._close_tunnel_internal(profile_name)
                return TunnelStatus.CLOSED, None, None

            if not config.host:
                return TunnelStatus.ERROR, None, "SSH host is required"

            # Check if we can reuse the existing tunnel
            if (
                profile_name in self._servers
                and self._is_connection_alive(profile_name)
                and not self._config_changed(profile_name, config)
            ):
                local_port = self._local_ports.get(profile_name)
                return TunnelStatus.OPEN, local_port, None

            # Need to create a new tunnel - close any existing one first
            await self._close_tunnel_internal(profile_name)

            try:
                local_port = config.local_port if config.local_port > 0 else self._find_free_port()

                # Verify connectivity with a quick nc -z test
                test_proc = await asyncio.create_subprocess_exec(
                    "ssh", config.host,
                    "nc", "-z", config.remote_host, str(config.remote_port),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stderr_bytes = b""
                    if test_proc.stderr:
                        stderr_bytes = await asyncio.wait_for(
                            test_proc.stderr.read(), timeout=15.0
                        )
                    await asyncio.wait_for(test_proc.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    test_proc.kill()
                    return TunnelStatus.ERROR, None, "SSH connection timed out"

                if test_proc.returncode != 0:
                    stderr_text = stderr_bytes.decode().strip()
                    error_msg = (
                        stderr_text
                        or f"Cannot reach {config.remote_host}:{config.remote_port}"
                          f" via {config.host}"
                    )
                    return TunnelStatus.ERROR, None, error_msg

                # Start local TCP proxy server
                ssh_host = config.host
                remote_host = config.remote_host
                remote_port = config.remote_port

                async def client_handler(
                    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
                ) -> None:
                    await _handle_client(reader, writer, ssh_host, remote_host, remote_port)

                server = await asyncio.start_server(
                    client_handler, "127.0.0.1", local_port
                )

                self._servers[profile_name] = server
                self._local_ports[profile_name] = local_port
                self._configs[profile_name] = config

                return TunnelStatus.OPEN, local_port, None

            except FileNotFoundError:
                return TunnelStatus.ERROR, None, "ssh command not found"
            except Exception as e:
                return TunnelStatus.ERROR, None, str(e) or repr(e)

    async def _close_tunnel_internal(self, profile_name: str) -> None:
        """Close tunnel without acquiring lock (internal use only)."""
        if profile_name in self._servers:
            server = self._servers[profile_name]
            server.close()
            await server.wait_closed()
            del self._servers[profile_name]

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
            for profile_name in list(self._servers.keys()):
                await self._close_tunnel_internal(profile_name)

    def get_local_port(self, profile_name: str) -> int | None:
        """Get the local port for a profile's tunnel."""
        return self._local_ports.get(profile_name)

    def is_tunnel_open(self, profile_name: str) -> bool:
        """Check if a tunnel is open for a profile."""
        return profile_name in self._servers and self._is_connection_alive(profile_name)

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
