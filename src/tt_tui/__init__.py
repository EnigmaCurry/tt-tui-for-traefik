"""TT TUI - A Textual-based TUI dashboard for Traefik."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tt-tui-for-traefik")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
