"""Data models for TT TUI configuration and state."""

from enum import Enum
from pathlib import Path
from typing import Self

import tomli
import tomli_w
from pydantic import BaseModel, Field, field_validator


class ConnectionStatus(str, Enum):
    """Connection status for a Traefik profile."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class BasicAuth(BaseModel):
    """Basic authentication credentials."""

    username: str = ""
    password: str = ""


class Profile(BaseModel):
    """A Traefik connection profile."""

    url: str = "http://localhost:8080"
    basic_auth: BasicAuth | None = None


class ProfileRuntime(BaseModel):
    """Runtime state for a profile (not persisted)."""

    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    version: str | None = None
    error: str | None = None


_VALID_TABS = frozenset({"entrypoints", "routers", "services", "middleware", "info", "settings"})


class Settings(BaseModel):
    """Application settings and profiles."""

    schema_version: int = 1
    selected_profile: str | None = None
    active_tab: str = "entrypoints"
    theme: str | None = None
    profiles: dict[str, Profile] = Field(default_factory=dict)

    @field_validator("active_tab")
    @classmethod
    def validate_active_tab(cls, v: str) -> str:
        """Ensure active_tab is a valid tab ID."""
        if v not in _VALID_TABS:
            return "entrypoints"
        return v

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the config file."""
        # Check for custom home directory
        import os

        if custom_home := os.environ.get("TT_LOCAL_HOME"):
            base = Path(custom_home)
        elif xdg_data := os.environ.get("XDG_DATA_HOME"):
            base = Path(xdg_data) / "tt-tui-for-traefik"
        else:
            base = Path.home() / ".local" / "share" / "tt-tui-for-traefik"

        base.mkdir(parents=True, exist_ok=True)
        return base / "config.toml"

    @classmethod
    def load(cls) -> Self:
        """Load settings from disk, or create default if not exists."""
        config_path = cls.get_config_path()
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomli.load(f)
            return cls.model_validate(data)
        # Create default settings with a default profile
        return cls(
            profiles={"default": Profile()},
            selected_profile="default",
        )

    def save(self) -> None:
        """Save settings to disk."""
        import os

        config_path = self.get_config_path()
        with open(config_path, "wb") as f:
            tomli_w.dump(self.model_dump(exclude_none=True), f)
        # Ensure restrictive permissions (0600) to protect credentials
        os.chmod(config_path, 0o600)

    def get_profile_key_from_url(self, url: str) -> str:
        """Generate a profile key from a URL."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return f"{host}:{port}"
        except Exception:
            return url

    def create_profile(self, name: str | None = None) -> str:
        """Create a new profile and return its key."""
        if name is None:
            # Generate a unique name
            base = "new-profile"
            counter = 1
            name = base
            while name in self.profiles:
                name = f"{base}-{counter}"
                counter += 1

        self.profiles[name] = Profile()
        self.selected_profile = name
        return name

    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name. Returns True if deleted."""
        if name in self.profiles:
            del self.profiles[name]
            if self.selected_profile == name:
                # Select another profile or None
                self.selected_profile = next(iter(self.profiles), None)
            return True
        return False

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Rename a profile. Returns True if successful."""
        if old_name not in self.profiles or new_name in self.profiles:
            return False
        self.profiles[new_name] = self.profiles.pop(old_name)
        if self.selected_profile == old_name:
            self.selected_profile = new_name
        return True
