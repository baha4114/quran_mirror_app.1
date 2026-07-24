# -*- coding: utf-8 -*-
"""
هستهٔ منطقی «قطب‌نمای قرآنی – پردازش آینه‌ای»
این ماژول کاملاً مستقل از رابط کاربری است و همهٔ الگوریتم‌ها را
مو‌به‌مو از نسخهٔ دسکتاپ (final_quran.py) منتقل کرده است.
بدون هیچ وابستگی سنگینی (بدون PyQt / hazm / qalsadi) تا روی اندروید هم اجرا شود.
"""
import os
import csv
import math
import json
import re

# ------------------------------------------------------------------
# توابع پایه
# ------------------------------------------------------------------
_PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'
_ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩'
_ENGLISH_DIGITS = '0123456789'


def conv(t):
    """تبدیل ارقام فارسی/عربی به انگلیسی (مطابق ModernQuranApp.conv)."""
    t = str(t)
    for p, e in zip(_PERSIAN_DIGITS, _ENGLISH_DIGITS):
        t = t.replace(p, e)
    for a, e in zip(_ARABIC_DIGITS, _ENGLISH_DIGITS):
        t = t.replace(a, e)
    return t


def mirror(n):
    """آینهٔ عدد: رقم‌ها را برعکس می‌کند (با pad دو رقمی)."""
    return int(str(n).zfill(2)[::-1])


# حذف اعراب/تشکیل عربی برای پردازش سبک متن (جایگزین lemmatizer روی موبایل)
_HARAKAT = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670\u0640]')


def strip_harakat(text):
    return _HARAKAT.sub('', text or '')


_ALEF_RE = re.compile(r'[\u0625\u0623\u0671\u0622]')
_YA_RE = re.compile(r'[\u064A\u0649]')
_WS_RE = re.compile(r'\s+')


def normalize_text(text):
    """نرمال‌سازی متن عربی برای جستجو: حذف اعراب و یکسان‌سازی الف/یاء/کاف/تاء مربوطه.
    نیازی به اعراب‌گذاری دقیق ورودی نیست."""
    if not text:
        return ''
    t = strip_harakat(str(text))
    t = _ALEF_RE.sub('\u0627', t)      # أ إ آ ٱ → ا
    t = _YA_RE.sub('\u06CC', t)        # ي ى → ی
    t = t.replace('\u0643', '\u06A9')  # ك → ک
    t = t.replace('\u0629', '\u0647')  # ة → ه
    t = t.replace('\u200c', ' ')       # نیم‌فاصله → فاصله
    t = _WS_RE.sub(' ', t).strip()
    return t


STOPWORDS = {
    "في", "من", "على", "إلى", "عن", "بم", "بما", "الذي", "الذين", "التي",
    "هو", "هي", "هم", "هن", "ما", "لا", "لم", "لن", "إن", "أن", "كان",
    "كانوا", "الله", "له", "لهم", "إليهم", "عليكم", "لكم", "و", "ف", "ثم",
    "أو", "قد", "يا", "ايها", "هل", "بل", "إذ", "إذا",
}


