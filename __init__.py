"""
Local p4a recipe override for harfbuzz.

چرا این فایل لازم است؟
----------------------
سورسِ رسمیِ harfbuzz با فلگِ `-Werror` کامپایل می‌شود. کلنگِ ۱۴ که در
NDK r25b هست، هشدارِ ساده‌ی `-Wunused-but-set-variable` (متغیرِ مقداردهی‌شده
ولی استفاده‌نشده در hb-subset-cff1.cc) را به‌خاطرِ `-Werror` به «خطا» تبدیل
می‌کند و کلِ بیلدِ harfbuzz -> pango می‌ایستد. این باعث می‌شد APK اصلاً
ساخته نشود (هرچند به‌خاطرِ لاگ‌گیری، اکشن تیکِ سبزِ کاذب می‌خورد).

راهِ حل:
--------
این recipe از recipeِ رسمیِ p4a ارث‌بری می‌کند و فقط فلگ‌های کامپایل را با
`-Wno-error` (و صریحاً خاموش‌کردنِ همان دو هشدار) گسترش می‌دهد. در automake
متغیرِ CXXFLAGS همیشه بعد از فلگ‌های داخلیِ پروژه روی خطِ فرمان قرار می‌گیرد،
پس `-Wno-error` بر `-Werror` غلبه می‌کند و بقیهٔ منطقِ رسمیِ بیلد دست‌نخورده
می‌ماند. هیچ چیزِ دیگری از رفتارِ استانداردِ harfbuzz تغییر نمی‌کند.
"""

from pythonforandroid.recipes.harfbuzz import HarfbuzzRecipe


# فلگ‌هایی که هشدارها را غیرکشنده می‌کنند (خطاهای دیده‌شده در NDK r25b / clang-14)
_SILENCE_FLAGS = (
    " -Wno-error"
    " -Wno-unused-but-set-variable"
    " -Wno-bitwise-instead-of-logical"
)


class HarfbuzzRecipePatched(HarfbuzzRecipe):
    """harfbuzz با فلگ‌های اصلاح‌شده تا با کلنگِ NDK r25b کامپایل شود."""

    def get_recipe_env(self, arch=None, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["CFLAGS"] = env.get("CFLAGS", "") + _SILENCE_FLAGS
        env["CXXFLAGS"] = env.get("CXXFLAGS", "") + _SILENCE_FLAGS
        return env


recipe = HarfbuzzRecipePatched()
