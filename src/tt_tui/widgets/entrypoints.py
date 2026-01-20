"""Entrypoints view widget."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Label, Static

from ..api import Entrypoint, EntrypointDetail


class EntrypointDetailPane(Vertical):
    """A pane showing detailed entrypoint information."""

    DEFAULT_CSS = """
    EntrypointDetailPane {
        height: auto;
        max-height: 50%;
        border-top: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    EntrypointDetailPane .detail-header {
        text-style: bold;
        padding-bottom: 1;
    }

    EntrypointDetailPane .detail-content {
        height: auto;
    }
    """

    def __init__(self, detail: EntrypointDetail, **kwargs) -> None:
        super().__init__(**kwargs)
        self._detail = detail
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield Label("", id="detail-header", classes="detail-header")
        yield Static("", id="detail-content", classes="detail-content")

    def on_mount(self) -> None:
        """Update display after mounting."""
        self._update_display()

    def update_detail(self, detail: EntrypointDetail) -> None:
        """Update the detail content in place."""
        self._detail = detail
        self._update_display()

    def _update_display(self) -> None:
        """Update all display elements."""
        d = self._detail

        header = self.query_one("#detail-header", Label)
        header.update(f"Entrypoint: {d.name}")

        # Build content text
        lines = [
            f"Address:       {d.address}",
        ]

        if d.protocol:
            lines.append(f"Protocol:      {d.protocol}")

        if d.transport:
            tls = d.transport.get("tls")
            if tls:
                lines.append("TLS:           Enabled")
                if cert_resolver := tls.get("certResolver"):
                    lines.append(f"  Resolver:    {cert_resolver}")
                if domains := tls.get("domains"):
                    lines.append(f"  Domains:     {len(domains)} configured")
            if d.transport.get("respondingTimeouts"):
                lines.append("Timeouts:      configured")

        if d.forwarded_headers:
            insecure = d.forwarded_headers.get("insecure", False)
            trusted_ips = d.forwarded_headers.get("trustedIPs", [])
            if insecure:
                lines.append("Fwd Headers:   Insecure (trust all)")
            elif trusted_ips:
                lines.append(f"Fwd Headers:   {len(trusted_ips)} trusted IP(s)")

        if d.http:
            redirections = d.http.get("redirections")
            if redirections:
                entry_point = redirections.get("entryPoint", {})
                if to := entry_point.get("to"):
                    scheme = entry_point.get("scheme", "")
                    if scheme:
                        lines.append(f"Redirect:      -> {to} ({scheme})")
                    else:
                        lines.append(f"Redirect:      -> {to}")
            middlewares = d.http.get("middlewares")
            if middlewares:
                lines.append(f"Middlewares:   {', '.join(middlewares)}")
            tls_config = d.http.get("tls")
            if tls_config:
                lines.append("HTTP TLS:      Enabled")

        if d.udp:
            timeout = d.udp.get("timeout")
            if timeout:
                lines.append(f"UDP Timeout:   {timeout}")

        content = self.query_one("#detail-content", Static)
        content.update("\n".join(lines))


class EntrypointsView(Vertical):
    """A widget displaying entrypoints."""

    DEFAULT_CSS = """
    EntrypointsView {
        height: 1fr;
    }

    EntrypointsView DataTable {
        height: 1fr;
    }

    EntrypointsView .no-data {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    EntrypointsView .error-message {
        padding: 2;
        color: $error;
        text-align: center;
    }

    EntrypointsView .loading {
        padding: 2;
        color: $warning;
        text-align: center;
    }
    """

    class EntrypointSelected(Message):
        """Message sent when an entrypoint is selected for detail view."""

        def __init__(self, entrypoint_name: str) -> None:
            self.entrypoint_name = entrypoint_name
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entrypoints: list[Entrypoint] = []
        self._router_stats: dict[str, dict[str, int]] = {}
        self._service_stats: dict[str, dict[str, int]] = {}
        self._middleware_stats: dict[str, dict[str, int]] = {}
        self._detail_pane: EntrypointDetailPane | None = None
        self._selected_entrypoint: str | None = None

    def compose(self) -> ComposeResult:
        yield DataTable(id="entrypoints-table")

    def on_mount(self) -> None:
        """Set up the data table."""
        table = self.query_one("#entrypoints-table", DataTable)
        table.add_columns("Name", "Address", "Protocol", "Routers", "Services", "Middlewares")
        table.cursor_type = "row"

    def update_entrypoints(
        self,
        entrypoints: list[Entrypoint],
        router_stats: dict[str, dict[str, int]] | None = None,
        service_stats: dict[str, dict[str, int]] | None = None,
        middleware_stats: dict[str, dict[str, int]] | None = None,
    ) -> None:
        """Update the entrypoints table."""
        self._entrypoints = entrypoints
        self._router_stats = router_stats or {}
        self._service_stats = service_stats or {}
        self._middleware_stats = middleware_stats or {}
        self._update_table(entrypoints)

    def _format_stats(self, stats: dict[str, int]) -> str:
        """Format stats for display with color indicators."""
        enabled = stats.get("enabled", 0)
        disabled = stats.get("disabled", 0)
        warning = stats.get("warning", 0)

        parts = []
        if enabled > 0:
            parts.append(f"[green]{enabled}✓[/]")
        if warning > 0:
            parts.append(f"[yellow]{warning}⚠[/]")
        if disabled > 0:
            parts.append(f"[red]{disabled}✗[/]")

        return " ".join(parts) if parts else "-"

    def _update_table(self, entrypoints: list[Entrypoint]) -> None:
        """Update the table with data, preserving selection."""
        table = self.query_one("#entrypoints-table", DataTable)

        # Get current cursor position/key
        current_key = None
        if table.cursor_row is not None and table.row_count > 0:
            try:
                current_key = table.get_row_at(table.cursor_row)
            except Exception:
                pass

        # Build new data
        new_keys = {e.name for e in entrypoints}
        existing_keys = set(table.rows.keys())

        # Remove rows that no longer exist
        for key in existing_keys - new_keys:
            table.remove_row(key)

        # Update or add rows
        for entrypoint in entrypoints:
            router_info = self._format_stats(self._router_stats.get(entrypoint.name, {}))
            service_info = self._format_stats(self._service_stats.get(entrypoint.name, {}))
            middleware_info = self._format_stats(self._middleware_stats.get(entrypoint.name, {}))
            row_data = (
                entrypoint.name,
                entrypoint.address,
                entrypoint.protocol or "-",
                router_info,
                service_info,
                middleware_info,
            )

            if entrypoint.name in existing_keys:
                # Update existing row by removing and re-adding
                table.remove_row(entrypoint.name)
            # Add row
            table.add_row(*row_data, key=entrypoint.name)

        # Restore cursor position if possible
        if current_key and str(current_key) in new_keys:
            for idx, key in enumerate(table.rows.keys()):
                if key == current_key:
                    table.cursor_row = idx
                    break

    async def clear_table(self) -> None:
        """Clear the entrypoints table."""
        table = self.query_one("#entrypoints-table", DataTable)
        table.clear()
        self._entrypoints = []
        self._selected_entrypoint = None
        await self._close_detail_pane()

    def show_error(self, message: str) -> None:
        """Show an error state - don't clear existing data."""
        pass

    def show_loading(self) -> None:
        """Show a loading state - don't clear existing data for smoother updates."""
        pass

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle entrypoint row selection (Enter/click)."""
        if event.row_key is None:
            return

        entrypoint_name = str(event.row_key.value)
        self.post_message(self.EntrypointSelected(entrypoint_name))

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle cursor movement - auto-update detail if visible."""
        if self._detail_pane is None:
            return
        if event.row_key is None:
            return

        entrypoint_name = str(event.row_key.value)
        self.post_message(self.EntrypointSelected(entrypoint_name))

    async def show_detail(self, detail: EntrypointDetail) -> None:
        """Show the entrypoint detail pane."""
        # Track the selected entrypoint
        self._selected_entrypoint = detail.name

        if self._detail_pane is not None:
            # Update existing pane in place
            self._detail_pane.update_detail(detail)
        else:
            # Create new pane
            self._detail_pane = EntrypointDetailPane(detail)
            await self.mount(self._detail_pane)

    def get_selected_entrypoint(self) -> str | None:
        """Get the currently selected entrypoint name."""
        return self._selected_entrypoint

    def has_detail_open(self) -> bool:
        """Check if the detail pane is currently open."""
        return self._detail_pane is not None

    async def _close_detail_pane(self) -> None:
        """Close the detail pane if open."""
        # Remove all existing detail panes
        for pane in self.query(EntrypointDetailPane):
            await pane.remove()
        self._detail_pane = None
        self._selected_entrypoint = None
