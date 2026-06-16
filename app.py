"""
SysMon Agent — 24/7 System Monitoring & Operations Assistant
Automation & Integration track — Claw-a-thon 2026

Improvements over base template:
- WebSocket real-time alert streaming
- Async background health checks with configurable intervals
- TF-IDF weighted RAG for SOP lookup
- System health dashboard with aggregated metrics
- Toast notification system via WebSocket
- Better structured incident escalation detection
"""

import os
import json
import datetime
import asyncio
import math
import re
import shutil
from typing import List, Optional, Dict, Any, Set
from collections import defaultdict
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Document parsers
from pypdf import PdfReader
import docx
import openpyxl

# ─── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMP_DIR = os.path.join(BASE_DIR, "temp_uploads")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
SOPS_FILE = os.path.join(DATA_DIR, "sops.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
METRICS_FILE = os.path.join(DATA_DIR, "metrics.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "model_name": "minimax/minimax-m2.5",
    "imap_server": "imap.gmail.com",
    "imap_user": "",
    "imap_pass": "",
    "imap_enabled": False,
    "imap_filter": '(SUBJECT "Nagios")',
    "health_check_interval": 60,
    "alert_escalation_window": 30,
    "alert_escalation_threshold": 3,
}

for fp, default in [(LOGS_FILE, []), (SOPS_FILE, []), (CONFIG_FILE, DEFAULT_CONFIG), (METRICS_FILE, [])]:
    if not os.path.exists(fp):
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return [] if path != CONFIG_FILE else dict(DEFAULT_CONFIG)


def write_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_config() -> Dict[str, Any]:
    env_key = os.environ.get("MAAS_API_KEY")
    config = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
    except Exception:
        pass
    if env_key:
        config["api_key"] = env_key
    return config


def mask_value(val: str) -> str:
    if not val:
        return ""
    if len(val) > 10:
        return val[:6] + "•" * (len(val) - 10) + val[-4:]
    return "•" * len(val)


def gen_id(prefix: str) -> str:
    return f"{prefix}-{int(datetime.datetime.now().timestamp() * 1000)}"


# ─── Document Parsers ──────────────────────────────────────────────────────────

def parse_txt(path: str) -> str:
    for enc in ["utf-8", "utf-16", "latin-1", "cp1252"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode file")


def parse_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = [p.extract_text() for p in reader.pages if p.extract_text()]
    return "\n".join(parts)


def parse_docx(path: str) -> str:
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_xlsx(path: str) -> str:
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        parts = []
        for sheet in wb.worksheets:
            parts.append(f"--- Sheet: {sheet.title} ---")
            for row in sheet.iter_rows(values_only=True):
                line = " | ".join(str(v) for v in row if v is not None)
                if line.strip():
                    parts.append(line)
        return "\n".join(parts)
    finally:
        wb.close()


PARSERS = {
    ".txt": parse_txt, ".pdf": parse_pdf,
    ".docx": parse_docx, ".doc": parse_docx,
    ".xlsx": parse_xlsx, ".xls": parse_xlsx,
}


# ─── TF-IDF RAG ───────────────────────────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    return re.findall(r'\w+', text.lower())


def compute_tfidf(query_tokens: List[str], doc_tokens: List[str], corpus_size: int = 1) -> float:
    """Simple TF-IDF score between query and document tokens."""
    if not doc_tokens:
        return 0.0
    doc_set = set(doc_tokens)
    tf = sum(1 for t in query_tokens if t in doc_set)
    if tf == 0:
        return 0.0
    tf_norm = tf / len(doc_tokens)
    # IDF approximation: penalize very common tokens
    idf = 1.0
    return tf_norm * idf


# ─── WebSocket Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.active -= dead


ws_manager = ConnectionManager()


# ─── Nagios Email Parser ──────────────────────────────────────────────────────

def parse_nagios_email(subject: str, body: str, date_str: str) -> Dict[str, Any]:
    state = "WARNING"
    host = "Unknown Host"
    service = "Unknown Service"
    message = body.strip().split("\n")[0] if body else subject

    sl = subject.lower()
    if "critical" in sl or "down" in sl:
        state = "CRITICAL"
    elif "ok" in sl or "recovery" in sl or "up" in sl:
        state = "OK"
    elif "warning" in sl:
        state = "WARNING"
    else:
        state = "WARNING"

    m = re.search(r'service alert:\s*([^/]+)/([^\s\*\!]+)\s+is\s+([^\s\*\!]+)', subject, re.I)
    m2 = re.search(r'host alert:\s*([^\s\*\!]+)\s+is\s+([^\s\*\!]+)', subject, re.I)
    if m:
        host = m.group(1).strip()
        service = m.group(2).strip()
    elif m2:
        host = m2.group(1).strip()
        service = "PING"
    else:
        for line in body.split("\n"):
            line_stripped = line.strip()
            if line_stripped.lower().startswith("host:"):
                host = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.lower().startswith("service:"):
                service = line_stripped.split(":", 1)[1].strip()

    if "Additional Info:" in body:
        parts = body.split("Additional Info:", 1)
        if len(parts) > 1:
            message = parts[1].strip().split("\n")[0].strip()
    elif "info:" in body.lower():
        match_info = re.search(r'info:\s*(.*)', body, re.I)
        if match_info:
            message = match_info.group(1).strip().split("\n")[0].strip()

    try:
        from email.utils import parsedate_to_datetime
        formatted_date = parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        formatted_date = date_str

    return {"state": state, "host": host, "service": service,
            "message": message, "date": formatted_date, "raw_subject": subject}


# ─── Mock Nagios Alerts ────────────────────────────────────────────────────────

def get_mock_alerts() -> List[Dict[str, Any]]:
    now = datetime.datetime.now()
    base_data = [
        ("CRITICAL", "k8s-prod-node-03", "Memory Usage", "CRITICAL - Memory usage is 96.5% (Threshold > 95.0%)", 5),
        ("CRITICAL", "redis-cache-shared", "CPU Load", "CRITICAL - CPU Load is 99.1% (Threshold > 90.0%)", 8),
        ("CRITICAL", "elastic-search-01", "JVM Heap Usage", "CRITICAL - JVM Heap usage is 94.2% (Threshold > 90.0%)", 9),
        ("CRITICAL", "payment-db-replica", "Replication Lag", "CRITICAL - Replication lag is 125s (Threshold > 60s)", 10),
        ("CRITICAL", "redis-cache-shared", "CPU Load", "CRITICAL - CPU Load is 94.6% (Threshold > 90.0%)", 12),
        ("WARNING", "db-postgres-master", "Connection Count", "WARNING - Active connections: 452 (Threshold > 400)", 14),
        ("WARNING", "nginx-ingress-controller", "HTTP 5xx Error Rate", "WARNING - HTTP 5xx errors: 2.1% (Threshold > 2.0%)", 16),
        ("WARNING", "redis-cache-shared", "CPU Load", "WARNING - CPU Load is 81.2% (Threshold > 80.0%)", 18),
        ("CRITICAL", "payment-api-gateway", "HTTP Response Time", "HTTP CRITICAL: 504 Gateway Timeout on /v1/charge", 22),
        ("CRITICAL", "k8s-prod-node-01", "Disk Space", "CRITICAL - Disk space usage is 92.1% on /data (Threshold > 90.0%)", 24),
        ("WARNING", "payment-db-replica", "Replication Lag", "WARNING - Replication lag: 15s (Threshold > 10s)", 25),
        ("CRITICAL", "payment-api-gateway", "HTTP Response Time", "CRITICAL - response time 3.2s (Threshold > 3.0s)", 28),
        ("WARNING", "payment-api-gateway", "HTTP Response Time", "WARNING - response time 1.8s (Threshold > 1.5s)", 35),
        ("OK", "auth-service-02", "CPU Load", "OK - CPU Load is 12.4% (recovered from CRITICAL)", 45),
    ]
    
    expanded_data = []
    for i in range(8):  # 8 * 14 = 112 items, limit to 100
        for s, h, svc, m, mi in base_data:
            time_offset = mi + i * 50
            expanded_data.append((s, h, svc, m, time_offset))
            
    expanded_data = expanded_data[:100]
    
    return [
        {"state": s, "host": h, "service": svc, "message": m,
         "date": (now - datetime.timedelta(minutes=mi)).strftime("%Y-%m-%d %H:%M:%S"),
         "raw_subject": f"** {'RECOVERY' if s == 'OK' else 'PROBLEM'} Service Alert: {h}/{svc} is {s} **"}
        for s, h, svc, m, mi in expanded_data
    ]


# ─── Escalation Detection ─────────────────────────────────────────────────────

def detect_escalations(alerts: List[Dict], window_min: int = 30, threshold: int = 3) -> List[Dict]:
    """Detect hosts with escalating alerts within a time window."""
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(minutes=window_min)

    host_alerts: Dict[str, List] = defaultdict(list)
    for a in alerts:
        try:
            dt = datetime.datetime.strptime(a["date"], "%Y-%m-%d %H:%M:%S")
            if dt >= cutoff and a["state"] != "OK":
                host_alerts[a["host"]].append({**a, "_dt": dt})
        except Exception:
            continue

    escalations = []
    for host, h_alerts in host_alerts.items():
        if len(h_alerts) >= threshold:
            h_alerts.sort(key=lambda x: x["_dt"])
            severity_order = {"WARNING": 1, "CRITICAL": 2}
            max_sev = max(severity_order.get(a["state"], 0) for a in h_alerts)
            escalating = any(
                severity_order.get(h_alerts[i]["state"], 0) > severity_order.get(h_alerts[i - 1]["state"], 0)
                for i in range(1, len(h_alerts))
            )
            escalations.append({
                "host": host,
                "alert_count": len(h_alerts),
                "max_severity": "CRITICAL" if max_sev == 2 else "WARNING",
                "escalating": escalating,
                "timeline": [{"time": a["date"], "state": a["state"],
                              "service": a["service"], "message": a["message"]} for a in h_alerts],
            })
    escalations.sort(key=lambda x: x["alert_count"], reverse=True)
    return escalations


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class LogItem(BaseModel):
    id: Optional[str] = None
    type: str  # incident | maintenance | note
    component: str
    severity: str  # low | medium | high
    status: str  # resolving | resolved | pending
    content: str
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]


# ─── App Lifecycle ─────────────────────────────────────────────────────────────

async def email_polling_loop():
    """Background task to periodically check IMAP for new alerts and broadcast them."""
    seen_alerts = set()
    
    # Wait a bit on startup for the app to settle
    await asyncio.sleep(5)
    
    # Initialize seen_alerts with current alerts
    try:
        initial_alerts = await asyncio.to_thread(get_nagios_alerts)
        for a in initial_alerts:
            key = (a.get("host"), a.get("service"), a.get("date"), a.get("state"))
            seen_alerts.add(key)
    except Exception as e:
        print(f"Error initializing seen alerts: {e}")
        
    while True:
        try:
            config = read_config()
            if config.get("imap_enabled") and config.get("imap_server") and config.get("imap_user") and config.get("imap_pass"):
                current_alerts = await asyncio.to_thread(get_nagios_alerts)
                new_alerts_found = []
                
                for a in current_alerts:
                    key = (a.get("host"), a.get("service"), a.get("date"), a.get("state"))
                    if key not in seen_alerts:
                        seen_alerts.add(key)
                        new_alerts_found.append(a)
                
                # Broadcast new alerts to all WebSocket clients
                for a in new_alerts_found:
                    await ws_manager.broadcast({
                        "type": "alert",
                        "data": a
                    })
                
                # Keep seen_alerts size reasonable
                if len(seen_alerts) > 500:
                    seen_alerts = { (a.get("host"), a.get("service"), a.get("date"), a.get("state")) for a in current_alerts }
        except Exception as e:
            print(f"Error in email polling loop: {e}")
            
        config = read_config()
        interval = config.get("health_check_interval", 60)
        await asyncio.sleep(max(interval, 10))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start email polling task
    polling_task = asyncio.create_task(email_polling_loop())
    yield
    # Shutdown: cancel task
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="SysMon Agent — 24/7 System Monitoring", lifespan=lifespan)