# ------------------------------------------------------------------
# پایگاه دادهٔ آیات
# ------------------------------------------------------------------
class QuranData:
    def __init__(self, csv_path):
        self.db = {}        # {(sura, ayah): {'arb':.., 'pers':..}}
        self.max_a = {}     # {sura: max_ayah}
        self.csv_path = csv_path
        self.load()

    def load(self):
        """خواندن datakavosh.csv (مطابق load_db در نسخهٔ دسکتاپ)."""
        with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
            first = f.readline()
            f.seek(0)
            if '\x1b' in first:
                delim = '\x1b'
            elif ';' in first:
                delim = ';'
            elif '\t' in first:
                delim = '\t'
            else:
                delim = ','
            r = csv.reader(f, delimiter=delim)
            h = [str(c).strip().upper() for c in next(r)]
            si, ai, ar, cv = (h.index('SID'), h.index('ACODE'),
                              h.index('ARBNAME'), h.index('CVALUE'))
            for row in r:
                if not row or len(row) <= max(si, ai, ar, cv):
                    continue
                raw_s, raw_a = str(row[si]).strip(), str(row[ai]).strip()
                if not raw_s or not raw_a:
                    continue
                s, a = int(conv(raw_s)), int(conv(raw_a))
                self.db[(s, a)] = {'arb': row[ar], 'pers': row[cv]}
                self.max_a[s] = max(self.max_a.get(s, 0), a)

    # --------- گردش ساعتی ---------
    def apply_circular(self, s_raw, a_raw):
        s, a = s_raw, a_raw
        orig_s, orig_a = s_raw, a_raw
        msg = ""
        if s > 114:
            s = ((s - 1) % 114) + 1
            msg += f"سوره {orig_s} خارج محدوده ← {s}. "
        max_a_val = self.max_a.get(s, 0)
        if max_a_val == 0:
            return None, None, True, "سوره نامعتبر"
        if a > max_a_val:
            a = ((a - 1) % max_a_val) + 1
            msg += f"آیه {orig_a} خارج محدوده سوره {s} (max={max_a_val}) ← {a}."
        is_fallback = (orig_s != s) or (orig_a != a)
        if not msg:
            msg = "مختصات دقیقاً در قرآن موجود است"
        return s, a, is_fallback, msg

    def find_seed(self, s, a):
        """یافتن نزدیک‌ترین آیهٔ معتبر با گردش ساعتی (مطابق run_prediction)."""
        final_s, final_a = s, a
        loop = 0
        while (final_s, final_a) not in self.db:
            loop += 1
            if loop > 6500:
                return None
            final_a += 1
            if final_a > self.max_a.get(final_s, 999):
                final_a = 1
                final_s += 1
            if final_s > 114:
                final_s = 1
        return final_s, final_a

    def get(self, s, a):
        return self.db.get((s, a))

    # --------- جستجوی آیه از روی متن ---------
    def _ensure_norm_index(self):
        """ساخت نمایهٔ نرمال‌شدهٔ متن آیات و ترجمه (یک‌بار، تنبل)."""
        if getattr(self, '_norm_ready', False):
            return
        self._norm_pairs = []
        self._norm_exact = {}
        self._norm_arb = {}
        self._norm_pers = {}
        for (s, a), v in self.db.items():
            nv = normalize_text(v.get('arb', ''))
            npr = normalize_text(v.get('pers', ''))
            self._norm_arb[(s, a)] = nv
            self._norm_pers[(s, a)] = npr
            self._norm_pairs.append(((s, a), nv))
            if nv and nv not in self._norm_exact:
                self._norm_exact[nv] = (s, a)
        self._norm_ready = True

    def find_by_text(self, query):
        """یافتن (سوره، آیه) از روی متن آیه یا ترجمه، بدون نیاز به اعراب دقیق.
        اولویت: تطبیق کامل ← داخل متن عربی ← داخل ترجمه ← یک آیه داخل ورودی طولانی."""
        q = normalize_text(query)
        if len(q) < 3:
            return None
        self._ensure_norm_index()
        if q in self._norm_exact:
            return self._norm_exact[q]
        for sa, nv in self._norm_pairs:
            if nv and q in nv:
                return sa
        for sa, npr in self._norm_pers.items():
            if npr and q in npr:
                return sa
        for sa, nv in self._norm_pairs:
            if nv and nv in q:
                return sa
        return None

    def search_by_ayah_number(self, n, limit=None):
        """همهٔ آیاتی که «شمارهٔ آیه»‌شان برابر n است، در سراسر سوره‌ها.
        مثال: n=2 ⇒ آیهٔ ۲ همهٔ سوره‌هایی که در دیتاکاوش موجودند.
        خروجی هم‌شکل search_all است: [{'s','a','arb','pers','score'}] مرتب‌شده بر اساس شمارهٔ سوره."""
        out = []
        for (s, a), v in self.db.items():
            if a == n:
                out.append({'s': s, 'a': a,
                            'arb': v.get('arb', ''), 'pers': v.get('pers', ''),
                            'score': 0})
        out.sort(key=lambda r: r['s'])
        return out[:limit] if limit else out

    def search_all(self, query, limit=300):
        """فهرست همهٔ آیاتِ حاویِ عبارت (در متن عربی یا ترجمهٔ فارسی)،
        مرتب‌شده از بیشترین تطابق تا کمترین. خروجی: [{'s','a','arb','pers','score'}].
        اگر ورودی فقط عدد باشد، جستجوی عددی روی «شمارهٔ آیه» انجام می‌شود."""
        # --- جستجوی عددی: ورودیِ صرفاً رقمی (فارسی/عربی/انگلیسی) ---
        raw_num = conv(str(query if query is not None else '')).strip()
        if raw_num and raw_num.isdigit():
            return self.search_by_ayah_number(int(raw_num), limit=limit)
        q = normalize_text(query)
        if len(q) < 2:
            return []
        self._ensure_norm_index()
        qwords = [w for w in q.split(' ') if w]
        scored = []
        for (s, a), v in self.db.items():
            na = self._norm_arb.get((s, a), '')
            npr = self._norm_pers.get((s, a), '')
            score = 0
            if q and (q == na or q == npr):
                score = 100000
            elif q and (q in na or q in npr):
                shorter = na if (q in na) else npr
                score = 50000 + max(0, 400 - len(shorter))
            else:
                wc = 0
                for w in qwords:
                    if w and (w in na or w in npr):
                        wc += 1
                if wc == 0:
                    continue
                score = wc * 100
                if wc == len(qwords):
                    score += 500
            scored.append((score, s, a))
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        out = []
        for score, s, a in scored[:limit]:
            v = self.db.get((s, a), {})
            out.append({'s': s, 'a': a,
                        'arb': v.get('arb', ''), 'pers': v.get('pers', ''),
                        'score': score})
        return out


# ------------------------------------------------------------------
# تحلیل زبانی سبک (جایگزین lemmatizer برای اجرا روی موبایل)
# ------------------------------------------------------------------
def get_dynamic_roots(text):
    words = set()
    for word in (text or '').split():
        clean = ''.join(c for c in strip_harakat(word) if c.isalpha())
        if len(clean) <= 2 or clean in STOPWORDS:
            continue
        words.add(clean)
    return words


def shared_dynamic_root(text1, text2):
    r1 = get_dynamic_roots(text1)
    r2 = get_dynamic_roots(text2)
    common = r1.intersection(r2)
    return len(common), common


def exact_opening_match(text1, text2):
    w1 = (text1 or '').split()[:3]
    w2 = (text2 or '').split()[:3]
    if len(w1) >= 2 and len(w2) >= 2:
        if w1[0] == w2[0] and w1[1] == w2[1]:
            return True
    return False


def is_qiyamah_question_and_answer(text_seed, text_target):
    q_words = ["مَتَى", "أَيَّانَ", "يَسْأَلُونَكَ", "يَسْأَلُ"]
    has_q = any(q in text_seed for q in q_words)
    t = (text_target or '').strip()
    has_ans = t.startswith("إِذَا") or t.startswith("يَوْمَ")
    return has_q and has_ans


def has_command(text):
    cmds = ["قُلْ", "افْعَلْ", "اتَّبِعُوا", "سِيحُوا", "أَقِمْ", "أْمُرْ", "انْهَ", "ادْعُوا", "يَا أَيُّهَا"]
    return any(c in (text or '') for c in cmds)


