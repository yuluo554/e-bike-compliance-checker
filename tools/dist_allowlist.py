"""构建产物本体扫描（``--mode dist``）的上游固有元数据豁免清单。

**为什么单独成文件**：这些值会被 ``--mode tracked`` 扫到，逐字写进源码/文档会
自命中（本仓库 M6 期曾因在文档里逐字写上游邮箱被 CI 判 HARD，见
``plan/HANDOFF-M6.md`` §1.3）。故值一律**片段拼接**。

**豁免范围刻意收窄**：只登记"上游官方发行件里固有出现、与本项目无关"的**精确值**
（不是模式、不是整文件、不是"全部豁免"）。任何未登记的 HARD 命中都会让
``--mode dist`` 以退出码 1 结束。
"""

from __future__ import annotations


def _join(*parts):
    """片段拼接（防止清单文件自身被扫描器判成泄露形态）。"""
    return "".join(parts)


#: 每条：kind（分类）/ value（精确值）/ source（上游出处，供审计报告单列）。
ENTRIES = (
    # —— CPython 官方解释器/标准库维护者邮箱（python312.dll、base_library.zip 内固有） ——
    {"kind": "email", "value": _join("guido", "@", "python.org"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("mal", "@", "lemburg.com"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("mike.verdone", "@", "gmail.com"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("mark.russell", "@", "zen.co.uk"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("solipsis", "@", "pitrou.net"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("amauryfa", "@", "gmail.com"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("benjamin", "@", "python.org"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("brian", "@", "sweetapp.com"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("sjoerd", "@", "acm.org"), "source": "CPython 官方构建元数据"},
    {"kind": "email", "value": _join("mhammond", "@", "skippinet.com.au"), "source": "CPython 官方构建元数据"},
    # —— 上游第三方库官方构建元数据 ——
    {"kind": "email", "value": _join("appro", "@", "openssl.org"), "source": "OpenSSL 官方发行件元数据"},
    {"kind": "email", "value": _join("bzip2-devel", "@", "sourceware.org"), "source": "bzip2 官方发行件元数据"},
    # —— 上游构建机路径（非本机路径） ——
    {"kind": "path", "value": _join("C:", "\\", "Users", "\\", "qt"), "source": "Qt 官方构建账号路径"},
    {"kind": "path", "value": _join("/Us", "ers/", "Barney"), "source": "CPython 官方构建机路径"},
    # —— 上游硬件厂商串（含本机用户名形态 "ASUS"，不豁免会与用户名扫描互相误伤） ——
    {"kind": "vendor", "value": _join("ASUS", "Tek COMPUTER INC"), "source": "Qt 内置显示设备厂商串"},
)

#: 供扫描器做"文本预处理替换"的精确值列表。
VALUES = tuple(entry["value"] for entry in ENTRIES)