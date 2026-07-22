# -*- coding: utf-8 -*-
"""
ai_manager.py — لایهٔ مستقلِ ارتباط با هوش مصنوعی (سازگار با OpenAI / NVIDIA NIM)
=================================================================================
تمامِ منطقِ شبکه اینجاست تا main.py شلوغ نشود.

- سازگارِ کامل با استانداردِ OpenAI (اندپوینت /chat/completions).
- پیش‌فرض به سرورهای رایگانِ انویدیا وصل می‌شود؛ فقط با تغییرِ base_url و model
  می‌توان به هر سرورِ سازگار با OpenAI وصل شد.
- همهٔ درخواست‌ها در یک ترد پس‌زمینه اجرا می‌شوند و نتیجه با Clock.schedule_once
  به ردهٔ رابط کاربری برگردانده می‌شود (UI هرگز فریز نمی‌شود).
- تنظیمات (کلید/آدرس/مدل) به‌صورتِ پویا و در لحظهٔ هر درخواست خوانده می‌شوند.

چرا urllib به‌جای requests؟
  urllib داخلِ خودِ پایتون است؛ پس هیچ وابستگیِ اضافه‌ای به buildozer تحمیل نمی‌کند
  (نه certifi، نه urllib3) و APK سبک‌تر و بیلد پایدارتر می‌شود. کنترلِ کاملِ
  streaming (خواندنِ خط‌به‌خطِ SSE) هم با آن ساده است.
"""

import re
import ssl
import json
import threading
import urllib.request
import urllib.error

import qref

from kivy.clock import Clock

# ---- پیش‌فرض‌های انویدیا (build.nvidia.com) ----
DEFAULT_BASE_URL = "https://api.avalai.ir/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MODELS_URL = "https://avalai.ir"

# تأمین‌کنندهٔ تنظیمات؛ main.py با set_config_provider یک تابع می‌دهد که دیکشنری
# {api_key, base_url, model} برمی‌گرداند. این‌طور تنظیمات همیشه «زنده» خوانده می‌شود.
_config_provider = None


def set_config_provider(fn):
    global _config_provider
    _config_provider = fn


def default_settings():
    return {"api_key": "", "base_url": DEFAULT_BASE_URL, "model": DEFAULT_MODEL}


def get_config():
    """تنظیماتِ فعلی را (با اعمالِ پیش‌فرض‌ها) برمی‌گرداند."""
    cfg = default_settings()
    try:
        if _config_provider:
            user = _config_provider() or {}
            for k in ("api_key", "base_url", "model"):
                v = user.get(k)
                if isinstance(v, str):
                    v = v.strip()
                if v:
                    cfg[k] = v
    except Exception:
        pass
    cfg["base_url"] = (cfg["base_url"] or DEFAULT_BASE_URL).rstrip("/")
    return cfg


# ------------------------------------------------------------------
# کمک‌رسان‌ها
# ------------------------------------------------------------------
def _ui(cb, *args):
    """فراخوانیِ امنِ یک callback روی تردِ اصلیِ Kivy."""
    if cb is None:
        return
    Clock.schedule_once(lambda _dt: cb(*args), 0)


def _ssl_context(unverified=False):
    if unverified:
        return ssl._create_unverified_context()
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


def _friendly_error(status=None):
    """تبدیلِ خطاهای فنی به پیامِ فارسیِ قابل‌فهم برای کاربر."""
    if status == 401:
        return "کلید API نامعتبر است. کلید را در تنظیماتِ هوش مصنوعی بررسی کن."
    if status == 403:
        return "دسترسی به این مدل مجاز نیست یا کلید منقضی شده. کلید یا نامِ مدل را بررسی کن."
    if status == 429:
        return ("سقفِ مجازِ درخواست پر شد (Rate limit / پایانِ سهمیه). "
                "کمی صبر کن یا یک کلید API تازه در تنظیمات جایگزین کن.")
    if status in (400, 404, 422):
        return "درخواست نامعتبر بود. نامِ مدل را در تنظیمات بررسی کن (مثلِ deepseek-ai/deepseek-v4-pro)."
    if status and status >= 500:
        return "سرورِ هوش مصنوعی موقتاً در دسترس نیست. کمی بعد دوباره تلاش کن."
    return "اتصال به اینترنت برقرار نشد. شبکه را بررسی کن و دوباره تلاش کن."


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text):
    """حذفِ بخشِ استدلالِ داخلیِ مدل‌های reasoning (مثلِ DeepSeek) از خروجیِ نهایی."""
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()


