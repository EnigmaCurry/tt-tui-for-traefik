"""Profile editor widget."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.events import Blur
from textual.message import Message
from textual.widgets import Checkbox, Input, Label, Static

from ..models import ConnectionStatus, Profile, ProfileRuntime, TunnelStatus

# SSH fields that should only sync on blur (not every keystroke)
_SSH_FIELD_IDS = frozenset(
    {
        "ssh-host-input",
        "ssh-remote-host-input",
        "ssh-remote-port-input",
        "ssh-local-port-input",
    }
)


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
        padding: 0 1;
    }

    ProfileEditor .field-label {
        color: $text-muted;
        padding: 0;
        margin: 0;
    }

    ProfileEditor Input {
        margin-bottom: 0;
        height: 3;
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
        padding: 1;
        color: $text-muted;
        text-align: center;
    }

    ProfileEditor .tunnel-open {
        color: $success;
    }

    ProfileEditor .tunnel-closed {
        color: $text-muted;
    }

    ProfileEditor .tunnel-error {
        color: $error;
    }

    ProfileEditor .tunnel-connecting {
        color: $warning;
    }

    ProfileEditor #ssh-fields {
        display: none;
    }

    ProfileEditor #ssh-fields.visible {
        display: block;
    }

    ProfileEditor #tunnel-status-display {
        display: none;
    }

    ProfileEditor #tunnel-status-display.visible {
        display: block;
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

                # SSH Tunnel section
                yield Checkbox("Enable SSH tunnel", id="ssh-enabled")

                with Vertical(id="ssh-fields"):
                    yield Label("SSH Host", classes="field-label")
                    yield Input(placeholder="~/.ssh/config Host name", id="ssh-host-input")

                    yield Label("Remote Host", classes="field-label")
                    yield Input(placeholder="localhost", id="ssh-remote-host-input")

                    yield Label("Remote Port", classes="field-label")
                    yield Input(placeholder="8080", id="ssh-remote-port-input")

                    yield Label("Local Port", classes="field-label")
                    yield Input(placeholder="auto", id="ssh-local-port-input")

                yield Static("", id="tunnel-status-display", classes="tunnel-closed")

                # Status section
                yield Static("Status", classes="field-label")
                yield Static("Disconnected", id="status-display", classes="status-disconnected")
                yield Static("", id="version-display", classes="version")

    def set_profile(
        self, name: str | None, profile: Profile | None, runtime: ProfileRuntime | None = None
    ) -> None:
        """Set the profile to edit.

        Only updates input fields when switching to a different profile.
        Use set_runtime() to update just the status display.
        """
        # Check if we're switching to a different profile
        switching_profile = name != self._profile_name

        # Only update profile data when switching profiles to avoid
        # overwriting user edits with stale data from periodic refreshes
        if switching_profile:
            self._profile_name = name
            self._profile = profile
        if runtime is not None:
            self._runtime = runtime

        # Only update input fields when switching profiles
        if switching_profile:
            url_input = self.query_one("#url-input", Input)
            username_input = self.query_one("#username-input", Input)
            password_input = self.query_one("#password-input", Input)

            # SSH tunnel fields
            ssh_enabled = self.query_one("#ssh-enabled", Checkbox)
            ssh_host = self.query_one("#ssh-host-input", Input)
            ssh_local_port = self.query_one("#ssh-local-port-input", Input)
            ssh_remote_host = self.query_one("#ssh-remote-host-input", Input)
            ssh_remote_port = self.query_one("#ssh-remote-port-input", Input)

            if profile:
                url_input.value = profile.url
                url_input.disabled = False
                username_input.value = profile.basic_auth.username if profile.basic_auth else ""
                username_input.disabled = False
                password_input.value = profile.basic_auth.password if profile.basic_auth else ""
                password_input.disabled = False

                # SSH tunnel fields
                tunnel = profile.ssh_tunnel
                ssh_enabled.value = tunnel.enabled if tunnel else False
                ssh_enabled.disabled = False
                ssh_host.value = tunnel.host if tunnel else ""
                if tunnel and tunnel.local_port > 0:
                    ssh_local_port.value = str(tunnel.local_port)
                else:
                    ssh_local_port.value = ""
                ssh_remote_host.value = tunnel.remote_host if tunnel else "localhost"
                ssh_remote_port.value = str(tunnel.remote_port) if tunnel else "8080"

                # Enable/disable SSH fields based on checkbox
                self._update_ssh_fields_state(ssh_enabled.value)
            else:
                url_input.value = ""
                url_input.disabled = True
                username_input.value = ""
                username_input.disabled = True
                password_input.value = ""
                password_input.disabled = True

                # Disable SSH fields
                ssh_enabled.value = False
                ssh_enabled.disabled = True
                ssh_host.value = ""
                ssh_local_port.value = ""
                ssh_remote_host.value = ""
                ssh_remote_port.value = ""
                self._update_ssh_fields_state(False)

        self._update_status_display()
        self._update_tunnel_status_display()

    def set_runtime(self, runtime: ProfileRuntime) -> None:
        """Update the runtime status display."""
        self._runtime = runtime
        self._update_status_display()
        self._update_tunnel_status_display()

    def _update_ssh_fields_state(self, enabled: bool) -> None:
        """Show or hide SSH fields based on the checkbox state."""
        ssh_fields = self.query_one("#ssh-fields", Vertical)
        tunnel_status = self.query_one("#tunnel-status-display", Static)

        if enabled:
            ssh_fields.add_class("visible")
            tunnel_status.add_class("visible")
            for input_widget in ssh_fields.query(Input):
                input_widget.disabled = False
        else:
            ssh_fields.remove_class("visible")
            tunnel_status.remove_class("visible")
            for input_widget in ssh_fields.query(Input):
                input_widget.disabled = True

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

    def _update_tunnel_status_display(self) -> None:
        """Update the tunnel status display based on runtime state."""
        tunnel_display = self.query_one("#tunnel-status-display", Static)
        tunnel_display.remove_class(
            "tunnel-open", "tunnel-closed", "tunnel-error", "tunnel-connecting"
        )

        # Only show tunnel status if SSH is enabled
        if self._profile and self._profile.ssh_tunnel and self._profile.ssh_tunnel.enabled:
            tunnel_status = self._runtime.tunnel_status
            if tunnel_status == TunnelStatus.OPEN:
                if self._runtime.tunnel_local_port:
                    port_info = f" (port {self._runtime.tunnel_local_port})"
                else:
                    port_info = ""
                tunnel_display.update(f"Tunnel: Open{port_info}")
                tunnel_display.add_class("tunnel-open")
            elif tunnel_status == TunnelStatus.CONNECTING:
                tunnel_display.update("Tunnel: Connecting...")
                tunnel_display.add_class("tunnel-connecting")
            elif tunnel_status == TunnelStatus.ERROR:
                error_msg = self._runtime.tunnel_error or "Error"
                tunnel_display.update(f"Tunnel: {error_msg}")
                tunnel_display.add_class("tunnel-error")
            else:
                tunnel_display.update("Tunnel: Closed")
                tunnel_display.add_class("tunnel-closed")
        else:
            tunnel_display.update("")

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        if event.checkbox.id == "ssh-enabled":
            self._update_ssh_fields_state(event.value)
            self._sync_profile_from_inputs()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        # For SSH fields, defer sync until blur/submit to avoid reconnecting on every keystroke
        if event.input.id in _SSH_FIELD_IDS:
            return
        self._sync_profile_from_inputs()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key on inputs - immediately sync SSH fields."""
        if event.input.id in _SSH_FIELD_IDS:
            self._sync_profile_from_inputs()

    def on_blur(self, event: Blur) -> None:
        """Handle blur events for SSH fields."""
        # Check multiple possible attributes for the widget that lost focus
        widget = getattr(event, "widget", None)
        if widget is self:
            # Event bubbled up - check if we can find the original sender
            # In Textual, when Blur bubbles, we need to check the focused history
            return
        if isinstance(widget, Input) and widget.id in _SSH_FIELD_IDS:
            self._sync_profile_from_inputs()

    def on_descendant_blur(self, event: Blur) -> None:
        """Handle blur events from descendant widgets."""
        widget = getattr(event, "widget", None)
        if isinstance(widget, Input) and widget.id in _SSH_FIELD_IDS:
            self._sync_profile_from_inputs()

    def _sync_profile_from_inputs(self) -> None:
        """Sync profile data from all input fields."""
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

        # SSH tunnel fields
        ssh_enabled = self.query_one("#ssh-enabled", Checkbox)
        ssh_host = self.query_one("#ssh-host-input", Input)
        ssh_local_port = self.query_one("#ssh-local-port-input", Input)
        ssh_remote_host = self.query_one("#ssh-remote-host-input", Input)
        ssh_remote_port = self.query_one("#ssh-remote-port-input", Input)

        from ..models import SSHTunnel

        # Parse port values with defaults
        try:
            local_port = int(ssh_local_port.value) if ssh_local_port.value.strip() else 0
        except ValueError:
            local_port = 0

        try:
            remote_port = int(ssh_remote_port.value) if ssh_remote_port.value.strip() else 8080
        except ValueError:
            remote_port = 8080

        self._profile.ssh_tunnel = SSHTunnel(
            enabled=ssh_enabled.value,
            host=ssh_host.value.strip(),
            remote_host=ssh_remote_host.value.strip() or "localhost",
            remote_port=remote_port,
            local_port=local_port,
        )

        self.post_message(self.ProfileChanged(self._profile_name, self._profile))
