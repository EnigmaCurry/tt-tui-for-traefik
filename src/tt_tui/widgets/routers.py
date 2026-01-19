"""Routers view widget with HTTP/TCP/UDP sub-tabs."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Label, Static, TabbedContent, TabPane

from ..api import Router


class RoutersView(Vertical):
    """A widget displaying routers in sub-tabs for HTTP, TCP, and UDP."""

    DEFAULT_CSS = """
    RoutersView {
        height: 1fr;
    }

    RoutersView TabbedContent {
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

    def compose(self) -> ComposeResult:
        with TabbedContent():
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
        self._update_table("http-table", routers)

    def update_tcp_routers(self, routers: list[Router]) -> None:
        """Update the TCP routers table."""
        self._update_table("tcp-table", routers)

    def update_udp_routers(self, routers: list[Router]) -> None:
        """Update the UDP routers table."""
        self._update_table("udp-table", routers)

    def _update_table(self, table_id: str, routers: list[Router]) -> None:
        """Update a router table with data."""
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear()

        for router in routers:
            status_text = router.status
            entry_points = ", ".join(router.entry_points) if router.entry_points else "-"
            table.add_row(
                router.name,
                status_text,
                router.rule or "-",
                router.service or "-",
                entry_points,
            )

    def clear_tables(self) -> None:
        """Clear all router tables."""
        for table_id in ("http-table", "tcp-table", "udp-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear()

    def show_error(self, message: str) -> None:
        """Show an error state in all tables."""
        self.clear_tables()

    def show_loading(self) -> None:
        """Show a loading state."""
        self.clear_tables()
