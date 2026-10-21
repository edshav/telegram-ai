# /// script
# requires-python = ">=3.11"
# dependencies = ["telethon>=1.36,<2", "mcp>=1.10,<2"]
# ///
"""Read-only Telegram MCP server (your own account, via Telethon).

Login once in a terminal:  uv run --env-file .env --script server.py login
"""
import asyncio
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import MessageEntityTextUrl
from telethon.utils import get_display_name

SESSION = Path(__file__).with_name("telegram.session")
MAX_LIMIT = 200
MAX_TEXT = 300

client: TelegramClient


def make_client() -> TelegramClient:
    return TelegramClient(str(SESSION), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])


@asynccontextmanager
async def lifespan(_):
    global client
    client = make_client()
    # never client.start() here: it prompts on stdout, which is the MCP wire
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Not logged in: run `uv run --env-file .env --script server.py login` in a terminal")
    await client.get_dialogs()  # caches access hashes so numeric chat ids resolve
    try:
        yield
    finally:
        await client.disconnect()


mcp = FastMCP("telegram", lifespan=lifespan)


def links(msg) -> list[str]:
    """Contacts a reader needs even when the text is truncated: hidden link URLs, @mentions, t.me/wa.me links."""
    found = [e.url for e in msg.entities or [] if isinstance(e, MessageEntityTextUrl)]
    found += re.findall(r"@\w{5,}|(?:t|wa)\.me/[^\s)\]]+", msg.message or "")
    return list(dict.fromkeys(found))


def fmt(msg, with_chat: bool = False) -> str:
    text = (msg.message or "").replace("\n", " ")
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
    return f"{chat}{msg.date.astimezone():%Y-%m-%d %H:%M} | {sender} | {text}"


@mcp.tool()
async def list_chats(unread_only: bool = False, limit: int = 50) -> str:
    """List chats, most recent first, as `id | title | unread N`. Pass the id to read_chat or search."""
    out = []
    async for d in client.iter_dialogs():
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
    res = await client(SearchRequest(q=query, limit=min(limit, MAX_LIMIT)))
    out = [f"@{c.username} | {c.title} | members {getattr(c, 'participants_count', None) or '?'}"
           for c in res.chats if getattr(c, "username", None)]
    return "\n".join(out) or "Nothing found."


@mcp.tool()
async def read_chat(chat_id: int | str, limit: int = 50, since: str | None = None) -> str:
    """Last messages of a chat, oldest first, as `date | sender | text` (local time).
    chat_id is an id from list_chats or a public @username (readable without joining).
    `since` is an ISO date/datetime (local time if no offset); older messages are skipped."""
    since_dt = datetime.fromisoformat(since).astimezone() if since else None
    msgs = []
    async for m in client.iter_messages(chat_id, limit=min(limit, MAX_LIMIT)):
        if since_dt and m.date < since_dt:
            break
        msgs.append(fmt(m))
    return "\n".join(reversed(msgs)) or "No messages."


@mcp.tool()
async def search(query: str, chat_id: int | str | None = None, limit: int = 50) -> str:
    """Full-text search, newest first. chat_id is an id from list_chats or a public @username.
    Without chat_id searches all joined chats and prefixes each line with `chat (id)`."""
    out = [fmt(m, with_chat=chat_id is None)
           async for m in client.iter_messages(chat_id, search=query, limit=min(limit, MAX_LIMIT))]
    return "\n".join(out) or "Nothing found."


async def login():
    c = make_client()
    await c.start()  # prompts for phone, code and 2FA password
    SESSION.chmod(0o600)
    print("Logged in as", get_display_name(await c.get_me()))
    await c.disconnect()


if __name__ == "__main__":
    if sys.argv[1:] == ["login"]:
        asyncio.run(login())
    else:
        mcp.run()
