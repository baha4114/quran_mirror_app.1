# -*- coding: utf-8 -*-
"""
منطق ویژگی‌های پیشرفته (مستقل از رابط کاربری):
- پردازش دورانی (چرخش ارقام)
- ساخت پرامپت تحلیل معنایی برای هوش مصنوعی
- نرمال‌سازی متن برای جستجوی پیشرفته
- تجزیهٔ فایل پشتیبان برای بازیابی
همهٔ توابع خالص هستند و به Kivy وابسته نیستند.
"""
import re


# ------------------------------------------------------------------
# پردازش دورانی (rotation) — منتقل‌شده از نسخهٔ دسکتاپ
# ------------------------------------------------------------------
def generate_rotation_cards(data, S, A):
    """کارت‌ها را با ترکیب ارقام خام سوره+آیه و چرخش راست تولید می‌کند.
    خروجی: لیستی از دیکشنری کارت‌ها (مثل core.process_matrix).
    """
    cards = []
    seed = data.get(S, A)
    if seed is None:
        return cards
    cards.append({
        'kind': 'seed', 'mode': 'بذر ساختاری (دورانی)',
        's': S, 'a': A, 'arb': seed['arb'], 'pers': seed['pers'],
        'is_fallback': False, 'reason': '',
    })
    num_str = str(S) + str(A)
    original = num_str
    seen = set()
    rc = 0
    while True:
        if rc > 0:
            num_str = num_str[-1] + num_str[:-1]
        if rc > 0 and num_str == original:
            break
        if rc > 24:  # محافظ در برابر حلقهٔ بی‌پایان
            break
        if len(num_str) >= 2:
            s_new = int(num_str[:2])
            a_part = num_str[2:]
            a_new = int(a_part) if a_part else 1
        else:
            s_new = int(num_str)
            a_new = 1
        fs, fa, is_fb, msg = data.apply_circular(s_new, a_new)
        if fs is not None:
            d = data.get(fs, fa)
            if d is not None and (fs, fa) not in seen:
                seen.add((fs, fa))
                if rc == 0:
                    mode = 'ترکیب اولیه %s ← %s:%s' % (num_str, fs, fa)
                else:
                    mode = 'چرخش %d (%s) ← %s:%s' % (rc, num_str, fs, fa)
                cards.append({
                    'kind': 'target', 'mode': mode, 's': fs, 'a': fa,
                    'arb': d['arb'], 'pers': d['pers'],
                    'is_fallback': is_fb, 'reason': (msg if is_fb else ''),
                })
        rc += 1
    return cards


# ------------------------------------------------------------------
# جستجوی پیشرفته — نرمال‌سازی عربی/فارسی
# ------------------------------------------------------------------
def normalize_arabic_persian(text):
    if not isinstance(text, str):
        return ''
    text = text.strip()
    text = re.sub(r'[\u064B-\u065F]', '', text)   # اعراب
    text = re.sub(r'\u0651', '', text)             # تشدید
    text = re.sub(r'\u0653', '', text)             # مد
    text = re.sub(r'[\u0625\u0623\u0671\u0622]', '\u0627', text)  # انواع الف ← ا
    text = re.sub(r'[\u064A\u0649]', '\u06CC', text)              # ي/ى ← ی
    text = re.sub(r'\u0643', '\u06A9', text)                       # ك ← ک
    text = re.sub(r'\u0629', '\u0647', text)                       # ة ← ه
    text = re.sub(r'\u0640', '', text)                             # کشیده
    text = re.sub(r'[^\w\s\u0600-\u06FF]', '', text)
    return text.lower()


