"""Services view widget with HTTP/TCP/UDP sub-tabs."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Label, Static, TabbedContent, TabPane

from ..api import Service, ServiceDetail
from .routers import ClickableStatic, _status_emoji


class ServiceDetailPane(Vertical):
    """A pane showing detailed service information."""

    DEFAULT_CSS = """
    ServiceDetailPane {
        height: auto;
        max-height: 50%;
        border-top: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    ServiceDetailPane .detail-header {
        text-style: bold;
        padding-bottom: 1;
    }

    ServiceDetailPane .detail-content {
        height: auto;
    }

    ServiceDetailPane .detail-error {
        color: $error;
    }

    ServiceDetailPane .link {
        color: $accent;
        text-style: underline;
    }
    """

    def __init__(self, detail: ServiceDetail, **kwargs) -> None:
        super().__init__(**kwargs)
        self._detail = detail

    def compose(self) -> ComposeResult:
        yield Label("", id="detail-header", classes="detail-header")
        yield ClickableStatic("", id="detail-content", classes="detail-content")
        yield Static("", id="detail-errors", classes="detail-error")

    def on_mount(self) -> None:
        """Update display after mounting."""
        self._update_display()

    def update_detail(self, detail: ServiceDetail) -> None:
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
        header.update(f"Service: {d.name}")

        # Build content text
        lines = [
            f"Provider:      {d.provider}",
            f"Status:        {d.status}",
            f"Type:          {d.type or '-'}",
        ]

        if d.servers_status:
            servers_info = ", ".join(f"{k}: {v}" for k, v in d.servers_status.items())
            lines.append(f"Servers:       {servers_info}")

        if d.load_balancer:
            servers = d.load_balancer.get("servers", [])
            if servers:
                lines.append(f"Load Balancer: {len(servers)} server(s)")
                for _, server in enumerate(servers[:5]):  # Show first 5
                    url = server.get("url", server.get("address", "unknown"))
                    lines.append(f"  - {url}")
                if len(servers) > 5:
                    lines.append(f"  ... and {len(servers) - 5} more")

        if d.weighted:
            services = d.weighted.get("services", [])
            lines.append(f"Weighted:      {len(services)} service(s)")

        if d.mirroring:
            lines.append(f"Mirroring:     {d.mirroring.get('service', '-')}")

        if d.failover:
            lines.append(f"Failover:      {d.failover.get('service', '-')}")

        if d.used_by:
            router_links = ", ".join(self._make_link("router", r) for r in d.used_by)
            lines.append(f"Used By:       {router_links}")

        if d.using:
            lines.append(f"Using:         {', '.join(d.using)}")

        content = self.query_one("#detail-content", Static)
        content.update("\n".join(lines))

        errors = self.query_one("#detail-errors", Static)
        if d.error:
            errors.update(f"Errors:        {', '.join(d.error)}")
        else:
            errors.update("")


class ServicesView(Vertical):
    """A widget displaying services in sub-tabs for HTTP, TCP, and UDP."""

    DEFAULT_CSS = """
    ServicesView {
        height: 1fr;
    }

    ServicesView > TabbedContent {
        height: 1fr;
    }

    ServicesView DataTable {
        height: 1fr;
    }

    ServicesView .status-enabled {
        color: $success;
    }

    ServicesView .status-disabled {
        color: $error;
    }

    ServicesView .no-data {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    ServicesView .error-message {
        padding: 2;
        color: $error;
        text-align: center;
    }

    ServicesView .loading {
        padding: 2;
        color: $warning;
        text-align: center;
    }
    """

    class ServiceSelected(Message):
        """Message sent when a service is selected for detail view."""

        def __init__(self, service_name: str, service_type: str) -> None:
            self.service_name = service_name
            self.service_type = service_type  # "http", "tcp", or "udp"
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http_services: list[Service] = []
        self._tcp_services: list[Service] = []
        self._udp_services: list[Service] = []
        self._detail_pane: ServiceDetailPane | None = None
        self._selected_service: str | None = None
        self._selected_service_type: str | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(id="services-tabs", initial="http-services"):
            with TabPane("HTTP", id="http-services"):
                yield DataTable(id="http-svc-table")
            with TabPane("TCP", id="tcp-services"):
                yield DataTable(id="tcp-svc-table")
            with TabPane("UDP", id="udp-services"):
                yield DataTable(id="udp-svc-table")

    def on_mount(self) -> None:
        """Set up the data tables."""
        for table_id in ("http-svc-table", "tcp-svc-table", "udp-svc-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.add_columns("Name", "Status", "Type", "Servers")
            table.cursor_type = "row"

    def update_http_services(self, services: list[Service]) -> None:
        """Update the HTTP services table."""
        self._http_services = services
        self._update_table("http-svc-table", services)

    def update_tcp_services(self, services: list[Service]) -> None:
        """Update the TCP services table."""
        self._tcp_services = services
        self._update_table("tcp-svc-table", services)

    def update_udp_services(self, services: list[Service]) -> None:
        """Update the UDP services table."""
        self._udp_services = services
        self._update_table("udp-svc-table", services)

    def _update_table(self, table_id: str, services: list[Service]) -> None:
        """Update a service table with data, preserving selection."""
        table = self.query_one(f"#{table_id}", DataTable)

        # Get current cursor position/key
        current_key = None
        if table.cursor_row is not None and table.row_count > 0:
            try:
                current_key = table.get_row_at(table.cursor_row)
            except Exception:
                pass

        # Build new data
        new_keys = {s.name for s in services}
        existing_keys = set(table.rows.keys())

        # Remove rows that no longer exist
        for key in existing_keys - new_keys:
            table.remove_row(key)

        # Update or add rows
        for service in services:
            servers_count = "-"
            if service.servers_status:
                servers_count = str(len(service.servers_status))
            row_data = (
                service.name,
                _status_emoji(service.status),
                service.type or "-",
                servers_count,
            )

            if service.name in existing_keys:
                # Update existing row by removing and re-adding
                table.remove_row(service.name)
            table.add_row(*row_data, key=service.name)

        # Restore cursor position if possible
        if current_key and str(current_key) in new_keys:
            for idx, key in enumerate(table.rows.keys()):
                if key == current_key:
                    table.cursor_row = idx
                    break

    async def clear_tables(self) -> None:
        """Clear all service tables."""
        for table_id in ("http-svc-table", "tcp-svc-table", "udp-svc-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear()
        self._http_services = []
        self._tcp_services = []
        self._udp_services = []
        self._selected_service = None
        self._selected_service_type = None
        await self._close_detail_pane()

    def show_error(self, message: str) -> None:
        """Show an error state - don't clear existing data."""
        pass

    def show_loading(self) -> None:
        """Show a loading state - don't clear existing data for smoother updates."""
        pass

    def _get_active_service_type(self) -> str:
        """Get the currently active service type based on the selected tab."""
        tabs = self.query_one("#services-tabs", TabbedContent)
        active_id = tabs.active
        if active_id == "tcp-services":
            return "tcp"
        elif active_id == "udp-services":
            return "udp"
        return "http"

    @on(TabbedContent.TabActivated)
    async def on_sub_tab_changed(self, event: TabbedContent.TabActivated) -> None:
        """Handle sub-tab changes - dismiss detail pane."""
        # Only respond to our own sub-tabs
        if event.tabbed_content.id == "services-tabs":
            await self._close_detail_pane()
            event.stop()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle service row selection (Enter/click)."""
        if event.row_key is None:
            return

        service_name = str(event.row_key.value)
        service_type = self._get_active_service_type()
        self.post_message(self.ServiceSelected(service_name, service_type))

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle cursor movement - auto-update detail if visible."""
        if self._detail_pane is None:
            return
        if event.row_key is None:
            return

        # Determine service type from the table that fired the event
        table_id = event.control.id
        if table_id == "http-svc-table":
            service_type = "http"
        elif table_id == "tcp-svc-table":
            service_type = "tcp"
        elif table_id == "udp-svc-table":
            service_type = "udp"
        else:
            return

        # Only handle events from the active tab's table
        if service_type != self._get_active_service_type():
            return

        service_name = str(event.row_key.value)
        self.post_message(self.ServiceSelected(service_name, service_type))

    async def show_detail(self, detail: ServiceDetail) -> None:
        """Show the service detail pane."""
        # Track the selected service
        self._selected_service = detail.name
        self._selected_service_type = self._get_active_service_type()

        if self._detail_pane is not None:
            # Update existing pane in place
            self._detail_pane.update_detail(detail)
        else:
            # Create new pane
            self._detail_pane = ServiceDetailPane(detail)
            await self.mount(self._detail_pane)

    def get_selected_service(self) -> tuple[str | None, str | None]:
        """Get the currently selected service name and type."""
        return self._selected_service, self._selected_service_type

    def has_detail_open(self) -> bool:
        """Check if the detail pane is currently open."""
        return self._detail_pane is not None

    async def _close_detail_pane(self) -> None:
        """Close the detail pane if open."""
        # Remove all existing detail panes
        for pane in self.query(ServiceDetailPane):
            await pane.remove()
        self._detail_pane = None
        self._selected_service = None
        self._selected_service_type = None