# ------------------------------------------------------------------
# هفت عملگر آینه‌ای (مشترک بین همهٔ الگوریتم‌ها)
# ------------------------------------------------------------------
def seven_operators(S, A):
    """(نام، (s_raw, a_raw)) برای هر هفت عملگر."""
    return [
        ("T1: جابجایی خالص", (A, S)),
        ("T2: تقارن درجا کامل", (mirror(S), mirror(A))),
        ("T3: تقارن درجا فقط سوره", (mirror(S), A)),
        ("T4: تقارن درجا فقط آیه", (S, mirror(A))),
        ("T5: جابجایی + تقارن کامل", (mirror(A), mirror(S))),
        ("T6: جابجایی + تقارن فقط سوره", (mirror(A), S)),
        ("T7: جابجایی + تقارن فقط آیه", (A, mirror(S))),
    ]


# پردازش ماتریس (نمای کارت‌ها) - مطابق ModernQuranApp.process
MATRIX_BEHAVIORS = [
    ("جابه‌جایی خالص بذر", lambda S, V: (V, S)),
    ("تقارن درجا کامل (آینه‌ی کامل)", lambda S, V: (mirror(S), mirror(V))),
    ("تقارن درجا فقط سوره", lambda S, V: (mirror(S), V)),
    ("تقارن درجا فقط آیه", lambda S, V: (S, mirror(V))),
    ("جابجایی + تقارن ضربدری کامل", lambda S, V: (mirror(V), mirror(S))),
    ("جابجایی + تقارن فقط سوره", lambda S, V: (mirror(V), S)),
    ("جابجایی + تقارن فقط آیه", lambda S, V: (V, mirror(S))),
]


def process_matrix(data, S, V):
    """خروجی: لیست دیکشنری کارت‌ها شامل بذر و هفت مقصد."""
    cards = []
    seed = data.get(S, V)
    cards.append({
        'kind': 'seed', 'mode': 'بذر ساختاری',
        's': S, 'a': V,
        'arb': seed['arb'], 'pers': seed['pers'],
        'is_fallback': False, 'reason': ''
    })
    for bname, func in MATRIX_BEHAVIORS:
        s_t, a_t = func(S, V)
        if data.get(s_t, a_t) is not None:
            d = data.get(s_t, a_t)
            cards.append({'kind': 'target', 'mode': bname, 's': s_t, 'a': a_t,
                          'arb': d['arb'], 'pers': d['pers'],
                          'is_fallback': False, 'reason': ''})
        else:
            orig_s, orig_a = s_t, a_t
            reason = ""
            if s_t > 114:
                s_t = ((s_t - 1) % 114) + 1
                reason += f"سوره {orig_s} پس از گردش ساعتی ← {s_t}. "
            max_a_new = data.max_a.get(s_t, 0)
            if max_a_new == 0:
                continue
            if a_t > max_a_new:
                old_a = a_t
                a_t = ((a_t - 1) % max_a_new) + 1
                reason += f"آیه {old_a} پس از گردش ساعتی ← {a_t}."
            if not reason:
                reason = "پس از گردش ساعتی"
            d = data.get(s_t, a_t)
            if d is not None:
                cards.append({'kind': 'target', 'mode': bname, 's': s_t, 'a': a_t,
                              'arb': d['arb'], 'pers': d['pers'],
                              'is_fallback': True, 'reason': reason})
    return cards


# ------------------------------------------------------------------
# الگوریتم پیش‌بینی معنایی (predict_mirror)
# ------------------------------------------------------------------
def predict_mirror(data, S, A, seed_text="", model=None):
    all_results = []
    for name, (s_raw, a_raw) in seven_operators(S, A):
        s, a, is_fallback, msg = data.apply_circular(s_raw, a_raw)
        if s is None:
            continue
        raw_score = 0
        is_odd = (A % 2 == 1)
        swap_ops = ["T1: جابجایی خالص", "T5: جابجایی + تقارن کامل",
                    "T6: جابجایی + تقارن فقط سوره", "T7: جابجایی + تقارن فقط آیه"]
        if (is_odd and name not in swap_ops) or (not is_odd and name in swap_ops):
            raw_score += 5
        target = data.get(s, a) or {}
        target_arb = target.get('arb', '')
        common_count = 0
        if seed_text and target_arb:
            common_count, _ = shared_dynamic_root(seed_text, target_arb)
            if common_count > 0:
                raw_score += common_count * 25
            if exact_opening_match(seed_text, target_arb):
                raw_score += 40
                if "T2" in name or "T7" in name:
                    raw_score += 20
            if "T5" in name and is_qiyamah_question_and_answer(seed_text, target_arb):
                raw_score += 50
            if "T1" in name and has_command(seed_text) and common_count > 0:
                raw_score += 30
            if "T4" in name and S == s:
                raw_score += 20
            confession = ["قَالُوا", "يَا وَيْلَنَا", "ظَالِمِينَ", "سُبْحَانَكَ"]
            if "T6" in name and any(cw in seed_text for cw in confession):
                raw_score += 30
        if is_fallback:
            if common_count > 0:
                raw_score -= 5
            else:
                raw_score -= 15
        if model is not None:
            try:
                _lens = numeric_lenses(data, S, A, s, a, is_fallback)
                raw_score += model.boost(name, seed_text, target_arb, _lens) * 60.0
            except Exception:
                pass
        display_score = min((raw_score / 150) * 100, 100)
        if display_score < 0:
            display_score = 0
        all_results.append((name, s, a, raw_score, display_score, is_fallback, msg))

    all_results.sort(key=lambda x: x[3], reverse=True)
    result = []
    for idx, (name, s, a, raw_score, display_score, is_fallback, msg) in enumerate(all_results):
        if idx < 3:
            status = f"رتبه {idx + 1} (نیاز به تحلیل دقیق انسانی)"
        elif display_score > 25:
            status = "محتمل"
        else:
            status = "ارتباط ضعیف"
        result.append((name, s, a, display_score, status, is_fallback, msg))
    return result


