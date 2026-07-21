"""
Local p4a recipe override for harfbuzz (2.6.4).

مشکل:
-----
سورسِ harfbuzz 2.6.4 با autotools ساخته می‌شود و فلگِ `-Werror` داخلِ خودِ
Makefileهایِ آن جاسازی شده است. کلنگِ ۱۴ (NDK r25b) یک هشدارِ بی‌ضرر
(`hb-subset-cff1.cc:472: 'supp_size' set but not used`) را به‌خاطرِ `-Werror` به خطا
تبدیل می‌کند و کلِ زنجیرهٔ harfbuzz -> pango می‌شکند.

چرا راهِ قبلی (تزریقِ CXXFLAGS از محیط) جواب نداد؟
----------------------------------------------
چون configure/Makefileِ harfbuzz فلگ‌هایِ خودرا داخلِ Makefile ثابت می‌کند و
`CXXFLAGS`ِ محیط را نادیده می‌گیرد؛ برای همین `-Wno-error` اصلاً به کامپایلر نمی‌رسید.

راهِ حلِ قطعی:
------------
در prebuild_arch (که بعد از بازکردنِ سورس و قبل از configure/make اجرا می‌شود)
مستقیماً رشتهٔ `-Werror` را از تمامِ فایل‌هایِ ساخت (configure, Makefile.in,
Makefile.am, Makefile, *.mk) حذف می‌کنیم. این دیگر به رفتارِ داخلیِ p4a وابسته
نیست و قطعاً اثر می‌کند. حذفِ `-Werror` کاملاً بی‌خطر است: فقط باعث می‌شود
هشدارها دیگر به خطا تبدیل نشوند (خروجیِ کتابخانه دقیقاً همان است).
"""

import os

from pythonforandroid.recipes.harfbuzz import HarfbuzzRecipe
from pythonforandroid.logger import info


# نامِ فایل‌هایی که ممکن است شاملِ -Werror باشند
_BUILD_FILE_NAMES = ("configure", "Makefile", "Makefile.in", "Makefile.am", "config.status")

_SILENCE_FLAGS = (
    " -Wno-error"
    " -Wno-unused-but-set-variable"
    " -Wno-bitwise-instead-of-logical"
)


def _strip_werror_in_tree(root):
    """حذفِ هر -Werror از فایل‌هایِ ساخت در کلِ درختِ سورس."""
    patched = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn in _BUILD_FILE_NAMES or fn.endswith(".mk") or fn.startswith("Makefile"):
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        data = f.read()
                except (OSError, IOError):
                    continue
                if "-Werror" in data:
                    # هم `-Werror` تنها و هم شکل‌هایِ ترکیبی را خنثی می‌کنیم
                    data = data.replace("-Werror", "-Wno-error")
                    try:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(data)
                        patched += 1
                    except (OSError, IOError):
                        continue
    return patched


class HarfbuzzRecipePatched(HarfbuzzRecipe):
    """harfbuzz بدونِ -Werror تا با کلنگِ NDK r25b کامپایل شود."""

    def get_recipe_env(self, arch=None, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["CFLAGS"] = env.get("CFLAGS", "") + _SILENCE_FLAGS
        env["CXXFLAGS"] = env.get("CXXFLAGS", "") + _SILENCE_FLAGS
        return env

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        build_dir = self.get_build_dir(arch.arch)
        count = _strip_werror_in_tree(build_dir)
        info("[harfbuzz-patch] -Werror حذف شد از {} فایل در {}".format(count, build_dir))


recipe = HarfbuzzRecipePatched()
