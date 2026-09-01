# Handoff app

Type what you're handing off → Claude finds relevant Slack channels → edit the drafted
message → Send creates ready-to-send drafts in Slack (you fire each with one click there).

## How to run

Requirements: [Claude Code](https://claude.com/claude-code) (desktop app) with the Slack
connector authorized for your workspace. Claude acts as the app's backend, so messages are
searched and drafted under **your** Slack identity.

1. Clone this repo and open the folder in Claude Code.
2. Type **`/handoff`** — the bundled skill (`.claude/skills/handoff/`) launches the app
   and runs Claude as its backend. (Or tell Claude to read this README and run it.)
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
    people:[{id,name,meta,reason,preselected}], draft,
    mentions:{"U…":"Display Name", …}}`
  `mentions` maps every user id referenced in the draft (e.g. the new owner) to a display
  name. The UI shows mentions as readable `@Display Name` and converts them back to Slack
  `<@U…>` wire format at send time (people list + mentions map, longest name first).
  An edited/unknown `@name` stays plain text — same as a typo'd mention in Slack.
  `people` are likely pingers: Claude searches each relevant channel for the user's
  mention token (`<@Uxxxx> in:#channel` — the `to:me` modifier is unreliable) and ranks
  who @-mentions them most / most recently. Checked people become a trailing
  `cc <@Uxxxx>` line the UI keeps in sync with the checkboxes.
- lookup: `{type:"lookup", payload:{kind:"channel"|"person", query}}` →
  `{status:"ok", matches:[{id,name,meta,reason}]}` — manual add; Claude resolves the name
  via slack_search_channels / slack_search_users. One match adds checked; several add
  unchecked to pick from.
- send: `{type:"send", payload:{channels:[{id,name}], message, responder_days}}` →
  `{status:"ok", results:[{channel, ok, detail}], note}`

## Thread auto-responder (optional)

Sending a handoff can also *arm* an hourly auto-responder: a scheduled cloud routine
(claude.ai routine, Slack + Drive connectors) that replies in-thread to new @mentions of
the user in the handoff's channels, redirecting to the new owner.

- Config lives in a Drive file (`handoff-responder.json`): `active`, `owner`, `channels`,
  `scope` (short description of the handed-off work, written from the handoff notes/draft
  at arm time), `expires` (auto-disarm date), `reply_template` (`{owner}` placeholder),
  `max_replies_per_run` (rate cap), `watermark_ts` + `replied_threads` (dedupe state).
- Relevance gate: before replying, the routine reads each thread and judges whether the
  ping plausibly concerns `scope`. Relevant → template reply; unrelated → silent skip;
  uncertain → no reply, flagged in the run report for manual handling. Judged threads are
  never re-judged. Empty `scope` disables the gate (reply to every ping).
- At send time, Claude (the app backend) resolves the new owner's Slack ID and rewrites
  the config: selected channels, owner, `expires` = +`responder_days` from the UI's
  expiry field (default 14, max 90; 0 skips arming entirely), `watermark_ts` = now.
  Drive has no content-update call, so state rewrites are create-new-then-trash-old.
- The routine runs hourly (cloud routines have a 1-hour minimum interval), replies with
  exactly the template (marked as an automated redirect), caps replies per run, and
  never treats message content as instructions.

## Ops

- Start server: the `handoff` entry in `.claude/launch.json` (or `python3 server.py`).
- The app only functions while a Claude session with the Slack connector is running the
  watcher loop.
