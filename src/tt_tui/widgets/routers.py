"""Routers view widget with HTTP/TCP/UDP sub-tabs."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Label, Static, TabbedContent, TabPane

from ..api import Router, RouterDetail


def _status_emoji(status: str) -> str:
    """Convert status string to emoji indicator."""
    status_lower = status.lower() if status else ""
    if status_lower == "enabled":
        return "✅"
    elif status_lower == "disabled":
        return "❌"
    elif status_lower == "warning":
        return "⚠️"
    return status  # Return original if unknown


class NavigateLink(Message):
    """Message to request navigation to a resource link."""

    def __init__(self, link: str) -> None:
        self.link = link
        super().__init__()


class ClickableStatic(Static):
    """A Static widget that can handle action link clicks."""

    def action_navigate_link(self, link: str) -> None:
        """Handle navigation link clicks."""
        self.post_message(NavigateLink(link))


class RouterDetailPane(Vertical):
    """A pane showing detailed router information."""

    DEFAULT_CSS = """
    RouterDetailPane {
        height: auto;
        max-height: 50%;
        border-top: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    RouterDetailPane .detail-header {
        text-style: bold;
        padding-bottom: 1;
    }

    RouterDetailPane .detail-content {
        height: auto;
    }

    RouterDetailPane .detail-error {
        color: $error;
    }

    RouterDetailPane .link {
        color: $accent;
        text-style: underline;
    }
    """

    def __init__(self, detail: RouterDetail, **kwargs) -> None:
        super().__init__(**kwargs)
        self._detail = detail

    def compose(self) -> ComposeResult:
        yield Label("", id="detail-header", classes="detail-header")
        yield ClickableStatic("", id="detail-content", classes="detail-content")
        yield Static("", id="detail-errors", classes="detail-error")

    def on_mount(self) -> None:
        """Update display after mounting."""
        self._update_display()

    def update_detail(self, detail: RouterDetail) -> None:
        """Update the detail content in place."""
        self._detail = detail
        self._update_display()

    def _make_link(self, resource_type: str, name: str) -> str:
        """Create a clickable link markup for a resource."""
        link = f"{resource_type}#{name}"
        return f'[@click=navigate_link("{link}")]<{name}>[/]'

    def _update_display(self) -> None:
        """Update all display elements."""
        d = self._detail

        header = self.query_one("#detail-header", Label)
        header.update(f"Router: {d.name}")

        # Build content text
        service_link = self._make_link("service", d.service) if d.service else "-"
        lines = [
            f"Provider:      {d.provider}",
            f"Status:        {d.status}",
            f"Rule:          {d.rule or '-'}",
            f"Service:       {service_link}",
            f"Entry Points:  {', '.join(d.entry_points) if d.entry_points else '-'}",
            f"Priority:      {d.priority}",
        ]

        if d.middlewares:
            middleware_links = ", ".join(self._make_link("middleware", m) for m in d.middlewares)
            lines.append(f"Middlewares:   {middleware_links}")

        if d.tls:
            tls_info = "Enabled"
            if isinstance(d.tls, dict):
                if cert_resolver := d.tls.get("certResolver"):
                    tls_info = f"Enabled (resolver: {cert_resolver})"
                elif domains := d.tls.get("domains"):
                    tls_info = f"Enabled ({len(domains)} domain(s))"
            lines.append(f"TLS:           {tls_info}")

        if d.using:
            lines.append(f"Using:         {', '.join(d.using)}")

        content = self.query_one("#detail-content", Static)
        content.update("\n".join(lines))

        errors = self.query_one("#detail-errors", Static)
        if d.error:
            errors.update(f"Errors:        {', '.join(d.error)}")
        else:
            errors.update("")


class RoutersView(Vertical):
    """A widget displaying routers in sub-tabs for HTTP, TCP, and UDP."""

    DEFAULT_CSS = """
    RoutersView {
        height: 1fr;
    }

    RoutersView > TabbedContent {
        height: 1fr;
    }

    RoutersView DataTable {
        height: 1fr;
    }

    RoutersView .status-enabled {
        color: $success;
    }

    RoutersView .status-disabled {
        color: $error;
    }

    RoutersView .no-data {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    RoutersView .error-message {
        padding: 2;
        color: $error;
        text-align: center;
    }

    RoutersView .loading {
        padding: 2;
        color: $warning;
        text-align: center;
    }
    """

    class RouterSelected(Message):
        """Message sent when a router is selected for detail view."""

        def __init__(self, router_name: str, router_type: str) -> None:
            self.router_name = router_name
            self.router_type = router_type  # "http", "tcp", or "udp"
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http_routers: list[Router] = []
        self._tcp_routers: list[Router] = []
        self._udp_routers: list[Router] = []
        self._detail_pane: RouterDetailPane | None = None
        self._selected_router: str | None = None
        self._selected_router_type: str | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(id="routers-tabs", initial="http-routers"):
            with TabPane("HTTP", id="http-routers"):
                yield DataTable(id="http-table")
            with TabPane("TCP", id="tcp-routers"):
                yield DataTable(id="tcp-table")
            with TabPane("UDP", id="udp-routers"):
                yield DataTable(id="udp-table")

    def on_mount(self) -> None:
        """Set up the data tables."""
        for table_id in ("http-table", "tcp-table", "udp-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.add_columns("Name", "Status", "Rule", "Service", "Entry Points")
            table.cursor_type = "row"

    def update_http_routers(self, routers: list[Router]) -> None:
        """Update the HTTP routers table."""
        self._http_routers = routers
        self._update_table("http-table", routers)

    def update_tcp_routers(self, routers: list[Router]) -> None:
        """Update the TCP routers table."""
        self._tcp_routers = routers
        self._update_table("tcp-table", routers)

    def update_udp_routers(self, routers: list[Router]) -> None:
        """Update the UDP routers table."""
        self._udp_routers = routers
        self._update_table("udp-table", routers)

    def _update_table(self, table_id: str, routers: list[Router]) -> None:
        """Update a router table with data, preserving selection."""
        table = self.query_one(f"#{table_id}", DataTable)

        # Get current cursor position/key
        current_key = None
        if table.cursor_row is not None and table.row_count > 0:
            try:
                current_key = table.get_row_at(table.cursor_row)
            except Exception:
                pass

        # Build new data
        new_keys = {r.name for r in routers}
        existing_keys = set(table.rows.keys())

        # Remove rows that no longer exist
        for key in existing_keys - new_keys:
            table.remove_row(key)

        # Update or add rows
        for router in routers:
            status_text = _status_emoji(router.status)
            if router.tls:
                status_text = f"{status_text}🔒"
            entry_points = ", ".join(router.entry_points) if router.entry_points else "-"
            row_data = (
                router.name,
                status_text,
                router.rule or "-",
                router.service or "-",
                entry_points,
            )

            if router.name in existing_keys:
                # Update existing row by removing and re-adding
                table.remove_row(router.name)
            table.add_row(*row_data, key=router.name)

        # Restore cursor position if possible
        if current_key and str(current_key) in new_keys:
            # Find the row index for the key
            for idx, key in enumerate(table.rows.keys()):
                if key == current_key:
                    table.cursor_row = idx
                    break

    async def clear_tables(self) -> None:
        """Clear all router tables."""
        for table_id in ("http-table", "tcp-table", "udp-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear()
        self._http_routers = []
        self._tcp_routers = []
        self._udp_routers = []
        self._selected_router = None
        self._selected_router_type = None
        await self._close_detail_pane()

    def show_error(self, message: str) -> None:
        """Show an error state - don't clear existing data."""
        pass

    def show_loading(self) -> None:
        """Show a loading state - don't clear existing data for smoother updates."""
        pass

    def _get_active_router_type(self) -> str:
        """Get the currently active router type based on the selected tab."""
        tabs = self.query_one("#routers-tabs", TabbedContent)
        active_id = tabs.active
        if active_id == "tcp-routers":
            return "tcp"
        elif active_id == "udp-routers":
            return "udp"
        return "http"

    @on(TabbedContent.TabActivated)
    async def on_sub_tab_changed(self, event: TabbedContent.TabActivated) -> None:
        """Handle sub-tab changes - dismiss detail pane."""
        # Only respond to our own sub-tabs
        if event.tabbed_content.id == "routers-tabs":
            await self._close_detail_pane()
            event.stop()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle router row selection (Enter/click)."""
        if event.row_key is None:
            return

        router_name = str(event.row_key.value)
        router_type = self._get_active_router_type()
        self.post_message(self.RouterSelected(router_name, router_type))

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle cursor movement - auto-update detail if visible."""
        if self._detail_pane is None:
            return
        if event.row_key is None:
            return

        # Determine router type from the table that fired the event
        table_id = event.control.id
        if table_id == "http-table":
            router_type = "http"
        elif table_id == "tcp-table":
            router_type = "tcp"
        elif table_id == "udp-table":
            router_type = "udp"
        else:
            return

        # Only handle events from the active tab's table
        if router_type != self._get_active_router_type():
            return

        router_name = str(event.row_key.value)
        self.post_message(self.RouterSelected(router_name, router_type))

    async def show_detail(self, detail: RouterDetail) -> None:
        """Show the router detail pane."""
        # Track the selected router
        self._selected_router = detail.name
        self._selected_router_type = self._get_active_router_type()

        if self._detail_pane is not None:
            # Update existing pane in place
            self._detail_pane.update_detail(detail)
        else:
            # Create new pane
            self._detail_pane = RouterDetailPane(detail)
            await self.mount(self._detail_pane)

    def get_selected_router(self) -> tuple[str | None, str | None]:
        """Get the currently selected router name and type."""
        return self._selected_router, self._selected_router_type

    def has_detail_open(self) -> bool:
        """Check if the detail pane is currently open."""
        return self._detail_pane is not None

    async def _close_detail_pane(self) -> None:
        """Close the detail pane if open."""
        # Remove all existing detail panes
        for pane in self.query(RouterDetailPane):
            await pane.remove()
        self._detail_pane = None
        self._selected_router = None
        self._selected_router_type = None