# ------------------------------------------------------------------
# پرامپت تحلیل معنایی برای هوش مصنوعی
# ------------------------------------------------------------------
SYSTEM_PROMPT = """شما یک پژوهشگر ارشد در زبان‌شناسی عربی، تفسیر و تحلیل ساختاری، ریاضی و هولوگرافیک قرآن هستید.
من در حال بررسی یک «شبکهٔ دادهٔ خودتراز» در قرآن هستم. الگوریتم ما یک آیه را به عنوان «بذر» می‌گیرد و با اعمال هفت عملگر ریاضی، مقصدهای بالقوهٔ آینه‌ای تولید می‌کند. وظیفهٔ شما تحلیل معنایی و اعتبارسنجی این کشف‌هاست.

هر عملگر «قانون رفتاری» اختصاصی خود را دارد؛ هر کشف را دقیقاً بر اساس قانون همان عملگر بسنجید:
۱. T1 (جابجایی خالص): رابطهٔ «علت و معلول» یا «فرمان و نتیجه» (بذر دستور می‌دهد، مقصد نتیجه را می‌گوید).
۲. T2 (تقارن درجا کامل): «تکمیل پازل داستانی» — قرینه‌شدن دقیق نام شخص، مکان یا رویداد در هر دو.
۳. T3 (تقارن درجا فقط سوره): «پژواک دقیق کلمات» — تکرار یک عبارت طولانی یا هم‌آغازی مطلق.
۴. T4 (تقارن درجا فقط آیه): چون هر دو در یک سوره‌اند، «تقابل و تضاد» (مؤمن/منافق، بهشت/جهنم).
۵. T5 (جابجایی + تقارن کامل): «دیالوگ متقاطع» — بذر پرسشی صریح (به‌ویژه دربارهٔ قیامت)، مقصد پاسخی کیهانی.
۶. T6 (جابجایی + تقارن فقط سوره): واژگان «اعتراف» (قالوا، یا ویلنا، سبحانک) و تصویر دادگاه الهی.
۷. T7 (جابجایی + تقارن فقط آیه): «تمثیل‌های موازی» (نور، شجره) یا تسبیح کائنات.

خروجی را با ساختار HTML زیبا و راست‌چین (RTL) و با تگ‌های <b>، <ul>، <br> ارائه دهید و برای هر کشف:
۱) تحلیل کوتاه کالبد و مفهوم بذر و مقصد،
۲) بررسی انتقادی رابطه بر پایهٔ قانون اختصاصی عملگر،
۳) تعیین نوع رابطهٔ نهایی (از: تقابل کامل، مکمل و بسط‌دهنده، گفت و گو، علت و معلول، پرسش و پاسخ)."""


def build_user_data_prompt(favs):
    groups = {}
    for fav in favs:
        mode = fav.get('mode', '') or 'نامشخص'
        groups.setdefault(mode, []).append(fav)
    lines = ['در ادامه فهرست کشفیات بر اساس رفتارهای کشف‌شده آمده است:\n']
    for mode, items in groups.items():
        lines.append('## رفتار: %s (تعداد: %d)' % (mode, len(items)))
        for idx, fav in enumerate(items, 1):
            lines.append('### کشف %d:' % idx)
            lines.append('- مبدأ: سوره %s آیه %s' % (fav.get('seed_s'), fav.get('seed_a')))
            lines.append('  متن عربی: %s' % fav.get('seed_arb', ''))
            lines.append('  ترجمه: %s' % fav.get('seed_pers', ''))
            if 'target_s' in fav and fav.get('target_s') is not None:
                lines.append('- مقصد: سوره %s آیه %s' % (fav.get('target_s'), fav.get('target_a')))
                lines.append('  متن عربی: %s' % fav.get('target_arb', ''))
                lines.append('  ترجمه: %s' % fav.get('target_pers', ''))
            else:
                if fav.get('pair_type') == 'operator_pair':
                    lines.append('- نوع: جفت عملگری (رابطهٔ آینه‌ای مستقیم بین دو خروجی)')
                for t_idx, target in enumerate(fav.get('all_targets', []), 1):
                    lines.append('- خروجی %d (%s): سوره %s آیه %s'
                                 % (t_idx, target.get('operator', ''), target.get('s'), target.get('a')))
                    lines.append('  متن عربی: %s' % target.get('arb', ''))
                    lines.append('  ترجمه: %s' % target.get('pers', ''))
            if fav.get('is_doubtful'):
                lines.append('- وضعیت ثبت: تردیدی (پژوهشگر در قطعیت این کشف تردید دارد)')
            lines.append('- یادداشت پژوهشگر: %s' % fav.get('note', ''))
            lines.append('- رفتار ثبت‌شده: %s' % fav.get('relation_type', 'نامشخص'))
            lines.append('')
        lines.append('---')
    lines.append('\nلطفاً با بررسی این داده‌ها تحلیل درخواستی را انجام دهید. خروجی حتماً HTML با استایل زیبا باشد.')
    return '\n'.join(lines)