# ------------------------------------------------------------------
# الگوریتم پیش‌بینی عددی نسخهٔ ۶.۱ (predict_mirror_numeric)
# ------------------------------------------------------------------
def _hemisphere(s, a):
    s_odd = s % 2 == 1
    a_odd = a % 2 == 1
    if (s_odd and a_odd) or (not s_odd and not a_odd):
        return 'R'
    return 'L'


def predict_mirror_numeric(data, S, A, model=None):
    seed_hemi = _hemisphere(S, A)
    results = []
    for op_name, (s_raw, a_raw) in seven_operators(S, A):
        s, a, is_fallback, msg = data.apply_circular(s_raw, a_raw)
        if s is None:
            continue
        hemi_pass = (seed_hemi == _hemisphere(s, a))
        # به‌جای شرط‌های همیشه‌درستِ قبلی، از نگاه‌های عددی و مدلِ یادگیرنده استفاده می‌کنیم
        try:
            lenses = numeric_lenses(data, S, A, s, a, is_fallback)
        except Exception:
            lenses = {}
        boost = 0.0
        if model is not None:
            try:
                boost = model.boost(op_name, '', (data.get(s, a) or {}).get('arb', ''), lenses)
            except Exception:
                boost = 0.0
        tolerance = abs((115 - s) - a)
        results.append({
            'op_name': op_name, 's': s, 'a': a, 'is_fallback': is_fallback,
            'msg': msg, 'hemi_pass': hemi_pass, 'boost': boost, 'lenses': lenses,
            'tolerance': tolerance, 'is_direct': not is_fallback,
        })

    coord_groups = {}
    for res in results:
        if res['hemi_pass']:
            coord_groups.setdefault((res['s'], res['a']), []).append(res)

    final_candidates = []
    for (s, a), group in coord_groups.items():
        count = len(group)
        has_direct = any(not g['is_fallback'] for g in group)
        if count >= 2 and has_direct:
            priority = 1
            reason = "هم‌سرایی مستقیم (دو یا چند عملگر بدون گردش ساعتی)"
        elif count >= 2 and not has_direct:
            priority = 2
            reason = "هم‌سرایی گردشی (دو یا چند عملگر پس از گردش ساعتی)"
        elif count == 1:
            priority = 3
            reason = "تک‌خروجی با تأیید نیم‌کره"
        else:
            priority = 4
            reason = "سایر"
        best = max(group, key=lambda x: (x['boost'], -x['tolerance']))
        final_candidates.append({
            'op_name': best['op_name'], 's': s, 'a': a, 'priority': priority,
            'reason': reason, 'is_fallback': best['is_fallback'], 'msg': best['msg'],
            'tolerance': best['tolerance'], 'group_count': count,
            'boost': best['boost'], 'lenses': best.get('lenses', {}),
            'all_ops': [g['op_name'] for g in group],
        })

    final_candidates.sort(key=lambda x: (x['priority'], -x.get('boost', 0.0), x['tolerance']))
    output = []
    for idx, item in enumerate(final_candidates, 1):
        op_display = " + ".join(item['all_ops']) if item['group_count'] > 1 else item['op_name']
        detail = f"{item['reason']} (تلورانس: {item['tolerance']})"
        if item.get('boost', 0.0) > 0.02:
            detail += " · امتیاز یادگیری: %d٪" % int(round(item['boost'] * 100))
        if item['is_fallback']:
            detail += f" ⚠️ {item['msg']}"
        output.append((op_display, item['s'], item['a'], idx, detail, item['is_fallback'], item['msg']))
    return output




# ==================================================================
# نسخهٔ ۷ — لایهٔ «نگاه‌های عددی» و موتور یادگیری از کشفیات لابراتوار
# این بخش کاملاً افزودنی است و رفتار قبلی برنامه را تغییر نمی‌دهد؛
# تا وقتی تعداد کشفیات کم باشد، وزن یادگیری نزدیک صفر می‌ماند.
# ==================================================================

# سوره‌های دارای حروف مقطعه
MUQATTAAT_SURAHS = {
    2, 3, 7, 10, 11, 12, 13, 14, 15, 19, 20, 26, 27, 28, 29, 30, 31, 32,
    36, 38, 40, 41, 42, 43, 44, 45, 46, 50, 68,
}

# فهرست نگاه‌های عددی (کلید، عنوان فارسی)
LENS_DEFS = [
    ('p_S', 'زوج/فرد سورهٔ بذر'),
    ('p_A', 'زوج/فرد آیهٔ بذر'),
    ('p_s', 'زوج/فرد سورهٔ مقصد'),
    ('p_a', 'زوج/فرد آیهٔ مقصد'),
    ('p_match', 'تطابق زوج/فردی بذر و مقصد'),
    ('hemi', 'نیم‌کرهٔ بذر ← مقصد'),
    ('sum_seed', 'جمع سوره+آیهٔ بذر'),
    ('sum_tgt', 'جمع سوره+آیهٔ مقصد'),
    ('sum_match', 'برابری جمع بذر و مقصد'),
    ('dsum_seed', 'جمع ارقام بذر'),
    ('dsum_tgt', 'جمع ارقام مقصد'),
    ('droot_seed', 'ریشهٔ دیجیتال بذر'),
    ('droot_tgt', 'ریشهٔ دیجیتال مقصد'),
    ('droot_match', 'تطابق ریشهٔ دیجیتال'),
    ('step_abs', 'گام مطلق بذر ← مقصد'),
    ('to_end_book', 'گام تا پایان قرآن (از مقصد)'),
    ('to_end_surah', 'گام تا پایان سورهٔ مقصد'),
    ('pos_ratio', 'جایگاه نسبی مقصد در سوره'),
    ('tolerance', 'تلورانس |(۱۱۵−سوره)−آیه|'),
    ('coord_group', 'عضویت در گروه ۱۰۶ / ۱۱۴ / ۱۱۵'),
    ('mirror_const', 'ثابت آینه‌ای سوره (S+آینهٔ S)'),
    ('shift1000', 'ریشهٔ دیجیتال وزن (سوره×۱۰۰۰+آیه)'),
    ('mul19', 'بخش‌پذیری بر ۱۹'),
    ('muq', 'حروف مقطعه'),
    ('d_surah', 'فاصلهٔ سوره‌ها'),
    ('d_ayah', 'فاصلهٔ آیه‌ها'),
    ('route', 'مسیر رسیدن (مستقیم / گردش ساعتی)'),
]

