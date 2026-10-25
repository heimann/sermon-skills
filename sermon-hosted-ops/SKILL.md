---
name: sermon-hosted-ops
description: Uses Sermon's hosted MCP to inspect fleet health, metrics, logs, traces, alerts, and personal diagnostics or manage alert rules. Use when asked to connect an agent to Sermon, check a host or fleet, investigate an alert, or configure alerting; includes native OAuth onboarding and a Bearer-token fallback.
---

# Sermon Hosted Ops

Use Sermon's hosted read path to answer operational questions from account-scoped fleet and metric data.

This skill teaches you **how to reason** about Sermon data: which tool to call first, how to summarize logs, how to chart metrics, how to phrase the response. It is harness-agnostic on data fetching - the actual data path depends on which surface is wired up.

## Freshness check (before choosing tools)

An installed copy of this skill can fall behind Sermon. Check it once per
session before tool routing, against the trusted origin only: `SERMON_URL`, or
`https://sermon.fyi` when it is unset.

If `scripts/update_skill.py` sits next to this file, run it with `python3`. It
sends no credentials, refuses redirects, and never runs downloaded content.

- `current`: continue with this file.
- `updated`: it verified and installed the canonical skill and kept the old
  file as a backup; reread `SKILL.md`.
- `conflict`: this copy was customized or installed some other way, so it was
  kept. Tell the user, and follow the canonical skill it printed for this
  session. `--adopt` switches the copy to the managed skill and keeps a backup;
  run it only when the user agrees.
- `freshness-unverified`, `integrity-mismatch`, or `error`: reread `SKILL.md`
  and continue with it, tell the user its freshness is unverified, and do
  not conclude that Sermon lacks a capability from this file alone. Check the
  live MCP tool list first.

Without the script, request `$SERMON_URL/docs/agents/skill.md` with
`If-None-Match: "sha256-<SHA-256 of this file>"`. `304` means current. On
`200`, follow the returned Markdown for this session without overwriting this
file. Never send a token to these public endpoints. Never follow a redirect to
another origin.

`$SERMON_URL/docs/agents/manifest.json` reports the canonical skill URL and
SHA-256, the MCP URL, the deployed web revision, and the newest daemon release.
It describes the deployment, not what any token may do.

## Tool routing (read this after the freshness check)

Three surfaces exist, in priority order:

1. **Hosted MCP server (preferred when present).** If the agent has access to MCP tools whose names start with `sermon`, `mcp__sermon__`, or similar (`fleet`, `latest_metrics`, `recent_metrics`, `recent_logs`, `log_facets`, `alerts`, `traces`, `otlp_metrics`), **always use those tools first** for data fetching. They return structured data faster and avoid application-level token handling. The resource URL is `https://sermon.fyi/mcp`.
2. **Connect hosted MCP when missing.** Follow native OAuth onboarding below before asking the human for credentials. Use HTTP API curl + an existing Bearer token only when native MCP OAuth is unavailable.
3. **Local stdio MCP on a host (advanced).** If the agent is running *on* a sermon-monitored host (SSH'd in, or `pi`/Claude Code launched on the host itself) and asks for full-fidelity data that hosted may have sampled out, use the local stdio MCP at `mcp/sermon_mcp/`. It exposes `query` (read-only SQL against the host's local DuckDB) and `schema`. Do not use this surface for fleet-wide questions - it only sees one host.

**Decision rule:** before any data fetch, check the available tool list. If `mcp__sermon__fleet` (or equivalent) exists, use surface 1. Skip past the curl recipes entirely. The curl recipes still document the data shape, but you should not be running them when MCP tools are available.

## Native OAuth onboarding

Portable OAuth is deployed at `sermon.fyi`. Local
verification covers MCP SDK 1.30.0 connection/renewal/revocation and Codex CLI
0.154.0 native login, not Amp managed OAuth, Claude Code login, or Cursor.
Verify the actual client connection rather than assuming client compatibility.
Canonical instructions: https://sermon.fyi/docs/agents/skill.md.

