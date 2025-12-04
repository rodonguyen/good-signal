# Technical Debt Report

**Project:** Trading Signal Bot
**Review Date:** 2025-12-04
**Reviewed By:** AI Code Review Specialist
**Total Issues:** 15

---

## Executive Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 4     |
| MEDIUM   | 6     |
| LOW      | 3     |

### Key Findings

1. **Missing error handling for webhook failures** - Discord notifications fail silently without retry
2. **No rate limiting protection** - Vulnerable to exchange API rate limits
3. **Hardcoded configuration values** - Retry delays and timeouts not configurable
4. **Missing test infrastructure** - pytest not installed, tests cannot run
5. **No logging to file** - All logs only to console, no persistence
6. **Security concern** - Webhook URLs may be committed to git

---

## Summary of Issues

### CRITICAL

1. **[CRIT-01]** Missing Retry Logic for Discord Notifications
2. **[CRIT-02]** Secrets Management - Webhook URL in Config File

### HIGH

3. **[HIGH-01]** No Rate Limiting Protection Against Exchange API
4. **[HIGH-02]** Test Infrastructure Not Installed
5. **[HIGH-03]** Missing Input Validation for Configuration Files
6. **[HIGH-04]** No Monitoring or Health Checks

### MEDIUM

7. **[MED-01]** Hardcoded Configuration Values
8. **[MED-02]** No Logging to File (Only Console)
9. **[MED-03]** Missing Database for Signal History
10. **[MED-04]** No Graceful Shutdown Mechanism
11. **[MED-05]** Missing API Authentication (Bybit)
12. **[MED-06]** Insufficient Error Context in Notifications

### LOW

13. **[LOW-01]** Code Documentation Could Be Improved
14. **[LOW-02]** Missing Type Hints in Some Functions
15. **[LOW-03]** No CI/CD Pipeline Configuration

---

## Detailed Findings

### CRITICAL Issues

#### [CRIT-01] Missing Retry Logic for Discord Notifications

**File:** `src/notifiers/discord_notifier.py:65-97`
**Category:** Reliability
**Severity:** CRITICAL

**Description:**
Discord webhook notifications fail silently without retry mechanism. If Discord API is temporarily down or rate-limited, the notification is lost forever. The strategy signal is logged to CSV but user never receives the alert.

**Impact:**
- Trading signals lost during Discord outages
- No visibility when notifications fail
- Users miss critical buy/sell opportunities
- False sense of security (bot appears working but notifications failing)

**Current Code:**
```python
def send(self, message: str) -> bool:
    try:
        response = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
        if response.status_code == 204:
            return True
        else:
            logger.error(f"Discord webhook failed: {response.status_code}")
            return False  # Signal lost, no retry
    except requests.Timeout:
        logger.error("Discord webhook timeout")
        return False  # Signal lost
```

**Recommended Fix:**
```python
def send(self, message: str, max_retries: int = 3) -> bool:
    """Send with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 204:
                return True
            elif response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('Retry-After', 5))
                time.sleep(retry_after)
                continue
            else:
                logger.error(f"Discord webhook failed: {response.status_code}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return False

        except requests.Timeout:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False

    return False
```

**References:**
- Discord API Rate Limits: https://discord.com/developers/docs/topics/rate-limits
- Exponential Backoff Pattern: https://en.wikipedia.org/wiki/Exponential_backoff

**Effort:** Medium
**Auto-fixable:** No

---

#### [CRIT-02] Secrets Management - Webhook URL in Config File

**File:** `config/discord.yaml`
**Category:** Security
**Severity:** CRITICAL

**Description:**
Discord webhook URL is stored in plain text YAML file (`config/discord.yaml`). If this file is accidentally committed to version control, the webhook URL is exposed publicly. An attacker can spam the webhook, causing Discord to rate-limit or revoke it.

**Impact:**
- **Credential Exposure:** Webhook URL leaked in git history
- **Unauthorized Access:** Anyone with URL can send messages to your Discord channel
- **Service Disruption:** Attacker can spam webhook until Discord blocks it
- **OWASP A05:2021:** Security Misconfiguration

**Attack Scenario:**
```bash
# Attacker finds webhook in public repo
curl -X POST https://discord.com/api/webhooks/YOUR_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "Spam message"}'
# Repeated spam causes Discord to rate-limit legitimate notifications
```

**Current Risk:**
```bash
$ git log --all --full-history -- config/discord.yaml
# If this returns commits, webhook URL may be in git history
```

**Recommended Fix:**

1. **Immediate Action:**
```bash
# Add to .gitignore
echo "config/discord.yaml" >> .gitignore

# Remove from git history (if already committed)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch config/discord.yaml" \
  --prune-empty --tag-name-filter cat -- --all

# Regenerate Discord webhook (old one is compromised)
```

2. **Use Environment Variables:**
```python
# src/scheduler.py
import os

webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
if not webhook_url:
    raise ValueError("DISCORD_WEBHOOK_URL environment variable not set")

self.notifier = DiscordNotifier(webhook_url)
```

3. **Create Template Config:**
```yaml
# config/discord.yaml.example
webhook_url: "https://discord.com/api/webhooks/REPLACE_WITH_YOUR_WEBHOOK"

# Instructions:
# 1. Copy this file to discord.yaml
# 2. Replace the placeholder with your actual webhook URL
# 3. Never commit discord.yaml to git
```

