---
name: caveman
description: "Use the installed caveman npm templating engine when the user asks for Caveman template functionality."
---

# Caveman

The project dependency `caveman@0.1.6` is an ordinary npm templating library,
not a Copilot command. Use it only when the user explicitly asks for Caveman
functionality.

## Project usage

- Package location: `node_modules/caveman`
- Its package entry point is `caveman.js`.
- Inspect the installed source and README before relying on undocumented
  template syntax.
- Do not introduce Caveman into the existing React/Vite frontend unless the
  user explicitly requests a migration or an isolated integration.
- Prefer a small isolated example or test before changing production rendering.

## Safety

Treat template input as untrusted. Do not render secrets into templates, and do
not weaken the existing frontend escaping or content-security protections.