class _ThinkFilter:
    """در جریانِ streaming، محتوای داخلِ <think>...</think> را زنده پنهان می‌کند."""
    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self.buf = ""
        self.in_think = False

    def feed(self, piece):
        self.buf += piece
        out = []
        while self.buf:
            if self.in_think:
                i = self.buf.find(self.CLOSE)
                if i == -1:
                    keep = len(self.CLOSE) - 1
                    if len(self.buf) > keep:
                        self.buf = self.buf[-keep:]
                    return "".join(out)
                self.buf = self.buf[i + len(self.CLOSE):]
                self.in_think = False
            else:
                i = self.buf.find(self.OPEN)
                if i == -1:
                    keep = len(self.OPEN) - 1
                    if len(self.buf) > keep:
                        out.append(self.buf[:-keep])
                        self.buf = self.buf[-keep:]
                    return "".join(out)
                out.append(self.buf[:i])
                self.buf = self.buf[i + len(self.OPEN):]
                self.in_think = True
        return "".join(out)

    def flush(self):
        r = "" if self.in_think else self.buf
        self.buf = ""
        return r


# ------------------------------------------------------------------
# هستهٔ درخواست
# ------------------------------------------------------------------
def chat(messages, on_delta=None, on_done=None, on_error=None,
         stream=True, temperature=0.6, max_tokens=1024, timeout=60):
    """یک درخواستِ چت (سازگار با OpenAI) در پس‌زمینه می‌فرستد.

    on_delta(text): برای حالتِ streaming، هر تکهٔ تازهٔ متن.
    on_done(full_text): متنِ کاملِ نهایی.
    on_error(msg): پیامِ خطای فارسی.
    همهٔ callbackها روی تردِ اصلیِ UI اجرا می‌شوند.
    """
    cfg = get_config()
    if not cfg.get("api_key"):
        _ui(on_error, "کلید API تنظیم نشده است. از دکمهٔ «تنظیمات هوش مصنوعی» کلیدت را وارد کن.")
        return

    def _worker():
        url = cfg["base_url"] + "/chat/completions"
        payload = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "stream": bool(stream),
        }
        # اگر سقف تعیین نشده باشد (None) اصلاً به سرور فرستاده نمی‌شود تا مدل
        # تا پایانِ طبیعیِ خودش ادامه دهد (بدون محدودیتِ توکن).
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        # ابتدا با اعتبارسنجیِ کاملِ SSL؛ اگر روی اندروید گواهی پیدا نشد، یک‌بار بدونِ
        # اعتبارسنجی تلاش می‌شود تا اتصال قطع نشود (سازشِ عملی برای اندروید).
        for unverified in (False, True):
            try:
                ctx = _ssl_context(unverified)
                resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
                if stream:
                    _read_stream(resp, on_delta, on_done)
                else:
                    raw = resp.read().decode("utf-8", "replace")
                    obj = json.loads(raw)
                    text = obj["choices"][0]["message"].get("content", "") or ""
                    _ui(on_done, _strip_think(text))
                return
            except urllib.error.HTTPError as e:
                _ui(on_error, _friendly_error(status=e.code))
                return
            except (ssl.SSLError, urllib.error.URLError) as e:
                # روی اندروید بستهٔ گواهی CA نیست؛ خطای گواهی اغلب داخلِ URLError
                # پیچیده می‌شود؛ پس اگر خطا از نوعِ SSL بود، یک‌بار بدونِ اعتبارسنجی دوباره تلاش می‌کنیم.
                reason = getattr(e, "reason", None)
                is_ssl = isinstance(e, ssl.SSLError) or isinstance(reason, ssl.SSLError)
                if is_ssl and not unverified:
                    continue
                _ui(on_error, _friendly_error())
                return
            except Exception:
                _ui(on_error, _friendly_error())
                return

    threading.Thread(target=_worker, daemon=True).start()