4. **Add to README.md:**
```markdown
## Environment Variables

Required environment variables:
- `DISCORD_WEBHOOK_URL`: Discord webhook URL for notifications

Or create `config/discord.yaml` (see discord.yaml.example)
```

**References:**
- OWASP Secrets Management: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- CWE-798: Use of Hard-coded Credentials
- Discord Webhook Security: https://discord.com/developers/docs/resources/webhook

**Effort:** Easy
**Auto-fixable:** No (requires manual secret rotation)

---

### HIGH Issues

#### [HIGH-01] No Rate Limiting Protection Against Exchange API

**File:** `src/data/bybit_fetcher.py:34-43`
**Category:** Reliability / Performance
**Severity:** HIGH

**Description:**
While `enableRateLimit: True` is set in ccxt config, there's no application-level rate limit enforcement. When monitoring multiple assets in `scheduler.py:269`, a simple 1-second `time.sleep(1)` is used. Bybit has strict rate limits (50 requests/5 seconds for public endpoints). If you add many assets, you'll hit rate limits and get IP banned.

**Impact:**
- IP ban from Bybit (temporary or permanent)
- Service downtime when rate limited
- Missed trading signals during cooldown period
- Exponential backoff doesn't prevent initial rate limit hit

**Current Code:**
```python
# src/scheduler.py:269-270
for asset_config in assets:
    self.run_strategy(asset_config)
    time.sleep(1)  # Insufficient for many assets
```

**Bybit Rate Limits (2025):**
- Public endpoints: 50 requests / 5 seconds
- If monitoring 10 assets with 1 API call each = 10 req/iteration
- Hourly schedule = safe, but if changed to 1-minute intervals = ban

**Recommended Fix:**

1. **Add Rate Limiter Class:**
```python
# src/utils/rate_limiter.py
import time
from collections import deque
from datetime import datetime, timedelta

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = timedelta(seconds=period_seconds)
        self.calls = deque()

    def wait_if_needed(self):
        """Block if rate limit would be exceeded."""
        now = datetime.now()

        # Remove calls outside the time window
        while self.calls and now - self.calls[0] > self.period:
            self.calls.popleft()

        # If at limit, wait until oldest call expires
        if len(self.calls) >= self.max_calls:
            sleep_time = (self.calls[0] + self.period - now).total_seconds()
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.calls.popleft()

        # Record this call
        self.calls.append(now)
```

2. **Integrate in Fetcher:**
```python
# src/data/bybit_fetcher.py
from src.utils.rate_limiter import RateLimiter

class BybitFetcher:
    def __init__(self, notifier=None):
        self.exchange = ccxt.bybit({...})
        # Bybit: 50 calls per 5 seconds (use 40 for safety margin)
        self.rate_limiter = RateLimiter(max_calls=40, period_seconds=5)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int):
        self.rate_limiter.wait_if_needed()  # Block if at limit
        # ... rest of fetch logic
```

3. **Remove Manual Sleep in Scheduler:**
```python
# src/scheduler.py:269-270
for asset_config in assets:
    self.run_strategy(asset_config)
    # No manual sleep needed - rate limiter handles it
```

**Testing:**
```python
# Test rate limiter
limiter = RateLimiter(max_calls=5, period_seconds=10)
start = time.time()
for i in range(10):
    limiter.wait_if_needed()
    print(f"Call {i+1} at {time.time() - start:.2f}s")
# Should take ~10 seconds (5 calls, then 5-second wait, then 5 more)
```

**References:**
- Bybit Rate Limits: https://bybit-exchange.github.io/docs/v5/rate-limit
- Token Bucket Algorithm: https://en.wikipedia.org/wiki/Token_bucket

**Effort:** Medium
**Auto-fixable:** No

---

#### [HIGH-02] Test Infrastructure Not Installed

**File:** `requirements.txt` (pytest not installed in environment)
**Category:** Testing / CI/CD
**Severity:** HIGH

**Description:**
`pytest` is listed in `requirements.txt` but not installed in the active Python environment. Running tests fails with "No module named pytest". This means:
1. Tests haven't been run recently (unknown code quality)
2. No CI/CD can be set up (tests would fail)
3. Refactoring is risky (no safety net)

**Impact:**
- Unknown code quality (tests may be passing or failing)
- Regression bugs introduced during changes
- Cannot implement CI/CD pipeline
- Difficult to onboard new developers

**Current State:**
```bash
$ python -m pytest tests/
C:\...\python.exe: No module named pytest
```

**Recommended Fix:**

1. **Install Dependencies:**
```bash
pip install -r requirements.txt

# Or create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Verify Installation:**
```bash
pytest tests/ -v

# Expected output:
# tests/test_bollinger_bands.py::test_calculate PASSED
# tests/test_bybit_fetcher.py::test_fetch PASSED
# ...
```

3. **Add to README.md:**
```markdown
## Development Setup

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run tests:
   ```bash
   pytest tests/ -v --cov=src
   ```
```

4. **Add Pre-commit Hook (Optional):**
```bash
# .git/hooks/pre-commit
#!/bin/bash
pytest tests/ || {
    echo "Tests failed. Commit aborted."
    exit 1
}
```

**Verification:**
```bash
# Run full test suite with coverage
pytest tests/ -v --cov=src --cov-report=html

