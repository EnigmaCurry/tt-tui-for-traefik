"""Info view widget showing Traefik and TUI information."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static

from ..api import TraefikOverview, TraefikVersion

# Project URL
PROJECT_URL = "https://github.com/EnigmaCurry/tt-tui-for-traefik"


class InfoView(Vertical):
    """A widget displaying Traefik version, providers, features, and project info."""

    DEFAULT_CSS = """
    InfoView {
        height: 1fr;
        padding: 1 1;
    }

    InfoView #summary-bar {
        height: auto;
        padding: 0;
        margin-bottom: 0;
    }

    InfoView .section-header {
        text-style: bold;
        padding: 1 0 0 0;
    }

    InfoView .section-content {
        padding: 0 0 0 2;
    }

    InfoView .project-url {
        padding: 2 0 0 0;
        color: $accent;
    }

    InfoView .loading {
        padding: 2;
        color: $warning;
        text-align: center;
    }

    InfoView .error-message {
        padding: 2;
        color: $error;
        text-align: center;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._version: TraefikVersion | None = None
        self._overview: TraefikOverview | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="summary-bar")
        yield Label("Traefik Version", classes="section-header")
        yield Static("Loading...", id="version-content", classes="section-content")
        yield Label("Enabled Providers", classes="section-header")
        yield Static("Loading...", id="providers-content", classes="section-content")
        yield Label("Features", classes="section-header")
        yield Static("Loading...", id="features-content", classes="section-content")
        yield Static(f"{PROJECT_URL}", id="project-url", classes="project-url")

    def update_version(self, version: TraefikVersion) -> None:
        """Update the version display."""
        self._version = version
        content = self.query_one("#version-content", Static)
        version_text = version.version
        if version.codename:
            version_text += f" ({version.codename})"
        content.update(version_text)

    def update_overview(self, overview: TraefikOverview) -> None:
        """Update the providers and features display."""
        self._overview = overview

        # Update providers
        providers_content = self.query_one("#providers-content", Static)
        if overview.enabled_providers:
            providers_content.update(", ".join(sorted(overview.enabled_providers)))
        else:
            providers_content.update("None")

        # Update features
        features_content = self.query_one("#features-content", Static)
        if overview.enabled_features:
            feature_lines = []
            for key, value in sorted(overview.enabled_features.items()):
                # Format the value appropriately
                if isinstance(value, bool):
                    display_value = "Enabled" if value else "Disabled"
                elif value == "" or value is None:
                    display_value = "Disabled"
                else:
                    display_value = str(value)
                feature_lines.append(f"{key}:\t{display_value}")
            features_content.update("\n".join(feature_lines))
        else:
            features_content.update("None")

    def _format_summary_stats(self, stats: dict[str, int], label: str) -> str:
        """Format stats for the summary bar."""
        enabled = stats.get("enabled", 0)
        disabled = stats.get("disabled", 0)
        warning = stats.get("warning", 0)

        parts = [f"{label}:"]
        if enabled > 0:
            parts.append(f"[green]{enabled}✓[/]")
        if warning > 0:
            parts.append(f"[yellow]{warning}⚠[/]")
        if disabled > 0:
            parts.append(f"[red]{disabled}✗[/]")

        if len(parts) == 1:
            parts.append("0")

        return " ".join(parts)

    def update_summary(self, global_totals: dict[str, dict[str, int]]) -> None:
        """Update the summary bar with global totals."""
        summary_bar = self.query_one("#summary-bar", Static)

        router_totals = global_totals.get("routers", {})
        service_totals = global_totals.get("services", {})
        middleware_totals = global_totals.get("middlewares", {})

        parts = [
            self._format_summary_stats(router_totals, "Routers"),
            "  ",
            self._format_summary_stats(service_totals, "Services"),
            "  ",
            self._format_summary_stats(middleware_totals, "Middlewares"),
        ]

        summary_bar.update("".join(parts))

    def show_error(self, message: str) -> None:
        """Show an error state."""
        version_content = self.query_one("#version-content", Static)
        version_content.update(f"Error: {message}")
        providers_content = self.query_one("#providers-content", Static)
        providers_content.update("-")
        features_content = self.query_one("#features-content", Static)
        features_content.update("-")

    def show_loading(self) -> None:
        """Show a loading state."""
        summary_bar = self.query_one("#summary-bar", Static)
        summary_bar.update("Loading...")
        version_content = self.query_one("#version-content", Static)
        version_content.update("Loading...")
        providers_content = self.query_one("#providers-content", Static)
        providers_content.update("Loading...")
        features_content = self.query_one("#features-content", Static)
        features_content.update("Loading...")

    def clear(self) -> None:
        """Clear the display."""
        self._version = None
        self._overview = None
        summary_bar = self.query_one("#summary-bar", Static)
        summary_bar.update("-")
        version_content = self.query_one("#version-content", Static)
        version_content.update("-")
        providers_content = self.query_one("#providers-content", Static)
        providers_content.update("-")
        features_content = self.query_one("#features-content", Static)
        features_content.update("-")
