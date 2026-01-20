"""Middlewares view widget with HTTP/TCP sub-tabs."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Label, Static, TabbedContent, TabPane

from ..api import Middleware, MiddlewareDetail
from .routers import ClickableStatic, _status_emoji


class MiddlewareDetailPane(Vertical):
    """A pane showing detailed middleware information."""

    DEFAULT_CSS = """
    MiddlewareDetailPane {
        height: auto;
        max-height: 50%;
        border-top: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    MiddlewareDetailPane .detail-header {
        text-style: bold;
        padding-bottom: 1;
    }

    MiddlewareDetailPane .detail-content {
        height: auto;
    }

    MiddlewareDetailPane .detail-error {
        color: $error;
    }

    MiddlewareDetailPane .link {
        color: $accent;
        text-style: underline;
    }
    """

    def __init__(self, detail: MiddlewareDetail, **kwargs) -> None:
        super().__init__(**kwargs)
        self._detail = detail

    def compose(self) -> ComposeResult:
        yield Label("", id="detail-header", classes="detail-header")
        yield ClickableStatic("", id="detail-content", classes="detail-content")
        yield Static("", id="detail-errors", classes="detail-error")

    def on_mount(self) -> None:
        """Update display after mounting."""
        self._update_display()

    def update_detail(self, detail: MiddlewareDetail) -> None:
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
        header.update(f"Middleware: {d.name}")

        # Build content text
        lines = [
            f"Provider:      {d.provider}",
            f"Status:        {d.status}",
            f"Type:          {d.type or '-'}",
        ]

        if d.used_by:
            router_links = ", ".join(self._make_link("router", r) for r in d.used_by)
            lines.append(f"Used By:       {router_links}")

        if d.using:
            middleware_links = ", ".join(self._make_link("middleware", m) for m in d.using)
            lines.append(f"Using:         {middleware_links}")

        # Display type-specific configuration
        if d.config:
            lines.append("")
            lines.append("Configuration:")
            self._format_config(d.config, lines, indent=2)

        content = self.query_one("#detail-content", Static)
        content.update("\n".join(lines))

        errors = self.query_one("#detail-errors", Static)
        if d.error:
            errors.update(f"Errors:        {', '.join(d.error)}")
        else:
            errors.update("")

    def _format_config(self, config: dict, lines: list[str], indent: int = 0) -> None:
        """Format configuration dictionary for display."""
        prefix = " " * indent
        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                self._format_config(value, lines, indent + 2)
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    lines.append(f"{prefix}{key}:")
                    for item in value[:5]:  # Show first 5
                        self._format_config(item, lines, indent + 2)
                        lines.append(f"{prefix}  ---")
                    if len(value) > 5:
                        lines.append(f"{prefix}  ... and {len(value) - 5} more")
                else:
                    # Simple list
                    if len(value) <= 3:
                        lines.append(f"{prefix}{key}: {', '.join(str(v) for v in value)}")
                    else:
                        lines.append(f"{prefix}{key}: {', '.join(str(v) for v in value[:3])}...")
            else:
                lines.append(f"{prefix}{key}: {value}")


class MiddlewaresView(Vertical):
    """A widget displaying middlewares in sub-tabs for HTTP and TCP."""

    DEFAULT_CSS = """
    MiddlewaresView {
        height: 1fr;
    }

    MiddlewaresView > TabbedContent {
        height: 1fr;
    }

    MiddlewaresView DataTable {
        height: 1fr;
    }

    MiddlewaresView .status-enabled {
        color: $success;
    }

    MiddlewaresView .status-disabled {
        color: $error;
    }

    MiddlewaresView .no-data {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    MiddlewaresView .error-message {
        padding: 2;
        color: $error;
        text-align: center;
    }

    MiddlewaresView .loading {
        padding: 2;
        color: $warning;
        text-align: center;
    }
    """

    class MiddlewareSelected(Message):
        """Message sent when a middleware is selected for detail view."""

        def __init__(self, middleware_name: str, middleware_type: str) -> None:
            self.middleware_name = middleware_name
            self.middleware_type = middleware_type  # "http" or "tcp"
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http_middlewares: list[Middleware] = []
        self._tcp_middlewares: list[Middleware] = []
        self._detail_pane: MiddlewareDetailPane | None = None
        self._selected_middleware: str | None = None
        self._selected_middleware_type: str | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(id="middlewares-tabs", initial="http-middlewares"):
            with TabPane("HTTP", id="http-middlewares"):
                yield DataTable(id="http-mw-table")
            with TabPane("TCP", id="tcp-middlewares"):
                yield DataTable(id="tcp-mw-table")

    def on_mount(self) -> None:
        """Set up the data tables."""
        for table_id in ("http-mw-table", "tcp-mw-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.add_columns("Name", "Status", "Type", "Provider")
            table.cursor_type = "row"

    def update_http_middlewares(self, middlewares: list[Middleware]) -> None:
        """Update the HTTP middlewares table."""
        self._http_middlewares = middlewares
        self._update_table("http-mw-table", middlewares)

    def update_tcp_middlewares(self, middlewares: list[Middleware]) -> None:
        """Update the TCP middlewares table."""
        self._tcp_middlewares = middlewares
        self._update_table("tcp-mw-table", middlewares)

    def _update_table(self, table_id: str, middlewares: list[Middleware]) -> None:
        """Update a middleware table with data, preserving selection."""
        table = self.query_one(f"#{table_id}", DataTable)

        # Get current cursor position/key
        current_key = None
        if table.cursor_row is not None and table.row_count > 0:
            try:
                current_key = table.get_row_at(table.cursor_row)
            except Exception:
                pass

        # Build new data
        new_keys = {m.name for m in middlewares}
        existing_keys = set(table.rows.keys())

        # Remove rows that no longer exist
        for key in existing_keys - new_keys:
            table.remove_row(key)

        # Update or add rows
        for middleware in middlewares:
            row_data = (
                middleware.name,
                _status_emoji(middleware.status),
                middleware.type or "-",
                middleware.provider,
            )

            if middleware.name in existing_keys:
                # Update existing row by removing and re-adding
                table.remove_row(middleware.name)
            table.add_row(*row_data, key=middleware.name)

        # Restore cursor position if possible
        if current_key and str(current_key) in new_keys:
            for idx, key in enumerate(table.rows.keys()):
                if key == current_key:
                    table.cursor_row = idx
                    break

    async def clear_tables(self) -> None:
        """Clear all middleware tables."""
        for table_id in ("http-mw-table", "tcp-mw-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear()
        self._http_middlewares = []
        self._tcp_middlewares = []
        self._selected_middleware = None
        self._selected_middleware_type = None
        await self._close_detail_pane()

    def show_error(self, message: str) -> None:
        """Show an error state - don't clear existing data."""
        pass

    def show_loading(self) -> None:
        """Show a loading state - don't clear existing data for smoother updates."""
        pass

    def _get_active_middleware_type(self) -> str:
        """Get the currently active middleware type based on the selected tab."""
        tabs = self.query_one("#middlewares-tabs", TabbedContent)
        active_id = tabs.active
        if active_id == "tcp-middlewares":
            return "tcp"
        return "http"

    @on(TabbedContent.TabActivated)
    async def on_sub_tab_changed(self, event: TabbedContent.TabActivated) -> None:
        """Handle sub-tab changes - dismiss detail pane."""
        # Only respond to our own sub-tabs
        if event.tabbed_content.id == "middlewares-tabs":
            await self._close_detail_pane()
            event.stop()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle middleware row selection (Enter/click)."""
        if event.row_key is None:
            return

        middleware_name = str(event.row_key.value)
        middleware_type = self._get_active_middleware_type()
        self.post_message(self.MiddlewareSelected(middleware_name, middleware_type))

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle cursor movement - auto-update detail if visible."""
        if self._detail_pane is None:
            return
        if event.row_key is None:
            return

        # Determine middleware type from the table that fired the event
        table_id = event.control.id
        if table_id == "http-mw-table":
            middleware_type = "http"
        elif table_id == "tcp-mw-table":
            middleware_type = "tcp"
        else:
            return

        # Only handle events from the active tab's table
        if middleware_type != self._get_active_middleware_type():
            return

        middleware_name = str(event.row_key.value)
        self.post_message(self.MiddlewareSelected(middleware_name, middleware_type))

    async def show_detail(self, detail: MiddlewareDetail) -> None:
        """Show the middleware detail pane."""
        # Track the selected middleware
        self._selected_middleware = detail.name
        self._selected_middleware_type = self._get_active_middleware_type()

        if self._detail_pane is not None:
            # Update existing pane in place
            self._detail_pane.update_detail(detail)
        else:
            # Create new pane
            self._detail_pane = MiddlewareDetailPane(detail)
            await self.mount(self._detail_pane)

    def get_selected_middleware(self) -> tuple[str | None, str | None]:
        """Get the currently selected middleware name and type."""
        return self._selected_middleware, self._selected_middleware_type

    def has_detail_open(self) -> bool:
        """Check if the detail pane is currently open."""
        return self._detail_pane is not None

    async def _close_detail_pane(self) -> None:
        """Close the detail pane if open."""
        # Remove all existing detail panes
        for pane in self.query(MiddlewareDetailPane):
            await pane.remove()
        self._detail_pane = None
        self._selected_middleware = None
        self._selected_middleware_type = None
