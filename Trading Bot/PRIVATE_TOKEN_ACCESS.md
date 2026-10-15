# Manually update a Dhan token from your phone

The dashboard header has **Update Dhan token**. It opens a masked form at
`/api/credentials/form`. The form verifies the supplied token using Dhan's
read-only profile endpoint, then saves only `DHAN_ACCESS_TOKEN` in the existing
project `.env` when you explicitly press **Verify and save token**. The bot
reloads credentials using its existing watcher. No token generation/renewal is
enabled. Risk and paper-only settings do not change.

The current token is never returned to the page, placed in URLs, stored in
browser storage, or included in application errors. The field clears on submit.
Treat the desktop and authenticated phone as trusted devices.

## Private phone access

Remote access stays disabled until all of these are completed:

1. A Windows administrator installs Tailscale on the desktop. The signed
   installer has been downloaded to
   `E:\trading_bot_full\.tools\tailscale\tailscale-setup.msi`.
   Do not accept default C: locations for project-managed files. The installer
   supports `INSTALLDIR`, `ServiceStateDirectory`, and `UserStateDirectory`;
   select E: destinations and verify the runtime state/log locations as part of
   installation. Windows itself may install its system networking components.
2. Sign in on the desktop and install/sign in to Tailscale on the phone using
   the same personal account. Never put Tailscale passwords/auth keys in chat.
3. Run `backend/enable_private_token_access.ps1 -Tailscale <installed executable>`.
   It records only the desktop hostname and allowed user in gitignored
   `backend/token_access.json`, and enables **private Tailscale Serve HTTPS**.
   Follow any Tailscale HTTPS enablement link, then rerun if necessary.
4. Open the printed HTTPS URL with Tailscale connected on the phone. Only that
   configured user can access the token form. Other API/dashboard paths are
   rejected through this private hostname. Do not enable Funnel or forward ports.

The backend must run on loopback with `--no-proxy-headers` so authorization uses
the actual local proxy connection, not a forwarded address. The supervisor now
sets this flag. The desktop must remain awake and connected.

Installation, sign-in, and a real phone-to-desktop request must be verified
before calling remote access operational. The local form working alone does
not establish that phone access works. A successful save confirms Dhan accepted
the token at validation time, not that market data/entry conditions are ready.
