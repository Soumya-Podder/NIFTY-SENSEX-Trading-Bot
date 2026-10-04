# NIFTY-SENSEX-Trading-Bot
NIFTY and SENSEX paper trading bot with strategy selection, risk controls and research tools. Unvalidated paper observations; live orders disabled.

See [Trading Bot/README.md](Trading%20Bot/README.md) for backend/frontend startup and the paper-trading policy.

## Development skills

The `skills` CLI is installed with npm's global layout under `.tools/npm-global`
inside this project, rather than npm's default C: prefix. The project launcher
also directs npm cache, temporary downloads and CLI state to this folder on E:.
From CMD:

```bat
cd /d E:\trading_bot_full
skills --version
skills list -a codex
skills update -p
```

From PowerShell use `./skills.cmd` instead of `skills`. Run these commands from
the project root so skill installation remains project-scoped. The installed
Vercel `vercel-react-best-practices` and `web-design-guidelines` skills live in
`.agents/skills/`; `skills-lock.json` records their source and content hashes.
These guide code reviews and implementation; they do not train trading agents.

To restore the CLI and skills on another checkout:

```bat
cd /d E:\trading_bot_full
set "TEMP=%CD%\.tmp-tests"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
npm install -g skills@1.7.0 --prefix "%CD%\.tools\npm-global" --cache "%CD%\.npm-cache"
skills experimental_install
```
