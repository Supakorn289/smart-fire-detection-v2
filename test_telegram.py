#!/usr/bin/env python3
from notify import send_telegram
ok = send_telegram('✅ Smart Fire Detection v2: Telegram test passed')
raise SystemExit(0 if ok else 1)
