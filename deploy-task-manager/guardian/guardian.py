# ===================================================================
# Guardian - Unified Service Guardian with Web Dashboard
# A single exe that monitors ALL services on the server.
# Web UI on port 9000, background thread checks every 30s
# (configurable via services.json "check_interval").
# ===================================================================
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import psutil

# --- Paths (works both as script and as PyInstaller exe) ---
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_FILE = BASE_DIR / "services.json"
LOG_FILE = BASE_DIR / "guardian.log"
ERROR_LOG_FILE = BASE_DIR / "guardian-error.log"
DEFAULT_PORT = 9000
CHECK_INTERVAL = 60
MAX_EVENTS = 100
VERSION = "2.1"

# --- self-management (no external install/stop scripts needed) ---
WATCHDOG_TASK = "Guardian-Watchdog"
BOOT_TASK = "Guardian-Boot"
# legacy per-service watchdog tasks from the old architecture - removed
# automatically whenever guardian starts with enough privileges
OLD_TASKS = ["TaskManager-Watchdog", "TaskManager-Watchdog-Boot",
             "ImgAgent-Watchdog", "ImgAgent-Watchdog-Boot"]
STOP_MARKER = BASE_DIR / "guardian.stopped"
INSTALL_SKIP_MARKER = BASE_DIR / "guardian.install-skip"
_sysroot = os.environ.get("SystemRoot", r"C:\Windows")
SCHTASKS = os.path.join(_sysroot, "System32", "schtasks.exe")
NETSH = os.path.join(_sysroot, "System32", "netsh.exe")
# CREATE_NO_WINDOW: guardian.exe is a windowed (console=False) exe.
# Launching console tools (schtasks/netsh) WITHOUT this flag makes Windows
# flash a black cmd window for every call - visible when the dashboard page
# polls /api/system (every 60s) or on guardian startup.
NO_WINDOW = 0x08000000

_config_lock = threading.Lock()


# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
def load_config():
    with _config_lock:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {"guardian_port": DEFAULT_PORT, "check_interval": CHECK_INTERVAL, "services": []}


def save_config(cfg):
    with _config_lock:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# -------------------------------------------------------------------
# Process management
# -------------------------------------------------------------------
def is_running(process_name, match_cmdline=None):
    """Check if a process with the given name is running.
    If match_cmdline is set, also check it appears in the command line."""
    if not process_name:
        return False
    target = process_name.lower()
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            pname = proc.info.get("name") or ""
            if pname.lower() == target:
                if match_cmdline:
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if match_cmdline.lower() not in cmdline.lower():
                        continue
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def start_proc(svc):
    """Start a service process. Returns (success, message)."""
    path = svc.get("path", "")
    args = svc.get("args", "")
    workdir = svc.get("workdir", "")
    if not path:
        return False, "path is empty"
    if not os.path.isfile(path):
        return False, f"file not found: {path}"
    try:
        cmd = f'"{path}"'
        if args:
            cmd += f" {args}"
        subprocess.Popen(
            cmd,
            cwd=workdir or None,
            shell=True,
            creationflags=NO_WINDOW,  # CREATE_NO_WINDOW
        )
        return True, "started"
    except Exception as e:
        return False, str(e)


def stop_proc(svc):
    """Stop a service process. Returns count of killed processes."""
    process_name = svc.get("process", "")
    match_cmdline = svc.get("match_cmdline")
    if not process_name:
        return 0
    target = process_name.lower()
    killed = 0
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            pname = proc.info.get("name") or ""
            if pname.lower() == target:
                if match_cmdline:
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if match_cmdline.lower() not in cmdline.lower():
                        continue
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def get_port_status(port):
    """Check if a TCP port is listening."""
    if not port:
        return None
    try:
        conns = psutil.net_connections(kind="tcp")
        for c in conns:
            if c.status == "LISTEN" and c.lport == int(port):
                return True
    except Exception:
        pass
    return False


def detect_ports(process_name, match_cmdline=None):
    """Auto-detect listening TCP ports owned by processes with the given name.

    Used when 'port' is NOT configured in services.json: the dashboard then
    shows what the process actually listens on, queried in real time on
    every refresh - no manual lookup needed.
    """
    if not process_name:
        return []
    target = process_name.lower()
    ports = set()
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            pname = proc.info.get("name") or ""
            if pname.lower() != target:
                continue
            if match_cmdline:
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if match_cmdline.lower() not in cmdline.lower():
                    continue
            # psutil 6.x renamed connections() -> net_connections()
            if hasattr(proc, "net_connections"):
                conns = proc.net_connections(kind="tcp")
            else:
                conns = proc.connections(kind="tcp")
            for c in conns:
                if c.status == "LISTEN" and c.laddr:
                    ports.add(c.laddr.port)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    return sorted(ports)


def _proc_name(pid):
    """Best-effort process name lookup by pid."""
    try:
        return psutil.Process(pid).name()
    except Exception:
        return "?"


def find_port_owner(port, own_process=None, match_cmdline=None):
    """Find the process LISTENING on `port`. Returns {'pid','name'} or None.

    Returns None when nobody listens. If the listener IS the service's own
    process (own_process / match_cmdline match) it is not a conflict either.
    Used to answer "why does my service keep dying": a leftover instance
    (e.g. an old `python main.py`) holding the port makes every newly
    started exe die instantly.
    """
    if not port:
        return None
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status != "LISTEN" or not c.laddr or c.laddr.port != int(port):
                continue
            pid = c.pid
            if not pid:
                continue
            try:
                p = psutil.Process(pid)
                pname = p.name() or ""
                is_own = False
                if own_process and pname.lower() == own_process.lower():
                    if match_cmdline:
                        cmd = " ".join(p.cmdline() or []).lower()
                        is_own = match_cmdline.lower() in cmd
                    else:
                        is_own = True
                if is_own:
                    return None
                return {"pid": pid, "name": pname}
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                return {"pid": pid, "name": "unknown"}
    except Exception:
        pass
    return None


