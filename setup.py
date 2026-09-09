from setuptools import setup, find_packages

setup(
    name="attack-tool",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "aiohttp>=3.8",
        "asyncio",
        "colorama",   # برای رنگ‌ها (اختیاری)
    ],
    entry_points={
        "console_scripts": [
            "attack-tool = attack_tool.main:main_menu",  # نام فرمان و تابع ورود
        ],
    },
    python_requires=">=3.8",
)