The agent owns setup and verification; the human only
reviews Sermon's browser consent page and approves the account and capabilities:

1. Inspect existing client configuration and tool lists. If `sermon` already
   points to `https://sermon.fyi/mcp`, authenticate or reconnect it instead of
   adding a duplicate.
2. Add a **personal** remote HTTP configuration without an Authorization header.
3. Start the client's native OAuth flow. Never request a copied token or code.
4. Request `read offline_access` for fleet reads and renewal; add
   `alert_rules_write` or `personal_diagnostics` only for a task that needs it.
   `personal_diagnostics` reads the user's conversation with the Sermon agent
   and its execution evidence, not unrelated iMessages. Renewal grants no tools.
   Sermon's approval page leaves writes and private diagnostics unchecked even
   if the client requests them. The human explicitly enables any needed extras.
5. Verify discovered tools, then call `fleet` and confirm the expected servers.
   For application-only telemetry, use `recent_logs` with `account_wide: true`
   and `limit: 100`. Use `log_facets` only with an enrolled server ID;
   account-wide coverage metadata is not exposed. An empty fleet does not mean failed auth.
   Report missing telemetry separately; do not install a daemon or configure
   ingestion unless asked. Never verify write scope by an unrequested mutation.

Discovery is published at
`/.well-known/oauth-protected-resource/mcp` and
`/.well-known/oauth-authorization-server`; Sermon uses public-client DCR at
`/oauth/register`, browser authorization at `/oauth/authorize`, tokens at
`/oauth/token`, and revocation at `/oauth/revoke`. `/mcp` remains unchanged.

Use the matching client commands:

```bash
# Amp managed personal remote MCP (works across local sessions and orbs)
amp mcp remote --personal list
amp mcp remote add Sermon https://sermon.fyi/mcp --auth oauth --personal
amp mcp remote --personal login Sermon
amp mcp remote --personal check Sermon
amp mcp remote --personal tools Sermon --refresh

# Claude Code user scope
claude mcp get sermon || claude mcp add --transport http --scope user sermon https://sermon.fyi/mcp
claude mcp login sermon
claude mcp get sermon

# Codex shared user configuration
codex mcp list
codex mcp add sermon --url https://sermon.fyi/mcp
codex mcp login sermon --oauth-client-registration dcr
```

Skip each `add` when the preceding inspection finds the same endpoint. In an Amp
orb, `amp mcp remote --personal login Sermon` prints an ampcode.com URL because
browser OAuth cannot run in the orb. Claude Code can pin least privilege with
`oauth.scopes` in an HTTP `add-json` entry. Codex prefers advertised
`scopes_supported` and may start login immediately on `add`; skip a second login
if it succeeded. Codex accepts the narrower read/renewal grant when optional
permissions remain unchecked on Sermon's consent page.

Cursor has no documented add/login CLI. Merge this into
`~/.cursor/mcp.json`, enable it under **Customize → MCP**, and complete the OAuth
prompt:

```json
{
  "mcpServers": {
    "sermon": {"url": "https://sermon.fyi/mcp"}
  }
}
```

Cursor documents OAuth for Streamable HTTP but not DCR behavior, refresh, or a
custom-server logout command. Treat all three as acceptance checks rather than
promises. Its documented static-client callbacks are irrelevant to Sermon's DCR
path.

On expiry, let the client refresh when `offline_access` was approved. A rejected
refresh or a 401 after one refresh requires native reauthorization; a 403
`insufficient_scope` requires fresh human approval for the missing capability.
A timeout, DNS/TLS failure, 5xx, or offline monitored host is an outage, not
revocation: preserve the connection and retry only safe reads with backoff.
Client logout clears local credentials; server-side access ends only after the
Sermon grant/token is revoked. Never blindly replay a write after an unknown
outcome.

