"""Status bar widget for the footer."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusBar(Horizontal):
    """A status bar widget showing context-sensitive help."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
    }

    StatusBar > .left {
        width: 1fr;
        padding: 0 1;
    }

    StatusBar > .right {
        width: auto;
        padding: 0 1;
        text-align: right;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._help_text = ""
        self._right_text = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="left-status", classes="left")
        yield Static("", id="right-status", classes="right")

    def set_help_text(self, text: str) -> None:
        """Set the help text on the left side."""
        self._help_text = text
        self.query_one("#left-status", Static).update(text)

    def set_right_text(self, text: str) -> None:
        """Set the text on the right side."""
        self._right_text = text
        self.query_one("#right-status", Static).update(text)
