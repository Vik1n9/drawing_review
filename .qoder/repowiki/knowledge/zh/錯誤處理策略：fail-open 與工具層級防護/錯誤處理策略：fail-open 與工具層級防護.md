---
kind: error_handling
name: 錯誤處理策略：fail-open 與工具層級防護
category: error_handling
scope:
    - '**'
source_files:
    - tools/console.py
    - tools/guard_hook.py
    - tools/installer.py
    - tools/update_guard.py
    - tools/dwg_guide.py
    - tests/test_guard_hook.py
---

本專案的錯誤處理採用「工具層級 fail-open」與「使用者輸出安全」雙軌設計，沒有統一的異常類型或中央錯誤碼表，而是讓每個 CLI 工具自行決定如何處理失敗。