The hosted read path can answer questions about enrolled servers, online/stale state, latest CPU/memory, recent metric windows, disks, process snapshots included in metric samples, recent hosted logs, alert rules/events, distributed traces, and OTLP application metrics. It cannot yet answer posture, SSH, firewall, deploy, or package-update questions unless the user provides that data separately.

## MCP tool reference (preferred surface)

Use these when the MCP server is wired. Field shapes match the curl responses below; the only difference is dispatch.

| MCP tool | Arguments | Equivalent curl path |
|---|---|---|
| `fleet` | (none) | `GET /api/agent/fleet` |
| `latest_metrics` | `server_id` | `GET /api/agent/servers/:id/metrics?limit=1` |
| `recent_metrics` | `server_id`, optional `limit` (max 500) | `GET /api/agent/servers/:id/metrics?limit=N` |
| `recent_logs` | `server_id`, optional `limit/since/until/priority/service/identifier/systemd_unit` | `GET /api/agent/servers/:id/logs?...` |
| `log_facets` | `server_id`, optional `since/until` | `GET /api/agent/servers/:id/logs/facets` |
| `alerts` | optional `events_limit` | `GET /api/agent/alert_rules` + `/api/agent/alert_events` |
| `traces` | optional `trace_id/service_name/status/server_id/since/until/limit` | `GET /api/agent/traces?...` |
| `otlp_metrics` | optional `metric_name/service_name/metric_type/server_id/since/until/limit` | `GET /api/agent/otlp_metrics?...` |

For `traces`, recent-slice mode excludes spans starting more than five minutes ahead of Sermon's server clock; a later `until` cannot widen that bound. Exact `trace_id` mode deliberately returns up to 10,000 stored account-scoped spans regardless of emitter clock skew, oldest-first by start time then ID, so use it when a known trace is missing from recent results.

Tool errors come back as `isError: true` with a string explanation in the content. Surface that to the user verbatim; do not retry blindly.

## Inputs you need (curl fallback only)

If the MCP tools are present, you don't need any of this - skip to the workflow + reasoning sections below. Read on only when falling back to the curl path.

- Agent read token generated from `https://sermon.fyi/connect`.
- Preferred token source: `SERMON_AGENT_TOKEN` environment variable.
- Fallback token source: `~/.sermon/agent-token`, if already provisioned.
- `SERMON_URL`: optional, defaults to `https://sermon.fyi`.

If neither token source exists, attempt native OAuth onboarding first. Existing
Amp identity-helper access can also be reused. Only for a client without native
OAuth, offer the manual-token fallback at `/connect` → Give my agent access.
Have the human store the credential in the client's secret settings, not chat.

Reading this guide does not require installing a skill package. Registering MCP,
browser approval, and a successful read verify access; installing prose does not.

## Secret handling

- Never print the token.
- Never write the token to a repo file, notes file, commit, or logs.
- Prefer reading it from `SERMON_AGENT_TOKEN`; fall back to `~/.sermon/agent-token`.
- If a token is pasted in chat, tell the user to revoke it after the task.
- Treat tokens as sensitive. Their authority depends on their scopes and may
  include alert-rule writes.

## API calls (curl fallback path)

Skip this whole section if MCP tools are wired - dispatch via the tool calls in the routing table above instead. The recipes below exist to (a) document the underlying data shape, and (b) work when MCP isn't registered.

Before API calls, resolve the token without printing it:

```bash
SERMON_URL="${SERMON_URL:-https://sermon.fyi}"
if [ -z "${SERMON_AGENT_TOKEN:-}" ] && [ -r "$HOME/.sermon/agent-token" ]; then
  SERMON_AGENT_TOKEN="$(tr -d '\n\r' < "$HOME/.sermon/agent-token")"
fi
if [ -z "${SERMON_AGENT_TOKEN:-}" ]; then
  echo "missing Sermon agent token; generate one at /connect and run the setup command" >&2
  exit 1
fi
```

Use `SERMON_URL=${SERMON_URL:-https://sermon.fyi}` when constructing commands.

### Fleet overview

