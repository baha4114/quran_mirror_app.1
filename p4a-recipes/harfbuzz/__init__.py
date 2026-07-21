"""
Local p4a recipe override for harfbuzz (2.6.4).

مشکل
----
سورسِ harfbuzz 2.6.4 با autotools ساخته می‌شود. اسکریپتِ configure خودش
`-Werror` را داخلِ Makefileهایِ تولیدشده جاسازی می‌کند. کلنگِ NDK r25b چند
هشدارِ بی‌ضرر را (مثلاً `hb-subset-cff1.cc:472 supp_size set but not used` و
`hb-ot-layout-gpos-table.hh:848 bitwise | with boolean`) به‌خاطرِ `-Werror` به خطا
تبدیل می‌کند و build می‌شکند.

چرا راه‌هایِ قبلی جواب ندادند؟
-------------------------
تزریقِ `-Wno-error` از طریقِ CFLAGS/CXXFLAGSیِ محیط اثر نداشت، چون Makefileِ
harfbuzz مقدارِ CXXFLAGS را خودش ثابت می‌کند و متغیرِ محیطی را نادیده می‌گیرد.
حذفِ رشتهٔ `-Werror` هم کافی نبود چون configure آن را پویا (غیرمتنی)
می‌سازد.

راهِ حلِ قطعی (مستقل از درونیاتِ Makefile)
----------------------------------------
خودِ کامپایلر (CC و CXX) را با یک اسکریپتِ wrapper جایگزین می‌کنیم که در
انتهایِ هر فرمان، `-Wno-error` (و خاموش‌کردنِ دو هشدارِ خاص) را اضافه
می‌کند. چون آخرین فلگ برنده است، `-Werror`یِ داخلِ Makefile بی‌اثر می‌شود.
این روش به محلِ تعریفِ `-Werror` وابسته نیست و قطعاً کار می‌کند.
حذفِ -Werror کاملاً بی‌خطر است: فقط هشدارها دیگر به خطا تبدیل نمی‌شوند؛
خروجیِ کتابخانه دقیقاً همان است.
"""

import os

from pythonforandroid.recipes.harfbuzz import HarfbuzzRecipe
from pythonforandroid.logger import info


# فلگ‌هایی که در انتهایِ هر فرمانِ کامپایل اضافه می‌شوند (آخرین فلگ برنده است)
_SILENCE = (
    " -Wno-error"
    " -Wno-unused-but-set-variable"
    " -Wno-bitwise-instead-of-logical"
)

# محلِ نگه‌داریِ اسکریپت‌هایِ wrapper (خارج از پوشهٔ build تا منطقِ unpackِ p4a دست‌نخورد)
_WRAPPER_DIR = "/tmp/hb_wrappers"


class HarfbuzzRecipePatched(HarfbuzzRecipe):
    """harfbuzz بدونِ تبدیلِ هشدار به خطا تا با کلنگِ NDK r25b کامپایل شود."""

    def get_recipe_env(self, arch=None, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        # هم از راهِ محیط (پشتیبان) و هم از راهِ wrapper (اصلی) خاموش می‌کنیم
        env["CFLAGS"] = env.get("CFLAGS", "") + _SILENCE
        env["CXXFLAGS"] = env.get("CXXFLAGS", "") + _SILENCE

        try:
            os.makedirs(_WRAPPER_DIR, exist_ok=True)
        except OSError:
            # اگر نشد، دست‌کم فلگ‌هایِ محیطی را داریم
            return env

        arch_name = getattr(arch, "arch", "host")
        for var, base in (("CC", "cc"), ("CXX", "cxx")):
            orig = (env.get(var) or "").strip()
            if not orig:
                continue
            wrapper = os.path.join(_WRAPPER_DIR, "hb_%s_%s.sh" % (base, arch_name))
            try:
                with open(wrapper, "w") as f:
                    # مهم: فلگ‌هایِ خاموش‌سازی بعد از "$@" می‌آیند تا آخرین فلگ باشند
                    f.write('#!/bin/sh\nexec %s "$@"%s\n' % (orig, _SILENCE))
                os.chmod(wrapper, 0o755)
            except OSError:
                continue
            env[var] = wrapper

        return env

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        # پشتیبانِ اضافی: هر -Werrorیِ متنی در فایل‌هایِ ساخت را هم خنثی می‌کنیم
        build_dir = self.get_build_dir(arch.arch)
        patched = 0
        for dirpath, _dirs, files in os.walk(build_dir):
            for fn in files:
                if fn == "configure" or fn.startswith("Makefile") or fn.endswith(".mk"):
                    path = os.path.join(dirpath, fn)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            data = f.read()
                    except (OSError, IOError):
                        continue
                    if "-Werror" in data:
                        data = data.replace("-Werror", "-Wno-error")
                        try:
                            with open(path, "w", encoding="utf-8") as f:
                                f.write(data)
                            patched += 1
                        except (OSError, IOError):
                            continue
        info("[harfbuzz-patch] wrapper فعال شد + -Werror در {} فایل خنثی شد".format(patched))


recipe = HarfbuzzRecipePatched()
