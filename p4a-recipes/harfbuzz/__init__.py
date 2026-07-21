"""
Recipe سفارشیِ harfbuzz برای پروژهٔ Quran Mirror
==================================================

چرا این فایل لازم است؟
----------------------
نسخهٔ harfbuzz==2.6.4 (که به‌عنوان وابستگیِ pango/freetype ساخته می‌شود) با
تول‌چینِ NDK r25b (clang-14) کامپایل نمی‌شود. علتِ *دقیق* در لاگ این است:

    hb-subset-cff1.cc:472:33: error: variable 'supp_size' set but not used
        [-Werror,-Wunused-but-set-variable]
        unsigned int  size0, size1, supp_size;
    1 error generated.

یعنی متغیرِ `supp_size` در تابع `plan_subset_encoding` مقداردهی می‌شود ولی هرگز
*خوانده* نمی‌شود (مقدارِ بازگشتی از `subset_enc_supp_codes.length` می‌آید، نه از
`supp_size`). این فقط یک هشدارِ بی‌ضرر است، اما چون harfbuzz با `-Werror` ساخته
می‌شود، همان هشدار به خطا تبدیل شده و کلِ build را می‌شکند.

راهبردِ رفع (قطعی و مستقل از سازوکارِ فلگ‌ها)
--------------------------------------------
به‌جای اینکه فقط با `-Werror` بجنگیم (که در تلاش‌های قبلی و در پیشنهادِ
`--disable-werror` جواب نداد؛ آن گزینه مخصوصِ meson است و configureِ autotools در
2.6.4 آن را نمی‌شناسد)، ریشهٔ هشدار را در خودِ سورس از بین می‌بریم:

  ۱) در `prebuild_arch` سطرِ اعلانِ `supp_size` را با `__attribute__((unused))`
     علامت می‌زنیم تا clang دیگر هیچ هشداری برای «set but not used» تولید نکند.
     این کار ۱۰۰٪ قطعی است و به ترتیب یا رسیدنِ فلگ‌ها به فازِ make وابسته نیست.

  ۲) به‌عنوانِ لایهٔ پشتیبان، `-Werror` را از فایل‌های ساختِ harfbuzz خنثی می‌کنیم
     و `-Wno-error ...` را هم به CFLAGS/CXXFLAGS می‌افزاییم تا اگر هشدارِ دیگری هم
     در آینده پیش آمد، build را نشکند.

نکته: نسخهٔ harfbuzz عمداً روی 2.6.4 نگه داشته شده و بالا برده نشده، چون تغییرِ
آن زنجیرهٔ freetype/pango را به‌هم می‌ریزد و سازگاریِ آزموده‌شده را از بین می‌برد.
"""

import os
import re

from pythonforandroid.recipes.harfbuzz import HarfbuzzRecipe
from pythonforandroid.logger import info, warning

_SILENCE = (
    " -Wno-error"
    " -Wno-unused-but-set-variable"
    " -Wno-bitwise-instead-of-logical"
)


class HarfbuzzRecipePatched(HarfbuzzRecipe):
    # میرورِ مطمئن: سرورِ قدیمیِ freedesktop.org گاهی دانلود را با HTTP 418
    # (anti-bot) بلاک می‌کند و کلِ بیلد را می‌شکند. آدرسِ رسمیِ GitHub پایدار است.
    url = "https://github.com/harfbuzz/harfbuzz/releases/download/{version}/harfbuzz-{version}.tar.xz"

    def get_recipe_env(self, arch=None, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        # لایهٔ پشتیبان: هشدارها را به خطا تبدیل نکن.
        env["CFLAGS"] = (env.get("CFLAGS", "") + _SILENCE).strip()
        env["CXXFLAGS"] = (env.get("CXXFLAGS", "") + _SILENCE).strip()
        return env

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        build_dir = self.get_build_dir(arch.arch)

        # ── (۱) فیکسِ قطعیِ سورس: علامت‌زدنِ supp_size به‌عنوان unused ──────────
        cff1 = os.path.join(build_dir, "src", "hb-subset-cff1.cc")
        try:
            with open(cff1, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()

            # با فاصله‌گذاریِ متغیر سازگار است (چه یک اسپیس چه دو اسپیس).
            patched_data, n = re.subn(
                r"unsigned\s+int\s+size0,\s*size1,\s*supp_size\s*;",
                "unsigned int size0, size1, supp_size __attribute__((unused));",
                data,
                count=1,
            )

            if n:
                with open(cff1, "w", encoding="utf-8") as f:
                    f.write(patched_data)
                info(
                    "[harfbuzz-patch] supp_size به‌عنوان unused علامت خورد "
                    "(رفعِ خطای اصلیِ hb-subset-cff1.cc)"
                )
            else:
                warning(
                    "[harfbuzz-patch] الگوی supp_size پیدا نشد؛ "
                    "به لایهٔ پشتیبانِ -Wno-error تکیه می‌شود"
                )
        except (OSError, IOError) as exc:
            warning(
                "[harfbuzz-patch] عدمِ دسترسی به hb-subset-cff1.cc: %s" % exc
            )

        # ── (۲) لایهٔ پشتیبان: خنثی‌سازیِ -Werror در فایل‌های ساخت ─────────────
        patched_files = 0
        for dirpath, _dirs, files in os.walk(build_dir):
            for fn in files:
                is_build_file = (
                    fn in ("configure", "configure.ac", "configure.in")
                    or fn.startswith("Makefile")
                    or fn.endswith((".mk", ".am", ".in"))
                )
                if not is_build_file:
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue
                if "-Werror" not in content:
                    continue
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(content.replace("-Werror", "-Wno-error"))
                    patched_files += 1
                except (OSError, IOError):
                    continue
        info("[harfbuzz-patch] -Werror در %d فایل خنثی شد" % patched_files)


recipe = HarfbuzzRecipePatched()
