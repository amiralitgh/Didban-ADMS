# Didban ADMS

<p align="center">
  <img src="zkteco-adms-listener/static/assets/didban-readme-hero.svg" alt="دیدبان — وضعیت دستگاه‌ها، کارکنان و داده‌های هویتی را از یک مرکز کنترل کنید." width="100%">
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

During operation, the listener uses SQLite for local persistence and a
server-side upload directory for ADMS file payloads. These runtime paths are
created under the application directory and can be backed up according to the
deployment environment.

## Deployment

The application can run as a standalone Python service or behind a reverse
proxy. Use `zkteco-adms-listener/README.md` as the starting point for local
deployment, then adapt networking, persistence, and authentication settings to
the target environment.