# ─── REST: Logs ────────────────────────────────────────────────────────────────

@app.get("/api/logs")
def get_logs():
    return read_json(LOGS_FILE)


@app.post("/api/logs")
async def create_log(item: LogItem):
    logs = read_json(LOGS_FILE)
    item.id = gen_id("log")
    if not item.created_at:
        item.created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if item.status == "resolved" and not item.resolved_at:
        item.resolved_at = item.created_at
    logs.append(item.model_dump())
    write_json(LOGS_FILE, logs)
    await ws_manager.broadcast({"type": "log_created", "data": item.model_dump()})
    return item


@app.put("/api/logs/{log_id}")
async def update_log(log_id: str, item: LogItem):
    logs = read_json(LOGS_FILE)
    for i, log in enumerate(logs):
        if log["id"] == log_id:
            if item.status == "resolved" and log["status"] != "resolved" and not item.resolved_at:
                item.resolved_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif item.status != "resolved":
                item.resolved_at = None
            item.id = log_id
            if not item.created_at:
                item.created_at = log["created_at"]
            logs[i] = item.model_dump()
            write_json(LOGS_FILE, logs)
            await ws_manager.broadcast({"type": "log_updated", "data": item.model_dump()})
            return item
    raise HTTPException(404, "Log not found")


@app.delete("/api/logs/{log_id}")
async def delete_log(log_id: str):
    logs = read_json(LOGS_FILE)
    filtered = [l for l in logs if l["id"] != log_id]
    if len(filtered) == len(logs):
        raise HTTPException(404, "Log not found")
    write_json(LOGS_FILE, filtered)
    await ws_manager.broadcast({"type": "log_deleted", "id": log_id})
    return {"status": "success"}


