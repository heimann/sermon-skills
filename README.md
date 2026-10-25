# Sermon Skills

Agent skills for using Sermon.

## Skills

- `sermon-hosted-ops` - connect an agent to Sermon's hosted MCP and inspect fleet health, metrics, logs, traces, alert rules and events, and daemon version status through `sermon.fyi`.

The canonical skill is served at `https://sermon.fyi/docs/agents/skill.md` from `docs/skills/sermon-hosted-ops/SKILL.md` in `heimann/sermon`. `heimann/sermon-skills` mirrors this directory for `npx skills` installs.

## Install with npx skills

```fish
npx --yes skills add heimann/sermon-skills --skill sermon-hosted-ops --agent claude-code --global --copy --full-depth -y
```

If your skills CLI does not resolve the short GitHub form, use the HTTPS URL:

```fish
npx --yes skills add https://github.com/heimann/sermon-skills --skill sermon-hosted-ops --agent claude-code --global --copy --full-depth -y
```

## Keeping an installed copy current

The skill tells the agent to run `scripts/update_skill.py` before it chooses tools. The script asks the trusted Sermon origin (`SERMON_URL`, default `https://sermon.fyi`) whether the local `SKILL.md` matches the canonical bytes:

- A matching copy costs one bodiless `304` request.
- A stale copy that the script installed and nobody edited is replaced, after the download matches both its ETag and the manifest hash. The previous file is kept as a `SKILL.md.previous-<hash>` backup. An edit saved before the swap makes the script keep that edit and replace nothing; a later write through an editor that still has the old file open lands in the backup.
- An edited or separately installed copy is kept. The script prints the canonical skill for the agent to follow in that session.
- When Sermon is unreachable, the agent keeps the cached copy and reports that its freshness is unverified.

`managed.json` next to `SKILL.md` records the origin and hash the script installed. Delete it to stop automatic replacement. The script writes only inside the skill directory, and it refuses a directory path that passes through a symlink; pass the resolved path instead. It needs a POSIX system.

### One-time migration for copies installed before the freshness check

Older copies have no freshness check. Some still state that Sermon has no alert API, which is wrong. Reinstall with the `npx skills` command above. To migrate an existing directory in place instead, run the updater from a fresh install against it:

```fish
python3 <fresh-install>/sermon-hosted-ops/scripts/update_skill.py --skill-dir <old-skill-dir> --adopt
```

`--adopt` saves the old file as `SKILL.md.previous-<hash>`, installs the verified canonical skill, and writes `managed.json`. It touches no other files.

## Updating the mirror in `heimann/sermon-skills`

Sync only after the `heimann/sermon` change that edits `SKILL.md` is deployed. A mirror ahead of `sermon.fyi` would make managed installs replace the newer skill with the older deployed one.

1. Copy `SKILL.md` and `scripts/` from `docs/skills/sermon-hosted-ops/` into `sermon-hosted-ops/` in the mirror.
2. From the mirror root, run `python3 sermon-hosted-ops/scripts/update_skill.py --skill-dir sermon-hosted-ops --check`. It must print `current`, which proves the mirror matches the deployed skill. Any other result means they differ; stop.
3. Run the same command with `--adopt` instead of `--check`. It prints `current` again and writes `managed.json` with that hash, so new installs start managed.
4. Commit `SKILL.md`, `scripts/`, and `managed.json` together.

## Connect to Sermon

Follow the skill's native OAuth onboarding. For clients without native OAuth, generate an agent token from `https://sermon.fyi/connect` and store it outside your repos:

```fish
mkdir -p ~/.sermon
printf '%s\n' '<token from /connect>' > ~/.sermon/agent-token
chmod 600 ~/.sermon/agent-token
```

Start a fresh agent session after installing so the skill metadata is loaded.

Do not commit or paste long-lived tokens. If a token is pasted into chat, revoke it after use.
