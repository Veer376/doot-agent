import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Suppress gRPC/absl C-core logs (e.g., "ALTS creds ignored...") by setting env vars early.
os.environ["ABSL_MIN_LOG_LEVEL"] = "3"
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_TRACE"] = ""


def setup_logging(log_level=None):
    # Use provided log_level if specified, otherwise fallback to env var
    log_type = log_level or os.getenv("LOG_LEVEL", "info").lower()

    # Check if handlers are already set up
    if logging.getLogger().hasHandlers():
        return

    # Clear existing handlers
    root = logging.getLogger()
    root.handlers = []

    # Setup formatter
    formatter = logging.Formatter("%(levelname)-8s [%(name)s] %(message)s")

    # Setup single handler for all loggers
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # Configure root logger
    root.addHandler(console)

    # Set log level based on environment variable
    if log_type == "debug":
        root.setLevel(logging.DEBUG)
    else:
        root.setLevel(logging.INFO)

    # Configure our main loggers
    toolkit_logger = logging.getLogger("toolkit")
    message_builder_logger = logging.getLogger("message_builder")
    agent_logger = logging.getLogger("agent")

    # Set all our loggers to the same level as root
    toolkit_logger.setLevel(root.level)
    message_builder_logger.setLevel(root.level)
    agent_logger.setLevel(root.level)

    # Silence third-party loggers
    for logger_name in [
        "WDM",
        "httpx",
        "selenium",
        "playwright",
        "urllib3",
        "asyncio",
        "langchain",
        "openai",
        "httpcore",
        "charset_normalizer",
        "anthropic._base_client",
        "PIL.PngImagePlugin",
        "trafilatura.htmlprocessing",
        "trafilatura",
        "grpc._cython.cygrpc",
        "grpc",
        "absl",
    ]:
        third_party = logging.getLogger(logger_name)
        third_party.setLevel(logging.ERROR)
        third_party.propagate = False
