#!/usr/bin/env python3
"""本機成果守門：更新倉庫之前先確認使用者的訓練成果不會被蓋掉，被蓋掉了要救得回來。

只用 Python 標準庫。

    python3 tools/update_guard.py check      # 0=安全 2=備份過期/清單需複核 3=尚未備份 4=疑似遺失
    python3 tools/update_guard.py list       # 列出備份（含絕對路徑）
    python3 tools/update_guard.py snapshot   # 備份到倉庫外
    python3 tools/update_guard.py diff       # 比對備份與現況
    python3 tools/update_guard.py restore    # 逐項救回
    python3 tools/update_guard.py commit     # 把本機成果送進 git object database
    python3 tools/update_guard.py install    # 安裝新版（線2 升級，由安裝程式呼叫）

## 為什麼需要這個工具

使用者是消防專業人員，倉庫在他自己的電腦上，訓練成果（規則裁示、實務見解、
案件圖面）**只存在本機、從未推上遠端**。他把倉庫網址貼給 AI 說「幫我更新」時，
AI 很可能 `git pull` 撞到本機改動就 `git checkout -- .`／`reset --hard`／`clean -fd`
清乾淨再拉——這會把他累積數月的成果一次抹掉，而且不可逆。

## 四個實作紀律（跟 graph_status.py 的「為什麼不用 mtime」同一種筆記）

1. **不另建要人工維護的基準檔。** 基準來源優先序：`安裝清單.json`（線2 安裝包，
   發版時自動產生）→ git（線1 clone）→ 最近一次備份的 manifest（退化）→ 都沒有
   則 `unknown`。多一份要同步的狀態檔就多一個漂移來源。

2. **備份放倉庫外。** repo 內就算 gitignore 也擋不住 `git clean -fdx` 與「刪目錄
   重裝」。主庫是倉庫的同層目錄（使用者找得到），另在家目錄留一份**索引**，
   讓使用者重裝到別的位置之後，新目錄仍找得回舊備份（`foreign_backup` 狀態）。

3. **`shared` 檔不整檔 restore。** `rules/*.json`、`graph.json` 是使用者裁示與上游
   法規更新**交錯**的檔案；拿三週前的備份整檔蓋回去，會把上游的修法一起吃掉。
   這類檔案的正確救援是列差異、重跑先紅再綠或逐則裁示。

4. **git 的比較基準是遠端追蹤分支，不是 HEAD。** 否則使用者一旦本機 commit
   （`commit` 子命令正是要他這麼做），所有成果都會被判成「與上游相同」，
   守門立刻變成假綠燈。

本工具**不做任何法規判斷**（審圖最高原則 2／4／5），只回答「哪些是你的成果、
有沒有備份、有沒有被蓋掉」。行為契約見 `skills/safe-update.md`。
"""

import argparse
import datetime
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

try:
    from tools.graph_status import sha256_file
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from graph_status import sha256_file

SCHEMA_VERSION = 1

# 線2 安裝包在倉庫根目錄留下的清單，就是「上游出貨時長什麼樣」的權威紀錄。
MANIFEST_NAME = "安裝清單.json"
REPORT_PREFIX = "更新報告-"
UPSTREAM_SUFFIX = ".上游新版"

BACKUP_MARKER = "-本機備份-"
INDEX_RELPATH = Path(".fire_review") / "backups.json"

# 超過這個大小只記 size 不算 sha256：開場診斷每次都會跑，
# 使用者的 DXF 動輒數十 MB，逐檔雜湊會讓 status 慢到沒人願意等。
MAX_HASH_BYTES = 64 * 1024 * 1024

USER, SHARED = "user", "shared"

# 使用者產物唯一可能落地的地方。反向列舉的關鍵前提：
# 資料區「內」的上游正典是封閉小集合（幾份 README、.gitkeep、範例案件），
# 而使用者產物是開放集合——正向列舉永遠會漏，反向排除才數得完。
DATA_ZONES = ("rules", "governance", "practice_notes", "training",
              "graphify-out", "input", "output")
ROOT_FILES = ("待確認事項.md",)

# 明確屬於上游的分區——不是使用者產物，改了不該觸發保護清單複核。
# 兩份清單合起來要涵蓋整個倉庫：漏掉的就是 unlisted_changes() 要叫出來的。
UPSTREAM_ZONES = ("tools", "skills", "tests", "docs", ".github", ".claude", "packaging")
UPSTREAM_ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md",
                       "requirements.txt", ".gitignore",
                       # 線2 安裝包放的雙擊入口與說明
                       "開場診斷.bat", "安裝完成-請把這段貼給你的AI.txt")

# fnmatch 語意：`*` 會跨過 `/`，所以 `input/範例/*` 涵蓋整棵子樹、
# `*/README.md` 涵蓋任何深度的 README。
UPSTREAM_EXCLUDE = (
    "README.md", "*/README.md", "*/.gitkeep",
    "input/範例/*",
    "graphify-out/.graphify_*", "graphify-out/cache/*",
    "*/__pycache__/*", "*.pyc", "*/.DS_Store", ".DS_Store",
    "*" + UPSTREAM_SUFFIX,
    MANIFEST_NAME, REPORT_PREFIX + "*",
)