def _read_stream(resp, on_delta, on_done):
    """خواندنِ خط‌به‌خطِ پاسخِ SSE و ارسالِ تکه‌های متن به UI."""
    acc = []
    tf = _ThinkFilter()
    for raw_line in resp:
        try:
            line = raw_line.decode("utf-8", "replace").strip()
        except Exception:
            continue
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = obj["choices"][0].get("delta", {}) or {}
            piece = delta.get("content") or ""
        except Exception:
            piece = ""
        if not piece:
            continue
        visible = tf.feed(piece)
        if visible:
            acc.append(visible)
            _ui(on_delta, visible)
    tail = tf.flush()
    if tail:
        acc.append(tail)
        _ui(on_delta, tail)
    _ui(on_done, "".join(acc).strip())


def test_connection(on_ok=None, on_fail=None):
    """یک درخواستِ کوچک برای آزمونِ اتصال/کلید."""
    chat(
        [{"role": "user", "content": "سلام"}],
        on_done=lambda _t: (on_ok("اتصال موفق بود ✓") if on_ok else None),
        on_error=lambda m: (on_fail(m) if on_fail else None),
        stream=False, temperature=0.0, max_tokens=8, timeout=30,
    )


# ------------------------------------------------------------------
# سازندهٔ پیام‌ها برای سه بخشِ اپ (تا main.py تمیز بماند)
# ------------------------------------------------------------------
def _verse_block(prefix, s, a, arb, pers):
    return "%s سوره %s ، آیه %s\n  عربی: %s\n  ترجمه: %s" % (
        prefix, s, a, (arb or "-"), (pers or "-"))


def build_note_messages(seed, target, operator):
    """پیام‌های "دستیارِ تحلیلِ دو آیه" هنگامِ ثبت کشف."""
    nl = chr(10)
    sys = nl.join([
        "تو پژوهشگری خبره در علومِ قرآنی و متخصصِ «پردازشِ آینه‌ایِ آیات» هستی. دو آیه که با یک عملگرِ آینه‌ای به هم پیوند خورده‌اند به تو داده می‌شود.",
        "تحلیل را در دو لایه بنویس: کالبد (پژواکِ واژگانی، تقارنِ ساختاری، هم‌آوایی) و روح (مفهوم، تفسیر، تقابل/تناظر). توجه کن قرینگی ممکن است در مفهوم باشد نه فقط در لفظ.",
        "به اثرانگشتِ عددیِ داده‌شده هم توجه کن (به‌ویژه بخش‌پذیری بر ۱۱ برای عملگرهای آینهٔ کامل T2/T5)؛ ولی دربارهٔ مضربِ ۱۹/۲۹ اغراق نکن چون هنوز اثبات‌نشده‌اند.",
        "خروجی فارسیِ روان و بی‌طرف، ۴ تا ۶ جمله، بدونِ مقدمه‌چینی و بدونِ تکرارِ متنِ آیه.",
    ])
    fp = ""
    try:
        fp = qref.fingerprint_text(seed.get("s"), seed.get("a"), target.get("s"), target.get("a"), qref.op_code(operator))
    except Exception:
        fp = ""
    usr = "عملگرِ آینه‌ای: %s" % (operator or "نامشخص")
    usr += nl + nl + _verse_block("آیهٔ بذر —", seed.get("s"), seed.get("a"), seed.get("arb"), seed.get("pers"))
    usr += nl + nl + _verse_block("آیهٔ مقصد —", target.get("s"), target.get("a"), target.get("arb"), target.get("pers"))
    if fp:
        usr += nl + nl + "اثرانگشتِ عددی:" + nl + fp
    usr += nl + nl + "تحلیلِ کوتاه و دقیق را در دو لایهٔ کالبد و روح بنویس."
    return [{"role": "system", "content": sys}, {"role": "user", "content": usr}]


