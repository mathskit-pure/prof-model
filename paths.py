"""PROF 工程统一路径解析：本机 Windows 与云端 Linux 共用一份代码。

环境变量优先，其次按平台给默认值：
  Windows 本机  —— 沿用既有 WorkBuddy 目录，保证改造后本机行为不变
  Linux 云端    —— 由 bootstrap 克隆到 /workspace 下的兄弟目录

可用变量：PROF_DIR（本工程根）、POOL_BASE（主项目 pool-core）、
          AFGI_DIR（AFGI 工程）、WESTOCK_BIN、WB_LIBRARY_SKILL、POOL_PY
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 本工程根目录（paths.py 所在目录）
WORK = Path(os.environ.get("PROF_DIR") or Path(__file__).resolve().parent)

_WIN = {
    "POOL_BASE": r"C:\Users\12066\WorkBuddy\2026-10-05-23-13-30",
    "AFGI_DIR": r"C:\Users\12066\WorkBuddy\2026-10-05-14-50-58\afgi_tdx",
}
_LINUX = {"POOL_BASE": "pool-core", "AFGI_DIR": "afgi_tdx"}


def _ref(env_var: str) -> Path:
    v = os.environ.get(env_var)
    if v:
        return Path(v)
    if os.name == "nt":
        return Path(_WIN[env_var])
    return WORK.parent / _LINUX[env_var]


MAIN = _ref("POOL_BASE")          # 主项目 pool-core
AFGI = _ref("AFGI_DIR")           # AFGI 情绪指数工程

PY = os.environ.get("POOL_PY") or sys.executable

# westock CLI：跨平台 Go 二进制，Windows 为 westock.exe，Linux 为 westock
WESTOCK = (os.environ.get("WESTOCK_BIN")
           or (str(Path.home() / ".local" / "bin" / "westock.exe") if os.name == "nt" else "westock"))


def library_skill() -> Path:
    """定位资料库 library skill（含 page/import_html.py）。"""
    env = os.environ.get("WB_LIBRARY_SKILL")
    cands: list[Path] = []
    if env:
        cands.append(Path(env))
    if os.name == "nt":
        cands.append(Path(os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\WorkBuddy\resources\app.asar.unpacked"
            r"\resources\plugins\workbuddy-builtin\skills\library")))
    else:
        cands += [
            Path("/root/.codebuddy/skills/library"),
            Path("/root/.workbuddy/skills/library"),
            Path.home() / ".codebuddy/skills/library",
            Path.home() / ".workbuddy/skills/library",
        ]
    for c in cands:
        if (c / "page" / "import_html.py").exists():
            return c
    raise FileNotFoundError(
        "找不到资料库 library skill（page/import_html.py），"
        f"可用 WB_LIBRARY_SKILL 指定。已尝试：{[str(c) for c in cands]}"
    )


if __name__ == "__main__":
    print(f"WORK    = {WORK}")
    print(f"MAIN    = {MAIN}")
    print(f"AFGI    = {AFGI}")
    print(f"PY      = {PY}")
    print(f"WESTOCK = {WESTOCK}")