LENS_TITLES = dict(LENS_DEFS)
# نگاه «مسیر» فقط گزارشی است و در امتیازدهی دخالت داده نمی‌شود
LENS_REPORT_ONLY = {'route'}


def digit_sum(n):
    return sum(int(c) for c in str(abs(int(n))))


def digital_root(n):
    n = abs(int(n))
    if n == 0:
        return 0
    r = n % 9
    return 9 if r == 0 else r


def _parity(n):
    return 'زوج' if int(n) % 2 == 0 else 'فرد'


def _bucket(v, edges):
    """دسته‌بندی یک عدد بر اساس مرزها؛ خروجی متنی برای شمارش آماری."""
    prev = None
    for e in edges:
        if v <= e:
            return ('≤%d' % e) if prev is None else ('%d..%d' % (prev + 1, e))
        prev = e
    return '>%d' % edges[-1]


def abs_offsets(data):
    """شمارهٔ مطلق آیه در کل قرآن (کش‌شده روی شیء داده)."""
    off = getattr(data, '_abs_offsets', None)
    if off:
        return off
    off = {}
    total = 0
    for s in range(1, 115):
        off[s] = total
        total += int(data.max_a.get(s, 0) or 0)
    off['__total__'] = total
    try:
        data._abs_offsets = off
    except Exception:
        pass
    return off


def abs_index(data, s, a):
    off = abs_offsets(data)
    return off.get(int(s), 0) + int(a)


def total_ayahs(data):
    return abs_offsets(data).get('__total__', 0)


def numeric_lenses(data, S, A, s, a, is_fallback=False):
    """همهٔ نگاه‌های عددی برای یک جفت بذر ← مقصد. خروجی: دیکشنری کلید ← مقدار متنی."""
    S, A, s, a = int(S), int(A), int(s), int(a)
    out = {}
    out['p_S'] = _parity(S)
    out['p_A'] = _parity(A)
    out['p_s'] = _parity(s)
    out['p_a'] = _parity(a)
    out['p_match'] = 'یکسان' if (S % 2, A % 2) == (s % 2, a % 2) else 'متفاوت'
    out['hemi'] = '%s←%s' % (_hemisphere(S, A), _hemisphere(s, a))
    sum_seed, sum_tgt = S + A, s + a
    edges = [10, 20, 40, 70, 110, 160, 250]
    out['sum_seed'] = _bucket(sum_seed, edges)
    out['sum_tgt'] = _bucket(sum_tgt, edges)
    out['sum_match'] = 'برابر' if sum_seed == sum_tgt else 'نابرابر'
    ds_seed = digit_sum(S) + digit_sum(A)
    ds_tgt = digit_sum(s) + digit_sum(a)
    out['dsum_seed'] = str(ds_seed)
    out['dsum_tgt'] = str(ds_tgt)
    out['droot_seed'] = str(digital_root(sum_seed))
    out['droot_tgt'] = str(digital_root(sum_tgt))
    out['droot_match'] = 'یکسان' if digital_root(sum_seed) == digital_root(sum_tgt) else 'متفاوت'
    try:
        i_seed = abs_index(data, S, A)
        i_tgt = abs_index(data, s, a)
        tot = total_ayahs(data) or 6236
    except Exception:
        i_seed, i_tgt, tot = 0, 0, 6236
    out['step_abs'] = _bucket(abs(i_tgt - i_seed), [50, 200, 600, 1500, 3000, 5000])
    out['to_end_book'] = _bucket(max(0, tot - i_tgt), [50, 200, 600, 1500, 3000, 5000])
    maxa = int(data.max_a.get(s, 0) or 0)
    out['to_end_surah'] = _bucket(max(0, maxa - a), [0, 3, 10, 30, 80, 200])
    if maxa > 0:
        r = float(a) / float(maxa)
        if r <= 0.2:
            out['pos_ratio'] = 'ابتدای سوره'
        elif r <= 0.4:
            out['pos_ratio'] = 'یک‌پنجم دوم'
        elif r <= 0.6:
            out['pos_ratio'] = 'میانهٔ سوره'
        elif r <= 0.8:
            out['pos_ratio'] = 'یک‌پنجم چهارم'
        else:
            out['pos_ratio'] = 'انتهای سوره'
    else:
        out['pos_ratio'] = 'نامشخص'
    out['tolerance'] = _bucket(abs((115 - s) - a), [0, 2, 5, 10, 20, 50])
    groups = []
    for label, val in (('بذر', sum_seed), ('مقصد', sum_tgt)):
        for g in (106, 114, 115):
            if val == g:
                groups.append('%s=%d' % (label, g))
    out['coord_group'] = ' ، '.join(groups) if groups else 'هیچ‌کدام'
    out['mirror_const'] = _bucket(S + mirror(S), [20, 40, 60, 90, 130, 200])
    out['shift1000'] = str(digital_root(s * 1000 + a))
    m19 = []
    if (S * 1000 + A) % 19 == 0:
        m19.append('بذر')
    if (s * 1000 + a) % 19 == 0:
        m19.append('مقصد')
    if (sum_seed + sum_tgt) % 19 == 0:
        m19.append('جمع کل')
    out['mul19'] = ' ، '.join(m19) if m19 else 'خیر'
    mq_seed = S in MUQATTAAT_SURAHS
    mq_tgt = s in MUQATTAAT_SURAHS
    if mq_seed and mq_tgt:
        out['muq'] = 'هر دو مقطعه'
    elif mq_seed:
        out['muq'] = 'فقط بذر'
    elif mq_tgt:
        out['muq'] = 'فقط مقصد'
    else:
        out['muq'] = 'هیچ‌کدام'
    out['d_surah'] = _bucket(abs(S - s), [0, 3, 10, 25, 50, 90])
    out['d_ayah'] = _bucket(abs(A - a), [0, 3, 10, 25, 60, 150])
    out['route'] = 'گردش ساعتی' if is_fallback else 'مستقیم'
    return out