def build_matrix_messages(seed, cards):
    """پیام‌های تحلیلِ یکپارچهٔ ماتریس برای صفحهٔ پردازش."""
    nl = chr(10)
    sys = nl.join([
        "تو پژوهشگری خبره در علومِ قرآنی و تفسیر هستی. یک آیهٔ «بذر» و چند آیهٔ «مقصد» به تو داده می‌شود که با عملگرهای گوناگون (هفت‌گانه یا گردشِ ارقام) از بذر ساخته شده‌اند.",
        "قاعدهٔ مهم: به‌زور و مصنوعی همهٔ مقصدها را به بذر ربط نده؛ اگر آیه‌ای پیوندِ معناداری با بذر ندارد، صادقانه بگو ارتباطش ضعیف یا سطحی است.",
        "برای هر مقصد، محتوای خودِ آیه را در سه لایه بررسی و تفسیر کن:",
        "۱) واژه‌ای: اشتراک یا قرابتِ واژگان و ریشه‌ها با بذر.",
        "۲) مفهومی: پیوندِ مضمون و معنا (فراتر از لفظ).",
        "۳) تفسیری: پیامِ کلی و نگاهِ تفسیری، و اینکه عملگرِ به‌کاررفته چه حالتی ساخته و نتیجه‌اش بامعناست یا نه.",
        "دربارهٔ حالتِ هر مقصد هم توضیح بده که چه نوع تبدیلی روی بذر انجام شده است.",
        qref.ANALYSIS_GUIDE,
        qref.SEMANTIC_GUIDE,
        "در پایان، در یک جمع‌بندیِ روشن بنویس: «به نظرم نزدیک‌ترین آیه به آیهٔ بذر این است: …» و دلیلِ کوتاهت را هم بیاور.",
        "فارسیِ روان و منظم با تیترهای کوتاه بنویس.",
    ])
    lines = [_verse_block("آیهٔ بذر —", seed.get("s"), seed.get("a"), seed.get("arb"), seed.get("pers")),
             "", "آیاتِ مقصد:"]
    for i, c in enumerate(cards, 1):
        _card = [
            "%d) [حالت: %s] سوره %s ، آیه %s" % (i, (c.get("mode", "") or "-"), c.get("s"), c.get("a")),
            "    عربی: %s" % (c.get("arb", "") or "-"),
            "    ترجمه: %s" % (c.get("pers", "") or "-"),
        ]
        try:
            for _fl in qref.fingerprint_text(seed.get("s"), seed.get("a"), c.get("s"), c.get("a"), qref.op_code(c.get("mode", ""))).split(nl):
                _card.append("    " + _fl)
        except Exception:
            pass
        lines.append(nl.join(_card))
    usr = nl.join(lines) + nl + nl + ("هر مقصد را در سه لایهٔ واژه‌ای، مفهومی و تفسیری بررسی کن، "
                                      "حالتش را توضیح بده، و در پایان نزدیک‌ترین آیه به بذر را با دلیل معرفی کن.")
    return [{"role": "system", "content": sys}, {"role": "user", "content": usr}]


def _format_discoveries(favs, featured, cap=40):
    def fmt(items, label):
        if not items:
            return "%s: (خالی)" % label
        out = ["%s (%d مورد):" % (label, len(items))]
        for i, it in enumerate(items[:cap], 1):
            note = it.get("note") or ""
            if len(note) > 220:
                note = note[:220] + "…"
            _fpx = ""
            try:
                if it.get("target_s") is not None:
                    _f = qref.numeric_fingerprint(it.get("seed_s"), it.get("seed_a"), it.get("target_s"), it.get("target_a"), qref.op_code(it.get("mode", "")))
                    _fpx = " | عددی: Δنزول=%+d، مجموع⁷%s" % (_f["d_nuzul"], ("÷11" if _f["mod11"] else "-"))
            except Exception:
                _fpx = ""
            out.append("%d) [%s] سوره %s:%s ⟵ سوره %s:%s | برچسب: %s%s%s" % (
                i, (it.get("mode", "") or "-"),
                it.get("seed_s"), it.get("seed_a"),
                it.get("target_s"), it.get("target_a"),
                it.get("relation_type", "نامشخص"),
                _fpx,
                (" | تحلیل: " + note) if note else ""))
        if len(items) > cap:
            out.append("… و %d موردِ دیگر (برای اختصار نمایش داده نشد)" % (len(items) - cap))
        return "\n".join(out)
    return fmt(favs, "لابراتوار") + "\n\n" + fmt(featured, "گلچین برگزیده")