# 誰擁有這個檔案——決定 restore 敢不敢整檔蓋回去。先命中先算。
OWNER_RULES = (
    ("rules/*", SHARED),          # 規則參數與法規全文都與上游共編
    # 法規圖譜與它的 id 台帳（node_ledger.json 必須與 graph.json 同版本——
    # 台帳斷了，抽取檔與訓練圖譜的跨圖譜參照就掛不回法規）。訓練成果不在這裡，見 training/。
    ("graphify-out/*", SHARED),
    ("governance/*", USER),
    ("practice_notes/*", USER),
    ("training/*", USER),
    ("input/*", USER),
    ("output/*", USER),
    ("待確認事項.md", USER),
)

PRISTINE, MODIFIED, ADDED, UNKNOWN = "pristine", "modified", "added", "unknown"

EXIT_CODES = {
    "no_local_data": 0,
    "protected": 0,
    "drifted": 2,
    "unlisted": 2,
    "unprotected": 3,
    "unknown": 3,
    "suspected_loss": 4,
    "foreign_backup": 4,
}

# onboarding.py 的步驟標記（ready/action/blocked）。
# 全新使用者不能看到紅燈——`no_local_data` 必須是 ready，否則第一次載入的人
# 第一步就卡住。備份沒做不影響審圖正確性，所以是 action 不是 blocked；
# 只有規則庫真的被還原（產出會是錯的）才 blocked。
STEP_STATES = {
    "no_local_data": "ready",
    "protected": "ready",
    "drifted": "action",
    "unlisted": "action",
    "unprotected": "action",
    "unknown": "action",
    "suspected_loss": "blocked",
    "foreign_backup": "blocked",
}

SEVERITY = ("suspected_loss", "foreign_backup", "unlisted", "drifted",
            "unprotected", "unknown", "protected", "no_local_data")


# ---------------------------------------------------------------------------
# 保護範圍
# ---------------------------------------------------------------------------

def matches_any(relpath, patterns):
    return any(fnmatch.fnmatch(relpath, pattern) for pattern in patterns)


def owner_for(relpath):
    for pattern, owner in OWNER_RULES:
        if fnmatch.fnmatch(relpath, pattern):
            return owner
    return USER


def iter_protected_paths(root):
    """保護範圍內實際存在的檔案，回傳 repo 相對的 posix 路徑。"""
    root = Path(root)
    for zone in DATA_ZONES:
        base = root / zone
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if not matches_any(rel, UPSTREAM_EXCLUDE):
                yield rel
    for name in ROOT_FILES:
        if (root / name).is_file():
            yield name


def file_entry(root, relpath):
    path = Path(root) / relpath
    size = path.stat().st_size
    entry = {"size": size, "owner": owner_for(relpath)}
    entry["sha256"] = None if size > MAX_HASH_BYTES else sha256_file(path)
    return entry


def collect_protected(root="."):
    """{relpath: {sha256, size, owner}}，路徑排序輸出。"""
    return {rel: file_entry(root, rel)
            for rel in sorted(iter_protected_paths(root))}


# ---------------------------------------------------------------------------
# 基準：安裝清單 → git → 備份 manifest
# ---------------------------------------------------------------------------

def run_git(root, args, timeout=30):
    """跑一個 git 子命令。git 不在、倉庫壞掉、逾時——一律回 None，不得拋例外。"""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def git_reference(root):
    """比較基準：優先遠端追蹤分支，退而求其次才是 HEAD。

    用 HEAD 會在使用者本機 commit 之後把所有成果判成「與上游相同」——
    而 `commit` 子命令正是要他這麼做，等於自己把守門變成假綠燈。
    """
    upstream = run_git(root, ["rev-parse", "--abbrev-ref",
                              "--symbolic-full-name", "@{u}"])
    if upstream and upstream.strip():
        return upstream.strip()
    head = run_git(root, ["rev-parse", "--verify", "HEAD"])
    return "HEAD" if head else None


def git_baseline(root):
    """{relpath: MODIFIED/ADDED} —— 沒列到的追蹤檔就是 pristine。"""
    reference = git_reference(root)
    if reference is None:
        return None
    changed = run_git(root, ["diff", "--name-only", "-z", reference])
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if changed is None or untracked is None:
        return None
    status = {}
    for rel in filter(None, changed.split("\0")):
        status[rel] = MODIFIED
    for rel in filter(None, untracked.split("\0")):
        status[rel] = ADDED
    return {"kind": "git", "reference": reference, "status": status}


def load_manifest(root):
    path = Path(root) / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return doc if isinstance(doc, dict) and doc.get("files") else None


def install_baseline(root):
    doc = load_manifest(root)
    if doc is None:
        return None
    return {"kind": "install", "version": doc.get("version"), "files": doc["files"]}


def resolve_baseline(root="."):
    """線2 的安裝清單優先於 git：安裝目錄沒有 .git，清單是那裡唯一的權威。"""
    return install_baseline(root) or git_baseline(root)