# -------------------------------------------------------------------
# Self-management: install / stop / restart / uninstall
# (absorbs manage.ps1 - no external scripts needed any more)
# -------------------------------------------------------------------
def _is_elevated():
    """True when running as admin or SYSTEM."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _schtasks(*args, timeout=15):
    """Run schtasks.exe, return (returncode, output-text)."""
    try:
        r = subprocess.run([SCHTASKS, *args], capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW)
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("gbk", errors="ignore")
        return r.returncode, out
    except Exception as e:
        return -1, str(e)


def task_exists(name):
    rc, _ = _schtasks("/Query", "/TN", name)
    return rc == 0


def cleanup_old_tasks():
    """Remove legacy per-service watchdog tasks (old architecture residue).

    Deleting SYSTEM tasks needs elevation; failures are ignored and the
    cleanup simply retries on the next start (e.g. after reboot guardian
    comes up via the SYSTEM boot task and the cleanup succeeds).
    """
    removed = []
    for t in OLD_TASKS:
        if task_exists(t):
            rc, _ = _schtasks("/Delete", "/TN", t, "/F")
            if rc == 0:
                removed.append(t)
    return removed


def _fw_rule_name(port):
    return f"Guardian Dashboard ({port})"


def firewall_rule_exists(port):
    try:
        r = subprocess.run([NETSH, "advfirewall", "firewall", "show", "rule",
                            f"name={_fw_rule_name(port)}"],
                           capture_output=True, timeout=15,
                           creationflags=NO_WINDOW)
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("gbk", errors="ignore")
        # localized output: just look for the port number itself
        return str(port) in out
    except Exception:
        return False


def ensure_firewall(port):
    """Allow inbound TCP on the dashboard port. Needs elevation."""
    try:
        subprocess.run([NETSH, "advfirewall", "firewall", "delete", "rule",
                        f"name={_fw_rule_name(port)}"], capture_output=True,
                       timeout=15, creationflags=NO_WINDOW)
        r = subprocess.run([NETSH, "advfirewall", "firewall", "add", "rule",
                            f"name={_fw_rule_name(port)}", "dir=in", "action=allow",
                            "protocol=TCP", f"localport={port}"],
                           capture_output=True, timeout=15,
                           creationflags=NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def _self_command():
    """Relaunch command for this guardian (exe or python script)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def do_install(port):
    """Create watchdog + boot scheduled tasks and open the firewall.
    Requires elevation. Returns (results, removed_old_tasks)."""
    cmd = _self_command()
    tr = " ".join(f'"{c}"' for c in cmd) + " --from-task"
    _schtasks("/Delete", "/TN", WATCHDOG_TASK, "/F")
    _schtasks("/Delete", "/TN", BOOT_TASK, "/F")
    rc, _ = _schtasks("/Create", "/TN", WATCHDOG_TASK, "/TR", tr,
                      "/SC", "MINUTE", "/MO", "1", "/RU", "SYSTEM",
                      "/RL", "HIGHEST", "/F")
    results = [("watchdog_task", rc == 0)]
    rc, _ = _schtasks("/Create", "/TN", BOOT_TASK, "/TR", tr,
                      "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")
    results.append(("boot_task", rc == 0))
    results.append(("firewall", ensure_firewall(port)))
    removed = cleanup_old_tasks()
    return results, removed


def _relaunch_elevated():
    """Relaunch ourselves with a UAC prompt. True when the elevated copy
    was actually spawned (user accepted)."""
    try:
        import ctypes
        if getattr(sys, "frozen", False):
            exe, params = sys.executable, "--elevated"
        else:
            exe = sys.executable
            params = f'"{Path(__file__).resolve()}" --elevated'
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, str(BASE_DIR), 1)
        return ret > 32
    except Exception:
        return False


def _launched_by_scheduler():
    """True when started by Task Scheduler (watchdog/boot task).

    Works for PyInstaller onefile too: the python process' parent is the
    bootloader exe; walk ancestors to find svchost/taskeng.
    """
    if "--from-task" in sys.argv[1:]:
        return True
    try:
        p = psutil.Process(os.getpid())
        for _ in range(4):
            p = p.parent()
            if p is None:
                return False
            name = (p.name() or "").lower()
            if name in ("svchost.exe", "taskeng.exe", "taskhost.exe", "taskhostw.exe"):
                return True
            if name == "explorer.exe":
                return False
        return False
    except Exception:
        return False