def build_chat_system(favs, featured):
    """سیستم‌پرامتِ چتِ صفحهٔ اصلی با کلِ دیتای کشفیاتِ کاربر."""
    return (
        "تو دستیارِ هوشمندِ اپلیکیشنِ «قطب‌نمای قرآنی» هستی؛ ابزاری برای «پردازشِ آینه‌ایِ آیات». "
        "کاربر مجموعه‌ای از کشفیاتِ خود (جفت‌آیه‌های آینه‌ای همراه با تحلیل و برچسب) را ثبت کرده است. "
        "با تکیه بر همین داده‌ها با کاربر گفتگو کن: خلاصه بده، الگو و شباهت پیدا کن، مقایسه و تحلیل کن و پیشنهاد بده. "
        "در تحلیل، هم لایهٔ کالبدی (پژواکِ واژگانی، تقارن، هم‌آوایی) و هم لایهٔ روحی (مفهوم و تفسیر) را ببین. دربارهٔ سرنخ‌های عددی صادق باش (مضربِ ۱۱ برای T2/T5 قطعی، ولی ۱۹/۲۹ اثبات‌نشده).\n"
        "اگر داده‌ای موجود نیست صادقانه بگو. فارسیِ روان و تا حدِ امکان کوتاه بنویس.\n\n"
        "=== دادهٔ کشفیاتِ کاربر ===\n" + _format_discoveries(favs, featured)
    )


# ------------------------------------------------------------------
# حالتِ «گفت‌وگو دربارهٔ قرآن کریم» (بازیابیِ آیات از کلِ دیتاکاوش)
# ------------------------------------------------------------------
def _parse_terms(text):
    """از خروجیِ مدل، فهرستِ کلیدواژه‌ها را (ترجیحاً JSON) بیرون می‌کشد."""
    if not text:
        return []
    t = _strip_think(text).strip()
    # ۱) تلاش برای یافتنِ آرایهٔ JSON داخلِ متن
    try:
        i = t.find("[")
        j = t.rfind("]")
        if i != -1 and j != -1 and j > i:
            arr = json.loads(t[i:j + 1])
            out = []
            for x in arr:
                if isinstance(x, str):
                    s = x.strip()
                    if s and s not in out:
                        out.append(s)
            if out:
                return out[:30]
    except Exception:
        pass
    # ۲) جایگزین: جداسازی با خط/کاما/خط‌عمودی
    parts = re.split(r"[\n,\u060C|\u061B]+", t)
    out = []
    for p in parts:
        p = p.strip().strip("\"'[]•- ").strip()
        if p and len(p) <= 40 and p not in out:
            out.append(p)
    return out[:30]