def classify(protected, baseline):
    """{relpath: pristine|modified|added|unknown}。"""
    if baseline is None:
        return {rel: UNKNOWN for rel in protected}
    if baseline["kind"] == "git":
        status = baseline["status"]
        return {rel: status.get(rel, PRISTINE) for rel in protected}

    shipped = baseline["files"]
    result = {}
    for rel, entry in protected.items():
        reference = shipped.get(rel)
        if reference is None:
            result[rel] = ADDED
        elif entry["sha256"] is None or reference.get("sha256") is None:
            # 超大檔沒算 sha——退回比 size，講不出細節但抓得到明顯的換檔
            result[rel] = (PRISTINE if entry["size"] == reference.get("size")
                           else MODIFIED)
        else:
            result[rel] = (PRISTINE if entry["sha256"] == reference["sha256"]
                           else MODIFIED)
    return result


def unlisted_changes(root=".", protected=None):
    """有異動、卻**不屬於任何已知分區**的檔案——保護清單該不該補的訊號。

    這是把「清單是完整的」這個前提變成每次 check 都驗的不變式
    （寫法抄 graph_status.untracked_graph_sources()）。

    注意判準是「分區歸屬」而不是「有沒有進保護清單」。第一版寫成後者，
    結果是這個不變式**永遠不可能觸發**：`collect_protected()` 與本函式套用同一份
    `UPSTREAM_EXCLUDE`，兩邊依建構方式就不可能不一致——一個只會回綠燈的關卡
    等於沒有關卡。真正會漏保護的情形是**資料區之外冒出新的產物目錄**
    （例如日後有工具開始寫 `reports/`），那才是需要有人來分類的東西。

    已知的上游分區不列入，否則維護者改 tools/、skills/、tests/ 會天天紅燈，
    而天天紅燈的關卡沒有人會看。
    """
    baseline = git_baseline(root)
    if baseline is None:
        return []
    stray = set()
    for rel in baseline["status"]:
        head = rel.split("/", 1)[0]
        if head in DATA_ZONES or rel in ROOT_FILES:
            continue  # 資料區內：不是進了保護清單，就是明確列為上游正典
        if head in UPSTREAM_ZONES or rel in UPSTREAM_ROOT_FILES:
            continue
        if matches_any(rel, UPSTREAM_EXCLUDE):
            continue
        stray.add(rel)
    return sorted(stray)


# ---------------------------------------------------------------------------
# 備份庫
# ---------------------------------------------------------------------------

def home_index_path():
    return Path.home() / INDEX_RELPATH


def read_index():
    path = home_index_path()
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "backups": []}
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"schema_version": SCHEMA_VERSION, "backups": []}
    if not isinstance(doc, dict) or not isinstance(doc.get("backups"), list):
        return {"schema_version": SCHEMA_VERSION, "backups": []}
    return doc


def record_in_index(manifest, zip_path):
    """索引只記路徑與時間——真正的內容在 zip 裡。

    索引存在的唯一理由：使用者重裝到**別的位置**之後，新目錄要找得回舊備份。
    所以它不能跟著倉庫一起被刪，只能放家目錄。寫不進去不算失敗（唯讀家目錄、
    受限沙盒都可能），備份本體已經落地了。
    """
    doc = read_index()
    doc["backups"] = [b for b in doc["backups"] if b.get("path") != str(zip_path)]
    doc["backups"].append({
        "path": str(zip_path),
        "repo_name": manifest["repo_name"],
        "repo_path": manifest["repo_path"],
        "created_at": manifest["created_at"],
        "note": manifest.get("note"),
        "entry_count": len(manifest["entries"]),
    })
    doc["backups"].sort(key=lambda b: b.get("created_at") or "")
    try:
        path = home_index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError:
        return False
    return True


def read_backup_manifest(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("manifest.json") as f:
                doc = json.load(f)
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) and "entries" in doc else None


def backup_candidates(root="."):
    """本倉庫的備份：同層目錄掃出來的，加上家目錄索引記得的。"""
    root = Path(root).resolve()
    found = {}
    for path in sorted(root.parent.glob(f"{root.name}{BACKUP_MARKER}*.zip")):
        found[str(path)] = path
    for record in read_index()["backups"]:
        if record.get("repo_name") != root.name:
            continue
        path = Path(record["path"])
        if path.is_file():
            found[str(path)] = path
    return [found[key] for key in sorted(found)]


def list_backups(root="."):
    result = []
    for path in backup_candidates(root):
        manifest = read_backup_manifest(path)
        if manifest is None:
            continue
        result.append({"path": str(path.resolve()), "manifest": manifest})
    result.sort(key=lambda b: b["manifest"].get("created_at") or "")
    return result


def latest_backup(root=".", same_repo_only=True):
    root = Path(root).resolve()
    backups = list_backups(root)
    if same_repo_only:
        backups = [b for b in backups
                   if b["manifest"].get("repo_path") == str(root)]
    return backups[-1] if backups else None


def resolve_backup(root=".", backup_id=None):
    """`--backup` 接受完整路徑或檔名片段；省略就取最近一次。"""
    if backup_id is None:
        return latest_backup(root)
    for record in list_backups(root):
        if backup_id in record["path"]:
            return record
    return None


# ---------------------------------------------------------------------------
# 診斷
# ---------------------------------------------------------------------------

