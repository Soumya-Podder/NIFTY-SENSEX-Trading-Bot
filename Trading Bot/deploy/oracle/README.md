# Oracle Ubuntu paper deployment

Target: Ubuntu 24.04, one persistent VM, one backend worker. ARM dependencies must be verified on the actual machine. This deployment remains paper-only.

1. Build the frontend locally with `npm run build`.
2. Transfer source and `frontend/dist` to `/srv/trading_bot_full/Trading Bot`. Exclude Windows virtual environments, `node_modules`, `.git`, temporary files and logs. Install Linux dependencies on the VM.
3. Transfer `.env` through SSH separately; never include secrets in a source archive or Git. Retain the authoritative risk limits and paper account settings.
4. For cutover, stop the local engine and supervisor, confirm shutdown, then transfer the account database and `data` directory. Include existing observation databases and report/model artifacts. Use SQLite's backup API for a running database; stop writers before taking the final migration snapshot. Never copy a live SQLite database without its committed WAL state.
5. Run `sudo bash '/srv/trading_bot_full/Trading Bot/deploy/oracle/install.sh'`. Installation enables the service at boot but intentionally does not start this newly installed service. Verify no local engine remains active before `sudo systemctl start paperbot`.
6. Verify health, recovered balance/positions, credentials, both chart histories, futures volume, Telegram and service restart recovery. Preserve pending exits; never manufacture closing fills.

Dashboard access from CMD (replace values):

```cmd
ssh -i "E:\path\oracle-key.key" -N -L 5175:127.0.0.1:5174 ubuntu@SERVER_IP
```

Open `http://127.0.0.1:5175`. No public dashboard/API ports are necessary; allow SSH only from your IP in Oracle ingress rules. Use SSH known-host verification; do not disable host-key checking. First confirm the host-key fingerprint against the VM's trusted console.

The browser's tunnel port 5175 differs from the app's default allowed origin. Set `WEB_ORIGIN=http://127.0.0.1:5175` in the VPS project `.env` before startup so dashboard POST controls work. Keep the local `.env` unchanged.

All application-generated data, caches, temporary files and logs live under `/srv/trading_bot_full`. Linux system packages remain managed in normal OS locations. No project files are created on the Windows C drive.

Keep a consistent account/data backup outside the VM. A free instance may become unavailable; an outage is not a valid strategy no-trade result. Rotate logs and monitor disk capacity before extended unattended operation.