# ------------------------------------------------------------------
# شناسایی عملگر و نوع پردازش از روی نام حالت
# ------------------------------------------------------------------
def op_code_of(mode_name):
    """کد عملگر (T1..T7) از روی نام حالت؛ در غیر این صورت OTHER."""
    m = str(mode_name or '')
    if 'خالص' in m:
        return 'T1'
    if 'ضربدری' in m:
        return 'T5'
    if 'جابجایی' in m and 'کامل' in m:
        return 'T5'
    if 'تقارن درجا کامل' in m:
        return 'T2'
    if 'جابجایی' in m and 'فقط سوره' in m:
        return 'T6'
    if 'جابجایی' in m and 'فقط آیه' in m:
        return 'T7'
    if 'فقط سوره' in m:
        return 'T3'
    if 'فقط آیه' in m:
        return 'T4'
    return 'OTHER'


PROC_MIRROR = 'MIRROR'      # پردازش آینه‌ای (هفت عملگر)
PROC_ROTATION = 'ROT'       # پردازش گردش/دوران ارقام بذر
PROC_OTHER = 'OTHER'        # گروهی و سایر

PROC_TITLES = {
    PROC_MIRROR: 'پردازش آینه‌ای',
    PROC_ROTATION: 'گردش ارقام بذر',
    PROC_OTHER: 'گروهی و سایر',
}


def proc_mode_of(mode_name):
    """نوع پردازش یک کشف: آینه‌ای، گردش ارقام، یا سایر."""
    m = str(mode_name or '')
    if ('چرخش' in m) or ('ترکیب اولیه' in m) or ('دورانی' in m):
        return PROC_ROTATION
    if op_code_of(m) != 'OTHER':
        return PROC_MIRROR
    return PROC_OTHER


_ROT_NUM_RE = re.compile(r'\((\d+)\)')


def infer_route(data, S, A, s, a, mode_name):
    """آیا مقصد مستقیم به دست آمده یا با گردش ساعتی؟ (برای کشفیات قدیمی هم بازسازی می‌شود)
    خروجی: True یعنی گردش ساعتی."""
    try:
        S, A, s, a = int(S), int(A), int(s), int(a)
    except Exception:
        return False
    kind = proc_mode_of(mode_name)
    raws = []
    if kind == PROC_MIRROR:
        code = op_code_of(mode_name)
        for name, (rs, ra) in seven_operators(S, A):
            if name.startswith(code):
                raws.append((rs, ra))
    elif kind == PROC_ROTATION:
        m = _ROT_NUM_RE.search(str(mode_name or ''))
        if m:
            num = m.group(1)
            if len(num) >= 2:
                raws.append((int(num[:2]), int(num[2:]) if num[2:] else 1))
            else:
                raws.append((int(num), 1))
    if not raws:
        return False
    for rs, ra in raws:
        if (rs, ra) == (s, a):
            return False
        try:
            if data is not None and data.get(rs, ra) is not None:
                return False
        except Exception:
            pass
    return True


# ------------------------------------------------------------------
# استخراج جفت‌های بذر ← مقصد از رکوردهای لابراتوار
# ------------------------------------------------------------------
def iter_discovery_pairs(records, data=None):
    """هر کشف (تکی، جفتی یا گروهی) را به جفت‌های ساده تبدیل می‌کند.
    label: +1 قطعی، -1 بن‌بست، 0 تردیدی/نامشخص."""
    for rec in (records or []):
        if not isinstance(rec, dict):
            continue
        S = rec.get('seed_s')
        A = rec.get('seed_a')
        if S is None or A is None:
            continue
        seed_arb = rec.get('seed_arb', '') or ''
        note = rec.get('note', '') or ''
        rel = rec.get('relation_type', '') or ''
        date = rec.get('date', '') or ''
        source = rec.get('source', '') or 'lab'
        base_label = -1 if rec.get('is_dead_end') else (0 if rec.get('is_doubtful') else 1)
        targets = rec.get('all_targets')
        if isinstance(targets, list) and targets:
            for t in targets:
                if not isinstance(t, dict):
                    continue
                mode_name = t.get('operator', '') or rec.get('mode', '')
                label = base_label
                verdict = t.get('verdict')
                if verdict == 'تأیید':
                    label = 1
                elif verdict == 'بن‌بست':
                    label = -1
                elif verdict == 'نامشخص':
                    label = 0
                if t.get('is_dead_end'):
                    label = -1
                yield _pair_row(data, S, A, t.get('s'), t.get('a'), mode_name,
                                seed_arb, t.get('arb', '') or '',
                                t.get('note', '') or note, rel, label, date, source, rec)
        else:
            yield _pair_row(data, S, A, rec.get('target_s'), rec.get('target_a'),
                            rec.get('mode', ''), seed_arb, rec.get('target_arb', '') or '',
                            note, rel, base_label, date, source, rec)


