from __future__ import annotations

import asyncio
from random import randint

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Static


class SpaceFriendlyInput(Input):
    """A small Input subclass that ensures the space key inserts a literal space.

    Some Textual versions interpret the space key as a focus/navigation key.
    This class forces a plain space character to be inserted.
    """

    def on_key(self, event) -> None:
        if event.key == "space":
            # Insert a real space at the current value end.
            self.value = f"{self.value} "
            return
        super().on_key(event)


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


class ChatApp(App):
    """A simple Textual chat app demonstrating streaming replies."""

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
    """

    title = "Doot Agent — Streaming Chat"
    streaming = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="chat-area"):
            yield ChatBubble(
                "System",
                "Welcome to **Doot Agent**!\n\nType a prompt below and press [bold green]Send[/] to see a streaming response demo.",
                role_color="cyan",
            )
        with Horizontal(id="input-area"):
            yield SpaceFriendlyInput(placeholder="Type something...", id="prompt")
            yield Button("Send", id="send")
        yield Footer()

    async def on_mount(self) -> None:
        prompt = self.query_one("#prompt", SpaceFriendlyInput)
        prompt.focus()
        self.set_focus(prompt)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            await self._handle_send()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._handle_send(event.value)

    async def _handle_send(self, value: str | None = None) -> None:
        prompt_value = value or self.query_one("#prompt", SpaceFriendlyInput).value
        prompt_value = prompt_value.strip()
        if not prompt_value:
            return
        input_widget = self.query_one("#prompt", SpaceFriendlyInput)
        input_widget.value = ""
        input_widget.focus()
        self.set_focus(input_widget)
        await self.stream_response(prompt_value)

    async def stream_response(self, prompt: str) -> None:
        """Simulate streaming tokens from an LLM and append into the chat view."""
        if self.streaming:
            return
        self.streaming = True

        user_bubble = ChatBubble("You", prompt, role_color="green")
        await self.query("#chat-area").first().mount(user_bubble)

        assistant_bubble = ChatBubble("Doot Agent", "", role_color="blue")
        await self.query("#chat-area").first().mount(assistant_bubble)

        dummy_responses = [
            "Sure! Here's a short story:\n\n",
            "Once upon a time, there was an AI named Doot who loved to help developers. ",
            "Each time someone asked a question, Doot would respond with kindness and clarity. ",
            "In the terminal, the messages would stream live, token by token.\n\n",
            "And that is how Doot became everyone's favorite coding companion.\n",
            "\nWould you like to see another example?",
        ]

        for chunk in dummy_responses:
            assistant_bubble.message += chunk
            assistant_bubble.refresh(layout=True)
            await asyncio.sleep(0.25 + randint(0, 150) / 1000)

        self.streaming = False


def run_chat_ui() -> None:
    app = ChatApp()
    app.run()
