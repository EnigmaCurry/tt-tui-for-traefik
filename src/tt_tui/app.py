"""Main TT TUI application."""

import argparse
from dataclasses import dataclass
from enum import Enum

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    Static,
    Tab,
    TabbedContent,
    TabPane,
    Tabs,
)

from .api import Middleware, Service, TraefikAPI, TraefikAPIError
from .models import ConnectionStatus, Profile, ProfileRuntime, Settings
from .monitor import check_connection
from .widgets import (
    EntrypointsView,
    MiddlewaresView,
    NavigateLink,
    ProfileEditor,
    ProfileList,
    RoutersView,
    ServicesView,
)


class ThemeProviderWithIndicator(Provider):
    """A theme provider that marks the current theme with an asterisk."""

    async def discover(self) -> Hits:
        """Show all themes when command palette opens."""
        current_theme = self.app.theme

        for theme_name in sorted(self.app.available_themes):
            if theme_name == current_theme:
                display = f"* {theme_name}"
            else:
                display = f"  {theme_name}"

            yield Hit(
                1,
                display,
                lambda name=theme_name: self._set_theme(name),
            )

    async def search(self, query: str) -> Hits:
        """Search for themes, marking the current one."""
        matcher = self.matcher(query)
        current_theme = self.app.theme

        for theme_name in self.app.available_themes:
            match = matcher.match(theme_name)
            if match > 0:
                if theme_name == current_theme:
                    display = f"* {theme_name}"
                else:
                    display = f"  {theme_name}"

                yield Hit(
                    match,
                    matcher.highlight(display),
                    lambda name=theme_name: self._set_theme(name),
                )

    def _set_theme(self, theme_name: str) -> None:
        """Set the application theme."""
        self.app.theme = theme_name


class ApiStatus(str, Enum):
    """Status of API calls."""

    IDLE = "idle"
    LOADING = "loading"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class DeepLink:
    """A deep link to a specific resource."""

    resource_type: str  # entrypoint, router, service, middleware
    resource_name: str
    protocol: str = "http"  # http, tcp, udp (for routers/services/middlewares)

    @classmethod
    def parse(cls, link: str) -> "DeepLink | None":
        """Parse a deep link string like 'entrypoint#websecure' or 'router:tcp#myrouter'."""
        if "#" not in link:
            return None

        type_part, name = link.split("#", 1)
        if not name:
            return None

        # Check for protocol specifier (e.g., router:tcp)
        if ":" in type_part:
            resource_type, protocol = type_part.split(":", 1)
        else:
            resource_type = type_part
            protocol = "http"

        valid_types = {"entrypoint", "router", "service", "middleware"}
        if resource_type not in valid_types:
            return None

        return cls(resource_type=resource_type, resource_name=name, protocol=protocol)


class StatusIndicator(Static):
    """A status indicator showing API call status."""

    DEFAULT_CSS = """
    StatusIndicator {
        width: 3;
        height: 1;
    }

    StatusIndicator.idle {
        color: #6c7086;
    }

    StatusIndicator.loading {
        color: white;
    }

    StatusIndicator.success {
        color: #a6e3a1;
    }

    StatusIndicator.error {
        color: #f38ba8;
    }
    """

    status: reactive[ApiStatus] = reactive(ApiStatus.IDLE)

    def __init__(self, **kwargs) -> None:
        super().__init__(" ● ", **kwargs)
        self.add_class("idle")

    def watch_status(self, status: ApiStatus) -> None:
        """Update appearance when status changes."""
        self.remove_class("loading", "success", "error", "idle")
        self.add_class(status.value)


class TitleBar(Horizontal):
    """Custom title bar showing status indicator, profile name, and connection status."""

    DEFAULT_CSS = """
    TitleBar {
        dock: top;
        width: 100%;
        height: 1;
        background: $primary;
    }

    TitleBar #title-profile {
        width: auto;
        padding: 0 1;
    }

    TitleBar #title-status {
        width: auto;
        color: $text;
    }

    TitleBar #title-status.connected {
        color: #a6e3a1;
    }

    TitleBar #title-status.disconnected {
        color: #f38ba8;
    }

    TitleBar #title-status.error {
        color: #f38ba8;
    }

    TitleBar #title-status.connecting {
        color: #f9e2af;
    }
    """

    def compose(self) -> ComposeResult:
        yield StatusIndicator(id="status-indicator")
        yield Static("No profile", id="title-profile")
        yield Static(" :: Disconnected", id="title-status")

    def update_profile(self, profile_name: str | None) -> None:
        """Update the displayed profile name."""
        label = self.query_one("#title-profile", Static)
        label.update(profile_name or "No profile")

    def update_connection_status(self, status: ConnectionStatus, error: str | None = None) -> None:
        """Update the connection status display."""
        status_label = self.query_one("#title-status", Static)
        status_label.remove_class("connected", "disconnected", "error", "connecting")

        if status == ConnectionStatus.CONNECTED:
            status_label.update(" :: Connected")
            status_label.add_class("connected")
        elif status == ConnectionStatus.CONNECTING:
            status_label.update(" :: Connecting...")
            status_label.add_class("connecting")
        elif status == ConnectionStatus.ERROR and error:
            status_label.update(f" :: {error}")
            status_label.add_class("error")
        else:
            status_label.update(" :: Disconnected")
            status_label.add_class("disconnected")


