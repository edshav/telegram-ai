# telegram

A read-only Telegram MCP server for your own account, packaged as a Claude Code plugin. It lists,
searches and reads your chats and public channels; it never sends, edits, deletes or marks
anything as read.

Tools: `list_chats`, `find_chats`, `read_chat`, `search`, `read_post`.

## Requirements

- [uv](https://docs.astral.sh/uv/) on your `PATH`.
- Your own Telegram API app: create one at <https://my.telegram.org/apps> and note its `api_id`
  and `api_hash`.

## Install

```
/plugin marketplace add edshav/skills
/plugin install telegram@edshav
```

## Log in

Until you log in, every tool answers with the exact login command for your installed copy. Run it
in your own terminal (not through Claude), for example:

```sh
uv run --no-config --script ~/.claude/plugins/cache/<...>/server.py login
```

It asks for `api_id`, `api_hash`, your phone number, the login code and your 2FA password, then
writes `~/.config/telegram-mcp/credentials.json` (directory 700, file 600). Reconnect `telegram` in
`/mcp` or restart Claude Code. Run `login` again to switch accounts.

## Security

- `credentials.json` is full access to your Telegram account. Any program running as you can read
  it, including Claude's own tools. Don't share it and don't copy it to another machine: log in
  separately on each one (using one key from two places at once gets it revoked by Telegram).
- Every message the tools read is untrusted text that goes straight to the model: public channels,
  groups, and DMs from anyone who can message you. A message can try to make the agent read your
  private chats or the credentials file and send them somewhere. Consider the Claude Code sandbox
  with network and file restrictions.
- To revoke access, end the session in Telegram → Settings → Devices.
- On Windows file modes are not enforced; the file is protected only by your user profile.

## Limits

- After a network drop longer than a few seconds, or a Telegram flood wait longer than 30 s at
  startup, the server stops working for that Claude session: reconnect it in `/mcp`.
