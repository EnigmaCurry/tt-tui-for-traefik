"""Profile list sidebar widget."""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static


class ProfileList(Vertical):
    """A sidebar widget showing the list of profiles."""

    BINDINGS = [
        Binding("c", "create_profile", "Create Profile"),
        Binding("delete", "delete_profile", "Delete Profile"),
    ]

    DEFAULT_CSS = """
    ProfileList {
        width: 32;
        border: solid $primary;
        background: $surface;
    }

    ProfileList > .title {
        dock: top;
        padding: 1 2;
        background: $primary;
        color: $text;
        text-style: bold;
    }

    ProfileList ListView {
        background: $surface;
    }

    ProfileList ListView:focus {
        border: none;
    }

    ProfileList ListItem {
        padding: 0 2;
    }

    ProfileList ListItem.--highlight {
        background: $accent;
    }

    ProfileList .empty-message {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    ProfileList .help-text {
        dock: bottom;
        padding: 1 2;
        color: $text-muted;
        text-align: center;
        border-top: solid $primary-darken-2;
    }
    """

    class ProfileSelected(Message):
        """Message sent when a profile is selected."""

        def __init__(self, profile_name: str | None) -> None:
            self.profile_name = profile_name
            super().__init__()

    class ProfileCreate(Message):
        """Message sent when user wants to create a profile."""

    class ProfileDelete(Message):
        """Message sent when user wants to delete a profile."""

        def __init__(self, profile_name: str) -> None:
            self.profile_name = profile_name
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._profiles: list[str] = []
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        yield Label("Profiles", classes="title")
        yield ListView(id="profile-listview")
        yield Static("[c] Create  [del] Delete", classes="help-text")

    def update_profiles(self, profiles: list[str], selected: str | None = None) -> None:
        """Update the list of profiles."""
        self._profiles = profiles
        self._selected = selected

        listview = self.query_one("#profile-listview", ListView)
        listview.clear()

        if not profiles:
            listview.mount(ListItem(Label("No profiles", classes="empty-message")))
        else:
            for name in profiles:
                prefix = "> " if name == selected else "  "
                item = ListItem(Label(f"{prefix}{name}"), id=f"profile-{name}")
                listview.mount(item)

            # Select the current profile in the listview
            if selected and selected in profiles:
                idx = profiles.index(selected)
                listview.index = idx

    @on(ListView.Selected)
    def on_listview_selected(self, event: ListView.Selected) -> None:
        """Handle profile selection."""
        if event.item and event.item.id:
            profile_name = event.item.id.replace("profile-", "")
            if profile_name != "No profiles":
                self.post_message(self.ProfileSelected(profile_name))

    def action_create_profile(self) -> None:
        """Create a new profile."""
        self.post_message(self.ProfileCreate())

    def action_delete_profile(self) -> None:
        """Delete the selected profile."""
        if self._selected:
            self.post_message(self.ProfileDelete(self._selected))
