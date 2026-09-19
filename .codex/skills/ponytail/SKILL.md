---
name: ponytail
description: "Use the installed ponytail npm package when the user asks for Ponytail functionality or maintenance automation."
---

# Ponytail

The project dependency `ponytail@1.0.57` is an ordinary npm package, not a
Copilot command. Use it only when the user explicitly asks for Ponytail
functionality.

## Project usage

- Package location: `node_modules/ponytail`
- Import it from JavaScript with `require("ponytail")`.
- Inspect the installed package before relying on undocumented behavior; its
  README is empty and its public entry point is `index.js`.
- Do not run its `autocommit`, `prepublish`, or `shout` scripts without explicit
  user approval because they can commit, push, publish, or modify the repository.
- Keep Ponytail-related changes separate from the trading engine unless the user
  explicitly requests integration.

## Safety

Never expose credentials or add automated publishing, pushing, or committing to
the trading project.
