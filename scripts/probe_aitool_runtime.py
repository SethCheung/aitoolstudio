#!/usr/bin/env python3
"""aitoolstudio runtime probe — run on user's macOS terminal that can reach LAN."""
import json
import subprocess
import sys
import time
from urllib import request, error

# Hard-coded absolute paths so we don't depend on shell PATH
CURL = "/usr/bin/curl"
SSHPASS = "/opt/homebrew/bin/sshpass"
SSH = "/usr/bin/ssh"

PLATFORM = "http://192.168.1.60:3000"
COMFYUI = ["192.168.1.195:8188", "192.168.1.197:8188", "192.168.1.249:8188"]
SSH_TARGET_60 = ("sethchang", "12301230", "192.168.1.60")
SSH_TARGET_COMFY = ("sjm", "Sjm744546", None)  # filled per host


def sh(cmd, timeout=15):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, out.stdout, out.stderr
    except Exception as e:
        return -1, "", repr(e)


def curl_http(host_port, path, timeout=4):
    cmd = [CURL, "-sS", "-o", "/dev/null", "-w", "%{http_code} %{time_total}",
           "--max-time", str(timeout), f"http://{host_port}{path}"]
    rc, so, se = sh(cmd, timeout=timeout + 2)
    if rc != 0:
        return None, se.strip() or so.strip()
    return so.strip().split(" ", 1)


def curl_body(host_port, path, timeout=5, max_bytes=600):
    cmd = [CURL, "-sS", "--max-time", str(timeout), f"http://{host_port}{path}"]
    rc, so, se = sh(cmd, timeout=timeout + 2)
    if rc != 0:
        return None, se.strip() or so.strip()
    return so[:max_bytes]


def ssh_run(user, pw, host, remote_cmd, timeout=15, use_sudo=False):
    target = f"{user}@{host}"
    ssh_cmd = [SSH, "-o", "StrictHostKeyChecking=no", "-o",
               "ConnectTimeout=5", "-o", "PreferredAuthentications=password",
               "-o", "PubkeyAuthentication=no",
               "-o", "RequestTTY=no"]
    if use_sudo:
        full = f"echo {pw} | sudo -S bash -c {remote_cmd!r}"
    else:
        full = remote_cmd
    cmd = [SSHPASS, "-p", pw] + ssh_cmd + [target, full]
    rc, so, se = sh(cmd, timeout=timeout)
    return rc, so, se


def banner(s):
    print()
    print("=" * 70)
    print(s)
    print("=" * 70)


# 1. Platform endpoint reachability
banner("1) Platform 60:3000 endpoint reachability")
endpoints = [
    "/", "/api/app-info", "/api/config", "/api/auth/me",
    "/api/projects", "/api/comfyui/instances", "/api/comfyui/status",
    "/api/resource-root", "/api/workflows", "/api/workflows-public",
    "/api/providers", "/api/models",
    "/login", "/projects", "/admin", "/smart-canvas",
]
for p in endpoints:
    code_t = curl_http("192.168.1.60:3000", p, timeout=4)
    if code_t and len(code_t) == 2:
        code, t = code_t
        print(f"  {code:>4}  {t}s  {p}")
    else:
        print(f"  ERR  {p}  ->  {code_t}")

# 2. ComfyUI nodes system_stats
banner("2) ComfyUI 195/197/249 system_stats")
for hp in COMFYUI:
    body = curl_body(hp, "/system_stats", timeout=5, max_bytes=400)
    if body is None:
        print(f"  -- {hp}  unreachable")
    else:
        try:
            j = json.loads(body)
            s = j.get("system", {})
            print(f"  OK {hp}  os={s.get('os')}  comfyui={s.get('comfyui_version')}  "
                  f"ram_free={s.get('ram_free')}  templates={s.get('installed_templates_version')}")
        except Exception:
            print(f"  ?? {hp}  body[:120]={body[:120]!r}")

# 3. ComfyUI /object_info class count
banner("3) ComfyUI /object_info class count (compared with 60 workflow JSON)")
for hp in COMFYUI:
    body = curl_body(hp, "/object_info", timeout=6, max_bytes=200000)
    if body is None:
        print(f"  -- {hp}  unreachable")
    else:
        try:
            j = json.loads(body)
            print(f"  OK {hp}  classes={len(j)}")
        except Exception as e:
            print(f"  ?? {hp}  parse err: {e}  body[:200]={body[:200]!r}")

# 4. 60 process and docker
banner("4) 60 host: python/uvicorn/main.py processes (via sudo)")
rc, so, se = ssh_run(*SSH_TARGET_60,
                     'ps -ef | grep -E "python|uvicorn|main.py" | grep -v grep',
                     timeout=10, use_sudo=True)
