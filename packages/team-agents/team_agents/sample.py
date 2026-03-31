from __future__ import annotations

import asyncio
from datetime import datetime
from random import choice, randint

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.reactive import reactive
    from textual.widgets import Button, Footer, Header, Input, Static
except ImportError:  # pragma: no cover
    App = None  # type: ignore
    ComposeResult = None  # type: ignore
    Container = None  # type: ignore
    Horizontal = None  # type: ignore
    Vertical = None  # type: ignore
    reactive = None  # type: ignore
    Button = None  # type: ignore
    Footer = None  # type: ignore
    Header = None  # type: ignore
    Input = None  # type: ignore
    Static = None  # type: ignore


class ChatBubble(Static):
    """A single chat bubble in the conversation."""

    def __init__(self, author: str, text: str, *, role_color: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.author = author
        self.role_color = role_color
        self.message = text

    def render(self) -> Panel:
        author = Text(self.author, style=f"bold {self.role_color}")
        body = Markdown(self.message)
        return Panel(body, title=author, border_style=self.role_color)


class DummyChatApp(App):
    """Sample streaming chat UI using Textual.

    This demonstrates a streaming-style conversation where a "model"
    emits token chunks over time, and the UI updates the latest message
    in place.
    """

    CSS = """
    Screen {
        background: $surface;
    }

    #chat-area {
        height: 1fr;
        overflow: auto;
        padding: 1 1;
    }

    #input-area {
        height: 3;
        padding: 0 1;
    }

    #send {
        width: 12;
    }
    """

    title = "Doot Agent — Streaming Chat Sample"

    streaming = reactive(False)

    def compose(self) -> ComposeResult:
        # NOTE: Textual Header has changed APIs across versions; keep it minimal.
        yield Header(show_clock=True)
        with Vertical(id="chat-area"):
            # Start with a welcoming system message
            yield ChatBubble(
                "System",
                "Welcome to **Doot Agent**!\n\nType a prompt below and press [bold green]Send[/] to see a streaming response demo.",
                role_color="cyan",
            )
        with Horizontal(id="input-area"):
            yield Input(placeholder="Type something...", id="prompt")
            yield Button("Send", id="send")
        yield Footer()

    async def on_mount(self) -> None:
        # Focus the prompt on launch
        # Textual Input.focus() is synchronous in this version.
        self.query_one("#prompt", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            prompt = self.query_one("#prompt", Input).value.strip()
            if not prompt:
                return
            # Clear input and start streaming a response
            self.query_one("#prompt", Input).value = ""
            await self.stream_response(prompt)

    async def stream_response(self, prompt: str) -> None:
        """Simulate streaming tokens from an LLM and append into the chat view."""
        if self.streaming:
            return
        self.streaming = True

        # Add a user bubble
        user_bubble = ChatBubble("You", prompt, role_color="green")
        await self.query("#chat-area").first().mount(user_bubble)

        # Add a placeholder for the assistant response and update it token-by-token
        assistant_bubble = ChatBubble("Doot Agent", "", role_color="blue")
        await self.query("#chat-area").first().mount(assistant_bubble)

        # Dummy token stream (simulate incremental response)
        dummy_responses = [
            "Sure! Here's a short story:\n\n",
            "Once upon a time, there was an AI named Doot who loved to help developers. ",
            "Each time someone asked a question, Doot would respond with kindness and clarity. ",
            "In the terminal, the messages would stream live, token by token.\n\n",
            "And that is how Doot became everyone\'s favorite coding companion.\n",
            "\nWould you like to see another example?",
        ]

        # Update bubble content incrementally
        for chunk in dummy_responses:
            assistant_bubble.message += chunk
            assistant_bubble.refresh(layout=True)
            # Random delay to make it feel like streaming
            await asyncio.sleep(0.25 + randint(0, 150) / 1000)

        # Add a tiny “done” message in the status footer
        self.notify("Doot Agent finished streaming. Press Send again to repeat.")
        self.streaming = False


def main() -> None:
    if App is None:
        print(
            "Textual is not installed. Install it with `pip install textual` to run this sample UI."
        )
        return

    app = DummyChatApp()
    app.run()


if __name__ == "__main__":
    main()