def detect_loss(root, protected, status, backup):
    """備份裡的成果，現在不見了或被還原成上游版本。

    這是 `git status` 答不出來的那一類：破壞發生後工作目錄一片乾淨，
    只有備份 manifest 還記得「這個檔案曾經是使用者的版本」。
    """
    if backup is None:
        return []
    lost = []
    for rel, entry in backup["manifest"]["entries"].items():
        if entry.get("upstream") == PRISTINE:
            continue  # 當初就是上游原樣，現在還是上游原樣不代表出事
        current = protected.get(rel)
        if current is None:
            lost.append({"path": rel, "reason": "檔案已不存在",
                         "owner": entry.get("owner", USER)})
        elif (current["sha256"] != entry.get("sha256")
              and status.get(rel) == PRISTINE):
            lost.append({"path": rel, "reason": "內容被還原成上游版本",
                         "owner": entry.get("owner", USER)})
    return sorted(lost, key=lambda item: item["path"])


def drift_against(protected, backup):
    """現況與備份的差異。"""
    if backup is None:
        return {"added": [], "changed": [], "removed": []}
    entries = backup["manifest"]["entries"]
    added = [rel for rel in protected if rel not in entries]
    removed = [rel for rel in entries if rel not in protected]
    changed = [rel for rel, entry in protected.items()
               if rel in entries and entry["sha256"] != entries[rel].get("sha256")]
    return {"added": sorted(added), "changed": sorted(changed),
            "removed": sorted(removed)}


def evaluate(root="."):
    root_path = Path(root).resolve()
    protected = collect_protected(root)
    baseline = resolve_baseline(root)
    status = classify(protected, baseline)
    backup = latest_backup(root)
    unlisted = unlisted_changes(root, protected)

    local = sorted(rel for rel, state in status.items()
                   if state in (MODIFIED, ADDED))
    lost = detect_loss(root, protected, status, backup)
    drift = drift_against(protected, backup)
    foreign = [b for b in list_backups(root)
               if b["manifest"].get("repo_path") != str(root_path)]

    if lost:
        state = "suspected_loss"
    elif not local and foreign and backup is None:
        state = "foreign_backup"
    elif unlisted:
        state = "unlisted"
    elif baseline is None and backup is None:
        state = "unknown"
    elif not local:
        state = "no_local_data"
    elif backup is None:
        state = "unprotected"
    elif drift["added"] or drift["changed"] or drift["removed"]:
        state = "drifted"
    else:
        state = "protected"

    return {
        "state": state,
        "repo_path": str(root_path),
        "baseline": baseline["kind"] if baseline else None,
        "protected_count": len(protected),
        "local_count": len(local),
        "local": local,
        "lost": lost,
        "drift": drift,
        "unlisted": unlisted,
        "backup": ({"path": backup["path"],
                    "created_at": backup["manifest"].get("created_at"),
                    "note": backup["manifest"].get("note")} if backup else None),
        "foreign_backups": [b["path"] for b in foreign],
        "backup_hint": str(default_backup_path(root)),
    }


def display_time(value):
    """created_at 帶微秒是為了排序；給人看的時候截到秒就好。"""
    return (value or "").split(".")[0] or "—"