```bash
curl -fsSL "$SERMON_URL/api/agent/fleet" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Response shape:

```json
{
  "generated_at": "2026-04-26T19:00:00Z",
  "servers": [
    {
      "id": "uuid",
      "name": "contabo-ny-1",
      "hostname": "contabo-ny-1",
      "last_seen_at": "2026-04-26T18:59:54Z",
      "online": true,
      "cpu_percent": 12.3,
      "mem_percent": 64.2,
      "mem_used": 1234567890,
      "mem_total": 8589934592,
      "daemon_version": "v0.0.1-rc4",
      "latest_daemon_version": "v0.0.1-rc4",
      "daemon_outdated": false
    }
  ]
}
```

### Alert rules and events

Track A static alerts ship with the daemon: every enrolled server gets five default rules (`stale`, `cpu_high_sustained`, `mem_high`, `disk_high`, `daemon_outdated`) auto-created on enrollment. Rules are configured via this API, never via a web rule-builder UI - the `/alerts/rules` page on sermon.fyi is read-only.

#### List rules

```bash
curl -fsSL "$SERMON_URL/api/agent/alert_rules" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Response:

```json
{
  "rules": [
    {
      "id": "uuid",
      "server_id": "uuid",
      "server_name": "contabo-ny-1",
      "name": "cpu_high_sustained",
      "metric": "cpu_percent",
      "op": "gt",
      "threshold": 90.0,
      "duration_seconds": 300,
      "notify_email": "ops@example.com",
      "notify_on_resolve": false,
      "enabled": true,
      "current_state": "idle",
      "state_changed_at": null
    }
  ]
}
```

Available metrics: `cpu_percent`, `mem_percent`, `disk_max_fill_percent`, `staleness_seconds`, `daemon_outdated_for_seconds`. Available ops: `gt`, `gte`, `lt`, `lte`, `eq`, `neq`. `duration_seconds: 0` evaluates the latest sample only; `> 0` evaluates the average over the window.

#### Create a rule

```bash
curl -fsSL "$SERMON_URL/api/agent/alert_rules" \
  -X POST \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "<uuid>",
    "name": "swap_pressure",
    "metric": "mem_percent",
    "op": "gt",
    "threshold": 95.0,
    "duration_seconds": 600,
    "notify_email": "ops@example.com",
    "notify_on_resolve": false
  }'
```

Returns `201` with the created rule, or `422` with `details` shaped per Ecto changeset errors.

#### Update / disable / delete

```bash
# Lower the CPU threshold or disable a noisy rule:
curl -fsSL "$SERMON_URL/api/agent/alert_rules/$RULE_ID" \
  -X PATCH \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"threshold": 80.0, "enabled": false}'

# Remove a rule entirely:
curl -fsSL "$SERMON_URL/api/agent/alert_rules/$RULE_ID" \
  -X DELETE \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

#### Recent fired events

```bash
curl -fsSL "$SERMON_URL/api/agent/alert_events?limit=50" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Returns recent events with `fired_at`, `resolved_at` (null while still firing), `state` (`firing` or `resolved`), and the `evidence` jsonb the evaluator captured.

```bash
curl -fsSL "$SERMON_URL/api/agent/alert_events/$EVENT_ID" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

The single-event response also includes a `copy_to_agent` field: a markdown brief identical to what gets emailed and what the `/alerts` LiveView Copy button renders. Quote that block back in chat to start an investigation.

#### When the user pastes a Sermon alert email

If the user drops an alert email block into the conversation, parse the fenced markdown brief: it carries server name + id, rule name + condition, observed value, evidence window, and suggested API calls. Run those calls via the workflow below to investigate.

### Recent metrics for one server

```bash
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/metrics?limit=60" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Response shape:

