# کلاس‌یار — فاز ۰: برنامه‌ریزی (نسخه‌ی پایتون)

> وضعیت: **منتظر تأیید** — طبق قواعد پرامپت، قبل از تأیید این سند کدی نوشته نمی‌شود.
> ⚠️ فایل `prototype.html` همراه پرامپت ارسال نشده است. ساختار صفحات زیر از متن پرامپت استخراج شده و بعد از دریافت پروتوتایپ تطبیق داده می‌شود.

---

## ۱. نگاشت تکنولوژی از Next.js به پایتون

| نیاز پرامپت | پیشنهاد پایتونی | دلیل |
|---|---|---|
| فول‌استک | **Django 5.x** (Python 3.12+) | احراز هویت، نقش‌ها، CSRF، مایگریشن، i18n و پنل ادمین آماده دارد؛ کد کمتر و امن‌تر |
| UI | قالب‌های Django + **HTMX** + **Alpine.js** (کوچک) | بدون SPA و بدون وابستگی سنگین؛ برای صفحات داشبوردی کافی است |
| استایل | **Tailwind CSS** (باینری standalone، بدون Node) + RTL | همان توکن‌های رنگ پروتوتایپ؛ فونت Vazirmatn self-host در `static/fonts` |
| دیتابیس | PostgreSQL + Django ORM | جای Prisma |
| احراز هویت | `django.contrib.auth` + مدل User سفارشی + نقش | بعداً `django-auth-ldap` یا `mozilla-django-oidc` برای SSO دانشگاه |
| جلسه‌ی زنده | **Django Channels** (WebSocket) + Redis | جای Socket.IO |
| اعتبارسنجی | Django Forms + **Pydantic v2** برای پیام‌های WebSocket و خروجی LLM | جای Zod |
| LLM | کلاس انتزاعی `LLMProvider` (httpx) با پیاده‌سازی‌های OpenAI-compatible / Anthropic / لوکال | از env خوانده می‌شود |
| STT | `STTProvider` + سرویس جدا با **faster-whisper** (FastAPI کوچک) | روی سرور دانشگاه؛ Web Speech فقط fallback آزمایشی |
| تاریخ شمسی | `jdatetime` + فیلتر قالب برای ارقام فارسی | |
| کارهای زمان‌بندی‌شده | **Celery beat** یا `django-q2` (حذف خودکار رونوشت‌ها) | پیشنهاد: Celery چون Redis از قبل هست |
| محدودیت نرخ | `django-ratelimit` | |
| خروجی | `openpyxl` (Excel)، **WeasyPrint** (PDF فارسی) | |
| تست | **pytest + pytest-django** (منطق)، **Playwright Python** (جریان‌ها) | جای Vitest |
| اجرا | Docker Compose: `web` (Daphne/Uvicorn) + `postgres` + `redis` + `whisper` + `worker` | |

> اگر FastAPI + React را ترجیح می‌دهید هم شدنی است، ولی پنل ادمین، CSRF، فرم‌ها و i18n را باید جدا سرهم کرد. پیشنهاد من Django است.

---

## ۲. ساختار پوشه‌ها

```
classyar/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md                    # فارسی
├── pyproject.toml
├── manage.py
├── config/                      # settings (base/dev/prod)، urls، asgi، celery
├── apps/
│   ├── accounts/                # User، Role، ورود، مجوزها (permissions.py)
│   ├── courses/                 # Course، Concept، Session، Enrollment، ورود CSV/Excel
│   ├── questions/               # Question، Option، QuestionConcept، بانک سؤال
│   ├── live/                    # جلسه‌ی زنده: consumers.py (WebSocket)، کد ۶ رقمی، QR، صفحه‌ی موبایل
│   ├── audio/                   # Transcript، TranscriptSignal، ConsentRecord، تشخیص نشانه (rules.py)
│   ├── suggestions/             # Suggestion، SuggestionDecision، جریان تأیید/رد
│   ├── dashboard/               # نمای کلی، دانشجویان، تحلیل یادگیری
│   ├── adminpanel/              # تنظیمات، گزارش بی‌نام، خروجی/حذف داده‌ی دانشجو
│   └── audit/                   # AuditLog + میان‌افزار/سرویس ثبت
├── lib/
│   ├── analytics/               # محاسبات خالص (بدون ORM) + تست واحد
│   │   ├── mastery.py           # تسلط مفهوم، heatmap، سطح اطمینان، «داده کافی نیست»
│   │   ├── items.py             # دشواری، قدرت تمییز، گزینه‌های انحرافی
│   │   └── alerts.py            # افت تسلط/مشارکت، روند مثبت
│   ├── llm/                     # base.py (LLMProvider)، providers/، prompts/system_prompt.md
│   ├── stt/                     # base.py (STTProvider)، whisper_client.py
│   └── jalali.py                # تاریخ شمسی و ارقام فارسی
├── locale/fa/LC_MESSAGES/       # همه‌ی متن‌های UI (gettext) — آماده‌ی افزودن انگلیسی
├── templates/
│   ├── base.html                # سایدبار راست، RTL
│   └── components/              # card, stat_card, tag, heatmap, progress_bar, ring,
│                                # alert, suggestion_item, modal, toast, data_table
├── static/ (fonts/vazirmatn, css, js)
├── services/whisper/            # میکروسرویس faster-whisper (Dockerfile جدا)
├── seed/                        # «مبانی برنامه‌نویسی»: ۴ مفهوم، ۸ جلسه، ۳۰ دانشجو
└── tests/ (unit/, integration/, e2e/)
```