class ConfirmDialog(ModalScreen[bool]):
    """A confirmation dialog modal."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    ConfirmDialog > Vertical {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    ConfirmDialog .dialog-title {
        text-style: bold;
        padding-bottom: 1;
    }

    ConfirmDialog .dialog-message {
        padding-bottom: 1;
    }

    ConfirmDialog Horizontal {
        align: center middle;
        height: auto;
        padding-top: 1;
    }

    ConfirmDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="dialog-title")
            yield Label(self._message, classes="dialog-message")
            with Horizontal():
                yield Button("Yes", variant="error", id="yes-btn")
                yield Button("No", variant="primary", id="no-btn")

    @on(Button.Pressed, "#yes-btn")
    def on_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def on_no(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class InputDialog(ModalScreen[str | None]):
    """A dialog modal with text input."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }

    InputDialog > Vertical {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    InputDialog .dialog-title {
        text-style: bold;
        padding-bottom: 1;
    }

    InputDialog Input {
        margin-bottom: 1;
    }

    InputDialog Horizontal {
        align: center middle;
        height: auto;
        padding-top: 1;
    }

    InputDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, initial_value: str = "") -> None:
        super().__init__()
        self._title = title
        self._initial_value = initial_value

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="dialog-title")
            yield Input(value=self._initial_value, id="input-field")
            with Horizontal():
                yield Button("OK", variant="primary", id="ok-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

    @on(Input.Submitted, "#input-field")
    def on_input_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#ok-btn")
    def on_ok(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_btn(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#input-field", Input).value.strip()
        if value:
            self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


@dataclass
class SearchResult:
    """A search result item."""

    resource_type: str  # entrypoint, router, service, middleware
    protocol: str  # http, tcp, udp, or empty for entrypoints
    name: str
    extra_info: str = ""  # type for services/middlewares, rule for routers

    @property
    def display_type(self) -> str:
        """Get display string for the type."""
        if self.protocol and self.resource_type != "entrypoint":
            return f"{self.resource_type}:{self.protocol}"
        return self.resource_type

    @property
    def display_info(self) -> str:
        """Get display string with extra info."""
        if self.extra_info:
            # Truncate long rules
            info = self.extra_info[:40] + "..." if len(self.extra_info) > 40 else self.extra_info
            return info
        return ""

    def matches(self, query: str) -> bool:
        """Check if this result matches the search query."""
        query = query.lower()
        return (
            query in self.name.lower()
            or query in self.extra_info.lower()
            or query in self.resource_type.lower()
            or query in self.protocol.lower()
        )

    def to_deep_link(self) -> DeepLink:
        """Convert to a DeepLink."""
        return DeepLink(
            resource_type=self.resource_type,
            resource_name=self.name,
            protocol=self.protocol or "http",
        )


class SearchModal(ModalScreen[DeepLink | None]):
    """A search modal for finding resources."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }

    SearchModal > Vertical {
        width: 80;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    SearchModal .search-title {
        text-style: bold;
        padding-bottom: 1;
    }

    SearchModal Input {
        margin-bottom: 1;
    }

    SearchModal DataTable {
        height: auto;
        max-height: 20;
    }

    SearchModal .no-results {
        color: $text-muted;
        text-align: center;
        padding: 1;
    }

    SearchModal .result-type {
        color: $accent;
    }
    """

    def __init__(self, results: list[SearchResult]) -> None:
        super().__init__()
        self._all_results = results
        self._filtered_results: list[SearchResult] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Search Resources", classes="search-title")
            yield Input(placeholder="Type to search...", id="search-input")
            yield DataTable(id="search-results")
            yield Label("No results", id="no-results", classes="no-results")

    def on_mount(self) -> None:
        """Set up the search modal."""
        table = self.query_one("#search-results", DataTable)
        table.add_columns("Type", "Name", "Info")
        table.cursor_type = "row"
        table.display = False

        no_results = self.query_one("#no-results", Label)
        no_results.display = False

        # Focus the input
        self.query_one("#search-input", Input).focus()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Filter results as the user types."""
        query = event.value.strip()
        table = self.query_one("#search-results", DataTable)
        no_results = self.query_one("#no-results", Label)

        table.clear()
        self._filtered_results = []

        if not query:
            table.display = False
            no_results.display = False
            return

        # Filter results using the matches method (searches name, type, rule, etc.)
        for result in self._all_results:
            if result.matches(query):
                self._filtered_results.append(result)

        if self._filtered_results:
            table.display = True
            no_results.display = False
            for i, result in enumerate(self._filtered_results[:50]):  # Limit to 50 results
                # Use index as key to avoid duplicates
                table.add_row(result.display_type, result.name, result.display_info, key=str(i))
            # Select first row
            if table.row_count > 0:
                table.move_cursor(row=0)
        else:
            table.display = False
            no_results.display = True

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search input - select first result."""
        self._select_current()

    @on(DataTable.RowSelected, "#search-results")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle result selection."""
        self._select_current()

    def action_select(self) -> None:
        """Select the current result."""
        self._select_current()

    def _select_current(self) -> None:
        """Select the currently highlighted result."""
        table = self.query_one("#search-results", DataTable)
        if table.row_count == 0 or not self._filtered_results:
            return

        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._filtered_results):
            result = self._filtered_results[cursor_row]
            self.dismiss(result.to_deep_link())

    def action_cancel(self) -> None:
        """Cancel the search."""
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Move cursor up in results."""
        table = self.query_one("#search-results", DataTable)
        if table.display and table.row_count > 0:
            table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down in results."""
        table = self.query_one("#search-results", DataTable)
        if table.display and table.row_count > 0:
            table.action_cursor_down()


class TraefikTUI(App):
    """A TUI dashboard for Traefik."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("/", "search", "Search"),
        Binding("escape", "escape_context", "Back", show=False),
        Binding("enter", "enter_context", "Enter", show=False),
    ]

    CSS = """
    /* Posting-inspired color scheme */
    $primary: #6366f1;
    $primary-darken-1: #4f46e5;
    $primary-darken-2: #4338ca;
    $secondary: #8b5cf6;
    $accent: #3b82f6;
    $surface: #1e1e2e;
    $surface-lighten-1: #313244;
    $background: #11111b;
    $text: #cdd6f4;
    $text-muted: #6c7086;
    $success: #a6e3a1;
    $warning: #f9e2af;
    $error: #f38ba8;

    Screen {
        background: $background;
    }

    Footer {
        background: $surface;
    }

    /* Tabs styling */
    TabbedContent {
        background: $surface;
        height: 1fr;
    }

    Tabs {
        background: $surface-lighten-1;
    }

    Tab {
        background: $surface-lighten-1;
        color: $text-muted;
        padding: 0 3;
    }

    Tab:hover {
        background: $surface;
        color: $text;
    }

    Tab.-active {
        background: $primary;
        color: $text;
    }

    TabPane {
        padding: 0;
    }

    /* Settings pane layout */
    #settings-content {
        height: 1fr;
        width: 100%;
    }

    #profile-list {
        width: 32;
    }

    #profile-editor {
        width: 1fr;
    }

    /* Placeholder tabs */
    .placeholder {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }

    .placeholder-title {
        text-style: bold;
        padding-bottom: 1;
    }

    """

    def __init__(
        self,
        deep_link: DeepLink | None = None,
        direct_url: str | None = None,
        direct_username: str | None = None,
        direct_password: str | None = None,
    ) -> None:
        super().__init__()
        self._direct_mode = direct_url is not None
        self.settings = Settings.load()

        # In direct mode, create a temporary profile
        if self._direct_mode:
            from .models import BasicAuth

            basic_auth = None
            if direct_username or direct_password:
                basic_auth = BasicAuth(
                    username=direct_username or "",
                    password=direct_password or "",
                )
            self.settings.profiles = {"direct": Profile(url=direct_url, basic_auth=basic_auth)}
            self.settings.selected_profile = "direct"
            # Don't start on settings tab in direct mode
            if self.settings.active_tab == "settings":
                self.settings.active_tab = "entrypoints"

        self._runtime: dict[str, ProfileRuntime] = {}
        self._dirty = False
        self._monitor_interval = 5.0
        self._consecutive_errors = 0
        self._error_threshold = 5
        self._deep_link = deep_link
        self._first_connection_checked = False
        # Apply saved theme
        if self.settings.theme:
            self.theme = self.settings.theme

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Save theme preference when changed via command palette."""
        if new_theme != self.settings.theme:
            self.settings.theme = new_theme
            self._dirty = True

    def search_themes(self) -> None:
        """Show theme picker with current theme indicated."""
        from textual.command import CommandPalette

        self.push_screen(
            CommandPalette(
                providers=[ThemeProviderWithIndicator],
                placeholder="Search for themes...",
            ),
        )

    def deliver_screenshot(self, filename: str | None = None, path: str | None = None) -> None:
        """Save screenshot, creating ~/Downloads if needed."""
        from pathlib import Path

        if path is None:
            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)
            path = str(downloads)
        saved_path = self.save_screenshot(filename=filename, path=path)
        if saved_path:
            self.notify(f"Screenshot saved to {saved_path}")

    def compose(self) -> ComposeResult:
        yield TitleBar(id="title-bar")
        with TabbedContent(initial=self.settings.active_tab):
            with TabPane("Entrypoints", id="entrypoints"):
                yield EntrypointsView(id="entrypoints-view")
            with TabPane("Routers", id="routers"):
                yield RoutersView(id="routers-view")
            with TabPane("Services", id="services"):
                yield ServicesView(id="services-view")
            with TabPane("Middleware", id="middleware"):
                yield MiddlewaresView(id="middlewares-view")
            if not self._direct_mode:
                with TabPane("Settings", id="settings"):
                    with Horizontal(id="settings-content"):
                        yield ProfileList(id="profile-list")
                        yield ProfileEditor(id="profile-editor")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        self._refresh_profile_list()
        self._update_title_bar()
        self._start_monitor()
        # Trigger immediate connection check
        self._check_connection_now()

        # Handle deep link - switch to correct tab
        if self._deep_link:
            tab_map = {
                "entrypoint": "entrypoints",
                "router": "routers",
                "service": "services",
                "middleware": "middleware",
            }
            target_tab = tab_map.get(self._deep_link.resource_type)
            if target_tab:
                self.settings.active_tab = target_tab
                tabbed_content = self.query_one(TabbedContent)
                tabbed_content.active = target_tab

        # Initial data refresh
        self._refresh_current_tab()

    def _set_api_status(self, status: ApiStatus) -> None:
        """Update the API status indicator."""
        indicator = self.query_one("#status-indicator", StatusIndicator)
        indicator.status = status

    def _update_title_bar(self) -> None:
        """Update the title bar with current profile and connection status."""
        title_bar = self.query_one("#title-bar", TitleBar)
        selected = self.settings.selected_profile

        # Update profile name (show URL in direct mode)
        if self._direct_mode and selected and selected in self.settings.profiles:
            title_bar.update_profile(self.settings.profiles[selected].url)
        else:
            title_bar.update_profile(selected)

        # Update connection status
        if selected and selected in self._runtime:
            runtime = self._runtime[selected]
            title_bar.update_connection_status(runtime.status, runtime.error)
        else:
            title_bar.update_connection_status(ConnectionStatus.DISCONNECTED)

    def _scroll_table_to_row(self, table: DataTable, row_key: str) -> None:
        """Scroll the table to show the given row."""
        if row_key not in table.rows:
            return
        row_index = table.get_row_index(row_key)
        y = sum(row.height for row in table.ordered_rows[:row_index])
        table.scroll_to(y=y, animate=False, force=True)

    def _select_table_row(self, table: DataTable, row_key: str) -> bool:
        """Select a row in a DataTable by its key. Returns True if found."""
        if row_key not in table.rows:
            return False
        # Get the visual row index for this key
        row_index = table.get_row_index(row_key)
        table.move_cursor(row=row_index, animate=False, scroll=False)
        return True

    def _select_table_row_with_retry(
        self, table: DataTable, row_key: str, callback: callable, retries: int = 10
    ) -> None:
        """Try to select a row, retrying until found or retries exhausted."""
        if self._select_table_row(table, row_key):
            callback()
            # Scroll after callback (detail pane) has been set up
            self.set_timer(0.1, lambda: self._scroll_table_to_row(table, row_key))
        elif retries > 0:
            self.set_timer(
                0.05,
                lambda: self._select_table_row_with_retry(table, row_key, callback, retries - 1),
            )
        else:
            # Row not found after retries, still call callback to show detail
            callback()

    async def _handle_deep_link_navigation(self, resource_type: str) -> None:
        """Navigate to the deep-linked resource if applicable."""
        if not self._deep_link or self._deep_link.resource_type != resource_type:
            return

        link = self._deep_link
        self._deep_link = None  # Clear so we only navigate once

        if resource_type == "entrypoint":
            entrypoints_view = self.query_one("#entrypoints-view", EntrypointsView)
            table = entrypoints_view.query_one("#entrypoints-table", DataTable)
            self._select_table_row_with_retry(
                table,
                link.resource_name,
                lambda: self._fetch_entrypoint_detail(link.resource_name),
            )
        elif resource_type == "router":
            routers_view = self.query_one("#routers-view", RoutersView)
            sub_tab_map = {
                "http": "http-routers",
                "tcp": "tcp-routers",
                "udp": "udp-routers",
            }
            table_map = {"http": "http-table", "tcp": "tcp-table", "udp": "udp-table"}

            # Search stored router lists for exact or partial match
            found_protocol = None
            actual_name = link.resource_name
            for proto, routers_list in [
                ("http", routers_view._http_routers),
                ("tcp", routers_view._tcp_routers),
                ("udp", routers_view._udp_routers),
            ]:
                for router in routers_list:
                    if router.name == link.resource_name:
                        found_protocol = proto
                        actual_name = router.name
                        break
                    if router.name.startswith(f"{link.resource_name}@"):
                        found_protocol = proto
                        actual_name = router.name
                        break
                if found_protocol:
                    break

            protocol = found_protocol or link.protocol
            sub_tab = sub_tab_map.get(protocol, "http-routers")
            table_id = table_map.get(protocol, "http-table")
            tabs = routers_view.query_one("#routers-tabs", TabbedContent)
            tabs.active = sub_tab
            table = routers_view.query_one(f"#{table_id}", DataTable)
            self._select_table_row_with_retry(
                table,
                actual_name,
                lambda name=actual_name, proto=protocol: self._fetch_router_detail(name, proto),
            )
        elif resource_type == "service":
            services_view = self.query_one("#services-view", ServicesView)
            sub_tab_map = {
                "http": "http-services",
                "tcp": "tcp-services",
                "udp": "udp-services",
            }
            table_map = {
                "http": "http-svc-table",
                "tcp": "tcp-svc-table",
                "udp": "udp-svc-table",
            }

            # Search stored service lists for exact or partial match
            found_protocol = None
            actual_name = link.resource_name
            for proto, services_list in [
                ("http", services_view._http_services),
                ("tcp", services_view._tcp_services),
                ("udp", services_view._udp_services),
            ]:
                for service in services_list:
                    if service.name == link.resource_name:
                        found_protocol = proto
                        actual_name = service.name
                        break
                    if service.name.startswith(f"{link.resource_name}@"):
                        found_protocol = proto
                        actual_name = service.name
                        break
                if found_protocol:
                    break

            protocol = found_protocol or link.protocol
            sub_tab = sub_tab_map.get(protocol, "http-services")
            table_id = table_map.get(protocol, "http-svc-table")
            tabs = services_view.query_one("#services-tabs", TabbedContent)
            tabs.active = sub_tab
            table = services_view.query_one(f"#{table_id}", DataTable)
            self._select_table_row_with_retry(
                table,
                actual_name,
                lambda name=actual_name, proto=protocol: self._fetch_service_detail(name, proto),
            )
        elif resource_type == "middleware":
            middlewares_view = self.query_one("#middlewares-view", MiddlewaresView)
            sub_tab_map = {"http": "http-middlewares", "tcp": "tcp-middlewares"}
            table_map = {"http": "http-mw-table", "tcp": "tcp-mw-table"}

            # Search stored middleware lists for exact or partial match
            found_protocol = None
            actual_name = link.resource_name
            for proto, middlewares_list in [
                ("http", middlewares_view._http_middlewares),
                ("tcp", middlewares_view._tcp_middlewares),
            ]:
                for middleware in middlewares_list:
                    if middleware.name == link.resource_name:
                        found_protocol = proto
                        actual_name = middleware.name
                        break
                    if middleware.name.startswith(f"{link.resource_name}@"):
                        found_protocol = proto
                        actual_name = middleware.name
                        break
                if found_protocol:
                    break

            protocol = found_protocol or link.protocol
            sub_tab = sub_tab_map.get(protocol, "http-middlewares")
            table_id = table_map.get(protocol, "http-mw-table")
            tabs = middlewares_view.query_one("#middlewares-tabs", TabbedContent)
            tabs.active = sub_tab
            table = middlewares_view.query_one(f"#{table_id}", DataTable)
            self._select_table_row_with_retry(
                table,
                actual_name,
                lambda name=actual_name, proto=protocol: self._fetch_middleware_detail(name, proto),
            )

    def _refresh_current_tab(self) -> None:
        """Refresh data for the currently active tab."""
        active_tab = self.settings.active_tab
        if active_tab == "entrypoints":
            self._refresh_entrypoints()
        elif active_tab == "routers":
            self._refresh_routers()
        elif active_tab == "services":
            self._refresh_services()
        elif active_tab == "middleware":
            self._refresh_middlewares()

    def _refresh_profile_list(self) -> None:
        """Refresh the profile list widget."""
        if self._direct_mode:
            self._update_title_bar()
            return
        profile_list = self.query_one("#profile-list", ProfileList)
        profiles = list(self.settings.profiles.keys())
        profile_list.update_profiles(profiles, self.settings.selected_profile)

        # Update the editor
        self._update_editor()

    def _update_editor(self) -> None:
        """Update the profile editor with the selected profile."""
        if self._direct_mode:
            self._update_title_bar()
            return
        editor = self.query_one("#profile-editor", ProfileEditor)
        selected = self.settings.selected_profile

        if selected and selected in self.settings.profiles:
            profile = self.settings.profiles[selected]
            runtime = self._runtime.get(selected, ProfileRuntime())
            editor.set_profile(selected, profile, runtime)
        else:
            editor.set_profile(None, None, None)

        # Also update the title bar
        self._update_title_bar()

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab changes."""
        # Only handle main app tabs, not sub-tabs
        if event.pane.id in (
            "entrypoints",
            "routers",
            "services",
            "middleware",
            "settings",
        ):
            self.settings.active_tab = event.pane.id
            self._dirty = True
            self._refresh_current_tab()

    @on(ProfileList.ProfileSelected)
    def on_profile_selected(self, event: ProfileList.ProfileSelected) -> None:
        """Handle profile selection."""
        if event.profile_name != self.settings.selected_profile:
            self.settings.selected_profile = event.profile_name
            self._dirty = True
            self._consecutive_errors = 0
            self._refresh_profile_list()
            # Trigger an immediate connection check
            self._check_connection_now()
            # Refresh current tab data
            self._refresh_current_tab()

    @on(ProfileList.ProfileCreate)
    def on_profile_create(self, event: ProfileList.ProfileCreate) -> None:
        """Handle profile creation."""
        self.settings.create_profile()
        self._dirty = True
        self._refresh_profile_list()

    @on(ProfileList.ProfileDelete)
    def on_profile_delete(self, event: ProfileList.ProfileDelete) -> None:
        """Handle profile deletion request."""

        def handle_delete(confirmed: bool) -> None:
            if confirmed:
                self.settings.delete_profile(event.profile_name)
                self._dirty = True
                self._refresh_profile_list()

        self.push_screen(
            ConfirmDialog("Delete Profile", f"Delete profile '{event.profile_name}'?"),
            handle_delete,
        )

    @on(ProfileList.ProfileRename)
    def on_profile_rename(self, event: ProfileList.ProfileRename) -> None:
        """Handle profile rename request."""

        def handle_rename(new_name: str | None) -> None:
            if new_name and new_name != event.profile_name:
                if new_name in self.settings.profiles:
                    self.notify(f"Profile '{new_name}' already exists", severity="error")
                    return
                if self.settings.rename_profile(event.profile_name, new_name):
                    self.settings.save()
                    self.notify(f"Renamed to '{new_name}'")
                    self._refresh_profile_list()
                else:
                    self.notify("Rename failed", severity="error")

        self.push_screen(
            InputDialog("Rename Profile", event.profile_name),
            handle_rename,
        )

    @on(ProfileEditor.ProfileChanged)
    def on_profile_changed(self, event: ProfileEditor.ProfileChanged) -> None:
        """Handle profile data changes."""
        if event.profile_name in self.settings.profiles:
            self.settings.profiles[event.profile_name] = event.profile
            self._dirty = True
            # Trigger connection check when URL changes
            self._check_connection_now()

    @work(exclusive=True, group="routers")
    async def _refresh_routers(self) -> None:
        """Fetch and display routers from the selected profile."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        routers_view = self.query_one("#routers-view", RoutersView)

        # Remember if detail pane was open and which router
        had_detail_open = routers_view.has_detail_open()
        selected_router, selected_router_type = routers_view.get_selected_router()

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            http_routers = await api.get_http_routers()
            tcp_routers = await api.get_tcp_routers()
            udp_routers = await api.get_udp_routers()

            routers_view.update_http_routers(http_routers)
            routers_view.update_tcp_routers(tcp_routers)
            routers_view.update_udp_routers(udp_routers)
            self._set_api_status(ApiStatus.SUCCESS)
            self._consecutive_errors = 0

            # Re-fetch detail if it was open
            if had_detail_open and selected_router and selected_router_type:
                # Use current active type - stored type may be stale
                active_type = routers_view._get_active_router_type()
                # Only refresh if still on the same protocol tab
                if active_type != selected_router_type:
                    await routers_view._close_detail_pane()
                else:
                    try:
                        if active_type == "tcp":
                            detail = await api.get_tcp_router(selected_router)
                        elif active_type == "udp":
                            detail = await api.get_udp_router(selected_router)
                        else:
                            detail = await api.get_http_router(selected_router)
                        await routers_view.show_detail(detail)
                    except TraefikAPIError:
                        # Router no longer exists, close detail pane
                        await routers_view._close_detail_pane()

            # Handle deep link navigation
            await self._handle_deep_link_navigation("router")

        except TraefikAPIError as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._error_threshold:
                await routers_view.clear_tables()
            self._set_api_status(ApiStatus.ERROR)
            self.notify(f"Connection error: {e}", severity="error")

    @on(RoutersView.RouterSelected)
    def on_router_selected(self, event: RoutersView.RouterSelected) -> None:
        """Handle router selection for detail view."""
        self._fetch_router_detail(event.router_name, event.router_type)

    @work(exclusive=True, group="router-detail")
    async def _fetch_router_detail(self, router_name: str, router_type: str) -> None:
        """Fetch and display router detail."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            if router_type == "tcp":
                detail = await api.get_tcp_router(router_name)
            elif router_type == "udp":
                detail = await api.get_udp_router(router_name)
            else:
                detail = await api.get_http_router(router_name)

            routers_view = self.query_one("#routers-view", RoutersView)
            await routers_view.show_detail(detail)
            self._set_api_status(ApiStatus.SUCCESS)
        except TraefikAPIError as e:
            self.notify(f"Failed to fetch router details: {e}", severity="error")
            self._set_api_status(ApiStatus.ERROR)

    @work(exclusive=True, group="services")
    async def _refresh_services(self) -> None:
        """Fetch and display services from the selected profile."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        services_view = self.query_one("#services-view", ServicesView)

        # Remember if detail pane was open and which service
        had_detail_open = services_view.has_detail_open()
        selected_service, selected_service_type = services_view.get_selected_service()

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            http_services = await api.get_http_services()
            tcp_services = await api.get_tcp_services()
            udp_services = await api.get_udp_services()

            services_view.update_http_services(http_services)
            services_view.update_tcp_services(tcp_services)
            services_view.update_udp_services(udp_services)
            self._set_api_status(ApiStatus.SUCCESS)
            self._consecutive_errors = 0

            # Re-fetch detail if it was open
            if had_detail_open and selected_service and selected_service_type:
                # Use current active type - stored type may be stale
                active_type = services_view._get_active_service_type()
                # Only refresh if still on the same protocol tab
                if active_type != selected_service_type:
                    await services_view._close_detail_pane()
                else:
                    try:
                        if active_type == "tcp":
                            detail = await api.get_tcp_service(selected_service)
                        elif active_type == "udp":
                            detail = await api.get_udp_service(selected_service)
                        else:
                            detail = await api.get_http_service(selected_service)
                        await services_view.show_detail(detail)
                    except TraefikAPIError:
                        # Service no longer exists, close detail pane
                        await services_view._close_detail_pane()

            # Handle deep link navigation
            await self._handle_deep_link_navigation("service")

        except TraefikAPIError as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._error_threshold:
                await services_view.clear_tables()
            self._set_api_status(ApiStatus.ERROR)
            self.notify(f"Connection error: {e}", severity="error")

    @on(ServicesView.ServiceSelected)
    def on_service_selected(self, event: ServicesView.ServiceSelected) -> None:
        """Handle service selection for detail view."""
        self._fetch_service_detail(event.service_name, event.service_type)

    @work(exclusive=True, group="service-detail")
    async def _fetch_service_detail(self, service_name: str, service_type: str) -> None:
        """Fetch and display service detail."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            if service_type == "tcp":
                detail = await api.get_tcp_service(service_name)
            elif service_type == "udp":
                detail = await api.get_udp_service(service_name)
            else:
                detail = await api.get_http_service(service_name)

            services_view = self.query_one("#services-view", ServicesView)
            await services_view.show_detail(detail)
            self._set_api_status(ApiStatus.SUCCESS)
        except TraefikAPIError as e:
            self.notify(f"Failed to fetch service details: {e}", severity="error")
            self._set_api_status(ApiStatus.ERROR)

    @work(exclusive=True, group="entrypoints")
    async def _refresh_entrypoints(self) -> None:
        """Fetch and display entrypoints from the selected profile."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        entrypoints_view = self.query_one("#entrypoints-view", EntrypointsView)

        # Remember if detail pane was open and which entrypoint
        had_detail_open = entrypoints_view.has_detail_open()
        selected_entrypoint = entrypoints_view.get_selected_entrypoint()

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            entrypoints = await api.get_entrypoints()

            # Fetch routers, services, middlewares to build usage stats per entrypoint
            http_routers = await api.get_http_routers()
            tcp_routers = await api.get_tcp_routers()
            udp_routers = await api.get_udp_routers()
            all_routers = http_routers + tcp_routers + udp_routers

            # Build router stats: {entrypoint_name: {enabled: N, disabled: N, warning: N}}
            router_stats: dict[str, dict[str, int]] = {}
            # Also track which services/middlewares are used by routers on each entrypoint
            ep_services: dict[str, set[str]] = {}
            ep_middlewares: dict[str, set[str]] = {}

            for router in all_routers:
                for ep_name in router.entry_points or []:
                    if ep_name not in router_stats:
                        router_stats[ep_name] = {
                            "enabled": 0,
                            "disabled": 0,
                            "warning": 0,
                        }
                        ep_services[ep_name] = set()
                        ep_middlewares[ep_name] = set()
                    status = (router.status or "").lower()
                    if status == "enabled":
                        router_stats[ep_name]["enabled"] += 1
                    elif status == "disabled":
                        router_stats[ep_name]["disabled"] += 1
                    elif status == "warning":
                        router_stats[ep_name]["warning"] += 1
                    # Track services and middlewares used by this router
                    if router.service:
                        ep_services[ep_name].add(router.service)
                    if router.middlewares:
                        ep_middlewares[ep_name].update(router.middlewares)

            # Fetch services and build stats
            http_services = await api.get_http_services()
            tcp_services = await api.get_tcp_services()
            udp_services = await api.get_udp_services()
            all_services_list = http_services + tcp_services + udp_services
            # Build lookup by full name and by base name (without @provider)
            all_services: dict[str, Service] = {}
            for s in all_services_list:
                all_services[s.name] = s
                base_name = s.name.split("@")[0] if "@" in s.name else s.name
                if base_name not in all_services:
                    all_services[base_name] = s

            service_stats: dict[str, dict[str, int]] = {}
            for ep_name, svc_names in ep_services.items():
                service_stats[ep_name] = {"enabled": 0, "disabled": 0, "warning": 0}
                for svc_name in svc_names:
                    # Try exact match first, then base name match
                    svc = all_services.get(svc_name)
                    if not svc:
                        base_name = svc_name.split("@")[0] if "@" in svc_name else svc_name
                        svc = all_services.get(base_name)
                    if svc:
                        status = (svc.status or "").lower()
                        if status == "enabled":
                            service_stats[ep_name]["enabled"] += 1
                        elif status == "disabled":
                            service_stats[ep_name]["disabled"] += 1
                        elif status == "warning":
                            service_stats[ep_name]["warning"] += 1

            # Fetch middlewares and build stats
            http_middlewares = await api.get_http_middlewares()
            tcp_middlewares = await api.get_tcp_middlewares()
            all_middlewares_list = http_middlewares + tcp_middlewares
            # Build lookup by full name and by base name (without @provider)
            all_middlewares: dict[str, Middleware] = {}
            for m in all_middlewares_list:
                all_middlewares[m.name] = m
                base_name = m.name.split("@")[0] if "@" in m.name else m.name
                if base_name not in all_middlewares:
                    all_middlewares[base_name] = m

            middleware_stats: dict[str, dict[str, int]] = {}
            for ep_name, mw_names in ep_middlewares.items():
                middleware_stats[ep_name] = {"enabled": 0, "disabled": 0, "warning": 0}
                for mw_name in mw_names:
                    # Try exact match first, then base name match
                    mw = all_middlewares.get(mw_name)
                    if not mw:
                        base_name = mw_name.split("@")[0] if "@" in mw_name else mw_name
                        mw = all_middlewares.get(base_name)
                    if mw:
                        status = (mw.status or "").lower()
                        if status == "enabled":
                            middleware_stats[ep_name]["enabled"] += 1
                        elif status == "disabled":
                            middleware_stats[ep_name]["disabled"] += 1
                        elif status == "warning":
                            middleware_stats[ep_name]["warning"] += 1

            entrypoints_view.update_entrypoints(
                entrypoints, router_stats, service_stats, middleware_stats
            )
            self._set_api_status(ApiStatus.SUCCESS)
            self._consecutive_errors = 0

            # Re-fetch detail if it was open
            if had_detail_open and selected_entrypoint:
                try:
                    detail = await api.get_entrypoint(selected_entrypoint)
                    await entrypoints_view.show_detail(detail)
                except TraefikAPIError:
                    # Entrypoint no longer exists, close detail pane
                    await entrypoints_view._close_detail_pane()

            # Handle deep link navigation
            await self._handle_deep_link_navigation("entrypoint")

        except TraefikAPIError as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._error_threshold:
                await entrypoints_view.clear_table()
            self._set_api_status(ApiStatus.ERROR)
            self.notify(f"Connection error: {e}", severity="error")

    @on(EntrypointsView.EntrypointSelected)
    def on_entrypoint_selected(self, event: EntrypointsView.EntrypointSelected) -> None:
        """Handle entrypoint selection for detail view."""
        self._fetch_entrypoint_detail(event.entrypoint_name)

    @work(exclusive=True, group="entrypoint-detail")
    async def _fetch_entrypoint_detail(self, entrypoint_name: str) -> None:
        """Fetch and display entrypoint detail."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            detail = await api.get_entrypoint(entrypoint_name)

            entrypoints_view = self.query_one("#entrypoints-view", EntrypointsView)
            await entrypoints_view.show_detail(detail)
            self._set_api_status(ApiStatus.SUCCESS)
        except TraefikAPIError as e:
            self.notify(f"Failed to fetch entrypoint details: {e}", severity="error")
            self._set_api_status(ApiStatus.ERROR)

    @work(exclusive=True, group="middlewares")
    async def _refresh_middlewares(self) -> None:
        """Fetch and display middlewares from the selected profile."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        middlewares_view = self.query_one("#middlewares-view", MiddlewaresView)

        # Remember if detail pane was open and which middleware
        had_detail_open = middlewares_view.has_detail_open()
        selected_middleware, selected_middleware_type = middlewares_view.get_selected_middleware()

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            http_middlewares = await api.get_http_middlewares()
            tcp_middlewares = await api.get_tcp_middlewares()

            middlewares_view.update_http_middlewares(http_middlewares)
            middlewares_view.update_tcp_middlewares(tcp_middlewares)
            self._set_api_status(ApiStatus.SUCCESS)
            self._consecutive_errors = 0

            # Re-fetch detail if it was open
            if had_detail_open and selected_middleware and selected_middleware_type:
                # Use current active type - stored type may be stale
                active_type = middlewares_view._get_active_middleware_type()
                # Only refresh if still on the same protocol tab
                if active_type != selected_middleware_type:
                    await middlewares_view._close_detail_pane()
                else:
                    try:
                        if active_type == "tcp":
                            detail = await api.get_tcp_middleware(selected_middleware)
                        else:
                            detail = await api.get_http_middleware(selected_middleware)
                        await middlewares_view.show_detail(detail)
                    except TraefikAPIError:
                        # Middleware no longer exists, close detail pane
                        await middlewares_view._close_detail_pane()

            # Handle deep link navigation
            await self._handle_deep_link_navigation("middleware")

        except TraefikAPIError as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._error_threshold:
                await middlewares_view.clear_tables()
            self._set_api_status(ApiStatus.ERROR)
            self.notify(f"Connection error: {e}", severity="error")

    @on(MiddlewaresView.MiddlewareSelected)
    def on_middleware_selected(self, event: MiddlewaresView.MiddlewareSelected) -> None:
        """Handle middleware selection for detail view."""
        self._fetch_middleware_detail(event.middleware_name, event.middleware_type)

    @work(exclusive=True, group="middleware-detail")
    async def _fetch_middleware_detail(self, middleware_name: str, middleware_type: str) -> None:
        """Fetch and display middleware detail."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        self._set_api_status(ApiStatus.LOADING)

        try:
            api = TraefikAPI(profile.url, profile.basic_auth)
            if middleware_type == "tcp":
                detail = await api.get_tcp_middleware(middleware_name)
            else:
                detail = await api.get_http_middleware(middleware_name)

            middlewares_view = self.query_one("#middlewares-view", MiddlewaresView)
            await middlewares_view.show_detail(detail)
            self._set_api_status(ApiStatus.SUCCESS)
        except TraefikAPIError as e:
            self.notify(f"Failed to fetch middleware details: {e}", severity="error")
            self._set_api_status(ApiStatus.ERROR)

    @work(exclusive=True, group="monitor")
    async def _check_connection_now(self) -> None:
        """Check the connection for the selected profile."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        # Show connecting status
        self._runtime[selected] = ProfileRuntime(status=ConnectionStatus.CONNECTING)
        self._update_editor()
        self._set_api_status(ApiStatus.LOADING)

        # Check the connection
        runtime = await check_connection(profile.url, profile.basic_auth)
        self._runtime[selected] = runtime
        self._update_editor()

        if runtime.status == ConnectionStatus.CONNECTED:
            self._set_api_status(ApiStatus.SUCCESS)
        else:
            self._set_api_status(ApiStatus.ERROR)
            # Navigate to Settings on first connection failure
            if not self._first_connection_checked and not self._direct_mode:
                self.settings.active_tab = "settings"
                tabbed_content = self.query_one(TabbedContent)
                tabbed_content.active = "settings"

        self._first_connection_checked = True

    def _start_monitor(self) -> None:
        """Start the background connection monitor."""
        self.set_interval(self._monitor_interval, self._monitor_tick)

    async def _monitor_tick(self) -> None:
        """Periodic tick for data refresh."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        # Refresh connection status
        runtime = await check_connection(profile.url, profile.basic_auth)
        self._runtime[selected] = runtime
        self._update_editor()

        # Refresh current tab data
        self._refresh_current_tab()

    async def action_escape_context(self) -> None:
        """Handle ESC contextually - dismiss panes, blur inputs, or focus tabs."""
        # Check if entrypoints detail pane is visible
        entrypoints_view = self.query_one("#entrypoints-view", EntrypointsView)
        if entrypoints_view._detail_pane is not None:
            await entrypoints_view._close_detail_pane()
            return

        # Check if router detail pane is visible
        routers_view = self.query_one("#routers-view", RoutersView)
        if routers_view._detail_pane is not None:
            await routers_view._close_detail_pane()
            return

        # Check if services detail pane is visible
        services_view = self.query_one("#services-view", ServicesView)
        if services_view._detail_pane is not None:
            await services_view._close_detail_pane()
            return

        # Check if middlewares detail pane is visible
        middlewares_view = self.query_one("#middlewares-view", MiddlewaresView)
        if middlewares_view._detail_pane is not None:
            await middlewares_view._close_detail_pane()
            return

        focused = self.focused

        # If an input is focused, blur it
        if isinstance(focused, Input):
            focused.blur()
            return

        # If on a sub-tab bar, ascend to parent tab bar
        if isinstance(focused, (Tab, Tabs)):
            # Find the current TabbedContent, then look for a parent TabbedContent
            node = focused
            current_tabbed_content = None
            while node is not None:
                if isinstance(node, TabbedContent):
                    if current_tabbed_content is None:
                        current_tabbed_content = node
                    else:
                        # Found a parent TabbedContent - focus its tabs
                        tabs = node.query_one(Tabs)
                        tabs.focus()
                        return
                node = node.parent
            # No parent TabbedContent found, stay on current tabs
            return

        # Otherwise, focus the nearest parent tab bar
        if focused is not None:
            node = focused
            while node is not None:
                if isinstance(node, TabbedContent):
                    tabs = node.query_one(Tabs)
                    tabs.focus()
                    return
                node = node.parent

        # Fallback: focus the main tab bar
        tabs = self.query_one("Tabs")
        tabs.focus()

    def action_enter_context(self) -> None:
        """Handle Enter contextually - descend into tab pane content."""
        focused = self.focused

        # If a Tab or Tabs is focused, descend into the active pane
        if isinstance(focused, (Tab, Tabs)):
            # Find the parent TabbedContent
            node = focused
            while node is not None:
                if isinstance(node, TabbedContent):
                    # Get the active pane and focus first focusable element
                    active_pane = node.query_one(f"TabPane#{node.active}", TabPane)
                    if active_pane:
                        for widget in active_pane.query("*"):
                            if widget.can_focus:
                                widget.focus()
                                return
                    return
                node = node.parent

    def action_save(self) -> None:
        """Save settings to disk."""
        if self._direct_mode:
            self.notify("Settings not saved in direct connection mode")
            return
        self.settings.save()
        self._dirty = False
        self.notify("Settings saved")

    def action_quit(self) -> None:
        """Quit the application."""
        if self._dirty and not self._direct_mode:
            self.settings.save()
        self.exit()

    def action_search(self) -> None:
        """Open the global search modal."""
        # Collect all resources from all views
        results: list[SearchResult] = []

        # Entrypoints
        entrypoints_view = self.query_one("#entrypoints-view", EntrypointsView)
        for ep in entrypoints_view._entrypoints:
            results.append(SearchResult("entrypoint", "", ep.name, ep.address))

        # Routers (include rule as extra_info)
        routers_view = self.query_one("#routers-view", RoutersView)
        for router in routers_view._http_routers:
            results.append(SearchResult("router", "http", router.name, router.rule or ""))
        for router in routers_view._tcp_routers:
            results.append(SearchResult("router", "tcp", router.name, router.rule or ""))
        for router in routers_view._udp_routers:
            results.append(SearchResult("router", "udp", router.name, router.rule or ""))

        # Services (include type as extra_info)
        services_view = self.query_one("#services-view", ServicesView)
        for service in services_view._http_services:
            results.append(SearchResult("service", "http", service.name, service.type or ""))
        for service in services_view._tcp_services:
            results.append(SearchResult("service", "tcp", service.name, service.type or ""))
        for service in services_view._udp_services:
            results.append(SearchResult("service", "udp", service.name, service.type or ""))

        # Middlewares (include type as extra_info)
        middlewares_view = self.query_one("#middlewares-view", MiddlewaresView)
        for mw in middlewares_view._http_middlewares:
            results.append(SearchResult("middleware", "http", mw.name, mw.type or ""))
        for mw in middlewares_view._tcp_middlewares:
            results.append(SearchResult("middleware", "tcp", mw.name, mw.type or ""))

        def handle_search_result(deep_link: DeepLink | None) -> None:
            if deep_link:
                self._deep_link = deep_link
                # Switch to the correct tab
                tab_map = {
                    "entrypoint": "entrypoints",
                    "router": "routers",
                    "service": "services",
                    "middleware": "middleware",
                }
                target_tab = tab_map.get(deep_link.resource_type)
                if target_tab:
                    self.settings.active_tab = target_tab
                    tabbed_content = self.query_one(TabbedContent)
                    tabbed_content.active = target_tab
                    self._refresh_current_tab()

        self.push_screen(SearchModal(results), handle_search_result)

    @on(NavigateLink)
    def on_navigate_link(self, event: NavigateLink) -> None:
        """Handle navigation link messages from detail panes."""
        self._navigate_to_link(event.link)

    def _navigate_to_link(self, link: str) -> None:
        """Navigate to a deep link."""
        deep_link = DeepLink.parse(link)
        if not deep_link:
            return

        self._deep_link = deep_link

        # Switch to the correct tab
        tab_map = {
            "entrypoint": "entrypoints",
            "router": "routers",
            "service": "services",
            "middleware": "middleware",
        }
        target_tab = tab_map.get(deep_link.resource_type)
        if target_tab:
            self.settings.active_tab = target_tab
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = target_tab
            # Refresh the tab which will trigger deep link navigation
            self._refresh_current_tab()


def main() -> None:
    """Entry point for the application."""
    parser = argparse.ArgumentParser(description="`tt` is a console TUI dashboard for Traefik")
    parser.add_argument(
        "--link",
        "-l",
        type=str,
        help="Deep link to a resource (e.g., entrypoint#websecure, router:tcp#myrouter)",
    )
    parser.add_argument(
        "--url",
        "-u",
        type=str,
        help="Direct connection URL (disables Settings tab)",
    )
    parser.add_argument(
        "--username",
        type=str,
        help="HTTP basic auth username (requires --url)",
    )
    parser.add_argument(
        "--password",
        type=str,
        help="HTTP basic auth password (requires --url)",
    )
    args = parser.parse_args()

    # Validate auth args require --url
    if (args.username or args.password) and not args.url:
        parser.error("--username and --password require --url")

    deep_link = None
    if args.link:
        deep_link = DeepLink.parse(args.link)
        if deep_link is None:
            parser.error(f"Invalid link format: {args.link}")

    app = TraefikTUI(
        deep_link=deep_link,
        direct_url=args.url,
        direct_username=args.username,
        direct_password=args.password,
    )
    app.run()


if __name__ == "__main__":
    main()
