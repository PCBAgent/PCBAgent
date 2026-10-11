#!/usr/bin/env python3
"""Open the same Pi agent in a desktop chat window.

The agent, its skills, and its commands are unchanged. This process only
draws the conversation and forwards each message to `pi --mode rpc`.
"""

import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DIALOG = {"confirm", "select", "input", "editor"}


def _plain(value):
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict):
        content = value.get("content")
        parts = []
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text") or "")
        text = "\n".join(part for part in parts if part)
        if not text:
            text = value.get("error") or value.get("message") or json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    if len(text) > 80000:
        text = text[:80000] + "\n…"
    return text


def _brief(value):
    if not isinstance(value, dict) or not value:
        return ""
    kept = {key: value[key] for key in ("stage", "action", "command", "path") if key in value}
    shown = kept or value
    text = json.dumps(shown, ensure_ascii=False)
    if len(text) > 240:
        text = text[:240] + "…"
    return "  " + text


def avatar_pixbuf(size=48):
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    gold = (232, 186, 104, 255)
    green = (62, 150, 104, 255)
    draw.ellipse((4, 4, 123, 123), fill=(22, 48, 38, 255))
    for y in (46, 62, 78):
        draw.rounded_rectangle((8, y, 26, y + 8), radius=4, fill=gold)
        draw.rounded_rectangle((102, y, 120, y + 8), radius=4, fill=gold)
    draw.rounded_rectangle((34, 30, 94, 98), radius=18, fill=green, outline=gold, width=3)
    draw.ellipse((46, 48, 62, 66), fill=(255, 248, 236, 255))
    draw.ellipse((70, 48, 86, 66), fill=(255, 248, 236, 255))
    draw.ellipse((52, 54, 58, 62), fill=(36, 42, 38, 255))
    draw.ellipse((76, 54, 82, 62), fill=(36, 42, 38, 255))
    draw.ellipse((54, 55, 56, 57), fill=(255, 255, 255, 255))
    draw.ellipse((78, 55, 80, 57), fill=(255, 255, 255, 255))
    draw.ellipse((44, 70, 52, 76), fill=(214, 120, 122, 180))
    draw.ellipse((80, 70, 88, 76), fill=(214, 120, 122, 180))
    draw.arc((52, 68, 76, 86), 20, 160, fill=(255, 244, 220, 255), width=3)
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    raw = io.BytesIO()
    image.save(raw, "png")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(raw.getvalue())
    loader.close()
    return loader.get_pixbuf()


