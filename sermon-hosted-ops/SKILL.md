---
name: sermon-hosted-ops
description: Use this skill whenever the user asks an AI agent to inspect Sermon-hosted fleet health, answer questions about enrolled servers, check whether a host is online/stale, summarize recent CPU or memory behavior, or investigate basic host metric symptoms through sermon.fyi. This is the current hosted Sermon read path before MCP exists, so use it even if the user says "check Sermon", "what's happening on contabo", "look at my fleet", or "is any server unhealthy" without explicitly mentioning the API.
---

# Sermon Hosted Ops

Use Sermon's hosted read API to answer operational questions from account-scoped fleet and metric data.

The current API is intentionally narrow and read-only. It can answer questions about enrolled servers, online/stale state, latest CPU/memory, recent metric windows, disks, process snapshots included in metric samples, and recent hosted logs. It cannot yet answer alert, posture, SSH, firewall, deploy, or package-update questions unless the user provides that data separately.

## Inputs you need

- Agent read token generated from `https://sermon.fyi/agents`.
- Preferred token source: `SERMON_AGENT_TOKEN` environment variable.
- Fallback token source: `~/.sermon/agent-token`, created by the setup command shown after token generation.
- `SERMON_URL`: optional, defaults to `https://sermon.fyi`.

If neither token source exists, ask the user to go to `/agents`, generate an agent token, and run the displayed setup command. Do not ask them to paste long-lived tokens into chat unless they explicitly accept revoking it afterward.

Setup command shape:

```fish
npx --yes skills add heimann/sermon-skills --skill sermon-hosted-ops --agent claude-code --global --copy --full-depth -y
mkdir -p ~/.sermon
printf '%s\n' '<token from /agents>' > ~/.sermon/agent-token
chmod 600 ~/.sermon/agent-token
```

Start a fresh Claude Code session after installing so the skill metadata is loaded.

## Secret handling

- Never print the token.
- Never write the token to a repo file, notes file, commit, or logs.
- Prefer reading it from `SERMON_AGENT_TOKEN`; fall back to `~/.sermon/agent-token`.
- If a token is pasted in chat, tell the user to revoke it after the task.
- These tokens are read-only, but they expose fleet metadata and recent samples, so treat them as sensitive.

## API calls

Before API calls, resolve the token without printing it:

```bash
SERMON_URL="${SERMON_URL:-https://sermon.fyi}"
if [ -z "${SERMON_AGENT_TOKEN:-}" ] && [ -r "$HOME/.sermon/agent-token" ]; then
  SERMON_AGENT_TOKEN="$(tr -d '\n\r' < "$HOME/.sermon/agent-token")"
fi
if [ -z "${SERMON_AGENT_TOKEN:-}" ]; then
  echo "missing Sermon agent token; generate one at /agents and run the setup command" >&2
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
12. State API limits explicitly when relevant: alerts and posture are not available through this API yet; hosted logs are recent/sampled/capped and not full journal search.

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