# -------------------------------------------------------------------
# Guardian engine
# -------------------------------------------------------------------
class Guardian:
    def __init__(self):
        self.events = []
        self.restart_counts = {}
        self.last_checks = {}
        self.last_starts = {}
        # restart-storm protection state
        self._consec_fail = {}     # name -> consecutive failed start attempts
        self._last_start_ts = {}  # name -> unix ts of the last start attempt

    def log_event(self, service, event, success=True, detail=""):
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "service": service,
            "event": event,
            "success": success,
            "detail": detail,
        }
        self.events.append(entry)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]
        # also write to file
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f'{entry["time"]}  [{service}] {event} {"OK" if success else "FAIL"} {detail}\n')
        except Exception:
            pass

    def check_all(self):
        cfg = load_config()
        now = time.time()
        for svc in cfg.get("services", []):
            name = svc.get("name", "")
            proc_name = svc.get("process", "")
            match_cmd = svc.get("match_cmdline")
            auto = svc.get("auto_restart", True)
            port = svc.get("port")

            running = is_running(proc_name, match_cmd)
            self.last_checks[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if running:
                # survived since the previous check -> reset the failure streak
                self._consec_fail[name] = 0
                continue
            if not auto:
                continue

            # The previous start attempt did not survive until now -> count it
            # as a failed start. After 5 consecutive failures we stop trying
            # every cycle and retry only every 5 minutes instead (restart
            # storm protection - typical cause: port held by a leftover
            # process, so every freshly started exe dies instantly).
            last_start = self._last_start_ts.get(name, 0)
            if last_start:
                self._consec_fail[name] = self._consec_fail.get(name, 0) + 1
            fails = self._consec_fail.get(name, 0)
            if fails >= 5 and (now - last_start) < 300:
                continue

            # Port-conflict pre-check: if a foreign process (e.g. a leftover
            # old "python main.py" instance) holds the port, the started exe
            # will die instantly. Record WHO holds it for diagnosis.
            extra = ""
            if port:
                owner = find_port_owner(port, proc_name, match_cmd)
                if owner:
                    extra = f" | port {port} held by PID {owner['pid']} ({owner['name']})"

            ok, detail = start_proc(svc)
            self._last_start_ts[name] = now
            self.log_event(name, "auto_restart", ok, detail + extra)
            if ok:
                self.restart_counts[name] = self.restart_counts.get(name, 0) + 1
                self.last_starts[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self):
        """Return current status of all services for the API."""
        cfg = load_config()
        result = []

        # ---- ONE pass over the process table for ALL services ----
        # (instead of one full scan per service - keeps /api/services fast
        # even with many services: single scan + deduped connection lookups)
        procs = {}        # lowercase process name -> [(pid, cmdline-lower, create_time)]
        pid_name = {}     # pid -> display process name
        for proc in psutil.process_iter(["name", "cmdline", "create_time"]):
            try:
                pname = proc.info.get("name") or ""
                if not pname:
                    continue
                procs.setdefault(pname.lower(), []).append(
                    (proc.pid,
                     " ".join(proc.info.get("cmdline") or []).lower(),
                     proc.info.get("create_time"))
                )
                pid_name[proc.pid] = pname
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # All listening TCP ports on the machine: port -> pid
        listen_map = {}
        try:
            for c in psutil.net_connections(kind="tcp"):
                if c.status == "LISTEN" and c.laddr and c.pid:
                    listen_map.setdefault(c.laddr.port, c.pid)
        except Exception:
            pass

        conn_cache = {}  # pid -> sorted listening ports (dedup across services)

        def _ports_of(pid):
            if pid not in conn_cache:
                try:
                    p = psutil.Process(pid)
                    # psutil 6.x renamed connections() -> net_connections()
                    if hasattr(p, "net_connections"):
                        conns = p.net_connections(kind="tcp")
                    else:
                        conns = p.connections(kind="tcp")
                    conn_cache[pid] = sorted({
                        c.laddr.port for c in conns
                        if c.status == "LISTEN" and c.laddr
                    })
                except Exception:
                    conn_cache[pid] = []
            return conn_cache[pid]

        for svc in cfg.get("services", []):
            name = svc.get("name", "")
            proc_name = (svc.get("process") or "").lower()
            match_cmd = (svc.get("match_cmdline") or "").lower()
            port = svc.get("port")

            candidates = procs.get(proc_name, [])
            if match_cmd:
                candidates = [c for c in candidates if match_cmd in c[1]]
            running = len(candidates) > 0

            # Real-time port detection: what does this process ACTUALLY
            # listen on right now? Used both for auto-display (when port
            # is not configured) and to make the listening status accurate:
            # a configured port counts as listening only if THIS service
            # process owns it - not just anyone on the machine.
            detected = []
            create_times = []
            for pid, _cmd, ct in candidates:
                detected.extend(_ports_of(pid))
                if ct:
                    create_times.append(ct)
            detected = sorted(set(detected))

            port_up = None
            port_owner = None
            if port:
                pnum = int(port)
                if pnum in detected:
                    port_up = True
                else:
                    port_up = False
                    opid = listen_map.get(pnum)
                    if opid is not None and opid not in {c[0] for c in candidates}:
                        port_owner = {
                            "pid": opid,
                            "name": pid_name.get(opid) or _proc_name(opid),
                        }

            # how long has the current process instance been alive
            uptime = None
            if running and create_times:
                uptime = max(0, int(time.time() - min(create_times)))

            result.append({
                "name": name,
                "process": proc_name,
                "match_cmdline": match_cmd or "",
                "path": svc.get("path", ""),
                "args": svc.get("args", ""),
                "workdir": svc.get("workdir", ""),
                "port": port,
                "port_listening": port_up,
                "port_owner": port_owner,
                "detected_ports": detected,
                "running": running,
                "uptime": uptime,
                "auto_restart": svc.get("auto_restart", True),
                "restart_count": self.restart_counts.get(name, 0),
                "degraded": self._consec_fail.get(name, 0) >= 5,
                "last_check": self.last_checks.get(name, ""),
                "last_restart": self.last_starts.get(name, ""),
            })
        return result

    def monitor_loop(self):
        while True:
            try:
                self.check_all()
            except Exception as e:
                self.log_event("guardian", "error", False, str(e))
            cfg = load_config()
            time.sleep(cfg.get("check_interval", CHECK_INTERVAL))


guardian = Guardian()


# -------------------------------------------------------------------
# Pydantic models
# -------------------------------------------------------------------
class ServiceCreate(BaseModel):
    name: str
    process: str
    path: str
    args: str = ""
    workdir: str = ""
    port: int | None = None
    auto_restart: bool = True
    match_cmdline: str = ""


# -------------------------------------------------------------------
# FastAPI
# -------------------------------------------------------------------
app = FastAPI(title="Guardian")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "guardian", "version": VERSION}


@app.get("/api/services")
def list_services():
    return {
        "services": guardian.get_status(),
        "check_interval": load_config().get("check_interval", CHECK_INTERVAL),
    }


@app.post("/api/services", status_code=201)
def add_service(req: ServiceCreate):
    cfg = load_config()
    existing = [s for s in cfg["services"] if s["name"] == req.name]
    if existing:
        raise HTTPException(409, f"service '{req.name}' already exists")
    svc = {
        "name": req.name,
        "process": req.process,
        "path": req.path,
        "args": req.args,
        "workdir": req.workdir,
        "port": req.port,
        "auto_restart": req.auto_restart,
    }
    if req.match_cmdline:
        svc["match_cmdline"] = req.match_cmdline
    cfg["services"].append(svc)
    save_config(cfg)
    guardian.log_event(req.name, "added")
    return {"ok": True, "service": svc}


