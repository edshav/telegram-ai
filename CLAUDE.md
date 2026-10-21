# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only Telegram MCP server for the user's own account, built on Telethon (user API, not a bot).
It is a single PEP 723 script, `server.py`: dependencies live in its `# /// script` header, so there is
no `pyproject.toml` and no lockfile. Claude Code spawns it over stdio as the `telegram` MCP server
(tools `list_chats`, `find_chats`, `read_chat`, `search`).

## Commands

```sh
uv run --env-file .env --script server.py login   # one-time interactive login (phone, code, 2FA)
uv run --env-file .env --script server.py         # run the MCP server on stdio
```

`.env` provides `TG_API_ID` and `TG_API_HASH`. There are no tests or linters. To check a change, restart the
Claude Code session (it respawns the server) and call the MCP tools.

## Constraints that span the file

- **stdout is the MCP wire.** Nothing on the server path may print or prompt. That is why `lifespan`
  calls `client.connect()` and fails if the session isn't authorized, and why the interactive
  `client.start()` lives only in the `login` subcommand.
- **Read-only by design.** The tools only read dialogs and messages. Adding anything that sends, edits,
  deletes or marks as read changes what the server is.
- **`telegram.session` is the account credential.** It's a Telethon SQLite session (with a `-journal`
  file), gitignored and chmod 600. It must never be read, copied or committed. Two processes on the same
  session at once (e.g. `login` while the server runs) can lock it or trip Telegram's duplicate-auth-key
  check.
- **Numeric chat ids resolve only after `get_dialogs()`.** `lifespan` calls it once at startup to cache
  access hashes. Tools take chat ids as printed by `list_chats`, or a public `@username`
  (from `find_chats`), which Telethon resolves and reads without joining.
- **Output is plain text lines built by `fmt`**, with dates in local time. `MAX_LIMIT` caps every
  `limit` argument and `MAX_TEXT` truncates message text, which keeps tool output small for the model.
  `fmt` still appends the sender's `@username` and a `[links: …]` tail (hidden link URLs, @mentions,
  t.me/wa.me links from the full text), so contacts survive truncation.
- Telethon is pinned `<2`: v2 has a different API.
