# ZKTeco ADMS Control Plane

This is a dependency-free Python ADMS receiver and browser control plane. It identifies devices by serial number (`SN`), stores incoming records per device, and queues commands for the correct device poll. The browser UI defaults to Persian/Farsi RTL with a local Sahel font.

## Start server

```bash
python3 server.py --host 0.0.0.0 --port 8090
```

## Device URL

Set ADMS server on the device to:

```text
http://YOUR_SERVER_HOST:8090
```

The server handles:

- `GET /iclock/cdata` (handshake/options response)
- `GET /iclock/registry`, `GET /iclock/push`, `GET /iclock/ping` (Rodrigo-style push endpoints)
- `POST /iclock/cdata` (receives logs/raw records)
- `POST /iclock/fdata` (receives uploaded file payloads such as photos)
- `GET /iclock/getrequest` (returns queued command for that SN, otherwise `OK`)
- `POST /iclock/devicecmd` (stores command ACK/results from device)
- `POST /iclock/querydata` (captures tablename query rows)
- `GET /healthz`

It also exposes app-facing JSON APIs:

- `GET /api/health`
- `GET /api/users?limit=500`
- `GET /api/users/{pin}`
- `POST /api/users/query` (queue user pull from device)
- `POST /api/users` (queue add user commands)
- `PUT /api/users/{pin}` (queue update user commands)
- `DELETE /api/users/{pin}?sn=DEVICE_SN` (queue delete user commands)
- `GET /api/biometrics?pin=...`
- `GET /api/commands?sn=...`
- `GET /api/devices`
- `GET /api/summary`
- `GET /api/attendance?sn=...`
- `GET /api/requests?sn=...`
- `GET /api/users/export?sn=...&format=csv|json`
- `POST /api/users/import?sn=...` (CSV or JSON)
- `POST /api/biometrics/query`
- `POST /api/biometrics` (structured or raw template command)
- `GET /api/biometrics/export`
- `POST /api/commands` (raw command)
- `POST /api/devices/{sn}/sync`
- `PUT /api/devices/{sn}` (rename device)
- `GET /api/operator-guide`
- `GET /api/user-fields`
- `GET /api/device-labels`
- `GET /api/devices/{sn}`
- `POST /api/users/copy` (copy one source user to selected devices)
- `POST /api/users/copy-many` (copy selected PINs to selected devices)

Open `http://127.0.0.1:8090/` for the dashboard after starting the server.
Use your own reachable hostname or address when configuring a device.

## Queue command

```bash
python3 queue_command.py --sn DEVICE_SN --cmd "YOUR_RAW_COMMAND"
```

## App JSON API examples

```bash
# list latest parsed users received from device
curl -s http://127.0.0.1:8090/api/users | jq .

# ask device to push USERINFO again
curl -s -X POST http://127.0.0.1:8090/api/users/query \
  -H 'Content-Type: application/json' \
  -d '{"sn":"YOUR_DEVICE_SERIAL","mode":"both"}' | jq .

# queue add user
curl -s -X POST http://127.0.0.1:8090/api/users \
  -H 'Content-Type: application/json' \
  -d '{"sn":"YOUR_DEVICE_SERIAL","pin":"100001","name":"Example User","password":"example-password","privilege":"0","dual_mode":true}' | jq .

# queue update user
curl -s -X PUT http://127.0.0.1:8090/api/users/100001 \
  -H 'Content-Type: application/json' \
  -d '{"sn":"YOUR_DEVICE_SERIAL","name":"Example User Updated","privilege":"0","password":"example-password","dual_mode":true}' | jq .

# queue delete user
curl -s -X DELETE 'http://127.0.0.1:8090/api/users/100001?sn=YOUR_DEVICE_SERIAL&dual_mode=1' | jq .

# import users from CSV
curl -s -X POST 'http://127.0.0.1:8090/api/users/import?sn=YOUR_DEVICE_SERIAL' \
  -H 'Content-Type: text/csv' --data-binary @users.csv | jq .

# request users and biometrics
curl -s -X POST http://127.0.0.1:8090/api/devices/YOUR_DEVICE_SERIAL/sync \
  -H 'Content-Type: application/json' -d '{}' | jq .
```

## Queue Rodrigo-style commands

```bash
python3 queue_rodrigo_style.py --sn DEVICE_SN add-user --pin 100001 --name "Example User" --password "example-password" --privilege 0
python3 queue_rodrigo_style.py --sn DEVICE_SN add-extuser --pin 100001 --first-name "Example"
python3 queue_rodrigo_style.py --sn DEVICE_SN add-userauth --pin 100001 --timezone-id 1 --door-id 15
python3 queue_rodrigo_style.py --sn DEVICE_SN query --table user
python3 queue_rodrigo_style.py --sn DEVICE_SN raw --cmd "DATA QUERY tablename=templatev10,fielddesc=*,filter=*"
```

Wire format sent to device:

- If you queue plain command (`--cmd "DATA QUERY USERINFO"`), response becomes `C:<id>:DATA QUERY USERINFO`.
- If you queue a full wire command starting with `C:`, it is sent as-is.

## Data storage

SQLite DB file:

```text
./adms.sqlite3
```

Tables:

- `request_log` (all request metadata + body)
- `attendance_raw` (each posted line)
- `querydata_raw` (rows posted to `/iclock/querydata`)
- `fdata_files` (file-upload metadata and saved payload path)
- `command_queue` (queued/sent commands per SN)
- `command_results` (ACK/status returned by device command callback)

## Watch live traffic

```bash
python3 watch_device.py --sn DEVICE_SN
```

## Show current queue/result state

```bash
python3 show_state.py
```
