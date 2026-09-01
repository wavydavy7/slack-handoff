# Handoff app

Type what you're handing off → Claude finds relevant Slack channels → edit the drafted
message → Send creates ready-to-send drafts in Slack (you fire each with one click there).

## How to run

Requirements: [Claude Code](https://claude.com/claude-code) (desktop app) with the Slack
connector authorized for your workspace. Claude acts as the app's backend, so messages are
searched and drafted under **your** Slack identity.

1. Clone this repo and open the folder in Claude Code.
2. Tell Claude: *"Read README.md and run the handoff app — start the server, open the
   preview, and run the watcher loop as the backend."*
3. Use the app in the preview pane. Keep the session open while you work; each request
   (channel search, drafting, sending) is processed by Claude within a few seconds.

Nothing posts to Slack automatically: "Send" creates drafts in your Slack, and you fire
each one yourself.

## Architecture

- `server.py` — stdlib HTTP server on 127.0.0.1:8931. Serves `index.html` and a file bridge:
  `POST /api/request` appends to `bridge/requests.jsonl`; `GET /api/response/<id>` returns
  `bridge/responses/<id>.json` (202 until it exists). The UI polls every 1.5s, 5-min timeout.
- `watch.sh` — blocks until `requests.jsonl` grows past `bridge/processed_count`, prints the
  new lines, exits. Claude runs it in the background; its exit re-invokes Claude, which
  processes the request (Slack channel search + message drafting, or draft creation on send),
  writes the response file, bumps `processed_count`, and restarts the watcher.
- Claude IS the backend: channel search uses the Slack MCP connector
  (`slack_search_channels` + `slack_search_public_and_private`), sending uses
  `slack_send_message_draft` (drafts, never direct posts — the user's click in Slack is the
  final approval).

## Request/response shapes

- prepare: `{type:"prepare", payload:{notes, who}}` →
  `{status:"ok", channels:[{id,name,meta,reason,preselected}],
    people:[{id,name,meta,reason,preselected}], draft}`
  `people` are likely pingers: Claude searches each relevant channel for the user's
  mention token (`<@Uxxxx> in:#channel` — the `to:me` modifier is unreliable) and ranks
  who @-mentions them most / most recently. Checked people become a trailing
  `cc <@Uxxxx>` line the UI keeps in sync with the checkboxes.
- send: `{type:"send", payload:{channels:[{id,name}], message}}` →
  `{status:"ok", results:[{channel, ok, detail}], note}`

## Ops

- Start server: the `handoff` entry in `.claude/launch.json` (or `python3 server.py`).
- The app only functions while a Claude session with the Slack connector is running the
  watcher loop.