def format_check(result):
    state = result["state"]
    lines = []

    def listing(paths, label, limit=10):
        for path in paths[:limit]:
            lines.append(f"  [{label}] {path}")
        if len(paths) > limit:
            lines.append(f"  …… 另有 {len(paths) - limit} 項")

    if state == "no_local_data":
        lines.append("✅ 這份倉庫還沒有你的本機成果——更新不會蓋掉任何東西")
        return "\n".join(lines)

    if state == "protected":
        backup = result["backup"]
        lines.append(f"✅ {result['local_count']} 件本機成果已備份，內容一致")
        lines.append(f"  備份：{backup['path']}（{display_time(backup['created_at'])}）")
        return "\n".join(lines)

    if state == "suspected_loss":
        lines.append(f"⛔ 疑似成果遺失 —— {len(result['lost'])} 件本機成果不見了或被還原成上游版本")
        for item in result["lost"][:10]:
            lines.append(f"  [{item['reason']}] {item['path']}")
        if len(result["lost"]) > 10:
            lines.append(f"  …… 另有 {len(result['lost']) - 10} 項")
        lines.append("→ **先不要再跑任何 git 命令**。依 skills/safe-update.md 的救援程序：")
        lines.append("   python3 tools/update_guard.py snapshot --note \"救援前現況\"")
        lines.append("   python3 tools/update_guard.py diff")
        lines.append("   python3 tools/update_guard.py restore --path {逐項確認}")
        return "\n".join(lines)

    if state == "foreign_backup":
        lines.append("⛔ 這份倉庫是全新的，但這台電腦有你先前的成果備份")
        for path in result["foreign_backups"][:5]:
            lines.append(f"  [備份] {path}")
        lines.append("→ 這通常代表倉庫被重新下載或重裝過。先確認要不要把成果救回來：")
        lines.append("   python3 tools/update_guard.py diff --backup {上面的路徑}")
        return "\n".join(lines)

    if state == "unlisted":
        lines.append("⚪ 保護清單需複核 —— 下列檔案有異動，但不屬於任何已知分區，"
                     "備份可能會漏掉它們")
        listing(result["unlisted"], "未分類")
        lines.append("→ 若是使用者產物，把它的目錄加進 tools/update_guard.py 的 "
                     "DATA_ZONES 與 OWNER_RULES；")
        lines.append("  若是上游檔案，加進 UPSTREAM_ZONES／UPSTREAM_ROOT_FILES；"
                     "若是暫存檔，加進 .gitignore。")
        return "\n".join(lines)

    if state == "unknown":
        lines.append("⚪ 無法判斷 —— 這份倉庫沒有 git 紀錄、沒有安裝清單，也沒有備份")
        lines.append(f"  保護範圍內有 {result['protected_count']} 個檔案，"
                     "但分不出哪些是上游正典、哪些是你的成果")
        lines.append("→ 建議先做一次備份，之後才有比較基準：")
        lines.append("   python3 tools/update_guard.py snapshot")
        return "\n".join(lines)

    if state == "unprotected":
        lines.append(f"⚪ 尚未備份 —— 你有 {result['local_count']} 件本機成果從未備份過")
        listing(result["local"], "本機成果")
        lines.append("→ 更新倉庫前請先備份（會寫到倉庫外，需你同意）：")
        lines.append("   python3 tools/update_guard.py snapshot --note \"更新前\"")
        return "\n".join(lines)

    drift = result["drift"]
    total = sum(len(v) for v in drift.values())
    backup = result["backup"]
    lines.append(f"⚪ 備份已過期 —— 自 {display_time(backup['created_at'])} 備份後有 {total} 件變動")
    for label, key in (("新增", "added"), ("變更", "changed"), ("刪除", "removed")):
        listing(drift[key], label, limit=5)
    lines.append(f"  上次備份：{backup['path']}")
    lines.append("→ 更新倉庫前請重新備份：python3 tools/update_guard.py snapshot --note \"更新前\"")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def timestamp(now=None):
    """精確到秒，不是到分。

    只到分鐘會讓同一分鐘內的兩次備份撞名而互相覆蓋——`restore` 內建的
    pre-restore 備份正好緊接在還原前發生，開發時就真的把「要還原的那份備份」
    蓋掉了。一個以防止資料遺失為職責的工具自己造成資料遺失，不能只靠測試補，
    檔名本身就得是唯一的。
    """
    return (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")


def default_backup_path(root=".", now=None):
    root = Path(root).resolve()
    base = f"{root.name}{BACKUP_MARKER}{timestamp(now)}"
    candidate = root.parent / f"{base}.zip"
    serial = 2
    while candidate.exists():  # 同秒內也可能撞——備份絕不覆蓋既有檔
        candidate = root.parent / f"{base}-{serial}.zip"
        serial += 1
    return candidate


def build_entries(root):
    protected = collect_protected(root)
    baseline = resolve_baseline(root)
    status = classify(protected, baseline)
    entries = {}
    for rel, entry in protected.items():
        entries[rel] = dict(entry, upstream=status.get(rel, UNKNOWN))
    return entries


def snapshot(root=".", note=None, dest=None, now=None, force=False):
    """備份保護範圍內的成果到倉庫外的單一 zip。

    只存**與上游不同或使用者新增**的檔案內容——上游原樣的檔案從上游本來就拿得回來，
    照抄一份只會讓每次備份多背十幾 MB 的法規 PDF，使用者反而不敢常備份。
    判不出上游狀態（`unknown`）時一律存內容：正確性優先於體積。
    """
    root_path = Path(root).resolve()
    entries = build_entries(root)
    previous = latest_backup(root)

    if not force and previous is not None:
        if previous["manifest"].get("entries") == entries:
            return {"skipped": True, "path": previous["path"],
                    "reason": "內容與上次備份完全相同", "entry_count": len(entries)}

    zip_path = Path(dest).resolve() if dest else default_backup_path(root, now)
    if zip_path.resolve().is_relative_to(root_path):
        raise ValueError(
            f"備份不得寫進倉庫內（{zip_path}）——git clean -fdx 與重裝都會把它一起帶走")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "note": note,
        # 微秒精度不是為了好看，是為了排序：同一秒內的兩份備份若 created_at 相同，
        # 「最近一次」就變成任意的，而 restore／check 都靠它挑基準。
        "created_at": datetime.datetime.now().isoformat(timespec="microseconds"),
        "repo_path": str(root_path),
        "repo_name": root_path.name,
        "tool": "tools/update_guard.py",
        "git": git_summary(root),
        "install_version": (load_manifest(root) or {}).get("version"),
        "entries": entries,
    }

    stored = []
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for rel, entry in entries.items():
            if entry["upstream"] == PRISTINE:
                continue
            zf.write(root_path / rel, f"files/{rel}")
            stored.append(rel)

    indexed = record_in_index(manifest, zip_path)
    return {"skipped": False, "path": str(zip_path), "entry_count": len(entries),
            "stored_count": len(stored), "indexed": indexed, "note": note}


