#!/usr/bin/env bash
# Fire Review — 一鍵環境部署
#
# 用法：
#   bash tools/setup.sh              # 安裝審圖交付物所需的 Python 套件
#   bash tools/setup.sh --with-graph # 另外安裝 graphify（法規知識圖譜的重建／CLI 查詢）
#
# 目的：讓引用本倉庫的人「一個指令」就能跑起所有交付物，不必自行逐一尋找、安裝套件。
# 核心審圖工具（fire_code_calc.py、regulation_index.py）只用標準庫，本步驟主要補齊
# DXF／xlsx／PDF 交付物所需的第三方套件。

set -euo pipefail
cd "$(dirname "$0")/.."   # 專案根目錄

PYTHON="${PYTHON:-python3}"
WITH_GRAPH=0
for arg in "$@"; do
  case "$arg" in
    --with-graph) WITH_GRAPH=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知參數：$arg（可用 --with-graph）"; exit 2 ;;
  esac
done

echo "== Fire Review 環境部署 =="
echo "Python：$($PYTHON --version 2>&1)"

echo "-- 安裝 requirements.txt --"
if ! "$PYTHON" -m pip install -r requirements.txt; then
  echo "pip 直接安裝失敗，改用 --user 重試..."
  "$PYTHON" -m pip install --user -r requirements.txt \
    || "$PYTHON" -m pip install --break-system-packages -r requirements.txt
fi

if [ "$WITH_GRAPH" = "1" ]; then
  echo "-- 安裝 graphify（法規知識圖譜）--"
  if command -v uv >/dev/null 2>&1; then
    uv tool install --upgrade graphifyy && graphify install || true
  else
    "$PYTHON" -m pip install --upgrade graphifyy \
      || "$PYTHON" -m pip install --user --upgrade graphifyy \
      || "$PYTHON" -m pip install --break-system-packages --upgrade graphifyy
  fi
fi

echo "-- 環境自檢 --"
"$PYTHON" tools/check_env.py || true
echo "== 完成 =="