def build_semantic_prompt(favs):
    return SYSTEM_PROMPT + '\n\n' + build_user_data_prompt(favs)


# ------------------------------------------------------------------
# تجزیهٔ فایل پشتیبان برای بازیابی
# ------------------------------------------------------------------
def _unpack_clean_groups(groups):
    items = []
    for g in groups or []:
        for e in g.get('items', []):
            seed = e.get('seed', {}) or {}
            tgt = e.get('target', {}) or {}
            items.append({
                'mode': e.get('mode', ''),
                'seed_s': seed.get('sura'), 'seed_a': seed.get('ayah'),
                'seed_arb': seed.get('arabic', ''), 'seed_pers': seed.get('translation', ''),
                'target_s': tgt.get('sura'), 'target_a': tgt.get('ayah'),
                'target_arb': tgt.get('arabic', ''), 'target_pers': tgt.get('translation', ''),
                'relation_type': e.get('relation_type', 'نامشخص'),
                'is_doubtful': bool(e.get('is_doubtful', False)),
                'note': e.get('note', ''), 'date': e.get('date', ''),
            })
    return items


def parse_backup(payload):
    """از محتوای JSON پشتیبان، (favs, featured) را می‌سازد.
    هم قالب تمیزِ خروجی برنامه و هم فهرست خام را می‌پذیرد.
    """
    if isinstance(payload, dict):
        if 'lab' in payload or 'featured' in payload:
            favs = _unpack_clean_groups(payload.get('lab'))
            featured = _unpack_clean_groups(payload.get('featured'))
            return favs, featured
        # شاید دیکشنری شامل favs/featured خام باشد
        if 'favs' in payload:
            return payload.get('favs') or [], payload.get('featured') or []
    if isinstance(payload, list):
        return payload, []
    return [], []


