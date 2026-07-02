"""Tail alerts.json del Wazuh manager y push a Redis stream events:raw_wazuh."""
from __future__ import annotations
import json, time, os
from pathlib import Path
import redis

ALERTS_FILE = Path("/var/ossec/logs/alerts/alerts.json")
STREAM      = "events:raw_wazuh"

def tail_f(path: Path):
    with path.open() as f:
        f.seek(0, 2)  # ir al final
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            yield line

def main():
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    print("[*] Bridge iniciado, escuchando alerts.json...", flush=True)
    for line in tail_f(ALERTS_FILE):
        try:
            alert = json.loads(line)
            if alert.get("rule", {}).get("level", 0) < 5:
                continue
            payload = {
                "host":                     alert.get("agent", {}).get("name", "unknown"),
                "mitre_technique":          (alert.get("rule", {}).get("mitre", {}).get("technique") or ["Unknown"])[0],
                "syscalls_per_min":         alert.get("data", {}).get("syscalls_per_min", 0),
                "files_touched_per_min":    alert.get("data", {}).get("files_touched_per_min", 0),
                "entropy_of_written_bytes": alert.get("data", {}).get("entropy", 0.0),
                "network_kbps":             alert.get("data", {}).get("network_kbps", 0),
                "command_line":             alert.get("data", {}).get("win", {}).get("eventdata", {}).get("commandLine", ""),
                "raw":                      alert,
            }
            r.xadd(STREAM, {"data": json.dumps(payload)})
            print(f"[+] Evento enviado a Redis: {payload['host']} - {payload['mitre_technique']}", flush=True)
        except Exception as e:
            print(f"[!] {e}", flush=True)

if __name__ == "__main__":
    main()