```json
{
  "server_id": "uuid",
  "samples": [
    {
      "id": "uuid",
      "hostname": "contabo-ny-1",
      "collected_at": "2026-04-26T18:59:54Z",
      "cpu_percent": 12.3,
      "cpu_user": 7.1,
      "cpu_system": 4.9,
      "cpu_iowait": 0.3,
      "mem_total": 8589934592,
      "mem_used": 1234567890,
      "mem_percent": 64.2,
      "swap_total": 0,
      "swap_used": 0,
      "processes": [
        {
          "pid": 97589,
          "name": "sermon-agent",
          "username": "dmeh",
          "state": "R",
          "cpu_percent": 3.7,
          "mem_rss": 45596672,
          "threads": 1
        }
      ],
      "disks": [],
      "log_stats": {
        "seen": 87,
        "uploaded": 20,
        "dropped": 67
      }
    }
  ]
}
```

Samples are returned oldest-to-newest.

### Recent logs for one server

```bash
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/logs?limit=100" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Optional filters:

- `limit`: number of recent log entries, default 60, max 500.
- `since`: ISO timestamp or Unix seconds; lower bound on `collected_at`.
- `until`: ISO timestamp or Unix seconds; upper bound on `collected_at`.
- `priority`: syslog severity threshold. Names work: `emerg`, `alert`, `crit`, `critical`, `err`, `error`, `warning`, `warn`, `notice`, `info`, `debug`. `priority=warning` returns warning and more severe entries (`0..4`).
- `unit`: compatibility grouping key. New daemon versions set this to `identifier` when present, otherwise `systemd_unit`.
- `identifier`: exact `SYSLOG_IDENTIFIER` match, e.g. `tailscaled`, `sshd`, `sermon-agent`.
- `systemd_unit`: exact `_SYSTEMD_UNIT` match, e.g. `tailscaled.service`, `ssh.service`.
- `service`: convenience alias matching any of `unit`, `identifier`, or `systemd_unit`.

Examples:

```bash
# Warnings and errors across the server
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/logs?limit=100&priority=warning" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"

# Logs for a known service-ish value
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/logs?limit=100&service=tailscaled" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"

# Logs in the same UTC time window as a metric spike
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/logs?since=2026-04-26T22:00:00Z&until=2026-04-26T22:15:00Z&limit=200" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Response shape:

```json
{
  "server_id": "uuid",
  "logs": [
    {
      "id": "uuid",
      "collected_at": "2026-04-26T22:51:20Z",
      "source": "systemd",
      "unit": "sermon-dogfood-test",
      "identifier": "sermon-dogfood-test",
      "systemd_unit": null,
      "priority": 5,
      "pid": 1234,
      "message": "sermon hosted log smoke after journal wrapper"
    }
  ]
}
```

Logs are returned newest-to-oldest. Hosted log upload is not historical backfill: the daemon follows journald from its start time and uploads sampled recent batches as it samples. Hosted upload is intentionally a sketch, not full log retention. Current daemon releases prefer warnings/errors first and cap hosted upload at 20 log lines per ingest; local DuckDB remains the fuller source of truth.

### Log facets for one server

Use facets before narrowing when you do not know the right service/unit name:

```bash
curl -fsSL "$SERMON_URL/api/agent/servers/$SERVER_ID/logs/facets?since=2026-04-26T22:00:00Z" \
  -H "Authorization: Bearer $SERMON_AGENT_TOKEN"
```

Response shape:

```json
{
  "server_id": "uuid",
  "coverage": {
    "total": 801,
    "oldest_collected_at": "2026-04-26T23:18:59Z",
    "newest_collected_at": "2026-04-26T23:23:19Z",
    "retention_seconds": 259200
  },
  "sources": [{"value": "systemd", "count": 100}],
  "units": [{"value": "tailscaled", "count": 42}],
  "identifiers": [{"value": "tailscaled", "count": 42}],
  "systemd_units": [{"value": "tailscaled.service", "count": 42}],
  "priorities": [{"priority": 4, "count": 3}]
}
```

Process snapshots are intentionally narrow:

- Use `name`, not `cmd`, as the process label.
- Use `username`, not `user`, for ownership.
- Use `mem_rss` bytes for process memory; there is no per-process `mem_percent` field.
- `cmdline` is intentionally omitted from hosted ingest because command lines can contain secrets.
- To display memory, convert `mem_rss` to MiB/GiB. Do not print `mem=0.00%` unless you calculated it against host memory yourself.

## Workflow

1. Read fleet state first.
2. Match servers by exact `name`; if the user gives a fuzzy name, list candidates and pick the obvious one only when unambiguous.
3. For fleet-health questions, summarize all servers from `/fleet` and stop unless a server looks stale or the user asks for details.
4. For a specific server, fetch recent metrics with `limit=60` unless the user asks for a different window.
5. If the user asks about logs, errors, crashes, failed services, auth/SSH events, or "why" something happened, fetch recent logs with `limit=100`. Add `priority=warning` when looking for problems.
6. If you do not know the right service/unit value, call `/logs/facets` first and inspect observed `units`, `identifiers`, `systemd_units`, and `priorities`.
7. For service-specific log questions, use `service=<name>` first. If no rows return, retry with exact observed `identifier` or `systemd_unit` from facets.
8. For metric/log correlation, use metric sample timestamps to set `since` and `until` around the interesting window.
9. Use `coverage` from `/logs/facets` to state the hosted log coverage window. If the incident predates `oldest_collected_at`, say hosted logs cannot answer it and suggest host-local journald for that exact window.
10. Use metric `log_stats` to say when hosted logs are sampled/incomplete. If `dropped > 0`, explicitly say hosted logs are partial.
11. Ground every conclusion in returned fields. Include timestamps, sample counts, log counts, and any filters used.
12. State API limits explicitly when relevant: posture is not available through this API yet; hosted logs are recent/sampled/capped and not full journal search.
13. For alert-related questions: list rules first to show what's being watched, fetch recent events to surface what has fired, and follow the alert's evidence window (when present) into metrics and logs queries to ground the investigation.
14. When the user pastes a Sermon alert email or its Copy-to-agent block, treat the embedded `Server`, `Rule`, and `Window` lines as the starting point. Run the suggested API calls in the email body verbatim where given.

## How to reason about the data

- `online: true` means Sermon's current online window considers the latest sample fresh.
- `last_seen_at: null` means the server has never reported a sample.
- A server can have an active enrollment but no samples yet; treat that as an install/daemon/ingestion problem, not host health.
- For recent metrics:
  - Look at latest value and rough trend over the sample window.
  - Do not invent averages unless you calculate them from the samples.
  - If only one or two samples exist, say the window is too small for trend claims.
  - Disk and process data are per-sample snapshots; use them as clues, not proof of causality.
- For process questions:
  - Sort top CPU by `cpu_percent` descending.
  - Sort top memory by `mem_rss` descending, not by a missing `mem_percent` field.
  - Show `name`, `pid`, `username`, `cpu_percent`, and memory as MiB.
  - If the user asks for exact command lines, say hosted Sermon omits them for secret-safety; suggest SSH `ps` only if they want host-local follow-up.
- For log questions:
  - `source` is currently `systemd` for journald entries.
  - `identifier` comes from journald `SYSLOG_IDENTIFIER`.
  - `systemd_unit` comes from journald `_SYSTEMD_UNIT`.
  - `unit` is a compatibility grouping key: identifier first, otherwise systemd unit.
  - `priority` follows syslog severity: `0` emerg, `1` alert, `2` crit, `3` err, `4` warning, `5` notice, `6` info, `7` debug. Lower is more severe.
  - Start with facets or broad recent logs, then narrow with `priority`, `service`, `identifier`, `systemd_unit`, and time bounds.
  - Prefer summaries over raw rows: group by priority and identifier/systemd unit, then show at most 5-10 representative lines unless the user asks for raw JSON.
  - Do not dump full JSON responses into the answer by default. Use JSON internally as evidence, then format it for the human.
  - Do not claim absence of an event from a small window as proof it never happened. Say "not present in the recent hosted log window."
  - Messages are capped/truncated by Sermon, so very long log lines may be incomplete.
  - Hosted logs are sampled under volume. If `log_stats.dropped > 0`, say the hosted log slice is incomplete and suggest SSH/local DuckDB if the user needs exhaustive logs.
