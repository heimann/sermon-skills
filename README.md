# Sermon Skills

Agent skills for using Sermon.

## Skills

- `sermon-hosted-ops` - connect an agent to Sermon's hosted MCP and inspect fleet health, metrics, logs, traces, alert rules and events, and daemon version status through `sermon.fyi`.
- `sermon-instrumentation-audit` - run inside one project's repository to audit how well it is wired into Sermon: arrival, service identity, environment, deployed revision, log and span shape, and investigation readiness.

Each skill is served at `https://sermon.fyi/docs/agents/skills/<name>.md` from `docs/skills/<name>/SKILL.md` in `heimann/sermon`; `sermon-hosted-ops` is also served at its original `https://sermon.fyi/docs/agents/skill.md`. `heimann/sermon-skills` mirrors this directory for `npx skills` installs.

## Install with npx skills

```fish
npx --yes skills add heimann/sermon-skills --skill sermon-hosted-ops --skill sermon-instrumentation-audit --agent claude-code --global --copy --full-depth -y
```

If your skills CLI does not resolve the short GitHub form, use the HTTPS URL:

```fish
npx --yes skills add https://github.com/heimann/sermon-skills --skill sermon-hosted-ops --skill sermon-instrumentation-audit --agent claude-code --global --copy --full-depth -y
```

## Keeping an installed copy current

Before it chooses tools, the agent runs `scripts/check_skill.py`. The script asks the trusted Sermon origin (`SERMON_URL`, default `https://sermon.fyi`) whether the local `SKILL.md` matches the canonical bytes. It takes the canonical path from the local file's own frontmatter `name`, so a copy is never compared against a different skill:

- A matching copy costs one bodiless `304` request.
- A stale copy gets the canonical skill, checked against its SHA-256 `ETag`, for the agent to follow in that session.
- When Sermon is unreachable or the download fails its check, the agent keeps the local copy and reports that its freshness is unverified.

The script never writes a file, so installed and customized copies stay as they are. To update the installed copy itself, reinstall with the `npx skills` command above.

### Copies installed before the freshness check

Reinstall any copy without `scripts/check_skill.py` once with the `npx skills` command above. Agents that read `https://sermon.fyi/docs/agents/skill.md` directly always get the current skill.

## Updating the mirror in `heimann/sermon-skills`

Sync after the `heimann/sermon` change that edits `SKILL.md` is deployed, so new installs report `current`:

1. For each changed skill, copy `SKILL.md` and `scripts/` from `docs/skills/<name>/` into `<name>/` in the mirror.
2. From the mirror root, run `python3 <name>/scripts/check_skill.py --skill <name>/SKILL.md`. It must print `current`; anything else means the mirror and the deployment differ.
3. Commit `SKILL.md` and `scripts/` together.

## Connect to Sermon

Follow the skill's native OAuth onboarding. For clients without native OAuth, generate an agent token from `https://sermon.fyi/connect` and store it outside your repos:

```fish
mkdir -p ~/.sermon
printf '%s\n' '<token from /connect>' > ~/.sermon/agent-token
chmod 600 ~/.sermon/agent-token
```

Start a fresh agent session after installing so the skill metadata is loaded.

Do not commit or paste long-lived tokens. If a token is pasted into chat, revoke it after use.