def git_summary(root):
    head = run_git(root, ["rev-parse", "HEAD"])
    if head is None:
        return None
    remote = run_git(root, ["config", "--get", "remote.origin.url"])
    return {"available": True, "head": head.strip(),
            "reference": git_reference(root),
            "remote": remote.strip() if remote else None}


# ---------------------------------------------------------------------------
# diff / restore
# ---------------------------------------------------------------------------

def compare(root=".", backup=None):
    """備份 vs 現況，逐檔分類。"""
    protected = collect_protected(root)
    entries = backup["manifest"]["entries"]
    result = {"missing": [], "changed": [], "added": [], "same": []}
    for rel, entry in sorted(entries.items()):
        current = protected.get(rel)
        item = {"path": rel, "owner": entry.get("owner", USER),
                "upstream": entry.get("upstream", UNKNOWN),
                "restorable": entry.get("upstream") != PRISTINE}
        if current is None:
            result["missing"].append(item)
        elif current["sha256"] != entry.get("sha256"):
            result["changed"].append(item)
        else:
            result["same"].append(item)
    for rel in sorted(protected):
        if rel not in entries:
            result["added"].append({"path": rel, "owner": owner_for(rel)})
    return result


def format_diff(root, backup, result):
    manifest = backup["manifest"]
    lines = [f"備份：{backup['path']}",
             f"時間：{display_time(manifest.get('created_at'))}"
             + (f"（{manifest['note']}）" if manifest.get("note") else ""),
             f"倉庫：{Path(root).resolve()}", ""]
    labels = (("missing", "備份裡有、現在不見了"), ("changed", "內容不同"),
              ("added", "備份之後才新增的"))
    for key, label in labels:
        items = result[key]
        lines.append(f"{label}：{len(items)} 項")
        for item in items[:20]:
            tag = "" if item.get("restorable", True) else "（上游原樣，備份未存內容）"
            shared = "（共編檔，restore 需 --force-shared）" if item["owner"] == SHARED else ""
            lines.append(f"  · {item['path']}{tag}{shared}")
        if len(items) > 20:
            lines.append(f"  …… 另有 {len(items) - 20} 項")
    lines.append(f"未變動：{len(result['same'])} 項")
    return "\n".join(lines)


def restore(root=".", backup=None, paths=(), force_shared=False, dry_run=True,
            now=None):
    """從備份救回檔案。

    兩道護欄：
    1. **先備份現況**——救援本身就是覆蓋，現況比備份新是很常見的事。
    2. **`shared` 檔預設拒絕**——`rules/*.json` 是使用者裁示與上游修法交錯的檔案，
       整檔蓋回舊版會把上游的法規更新一起吃掉。
    """
    root_path = Path(root).resolve()
    entries = backup["manifest"]["entries"]
    targets = list(paths) if paths else [
        rel for rel, entry in entries.items() if entry.get("upstream") != PRISTINE]

    planned, refused, unavailable = [], [], []
    for rel in sorted(set(targets)):
        entry = entries.get(rel)
        if entry is None:
            unavailable.append({"path": rel, "reason": "備份裡沒有這個檔案"})
        elif entry.get("upstream") == PRISTINE:
            unavailable.append({"path": rel, "reason": "備份當下就是上游原樣，未存內容"})
        elif entry.get("owner") == SHARED and not force_shared:
            refused.append({"path": rel,
                            "reason": "共編檔——整檔還原會把上游的法規更新一起蓋掉，"
                                      "請改用 diff 列差異後重跑先紅再綠或逐則裁示"})
        else:
            planned.append(rel)

    result = {"dry_run": dry_run, "planned": planned, "refused": refused,
              "unavailable": unavailable, "restored": [], "pre_restore": None}
    if dry_run or not planned:
        return result

    result["pre_restore"] = snapshot(root, note="救援前現況", now=now, force=True)
    if Path(result["pre_restore"]["path"]).resolve() == Path(backup["path"]).resolve():
        raise RuntimeError(
            "救援前備份撞到了要還原的那份備份——中止，以免把來源蓋掉")
    with zipfile.ZipFile(backup["path"]) as zf:
        for rel in planned:
            target = root_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(f"files/{rel}") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            result["restored"].append(rel)
    return result


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

def commit(root=".", by=None):
    """把本機成果送進 git object database。

    價值在於**改變可逆性**：未提交的改動被 `git checkout --` 蓋掉是永久消失
    （那些內容從來沒進過 object database）；已提交的則 reflog 救得回。
    一個子命令換掉一整類不可逆風險。
    """
    if git_reference(root) is None:
        return {"ok": False, "reason": "這份倉庫沒有 git 紀錄（線2 安裝包就是這樣），"
                                       "改用 snapshot 備份"}
    zones = [zone for zone in DATA_ZONES if (Path(root) / zone).exists()]
    zones += [name for name in ROOT_FILES if (Path(root) / name).is_file()]
    if run_git(root, ["add", "-A", "--", *zones]) is None:
        return {"ok": False, "reason": "git add 失敗"}
    staged = run_git(root, ["diff", "--cached", "--name-only", "-z", "--", *zones])
    changed = sorted(filter(None, (staged or "").split("\0")))
    if not changed:
        return {"ok": True, "committed": False, "changed": [],
                "reason": "沒有待提交的本機成果"}
    stamp = datetime.date.today().isoformat()
    message = f"本機成果存檔 {stamp}"
    if by:
        message += f"（{by}）"
    if run_git(root, ["commit", "-m", message]) is None:
        return {"ok": False, "reason": "git commit 失敗（可能未設定 user.name／user.email）"}
    return {"ok": True, "committed": True, "changed": changed, "message": message}