@app.delete("/api/services/{name}")
def remove_service(name: str):
    cfg = load_config()
    before = len(cfg["services"])
    cfg["services"] = [s for s in cfg["services"] if s["name"] != name]
    if len(cfg["services"]) == before:
        raise HTTPException(404, f"service '{name}' not found")
    save_config(cfg)
    guardian.log_event(name, "removed")
    return {"ok": True}


@app.post("/api/services/{name}/start")
def start_service(name: str):
    cfg = load_config()
    svc = next((s for s in cfg["services"] if s["name"] == name), None)
    if not svc:
        raise HTTPException(404, f"service '{name}' not found")
    svc["auto_restart"] = True
    save_config(cfg)
    ok, detail = start_proc(svc)
    guardian.log_event(name, "manual_start", ok, detail)
    if ok:
        guardian.last_starts[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"ok": ok, "detail": detail}


@app.post("/api/services/{name}/stop")
def stop_service(name: str):
    cfg = load_config()
    svc = next((s for s in cfg["services"] if s["name"] == name), None)
    if not svc:
        raise HTTPException(404, f"service '{name}' not found")
    svc["auto_restart"] = False
    save_config(cfg)
    killed = stop_proc(svc)
    guardian.log_event(name, "manual_stop", killed > 0, f"killed {killed} processes")
    return {"ok": killed > 0, "killed": killed}


@app.post("/api/services/{name}/restart")
def restart_service(name: str):
    cfg = load_config()
    svc = next((s for s in cfg["services"] if s["name"] == name), None)
    if not svc:
        raise HTTPException(404, f"service '{name}' not found")
    stop_proc(svc)
    time.sleep(2)
    ok, detail = start_proc(svc)
    guardian.log_event(name, "manual_restart", ok, detail)
    if ok:
        guardian.last_starts[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"ok": ok, "detail": detail}


@app.post("/api/port/{port}/free")
def free_port(port: int):
    """Kill the FOREIGN process holding `port` and restart services bound to it.

    One-click fix for the classic situation: an old instance (e.g. a leftover
    `python main.py` from before guardian existed) keeps the port, so every
    exe the guardian starts dies instantly with a bind error.
    Safety guards: refuses guardian itself, system-critical processes and
    processes that belong to another managed service.
    """
    # never kill a process that belongs to another managed service
    for st in guardian.get_status():
        if st.get("running") and port in (st.get("detected_ports") or []):
            raise HTTPException(
                409,
                f"端口 {port} 正由已守护服务 {st['name']} 使用，不能终止；请检查端口配置",
            )

    critical = {"guardian.exe", "system", "svchost.exe", "lsass.exe", "csrss.exe",
                "services.exe", "wininit.exe", "winlogon.exe", "smss.exe"}
    victims = []
    seen = set()
    try:
        for c in psutil.net_connections(kind="tcp"):
            if (c.status == "LISTEN" and c.laddr and c.laddr.port == int(port)
                    and c.pid and c.pid != os.getpid() and c.pid not in seen):
                seen.add(c.pid)
                try:
                    p = psutil.Process(c.pid)
                    pname = (p.name() or "").lower()
                except psutil.NoSuchProcess:
                    continue
                if pname in critical:
                    raise HTTPException(
                        400,
                        f"端口 {port} 被系统进程 {pname} (PID {c.pid}) 占用，拒绝终止",
                    )
                victims.append(p)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"查询端口占用失败: {e}")

    if not victims:
        return {"ok": True, "killed": 0, "detail": f"端口 {port} 空闲，无需处理"}

    killed = []
    for p in victims:
        try:
            pid, pname = p.pid, (p.name() or "?")
            p.kill()
            p.wait(timeout=5)
            killed.append(f"PID {pid} ({pname})")
            guardian.log_event("port", "free_port", True,
                               f"port {port}: killed PID {pid} ({pname})")
        except psutil.NoSuchProcess:
            continue
        except Exception as e:
            guardian.log_event("port", "free_port", False,
                               f"port {port}: PID {p.pid}: {e}")
            return {"ok": False, "killed": len(killed),
                    "detail": f"终止 PID {p.pid} 失败: {e}"}

    # immediately (re)start every managed service that wants this port,
    # with the backoff counters reset so it starts right now
    cfg = load_config()
    started = []
    for svc in cfg.get("services", []):
        if svc.get("port") == int(port):
            sname = svc.get("name", "")
            guardian._consec_fail[sname] = 0
            guardian._last_start_ts.pop(sname, None)
            ok, detail = start_proc(svc)
            if ok:
                guardian.last_starts[sname] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                started.append(sname)
            else:
                started.append(f"{sname}(失败: {detail})")

    msg = "已终止 " + ", ".join(killed)
    if started:
        msg += "；已重新拉起: " + ", ".join(started)
    return {"ok": True, "killed": len(killed), "detail": msg}


@app.get("/api/system")
def system_status():
    """Self-install / self-health info for the dashboard status line."""
    port = load_config().get("guardian_port", DEFAULT_PORT)
    return {
        "version": VERSION,
        "guardian_port": port,
        "watchdog": task_exists(WATCHDOG_TASK),
        "boot": task_exists(BOOT_TASK),
        "firewall": firewall_rule_exists(port),
        "elevated": _is_elevated(),
        "old_tasks": [t for t in OLD_TASKS if task_exists(t)],
        "install_skip": INSTALL_SKIP_MARKER.exists(),
    }