def _pair_row(data, S, A, s, a, mode_name, seed_arb, target_arb,
              note, rel, label, date, source, rec):
    try:
        S, A, s, a = int(S), int(A), int(s), int(a)
    except Exception:
        S = A = s = a = 0
    is_fb = rec.get('is_fallback')
    if is_fb is None:
        is_fb = infer_route(data, S, A, s, a, mode_name) if (data is not None and s) else False
    lenses = {}
    if data is not None and s and a:
        try:
            lenses = numeric_lenses(data, S, A, s, a, bool(is_fb))
        except Exception:
            lenses = {}
    return {
        'op': op_code_of(mode_name),
        'proc': proc_mode_of(mode_name),
        'mode': mode_name,
        'S': S, 'A': A, 's': s, 'a': a,
        'seed_arb': seed_arb, 'target_arb': target_arb,
        'note': note, 'relation_type': rel,
        'label': label, 'date': date, 'source': source,
        'is_fallback': bool(is_fb),
        'lenses': lenses,
    }


# ------------------------------------------------------------------
# موتور یادگیری: از کشفیات قطعی و بن‌بستی یاد می‌گیرد
# ------------------------------------------------------------------
class LearnedModel:
    """مدل سبک و قابل اجرا روی موبایل:
    ۱) برای هر عملگر، رفتار هر «نگاه عددی» را در کشفیات قطعی و بن‌بستی می‌شمارد.
    ۲) از تحلیل‌های نوشته‌شده و متن آیات، «فضای معنایی» هر عملگر را می‌سازد.
    ۳) خروجی نهایی با ضریب اطمینان n/(n+K) با الگوریتم قبلی ترکیب می‌شود،
       تا وقتی داده کم است رفتار برنامه دقیقاً مثل قبل بماند.
    """

    K_CONF = 20          # ضریب احتیاط: با ۲۰ نمونه، وزن یادگیری ۵۰٪ می‌شود
    BLIND_WEIGHT = 2.0   # داده‌های آزمون کور ارزش بیشتری دارند

    def __init__(self):
        self.pos = {}        # op -> lens -> value -> وزن
        self.neg = {}
        self.n_pos = {}
        self.n_neg = {}
        self.kw_pos = {}     # op -> واژه -> وزن (فضای معنایی مثبت)
        self.kw_neg = {}
        self.note_kw = {}    # op -> واژه -> وزن (از تحلیل‌های نوشته‌شده)
        self.seed_kw = {}    # op -> واژه -> وزن (فضای آیهٔ بذر)
        self.rel_counts = {}  # op -> نوع ارتباط -> شمار
        self.pairs = 0
        self.pos_total = 0
        self.neg_total = 0
        self.doubt_total = 0

    # ---------- ساخت ----------
    @staticmethod
    def _bump(store, key, sub, w=1.0):
        d = store.setdefault(key, {})
        d[sub] = d.get(sub, 0.0) + w

    def add_row(self, row):
        label = row.get('label', 0)
        op = row.get('op', 'OTHER')
        w = self.BLIND_WEIGHT if row.get('source') == 'blind' else 1.0
        self.pairs += 1
        if label == 0:
            self.doubt_total += 1
            return
        lenses = row.get('lenses') or {}
        if label > 0:
            self.pos_total += 1
            self.n_pos[op] = self.n_pos.get(op, 0.0) + w
            store, kw = self.pos, self.kw_pos
        else:
            self.neg_total += 1
            self.n_neg[op] = self.n_neg.get(op, 0.0) + w
            store, kw = self.neg, self.kw_neg
        table = store.setdefault(op, {})
        for k, v in lenses.items():
            if k in LENS_REPORT_ONLY:
                continue
            self._bump(table, k, v, w)
        # فضای معنایی
        words = get_dynamic_roots(normalize_text(row.get('target_arb', '')))
        for word in words:
            self._bump({'x': kw.setdefault(op, {})}, 'x', word, w) if False else None
        tgt = kw.setdefault(op, {})
        for word in words:
            tgt[word] = tgt.get(word, 0.0) + w
        if label > 0:
            sd = self.seed_kw.setdefault(op, {})
            for word in get_dynamic_roots(normalize_text(row.get('seed_arb', ''))):
                sd[word] = sd.get(word, 0.0) + w
            nk = self.note_kw.setdefault(op, {})
            for word in get_dynamic_roots(normalize_text(row.get('note', ''))):
                nk[word] = nk.get(word, 0.0) + w
            rel = (row.get('relation_type') or '').strip()
            if rel and rel != 'نامشخص':
                rc = self.rel_counts.setdefault(op, {})
                rc[rel] = rc.get(rel, 0) + 1

    # ---------- اطمینان ----------
    def confidence(self, op=None):
        n_all = sum(self.n_pos.values()) + sum(self.n_neg.values())
        if op is None:
            n = n_all
        else:
            n = self.n_pos.get(op, 0.0) + self.n_neg.get(op, 0.0) + 0.25 * n_all
        return n / (n + float(self.K_CONF)) if n > 0 else 0.0

    # ---------- امتیاز نگاه‌های عددی ----------
    def lens_score(self, op, lenses):
        """نسبت درست‌نمایی لگاریتمی (بیز ساده با هموارسازی) در بازهٔ تقریبی -۱ تا +۱."""
        if not lenses:
            return 0.0
        p_tab = self.pos.get(op, {})
        n_tab = self.neg.get(op, {})
        if not p_tab and not n_tab:
            return 0.0
        P = self.n_pos.get(op, 0.0)
        N = self.n_neg.get(op, 0.0)
        total = 0.0
        used = 0
        for k, v in lenses.items():
            if k in LENS_REPORT_ONLY:
                continue
            pc = p_tab.get(k, {}).get(v, 0.0)
            nc = n_tab.get(k, {}).get(v, 0.0)
            if pc == 0.0 and nc == 0.0:
                continue
            pr = (pc + 1.0) / (P + 2.0)
            nr = (nc + 1.0) / (N + 2.0)
            try:
                total += math.log(pr / nr)
            except Exception:
                continue
            used += 1
        if not used:
            return 0.0
        avg = total / float(used)
        return max(-1.0, min(1.0, avg / 1.2))

    # ---------- امتیاز فضای معنایی ----------
    @staticmethod
    def _overlap(profile, words):
        if not profile or not words:
            return 0.0
        top = sorted(profile.items(), key=lambda x: -x[1])[:60]
        if not top:
            return 0.0
        mx = top[0][1] or 1.0
        score = 0.0
        for word, c in top:
            if word in words:
                score += c / mx
        return min(1.0, score / 3.0)

    def semantic_score(self, op, seed_text, target_text):
        w_t = get_dynamic_roots(normalize_text(target_text or ''))
        w_s = get_dynamic_roots(normalize_text(seed_text or ''))
        pos = self._overlap(self.kw_pos.get(op, {}), w_t)
        neg = self._overlap(self.kw_neg.get(op, {}), w_t)
        notes = self._overlap(self.note_kw.get(op, {}), w_t)
        seed_fit = self._overlap(self.seed_kw.get(op, {}), w_s)
        val = 0.55 * pos + 0.25 * notes + 0.20 * seed_fit - 0.5 * neg
        return max(-1.0, min(1.0, val))

    # ---------- خروجی نهایی ----------
    def boost(self, op_name, seed_text='', target_text='', lenses=None):
        op = op_code_of(op_name) if not str(op_name or '').startswith('T') else str(op_name)[:2]
        conf = self.confidence(op)
        if conf <= 0.0:
            return 0.0
        num = self.lens_score(op, lenses or {})
        sem = self.semantic_score(op, seed_text, target_text) if (seed_text or target_text) else 0.0
        return conf * (0.6 * num + 0.4 * sem)

    # ---------- گزارش‌ها (برای داشبورد) ----------
    def top_lenses(self, op, k=6):
        """قوی‌ترین نگاه‌های تفکیک‌کنندهٔ قطعی از بن‌بست برای یک عملگر."""
        p_tab = self.pos.get(op, {})
        n_tab = self.neg.get(op, {})
        P = self.n_pos.get(op, 0.0)
        N = self.n_neg.get(op, 0.0)
        rows = []
        for key, _title in LENS_DEFS:
            if key in LENS_REPORT_ONLY:
                continue
            vals = set(list(p_tab.get(key, {}).keys()) + list(n_tab.get(key, {}).keys()))
            best = None
            for v in vals:
                pc = p_tab.get(key, {}).get(v, 0.0)
                nc = n_tab.get(key, {}).get(v, 0.0)
                if pc + nc < 2:
                    continue
                pr = (pc + 1.0) / (P + 2.0)
                nr = (nc + 1.0) / (N + 2.0)
                try:
                    lr = math.log(pr / nr)
                except Exception:
                    continue
                if best is None or abs(lr) > abs(best[1]):
                    best = (v, lr, pc, nc)
            if best:
                rows.append({'lens': key, 'title': LENS_TITLES.get(key, key),
                             'value': best[0], 'power': best[1],
                             'pos': best[2], 'neg': best[3]})
        rows.sort(key=lambda r: -abs(r['power']))
        return rows[:k]

    def top_keywords(self, op, k=10):
        prof = {}
        for src, w in ((self.kw_pos.get(op, {}), 1.0), (self.note_kw.get(op, {}), 1.2)):
            for word, c in src.items():
                prof[word] = prof.get(word, 0.0) + c * w
        neg = self.kw_neg.get(op, {})
        for word in list(prof.keys()):
            prof[word] -= 0.7 * neg.get(word, 0.0)
        rows = [(w, c) for w, c in prof.items() if c > 0]
        rows.sort(key=lambda x: -x[1])
        return rows[:k]

    def top_relations(self, op, k=3):
        rows = sorted(self.rel_counts.get(op, {}).items(), key=lambda x: -x[1])
        return rows[:k]