# ---------------------------------------------------------------------------
# install（線2 升級）
# ---------------------------------------------------------------------------

def install(root=".", source=None, by=None, dry_run=False, now=None):
    """把新版安裝到既有目錄，保住使用者改過的檔案。

    逐檔四種處置（依舊 `安裝清單.json` 判定）：
      · 不在保護範圍          → 直接更新（工具、skill、文件都是上游的）
      · 在範圍內且未改過      → 直接更新
      · 在範圍內且**改過**    → 保住原檔，新版另存 `.上游新版` 供比對
      · 不在舊清單（使用者新增）→ 完全不動

    第三種是本函式的重點：不問就覆蓋等於抹掉成果，不問就跳過等於他永遠拿不到
    上游的修法。兩份都留著、把選擇權交回給他，才是唯一誠實的做法。
    """
    root_path = Path(root).resolve()
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError(f"找不到新版來源目錄：{source_path}")

    old_manifest = load_manifest(root) or {"files": {}}
    shipped = old_manifest.get("files", {})
    protected_now = collect_protected(root)

    plan = {"updated": [], "preserved": [], "untouched": [], "new": []}
    for path in sorted(source_path.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(source_path).as_posix()
        target = root_path / rel
        if not target.exists():
            plan["new"].append(rel)
        elif rel not in protected_now:
            plan["updated"].append(rel)
        elif rel in shipped and protected_now[rel]["sha256"] == shipped[rel].get("sha256"):
            plan["updated"].append(rel)
        else:
            plan["preserved"].append(rel)

    result = {"dry_run": dry_run, "plan": plan, "source": str(source_path),
              "snapshot": None, "report": None}
    if dry_run:
        return result

    result["snapshot"] = snapshot(root, note="安裝新版前", now=now, force=True)

    for rel in plan["new"] + plan["updated"]:
        target = root_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path / rel, target)
    for rel in plan["preserved"]:
        target = root_path / (rel + UPSTREAM_SUFFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path / rel, target)

    new_manifest = source_path / MANIFEST_NAME
    if new_manifest.is_file():
        shutil.copy2(new_manifest, root_path / MANIFEST_NAME)

    result["report"] = write_install_report(root_path, result, by=by, now=now)
    return result


def write_install_report(root_path, result, by=None, now=None):
    plan = result["plan"]
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d")
    path = root_path / f"{REPORT_PREFIX}{stamp}.txt"
    lines = [
        "Fire Review 更新報告",
        f"時間：{datetime.datetime.now().isoformat(timespec='seconds')}",
        f"執行者：{by or '安裝程式'}",
        "",
        f"更新前的備份：{(result.get('snapshot') or {}).get('path', '（無）')}",
        "  這個備份在倉庫外，更新與重裝都動不到它。",
        "",
        f"■ 保留了你的版本（共 {len(plan['preserved'])} 個檔案）",
        "  這些檔案你改過，所以沒有被覆蓋。上游的新版放在同名檔加上"
        f" 「{UPSTREAM_SUFFIX}」的檔案裡，你可以逐一比對後決定要不要採用。",
    ]
    lines += [f"    · {rel}  →  {rel}{UPSTREAM_SUFFIX}" for rel in plan["preserved"]] or ["    （無）"]
    lines += [
        "",
        f"■ 已更新到新版（共 {len(plan['updated']) + len(plan['new'])} 個檔案）",
        "  這些檔案你沒有改過，或本來就不屬於你的成果，已直接換成新版。",
        "",
        "■ 完全沒有被動到",
        "  你自己新增的檔案（案件圖面、實務見解、訓練素材）安裝程式一律不碰。",
        "",
        "下一步：",
        "  1. 跑一次開場診斷確認狀態（雙擊「開場診斷.bat」，或在終端機執行）",
        "       python3 tools/onboarding.py status",
        "  2. 逐一處理上面列出的 .上游新版 檔案",
        "  3. 規則庫如有變動，跑 python3 tools/fire_code_calc.py run-tests --strict",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_check(args):
    result = evaluate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_check(result))
    return EXIT_CODES[result["state"]]


def cmd_list(args):
    backups = list_backups(args.root)
    if args.format == "json":
        print(json.dumps(backups, ensure_ascii=False, indent=2))
        return 0
    if not backups:
        print("尚無備份。")
        print(f"→ 做第一次備份：python3 tools/update_guard.py snapshot")
        print(f"  會寫到：{default_backup_path(args.root)}")
        return 0
    print(f"共 {len(backups)} 份備份（新的在後）：")
    for record in backups:
        manifest = record["manifest"]
        note = f"｜{manifest['note']}" if manifest.get("note") else ""
        print(f"  {display_time(manifest.get('created_at'))}  "
              f"{len(manifest['entries'])} 件{note}")
        print(f"    {record['path']}")
    return 0