@app.post("/api/guardian/{action}")
def guardian_action(action: str):
    """Stop / restart / uninstall guardian itself - panel buttons."""
    if action not in ("stop", "restart", "uninstall"):
        raise HTTPException(404, "unknown action")

    def _write_stop_marker():
        try:
            STOP_MARKER.write_text("stopped", encoding="utf-8")
        except Exception:
            pass

    def _exit_soon():
        # give the HTTP response time to flush, then die hard
        threading.Timer(1.5, lambda: os._exit(0)).start()

    if action == "stop":
        _write_stop_marker()
        guardian.log_event("guardian", "manual_stop", True,
                           "stop marker written, exiting")
        _exit_soon()
        return {"ok": True,
                "detail": "守护已停止（不会被自动拉起）。重新启动：双击 guardian.exe"}

    if action == "restart":
        cmd = _self_command() + ["--delayed"]
        subprocess.Popen(cmd, cwd=str(BASE_DIR), creationflags=NO_WINDOW)
        guardian.log_event("guardian", "manual_restart", True, "respawning self")
        _exit_soon()
        return {"ok": True, "detail": "守护正在重启，面板几秒后自动恢复"}

    # uninstall: stop marker + remove tasks + remove firewall rule
    _write_stop_marker()
    failed = []
    for t in [WATCHDOG_TASK, BOOT_TASK] + OLD_TASKS:
        rc, _ = _schtasks("/Delete", "/TN", t, "/F")
        if rc != 0 and task_exists(t):
            failed.append(t)
    port = load_config().get("guardian_port", DEFAULT_PORT)
    try:
        subprocess.run([NETSH, "advfirewall", "firewall", "delete", "rule",
                        f"name={_fw_rule_name(port)}"],
                       capture_output=True, timeout=15,
                       creationflags=NO_WINDOW)
    except Exception:
        pass
    guardian.log_event("guardian", "uninstall", not failed,
                       f"tasks removed{'' if not failed else ', failed: ' + ','.join(failed)}")
    _exit_soon()
    if failed:
        return {"ok": False,
                "detail": f"守护已停止，但这些计划任务删除失败（需管理员手动删）：{', '.join(failed)}"}
    return {"ok": True, "detail": "已卸载：计划任务已删除、防火墙规则已移除、守护已停止"}


@app.put("/api/services/{name}")
def update_service(name: str, req: ServiceCreate):
    cfg = load_config()
    svc = next((s for s in cfg["services"] if s["name"] == name), None)
    if not svc:
        raise HTTPException(404, f"service '{name}' not found")
    svc.update({
        "name": req.name,
        "process": req.process,
        "path": req.path,
        "args": req.args,
        "workdir": req.workdir,
        "port": req.port,
        "auto_restart": req.auto_restart,
    })
    if req.match_cmdline:
        svc["match_cmdline"] = req.match_cmdline
    elif "match_cmdline" in svc:
        del svc["match_cmdline"]
    save_config(cfg)
    return {"ok": True, "service": svc}


@app.get("/api/events")
def get_events(limit: int = MAX_EVENTS):
    """Newest first. The panel paginates these 20 per page."""
    events = list(reversed(guardian.events))[:limit]
    return {"events": events, "total": len(guardian.events),
            "max_events": MAX_EVENTS}


@app.delete("/api/events")
def clear_events():
    """Panel button: wipe the in-memory event list."""
    n = len(guardian.events)
    guardian.events.clear()
    guardian.log_event("guardian", "log_cleared", True, f"cleared {n} events")
    return {"ok": True, "cleared": n}