def quran_search_terms(question, on_done=None, on_error=None):
    """مرحلهٔ ۱: از مدل می‌خواهد فهرستی از کلیدواژه/ریشه‌های عربیِ مرتبط با پرسش را بدهد
    (هم مستقیم و هم اشاره‌های غیرمستقیم و مترادف‌ها) تا در متنِ آیاتِ دیتاکاوش جست‌وجو شوند.
    on_done(list_of_terms) روی تردِ اصلیِ UI صدا زده می‌شود."""
    sys = (
        "تو یک کمک‌جوی قرآنی هستی. کاربر پرسشی دربارهٔ قرآن می‌پرسد و ما می‌خواهیم همهٔ آیاتِ مرتبط "
        "(مستقیم و غیرمستقیم) را از متنِ قرآن بیرون بکشیم. "
        "وظیفهٔ تو فقط این است که فهرستی از کلیدواژه‌ها و ریشه‌های عربیِ مرتبط با موضوع را بدهی تا در متنِ آیات جست‌وجو شوند. "
        "هم واژه‌های مستقیم، هم واژه‌های اشاره‌کنندهٔ غیرمستقیم، هم مترادف‌ها و هم صورت‌های صرفیِ پرکاربرد (مفرد/جمع/فعل/اسم) را بیاور تا هیچ آیهٔ مرتبطی جا نماند. "
        "خروجی را فقط و فقط به‌صورتِ یک آرایهٔ JSON از رشته‌های عربی بده، بدونِ هیچ توضیحِ اضافه. "
        "مثال برای موضوعِ اعداد: [\"عدد\",\"عدّ\",\"احصى\",\"سبع\",\"عشرة\",\"الف\",\"مئة\"]. حداکثر ۳۰ کلیدواژه."
    )

    def _parsed(text):
        if on_done:
            on_done(_parse_terms(text))

    chat([{"role": "system", "content": sys},
          {"role": "user", "content": (question or "").strip()}],
         on_done=_parsed, on_error=on_error,
         stream=False, temperature=0.2, max_tokens=400, timeout=40)


def build_quran_messages(question, verses, history=None):
    """مرحلهٔ ۲: آیاتِ بازیابی‌شده از کلِ دیتاکاوش + پرسشِ کاربر را به مدل می‌دهد تا تحلیل کند."""
    nl = chr(10)
    sys = nl.join([
        "تو پژوهشگری خبره در علومِ قرآنی و تفسیر هستی و دستیارِ بخشِ «گفت‌وگو دربارهٔ قرآن کریم» در اپلیکیشنِ «قطب‌نمای قرآنی».",
        "به تو فهرستی از آیاتِ قرآن (متنِ عربی و ترجمهٔ فارسی) داده می‌شود که با جست‌وجوی گسترده در کلِ منبعِ دادهٔ «دیتاکاوش» (کلِ ۶۲۳۶ آیه) و بر اساسِ کلیدواژه‌های مرتبط با پرسشِ کاربر گرد آمده‌اند.",
        "قاعده‌ها:",
        "۱) پاسخ را فقط بر پایهٔ همین آیاتِ داده‌شده بنا کن؛ آیه از خودت نساز و مرجعِ نادرست نده.",
        "۲) هم آیاتِ مستقیم و هم آیاتی که غیرمستقیم به موضوع اشاره دارند را بیاور و هیچ آیهٔ مرتبطی را از قلم ننداز.",
        "۳) اگر آیه‌ای در فهرست هست ولی به موضوع ربط ندارد، کنارش بگذار و صادق باش.",
        "۴) اگر گمان می‌کنی آیهٔ مرتبطی هست که در فهرست نیامده، بگو «در نتایجِ جست‌وجو نبود» و از کاربر بخواه واژهٔ دقیق‌تری بدهد تا دوباره بگردیم.",
        "برای هر آیه، نشانیِ (سوره:آیه) و خلاصهٔ ربطش به موضوع را روشن بنویس. فارسیِ روان و منظم با تیتر و فهرست بنویس.",
        qref.ANALYSIS_GUIDE,
        qref.SEMANTIC_GUIDE,
    ])
    lines = ["پرسشِ کاربر: " + (question or "").strip(), "",
             "آیاتِ بازیابی‌شده از دیتاکاوش (%d آیه):" % len(verses or [])]
    if verses:
        for i, v in enumerate(verses, 1):
            lines.append("%d) سوره %s ، آیه %s" % (i, v.get("s"), v.get("a")))
            lines.append("   عربی: %s" % (v.get("arb", "") or "-"))
            lines.append("   ترجمه: %s" % (v.get("pers", "") or "-"))
    else:
        lines.append("(هیچ آیه‌ای در جست‌وجو یافت نشد — از کاربر بخواه پرسش را با واژه‌های دیگری بازگو کند.)")
    usr = nl.join(lines)
    msgs = [{"role": "system", "content": sys}]
    if history:
        for m in history:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
                msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": usr})
    return msgs
