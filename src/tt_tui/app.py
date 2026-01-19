"""Main TT TUI application."""

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, Static, TabbedContent, TabPane

from .models import ConnectionStatus, Profile, ProfileRuntime, Settings
from .monitor import check_connection
from .widgets import ProfileEditor, ProfileList, StatusBar


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

    Footer {
        background: $surface;
    }

    /* Main layout */
    #main-container {
        height: 1fr;
    }

    #sidebar {
        width: 32;
        border-right: solid $primary-darken-2;
    }

    #content {
        width: 1fr;
    }

    /* Tabs styling */
    TabbedContent {
        background: $surface;
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
    #settings-pane {
        height: 1fr;
    }

    #settings-content {
        height: 1fr;
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
        with Horizontal(id="main-container"):
            yield ProfileList(id="sidebar")
            with Container(id="content"):
                with TabbedContent(initial="settings"):
                    with TabPane("Settings", id="settings"):
                        with Horizontal(id="settings-content"):
                            yield ProfileEditor(id="profile-editor")
                    with TabPane("Routers", id="routers"):
                        with Vertical(classes="placeholder"):
                            yield Static("Routers", classes="placeholder-title")
                            yield Static("View and manage HTTP/TCP routers")
                            yield Static("(Coming soon)")
                    with TabPane("Services", id="services"):
                        with Vertical(classes="placeholder"):
                            yield Static("Services", classes="placeholder-title")
                            yield Static("View backend services and load balancers")
                            yield Static("(Coming soon)")
                    with TabPane("Middleware", id="middleware"):
                        with Vertical(classes="placeholder"):
                            yield Static("Middleware", classes="placeholder-title")
                            yield Static("View middleware chain configurations")
                            yield Static("(Coming soon)")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        self._refresh_profile_list()
        self._start_monitor()

    def _refresh_profile_list(self) -> None:
        """Refresh the profile list widget."""
        profile_list = self.query_one("#sidebar", ProfileList)
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

    @on(ProfileList.ProfileSelected)
    def on_profile_selected(self, event: ProfileList.ProfileSelected) -> None:
        """Handle profile selection."""
        if event.profile_name != self.settings.selected_profile:
            self.settings.selected_profile = event.profile_name
            self._dirty = True
            self._refresh_profile_list()
            # Trigger an immediate connection check
            self._check_connection_now()

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

        # Check the connection
        runtime = await check_connection(profile.url, profile.basic_auth)
        self._runtime[selected] = runtime
        self._update_editor()

    def _start_monitor(self) -> None:
        """Start the background connection monitor."""
        self.set_interval(self._monitor_interval, self._monitor_tick)

    async def _monitor_tick(self) -> None:
        """Periodic tick for the connection monitor."""
        selected = self.settings.selected_profile
        if not selected or selected not in self.settings.profiles:
            return

        profile = self.settings.profiles[selected]
        if not profile.url:
            return

        runtime = await check_connection(profile.url, profile.basic_auth)
        self._runtime[selected] = runtime
        self._update_editor()

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