# -------------------------------------------------------------------
# HTML Dashboard (embedded - no external files needed)
# -------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Guardian - 服务守护面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.header{background:#161b22;padding:14px 24px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.header h1{font-size:20px;color:#58a6ff;display:flex;align-items:center;gap:8px}
.header h1 .icon{width:28px;height:28px;background:#58a6ff;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:16px;color:#0d1117}
.stats{display:flex;gap:20px;font-size:14px;color:#8b949e}
.stats b{font-size:18px}
.stats .run{color:#3fb950}
.stats .stop{color:#f85149}
.container{max-width:1280px;margin:0 auto;padding:20px}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.btn{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-size:14px;transition:.2s}
.btn-add{background:#238636;color:#fff}
.btn-add:hover{background:#2ea043}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;transition:.2s}
.card.run{border-left:3px solid #3fb950}
.card.stop{border-left:3px solid #f85149}
.card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.card-head h3{font-size:16px}
.badge{padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600}
.badge.run{background:rgba(59,185,80,.12);color:#3fb950}
.badge.stop{background:rgba(248,81,73,.12);color:#f85149}
.badge.deg{background:rgba(210,153,34,.15);color:#d29922}
.btn-s.free{color:#d29922;border-color:#9e6a03;margin-left:8px;padding:2px 8px}
.btn-s.free:hover{background:rgba(210,153,34,.15)}
.info{font-size:13px;color:#8b949e;margin-bottom:12px;line-height:1.8}
.info code{background:#21262d;padding:1px 6px;border-radius:3px;color:#c9d1d9;font-family:Consolas,monospace;font-size:12px}
.actions{display:flex;gap:6px}
.btn-s{padding:4px 10px;font-size:12px;border-radius:4px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;cursor:pointer;transition:.15s}
.btn-s:hover{background:#30363d}
.btn-s.start{color:#3fb950;border-color:#238636}
.btn-s.stop{color:#f85149;border-color:#da3633}
.btn-s.restart{color:#58a6ff;border-color:#1f6feb}
.btn-s.remove{color:#8b949e}
.events{margin-top:28px}
.events h2{font-size:16px;color:#58a6ff;margin-bottom:12px}
.evt-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.evt-head h2{margin-bottom:0}
.evt-total{font-size:12px;color:#8b949e;font-weight:400}
.evt-tools{display:flex;align-items:center;gap:10px}
.pager{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#8b949e}
.pager .pginfo{margin:0 6px}
.btn-s.clear{color:#d29922;border-color:#9e6a03}
.btn-s.clear:hover{background:rgba(210,153,34,.15)}
.btn-s:disabled{opacity:.35;cursor:not-allowed}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{text-align:left;padding:8px 12px;color:#8b949e;border-bottom:1px solid #30363d;position:sticky;top:0;background:#161b22}
.tbl td{padding:8px 12px;border-bottom:1px solid #21262d}
.tbl tr:hover td{background:#161b22}
.ev-ok{color:#3fb950}
.ev-fail{color:#f85149}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}
.modal-bg.show{display:flex}
.modal{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px;width:500px;max-width:90%;max-height:90vh;overflow-y:auto}
.modal h2{margin-bottom:16px;color:#58a6ff;font-size:18px}
.fg{margin-bottom:12px}
.fg label{display:block;margin-bottom:4px;font-size:13px;color:#8b949e}
.fg label .req{color:#f85149}
.fg input,.fg select{width:100%;padding:8px;border:1px solid #30363d;border-radius:4px;background:#0d1117;color:#c9d1d9;font-size:14px}
.fg input:focus{outline:none;border-color:#58a6ff}
.modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
.toast{position:fixed;top:16px;right:16px;padding:12px 20px;background:#161b22;border:1px solid #30363d;border-radius:8px;color:#c9d1d9;font-size:14px;z-index:200;animation:sl .3s ease;display:none}
.toast.show{display:block}
.toast.ok{border-color:#3fb950}
.toast.err{border-color:#f85149}
.sysbtns{display:flex;gap:6px}
@keyframes sl{from{transform:translateX(120%)}to{transform:translateX(0)}}
.empty{text-align:center;padding:40px;color:#8b949e}
</style>
</head>
<body>
<div class="header">
  <h1><span class="icon">G</span>Guardian 服务守护</h1>
  <div class="stats" id="stats"></div>
  <div class="sysbtns">
    <button class="btn-s restart" onclick="guardianAct('restart')">重启守护</button>
    <button class="btn-s stop" onclick="guardianAct('stop')">停止守护</button>
    <button class="btn-s remove" onclick="guardianAct('uninstall')">卸载</button>
  </div>
</div>
<div class="container">
  <div class="toolbar">
    <span style="color:#8b949e;font-size:14px" id="intervalTxt">每 30 秒自动巡检，进程挂了自动拉起</span>
    <button class="btn btn-add" onclick="openModal()">+ 添加服务</button>
  </div>
  <div id="sysInfo" style="font-size:12px;color:#8b949e;margin-bottom:12px"></div>
  <div class="grid" id="grid"></div>
  <div class="events">
    <div class="evt-head">
      <h2>事件日志 <span id="evtTotal" class="evt-total"></span></h2>
      <div class="evt-tools">
        <span class="pager" id="pager"></span>
        <button class="btn-s clear" onclick="clearEvents()">清除日志</button>
      </div>
    </div>
    <table class="tbl" id="evtTbl">
      <thead><tr><th>时间</th><th>服务</th><th>事件</th><th>结果</th><th>详情</th></tr></thead>
      <tbody id="evtBody"></tbody>
    </table>
  </div>
</div>
<div class="modal-bg" id="modalBg">
  <div class="modal">
    <h2 id="modalTitle">添加守护服务</h2>
    <div class="fg"><label>服务名称 <span class="req">*</span></label><input id="f_name" placeholder="deploy-task-manager"></div>
    <div class="fg"><label>进程名 <span class="req">*</span></label><input id="f_process" placeholder="python.exe 或 imgagent-server.exe"></div>
    <div class="fg"><label>命令行匹配（可选，用于区分同名进程）</label><input id="f_match" placeholder="main.py"></div>
    <div class="fg"><label>可执行文件路径 <span class="req">*</span></label><input id="f_path" placeholder="D:\Python311\python.exe"></div>
    <div class="fg"><label>启动参数</label><input id="f_args" placeholder="main.py --port 8000"></div>
    <div class="fg"><label>工作目录</label><input id="f_workdir" placeholder="D:\deploy-task-manager\deploy"></div>
    <div class="fg"><label>监听端口（可选，用于显示状态和检测占用）</label><input id="f_port" type="number" placeholder="8000"></div>
    <div class="fg"><label>自动重启</label><select id="f_auto"><option value="true">是 - 挂了自动拉起</option><option value="false">否 - 仅监控不重启</option></select></div>
    <div class="modal-actions">
      <button class="btn-s" onclick="closeModal()">取消</button>
      <button class="btn btn-add" onclick="saveService()">保存</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
function toast(msg,ok){var t=document.getElementById('toast');t.textContent=msg;t.className='toast show '+(ok?'ok':'err');setTimeout(()=>t.className='toast',3000)}
async function api(method,url,body){
  var opt={method:method,headers:{'Content-Type':'application/json'}};
  if(body)opt.body=JSON.stringify(body);
  var r=await fetch(url,opt);
  return r.json();
}
function fmtUp(sec){
  if(sec==null)return '-';
  if(sec<60)return sec+' 秒';
  if(sec<3600)return Math.floor(sec/60)+' 分 '+(sec%60)+' 秒';
  if(sec<86400)return Math.floor(sec/3600)+' 时 '+Math.floor(sec%3600/60)+' 分';
  return Math.floor(sec/86400)+' 天 '+Math.floor(sec%86400/3600)+' 时';
}
function render(services){
  var run=0,stop=0;
  services.forEach(s=>{if(s.running)run++;else stop++});
  document.getElementById('stats').innerHTML='<span>守护 <b>'+(run+stop)+'</b> 个服务</span> <span class="run">运行中 <b class="run">'+run+'</b></span> <span class="stop">已停止 <b class="stop">'+stop+'</b></span>';
  var g=document.getElementById('grid');
  if(!services.length){g.innerHTML='<div class="empty">还没有守护服务，点击右上角「添加服务」</div>';return}
  g.innerHTML=services.map(s=>{
    var cls=s.running?'run':'stop';
    var badge=s.running?'<span class="badge run">RUNNING</span>':'<span class="badge stop">STOPPED</span>';
    if(s.degraded)badge+=' <span class="badge deg">已降频重试</span>';
    var portTxt;
    if (s.port) {
      if(s.port_listening){
        portTxt='端口 <code>'+s.port+'</code> <span style="color:#3fb950">listening</span>';
      }else if(s.port_owner){
        portTxt='端口 <code>'+s.port+'</code> <span style="color:#f85149">被 PID '+s.port_owner.pid+' ('+s.port_owner.name+') 占用</span>'+
          '<button class="btn-s free" onclick="freePort('+s.port+','+s.port_owner.pid+')">释放端口</button>';
      }else{
        portTxt='端口 <code>'+s.port+'</code> <span style="color:#f85149">not listening</span>';
      }
    } else if (s.detected_ports && s.detected_ports.length>0) {
      portTxt='端口 <code>'+s.detected_ports.join('</code> <code>')+'</code> <span style="color:#3fb950">(自动探测)</span>';
    } else {
      portTxt='端口 <code>-</code>';
    }
    var autoTxt=s.auto_restart?'<span style="color:#3fb950">自动重启</span>':'<span style="color:#8b949e">仅监控</span>';
    var degTxt=s.degraded?'<div style="color:#d29922;font-size:12px">连续启动失败已超过 5 次，降频为每 5 分钟重试一次</div>':'';
    return '<div class="card '+cls+'">'+
      '<div class="card-head"><h3>'+s.name+'</h3>'+badge+'</div>'+
      '<div class="info">'+
        '<div>进程 <code>'+s.process+'</code>'+(s.match_cmdline?' (匹配 <code>'+s.match_cmdline+'</code>)':'')+'</div>'+
        '<div>'+portTxt+'</div>'+
        '<div>'+autoTxt+' | 重启 <b>'+s.restart_count+'</b> 次 | 已运行 '+fmtUp(s.uptime)+'</div>'+
        degTxt+
        '<div>上次检查: '+(s.last_check||'-')+'</div>'+
        '<div>上次重启: '+(s.last_restart||'-')+'</div>'+
      '</div>'+
      '<div class="actions">'+
        '<button class="btn-s start" onclick="doAct(\''+s.name+'\',\'start\')">启动</button>'+
        '<button class="btn-s stop" onclick="doAct(\''+s.name+'\',\'stop\')">停止</button>'+
        '<button class="btn-s restart" onclick="doAct(\''+s.name+'\',\'restart\')">重启</button>'+
        '<button class="btn-s remove" onclick="doRemove(\''+s.name+'\')">删除</button>'+
      '</div>'+
    '</div>';
  }).join('');
}
async function freePort(port,pid){
  if(!confirm('将终止占用端口 '+port+' 的进程 PID '+pid+'，并自动拉起需要该端口的服务。继续？'))return;
  var d=await api('POST','/api/port/'+port+'/free');
  toast(d.detail||'已处理',d.ok);
  refresh();
}
async function loadSystem(){
  try{
    var s=await api('GET','/api/system');
    var h=[];
    if(s.watchdog){
      h.push('<span style="color:#3fb950">自启任务：已安装</span>');
    }else{
      h.push('<span style="color:#d29922">自启任务：未安装 —— 右键 guardian.exe 选「以管理员身份运行」一次即可</span>');
    }
    if(s.firewall===false){
      h.push('<span style="color:#d29922">防火墙未放行 '+s.guardian_port+'（远程可能打不开面板）</span>');
    }
    if(s.old_tasks&&s.old_tasks.length){
      h.push('<span style="color:#d29922">旧守护任务残留：'+s.old_tasks.join(', ')+'（重启服务器后自动清理，或以管理员运行一次）</span>');
    }
    var el=document.getElementById('sysInfo');
    if(el)el.innerHTML=h.join(' &nbsp;·&nbsp; ');
  }catch(e){}
}
async function guardianAct(act){
  var msg={
    stop:'确认停止守护？所有被守护的服务将不再被自动拉起（服务本身不会被停止）。重新启动：双击 guardian.exe。',
    restart:'确认重启守护？面板会中断几秒后自动恢复，被守护的服务不受影响。',
    uninstall:'确认卸载守护？将删除自启计划任务、移除防火墙规则并停止守护（文件不删除）。'
  }[act];
  if(!confirm(msg))return;
  try{
    var d=await api('POST','/api/guardian/'+act);
    toast(d.detail||'已执行',d.ok);
  }catch(e){toast('守护正在退出…',true)}
  if(act==='restart'){setTimeout(refresh,5000);setTimeout(loadSystem,5000)}
}
var evtAll=[],evtPage=0,EVT_PAGE_SIZE=20,evtMax=100;
function renderEvents(){
  var total=evtAll.length;
  var pages=Math.max(1,Math.ceil(total/EVT_PAGE_SIZE));
  if(evtPage>pages-1)evtPage=pages-1;
  if(evtPage<0)evtPage=0;
  var rows=evtAll.slice(evtPage*EVT_PAGE_SIZE,(evtPage+1)*EVT_PAGE_SIZE);
  var html=rows.length?rows.map(e=>{
    var r=e.success?'<span class="ev-ok">OK</span>':'<span class="ev-fail">FAIL</span>';
    return '<tr><td>'+e.time+'</td><td>'+e.service+'</td><td>'+e.event+'</td><td>'+r+'</td><td style="color:#8b949e">'+(e.detail||'')+'</td></tr>';
  }).join(''):'<tr><td colspan="5" style="text-align:center;padding:28px;color:#8b949e">暂无日志</td></tr>';
  document.getElementById('evtBody').innerHTML=html;
  document.getElementById('evtTotal').textContent=total?('共 '+total+' 条 · 最多自动保留 '+ (evtMax||100) +' 条'):'';
  var p='<button class="btn-s" '+(evtPage<=0?'disabled':'')+' onclick="evtGo('+(evtPage-1)+')">上一页</button>';
  p+='<span class="pginfo">第 '+(evtPage+1)+' / '+pages+' 页（每页 '+EVT_PAGE_SIZE+' 条）</span>';
  p+='<button class="btn-s" '+(evtPage>=pages-1?'disabled':'')+' onclick="evtGo('+(evtPage+1)+')">下一页</button>';
  document.getElementById('pager').innerHTML=p;
}
function evtGo(p){evtPage=p;renderEvents()}
async function clearEvents(){
  if(!confirm('确认清空事件日志？'))return;
  try{
    var d=await api('DELETE','/api/events');
    toast('已清除 '+(d.cleared!=null?d.cleared:0)+' 条日志',true);
  }catch(e){toast('清除失败',false)}
  evtPage=0;
  refresh();
}
async function refresh(){
  try{
    var d=await api('GET','/api/services');
    render(d.services);
    if(d.check_interval){
      var t=document.getElementById('intervalTxt');
      if(t)t.textContent='每 '+d.check_interval+' 秒自动巡检，进程挂了自动拉起';
    }
  }catch(e){console.log(e)}
  try{
    var ev=await api('GET','/api/events?limit=100');
    evtAll=ev.events||[];
    if(ev.max_events)evtMax=ev.max_events;
    renderEvents();
  }catch(e){console.log(e)}
}
async function doAct(name,act){
  var d=await api('POST','/api/services/'+name+'/'+act);
  toast(name+' '+act+': '+(d.ok?'成功':'失败')+' '+(d.detail||d.killed||''),d.ok);
  refresh();
}
async function doRemove(name){
  if(!confirm('确认删除服务「'+name+'」？'))return;
  await api('DELETE','/api/services/'+name);
  toast(name+' 已删除',true);
  refresh();
}
function openModal(){document.getElementById('modalBg').classList.add('show')}
function closeModal(){document.getElementById('modalBg').classList.remove('show')}
async function saveService(){
  var body={
    name:document.getElementById('f_name').value.trim(),
    process:document.getElementById('f_process').value.trim(),
    match_cmdline:document.getElementById('f_match').value.trim(),
    path:document.getElementById('f_path').value.trim(),
    args:document.getElementById('f_args').value.trim(),
    workdir:document.getElementById('f_workdir').value.trim(),
    port:document.getElementById('f_port').value?parseInt(document.getElementById('f_port').value):null,
    auto_restart:document.getElementById('f_auto').value==='true'
  };
  if(!body.name||!body.process||!body.path){toast('名称、进程名、路径不能为空',false);return}
  var d=await api('POST','/api/services',body);
  if(d.ok){toast(body.name+' 已添加',true);closeModal();
    ['f_name','f_process','f_match','f_path','f_args','f_workdir','f_port'].forEach(id=>document.getElementById(id).value='');
    refresh();
  }else{toast(d.detail||'添加失败',false)}
}
refresh();
loadSystem();
setInterval(refresh,10000);
setInterval(loadSystem,60000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def _write_crash_log(exc_text):
    """Write crash info to guardian-error.log so a failure is NEVER invisible."""
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n===== CRASH {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (v{VERSION}) =====\n")
            f.write(exc_text + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    _args = sys.argv[1:]

    # restart handoff / elevation handoff: give the previous instance
    # time to release the port before we probe it
    if "--delayed" in _args or "--elevated" in _args:
        time.sleep(2.5)

    # Stop marker (written by the panel's 停止/卸载 button):
    #  - launched by Task Scheduler  -> stay stopped, exit quietly
    #  - launched by a human (double-click / reinstall) -> stale intent,
    #    remove the marker and start
    if STOP_MARKER.exists():
        if "--elevated" in _args or not _launched_by_scheduler():
            try:
                STOP_MARKER.unlink()
            except Exception:
                pass
        else:
            sys.exit(0)

    # PyInstaller --noconsole gives stdout/stderr = None.
    # Redirect them to guardian.log (NOT devnull!) so every error is visible.
    try:
        if sys.stdout is None:
            sys.stdout = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
        if sys.stderr is None:
            sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        pass

    try:
        cfg = load_config()
        port = cfg.get("guardian_port", DEFAULT_PORT)
    except BaseException:
        import traceback
        _write_crash_log(traceback.format_exc())
        raise

    # Port pre-check: the watchdog task launches this exe EVERY MINUTE.
    # If the port is already taken, another guardian instance is alive -
    # exit quietly instead of crashing and flooding guardian-error.log.
    import socket as _socket
    _probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        _probe.bind(("0.0.0.0", port))
    except OSError:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"port {port} already in use - another guardian instance "
                    f"is running, exit quietly\n"
                )
        except Exception:
            pass
        sys.exit(0)
    finally:
        _probe.close()

    # ---- self-install (replaces 安装.cmd / manage.ps1) ----
    # GUARDIAN_NO_INSTALL=1 is a test/dev escape hatch: run the dashboard
    # without touching scheduled tasks or the firewall.
    if os.environ.get("GUARDIAN_NO_INSTALL") != "1":
        try:
            if task_exists(WATCHDOG_TASK):
                # already installed: keep firewall + legacy cleanup fresh
                if not firewall_rule_exists(port):
                    ensure_firewall(port)
                cleanup_old_tasks()
            elif _is_elevated():
                results, removed = do_install(port)
                ok = all(v for _, v in results)
                detail = ", ".join(f"{k}:{'OK' if v else 'FAIL'}" for k, v in results)
                if removed:
                    detail += f", removed legacy tasks: {', '.join(removed)}"
                guardian.log_event("guardian", "install", ok, detail)
            elif not INSTALL_SKIP_MARKER.exists():
                # not installed and not elevated: ask UAC once and hand over
                if _relaunch_elevated():
                    sys.exit(0)
                # user declined the UAC prompt - never nag again, just run
                try:
                    INSTALL_SKIP_MARKER.touch()
                except Exception:
                    pass
                guardian.log_event("guardian", "install", False,
                                   "UAC declined - running without autostart tasks")
        except Exception as e:
            try:
                _write_crash_log(f"self-install warning (non-fatal): {e}\n")
            except Exception:
                pass

    try:
        print(f"\n===== Guardian v{VERSION} starting {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} =====")
        print(f"Port: {port}")
        print(f"Config: {CONFIG_FILE}")

        mon_thread = threading.Thread(target=guardian.monitor_loop, daemon=True)
        mon_thread.start()
        print("Monitor thread started")

        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except BaseException:
        # BaseException: uvicorn exits with SystemExit on port-bind failure,
        # which `except Exception` would NOT catch.
        import traceback
        _write_crash_log(traceback.format_exc())
        raise
