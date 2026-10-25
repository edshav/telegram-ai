# /// script
# requires-python = ">=3.11"
# dependencies = ["telethon>=1.36,<2", "mcp>=1.10,<2"]
# ///
"""Read-only Telegram MCP server (your own account, via Telethon).

Login once in a terminal:  uv run --no-config --script server.py login
"""
import asyncio
import json
import os
import re
import struct
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import MessageEntityTextUrl
from telethon.utils import get_display_name

CREDS = Path.home() / ".config" / "telegram-mcp" / "credentials.json"
# addressed to the model: tool errors reach it, not the user
LOGIN_HINT = (
    "Not logged in. Ask the user to run this in their own terminal, outside Claude: "
    f'uv run --no-config --script "{Path(__file__).resolve()}" login, '
    "then reconnect telegram in /mcp or restart Claude Code. "
    "Do not run it yourself and do not ask for the login code or password."
)
MAX_LIMIT = 200
MAX_TEXT = 300
MAX_PHOTOS = 10  # a Telegram album holds at most 10 items

client: TelegramClient | None = None


def load_client() -> TelegramClient | None:
    """A client on the saved credentials, or None if the file is missing or broken in any way."""
    try:
        c = json.loads(CREDS.read_text())
        return TelegramClient(StringSession(c["session"]), int(c["api_id"]), str(c["api_hash"]))
    except (OSError, ValueError, KeyError, TypeError, OverflowError, struct.error):
        return None


def save_creds(api_id: int, api_hash: str, session: str) -> None:
    CREDS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CREDS.parent.chmod(0o700)  # mkdir's mode is ignored for an existing dir
    fd = os.open(CREDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    CREDS.chmod(0o600)  # os.open's mode applies only to a new file
    with os.fdopen(fd, "w") as f:
        json.dump({"api_id": api_id, "api_hash": api_hash, "session": session}, f)


def tg() -> TelegramClient:
    if client is None:
        raise RuntimeError(LOGIN_HINT)
    return client


@asynccontextmanager
async def lifespan(_):
    global client
    if c := load_client():
        # never c.start() here: it prompts on stdout, which is the MCP wire
        await c.connect()  # network errors still fail startup: accepted limit in the spec
        if await c.is_user_authorized():
            await c.get_dialogs()  # caches access hashes so numeric chat ids resolve
            client = c
    try:
        yield
    finally:
        client = None
        if c:
            await c.disconnect()


mcp = FastMCP("telegram", lifespan=lifespan)


def links(msg) -> list[str]:
    """Contacts a reader needs even when the text is truncated: hidden link URLs, @mentions, t.me/wa.me links."""
    found = [e.url for e in msg.entities or [] if isinstance(e, MessageEntityTextUrl)]
    found += re.findall(r"@\w{5,}|(?:t|wa)\.me/[^\s)\]]+", msg.message or "")
    return list(dict.fromkeys(found))


def fmt(msg, with_chat: bool = False, full: bool = False) -> str:
    text = msg.message or ""
    if not full:
        text = text.replace("\n", " ")
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "…"
    if found := links(msg):
        text = f"{text} [links: {' '.join(found)}]"
    if msg.media:
        text = f"{text} [{type(msg.media).__name__.removeprefix('MessageMedia')}]".strip()
    chat = f"{get_display_name(msg.chat)} ({msg.chat_id}) | " if with_chat else ""
    sender = get_display_name(msg.sender) or msg.sender_id
    if username := getattr(msg.sender, "username", None):
        sender = f"{sender} @{username}"
    return f"{chat}{msg.date.astimezone():%Y-%m-%d %H:%M} | #{msg.id} | {sender} | {text}"


@mcp.tool()
async def list_chats(unread_only: bool = False, limit: int = 50) -> str:
    """List chats, most recent first, as `id | title | unread N`. Pass the id to read_chat or search."""
    out = []
    async for d in tg().iter_dialogs():
        if unread_only and not d.unread_count:
            continue
        out.append(f"{d.id} | {d.name} | unread {d.unread_count}")
        if len(out) >= min(limit, MAX_LIMIT):
            break
    return "\n".join(out) or "No chats."


@mcp.tool()
async def find_chats(query: str, limit: int = 20) -> str:
    """Search Telegram's public directory for groups and channels, as `@username | title | members N`.
    Pass the @username to read_chat or search to read them without joining."""
    res = await tg()(SearchRequest(q=query, limit=min(limit, MAX_LIMIT)))
    out = [f"@{c.username} | {c.title} | members {getattr(c, 'participants_count', None) or '?'}"
           for c in res.chats if getattr(c, "username", None)]
    return "\n".join(out) or "Nothing found."


@mcp.tool()
async def read_chat(chat_id: int | str, limit: int = 50, since: str | None = None) -> str:
    """Last messages of a chat, oldest first, as `date | #id | sender | text` (local time).
    chat_id is an id from list_chats or a public @username (readable without joining).
    `since` is an ISO date/datetime (local time if no offset); older messages are skipped."""
    since_dt = datetime.fromisoformat(since).astimezone() if since else None
    msgs = []
    async for m in tg().iter_messages(chat_id, limit=min(limit, MAX_LIMIT)):
        if since_dt and m.date < since_dt:
            break
        msgs.append(fmt(m))
    return "\n".join(reversed(msgs)) or "No messages."


@mcp.tool()
async def search(query: str, chat_id: int | str | None = None, limit: int = 50) -> str:
    """Full-text search, newest first. chat_id is an id from list_chats or a public @username.
    Without chat_id searches all joined chats and prefixes each line with `chat (id)`."""
    out = [fmt(m, with_chat=chat_id is None)
           async for m in tg().iter_messages(chat_id, search=query, limit=min(limit, MAX_LIMIT))]
    return "\n".join(out) or "Nothing found."


@mcp.tool(structured_output=False)
async def read_post(chat_id: int | str, message_id: int, photos: bool = True) -> list:
    """One message untruncated, plus the photos of its album when `photos` is true.
    message_id is the `#id` from read_chat or search; any message of an album finds the whole album."""
    c = tg()
    msg = await c.get_messages(chat_id, ids=message_id)
    if not msg:
        return ["No such message."]
    album = [msg]
    if msg.grouped_id:
        near = await c.get_messages(chat_id, ids=list(range(message_id - MAX_PHOTOS + 1, message_id + MAX_PHOTOS)))
        album = [m for m in near if m and m.grouped_id == msg.grouped_id]
    out = ["\n".join(fmt(m, full=True) for m in album if m.message) or fmt(msg, full=True)]
    if photos:
        for m in album:
            if m.photo:
                # 800px "x" size keeps each image small for the model; fall back to the largest
                data = await m.download_media(bytes, thumb="x") or await m.download_media(bytes)
                out.append(Image(data=data, format="jpeg"))
    return out


async def login():
    print("Get an api_id and api_hash by creating an app at https://my.telegram.org/apps")
    api_id = int(input("api_id: "))
    api_hash = input("api_hash: ").strip()
    c = TelegramClient(StringSession(), api_id, api_hash)
    await c.start()  # prompts for phone, code and 2FA password
    save_creds(api_id, api_hash, c.session.save())
    print("Logged in as", get_display_name(await c.get_me()), "- credentials saved to", CREDS)
    await c.disconnect()


if __name__ == "__main__":
    if sys.argv[1:] == ["login"]:
        asyncio.run(login())
    else:
        mcp.run()
