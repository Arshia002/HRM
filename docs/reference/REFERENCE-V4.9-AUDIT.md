# SazmanHR v4.9.0 — Reference Package Audit

## Package identity

- Outer ZIP SHA-256: `789703ed3b057c82089a0424a7807db8a0cacc4e0188f865c76d927d711639f9`
- Installer SHA-256: `b323aa8c3d1581ecd26a65f92dd3cf6918f74d2c16918494dc3f24691f89dd5d`
- Embedded payload files: **99**
- Reference version: **4.9.0**

## Exact UI contract

- `index.html` — 46,987 bytes — `3e44e10bf0cea1ccee018bcda50035101ff956a4102a2887d01422695adad3cf`
- `assets/styles.css` — 546,280 bytes — `86f3c46e45200a475862f1e609791d59624d2542c22fa9ba9d5ad366a03182ba`
- `assets/app.js` — 1,137,491 bytes — `d65eebcb8e807effe84c856e35c7a96778773cbb7ea33e753a997e8adf4d9070`
- `assets/login-power-final.webp` — 248,150 bytes — `06f5165bca158ddc61c715aaa7df9070ba8ab72e2742796110e1fc0bcd8966f1`
- `assets/logo.svg` — 455 bytes — `078ed95b4afa50d3dfc14b49d8c34b6a6f99d84fc8894acc2cc9e0ecc20e7adf`
- `assets/modules/access-control.js` — 2,742 bytes — `4e1dab808c0d71f02c44fad7152ad9ef4bdab7372f62ab2f22fc0a8c348cfd20`
- `assets/modules/accessibility.js` — 1,681 bytes — `8c6c5b6d4dac2a9eb29768d10647481c248f5bf21fc2c246bdaab5513ca28315`
- `assets/modules/application-services.js` — 1,581 bytes — `3a7d1f49c2d0a4a4e95129ab06c7a6729db125ba69a1477d42fba9bf81284f8a`
- `assets/modules/audit-center.js` — 2,657 bytes — `481d52dabba05437e453722ddac0f97d1d8d67e0f4b4b272d937ea46c9f4fc47`
- `assets/modules/auth-shell.js` — 7,982 bytes — `3660f37f122bb4366a9ff634f491c4f322450f98e578c92f0bc7b809d5d9d971`
- `assets/modules/backup-client.js` — 2,448 bytes — `0f558d281eb13442fabf07665f8b7a372d4b61d833b4f5e33f2482d0ee046f0a`
- `assets/modules/global-search.js` — 2,958 bytes — `79c015d0f2338c0aa9925a45f892cc5a3f105e9e3b632650a7069c593cc337d9`
- `assets/modules/job-family-engine.js` — 8,316 bytes — `b321b961a7ed7795ef5c609d67e6f636fd8fb5a927d16065733787683907ed88`
- `assets/modules/runtime-core.js` — 7,067 bytes — `46d7acded7dc49bb56bee933d95e0e0c8e77d14d176cbdb86c74bcf3f3131183`
- `assets/modules/security-ui.js` — 1,873 bytes — `e2023d44cde495a92edae12c8b134162f32b88f99b770279f030addee39086df`
- `assets/modules/system-health.js` — 3,454 bytes — `442ed26b48e9a93a4c774f368f45cb2134cd3c1d9aeb96d77ebc4742ab374dba`
- `assets/modules/xlsx-engine.js` — 15,899 bytes — `1821a87d2d94e59dca743ad44d5524ae696949cd197687faf1fb712fe1da3325`

### Navigation/pages
- `formalChart` — ⌘ چارت سازمان
- `statusChart` — ⌁ وضعیت چارت
- `personnelDirectory` — ☷ لیست کلی پرسنل
- `personnelEducation` — 🎓 تحصیلات پرسنل
- `jobFamilies` — ⚡ وضعیت پرسنل
- `personnelAge` — ◷ سن پرسنل
- `reports` — ▤ گزارش‌ها
- `imports` — ⇧ ورود و به‌روزرسانی Excel
- `users` — ♙ مدیریت کاربران
- `history` — ↻ سوابق فعالیت و پشتیبان
- `systemHealth` — ✓ سلامت سیستم
- `settings` — ⚙ تنظیمات

## Data contract

- Personnel: **1356**, unique IDs: **1356**, unique personnel numbers: **1356**
- Chart slides: **53** (pages 1–53)
- Person details coverage: **1356/1356**, total raw detail fields: **67,205**
- Education coverage: **1356/1356**
- Gender coverage: **1356/1356**
- Service history: **684 people / 6,161 records**
- Training history: **507 people / 12,556 records**
- Position catalog: **1,335 entries**, **474 approved detailed positions**
- Vacancy audit: **474 positions**
- Private manifest integrity: **PASS**

### Authoritative summary fields
- `total_count`: `1356`
- `pages`: `53`
- `approved_fixed_posts`: `536`
- `approved_named_posts_legacy`: `32`
- `approved_posts_total`: `568`
- `named_count`: `185`
- `formal_count`: `523`
- `outside_chart_count`: `1`
- `personnel_directory_unique_people`: `1356`
- `job_family_total`: `1356`
- `service_history_personnel_count`: `684`

## Private datasets
- `initial-data.json` — 4,351,500 bytes — `e26f51c8ed03c0a6f1646e52a39505317e91052e4ce531c2e3d915ad396f3c5b` — PASS
- `position-catalog.json` — 270,653 bytes — `4c1cdd2514011b6e62e288b3544774a8b5ce03633a3fa2cd189cf0f9b1c689c7` — PASS
- `placement-models.json` — 3,075,343 bytes — `2e2fc0cf6552aa973cd64b2505a6163b148bf3f10ba0339b524934b1f79fffae` — PASS
- `person-education.json` — 111,624 bytes — `a711c1d9d829f14b51fee193ecaece373193a71f2023b9d46fc8b6b51f0c7e89` — PASS
- `person-details.json` — 7,290,951 bytes — `5bde210bdda3ec435a3bb8fd8fdd9f1aa8eb0b4a101fbda268d89fdb71e27058` — PASS
- `service-history.json` — 1,941,379 bytes — `3c4ed5bc9778f589a2f837530b64dc86aeb35caeae2c45fbad6f65b076fd6a11` — PASS
- `training-history.json` — 2,375,911 bytes — `1665d61bceb06ebba4d59d6dfd53979cf6b62d9e3574e37507b75ea3e7b6d92f` — PASS
- `vacancy-audit.json` — 240,625 bytes — `2b85b930c3cff3609df6f2099e81a3710a34f371bdf08be78263d1417043e024` — PASS
- `gender-map.json` — 21,874 bytes — `e238021ce12da05726682a5611347a68046e76f3d470e9f6a9e5dc08ed5c7578` — PASS

## Key architectural conclusion

The reference installer is a custom Go self-extracting installer with an embedded ZIP payload. The exact UI and private-data contract can be extracted without executing the installer. For the new Windows-service package, transplant the reference **payload contract** (web/static files + protected dataset content/schema), not the old desktop/server executables or installer runtime.