# Open htmlcov/index.html to see coverage report
```

**Effort:** Trivial
**Auto-fixable:** Yes (just run `pip install -r requirements.txt`)

---

#### [HIGH-03] Missing Input Validation for Configuration Files

**File:** `src/scheduler.py:95-107`, `config/assets.yaml`
**Category:** Reliability / Security
**Severity:** HIGH

**Description:**
Configuration files (`assets.yaml`, `discord.yaml`) are loaded without schema validation. Malformed YAML or incorrect values cause cryptic runtime errors deep in the execution flow. For example:
- Invalid symbol format → API error during fetch
- Missing required fields → KeyError when accessing config
- Invalid timeframe → ccxt exception
- Negative BB period → NaN values, silent signal failures

**Impact:**
- Runtime crashes with unclear error messages
- Silent failures (NaN values propagate)
- Difficult debugging (error far from root cause)
- Injection risk if user-controlled fields are unsanitized

**Current Code:**
```python
# src/scheduler.py:95-107
def _load_yaml(self, path: str) -> Dict:
    with open(path, "r") as f:
        config = yaml.safe_load(f)  # No validation
    return config
```

**Attack Scenario (YAML Injection):**
```yaml
# Malicious config
assets:
  - symbol: "BTCUSDT'; DROP TABLE signals;--"  # SQL injection attempt
    timeframe: "!!python/object/apply:os.system ['rm -rf /']"  # Code execution
```

**Recommended Fix:**

1. **Install Validation Library:**
```bash
pip install pydantic  # Add to requirements.txt
```

2. **Define Config Schema:**
```python
# src/config/schemas.py
from pydantic import BaseModel, Field, validator
from typing import List

class IndicatorParams(BaseModel):
    period: int = Field(gt=0, le=200, description="BB period must be 1-200")
    std_dev: float = Field(gt=0, le=5, description="Std dev must be 0-5")

class AssetConfig(BaseModel):
    symbol: str = Field(regex=r'^[A-Z0-9]{6,12}$', description="Valid symbol format")
    timeframe: str = Field(regex=r'^(1m|5m|15m|1h|4h|1d)$')
    strategy: str = Field(regex=r'^[A-Za-z]+Strategy$')
    indicator: str = Field(regex=r'^[A-Za-z]+$')
    indicator_params: IndicatorParams

    @validator('symbol')
    def validate_symbol(cls, v):
        # Whitelist approach
        allowed_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        if v not in allowed_symbols:
            raise ValueError(f"Symbol {v} not in whitelist: {allowed_symbols}")
        return v

class AssetsConfig(BaseModel):
    assets: List[AssetConfig] = Field(min_items=1, max_items=20)

class DiscordConfig(BaseModel):
    webhook_url: str = Field(regex=r'^https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$')
```

3. **Validate on Load:**
```python
# src/scheduler.py
from src.config.schemas import AssetsConfig, DiscordConfig
from pydantic import ValidationError

def _load_yaml(self, path: str, schema: BaseModel) -> Dict:
    try:
        with open(path, "r") as f:
            raw_config = yaml.safe_load(f)

        # Validate against schema
        validated = schema(**raw_config)
        return validated.dict()

    except ValidationError as e:
        logger.error(f"Invalid config in {path}:")
        for error in e.errors():
            logger.error(f"  {error['loc']}: {error['msg']}")
        raise ValueError(f"Config validation failed for {path}")

# Usage
self.assets_config = self._load_yaml(config_path, AssetsConfig)
self.discord_config = self._load_yaml(discord_config_path, DiscordConfig)
```

4. **Test with Invalid Config:**
```python
# tests/test_config_validation.py
import pytest
from src.config.schemas import AssetConfig

def test_invalid_symbol_format():
    with pytest.raises(ValidationError):
        AssetConfig(
            symbol="BTC-USDT",  # Invalid format (dash not allowed)
            timeframe="1h",
            strategy="BBTrendlineStrategy",
            indicator="BollingerBands",
            indicator_params={"period": 20, "std_dev": 2.0}
        )

def test_negative_period():
    with pytest.raises(ValidationError):
        AssetConfig(
            symbol="BTCUSDT",
            timeframe="1h",
            strategy="BBTrendlineStrategy",
            indicator="BollingerBands",
            indicator_params={"period": -5, "std_dev": 2.0}  # Invalid
        )
```

**References:**
- Pydantic Documentation: https://docs.pydantic.dev/
- OWASP Input Validation: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- CWE-20: Improper Input Validation

**Effort:** Medium
**Auto-fixable:** No

---

#### [HIGH-04] No Monitoring or Health Checks

**File:** `main.py:77`, `src/scheduler.py:317-342`
**Category:** Operations / Observability
**Severity:** HIGH

**Description:**
No monitoring, health checks, or alerting when the bot crashes or hangs. If the bot silently stops (network outage, exception in scheduler loop, infinite hang), you won't know until you manually check. No metrics tracked for:
- Uptime
- Signal generation frequency
- API call success rate
- Notification delivery rate

**Impact:**
- Silent failures (bot stops, you don't know)
- Missed trading opportunities for hours/days
- No visibility into bot health
- Difficult to diagnose issues post-mortem

**Scenarios:**
1. Bot crashes at 2 AM → You don't notice until next day
2. Bybit API is down → Bot hangs forever in retry loop, no timeout
3. Discord webhook revoked → Signals generated but not sent, no alert

**Recommended Fix:**

1. **Add Health Check Endpoint:**
```python
# src/monitoring/health.py
from flask import Flask, jsonify
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

