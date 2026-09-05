# چک‌لیست استقرار Production HRM

## قبل از نصب
- Windows Server 2022 64-bit
- VM/Server اختصاصی ترجیحاً 8 Core / 32 GB / 1 TB SSD
- Static internal IP
- Internal DNS record برای HRM
- Firewall rule فقط بین Clientهای مجاز و TCP 8765
- مقصد Backup ثانویه از IT
- مشخص شدن 2 Super Admin و 4 HR Admin

## نصب
- فقط Artifact سبز GitHub با SHA-256 ثبت‌شده استفاده شود.
- Server component روی Server نصب شود.
- Client component روی 6 سیستم منابع انسانی نصب شود.
- ورود اولیه و تغییر اجباری رمز انجام شود.
- TLS fingerprint/pinning روی Clientها تأیید شود.

## پذیرش
- Health/TLS/Service/ACL PASS
- 6 Client همزمان PASS
- ثبت و مشاهده جابه‌جایی پرسنلی PASS
- Backup محلی و ثانویه PASS
- Restore آزمایشی PASS
- قطع/وصل شبکه PASS
- Audit chain PASS
- 0 Critical Bug / 0 Data Loss / 0 Security Blocker