---

## ۳. مدل داده

| مدل | فیلدهای کلیدی |
|---|---|
| `User` | username، full_name، student_no (اختیاری)، role (FK)، is_active |
| `Role` | code: `teacher` / `student` / `admin` |
| `Course` | title، code، term، teacher (FK User) |
| `Enrollment` | course، student — یکتا (course, student) |
| `Concept` | course، title، order |
| `Session` | course، number، date (شمسی در نمایش)، status: planned/live/closed، join_code (۶ رقمی، فقط هنگام live) |
| `Question` | course، text، status: draft/approved، source: manual/ai_draft |
| `QuestionConcept` | question، concept (چند به چند) |
| `Option` | question، text، is_correct، order |
| `SessionQuestion` | session، question، state: pending/open/paused/closed، opened_at |
| `Response` | session_question، student، option، answered_at — یکتا (session_question, student) |
| `Transcript` | session، text، started_at، expires_at (برای حذف خودکار) — **بدون فایل صوت** |
| `TranscriptSignal` | transcript، kind: question/confusion/repeat_request/example_request/topic_shift، span، detector: rules/llm |
| `Suggestion` | course، title، body، evidence (JSON: ارجاع به سؤال/جلسه/مفهوم + n)، confidence: low/medium/high، limitations، status: pending/approved/rejected/edited |
| `SuggestionDecision` | suggestion، decided_by، decision، edited_body، decided_at |
| `AuditLog` | actor، action، object_type، object_id، at، meta (بدون داده‌ی شخصی) |
| `ConsentRecord` | course، teacher، kind: audio/data_processing، text_version، announced_to_class، at |
| `Setting` | scope: global/course، key، value (JSON) — آستانه‌ها، نگهداری، نمایش نام، ارائه‌دهنده‌ها |

**قاعده‌ی تسلط (نسخه‌ی ۱):** برای مفهوم c و دانشجو/کلاس:
`mastery = پاسخ‌های صحیح به سؤال‌های برچسب c ÷ کل پاسخ‌ها به آن سؤال‌ها`.
اگر `n < 10` ← «داده کافی نیست». سطح اطمینان از بازه‌ی Wilson (۹۵٪) محاسبه می‌شود: عرض بازه < ۰٫۱۵ بالا، < ۰٫۳ متوسط، بقیه پایین.

---

## ۴. نقشه‌ی مسیرها

**استاد** (`/t/...`)
- `/t/` نمای کلی · `/t/live/` و `/t/live/<session>/` جلسه‌ی زنده · `/t/audio/<session>/` شنود
- `/t/students/` فهرست · `/t/students/<id>/` جزئیات (مودال HTMX)
- `/t/analytics/` · `/t/suggestions/` · `/t/courses/` (درس، مفهوم، جلسه، بانک سؤال، ورود CSV)
- `/t/evidence/heatmap/<concept>/<session>/` شواهد هر خانه

**دانشجو**
- `/join/` ورود با کد · `/s/live/` صفحه‌ی موبایل پاسخ · `/s/progress/` پیشرفت خودش

**ادمین** (`/a/...`): کاربران، درس‌ها، تنظیمات، حریم خصوصی/نگهداری، گزارش بی‌نام، خروجی/حذف داده‌ی دانشجو

**WebSocket**: `ws/live/<session>/teacher/` و `ws/live/<session>/student/`

> شناسه‌ها در URL عددی/UUID هستند؛ هیچ نام یا شماره‌ی دانشجویی در URL یا لاگ نمی‌آید.

---

## ۵. امنیت (خلاصه)
- همه‌ی querysetها از `scoped_for(user)` می‌گذرند (استاد فقط درس‌های خودش) + تست دسترسی برای هر view
- Argon2 برای رمز، CSRF پیش‌فرض Django، `django-ratelimit` روی ورود و `/join/`
- فیلتر لاگ برای حذف PII؛ ارسال به LLM فقط داده‌ی تجمیعی بی‌نام مگر با مجوز صریح ادمین

---

## ۶. پرسش‌هایی که پاسخشان لازم است
1. **Django** (پیشنهاد من) یا **FastAPI + فرانت جدا**؟
2. فایل **`prototype.html`** را بفرستید تا طراحی دقیقاً از آن برداشته شود.
3. ارائه‌دهنده‌ی پیش‌فرض LLM در فاز ۴ چیست؟ (API ابری یا مدل داخلی دانشگاه — OpenAI-compatible؟)
4. اندازه‌ی مدل Whisper روی سرور (GPU دارد؟ `small` / `medium` / `large-v3`)
