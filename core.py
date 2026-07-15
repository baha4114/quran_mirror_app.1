# -*- coding: utf-8 -*-
"""
هستهٔ منطقی «قطب‌نمای قرآنی – پردازش آینه‌ای»
این ماژول کاملاً مستقل از رابط کاربری است و همهٔ الگوریتم‌ها را
مو‌به‌مو از نسخهٔ دسکتاپ (final_quran.py) منتقل کرده است.
بدون هیچ وابستگی سنگینی (بدون PyQt / hazm / qalsadi) تا روی اندروید هم اجرا شود.
"""
import os
import csv
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

    def search_all(self, query, limit=300):
        """فهرست همهٔ آیاتِ حاویِ عبارت (در متن عربی یا ترجمهٔ فارسی)،
        مرتب‌شده از بیشترین تطابق تا کمترین. خروجی: [{'s','a','arb','pers','score'}]."""
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
def predict_mirror(data, S, A, seed_text=""):
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


def predict_mirror_numeric(data, S, A):
    seed_hemi = _hemisphere(S, A)
    results = []
    for op_name, (s_raw, a_raw) in seven_operators(S, A):
        s, a, is_fallback, msg = data.apply_circular(s_raw, a_raw)
        if s is None:
            continue
        hemi_pass = (seed_hemi == _hemisphere(s, a))
        fingerprint_pass = False
        if op_name.startswith("T1"):
            if (S + A == s + a) and (abs(S - A) == abs(s - a)):
                fingerprint_pass = True
        elif op_name.startswith("T2"):
            if (S + mirror(S) == s + mirror(s)) and (A + mirror(A) == a + mirror(a)):
                fingerprint_pass = True
        elif op_name.startswith("T3"):
            if A == a:
                fingerprint_pass = True
        elif op_name.startswith("T4"):
            if S == s:
                fingerprint_pass = True
        elif op_name.startswith("T5"):
            if abs((S + mirror(S)) - (a + mirror(a))) == abs((A + mirror(A)) - (s + mirror(s))):
                fingerprint_pass = True
        elif op_name.startswith("T6"):
            if S == a:
                fingerprint_pass = True
        elif op_name.startswith("T7"):
            if A == s:
                fingerprint_pass = True
        tolerance = abs((115 - s) - a)
        results.append({
            'op_name': op_name, 's': s, 'a': a, 'is_fallback': is_fallback,
            'msg': msg, 'hemi_pass': hemi_pass, 'fingerprint_pass': fingerprint_pass,
            'tolerance': tolerance, 'is_direct': not is_fallback,
        })

    coord_groups = {}
    for res in results:
        if res['hemi_pass'] and res['fingerprint_pass']:
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
            reason = "تک‌خروجی با تأیید نیم‌کره و اثر انگشت"
        else:
            priority = 4
            reason = "سایر"
        best = min(group, key=lambda x: x['tolerance'])
        final_candidates.append({
            'op_name': best['op_name'], 's': s, 'a': a, 'priority': priority,
            'reason': reason, 'is_fallback': best['is_fallback'], 'msg': best['msg'],
            'tolerance': best['tolerance'], 'group_count': count,
            'all_ops': [g['op_name'] for g in group],
        })

    final_candidates.sort(key=lambda x: (x['priority'], x['tolerance']))
    output = []
    for idx, item in enumerate(final_candidates, 1):
        op_display = " + ".join(item['all_ops']) if item['group_count'] > 1 else item['op_name']
        detail = f"{item['reason']} (تلورانس: {item['tolerance']})"
        if item['is_fallback']:
            detail += f" ⚠️ {item['msg']}"
        output.append((op_display, item['s'], item['a'], idx, detail, item['is_fallback'], item['msg']))
    return output
