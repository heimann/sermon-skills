# Sermon Skills

Agent skills for using Sermon.

## Skills

- `sermon-hosted-ops` - inspect Sermon-hosted fleet health and recent host metrics through `sermon.fyi`.

## Install with npx skills

```fish
npx --yes skills add heimann/sermon-skills --skill sermon-hosted-ops --agent claude-code --global --copy --full-depth -y
```

If your skills CLI does not resolve the short GitHub form, use the HTTPS URL:

```fish
npx --yes skills add https://github.com/heimann/sermon-skills --skill sermon-hosted-ops --agent claude-code --global --copy --full-depth -y
```

## Connect to Sermon

Generate an agent token from `https://sermon.fyi/agents`, then store it outside your repos:

```fish
mkdir -p ~/.sermon
printf '%s\n' '<token from /agents>' > ~/.sermon/agent-token
chmod 600 ~/.sermon/agent-token
```

Start a fresh Claude Code session after installing so the skill metadata is loaded.

Do not commit or paste long-lived tokens. If a token is pasted into chat, revoke it after use.