# ------------------------------------------------------------------
# تبدیل ساده HTML به متن (نمایش داخل برنامه در صورت نبود مرورگر)
# ------------------------------------------------------------------
def strip_html(html):
    if not html:
        return ''
    text = re.sub(r'(?is)<(script|style).*?</\1>', '', html)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|li|h[1-6]|tr)>', '\n', text)
    text = re.sub(r'(?i)<li[^>]*>', '• ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()


# ------------------------------------------------------------------
# پرامپت پیش‌بینی معنایی (۷ قانون T1..T7) — منتقل‌شده از نسخهٔ ویندوز
# ------------------------------------------------------------------
def build_prediction_prompt(seed_s, seed_a, seed_arb, seed_pers, preds):
    """پرامپت کمک به پیش‌بینی معنایی برای یک بذر و ۷ مقصد آن.
    preds: فهرستی از دیکشنری‌ها با کلیدهای rank, op_code, s, a, arb, pers, is_fallback
    """
    header = (
        "شما یک پژوهشگر ارشد در زمینه زبان‌شناسی عربی، تفسیر و تحلیل ساختاری، ریاضی و هولوگرافیک قرآن هستید.\n"
        "من در حال بررسی یک شبکه داده‌ای خودتراز در قرآن هستم. الگوریتم ما یک آیه را به عنوان «بذر» گرفته و با اعمال ۷ عملگر ریاضی، ۷ مقصد بالقوه تولید کرده است. تنها یکی از این مقاصد، جفتِ آینه‌ای و همتای پنهانِ بذر است.\n\n"
        "بذر (سوره " + str(seed_s) + " آیه " + str(seed_a) + "):\n"
        "متن عربی: " + str(seed_arb) + "\n"
        "ترجمه: " + str(seed_pers) + "\n\n"
        "در زیر ۷ مقصد احتمالی آورده شده است. وظیفه شما این است که هر گزینه را «صرفاً و دقیقاً» بر اساس قانونِ اختصاصیِ همان عملگر در ماتریس زیر بررسی کنید:\n\n"
        "🔍 ماتریس رفتاری (قوانین بررسی گزینه‌ها):\n"
        "۱. اگر عملگر گزینه (T1 - جابجایی خالص) است: در بذر و مقصد به دنبال رابطه «علت و معلول» یا «فرمان و نتیجه» باشید (مثلاً بذر دستور می‌دهد، مقصد نتیجه آن را می‌گوید).\n"
        "۲. اگر عملگر گزینه (T2 - تقارن درجا کامل) است: به دنبال «تکمیل پازل داستانی» باشید. آیا نام یک شخص، مکان یا یک رویداد خاص در هر دو دقیقاً قرینه شده است؟\n"
        "۳. اگر عملگر گزینه (T3 - تقارن درجا فقط سوره) است: به دنبال «پژواک دقیق کلمات» باشید. باید یک عبارت طولانی یا هم‌آغازی مطلق در هر دو آیه کپی شده باشد.\n"
        "۴. اگر عملگر گزینه (T4 - تقارن درجا فقط آیه) است: چون هر دو آیه در یک سوره هستند، به دنبال «تقابل و تضاد» باشید (مثلاً مؤمن در برابر منافق، بهشت در برابر جهنم).\n"
        "۵. اگر عملگر گزینه (T5 - جابجایی + تقارن کامل) است: به دنبال «دیالوگ متقاطع» باشید. معمولاً بذر یک پرسش صریح (مخصوصاً درباره زمان/قیامت) مطرح می‌کند و مقصد با یک رویداد کیهانی پاسخ می‌دهد.\n"
        "۶. اگر عملگر گزینه (T6 - جابجایی + تقارن فقط سوره) است: به دنبال واژگان «اعتراف» (قالوا، یا ویلنا، سبحانک) و به تصویر کشیدن یک دادگاه الهی باشید.\n"
        "۷. اگر عملگر گزینه (T7 - جابجایی + تقارن فقط آیه) است: به دنبال «تمثیل‌های موازی» (مثل نور، شجره) یا موضوع تسبیح کائنات و پرندگان باشید.\n\n"
        "هفت مقصد بالقوه (محاسبه شده توسط قطب‌نما):\n"
    )
    body = ''
    if not preds:
        body = 'اطلاعات مقصدها در دسترس نیست.\n'
    else:
        for p in preds:
            fb = ' [با گردش ساعتی]' if p.get('is_fallback') else ''
            body += (
                '\nگزینه ' + str(p.get('rank')) + ' (عملگر ' + str(p.get('op_code')) + ')' + fb +
                ' ← سوره ' + str(p.get('s')) + ' آیه ' + str(p.get('a')) + '\n' +
                'متن عربی: ' + str(p.get('arb', '')) + '\n' +
                'ترجمه: ' + str(p.get('pers', '')) + '\n'
            )
    footer = (
        "\nلطفاً خروجی خود را با ساختار HTML (با تگ‌های <b>، <ul>، <br> و استایل راست‌چین RTL) به این شکل ارائه دهید:\n"
        "۱. تحلیل کوتاه کالبد و مفهوم بذر.\n"
        "۲. بررسی انتقادی هر ۷ گزینه: هر گزینه را دقیقاً با قانون اختصاصی همان T در ماتریس رفتاری بسنجید. گزینه‌هایی که از قانون خودشان پیروی نمی‌کنند را با ذکر دلیل رد کنید.\n"
        "۳. معرفی قوی‌ترین مقصد: کدام گزینه دقیقاً در قالب قانونِ عملگر خود قفل می‌شود؟ دلیل قطعی خود را بنویسید (ریشه‌های مشترک را پررنگ کنید).\n"
        "۴. تعیین نوع رابطه نهایی: (از بین: تقابل کامل، مکمل و بسط‌دهنده، گفت و گو، علت و معلول، پرسش و پاسخ).\n"
    )
    return header + body + footer
