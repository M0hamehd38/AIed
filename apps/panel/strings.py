"""Persian UI strings for the teacher panel (kept apart from code and templates' logic)."""
NAV = {
    'dashboard': 'نمای کلی', 'live': 'جلسه‌ی زنده', 'audio': 'شنود و تحلیل صوت', 'students': 'دانشجویان',
    'analytics': 'تحلیل یادگیری', 'suggestions': 'پیشنهادهای هوشمند', 'courses': 'درس‌ها و جلسات', 'settings': 'تنظیمات',
}
SUB = {
    'live': 'آزمونک زنده و پاسخ لحظه‌ای', 'audio': 'فقط با رضایت و کنترل شما', 'students': 'تسلط و مشارکت، با شواهد',
    'analytics': 'مفاهیم، روند ترم و تحلیل سؤال', 'suggestions': 'هیچ پیشنهادی بدون تأیید شما اجرا نمی‌شود',
    'courses': 'مفاهیم، جلسات و بانک سؤال', 'settings': 'آستانه‌ها، حریم خصوصی و نگهداری داده',
}
INSUFFICIENT = 'داده کافی نیست'
NOT_JUDGEMENT = 'این‌ها شاخص‌هایی درباره‌ی مفاهیم هستند، نه ارزیابی شخص.'
CONF = {'high': 'اطمینان بالا', 'medium': 'اطمینان متوسط', 'low': 'اطمینان پایین', 'insufficient': 'داده کافی نیست'}
CONF_CLASS = {'high': 'green', 'medium': 'blue', 'low': 'orange', 'insufficient': 'gray'}
LEVEL_CLASS = {'g': 'green', 'o': 'orange', 'r': 'red'}
LEVEL_COLOR = {'g': 'var(--green)', 'o': 'var(--orange)', 'r': 'var(--red)'}
AUDIT_ACTIONS = {'approve': ('تأیید', 'green'), 'reject': ('رد', 'gray'), 'edit': ('ویرایش', 'purple'),
                 'draft_question': ('ساخت پیش‌نویس', 'blue'), 'settings': ('تنظیمات', 'gray'),
                 'create_course': ('ایجاد درس', 'blue'), 'import_students': ('ورود دانشجو', 'blue'),
                 'approve_question': ('تأیید سؤال', 'green')}
MSG = {
    'approved': 'پیشنهاد تأیید و در لاگ ممیزی ثبت شد.',
    'rejected': 'پیشنهاد رد و در لاگ ممیزی ثبت شد.',
    'edited': 'ویرایش ذخیره شد.',
    'drafted': 'پیش‌نویس به بانک سؤال اضافه شد و تا تأیید شما استفاده نمی‌شود.',
    'settings_saved': 'تنظیمات ذخیره شد.',
    'thresholds_bad': 'آستانه‌ی سبز باید بزرگ‌تر از نارنجی باشد.',
    'course_created': 'درس «{title}» ایجاد شد.',
    'course_active': 'درس فعال: {title}',
    'concept_added': 'مفهوم اضافه شد.',
    'session_added': 'جلسه‌ی {n} اضافه شد.',
    'session_bad': 'تاریخ را به شکل ۱۴۰۵/۰۷/۳۰ و موضوع جلسه را وارد کنید.',
    'question_added': 'سؤال به بانک اضافه شد.',
    'question_bad': 'متن سؤال، هر چهار گزینه و دست‌کم یک مفهوم لازم است.',
    'question_approved': 'سؤال تأیید شد و به بانک اضافه شد.',
    'csv_done': '{n} دانشجو اضافه شد.',
    'csv_skipped': '{n} ردیف نامعتبر یا تکراری نادیده گرفته شد.',
    'csv_bad': 'فایل CSV خوانده نشد. ستون‌ها باید «کد، نام» باشند و فایل با UTF-8 ذخیره شده باشد.',
    'course_bad': 'نام درس و دست‌کم یک مفهوم لازم است.',
}