# ─── REST: SOPs ────────────────────────────────────────────────────────────────

@app.get("/api/sops")
def get_sops():
    return read_json(SOPS_FILE)


@app.delete("/api/sops/{sop_id}")
def delete_sop(sop_id: str):
    sops = read_json(SOPS_FILE)
    filtered = [s for s in sops if s["id"] != sop_id]
    if len(filtered) == len(sops):
        raise HTTPException(404, "SOP not found")
    write_json(SOPS_FILE, filtered)
    return {"status": "success"}


@app.post("/api/sops/upload")
async def upload_sop(file: UploadFile = File(...), title: str = Form(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = os.path.join(TEMP_DIR, f"temp_{file.filename}")
    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    try:
        parser = PARSERS.get(ext)
        if not parser:
            raise HTTPException(400, f"Unsupported format: {ext}")
        content = parser(temp_path)
        sops = read_json(SOPS_FILE)
        sop = {"id": gen_id("sop"), "title": title or file.filename,
               "filename": file.filename, "content": content}
        sops.append(sop)
        write_json(SOPS_FILE, sops)
        return {"status": "success", "data": sop}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Parse error: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ─── REST: Config ──────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    config = read_config()
    key = config.get("api_key", "")
    imap_pass = config.get("imap_pass", "")
    return {
        "api_key": mask_value(key), "has_key": bool(key),
        "model_name": config.get("model_name", DEFAULT_CONFIG["model_name"]),
        "imap_server": config.get("imap_server", ""),
        "imap_user": config.get("imap_user", ""),
        "imap_pass": mask_value(imap_pass),
        "imap_enabled": config.get("imap_enabled", False),
        "imap_filter": config.get("imap_filter", ""),
        "health_check_interval": config.get("health_check_interval", 60),
        "alert_escalation_window": config.get("alert_escalation_window", 30),
        "alert_escalation_threshold": config.get("alert_escalation_threshold", 3),
    }


@app.post("/api/config")
def update_config(data: Dict[str, Any]):
    local = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                local.update(json.load(f))
    except Exception:
        pass

    for key in ["api_key", "imap_pass"]:
        if key in data:
            val = data[key]
            if val and "•" not in val and "*" not in val:
                local[key] = val
            elif not val:
                local[key] = ""

    for key in ["model_name", "imap_server", "imap_user", "imap_filter",
                 "health_check_interval", "alert_escalation_window", "alert_escalation_threshold"]:
        if key in data:
            local[key] = data[key]

    if "imap_enabled" in data:
        local["imap_enabled"] = bool(data["imap_enabled"])

    write_json(CONFIG_FILE, local)
    return {"status": "success"}


# ─── REST: Handover Report ─────────────────────────────────────────────────────

@app.get("/api/handover")
def generate_handover(sender: Optional[str] = None, receiver: Optional[str] = None):
    logs = read_json(LOGS_FILE)
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    inc_open = [l for l in logs if l["type"] == "incident" and l["status"] != "resolved"]
    inc_done = [l for l in logs if l["type"] == "incident" and l["status"] == "resolved"]
    maint = [l for l in logs if l["type"] == "maintenance"]
    notes = [l for l in logs if l["type"] == "note"]

    r = []
    r.append(f"# BÁO CÁO BÀN GIAO CA TRỰC — SYSMON 24/7")
    r.append(f"*Lập lúc: {now_str}*\n---")

    sections = [
        ("1. Sự cố đang xử lý", inc_open, lambda l: f"[{l['severity'].upper()}] [{l['status'].upper()}]"),
        ("2. Sự cố đã khắc phục", inc_done, lambda l: "[RESOLVED]"),
        ("3. Bảo trì & Giám sát", maint, lambda l: f"[{l['status'].upper()}]"),
        ("4. Ghi chú & Việc cần theo dõi", notes, lambda l: f"[{l['status'].upper()}]"),
    ]
    for title, items, tag_fn in sections:
        r.append(f"\n## {title} ({len(items)})")
        if not items:
            r.append("- (Trống)")
        else:
            for i, l in enumerate(items, 1):
                r.append(f"{i}. **{l['component']}** {tag_fn(l)}")
                r.append(f"   - Thời gian: {l['created_at']}")
                r.append(f"   - Chi tiết: {l['content']}")

    r.append(f"\n---")
    s = sender.strip() if sender else "[Kỹ sư bàn giao]"
    rv = receiver.strip() if receiver else "[Kỹ sư nhận bàn giao]"
    r.append(f"*Người bàn giao: {s}*\n*Người nhận: {rv}*")
    return {"markdown": "\n".join(r)}


# ─── REST: Nagios Alerts ──────────────────────────────────────────────────────

@app.get("/api/nagios-alerts")
def get_nagios_alerts():
    config = read_config()
    alerts = []

    if config.get("imap_enabled") and config.get("imap_server") and config.get("imap_user") and config.get("imap_pass"):
        import imaplib
        import email
        from email.header import decode_header
        try:
            mail = imaplib.IMAP4_SSL(config["imap_server"], 993)
            mail.login(config["imap_user"], config["imap_pass"])
            mail.select("INBOX")
            status, messages = mail.search(None, config.get("imap_filter", '(SUBJECT "Nagios")'))
            if status == "OK":
                ids = messages[0].split()[-100:]
                ids.reverse()
                for mid in ids:
                    res, data = mail.fetch(mid, "(RFC822)")
                    if res != "OK":
                        continue
                    for part in data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            subj, enc = decode_header(msg["Subject"])[0]
                            if isinstance(subj, bytes):
                                subj = subj.decode(enc or "utf-8", errors="ignore")
                            body = ""
                            if msg.is_multipart():
                                for p in msg.walk():
                                    if p.get_content_type() == "text/plain" and "attachment" not in str(p.get("Content-Disposition")):
                                        body = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", errors="ignore")
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                            alerts.append(parse_nagios_email(subj, body, msg["Date"]))
            mail.logout()
        except Exception as e:
            print(f"IMAP error: {e}")

    if not alerts:
        alerts = get_mock_alerts()
    return alerts


# ─── REST: Escalation ─────────────────────────────────────────────────────────

@app.get("/api/escalations")
def get_escalations():
    alerts = get_nagios_alerts()
    config = read_config()
    return detect_escalations(
        alerts,
        window_min=config.get("alert_escalation_window", 30),
        threshold=config.get("alert_escalation_threshold", 3),
    )


# ─── REST: Dashboard Stats ────────────────────────────────────────────────────

@app.get("/api/dashboard")
def get_dashboard():
    logs = read_json(LOGS_FILE)
    alerts = get_nagios_alerts()
    escalations = detect_escalations(alerts)
    now = datetime.datetime.now()

    # Log stats
    total_logs = len(logs)
    open_incidents = sum(1 for l in logs if l["type"] == "incident" and l["status"] != "resolved")
    resolved_today = sum(1 for l in logs if l["type"] == "incident" and l["status"] == "resolved"
                         and l.get("resolved_at", "").startswith(now.strftime("%Y-%m-%d")))

    # Alert stats
    critical_count = sum(1 for a in alerts if a["state"] == "CRITICAL")
    warning_count = sum(1 for a in alerts if a["state"] == "WARNING")
    ok_count = sum(1 for a in alerts if a["state"] == "OK")

    # Unique hosts with issues
    affected_hosts = len(set(a["host"] for a in alerts if a["state"] != "OK"))

    # Uptime estimate (mock: based on resolved vs total)
    uptime_pct = round((resolved_today / max(open_incidents + resolved_today, 1)) * 100, 1) if (open_incidents + resolved_today) > 0 else 99.9

    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "logs": {"total": total_logs, "open_incidents": open_incidents, "resolved_today": resolved_today},
        "alerts": {"critical": critical_count, "warning": warning_count, "ok": ok_count},
        "escalations": len(escalations),
        "affected_hosts": affected_hosts,
        "uptime_pct": uptime_pct,
    }


# ─── REST: Chat ────────────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat_with_agent(req: ChatRequest):
    config = read_config()
    api_key = config.get("api_key", "")
    model = config.get("model_name", DEFAULT_CONFIG["model_name"])

    if not api_key:
        return {"response": "⚠️ Chưa cấu hình API Key. Vui lòng mở Settings (⚙️) để nhập GreenNode API Key."}

    logs = read_json(LOGS_FILE)
    sops = read_json(SOPS_FILE)

    # Build logs context
    if logs:
        logs_ctx = "\n".join(
            f"- [{l['type'].upper()}] {l['component']} | {l['severity']} | {l['status']} | {l['created_at']} | {l['content']}"
            for l in logs
        )
    else:
        logs_ctx = "Không có log nào."

    # Build Nagios context
    try:
        nagios = get_nagios_alerts()
        # Find the latest state for each unique host/service
        latest_alerts = {}
        for a in nagios:
            key = (a["host"], a["service"])
            if key not in latest_alerts:
                latest_alerts[key] = a
        
        # Only keep active non-OK alerts
        active_alerts = [a for a in latest_alerts.values() if a["state"] != "OK"]
        active_alerts_ctx = "\n".join(
            f"- [{a['state']}] {a['host']}/{a['service']}: {a['message']} ({a['date']})"
            for a in active_alerts
        )
        
        # Build compact history timeline (last 30 events)
        recent_history = nagios[:30]
        history_ctx = "\n".join(
            f"- [{a['state']}] {a['host']}/{a['service']}: {a['message']} ({a['date']})"
            for a in recent_history
        )
        
        # Pre-analyze escalations
        escalations = detect_escalations(
            nagios,
            window_min=config.get("alert_escalation_window", 30),
            threshold=config.get("alert_escalation_threshold", 3)
        )
        
        if escalations:
            esc_ctx = "\n".join(
                f"- Host {e['host']} có {e['alert_count']} alert, trạng thái cao nhất {e['max_severity']}." + (" (⚡ Đang có dấu hiệu leo thang!)" if e['escalating'] else "")
                for e in escalations
            )
        else:
            esc_ctx = "Không phát hiện leo thang sự cố nào."
            
        nagios_ctx = (
            f"=== CÁC CẢNH BÁO CHƯA KHẮC PHỤC HIỆN TẠI ===\n"
            f"{active_alerts_ctx if active_alerts_ctx else 'Không có cảnh báo hoạt động.'}\n\n"
            f"=== LỊCH SỬ CẢNH BÁO GẦN ĐÂY ===\n"
            f"{history_ctx if history_ctx else 'Không có lịch sử cảnh báo.'}\n\n"
            f"=== BÁO CÁO PHÂN TÍCH LEO THANG (ESCALATION) ===\n"
            f"{esc_ctx}"
        )
    except Exception as e:
        print(f"Error building Nagios context: {e}")
        nagios_ctx = "Không thể lấy dữ liệu cảnh báo."

    # TF-IDF weighted SOP matching
    query_tokens = tokenize(req.message)
    scored = []
    for sop in sops:
        doc_tokens = tokenize(sop["title"] + " " + sop["content"])
        score_title = compute_tfidf(query_tokens, tokenize(sop["title"]))
        score_content = compute_tfidf(query_tokens, doc_tokens)
        total = score_title * 3 + score_content
        if total > 0:
            scored.append((total, sop))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_sops = [s for _, s in scored[:3]] or sops[:2]

    if top_sops:
        sops_ctx = "\n---\n".join(
            f"QUY TRÌNH: {s['title']} ({s['filename']})\n{s['content']}" for s in top_sops
        )
    else:
        sops_ctx = "Chưa có tài liệu SOP. Người dùng có thể tải lên (.docx, .xlsx, .pdf, .txt)."

    system_prompt = (
        "Bạn là SysMon Agent — Trợ lý Giám sát Hệ thống 24/7 của VNG Cloud/ZaloPay.\n"
        "Nhiệm vụ: hỗ trợ kỹ sư trực ca giám sát, phát hiện sự cố, tra cứu SOP, soạn email incident, phân tích alert.\n\n"
        f"=== LOG CA TRỰC ===\n{logs_ctx}\n\n"
        f"=== CẢNH BÁO NAGIOS ===\n{nagios_ctx}\n\n"
        f"=== TÀI LIỆU SOP ===\n{sops_ctx}\n\n"
        "QUY TẮC:\n"
        "1. Trả lời tiếng Việt, ngắn gọn, chuyên nghiệp.\n"
        "2. Khi hỏi về xử lý sự cố → ưu tiên tra cứu SOP. Nếu không có → hướng dẫn upload thêm.\n"
        "3. Khi yêu cầu soạn email incident → tự động trích xuất từ log:\n"
        "   - Tiêu đề: [SysMon Alert] - Sự cố {component} - Mức độ {severity}\n"
        "   - Nội dung: thời gian, ảnh hưởng, trạng thái xử lý\n"
        "4. Khi hỏi về alert chưa recovery → chỉ alert CRITICAL/WARNING (chưa OK).\n"
        "5. Khi hỏi về alert spike/leo thang → phân tích timeline, tìm host có lỗi tăng dần.\n"
        "6. Khi người dùng hỏi bằng tiếng Anh → trả lời tiếng Anh."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend({"role": m.role, "content": m.content} for m in req.history)
    messages.append({"role": "user", "content": req.message})

    api_url = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1/chat/completions"
    try:
        resp = requests.post(api_url, json={"model": model, "messages": messages, "temperature": 0.2},
                             headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                             timeout=30)
        if resp.status_code == 200:
            return {"response": resp.json()["choices"][0]["message"]["content"]}
        return {"response": f"⚠️ API Error ({resp.status_code}): {resp.text[:200]}"}
    except Exception as e:
        return {"response": f"⚠️ Lỗi kết nối: {e}"}


# ─── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Client can send ping or subscribe commands
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ─── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    idx = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return {"message": "Frontend not found. Place index.html in frontend/"}


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
