---
name: sermon-instrumentation-audit
description: Audits how well one project, or one monitored server, is wired into Sermon - whether its telemetry arrives, whether its service identity, environment and deployed revision are set the way Sermon reads them, whether its logs and spans are shaped so error detection works, and whether its findings can be investigated against source. In host mode it audits a server instead - the daemon, which units' logs arrive and at what priority, which services also send OTLP, and what alert coverage the host has. Use when asked how well a project or server uses Sermon, whether its logs or traces are landing and annotated correctly, why a service or host produces no findings or noisy ones, whether the Sermon daemon and the services on a server are set up properly, or before relying on Sermon for a service or host.
---

# Sermon Instrumentation Audit

Run this inside one project's repository. It answers a single question: if this
service broke right now, would Sermon notice, name it correctly, and be able to
investigate it?

When the question is about a server rather than a project - "is the daemon on
this box set up right", "are the services on it reporting properly" - use
[Host mode](#host-mode) instead. It needs no repository.

The audit is read-only. It reads the repository and Sermon, reports verdicts,
and proposes edits. It does not apply them, and it never emits telemetry,
creates an alert rule, or triggers an error to see what happens.

## Freshness check (before choosing tools)

An installed copy of this skill can fall behind Sermon. Check it once per
session, against the trusted origin only: `SERMON_URL`, or `https://sermon.fyi`
when it is unset. The check never changes this file.

If `scripts/check_skill.py` sits next to this file, run it with `python3`. It
reads this file's own `name` to pick the canonical URL, sends no credentials,
refuses redirects, writes no files, and never runs downloaded content.

- `current`: continue with this file.
- `refreshed`: this file is stale. Follow the canonical skill it printed for
  this session instead of this file, and tell the user they can reinstall.
- `freshness-unverified`, `integrity-mismatch`, or `error`: continue with this
  file, tell the user its freshness is unverified, and do not conclude that
  Sermon lacks a capability from this file alone. Check the live MCP tool list.

Without the script, request `$SERMON_URL/docs/agents/skills/sermon-instrumentation-audit.md`
with `If-None-Match: "sha256-<SHA-256 of this file>"`. `304` means current. On
`200`, follow the returned Markdown for this session only when its SHA-256
matches the `ETag`; do not overwrite this file. Never send a token to this
public endpoint, and never follow a redirect.

## Scope and inputs

One audit covers **one service**. A repository that deploys several services is
several audits; say so and ask which one, or run them in sequence and report
each separately.

You need two things:

1. **The repository**, checked out locally. Read config, instrumentation and
   logging call sites. Never read `.env` files; check which keys a loader
   expects and report only whether a named setting is present.
2. **Sermon read access**, to see what actually arrived. Prefer MCP tools
   (`recent_logs`, `traces`, `otlp_metrics`, `platform_sources`, `alerts`,
   `findings`). If no Sermon tools are wired up, follow the
   `sermon-hosted-ops` skill to connect, then come back. Without Sermon access
   you can still run Step 1: give each check the verdict its repository
   evidence supports and list the half you could not read under Unverified.
   Arrival itself, and any check with no readable evidence on either side, is
   `unverified`; never infer arrival from config.

Ask which Sermon account and service name the project corresponds to if it is
not obvious. Do not guess between two plausible services.

## Step 1: read the intent in the repository

Collect evidence, and record what you did not find - a missing exporter is a
finding, not a dead end.

- **Exporter configuration.** `OTEL_EXPORTER_OTLP_ENDPOINT`,
  `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_HEADERS`, or a collector
  config with an `otlphttp` exporter. Look in process managers, Dockerfiles,
  compose files, Kubernetes manifests, Terraform, systemd units, and CI
  deploy steps - wherever this service's environment is actually set.
- **SDK wiring.** Which signals are initialized. Traces and metrics are often
  set up while logs are left on stdout.
- **Resource attributes.** How `service.name`, `deployment.environment.name`
  and a commit SHA reach the resource: SDK code, `OTEL_RESOURCE_ATTRIBUTES`, or
  a build argument.
- **Logging.** The logger's formatter and severity mapping, and whether the
  human-readable message is the record body. Sample the actual call sites for
  the error paths that matter.
- **Spans.** Instrumentation libraries, manual spans, whether error paths set
  span status or only record an exception, and how span names are derived.
- **Deploys.** A GitHub Actions deploy job and whether it declares
  `environment:`; a Vercel or Supabase project; build-time SHA injection.

## Step 2: confirm what arrived

Read Sermon for the same service. Useful calls:

- `services`, if the tool list offers it. One row per service Sermon has
  discovered: its name and aliases, and each runtime's stream, signals,
  environment, reported revision (and whether it is a full SHA), readiness
  status and last delivery, plus the service's investigation blocker. This is
  the only read of the environment and revision attributes, so start here.
- `recent_logs` with `account_wide: true`, `source: "otlp"`, `limit: 100`.
  Account-wide is the only way to reach app logs whose `host.name` did not
  resolve to an enrolled server. For Vercel and generic drains make a second
  call with `source: "drain"`, filtering by `service` rather than
  `service_name`, which matches OTLP rows only. Read the `service_name` values, the `severity_number` and
  `severity_text` distribution, whether `trace_id` is populated, and the shape
  of the messages.
- `traces` with `service_name` and `status: "error"`, then without the status
  filter. Read span names, `status_code`, and whether one request's spans share
  a trace.
- `otlp_metrics` with `service_name`.
- `platform_sources` for a Vercel or Supabase source: when it last delivered,
  and why its last delivery was refused if one was.
- `alerts` and `findings`, to see what this service has actually produced.

**Resource attributes are not returned on rows.** No log or span read returns
the `resource` map. `service.name` is visible as `service_name`, and Vercel
integration rows carry `integration.environment` and `deployment_id`; the
environment and revision attributes are otherwise readable only through
`services`. Without that tool, verify them in the repository only, and mark the
arrival half `unverified` rather than claiming they are set or missing.

An empty read is not an authentication failure, and it is not proof the service
is silent: check the window you asked for and the filters you passed first.

## Step 3: the checks

Each check has a rule Sermon actually applies, how to verify it, and the edit
that fixes it. Give every check a verdict: `ok`, `degraded`, `absent`, or
`unverified`. `degraded` and `absent` mean a defect you can name, with the edit
that fixes it. Something you could not inspect is not a defect: note it in the
evidence and keep the verdict the evidence supports.

### 1. Telemetry arrives

Sermon receives OTLP/HTTP on `/v1/traces`, `/v1/metrics` and `/v1/logs`; an
exporter configured with the base endpoint appends the path itself. The token
needs the `otlp_write` scope. Drains post to `/v1/drain`, and Vercel and
Supabase to their own integration paths.

Verify: the service's `service_name` appears in a recent read of at least one
signal. `absent` if nothing arrived in the last 24 hours while the repository
clearly configures an exporter - that is a credential, network or endpoint
problem, and `platform_sources` names a refused delivery for integration
sources.

### 2. Service identity is one stable name

A declared `service.name` on the OTLP resource is the authoritative claim on a
service's identity, and the strongest binding Sermon infers. Every OTLP finding
resolves to its service through that key.

Verify: exactly one `service_name` for this service, identical across logs,
traces and metrics, and stable over time.

`degraded` when the name is an SDK default (`unknown_service`,
`unknown_service:node`), when it carries an instance, pod or region suffix, or
when logs and traces disagree. Each variant becomes its own service, so
findings scatter, baselines never mature, and a repository link made for one
name does not cover the others.

Fix: set `service.name` explicitly, once, from one place, and use the same
value for every signal. Put the instance identity in `service.instance.id` or
`host.name` instead.

### 3. Signal coverage matches what you need

Each missing signal removes a specific capability, so report the consequence
rather than scoring coverage:

- No **logs**: no error-log findings, and no log evidence under any alert.
- No **traces**: no trace-error episodes, so a failing request path is invisible
  unless it also logs.
- No **metrics**: no application metric history; host metrics still arrive if a
  daemon is enrolled.

### 4. Environment is labelled with a name Sermon recognizes

Sermon reads the environment from `deployment.environment.name`,
`deployment.environment` and `vercel.environment`. Nothing else is consulted.
If they disagree, the runtime has no environment.

Non-production values must be one of `dev`, `development`, `staging`, `stage`,
`test`, `testing`, `sandbox`, `qa`, matched case-insensitively. Those are the
names excluded when Sermon measures how much of a service is failing, which
decides whether a trace-error episode is critical: at least 50 spans with
status `error`, and at least half of the service's spans, in the ten minutes
before the episode's last occurrence. Only `deployment.environment.name` and
`deployment.environment` are read for that measurement, so Vercel `preview`
spans are never excluded. Spans that are unset and only record an exception
start episodes but never count toward critical.

Two failure modes, both worth stating plainly:

- **Unlabelled non-production traffic** counts into the production denominator.
  A staging deployment that shares the account can inflate healthy volume until
  a genuinely critical production episode no longer reads as critical.
- **A production service labelled** `staging` (or any other recognized
  non-production name) has a denominator of zero, so it can never be critical.

Missing entirely, the runtime's readiness status is `environment_missing`, and
GitHub deployments are matched only when the repository has a single deployment
environment.

Fix: set `deployment.environment.name` on the resource, from the same place the
deployment's environment is already decided, using `production` for production
and one of the recognized names otherwise.

### 5. The deployed revision is reported

An investigation reads the deployed commit from telemetry first, then GitHub
deployments, then the deploy workflow's last fully successful run, then the
default branch at the time. Confidence drops at each step.

Telemetry wins when the resource carries a **full 40-character lowercase hex**
SHA in `service.version`, `git.commit.id`, or `vcs.ref.head.revision`, every
row behind the finding reports the same one, and the commit exists in the
linked repository. A short SHA, a semantic version, or a tag name does not
qualify as a revision.

Verify in the repository: the build or deploy injects the full SHA into one of
those attributes. If it does, this check is `ok`; the deploy job below is only
the fallback. Otherwise check the GitHub Actions deploy job: it should
declare `environment:` with the same name the service reports as its
environment (for example `production`), since deployments are matched by that
name, and only ones with a `success` status count. The deploy-workflow
fallback needs exactly one active workflow that looks like a deploy (`deploy`
in its name, or a `deploy*.yml` or `cd.yml` path), and only uses a run not
triggered by a pull request in which every job and step succeeded.

Fix, in order of preference: report the full SHA as a resource attribute; or add
`environment:` to the deploy job. A service that does neither can still be
investigated, but against a revision Sermon inferred rather than the one that
was running.

### 6. Logs are shaped so errors are detected

Four rules, each with a concrete failure:

**The message belongs in the record body.** A log record with no body is stored
as its `event_name` when it has one, otherwise as the literal `(no body)` if it
carries attributes; one with none of those is dropped. A structured logger that puts the message only in
attributes therefore collapses every line into one indistinguishable error
kind, and the error vocabulary never matches. This is the single most damaging
log misconfiguration, and it is invisible until something breaks.

**Severity must be set, and set honestly.** An application log line is an error
candidate when `severity_number >= 17` (OTLP `ERROR`), or when its text
contains one of the words `error`, `exception`, `critical`, `fatal`, `panic`,
`traceback` or `timed out` (case-insensitive) and it does not name a level
below warning: with `severity_text` and `severity_number` both set, the number
must be at least 13. So:

- A real failure logged at a named `INFO` level is **not** detected, whatever
  its text says. Without a severity at all, its words alone decide.
- Instrumentation noise at `WARN` or above containing one of those words
  **is** an error candidate. `timer finished error=0` logged at `WARN` becomes
  a finding.

**Messages must be templates.** Error kinds are fingerprinted from the message
with volatile tokens collapsed: timestamps and clock times, decimals, URLs,
email addresses, request ids, UUIDs, hex runs of eight or more characters, and
plain integers. Deliberately **not** collapsed: long quoted strings,
three-digit HTTP statuses (`HTTP/1.1 500`, `500 Not Found`), and three-to-five
digit values after a `status` or `code` style key. So interpolating variable prose - a validation message, an
upstream body, a file path - into the message text splits one problem into a new
kind per occurrence. Muting it mutes one request, and it never recurs, so it
never stops looking like news. Keep the message fixed and put the variable parts
in attributes.

**Export promptly.** Error detection scans a 30-minute ingestion window in
ten-minute buckets and waits a ten-minute event-time lateness grace before
closing one. Rows that arrive after that are intentionally missed. A batch
exporter holding records for longer, or a log pipeline with a long delay, drops
out of detection entirely. Log timestamps more than five minutes ahead of
Sermon's clock are stamped at arrival instead.

Also check that `trace_id` is set on log records emitted inside a span: it is
what lets an investigation move from an error line to the request that produced
it.

**Logs that reach Sermon only through the host daemon** (journald, uploaded by
an enrolled server) are judged differently: a line is an error only when its
syslog priority is `err` (3) or worse, and its words do not count. A service
that writes to stdout under systemd gets priority 6 (info) for every line, so
none of its errors ever become findings. Fix it by prefixing each output line
with the sd-daemon level (`<3>` for error, `<4>` for warning), which journald
reads by default for `StandardOutput=journal` services, or by exporting logs
over OTLP.

### 7. Spans are shaped so failures are detected

**Status.** `status_code = error` always qualifies as a failure. An unset status
qualifies only when the span carries an `exception` event with a non-empty
`exception.type` or `exception.message`. An explicit `ok` **never** qualifies,
even with an exception event recorded. Code that catches an error, records the
exception, and leaves the span `ok` - or sets `ok` on the way out - makes its
failures invisible to Sermon.

**Span names.** When a failing span records an exception, its error kind is
the exception type plus the exception message, with UUIDs, hex ids and every
digit run collapsed - status codes included, unlike log messages, so
`payments responded 502` and `payments responded 503` are one kind. Otherwise
the kind is the span name, used exactly, plus the status message collapsed the
same way. So a span named with a raw path (`GET /users/8123`)
that fails without an exception event gives every request its own error kind.
Use the route template.

**One trace per request.** Spans are correlated by propagated context. A missing
propagator between two services turns one failing request into two unrelated
error episodes.

**Clock.** Recent-span reads exclude spans starting more than five minutes ahead
of Sermon's clock. A skewed emitter's spans are still fetchable by `trace_id`,
but they fall out of recent views.

### 8. Non-production traffic is separated

Exporting development, preview or test traffic to the same Sermon account
produces real error episodes from it. Environment labels change how failure
volume is measured; they do not stop detection.

Verify: whether non-production builds use the same endpoint and token. Report
the choice rather than assuming one - some teams want preview errors, most do
not.

Fix: give non-production its own account or token, or accept the episodes and
label the environment so production measurement stays honest.

### 9. Findings can be investigated against source

For Sermon to read this project's code when investigating one of its findings,
three operator approvals must hold, in this order: GitHub connected, a
repository link in `connected` state for the service, and source sharing
approved. The first missing one is the blocker to report; `services` names it.
Separately, each runtime reports whether it has an environment and a telemetry
revision (`environment_missing`, `revision_missing`, or
`revision_check_required` when both are present, meaning the commit is checked
against the repository when an investigation starts).

Each of those is an operator decision made in Sermon's own UI. Report the
blocker and link to the service's review page. **Never** request or grant
source access through chat, and never treat an audit as consent.

## Report

End with this shape and nothing else:

```
## Sermon audit: <service>

Verdict: <ready | partial | not wired up>

| Check | Verdict | Evidence |
| --- | --- | --- |
| Arrival | ok | 412 otlp log rows, 1.2k spans in 24h |
| Service identity | degraded | service_name "api" on logs, "api-prod-7f" on traces |
| Signal coverage | ... | ... |
| Environment | ... | ... |
| Revision | ... | ... |
| Log shape | ... | ... |
| Span shape | ... | ... |
| Non-production separation | ... | ... |
| Investigation readiness | ... | ... |

## Fix first
1. <the one edit, and the file it goes in>
2. ...

## Unverified
- <what you could not read, and why>
```

Give exactly these nine rows, in this order and with these names, one per
check above, so reports compare across services and over time. The verdict
cell holds exactly one word, `ok`, `degraded`, `absent` or `unverified`, with
any qualification in the evidence cell. When the repository side of a check is
readable, the verdict is what it shows, even if Sermon could not be read; keep
`unverified` for Arrival without Sermon access and for checks with no evidence
on either side.

Order the fixes by what they unblock, not by how easy they are. One edit that
makes failures detectable outranks three that tidy attributes.

Keep the evidence column to what you actually read: counts, names, a sample
message shape. Do not restate the rules back to the operator.

## Host mode

Audits one enrolled server: whether the daemon is healthy, whether every service
on the host is reporting, and whether a failure there would reach anyone. It
reads only Sermon; it never runs a command on the host. If the host's services
have repositories checked out locally, read their logging configuration for
the fixes, but do not audit each service in full: recommend the repository
audit for the ones that need it.

Find the server with `fleet` and ask which one if the name is ambiguous. Then
read:

- `fleet`: online state, `daemon_version` against `latest_daemon_version`, and
  `daemon_outdated`.
- `latest_metrics`: `log_stats` (`seen`, `uploaded`, `dropped`), `daemon_self`
  CPU and memory, disks, and the top processes with their systemd units. If
  that sample has no processes or disks, read `recent_metrics` with `limit: 10`
  and use the newest sample that has them; an empty sample is not a daemon
  fault.
- `log_facets`: lines per unit and per priority over 24 hours, and the
  coverage window.
- `recent_logs` with `server_id`, `service` set to one unit and `limit: 100`,
  for each application unit: the message shape and its priorities.
- `alerts` with `rules_only: true` and `server_id`, and `findings`, to see what
  this host has actually produced.
- `services`, for each unit's host stream (`host:<server id>:<identifier>`)
  and whether the same service also has an `otlp:` stream.
- `baseline_history`, newest revision only: what Sermon has learned is normal.

### Host checks

**Daemon.** `ok` when online, current, and `dropped` is 0. `degraded` when the
daemon is outdated, reports dropped log lines, or its own CPU or memory is near
the host's `daemon_cpu_high` or `daemon_rss_high` thresholds. `absent` when the
server is offline or stale.

**Log coverage.** Every unit that runs a service should appear in
`log_facets`. Compare against the units in the top-process list: a service that
runs but logs nothing to journald (PostgreSQL and nginx write to their own
files by default) is invisible to Sermon, including its errors. Name each one
and where it logs instead.

**Log priority.** For each application unit, compare the priorities its lines
arrive at with what the messages say. Host lines are errors only at priority 3
or worse; words do not count. A unit whose `[error]` or `ERROR` lines arrive at
priority 6 produces no error findings at all: `degraded`, with the
sd-daemon-prefix fix from check 6 above. When reading a service's repository
for the fix, check its production-only logger configuration too: a prefixing
formatter is often wired there and nowhere else. Do not call a unit healthy because it
has no error findings until its priorities are honest.

**Log volume.** Name any unit that dominates the upload, and what its lines
are. Routine request lines (`GET /health`, `Sent 200`) and, on the host that runs
Sermon itself, its own ingest requests crowd the hosted window, which is
sampled, without adding signal. `degraded` when one unit's routine lines are
most of the host's volume.

**Application telemetry.** For each application unit, whether its service
also sends OTLP (`services` shows an `otlp:` stream). A journald-only service
has no traces, no environment and no revision, so its findings cannot be pinned
to a deployed commit. List these; each is a candidate for the repository audit.

**Alert coverage.** The host's rules can watch CPU, memory, disk fill,
staleness, daemon health and insert failures. No rule watches whether a
systemd unit is running. A crash-looping unit is noticed only through the
lines it and systemd log at priority 3 or worse, so a service whose own errors
arrive at priority 6 can fail silently. Say which services that applies to.
`degraded` when the standard host rules are missing or disabled.

**Baseline.** Compare the newest baseline revision against the current sample.
A claim that no longer matches - disk fill, memory band, which processes are
the heavy ones - means anomaly detection is judging against the wrong normal.
`degraded`, naming the stale claim and the current value.

**Investigation readiness.** For each application service on the host, its
`investigation_blocker` from `services`. Report the blockers; never approve
anything.

### Host report

```
## Sermon host audit: <server>

Verdict: <ready | partial | not wired up>

| Check | Verdict | Evidence |
| --- | --- | --- |
| Daemon | ok | v0.0.2 (latest), online, 0 dropped |
| Log coverage | ... | ... |
| Log priority | ... | ... |
| Log volume | ... | ... |
| Application telemetry | ... | ... |
| Alert coverage | ... | ... |
| Baseline | ... | ... |
| Investigation readiness | ... | ... |

## Services on this host

| Unit | Lines/24h | Priorities | OTLP | Errors become findings |
| --- | --- | --- | --- | --- |
| ... | ... | ... | yes / no | yes / no, and why |

## Fix first
1. ...

## Unverified
- ...
```

The same verdict rules apply as in the repository report: one word per cell,
and `degraded` or `absent` only for a defect you can name with its fix.

## Limits

- Without the `services` tool, checks 4, 5 and 9 are repository-side only.
  It is offered only to accounts with code investigations rolled out.
- Error findings from log paths other than CloudWatch, persistent trace-error
  findings, and consented source investigations are each rolled out per
  account. Account feature state is not readable with an ordinary token, so a
  service can pass this audit and still produce no findings. When findings are
  absent despite well-shaped telemetry, say that rollout state is unverified
  rather than blaming the instrumentation.
- Sampling: hosted logs are sampled, so counts read from `recent_logs` are
  evidence of arrival, not a volume measurement.
- This audit judges instrumentation. It does not judge whether the alert rules,
  mutes and expected errors on top of it match what the team wants paged.
