import asyncio
import os
import re
import sys

PORT = int(os.getenv("PLAYWRIGHT_PORT", "3000"))
HOST = os.getenv("PLAYWRIGHT_HOST", "0.0.0.0")
WS_FILE = os.getenv("WS_ENDPOINT_FILE", "/var/run/playwright-ws-endpoint")

# Playwright CLI will output a line like:
#   Listening on ws://0.0.0.0:3000/playwright
ENDPOINT_RE = re.compile(r"Listening on\s+(ws:\/\/[^\s]+)")


async def run():
    # Start the Playwright websocket server
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "playwright",
        "run-server",
        "--port",
        str(PORT),
        "--host",
        HOST,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    ws_endpoint = None
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="ignore").rstrip()
        print(line, flush=True)
        if ws_endpoint is None:
            m = ENDPOINT_RE.search(line)
            if m:
                ws_endpoint = m.group(1)
                # Replace 0.0.0.0 with actual hostname for external clients if needed
                external_host = os.getenv("PUBLIC_HOST")
                if external_host and ws_endpoint.startswith("ws://0.0.0.0:"):
                    ws_endpoint = ws_endpoint.replace(
                        "ws://0.0.0.0:", f"ws://{external_host}:"
                    )
                with open(WS_FILE, "w") as f:
                    f.write(ws_endpoint)
                print(
                    f"[server] Wrote ws endpoint to {WS_FILE}: {ws_endpoint}",
                    flush=True,
                )

    rc = await proc.wait()
    return rc


if __name__ == "__main__":
    try:
        rc = asyncio.run(run())
        sys.exit(rc)
    except KeyboardInterrupt:
        pass
