#!/usr/bin/env python3
"""Check the running local API, PostgREST, checkpoint storage and Redis without an LLM call.

Creates one smoke-test thread. --thread-file saves its ID for a post-restart check.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--thread-file', type=Path)
    parser.add_argument('--verify-existing', action='store_true')
    args = parser.parse_args()
    if args.verify_existing and not args.thread_file:
        parser.error('--verify-existing requires --thread-file')
    base = args.base_url.rstrip('/')

    def request(path, body=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(base + path, data=data, method=method,
                      headers={'Authorization': 'Bearer local', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as result:
            return json.load(result)

    deadline = time.monotonic() + 90
    while True:
        try:
            if request('/')['status'] == 'ok':
                break
        except (OSError, URLError, HTTPError):
            if time.monotonic() >= deadline:
                raise
        time.sleep(1)

    assistants = request('/assistants/search', {})
    assert any(a['assistant_id'] == 'chat_agent' for a in assistants), assistants
    schemas = request('/assistants/chat_agent/schemas')
    assert schemas['graph_id'] == 'chat_agent'
    if args.verify_existing:
        thread_id = args.thread_file.read_text().strip()
    else:
        thread = request('/threads', {'metadata': {'smoke_test': True}})
        thread_id = thread['thread_id']
        request(f'/threads/{thread_id}', {'metadata': {'persisted_marker': 'doot-smoke'}}, method='PATCH')
        if args.thread_file:
            args.thread_file.write_text(thread_id)
    stored = request(f'/threads/{thread_id}')
    assert stored['metadata']['smoke_test'] is True
    assert stored['metadata']['persisted_marker'] == 'doot-smoke'
    assert isinstance(request(f'/threads/{thread_id}/state')['values'], dict)
    assert isinstance(request(f'/threads/{thread_id}/history', {}), list)
    assert request(f'/threads/{thread_id}/runs') == []
    print('OK: assistant schema, persisted thread metadata, PostgreSQL state/history, Redis run listing')
    print(f'Smoke thread: {thread_id}; no model calls made.')


if __name__ == '__main__':
    main()