class Chat(Gtk.Window):
    def __init__(self):
        super().__init__(title="PCBAgent")
        self.set_default_size(1080, 680)
        self.avatar = avatar_pixbuf()
        self.set_icon(self.avatar)
        self.busy = False
        self.column = None
        self.blocks = {}
        env = os.environ.copy()
        local_bin = str(Path.home() / ".local" / "bin")
        if local_bin not in env.get("PATH", "").split(":"):
            env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
        self.proc = subprocess.Popen(
            ["pi", "--mode", "rpc", "--approve"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.write_lock = threading.Lock()
        self.alive = True
        threading.Thread(target=self._read_stderr, daemon=True).start()
        threading.Thread(target=self._read_stdout, daemon=True).start()

        style = Gtk.CssProvider()
        style.load_from_data(b"""
            window, scrolledwindow, viewport, box { background: #171a18; }
            label { color: #f3efe6; }
            .muted { color: #a39e93; font-size: 13px; }
            .think { color: #c8c2b6; font-size: 14px; }
            .tool { color: #9dceb4; font-size: 13px; }
            .name { font-weight: 700; }
            .user {
                background: #2c3830;
                color: #f3efe6;
                border-radius: 16px;
                padding: 8px 12px;
            }
            button.send { background: #3d9a6a; color: #101410; border-radius: 14px; padding: 8px 14px; }
            button.stop { background: #a85a42; color: #f3efe6; }
            button.choice {
                background: #262b28;
                color: #f3efe6;
                border: 1px solid #3c433e;
                border-radius: 12px;
            }
            entry {
                color: #f3efe6;
                background: #242824;
                caret-color: #e8ba68;
                min-height: 42px;
                border-radius: 14px;
                border: 1px solid #3c433e;
                padding: 6px 12px;
            }
            entry placeholder { color: #8d887e; }
            entry:focus { border-color: #3d9a6a; }
            textview, textview text { color: #f3efe6; background: #242824; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        header.set_margin_top(14)
        header.set_margin_bottom(10)
        header.pack_start(Gtk.Image.new_from_pixbuf(self.avatar), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(label="PCBAgent", xalign=0)
        name.get_style_context().add_class("name")
        sub = Gtk.Label(label="Same agent, on this machine", xalign=0)
        sub.get_style_context().add_class("muted")
        titles.pack_start(name, False, False, 0)
        titles.pack_start(sub, False, False, 0)
        header.pack_start(titles, False, False, 0)

        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.messages.set_margin_start(16)
        self.messages.set_margin_end(16)
        self.messages.set_margin_top(8)
        self.messages.set_margin_bottom(8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.add(self.messages)
        self.scroll = scroll.get_vadjustment()

        self.status = Gtk.Label(label="", xalign=0)
        self.status.get_style_context().add_class("muted")
        self.status.set_margin_start(16)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Describe a circuit, or use /design")
        self.entry.set_hexpand(True)
        self.entry.set_can_focus(True)
        self.entry.connect("activate", self._on_button)

        self.button = Gtk.Button(label="Send")
        self.button.get_style_context().add_class("send")
        self.button.connect("clicked", self._on_button)

        composer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        composer.set_margin_start(12)
        composer.set_margin_end(12)
        composer.set_margin_top(8)
        composer.set_margin_bottom(14)
        composer.pack_start(self.entry, True, True, 0)
        composer.pack_start(self.button, False, False, 0)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(header, False, False, 0)
        root.pack_start(scroll, True, True, 0)
        root.pack_start(self.status, False, False, 4)
        root.pack_start(composer, False, False, 0)
        self.add(root)
        self.connect("destroy", self._close)
        self.show_all()
        self.entry.grab_focus()

    def _close(self, _window):
        self.alive = False
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        Gtk.main_quit()

    def _entry_text(self):
        return self.entry.get_text().strip()

    def _on_button(self, _button):
        if self.busy:
            self._send({"type": "abort"})
            return
        text = self._entry_text()
        if not text:
            return
        self.entry.set_text("")
        self._add_user(text)
        self._begin_agent()
        self._set_busy(True)
        self.status.set_text("Working")
        self._send({"type": "prompt", "message": text})

    def _set_busy(self, busy):
        self.busy = busy
        self.button.set_label("Stop" if busy else "Send")
        if busy:
            self.button.get_style_context().add_class("stop")
        else:
            self.button.get_style_context().remove_class("stop")
            self.status.set_text("")

    def _pin(self):
        GLib.idle_add(lambda: self.scroll.set_value(self.scroll.get_upper()) or False)

    def _add_user(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, max_width_chars=72)
        label.get_style_context().add_class("user")
        row = Gtk.Box()
        row.pack_end(label, False, False, 0)
        self.messages.pack_start(row, False, False, 0)
        row.show_all()
        self._pin()

    def _begin_agent(self):
        who = Gtk.Label(label="PCBAgent", xalign=0)
        who.get_style_context().add_class("name")
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        col.pack_start(who, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.pack_start(Gtk.Image.new_from_pixbuf(self.avatar), False, False, 0)
        row.pack_start(col, True, True, 0)
        self.messages.pack_start(row, False, False, 0)
        row.show_all()
        self.column = col
        self.blocks = {}
        self._pin()

    def _write(self, key, text, replace=False, style=None, heading=None):
        def run():
            if self.column is None:
                self._begin_agent()
            label = self.blocks.get(key)
            if label is None:
                if heading:
                    title = Gtk.Label(label=heading, xalign=0)
                    title.get_style_context().add_class("muted")
                    self.column.pack_start(title, False, False, 0)
                    title.show()
                label = Gtk.Label(label="", xalign=0, wrap=True, selectable=True, max_width_chars=90)
                label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                if style:
                    label.get_style_context().add_class(style)
                self.column.pack_start(label, False, False, 0)
                label.show()
                self.blocks[key] = label
            label.set_text(text if replace else label.get_text() + text)
            self._pin()
            return False

        GLib.idle_add(run)

    def _append(self, text):
        self._write(("text", 0), text)

    def _set_status(self, text):
        GLib.idle_add(lambda: self.status.set_text(text or "") or False)

    def _settled(self):
        def run():
            self.column = None
            self.blocks = {}
            self._set_busy(False)
            return False

        GLib.idle_add(run)

    def _send(self, record):
        if self.proc.poll() is not None:
            self._append("The agent has stopped.")
            return
        line = json.dumps(record).encode() + b"\n"
        with self.write_lock:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()

    def _read_stderr(self):
        log = ROOT / ".agent" / "chat-stderr.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("ab") as handle:
            for chunk in iter(lambda: self.proc.stderr.readline(), b""):
                handle.write(chunk)
                handle.flush()

    def _read_stdout(self):
        while self.alive:
            line = self.proc.stdout.readline()
            if not line:
                break
            self._record(line.decode("utf-8", "replace").rstrip("\r\n"))
        if self.alive and self.proc.poll() not in (None, 0):
            self._append("The agent exited.")
            self._settled()

    def _record(self, line):
        if not line:
            return
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return
        kind = record.get("type")
        if kind == "message_update":
            self._message_update(record.get("assistantMessageEvent") or {})
        elif kind == "message_end":
            message = record.get("message") or {}
            if message.get("role") == "assistant":
                self._assistant_message(message)
        elif kind == "tool_execution_start":
            name = str(record.get("toolName") or "a tool")
            self._set_status("Working")
            self._write(
                ("call", record.get("toolCallId")),
                name + _brief(record.get("args")),
                replace=True,
                style="tool",
            )
        elif kind == "tool_execution_end":
            name = str(record.get("toolName") or "a tool")
            if record.get("isError"):
                name += " failed"
            self._write(
                ("result", record.get("toolCallId")),
                _plain(record.get("result")),
                replace=True,
                style="tool",
                heading=name,
            )
        elif kind == "agent_settled":
            self._settled()
        elif kind == "response" and record.get("success") is False:
            self._append(record.get("error") or "The agent rejected that message.")
            self._settled()
        elif kind == "extension_ui_request" and record.get("method") in DIALOG:
            GLib.idle_add(lambda: self._dialog(record) or False)
        elif kind == "extension_ui_request" and record.get("method") == "notify":
            note = record.get("message") or ""
            if note:
                self._write(("note", record.get("id")), note, replace=True, style="muted")

    def _message_update(self, event):
        kind = event.get("type")
        index = event.get("contentIndex", 0)
        if kind == "thinking_delta" and event.get("delta"):
            self._set_status("Thinking")
            self._write(("think", index), event["delta"], style="think")
        elif kind == "thinking_end" and event.get("content"):
            self._set_status("Working")
            self._write(("think", index), event["content"], replace=True, style="think")
        elif kind == "text_delta" and event.get("delta"):
            self._set_status("Working")
            self._write(("text", index), event["delta"])
        elif kind == "text_end" and event.get("content"):
            self._write(("text", index), event["content"], replace=True)
        elif kind == "toolcall_end":
            call = event.get("toolCall") or {}
            self._write(
                ("call", call.get("id") or index),
                str(call.get("name") or "tool") + _brief(call.get("arguments")),
                replace=True,
                style="tool",
            )
        elif kind == "error":
            error = event.get("error") or {}
            self._append(error.get("errorMessage") or "The model stopped.")

    def _assistant_message(self, message):
        if message.get("errorMessage"):
            self._write(("error", 0), message["errorMessage"], replace=True)
        for index, block in enumerate(message.get("content") or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "thinking" and block.get("thinking"):
                self._write(("think", index), block["thinking"], replace=True, style="think")
            elif block.get("type") == "text" and block.get("text"):
                self._write(("text", index), block["text"], replace=True)
            elif block.get("type") == "toolCall":
                self._write(
                    ("call", block.get("id") or index),
                    str(block.get("name") or "tool") + _brief(block.get("arguments")),
                    replace=True,
                    style="tool",
                )

    def _dialog(self, request):
        body = Gtk.Label(label=request.get("message") or request.get("placeholder") or "", xalign=0, wrap=True, max_width_chars=36)
        title = Gtk.Label(label=request.get("title") or "PCBAgent", xalign=0)
        title.get_style_context().add_class("name")
        choices = Gtk.Box(spacing=8)
        choices.set_margin_top(6)

        def answer(fields):
            choices.destroy()
            payload = {"type": "extension_ui_response", "id": request.get("id")}
            payload.update(fields)
            self._send(payload)

        method = request.get("method")
        if method == "confirm":
            for label, fields in (("Yes", {"confirmed": True}), ("No", {"confirmed": False})):
                button = Gtk.Button(label=label)
                button.get_style_context().add_class("choice")
                button.connect("clicked", lambda _b, fields=fields: answer(fields))
                choices.pack_start(button, False, False, 0)
        elif method == "select":
            for option in request.get("options") or []:
                button = Gtk.Button(label=option)
                button.get_style_context().add_class("choice")
                button.connect("clicked", lambda _b, option=option: answer({"value": option}))
                choices.pack_start(button, False, False, 0)
        else:
            field = Gtk.TextView()
            field.get_buffer().set_text(request.get("prefill") or "")
            button = Gtk.Button(label="Send")
            button.get_style_context().add_class("choice")

            def send_field(_button):
                buf = field.get_buffer()
                answer({"value": buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)})

            button.connect("clicked", send_field)
            choices.pack_start(field, True, True, 0)
            choices.pack_start(button, False, False, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.pack_start(title, False, False, 0)
        col.pack_start(body, False, False, 0)
        col.pack_start(choices, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.pack_start(Gtk.Image.new_from_pixbuf(self.avatar), False, False, 0)
        row.pack_start(col, True, True, 0)
        self.messages.pack_start(row, False, False, 0)
        row.show_all()
        self._pin()
        return False


def main():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        sys.exit("No graphical desktop in this session. Open the chat from the GX10 desktop.")
    Chat()
    Gtk.main()


if __name__ == "__main__":
    main()
