# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only Telegram MCP server for the user's own account, built on Telethon (user API, not a bot),
shipped as the Claude Code plugin `telegram` from the `edshav` marketplace (`edshav/skills`).
`server.py` is a single PEP 723 script: dependencies live in its `# /// script` header, so there is
no `pyproject.toml` and no lockfile. `.claude-plugin/plugin.json` registers it as a stdio MCP server
(tools `mcp__plugin_telegram_telegram__list_chats`, `find_chats`, `read_chat`, `search`, `read_post`).

## Commands

```sh
uv run --no-config --script server.py login   # one-time interactive login (api_id/hash, phone, code, 2FA)
uv run --no-config --script server.py         # run the MCP server on stdio
claude --plugin-dir .                         # dev loop: load this checkout as the plugin
```

There are no tests or linters. The installed plugin runs the cached GitHub copy, so to check a local
change start Claude Code with `--plugin-dir` and call the MCP tools.

## Constraints that span the file

- **stdout is the MCP wire.** Nothing on the server path may print or prompt. `lifespan` only
  `connect()`s; the interactive `client.start()` lives in the `login` subcommand.
- **Not logged in is not a crash.** Missing, broken or revoked credentials leave `client` as `None`,
  and every tool goes through `tg()`, which raises `LOGIN_HINT` as a tool error. The hint is
  addressed to the model and tells it not to run `login` itself.
- **`--no-config` on every `uv run`.** The server starts in whatever project Claude Code was opened in;
  without it uv would honour that project's `uv.toml` and could install packages from its index.
- **Read-only by design.** The tools only read dialogs and messages. Adding anything that sends, edits,
  deletes or marks as read changes what the server is.
- **`~/.config/telegram-mcp/credentials.json` is the account credential.** It holds `api_id`,
  `api_hash` and a Telethon `StringSession` string; directory 700, file 600. It must never be read,
  printed, copied or committed. The server loads it into an in-memory session and never writes to
  disk, so any number of Claude sessions can run the server at once.
- **Numeric chat ids resolve only after `get_dialogs()`.** `lifespan` calls it once at startup to cache
  access hashes. Tools take chat ids as printed by `list_chats`, or a public `@username`
  (from `find_chats`), which Telethon resolves and reads without joining.
- **Output is plain text lines built by `fmt`**, with dates in local time. `MAX_LIMIT` caps every
  `limit` argument and `MAX_TEXT` truncates message text, which keeps tool output small for the model;
  `read_post` returns one message (or album) untruncated with its photos as images.
  `fmt` still appends the sender's `@username` and a `[links: …]` tail (hidden link URLs, @mentions,
  t.me/wa.me links from the full text), so contacts survive truncation.
- Telethon is pinned `<2`: v2 has a different API.
