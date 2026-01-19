"""Profile editor widget."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Label, Static

from ..models import ConnectionStatus, Profile, ProfileRuntime


class ProfileEditor(Vertical):
    """A widget for editing profile details."""

    DEFAULT_CSS = """
    ProfileEditor {
        border: solid $primary;
        background: $surface;
    }

    ProfileEditor > .title {
        dock: top;
        padding: 0 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }

    ProfileEditor .field-group {
        padding: 1 2;
    }

    ProfileEditor .field-label {
        color: $text-muted;
        padding-bottom: 0;
    }

    ProfileEditor Input {
        margin-bottom: 1;
    }

    ProfileEditor .status-section {
        height: auto;
        padding: 1 2;
        border-top: solid $primary-darken-2;
    }

    ProfileEditor VerticalScroll {
        height: 1fr;
    }

    ProfileEditor .status-connected {
        color: $success;
    }

    ProfileEditor .status-disconnected {
        color: $text-muted;
    }

    ProfileEditor .status-error {
        color: $error;
    }

    ProfileEditor .status-connecting {
        color: $warning;
    }

    ProfileEditor .version {
        color: $text-muted;
    }

    ProfileEditor .no-profile {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }
    """

    class ProfileChanged(Message):
        """Message sent when profile data changes."""

        def __init__(self, profile_name: str, profile: Profile) -> None:
            self.profile_name = profile_name
            self.profile = profile
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._profile_name: str | None = None
        self._profile: Profile | None = None
        self._runtime: ProfileRuntime = ProfileRuntime()

    def compose(self) -> ComposeResult:
        yield Label("Profile Details", classes="title")
        with VerticalScroll():
            with Vertical(classes="field-group"):
                yield Label("URL", classes="field-label")
                yield Input(placeholder="http://localhost:8080", id="url-input")

                yield Label("Username", classes="field-label")
                yield Input(placeholder="(optional)", id="username-input")

                yield Label("Password", classes="field-label")
                yield Input(placeholder="(optional)", password=True, id="password-input")
        with Vertical(classes="status-section"):
            yield Static("Status", classes="field-label")
            yield Static("Disconnected", id="status-display", classes="status-disconnected")
            yield Static("", id="version-display", classes="version")

    def set_profile(
        self, name: str | None, profile: Profile | None, runtime: ProfileRuntime | None = None
    ) -> None:
        """Set the profile to edit."""
        self._profile_name = name
        self._profile = profile
        self._runtime = runtime or ProfileRuntime()

        url_input = self.query_one("#url-input", Input)
        username_input = self.query_one("#username-input", Input)
        password_input = self.query_one("#password-input", Input)

        if profile:
            url_input.value = profile.url
            url_input.disabled = False
            username_input.value = profile.basic_auth.username if profile.basic_auth else ""
            username_input.disabled = False
            password_input.value = profile.basic_auth.password if profile.basic_auth else ""
            password_input.disabled = False
        else:
            url_input.value = ""
            url_input.disabled = True
            username_input.value = ""
            username_input.disabled = True
            password_input.value = ""
            password_input.disabled = True

        self._update_status_display()

    def set_runtime(self, runtime: ProfileRuntime) -> None:
        """Update the runtime status display."""
        self._runtime = runtime
        self._update_status_display()

    def _update_status_display(self) -> None:
        """Update the status display based on runtime state."""
        status_display = self.query_one("#status-display", Static)
        version_display = self.query_one("#version-display", Static)

        status = self._runtime.status
        status_display.remove_class(
            "status-connected", "status-disconnected", "status-error", "status-connecting"
        )

        if status == ConnectionStatus.CONNECTED:
            status_display.update("Connected")
            status_display.add_class("status-connected")
            if self._runtime.version:
                version_display.update(f"Traefik {self._runtime.version}")
            else:
                version_display.update("")
        elif status == ConnectionStatus.CONNECTING:
            status_display.update("Connecting...")
            status_display.add_class("status-connecting")
            version_display.update("")
        elif status == ConnectionStatus.ERROR:
            error_msg = self._runtime.error or "Error"
            status_display.update(f"Error: {error_msg}")
            status_display.add_class("status-error")
            version_display.update("")
        else:
            status_display.update("Disconnected")
            status_display.add_class("status-disconnected")
            version_display.update("")

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if not self._profile_name or not self._profile:
            return

        url_input = self.query_one("#url-input", Input)
        username_input = self.query_one("#username-input", Input)
        password_input = self.query_one("#password-input", Input)

        # Update the profile
        self._profile.url = url_input.value

        username = username_input.value.strip()
        password = password_input.value

        if username or password:
            from ..models import BasicAuth

            self._profile.basic_auth = BasicAuth(username=username, password=password)
        else:
            self._profile.basic_auth = None

        self.post_message(self.ProfileChanged(self._profile_name, self._profile))
