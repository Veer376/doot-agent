from PIL import Image
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.padding import Padding
from rich.console import Group
from typing import Any
from rich.syntax import Syntax
from rich import box
from rich.markdown import Markdown

console = Console()

def pretty_message(message: Any, console: Console = None):
    """
    Formats and prints a message directly to the console using Rich,
    with automatic text wrapping and preserved indentation.
    """
    if console is None:
        console = Console()

    # --- Helper function to create consistently styled sections ---
    def _create_section(title: str, content: Any, indent: int = 3) -> Group:
        """Creates a title Text and a Padding-wrapped content Text or other renderable."""
        if not content:
            return Group()  # Return an empty group if there's no content

        # If content is already a rich renderable (like Syntax or Group), use it directly
        from rich.console import RenderableType

        if hasattr(content, "__rich__") or isinstance(content, RenderableType):
            content_element = content
        elif isinstance(content, str):
            # If it's a string, convert to Text as before
            if not content.strip():
                return Group()
            # content_element = Text(content.strip(), style="default")
            content_element = Markdown(content.strip())
        else:
            # For any other type, convert to string and then to Text
            content_element = Text(str(content).strip(), style="default")

        return Group(
            Text(title, style="bold"),
            Padding(content_element, (0, 0, 0, indent)),  # (top, right, bottom, left)
        )

    # --- Handlers for specific message types ---

    def _build_ai_panel(msg: Any) -> Panel:
        render_groups = []

        if getattr(msg, "thought", None):
            render_groups.append(_create_section("🤔 Thinking:", msg.thought))

        if getattr(msg, "content", None):
            render_groups.append(_create_section("💡 Reasoning:", msg.content))

        if getattr(msg, "tool_calls", None):
            from rich.console import Group as RichGroup

            # Create a separate section for each tool call
            tool_group = RichGroup()
            for call in msg.tool_calls:
                name = call.get("name", "unknown_tool")
                args_str = ", ".join(
                    f"{k}='{v}'" for k, v in call.get("args", {}).items()
                )
                code = f"> {name}({args_str})"
                syntax = Syntax(
                    code,
                    "python",
                    background_color="default",  # This removes the black bg
                    line_numbers=False,
                    word_wrap=True,
                    indent_guides=True,
                )
                tool_group.renderables.append(syntax)

            # Add the tool group directly to render_groups
            render_groups.append(_create_section("\n🔧 Tool Calls:", tool_group))

        # Filter out any empty groups before creating the final body
        body = Group(*[group for group in render_groups if group])
        title = Text(
            "✨ AI",
            style="bold green",
        )
        return Panel(
            body,
            title=title,
            title_align="left",
            border_style="bold green",
            expand=False,
            width=100,
            highlight=True,
            box=box.ROUNDED,
        )

    def _build_tool_panel(msg: Any) -> Panel:
        # Handle different possible structures of tool message content
        
        if isinstance(msg.content, dict):
            error = msg.content.get("error", None)
            message = msg.content.get("message", "")
        else:
            message = str(msg.content)
            error = None
            
        body = _create_section("Error" if error else "Success", error if error else message)
        title = Text("🔨 Tool", style="bold")
        return Panel(body, title=title, border_style="bold", expand=False, width=70)

    def _build_human_panel(msg: Any) -> Panel:
        body = _create_section("👤 User:", msg.content)
        title = Text("💬 Human Message", style="bold")
        return Panel(body, title=title, border_style="bold", expand=False, width=70)

    def _build_default_panel(msg: Any) -> Panel:
        body = _create_section("ℹ️ Message:", getattr(msg, "content", "[No Content]"))
        title = Text(f"📦 {msg.__class__.__name__}", style="bold")
        return Panel(body, title=title, border_style="magenta", expand=False, width=70)

    # --- Dispatcher to select the correct handler ---

    msg_type = message.__class__.__name__
    panel_builders = {
        "GeminiMessage": _build_ai_panel,
        "AIMessage": _build_ai_panel,
        "ToolMessage": _build_tool_panel,
        "HumanMessage": _build_human_panel,
    }

    builder = panel_builders.get(msg_type, _build_default_panel)
    panel_to_print = builder(message)

    console.print(panel_to_print)


if __name__ == "__main__":
    """Test function to demonstrate the pretty print utility."""

    ai_message = AIMessage(content="Hello, how can I assist you today?")
    pretty_message(ai_message)

    human_message = HumanMessage(content="I need help with my order.")
    pretty_message(human_message)

    tool_message = ToolMessage(tool_call_id="tool_1", content={"message": "Tool executed successfully."})
    pretty_message(tool_message)