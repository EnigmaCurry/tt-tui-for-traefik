"""Main TT TUI application."""

from enum import Enum

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static, Tab, TabbedContent, TabPane, Tabs

from .api import TraefikAPI, TraefikAPIError
from .models import ConnectionStatus, Profile, ProfileRuntime, Settings
from .monitor import check_connection
from .widgets import EntrypointsView, MiddlewaresView, ProfileEditor, ProfileList, RoutersView, ServicesView, StatusBar


class ApiStatus(str, Enum):
    """Status of API calls."""

    IDLE = "idle"
    LOADING = "loading"
    SUCCESS = "success"
    ERROR = "error"


class StatusIndicator(Static):
    """A status indicator showing API call status."""

    DEFAULT_CSS = """
    StatusIndicator {
        dock: top;
        width: 3;
        height: 1;
        background: $primary;
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


class TraefikTUI(App):
    """A TUI dashboard for Traefik."""

    TITLE = "TT TUI for Traefik"
    SUB_TITLE = "Dashboard"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+s", "save", "Save"),
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

    Header {
        background: $primary;
    }

    HeaderTitle {
        width: 1fr;
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

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self._runtime: dict[str, ProfileRuntime] = {}
        self._dirty = False
        self._monitor_interval = 5.0

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusIndicator(id="status-indicator")
        with TabbedContent(initial=self.settings.active_tab):
            with TabPane("Entrypoints", id="entrypoints"):
                yield EntrypointsView(id="entrypoints-view")
            with TabPane("Routers", id="routers"):
                yield RoutersView(id="routers-view")
            with TabPane("Services", id="services"):
                yield ServicesView(id="services-view")
            with TabPane("Middleware", id="middleware"):
                yield MiddlewaresView(id="middlewares-view")
            with TabPane("Settings", id="settings"):
                with Horizontal(id="settings-content"):
                    yield ProfileList(id="profile-list")
                    yield ProfileEditor(id="profile-editor")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        self._refresh_profile_list()
        self._start_monitor()
        # Initial data refresh
        self._refresh_current_tab()

    def _set_api_status(self, status: ApiStatus) -> None:
        """Update the API status indicator."""
        indicator = self.query_one("#status-indicator", StatusIndicator)
        indicator.status = status

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
        profile_list = self.query_one("#profile-list", ProfileList)
        profiles = list(self.settings.profiles.keys())
        profile_list.update_profiles(profiles, self.settings.selected_profile)

        # Update the editor
        self._update_editor()

    def _update_editor(self) -> None:
        """Update the profile editor with the selected profile."""
        editor = self.query_one("#profile-editor", ProfileEditor)
        selected = self.settings.selected_profile

        if selected and selected in self.settings.profiles:
            profile = self.settings.profiles[selected]
            runtime = self._runtime.get(selected, ProfileRuntime())
            editor.set_profile(selected, profile, runtime)
        else:
            editor.set_profile(None, None, None)

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab changes."""
        # Only handle main app tabs, not sub-tabs
        if event.pane.id in ("entrypoints", "routers", "services", "middleware", "settings"):
            self.settings.active_tab = event.pane.id
            self._dirty = True
            self._refresh_current_tab()

    @on(ProfileList.ProfileSelected)
    def on_profile_selected(self, event: ProfileList.ProfileSelected) -> None:
        """Handle profile selection."""
        if event.profile_name != self.settings.selected_profile:
            self.settings.selected_profile = event.profile_name
            self._dirty = True
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

    @on(ProfileEditor.ProfileChanged)
    def on_profile_changed(self, event: ProfileEditor.ProfileChanged) -> None:
        """Handle profile data changes."""
        if event.profile_name in self.settings.profiles:
            self.settings.profiles[event.profile_name] = event.profile

            # Check if we need to rename based on URL
            new_key = self.settings.get_profile_key_from_url(event.profile.url)
            if new_key and new_key != event.profile_name and new_key not in self.settings.profiles:
                self.settings.rename_profile(event.profile_name, new_key)
                self._refresh_profile_list()

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

            # Re-fetch detail if it was open
            if had_detail_open and selected_router and selected_router_type:
                if selected_router_type == "tcp":
                    detail = await api.get_tcp_router(selected_router)
                elif selected_router_type == "udp":
                    detail = await api.get_udp_router(selected_router)
                else:
                    detail = await api.get_http_router(selected_router)
                await routers_view.show_detail(detail)

        except TraefikAPIError as e:
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

            # Re-fetch detail if it was open
            if had_detail_open and selected_service and selected_service_type:
                if selected_service_type == "tcp":
                    detail = await api.get_tcp_service(selected_service)
                elif selected_service_type == "udp":
                    detail = await api.get_udp_service(selected_service)
                else:
                    detail = await api.get_http_service(selected_service)
                await services_view.show_detail(detail)

        except TraefikAPIError as e:
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

            entrypoints_view.update_entrypoints(entrypoints)
            self._set_api_status(ApiStatus.SUCCESS)

            # Re-fetch detail if it was open
            if had_detail_open and selected_entrypoint:
                detail = await api.get_entrypoint(selected_entrypoint)
                await entrypoints_view.show_detail(detail)

        except TraefikAPIError as e:
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

            # Re-fetch detail if it was open
            if had_detail_open and selected_middleware and selected_middleware_type:
                if selected_middleware_type == "tcp":
                    detail = await api.get_tcp_middleware(selected_middleware)
                else:
                    detail = await api.get_http_middleware(selected_middleware)
                await middlewares_view.show_detail(detail)

        except TraefikAPIError as e:
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
        self.settings.save()
        self._dirty = False
        self.notify("Settings saved")

    def action_quit(self) -> None:
        """Quit the application."""
        if self._dirty:
            self.settings.save()
        self.exit()


def main() -> None:
    """Entry point for the application."""
    app = TraefikTUI()
    app.run()


if __name__ == "__main__":
    main()
