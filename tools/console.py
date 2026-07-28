#!/usr/bin/env python3
"""讓工具的輸出在任何平台、任何主控台編碼下都印得出中文。

只用 Python 標準庫。

## 為什麼需要這個

本倉庫所有面向使用者的輸出都是繁體中文，而 Windows 的 Python 在 stdout
**被重導向或接管道**時，用的是系統 locale 編碼（英文版 Windows 是 cp1252），
一遇到中文就 `UnicodeEncodeError` 當場中斷——連第一行歡迎訊息都印不出來。

直接在主控台跑時不會發生（Python 會走 Windows 的 Unicode 主控台 API），
所以這個 bug 很容易漏掉。但它會打中兩種真實情況：

1. **AI 代理執行工具並讀取輸出**——那正是本倉庫的主要使用方式
   （`README.md` 就是叫代理去跑 `python tools/onboarding.py status`）
2. 使用者把輸出導進檔案留存，例如 `python tools/update_guard.py check > 紀錄.txt`

實際案例：v0.1.0 發版時，CI 的 windows job 在 `installer.py` 的第一個 `print`
就炸掉——27 個 CLI 工具全中。

## 為什麼不是靠環境變數

`PYTHONUTF8=1` 或 `PYTHONIOENCODING` 能解，但要求**每個呼叫端**都記得設。
安裝包附的兩個 .bat 有設（雙擊的使用者涵蓋到了），可是 AI 代理直接跑
`python tools/onboarding.py` 時不會。工具自己保證自己的輸出印得出來，
才不會把正確性押在呼叫端的紀律上。

`errors="replace"` 是刻意的：真的遇到連 UTF-8 都表達不了的東西時，
印出替代字元也好過整個流程中斷——診斷工具自己壞掉比漏報更糟。
"""

import sys


def force_utf8_output(streams=None):
    """把標準輸出與標準錯誤切成 UTF-8。可重複呼叫，失敗一律吞掉。

    回傳實際改動過的串流名稱，方便測試斷言。
    """
    changed = []
    for name in (streams or ("stdout", "stderr")):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # 被測試換成 StringIO、或在沒有標準串流的環境裡
        try:
            if (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
                reconfigure(encoding="utf-8", errors="replace")
                changed.append(name)
        except (ValueError, OSError):
            pass  # 串流已關閉或不支援重設——不值得為了這個讓工具跑不起來
    return changed