def learn_from_discoveries(records, data=None):
    """ساخت مدل از روی کشفیات لابراتوار. همیشه یک مدل معتبر برمی‌گرداند."""
    model = LearnedModel()
    try:
        for row in iter_discovery_pairs(records, data):
            model.add_row(row)
    except Exception:
        pass
    return model


def dataset_rows(records, data=None):
    """ردیف‌های تخت برای خروجی CSV دیتاست (هر جفت بذر ← مقصد یک ردیف)."""
    return list(iter_discovery_pairs(records, data))


def stats_summary(records, data=None):
    """آمار کلی برای داشبورد پژوهش: تفکیک نوع پردازش، مسیر، و وضعیت."""
    rows = dataset_rows(records, data)
    out = {
        'pairs': len(rows), 'pos': 0, 'neg': 0, 'doubt': 0,
        'by_proc': {}, 'by_route': {'مستقیم': 0, 'گردش ساعتی': 0},
        'by_op': {},
    }
    for r in rows:
        lab = r['label']
        if lab > 0:
            out['pos'] += 1
        elif lab < 0:
            out['neg'] += 1
        else:
            out['doubt'] += 1
        p = out['by_proc'].setdefault(r['proc'], {'n': 0, 'pos': 0, 'neg': 0, 'doubt': 0})
        p['n'] += 1
        p['pos' if lab > 0 else ('neg' if lab < 0 else 'doubt')] += 1
        out['by_route']['گردش ساعتی' if r['is_fallback'] else 'مستقیم'] += 1
        o = out['by_op'].setdefault(r['op'], {'n': 0, 'pos': 0, 'neg': 0, 'doubt': 0, 'fb': 0})
        o['n'] += 1
        o['pos' if lab > 0 else ('neg' if lab < 0 else 'doubt')] += 1
        if r['is_fallback']:
            o['fb'] += 1
    return out