class HealthMonitor:
    def __init__(self):
        self.last_heartbeat = datetime.now()
        self.signals_generated = 0
        self.api_calls_success = 0
        self.api_calls_failed = 0
        self.notifications_sent = 0
        self.notifications_failed = 0

    def heartbeat(self):
        self.last_heartbeat = datetime.now()

    def is_healthy(self) -> bool:
        # Unhealthy if no heartbeat in last 5 minutes
        return datetime.now() - self.last_heartbeat < timedelta(minutes=5)

health_monitor = HealthMonitor()

@app.route('/health')
def health():
    healthy = health_monitor.is_healthy()
    return jsonify({
        'status': 'healthy' if healthy else 'unhealthy',
        'last_heartbeat': health_monitor.last_heartbeat.isoformat(),
        'uptime_seconds': (datetime.now() - start_time).total_seconds(),
        'signals_generated': health_monitor.signals_generated,
        'api_success_rate': health_monitor.api_calls_success /
                           (health_monitor.api_calls_success + health_monitor.api_calls_failed)
                           if (health_monitor.api_calls_success + health_monitor.api_calls_failed) > 0
                           else 0,
        'notification_success_rate': health_monitor.notifications_sent /
                                    (health_monitor.notifications_sent + health_monitor.notifications_failed)
                                    if (health_monitor.notifications_sent + health_monitor.notifications_failed) > 0
                                    else 0
    }), 200 if healthy else 503

# Run in background thread
def run_health_server():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_health_server, daemon=True).start()
```

2. **Integrate in Scheduler:**
```python
# src/scheduler.py
from src.monitoring.health import health_monitor

def run_all_assets(self):
    health_monitor.heartbeat()  # Record activity
    # ... rest of logic

def run_strategy(self, asset_config: Dict[str, Any]):
    try:
        df = self.fetcher.get_ohlcv(...)
        if df is not None:
            health_monitor.api_calls_success += 1
        else:
            health_monitor.api_calls_failed += 1

        signal_data = strategy.generate_signal(df)
        if signal_data:
            health_monitor.signals_generated += 1
            success = self.notifier.send_signal(symbol, signal_data)
            if success:
                health_monitor.notifications_sent += 1
            else:
                health_monitor.notifications_failed += 1
    except Exception as e:
        health_monitor.api_calls_failed += 1
        raise
```

3. **External Monitoring (UptimeRobot, Healthchecks.io):**
```bash
# Ping health endpoint every 5 minutes
# If returns 503 or times out → Send alert email/SMS

# Free services:
# - https://uptimerobot.com (free tier: 50 monitors)
# - https://healthchecks.io (free tier: 20 checks)
```

4. **Add Watchdog Timer:**
```python
# src/monitoring/watchdog.py
import threading
import time
from datetime import datetime, timedelta

class Watchdog:
    def __init__(self, timeout_minutes: int = 10, callback=None):
        self.timeout = timedelta(minutes=timeout_minutes)
        self.last_fed = datetime.now()
        self.callback = callback
        self.running = True

        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()

    def feed(self):
        """Call this regularly to show bot is alive."""
        self.last_fed = datetime.now()

    def _watch(self):
        while self.running:
            time.sleep(60)  # Check every minute
            if datetime.now() - self.last_fed > self.timeout:
                # Bot hasn't fed watchdog in timeout period
                if self.callback:
                    self.callback("Watchdog timeout - bot may be hung")
                break

# Usage in scheduler
def start(self):
    watchdog = Watchdog(
        timeout_minutes=10,
        callback=lambda msg: self.notifier.send_error(msg)
    )

    while True:
        schedule.run_pending()
        watchdog.feed()  # Show we're alive
        time.sleep(60)
```

**References:**
- Health Check Pattern: https://microservices.io/patterns/observability/health-check-api.html
- Prometheus Metrics: https://prometheus.io/docs/practices/instrumentation/

**Effort:** Medium
**Auto-fixable:** No

---

### MEDIUM Issues

#### [MED-01] Hardcoded Configuration Values

**Files:** Multiple
**Category:** Maintainability
**Severity:** MEDIUM

**Description:**
Many configuration values are hardcoded in source code instead of being configurable via config files or environment variables:

| Value | Location | Issue |
|-------|----------|-------|
| `max_retries = 3` | `src/data/bybit_fetcher.py:41` | Cannot adjust retry count without code change |
| `base_retry_delay = 5` | `src/data/bybit_fetcher.py:42` | Retry delay hardcoded |
| `timeout = 10` | `src/notifiers/discord_notifier.py:63` | Webhook timeout not configurable |
| `limit = 100` | `src/scheduler.py:193` | OHLCV fetch limit hardcoded |
| `:00` | `src/scheduler.py:325` | Schedule interval hardcoded (every hour at :00) |

**Impact:**
- Requires code changes for simple configuration adjustments
- Difficult to tune for different environments (dev/staging/prod)
- Cannot adjust parameters for different symbols (BTC vs altcoins may need different settings)

**Recommended Fix:**

Create `config/settings.yaml`:
```yaml
# Application Settings

