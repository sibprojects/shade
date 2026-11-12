"""Stands in for `claude -p --input-format stream-json --output-format stream-json`."""

import json
import os
import sys
import time


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def delta(text):
    emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "text_delta", "text": text}}})


emit({"type": "system", "subtype": "init", "pid": os.getpid()})
line = sys.stdin.readline()
if not line:
    sys.exit(0)
msg = json.loads(line)["message"]
content = msg["content"]
blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
text = " ".join(b.get("text", "") for b in blocks if b["type"] == "text")
images = sum(1 for b in blocks if b["type"] == "image")
args = sys.argv[1:]

if "FAIL_LOGIN" in text:
    emit({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login"})
elif "FAIL_LIMIT" in text:
    emit({"type": "result", "subtype": "success", "is_error": True, "result": "Claude AI usage limit reached|1767225600"})
elif "CRASH" in text:
    sys.stderr.write("boom\n")
    sys.exit(3)
else:
    if "SLOW" in text:
        for _ in range(50):
            delta("tick ")
            time.sleep(0.1)
    info = {
        "pid": os.getpid(),
        "ppid": os.getppid(),  # a venv python.exe on Windows is a launcher process
        "images": images,
        "has_key": "ANTHROPIC_API_KEY" in os.environ,
        "model": args[args.index("--model") + 1],
        "effort": args[args.index("--effort") + 1],
        "system": args[args.index("--system-prompt") + 1],
        "tools": args[args.index("--tools") + 1],
    }
    delta("Hello")
    delta(" world ")
    delta(json.dumps(info))
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "Hello world",
          "usage": {"input_tokens": 7, "output_tokens": 11, "cache_read_input_tokens": 5}})
