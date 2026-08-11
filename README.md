# Didban ADMS

<p align="center">
  <img src="zkteco-adms-listener/static/assets/didban-hero-scene.svg" alt="Didban ADMS" width="100%">
</p>

Didban is a self-hosted control plane for ZKTeco attendance devices using the
ADMS HTTP push/poll protocol. It receives device traffic, separates records by
serial number, stores employees, biometrics, attendance, and command results,
and provides a Persian RTL browser dashboard for day-to-day operations.

## Capabilities

- Receive attendance, user, fingerprint, face, photo, and raw ADMS payloads.
- Identify every device by its ADMS serial number (`SN`).
- Queue device-scoped user create, update, delete, copy, and synchronization commands.
- Query and export employees, biometrics, attendance, raw requests, and backups.
- Track command delivery from queued to sent, acknowledged, or failed.
- Keep device traffic public for ADMS while protecting dashboard APIs with a
  single-operator session.
- Keep every dashboard table within the page width and wrap long values safely.

## Project Layout

- `zkteco-adms-listener/server.py` — dependency-free ADMS server and JSON API.
- `zkteco-adms-listener/static/` — RTL dashboard, styles, and local assets.

## Run Locally

```bash
cd zkteco-adms-listener
export DIDBAN_ADMIN_PASSWORD='choose-a-password'
python3 server.py --host 0.0.0.0 --port 8090
```

Open `http://127.0.0.1:8090/` for the dashboard. Configure a device's ADMS
server URL to the host and port where this listener is reachable.

## ADMS Routes

The listener implements the core device-facing routes:

- `GET /iclock/cdata`
- `POST /iclock/cdata`
- `GET /iclock/getrequest`
- `POST /iclock/devicecmd`
- `POST /iclock/querydata`
- `POST /iclock/fdata`
- `GET /iclock/registry`
- `GET /iclock/push`
- `GET /iclock/ping`

Commands are delivered when the matching device polls
`/iclock/getrequest`; the serial number is the device identity, not its IP
address.

## Verification

```bash
python3 -m py_compile zkteco-adms-listener/server.py
curl -fsS http://127.0.0.1:8090/healthz
```

The SQLite database and uploaded device payloads are runtime data and are not
committed to Git.

## Production

The deployment is environment-specific. See `zkteco-adms-listener/README.md`
for the application entry point; keep infrastructure details, credentials, and
operational handoff notes outside this public repository.