data_fetcher:
  max_retries: 3
  base_retry_delay: 5  # seconds
  ohlcv_limit: 100

notifier:
  timeout: 10  # seconds
  max_retries: 3

scheduler:
  schedule_interval: "1h"  # Options: 1m, 5m, 15m, 1h
  schedule_offset: ":00"   # Offset within hour (e.g., :00, :15, :30)

logging:
  level: "INFO"
  file: "logs/trading_bot.log"
  max_bytes: 10485760  # 10 MB
  backup_count: 5
```

Load in components:
```python
# src/data/bybit_fetcher.py
def __init__(self, notifier=None, config: Dict = None):
    config = config or {}
    self.max_retries = config.get('max_retries', 3)
    self.base_retry_delay = config.get('base_retry_delay', 5)
```

**Effort:** Easy
**Auto-fixable:** No

---

#### [MED-02] No Logging to File (Only Console)

**File:** `main.py:25-43`
**Category:** Observability
**Severity:** MEDIUM

**Description:**
All logs go to stdout only (`handlers=[logging.StreamHandler(sys.stdout)]`). When running as background service, logs are lost when terminal closes. No persistent logging for:
- Debugging past issues
- Audit trail of signals generated
- Performance analysis
- Compliance requirements

**Impact:**
- Cannot debug issues that occurred in the past
- No audit trail (who did what when)
- Logs lost when process restarts
- Difficult to monitor long-term trends

**Recommended Fix:**

```python
# main.py
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging():
    """Configure logging with both console and file handlers."""

    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)

    # File handler (DEBUG level, rotating)
    file_handler = RotatingFileHandler(
        filename="logs/trading_bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Error file handler (ERROR level only)
    error_handler = RotatingFileHandler(
        filename="logs/errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)
```

**Log Rotation Strategy:**
- `trading_bot.log`: All logs (DEBUG+), 10 MB max, 5 backups (50 MB total)
- `errors.log`: Errors only, 5 MB max, 3 backups (15 MB total)
- Automatic rotation when file size exceeds limit
- Old logs compressed (optional with `gzip` parameter)

**Effort:** Easy
**Auto-fixable:** Yes

---

#### [MED-03] Missing Database for Signal History

**File:** `src/scheduler.py:133-167` (CSV logging)
**Category:** Data Management
**Severity:** MEDIUM

**Description:**
Signals are logged to CSV file (`logs/signals.csv`) which has limitations:
- No indexing (slow queries)
- No concurrent write support (race conditions)
- No data validation (malformed rows)
- Difficult to query historical data
- No relationships (cannot join with other data)
- File corruption risk if process crashes during write

**Impact:**
- Cannot easily analyze trading patterns
- No backtesting infrastructure
- Difficult to generate reports
- File corruption risk
- No support for multiple bot instances (concurrent writes)

**Recommended Fix:**

1. **Install SQLite (Lightweight, No Server):**
```bash
# Already included in Python, no pip install needed
```

2. **Create Database Schema:**
```python
# src/database/models.py
import sqlite3
from datetime import datetime
from pathlib import Path

class SignalDatabase:
    def __init__(self, db_path: str = "data/signals.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                price REAL NOT NULL,
                threshold REAL NOT NULL,
                bb_upper REAL NOT NULL,
                bb_lower REAL NOT NULL,
                bb_middle REAL NOT NULL,
                slope REAL NOT NULL,
                distance REAL NOT NULL,
                bb_width REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_symbol_timestamp (symbol, timestamp),
                INDEX idx_signal_timestamp (signal, timestamp)
            )
        """)
        self.conn.commit()

    def insert_signal(self, symbol: str, signal_data: dict):
        metadata = signal_data.get("metadata", {})
        self.conn.execute("""
            INSERT INTO signals (
                timestamp, symbol, signal, price, threshold,
                bb_upper, bb_lower, bb_middle, slope, distance, bb_width
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data["timestamp"],
            symbol,
            signal_data["signal"],
            signal_data["price"],
            signal_data["threshold"],
            signal_data["bb_upper"],
            signal_data["bb_lower"],
            signal_data["bb_middle"],
            metadata.get("slope", 0),
            metadata.get("distance_to_threshold", 0),
            metadata.get("bb_width", 0)
        ))
        self.conn.commit()

    def get_signals(self, symbol: str = None, start_date: datetime = None,
                   end_date: datetime = None, signal_type: str = None):
        """Query signals with filters."""
        query = "SELECT * FROM signals WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        if signal_type:
            query += " AND signal = ?"
            params.append(signal_type)

        query += " ORDER BY timestamp DESC"

        cursor = self.conn.execute(query, params)
        return cursor.fetchall()
```

3. **Integrate in Scheduler:**
```python
# src/scheduler.py
from src.database.models import SignalDatabase

def __init__(self, config_path: str, discord_config_path: str):
    # ... existing init ...
    self.db = SignalDatabase()

def _log_signal_to_csv(self, symbol: str, signal_data: Dict[str, Any]):
    """Log signal to database."""
    try:
        self.db.insert_signal(symbol, signal_data)
        logger.info(f"Signal logged to database: {symbol} {signal_data['signal']}")
    except Exception as e:
        logger.error(f"Error logging signal to database: {e}")
```

4. **Example Queries:**
```python
# Get all BTC signals in last 7 days
from datetime import datetime, timedelta
db = SignalDatabase()
signals = db.get_signals(
    symbol='BTCUSDT',
    start_date=datetime.now() - timedelta(days=7)
)

# Get BUY signals only
buy_signals = db.get_signals(signal_type='BUY')

# Calculate success rate (would need price tracking)
```

**Migration Path:**
```python
# scripts/migrate_csv_to_db.py
import csv
from src.database.models import SignalDatabase
from datetime import datetime

db = SignalDatabase()
with open('logs/signals.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        signal_data = {
            'timestamp': datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S'),
            'signal': row['signal'],
            'price': float(row['price']),
            'threshold': float(row['threshold']),
            'bb_upper': float(row['bb_upper']),
            'bb_lower': float(row['bb_lower']),
            'bb_middle': float(row['bb_middle']),
            'metadata': {
                'slope': float(row['slope']),
                'distance_to_threshold': float(row['distance']),
                'bb_width': float(row['bb_width'])
            }
        }
        db.insert_signal(row['symbol'], signal_data)
```

**Effort:** Medium
**Auto-fixable:** No

---

#### [MED-04] No Graceful Shutdown Mechanism

**File:** `src/scheduler.py:334-342`
**Category:** Reliability
**Severity:** MEDIUM

**Description:**
When user presses Ctrl+C or sends SIGTERM, the bot catches `KeyboardInterrupt` but doesn't perform cleanup:
- No flush of pending logs
- No database connection close
- No in-flight API requests canceled
- No "shutting down" notification sent to Discord

If shutdown occurs mid-strategy run, data may be inconsistent.

**Impact:**
- Lost logs if buffered logs not flushed
- Database corruption risk (SQLite)
- Confused state (was last signal sent or not?)
- No audit trail of shutdown events

**Current Code:**
```python
# src/scheduler.py:338-342
except KeyboardInterrupt:
    logger.info("Scheduler stopped by user")
    # No cleanup performed
```

**Recommended Fix:**

```python
# src/scheduler.py
import signal
import sys

class TradingScheduler:
    def __init__(self, ...):
        # ... existing init ...
        self.shutdown_flag = False

        # Register signal handlers
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        if self.shutdown_flag:
            logger.warning("Forced shutdown (second signal)")
            sys.exit(1)

        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_flag = True

    def _cleanup(self):
        """Perform cleanup before exit."""
        logger.info("Performing cleanup...")

        # Notify via Discord
        try:
            self.notifier.send("🛑 Trading bot shutting down gracefully")
        except Exception as e:
            logger.error(f"Failed to send shutdown notification: {e}")

        # Close database connection
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")

        # Flush logs
        for handler in logging.root.handlers:
            handler.flush()

        logger.info("Cleanup complete")

    def start(self):
        """Start the scheduler with graceful shutdown support."""
        logger.info("Starting TradingScheduler...")

        schedule.every().hour.at(":00").do(self.run_all_assets)

        # Run immediately
        logger.info("Running initial strategy execution...")
        self.run_all_assets()

        logger.info("Scheduler started. Press Ctrl+C to stop.")

        try:
            while not self.shutdown_flag:
                schedule.run_pending()
                time.sleep(1)  # Check more frequently for shutdown flag

        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self.notifier.send_error(f"Scheduler crashed: {str(e)}")

        finally:
            # Always cleanup, even on exception
            self._cleanup()
            logger.info("Trading bot shut down")
```

**Testing:**
```bash
# Start bot
python main.py

# In another terminal, send SIGTERM
kill -TERM <pid>

# Should see in logs:
# Received signal 15, initiating graceful shutdown...
# Performing cleanup...
# Database connection closed
# Cleanup complete
# Trading bot shut down
```

**Effort:** Easy
**Auto-fixable:** No

---

#### [MED-05] Missing API Authentication (Bybit)

**File:** `src/data/bybit_fetcher.py:34-39`
**Category:** Security / Functionality
**Severity:** MEDIUM

**Description:**
Bybit API client initialized without authentication (no API key/secret). Currently only public endpoints are used (OHLCV data), but:
1. **Rate limits are higher for authenticated requests** (50 → 120 req/5s)
2. **Cannot place orders** (future feature requirement)
3. **Cannot access private endpoints** (account balance, positions)
4. **IP-based rate limiting only** (no per-account limit)

**Impact:**
- Lower rate limits (50 vs 120 requests per 5 seconds)
- Cannot implement automated trading (future requirement)
- Cannot verify signals against actual positions
- All requests tied to IP (VPS IP can be shared, hit limits faster)

**Recommended Fix:**

1. **Add API Credentials to Config:**
```yaml
# config/bybit.yaml (add to .gitignore!)
api_key: "YOUR_API_KEY"
api_secret: "YOUR_API_SECRET"
testnet: false  # Use testnet for development
```

2. **Update Fetcher:**
```python
# src/data/bybit_fetcher.py
import os

class BybitFetcher:
    def __init__(self, notifier=None, api_key: str = None, api_secret: str = None):
        # Load from config or environment
        api_key = api_key or os.getenv('BYBIT_API_KEY')
        api_secret = api_secret or os.getenv('BYBIT_API_SECRET')

        config = {
            "enableRateLimit": True,
            "options": {"defaultType": "linear"}
        }

        # Add credentials if provided (optional for public endpoints)
        if api_key and api_secret:
            config["apiKey"] = api_key
            config["secret"] = api_secret
            logger.info("Bybit client initialized with authentication")
        else:
            logger.warning("Bybit client initialized without authentication (lower rate limits)")

        self.exchange = ccxt.bybit(config)
```

3. **Environment Variables (Recommended):**
```bash
# .env (add to .gitignore)
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true

# Load in main.py
from dotenv import load_dotenv
load_dotenv()
```

4. **Security Best Practices:**
- Create API key with **read-only permissions** (no withdrawal, no trading)
- Whitelist your server IP in Bybit API settings
- Rotate API keys periodically (every 90 days)
- Never commit credentials to git

**Note:** For current use case (read-only public data), authentication is optional but recommended for better rate limits.

**Effort:** Easy
**Auto-fixable:** No (requires manual API key creation)

---

#### [MED-06] Insufficient Error Context in Notifications

**File:** `src/notifiers/discord_notifier.py:174-185`, `src/data/bybit_fetcher.py:110-120`
**Category:** Observability
**Severity:** MEDIUM

**Description:**
Error notifications sent to Discord lack context needed for debugging:
- No stack traces
- No error codes
- No retry attempts remaining
- No link to logs
- No suggestion for resolution

Example current error notification:
```
⚠️ **ERROR** ⚠️

Error processing BTCUSDT: Network error
```

**Impact:**
- Cannot diagnose issues from notification alone
- Must check logs manually (if running on remote server, requires SSH)
- Unclear if error is transient or permanent
- No actionable information for user

**Recommended Fix:**

```python
# src/notifiers/discord_notifier.py
def send_error(self, error_message: str, error: Exception = None,
               context: dict = None) -> bool:
    """
    Send enhanced error notification with context.

    Args:
        error_message: Human-readable error description
        error: Optional exception object
        context: Optional dict with additional context
    """
    formatted = f"⚠️ **ERROR** ⚠️\n\n{error_message}"

    # Add error details
    if error:
        error_type = type(error).__name__
        formatted += f"\n\n**Error Type:** `{error_type}`"
        formatted += f"\n**Details:** `{str(error)}`"

    # Add context
    if context:
        formatted += "\n\n**Context:**"
        for key, value in context.items():
            formatted += f"\n• {key}: `{value}`"

    # Add timestamp
    from datetime import datetime
    formatted += f"\n\n**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # Add actionable suggestions
    if error and isinstance(error, ccxt.NetworkError):
        formatted += "\n\n**Suggested Action:** Check network connectivity or Bybit status"
    elif error and isinstance(error, ccxt.ExchangeError):
        formatted += "\n\n**Suggested Action:** Check Bybit API status or symbol validity"

    return self.send(formatted)

# Usage in scheduler
try:
    df = self.fetcher.get_ohlcv(symbol, timeframe, limit=100)
except Exception as e:
    self.notifier.send_error(
        f"Failed to fetch data for {symbol}",
        error=e,
        context={
            'symbol': symbol,
            'timeframe': timeframe,
            'attempt': f"{attempt}/{max_attempts}",
            'server': os.uname().nodename  # Server hostname
        }
    )
```

**Enhanced Notification Example:**
```
⚠️ **ERROR** ⚠️

Failed to fetch data for BTCUSDT

**Error Type:** `NetworkError`
**Details:** `Connection timeout after 10 seconds`

**Context:**
• symbol: `BTCUSDT`
• timeframe: `1h`
• attempt: `3/3`
• server: `trading-bot-01`

**Time:** 2025-12-04 14:32:15

**Suggested Action:** Check network connectivity or Bybit status
```

**Effort:** Easy
**Auto-fixable:** No

---

### LOW Issues

#### [LOW-01] Code Documentation Could Be Improved

**Files:** Multiple
**Category:** Maintainability
**Severity:** LOW

**Description:**
While code has docstrings, some areas could benefit from additional documentation:
- No architecture diagram
- No sequence diagrams for key flows
- Magic numbers without explanation (e.g., `std_dev=2.0` - why 2.0?)
- Complex logic without inline comments (BB trendline calculation)

**Recommended Fix:**

1. **Add Architecture Diagram to README:**
```markdown
## Architecture

```
┌─────────────┐
│   main.py   │
│   (entry)   │
└──────┬──────┘
       │
       v
┌─────────────────────────────────┐
│   TradingScheduler              │
│   (orchestrator)                │
│   • Loads config                │
│   • Schedules runs              │
│   • Coordinates components      │
└──┬──────┬──────┬────────────┬───┘
   │      │      │            │
   v      v      v            v
┌──────┐ ┌──────┐ ┌────────┐ ┌──────────┐
│Bybit │ │  BB  │ │Strategy│ │ Discord  │
│Fetch │ │Indic.│ │        │ │ Notifier │
└──────┘ └──────┘ └────────┘ └──────────┘
```
```

2. **Add Inline Comments for Complex Logic:**
```python
# src/strategies/bb_trendline.py:102-104
# Calculate trendline slope from last 2 BB values
# Positive slope = bands widening/moving up
# Negative slope = bands narrowing/moving down
upper_slope = float(t_minus_1["bb_upper"] - t_minus_2["bb_upper"])

# Extrapolate to current candle (linear projection)
# If slope = +100, BB_upper was rising by $100/hour
# Threshold = last BB value + projected change
upper_threshold = float(t_minus_1["bb_upper"] + upper_slope)
```

**Effort:** Easy
**Auto-fixable:** No

---

#### [LOW-02] Missing Type Hints in Some Functions

**Files:** `src/scheduler.py:255-273`, others
**Category:** Code Quality
**Severity:** LOW

**Description:**
Some functions lack complete type hints. While most classes use type hints, a few functions don't:

```python
# src/scheduler.py:255
def run_all_assets(self):  # Missing return type hint
    ...

# src/scheduler.py:275
def test_components(self) -> bool:  # Good! Has return type
    ...
```

**Impact:**
- Reduced IDE autocomplete support
- Harder to catch type errors before runtime
- Less self-documenting code

**Recommended Fix:**

```python
from typing import Dict, List, Any, Optional

def run_all_assets(self) -> None:
    """Execute strategies for all configured assets."""
    ...

def run_strategy(self, asset_config: Dict[str, Any]) -> None:
    """Execute strategy for a single asset."""
    ...
```

**Automate with mypy:**
```bash
# Add to requirements.txt
mypy>=1.0.0

# Run type checking
mypy src/ --strict

# Add to pre-commit hook
```

**Effort:** Trivial
**Auto-fixable:** Partially (can use mypy annotations)

---

#### [LOW-03] No CI/CD Pipeline Configuration

**Files:** (Missing `.github/workflows/` or similar)
**Category:** DevOps
**Severity:** LOW

**Description:**
No automated CI/CD pipeline configured. Every code change requires manual testing. No automated:
- Test execution
- Code formatting checks (black)
- Type checking (mypy)
- Dependency security scanning
- Deployment to production

**Impact:**
- Manual testing required for every change
- Risk of deploying untested code
- No automated security scanning
- Slower development velocity

**Recommended Fix:**

Create `.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt

    - name: Run tests
      run: |
        pytest tests/ -v --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

    - name: Check code formatting
      run: |
        black --check .

    - name: Type checking
      run: |
        mypy src/ --strict

    - name: Security scan
      run: |
        pip install safety
        safety check

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
    - uses: actions/checkout@v3

    - name: Deploy to production
      run: |
        # Add deployment steps here
        echo "Deploy to VPS via SSH"
```

**Benefits:**
- Automated testing on every commit
- Catch bugs before merge
- Enforced code quality standards
- Security vulnerability detection

**Effort:** Easy
**Auto-fixable:** No

---

## Recommendations Summary

### Immediate Actions (Critical)

1. **[CRIT-01]** Add retry logic to Discord notifier (prevent lost signals)
2. **[CRIT-02]** Move webhook URL to environment variables (security)

### Short-term (Within 1-2 weeks)

3. **[HIGH-01]** Implement rate limiter for Bybit API
4. **[HIGH-02]** Install test dependencies and run tests
5. **[HIGH-03]** Add configuration validation
6. **[HIGH-04]** Add health check endpoint and monitoring

### Medium-term (Within 1 month)

7. **[MED-01]** Externalize hardcoded configuration
8. **[MED-02]** Implement file logging with rotation
9. **[MED-03]** Migrate from CSV to SQLite database
10. **[MED-04]** Implement graceful shutdown
11. **[MED-05]** Add optional Bybit authentication
12. **[MED-06]** Enhance error notifications with context

### Long-term (Nice to have)

13. **[LOW-01]** Improve documentation and diagrams
14. **[LOW-02]** Add complete type hints
15. **[LOW-03]** Set up CI/CD pipeline

---

## Metrics

### Code Quality Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Test Coverage | Unknown | >80% |
| Type Hint Coverage | ~70% | 100% |
| Code Duplication | Low (1 resolved) | <5% |
| Cyclomatic Complexity | Low (<10) | <15 |
| Documentation Coverage | Medium | High |

### Operational Metrics (Proposed)

| Metric | Current | Target |
|--------|---------|--------|
| Uptime | Unknown | >99% |
| Mean Time to Detect (MTTD) | Manual | <5 min |
| Mean Time to Resolve (MTTR) | Unknown | <1 hour |
| Signal Delivery Rate | Unknown | >99.9% |
| API Call Success Rate | Unknown | >95% |

---

## Conclusion

The codebase is **well-structured and maintainable**, with clear separation of concerns and good use of abstractions (base classes). However, it lacks **production-ready operational features** like monitoring, retry logic, and comprehensive error handling.

**Priority Focus:**
1. Reliability (retries, rate limiting, health checks)
2. Security (secrets management, input validation)
3. Observability (logging, monitoring, error context)

Addressing the CRITICAL and HIGH severity issues will significantly improve reliability and security. The MEDIUM issues are important for long-term maintainability and operational excellence.
