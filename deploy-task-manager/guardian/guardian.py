# ===================================================================
# Guardian - Unified Service Guardian with Web Dashboard
# A single exe that monitors ALL services on the server.
# Web UI on port 9000, background thread checks every 60s.
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
DEFAULT_PORT = 9000
CHECK_INTERVAL = 60
MAX_EVENTS = 500

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
            creationflags=0x08000000,  # CREATE_NO_WINDOW
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


# -------------------------------------------------------------------
# Guardian engine
# -------------------------------------------------------------------
class Guardian:
    def __init__(self):
        self.events = []
        self.restart_counts = {}
        self.last_checks = {}
        self.last_starts = {}

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
        for svc in cfg.get("services", []):
            name = svc.get("name", "")
            proc_name = svc.get("process", "")
            match_cmd = svc.get("match_cmdline")
            auto = svc.get("auto_restart", True)
            port = svc.get("port")

            running = is_running(proc_name, match_cmd)
            port_up = get_port_status(port) if port else None
            self.last_checks[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not running and auto:
                ok, detail = start_proc(svc)
                self.log_event(name, "auto_restart", ok, detail)
                if ok:
                    self.restart_counts[name] = self.restart_counts.get(name, 0) + 1
                    self.last_starts[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self):
        """Return current status of all services for the API."""
        cfg = load_config()
        result = []
        for svc in cfg.get("services", []):
            name = svc.get("name", "")
            proc_name = svc.get("process", "")
            match_cmd = svc.get("match_cmdline")
            port = svc.get("port")
            running = is_running(proc_name, match_cmd)
            port_up = get_port_status(port) if port else None
            result.append({
                "name": name,
                "process": proc_name,
                "match_cmdline": match_cmd or "",
                "path": svc.get("path", ""),
                "args": svc.get("args", ""),
                "workdir": svc.get("workdir", ""),
                "port": port,
                "port_listening": port_up,
                "running": running,
                "auto_restart": svc.get("auto_restart", True),
                "restart_count": self.restart_counts.get(name, 0),
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
    return {"status": "ok", "service": "guardian"}


@app.get("/api/services")
def list_services():
    return {"services": guardian.get_status()}


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
        guardian.restart_counts[name] = guardian.restart_counts.get(name, 0) + 1
        guardian.last_starts[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"ok": ok, "detail": detail}


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
def get_events(limit: int = 50):
    events = list(reversed(guardian.events))[:limit]
    return {"events": events}


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
@keyframes sl{from{transform:translateX(120%)}to{transform:translateX(0)}}
.empty{text-align:center;padding:40px;color:#8b949e}
</style>
</head>
<body>
<div class="header">
  <h1><span class="icon">G</span>Guardian 服务守护</h1>
  <div class="stats" id="stats"></div>
</div>
<div class="container">
  <div class="toolbar">
    <span style="color:#8b949e;font-size:14px">每 60 秒自动巡检，进程挂了自动拉起</span>
    <button class="btn btn-add" onclick="openModal()">+ 添加服务</button>
  </div>
  <div class="grid" id="grid"></div>
  <div class="events">
    <h2>事件日志</h2>
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
    <div class="fg"><label>监听端口（可选，仅展示用）</label><input id="f_port" type="number" placeholder="8000"></div>
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
function render(services){
  var run=0,stop=0;
  services.forEach(s=>{if(s.running)run++;else stop++});
  document.getElementById('stats').innerHTML='<span>守护 <b>'+(run+stop)+'</b> 个服务</span> <span class="run">运行中 <b class="run">'+run+'</b></span> <span class="stop">已停止 <b class="stop">'+stop+'</b></span>';
  var g=document.getElementById('grid');
  if(!services.length){g.innerHTML='<div class="empty">还没有守护服务，点击右上角「添加服务」</div>';return}
  g.innerHTML=services.map(s=>{
    var cls=s.running?'run':'stop';
    var badge=s.running?'<span class="badge run">RUNNING</span>':'<span class="badge stop">STOPPED</span>';
    var portTxt=s.port?('端口 <code>'+s.port+'</code> '+(s.port_listening?'<span style="color:#3fb950">listening</span>':'<span style="color:#f85149">not listening</span>')):'端口 <code>-</code>';
    var autoTxt=s.auto_restart?'<span style="color:#3fb950">自动重启</span>':'<span style="color:#8b949e">仅监控</span>';
    return '<div class="card '+cls+'">'+
      '<div class="card-head"><h3>'+s.name+'</h3>'+badge+'</div>'+
      '<div class="info">'+
        '<div>进程 <code>'+s.process+'</code>'+(s.match_cmdline?' (匹配 <code>'+s.match_cmdline+'</code>)':'')+'</div>'+
        '<div>'+portTxt+'</div>'+
        '<div>'+autoTxt+' | 重启 <b>'+s.restart_count+'</b> 次</div>'+
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
function renderEvents(events){
  document.getElementById('evtBody').innerHTML=events.map(e=>{
    var r=e.success?'<span class="ev-ok">OK</span>':'<span class="ev-fail">FAIL</span>';
    return '<tr><td>'+e.time+'</td><td>'+e.service+'</td><td>'+e.event+'</td><td>'+r+'</td><td style="color:#8b949e">'+(e.detail||'')+'</td></tr>';
  }).join('');
}
async function refresh(){
  try{
    var d=await api('GET','/api/services');
    render(d.services);
  }catch(e){console.log(e)}
  try{
    var ev=await api('GET','/api/events?limit=30');
    renderEvents(ev.events);
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
setInterval(refresh,10000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Start monitoring thread
    mon_thread = threading.Thread(target=guardian.monitor_loop, daemon=True)
    mon_thread.start()

    cfg = load_config()
    port = cfg.get("guardian_port", DEFAULT_PORT)

    print(f"Guardian started on port {port}")
    print(f"Dashboard: http://0.0.0.0:{port}")
    print(f"Config: {CONFIG_FILE}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
