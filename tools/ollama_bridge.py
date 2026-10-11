#!/usr/bin/env python3
"""Local OpenAI-chat → native Ollama bridge with explicit thinking controls and metrics.

Text/tools only. Binds loopback; never logs prompts, arguments, reasoning or credentials.
Ollama API: https://docs.ollama.com/api/chat
"""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
import uuid

METRICS = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count")


def native_request(body, context=32768, thinking=None):
    effort = body.get("reasoning_effort", "none")
    think = False if effort in (None, "none", "off") else True
    supported = (thinking or {}).get("values")
    if supported is not None:
        if not think and False not in supported:
            raise ValueError("Selected model cannot disable thinking; select a model supporting think:false")
        if think and effort in supported:
            think = effort
        elif think and True not in supported:
            raise ValueError(f"Model does not support requested reasoning effort {effort}")
    messages, tool_names = [], {}
    for original in body.get("messages", []):
        role = original["role"]
        content = original.get("content") or ""
        if isinstance(content, list):
            if any(item.get("type") != "text" for item in content):
                raise ValueError("PCB bridge supports text and tools only")
            content = "\n".join(item["text"] for item in content)
        message = {"role": "system" if role == "developer" else role, "content": content}
        if original.get("reasoning_content"):
            message["thinking"] = original["reasoning_content"]
        if original.get("tool_calls"):
            calls = []
            for call in original["tool_calls"]:
                fn = dict(call["function"])
                if isinstance(fn["arguments"], str):
                    fn["arguments"] = json.loads(fn["arguments"])
                if not isinstance(fn["arguments"], dict):
                    raise ValueError("Tool arguments must be JSON objects")
                tool_names[call["id"]] = fn["name"]
                calls.append({"function": fn})
            message["tool_calls"] = calls
        if role == "tool":
            tool_id = original.get("tool_call_id")
            if tool_id not in tool_names:
                raise ValueError("Tool result lacks a matching assistant call")
            message["tool_name"] = tool_names[tool_id]
        messages.append(message)
    cap = int(body.get("max_completion_tokens") or body.get("max_tokens") or -1)
    if cap == 0 or cap < -1:
        raise ValueError("Token budget must be positive or -1 (unlimited)")
    result = {"model": body["model"], "messages": messages, "stream": True, "think": think,
              "keep_alive": -1, "options": {"num_predict": cap, "num_ctx": context}}
    for field in ("temperature", "top_p", "stop"):
        if field in body:
            result["options"][field] = body[field]
    if body.get("tools"):
        result["tools"] = body["tools"]
    return result