print(f"  rc={rc}")
if so.strip():
    print(so.strip())
if se.strip():
    print("STDERR:", se.strip()[:300])

banner("5) 60 host: docker ps -a (via sudo)")
rc, so, se = ssh_run(*SSH_TARGET_60,
                     "docker ps -a 2>&1",
                     timeout=12, use_sudo=True)
print(f"  rc={rc}")
print(so.strip()[:1500])
if se.strip():
    print("STDERR:", se.strip()[:300])

banner("6) 60 host: docker logs --tail 100 aitoolstudio-canvas (via sudo)")
rc, so, se = ssh_run(*SSH_TARGET_60,
                     "docker logs --tail 100 aitoolstudio-canvas 2>&1",
                     timeout=15, use_sudo=True)
print(f"  rc={rc}")
print(so.strip()[-3000:])
if se.strip():
    print("STDERR:", se.strip()[:300])

banner("7) 60 host: API/.env COMFYUI / RESOURCE config")
for p in ["~/API/.env", "~/aitoolstudio/API/.env", "~/API/.env.example"]:
    rc, so, se = ssh_run(*SSH_TARGET_60, f"cat {p} 2>/dev/null", timeout=8)
    if so.strip():
        print(f"  --- {p} ---")
        for line in so.splitlines():
            if any(k in line for k in ("COMFYUI", "RESOURCE", "AITOOL", "ADMIN")):
                print("    " + line)

# 8. ComfyUI workers: process + service + port + mount
banner("8) ComfyUI workers: process / mount / object_info (via sjm@)")
for last in ("195", "197", "249"):
    host = f"192.168.1.{last}"
    print(f"\n  --- {host} ---")
    # process
    rc, so, se = ssh_run("sjm", "Sjm744546", host,
                         'ps -ef | grep -E "python|main.py" | grep -v grep | head -10',
                         timeout=8)
    if so.strip():
        for line in so.splitlines()[:8]:
            print("    proc:", line)
    else:
        print("    proc: <none>")
    # systemctl
    rc, so, se = ssh_run("sjm", "Sjm744546", host,
                         'systemctl is-active comfyui 2>&1; systemctl status comfyui --no-pager 2>&1 | head -20',
                         timeout=8)
    if so.strip():
        for line in so.splitlines()[:15]:
            print("    svc :", line)
    # port 8188
    rc, so, se = ssh_run("sjm", "Sjm744546", host,
                         'ss -ltnp 2>/dev/null | grep 8188; (echo > /dev/tcp/127.0.0.1/8188) 2>&1 && echo "tcp 8188 OPEN" || echo "tcp 8188 CLOSED"',
                         timeout=6)
    if so.strip():
        for line in so.splitlines()[:5]:
            print("    port:", line)
    # resource mount
    rc, so, se = ssh_run("sjm", "Sjm744546", host,
                         'ls -la /mnt/nas_comfyui 2>&1 | head -5; ls -la /mnt/comfyui-models 2>&1 | head -5; mount | grep -E "nas_comfyui|comfyui-models" 2>&1',
                         timeout=6)
    if so.strip():
        for line in so.splitlines()[:10]:
            print("    mnt :", line)
    # extra_model_paths
    rc, so, se = ssh_run("sjm", "Sjm744546", host,
                         'cat ~/ComfyUI/extra_model_paths.yaml 2>/dev/null | head -30',
                         timeout=6)
    if so.strip():
        for line in so.splitlines()[:20]:
            print("    yaml:", line)

banner("9) Workflow compatibility: workflows/Z-Image-Enhance.json vs 195/197/249 /object_info")
try:
    import urllib.request
    with open("/Users/apple/Documents/GitHub/aitoolstudio/workflows/Z-Image-Enhance.json") as f:
        wf = json.load(f)
    class_types = sorted({n.get("class_type") for n in wf.values() if isinstance(n, dict) and n.get("class_type")})
    print(f"  Z-Image-Enhance needs {len(class_types)} class_types")
    for hp in COMFYUI:
        try:
            with urllib.request.urlopen(f"http://{hp}/object_info", timeout=6) as r:
                obj = json.loads(r.read())
            have = set(obj.keys())
            missing = [c for c in class_types if c not in have]
            print(f"  {hp}  have={len(have)}  missing={len(missing)}  -> {missing[:5]}")
        except Exception as e:
            print(f"  {hp}  ERR {e}")
except FileNotFoundError:
    print("  local Z-Image-Enhance.json not found, skipped")

print()
print("DONE")