def cmd_snapshot(args):
    result = snapshot(args.root, note=args.note, dest=args.dest)
    if result["skipped"]:
        print(f"✅ 不必重複備份——{result['reason']}")
        print(f"  現有備份：{result['path']}")
        return 0
    print(f"✅ 已備份保護範圍內的 {result['entry_count']} 個檔案"
          f"（其中 {result['stored_count']} 個是你的成果，存了完整內容；"
          f"其餘與上游相同，從上游本來就拿得回來）")
    print(f"  {result['path']}")
    print("  這個檔案在倉庫外，更新、重裝、git clean 都動不到它。")
    if not result["indexed"]:
        print("  （家目錄索引寫入失敗——備份本體沒問題，但換目錄後要自己記得這個路徑）")
    return 0


def cmd_diff(args):
    backup = resolve_backup(args.root, args.backup)
    if backup is None:
        print("找不到可比對的備份。", file=sys.stderr)
        return 3
    result = compare(args.root, backup)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_diff(args.root, backup, result))
    return 0


def cmd_restore(args):
    backup = resolve_backup(args.root, args.backup)
    if backup is None:
        print("找不到可還原的備份。", file=sys.stderr)
        return 3
    if not args.path and not args.all:
        print("請指定 --path {路徑}（可重複）或 --all。", file=sys.stderr)
        return 2
    result = restore(args.root, backup, paths=args.path,
                     force_shared=args.force_shared, dry_run=not args.apply)
    for item in result["refused"]:
        print(f"⛔ 拒絕還原 {item['path']}：{item['reason']}")
    for item in result["unavailable"]:
        print(f"—  略過 {item['path']}：{item['reason']}")
    if result["dry_run"]:
        print(f"\n預演：會還原 {len(result['planned'])} 個檔案（加 --apply 才真的寫入）")
        for rel in result["planned"]:
            print(f"  · {rel}")
        return 0
    print(f"\n✅ 已還原 {len(result['restored'])} 個檔案")
    if result["pre_restore"]:
        print(f"  還原前的現況已備份到：{result['pre_restore']['path']}")
    return 0


def cmd_commit(args):
    result = commit(args.root, by=args.by)
    if not result["ok"]:
        print(f"⛔ {result['reason']}", file=sys.stderr)
        return 2
    if not result["committed"]:
        print(f"✅ {result['reason']}")
        return 0
    print(f"✅ 已提交 {len(result['changed'])} 個檔案：{result['message']}")
    print("  這些改動現在進了 git object database——就算被還原也能用 reflog 救回。")
    return 0


def cmd_install(args):
    result = install(args.root, source=args.source, by=args.by, dry_run=args.dry_run)
    plan = result["plan"]
    print(f"更新：{len(plan['updated'])} 個檔案")
    print(f"新增：{len(plan['new'])} 個檔案")
    print(f"保留你的版本：{len(plan['preserved'])} 個檔案")
    for rel in plan["preserved"]:
        print(f"  · {rel}（新版在 {rel}{UPSTREAM_SUFFIX}）")
    if result["dry_run"]:
        print("\n（預演，未寫入任何檔案）")
        return 0
    print(f"\n更新前備份：{result['snapshot']['path']}")
    print(f"更新報告：{result['report']}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="本機成果守門：更新倉庫前確認訓練成果不會被蓋掉")
    p.add_argument("--root", default=".", help="倉庫根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check", help="診斷（0=安全 2=備份過期/清單需複核 3=尚未備份 4=疑似遺失）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("list", help="列出備份（含絕對路徑）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("snapshot", help="備份本機成果到倉庫外")
    s.add_argument("--note", help="這次備份的事由，例如「更新前」")
    s.add_argument("--dest", help="自訂備份檔路徑（必須在倉庫外）")
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("diff", help="比對備份與現況")
    s.add_argument("--backup", help="備份路徑或檔名片段（預設取最近一次）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("restore", help="從備份救回檔案（預設預演，加 --apply 才寫入）")
    s.add_argument("--backup", help="備份路徑或檔名片段（預設取最近一次）")
    s.add_argument("--path", action="append", default=[], help="要還原的路徑（可重複）")
    s.add_argument("--all", action="store_true", help="還原備份裡的全部本機成果")
    s.add_argument("--apply", action="store_true", help="真的寫入（預設只預演）")
    s.add_argument("--force-shared", action="store_true",
                   help="連共編檔（rules/、graphify-out/）也整檔還原——"
                        "會把上游的法規更新一起蓋掉，非必要不要用")
    s.set_defaults(func=cmd_restore)

    s = sub.add_parser("commit", help="把本機成果送進 git object database")
    s.add_argument("--by", help="操作人")
    s.set_defaults(func=cmd_commit)

    s = sub.add_parser("install", help="安裝新版到既有目錄（線2 升級）")
    s.add_argument("--from", dest="source", required=True, help="新版解壓後的目錄")
    s.add_argument("--by", help="操作人")
    s.add_argument("--dry-run", action="store_true", help="只列處置計畫，不寫入")
    s.set_defaults(func=cmd_install)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