class Translator:
    def __init__(self, model, think):
        self.model, self.think = model, think
        self.id = "chatcmpl-" + uuid.uuid4().hex
        self.calls = []
        self.done = False
        self.thinking_chars = 0
        self.metrics = {}

    def chunk(self, delta, finish=None, usage=None):
        result = {"id": self.id, "object": "chat.completion.chunk", "created": int(time.time()), "model": self.model,
                  "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        if usage is not None:
            result["usage"] = usage
        return result

    def feed(self, data):
        if data.get("error"):
            raise ValueError(data["error"])
        if self.done:
            raise ValueError("Data after completed Ollama response")
        msg = data.get("message", {})
        thinking = msg.get("thinking", "")
        self.thinking_chars += len(thinking)
        chunks = []
        if thinking:
            chunks.append(self.chunk({"reasoning_content": thinking}))
        if msg.get("content"):
            chunks.append(self.chunk({"content": msg["content"]}))
        self.calls.extend(msg.get("tool_calls", []))
        if data.get("done"):
            reason = data.get("done_reason")
            if reason not in ("stop", "length"):
                raise ValueError(f"Unexpected Ollama stop reason: {reason}")
            self.done = True
            self.metrics = {key: data.get(key) for key in METRICS}
            # Do not expose any tool call until completion confirms it wasn't truncated.
            if reason != "length" and self.calls:
                calls = []
                for index, call in enumerate(self.calls):
                    fn = call.get("function", {})
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        args = json.loads(args)
                    if not fn.get("name") or not isinstance(args, dict):
                        raise ValueError("Malformed native tool call; discarded")
                    calls.append({"index": index, "id": "call_" + uuid.uuid4().hex, "type": "function",
                                  "function": {"name": fn["name"], "arguments": json.dumps(args)}})
                chunks.append(self.chunk({"tool_calls": calls}))
                reason = "tool_calls"
            inp, out = data.get("prompt_eval_count", 0), data.get("eval_count", 0)
            chunks.append(self.chunk({}, reason, {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}))
        return chunks


class Bridge(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def json_response(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/models":
            self.json_response(200, {"object": "list", "data": [{"id": self.server.model, "object": "model", "owned_by": "local"}]})
        else:
            self.json_response(404, {"error": {"message": "Unknown endpoint"}})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.json_response(404, {"error": {"message": "Unknown endpoint"}})
            return
        started = time.monotonic()
        translator, stream_started, response = None, False, None
        metrics = {"event": "request", "status": "error"}
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 8 * 1024 * 1024:
                raise ValueError("Request size must be between 1 byte and 8 MiB")
            body = json.loads(self.rfile.read(size))
            if body.get("model") != self.server.model:
                raise ValueError("Model is not the bridge's configured model")
            if not body.get("stream"):
                raise ValueError("PCB bridge requires stream:true")
            request = native_request(body, self.server.context, self.server.thinking)
            metrics.update(model=request["model"], think=request["think"], token_budget=request["options"]["num_predict"])
            translator = Translator(request["model"], request["think"])
            upstream = Request(self.server.upstream + "/api/chat", data=json.dumps(request).encode(), headers={"Content-Type": "application/json"})
            response = urlopen(upstream, timeout=None)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            stream_started = True
            for raw in response:
                if not raw.strip():
                    continue
                data = json.loads(raw)
                if "first_event_s" not in metrics:
                    metrics["first_event_s"] = round(time.monotonic()-started, 3)
                for chunk in translator.feed(data):
                    self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                    self.wfile.flush()
                if translator.done:
                    break
            if not translator.done:
                raise ValueError("Ollama stream ended before a completion marker; incomplete output discarded")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            metrics.update(translator.metrics, status="complete", thinking_chars=translator.thinking_chars,
                           unexpected_thinking=translator.think is False and translator.thinking_chars > 0)
        except (OSError, ValueError, KeyError, TypeError) as error:
            metrics.update(error=type(error).__name__, reason=str(error)[:300])
            try:
                failure = {"error": {"message": str(error), "type": "pcb_bridge_error"}}
                if stream_started:
                    self.wfile.write(b"data: " + json.dumps(failure).encode() + b"\n\ndata: [DONE]\n\n")
                    self.wfile.flush()
                else:
                    self.json_response(502, failure)
            except OSError:
                pass
        finally:
            if response:
                response.close()
            metrics["elapsed_s"] = round(time.monotonic()-started, 3)
            with self.server.log_lock, self.server.log.open("a") as handle:
                handle.write(json.dumps(metrics) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.getenv("PCB_OLLAMA_MODEL", "nemotron3:33b"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--upstream", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    metadata = json.load(urlopen(Request(args.upstream + "/api/show", data=json.dumps({"model": args.model}).encode(), headers={"Content-Type": "application/json"}), timeout=None))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Bridge)
    server.model, server.upstream, server.thinking = args.model, args.upstream.rstrip("/"), metadata.get("thinking")
    server.context = int(os.getenv("PCB_CONTEXT_WINDOW", "32768"))
    if server.context <= 0:
        raise ValueError("Context limit must be positive")
    server.log = Path(__file__).resolve().parents[1] / ".agent" / "ollama.jsonl"
    server.log.parent.mkdir(exist_ok=True)
    server.log_lock = threading.Lock()
    print(json.dumps({"listening": f"http://127.0.0.1:{args.port}/v1", "model": args.model,
                      "thinking_metadata": server.thinking, "log": str(server.log)}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