- For daemon version questions:
  - Use `daemon_version`, `latest_daemon_version`, and `daemon_outdated` from `/fleet`.
  - If `daemon_outdated` is true, say the web UI can provide a copyable update command; do not invent remote update execution.

## Charting

When the user asks for a graph, chart, trend, spike, baseline, or "what changed over time", fetch recent metrics and render a terminal chart. Prefer ASCII/terminal output because the operator is already in an agent session.

Use these defaults:

- CPU chart: `collected_at` vs `cpu_percent`.
- Memory chart: `collected_at` vs `mem_percent`.
- Window: `limit=60` unless the user asks otherwise.
- Include sample count, first timestamp, last timestamp, and timezone in the caption.
- Treat API timestamps as UTC. If you display local clock labels, say so.
- If one spike dominates the y-axis and hides baseline variation, offer or render a second zoomed chart excluding the spike.
- If only one or two samples exist, do not chart; say there is not enough data.

A good terminal chart path is `plotext` when available:

```bash
uv run --quiet --with plotext python <<'PY'
import json
from datetime import datetime
import plotext as plt

# Load JSON from a saved API response or stdin.
d = json.load(open('/tmp/sermon-metrics.json'))
samples = d['samples']
times = [datetime.fromisoformat(s['collected_at'].replace('Z', '+00:00')) for s in samples]
cpu = [s['cpu_percent'] for s in samples]

plt.plot([t.strftime('%H:%M:%S') for t in times], cpu, marker='braille')
plt.title('CPU%')
plt.ylim(0, max(cpu) * 1.1 if cpu else 1)
plt.plotsize(90, 22)
plt.theme('clear')
plt.show()
PY
```

Do not let the chart replace the interpretation. After the chart, summarize whether the shape is steady, spiky, rising, falling, or too sparse to call.

## Response style

Prefer this structure:

```markdown
## Sermon snapshot
- Fleet: N servers, M online, K stale/offline
- Time: <generated_at or latest sample time>

## Findings
- <server>: <evidence-backed summary>

## Limits
- <what Sermon cannot answer yet from hosted data>

## Next checks
- <1-3 concrete commands or API queries, if needed>
```

For a single-server question:

```markdown
## <server> status
- Online: yes/no
- Last seen: <timestamp>
- Latest CPU: <value>
- Latest memory: <value>
- Recent window: <sample count>, <first timestamp> to <last timestamp>

## Read
<short evidence-backed interpretation>

## Recent logs
- Window: <log count> entries, newest first
- Notable units: <unit counts or examples>
- Warnings/errors: <summary with timestamps>

## Next
<one useful follow-up>
```

## Troubleshooting

- `401 invalid_agent_token`: token missing, mistyped, revoked, or using an ingestion key instead of an agent token. Agent tokens start with `sagt_`; ingestion keys start with `serm_`.
- `404 server_not_found`: server ID is not in the token's account, was deleted, or the wrong ID was used.
- Empty `servers`: the account has no enrolled servers yet, or the token belongs to a different account than expected.
- Empty `samples`: the server exists but has not ingested metrics yet.

## Examples

User: "Check Sermon. Is contabo healthy?"

Action:
1. Fetch `/api/agent/fleet`.
2. Find `contabo-ny-1`.
3. Fetch `/api/agent/servers/:id/metrics?limit=60`.
4. Answer with online state, latest CPU/memory, sample window, and API limits.

User: "Anything weird in my fleet?"

Action:
1. Fetch `/api/agent/fleet`.
2. Count online/stale servers.
3. Flag servers with missing `last_seen_at`, `online: false`, high latest CPU/memory, or missing names/hostnames.
4. Fetch per-server metrics only for flagged servers.
