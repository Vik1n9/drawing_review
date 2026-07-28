#!/usr/bin/env python3
"""訓練模式歸檔工具：把 training/inbox/ 的訓練素材確定性歸類到既有正典位置。

只用 Python 標準庫。

    python3 tools/training_intake.py classify                 # 乾跑，只印路由建議，不動任何檔案
    python3 tools/training_intake.py apply --batch {批次名} --operator {歸檔人}
    python3 tools/training_intake.py status                   # 供工作流程前置檢查（0=可續行 2=圖譜需補建）

設計邊界（呼應 AGENTS.md 底線 1 與 skills/red-green.md）：

- 本工具**只搬檔案、不做法規判斷**。分類只看副檔名、檔名樣式與輕量內容探測，
  信心不足一律標 needs_confirmation 交人工確認。
- 本工具**拒絕**寫入規則庫與判斷筆記（equipment_rules.json / mixed_use_rules.json /
  rule_tests.json / review_corrections.md 等）。法規參數入庫一律走 skills/red-green.md
  的 RED → Verify RED → GREEN → Verify GREEN；回饋筆記依 review_corrections.md 既有格式
  由人工確認後追加。
- 歸檔目的地一律是既有正典位置，既有工具（fire_code_calc / regulation_index /
  stage_report_xlsx）零修改即可吃到訓練結果；training/ 只保存原始素材副本與歸檔紀錄。
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

try:  # 以 tools.training_intake 匯入（測試）
    from tools import graph_status
except ImportError:  # 以 python3 tools/training_intake.py 執行（sys.path[0] = tools/）
    import graph_status

TRAINING_DIR = "training"
INBOX_DIR = "training/inbox"
REGISTRY_PATH = "training/registry.json"
GRAPH_PENDING_PATH = "training/graph_pending.json"

REGULATION_DIR = "rules/core"
CHECKLIST_DIR = "rules/checklists"
CORRECTIONS_PATH = "rules/review_corrections.md"
RULE_DOCS = ("rules/equipment_rules.json", "rules/mixed_use_rules.json")
PRACTICE_STAGING_DIR = "practice_notes/staging"
PRACTICE_INDEX_PATH = "practice_notes/index.json"

# 訓練模式不得直接寫入的路徑：規則參數走先紅再綠，判斷筆記走人工確認，核定走 governance，
# 實務註解走 practice_note_engine 的「確認納入」關卡
FORBIDDEN_FILES = {
    "rules/equipment_rules.json",
    "rules/mixed_use_rules.json",
    "rules/rule_tests.json",
    "rules/article18_equipment_options.json",
    "rules/regulation_index.json",
    "rules/review_corrections.md",
    "rules/stage_two_judgment_rules.md",
}
FORBIDDEN_PREFIXES = ("rules/regulation_articles/", "governance/", "input/", "output/",
                      "practice_notes/active/")

ARTICLE_HEADING = re.compile(r"第\s*\d+(?:-\d+)?\s*條")
ARTICLE_ASSET_NAME = re.compile(r"article-\d+", re.IGNORECASE)
CHECKLIST_HINTS = ("判斷", "檢核", "14~31", "14-31")
FORMAT_HINTS = ("格式範本", "範本", "範例")
FEEDBACK_FIELDS = ("Error:", "Correction:")

TEXT_SUFFIXES = {".md", ".txt"}
PROBE_BYTES = 200_000


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_head(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(PROBE_BYTES)
    except OSError:
        return ""


def load_json_or_none(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def assets_dir(root):
    """找出法規附表圖資料夾；不存在或多於一個時回 None（交人工確認）。"""
    matches = sorted((Path(root) / REGULATION_DIR).glob("*_assets"))
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# 分類

def classify_file(path, root=".", batch_rel=None):
    """對單一素材產生路由建議。純確定性判定，不做任何法規解讀。"""
    path = Path(path)
    name = path.name
    suffix = path.suffix.lower()
    batch_rel = batch_rel or f"{TRAINING_DIR}/{{批次}}"

    def result(kind, destination, reason, needs_confirmation=False):
        return {
            "source_name": name,
            "source_path": path.as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "kind": kind,
            "destination": destination,
            "reason": reason,
            "needs_confirmation": needs_confirmation,
        }

    if suffix == ".json":
        doc = load_json_or_none(path)
        if isinstance(doc, dict) and {"ref_article", "judgment"} <= set(doc):
            return result(
                "practice-note", f"{PRACTICE_STAGING_DIR}/{name}",
                "含 ref_article／judgment 欄位 → 判為實務註解。進 staging/ 待使用者「確認納入」；"
                "套用一律走 tools/practice_note_engine.py conflict-check → apply，本工具不直接寫 active/",
            )

    if suffix in TEXT_SUFFIXES:
        text = read_text_head(path)
        if suffix == ".md" and len(ARTICLE_HEADING.findall(text)) >= 20:
            return result(
                "regulation-fulltext", f"{REGULATION_DIR}/{name}",
                f"Markdown 且偵測到 {len(ARTICLE_HEADING.findall(text))} 處條號 → 判為法規全文。"
                "⚠️ regulation_index.py build 會 glob rules/core/*.md，此資料夾必須維持單一全文 md，"
                "只能『替換』不能並存（見 rules/README.md）",
                needs_confirmation=True,
            )
        if all(field in text for field in FEEDBACK_FIELDS):
            return result(
                "case-feedback", f"{batch_rel}/sources/{name}",
                "含 Error:／Correction: 欄位 → 判為實案回饋筆記。"
                f"本工具不自動寫入 {CORRECTIONS_PATH}——須由 /train 第五步依既有筆記格式、"
                "經使用者確認後追加",
            )

    if suffix in (".png", ".jpg", ".jpeg", ".pdf") and ARTICLE_ASSET_NAME.search(name):
        target = assets_dir(root)
        if target is None:
            return result(
                "regulation-asset", f"{REGULATION_DIR}/（_assets 資料夾未定）/{name}",
                "檔名 match article-\\d+ → 判為法規附表圖，但 rules/core/ 下找不到唯一的 *_assets 資料夾",
                needs_confirmation=True,
            )
        return result(
            "regulation-asset", f"{target.relative_to(Path(root)).as_posix()}/{name}",
            "檔名 match article-\\d+ → 判為法規條文附表圖",
        )

    if suffix == ".xlsx":
        if any(hint in name for hint in FORMAT_HINTS):
            return result(
                "format-template", f"{batch_rel}/formats/{name}",
                "檔名含格式範本字樣 → 判為交付物格式範本（無既有正典位置，登錄到 registry.json 供工具查詢）",
            )
        if any(hint in name for hint in CHECKLIST_HINTS):
            return result(
                "judgment-checklist", f"{CHECKLIST_DIR}/{name}",
                "檔名含判斷／檢核字樣 → 判為 §14~31 實務判斷表",
            )
        return result(
            "unknown", f"{batch_rel}/sources/unclassified/{name}",
            "xlsx 但檔名無可辨識線索 → 需人工指定用途與目的地",
            needs_confirmation=True,
        )

    if suffix in (".pdf", ".docx", ".doc"):
        if any(hint in name for hint in FORMAT_HINTS):
            return result(
                "format-template", f"{batch_rel}/formats/{name}",
                "檔名含格式範本／範例字樣 → 判為交付物格式範本",
            )
        return result(
            "regulation-doc", f"{REGULATION_DIR}/{name}",
            "PDF/Word 文件 → 判為法規類文件（判斷基準本文、函釋、對照表等）",
            needs_confirmation=True,
        )

    return result(
        "unknown", f"{batch_rel}/sources/unclassified/{name}",
        f"無法由副檔名（{suffix or '無'}）與檔名判定類型 → 需人工指定",
        needs_confirmation=True,
    )


def classify_inbox(root=".", inbox=None, batch_rel=None):
    inbox = Path(root) / (inbox or INBOX_DIR)
    if not inbox.is_dir():
        return []
    files = sorted(p for p in inbox.rglob("*") if p.is_file() and p.name != ".gitkeep")
    return [classify_file(p, root=root, batch_rel=batch_rel) for p in files]


def check_destination(destination):
    """回傳阻擋原因；可歸檔則回 None。"""
    dest = Path(destination).as_posix()
    if dest in FORBIDDEN_FILES:
        return (f"目的地 {dest} 是規則庫／判斷筆記，訓練模式不得直接寫入——"
                "法規參數走先紅再綠（skills/red-green.md），判斷筆記由人工確認後追加")
    for prefix in FORBIDDEN_PREFIXES:
        if dest.startswith(prefix):
            return (f"目的地 {dest} 位於 {prefix}，訓練模式不得寫入"
                    "（逐條 JSON 由 regulation_index.py build 產生；"
                    "governance/ 由核定流程管理；input/ 只讀不改；output/ 為案件產出）")
    return None


# ---------------------------------------------------------------------------
# 歸檔

def load_registry(root="."):
    path = Path(root) / REGISTRY_PATH
    if not path.is_file():
        return {"schema_version": 1, "latest_batch": None, "batches": [],
                "assets": {"format_templates": []}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


NOTES_TEMPLATE = """# 訓練批次紀錄：{batch}

- 歸檔日期：{date}
- 歸檔人：{operator}
- 素材件數：{count}

## 歸檔內容

見 `manifest.json`（含每件素材的 sha256、分類理由與目的地）。

## 下游產物（逐項完成後回填，未完成請保留待辦標記）

- [ ] 法規索引重建：`python3 tools/regulation_index.py build`
- [ ] 新增測試（先紅再綠 RED）：`rules/rule_tests.json` 的測試 ID —— 待填
- [ ] 新增規則（GREEN）：`rules/equipment_rules.json` 的規則 ID —— 待填（一律 `verified: false`）
- [ ] 回饋筆記追加：`rules/review_corrections.md` / `rules/stage_two_judgment_rules.md` 的日期標題 —— 待填
- [ ] 訓練圖譜：`python3 tools/training_graph_build.py build`
- [ ] 法規圖譜（動到 rules/core/ 才需要）：`python3 tools/regulation_graph_build.py verify`
      → `rebuild --commit` → `python3 tools/graph_status.py stamp --graph regulation`
- [ ] 送核定：`python3 tools/verification_sheet.py export`

## 注意

本批次新增的規則參數一律 `verified: false`，未經消防專業人員核定不得作為審查依據。
引用 `review_corrections.md` / `stage_two_judgment_rules.md` 的結論必附
「本判斷慣例未經消防專業人員核定，以現行法規為準」。
"""


def apply_plan(items, batch, operator, root=".", batch_date=None, clear_inbox=False,
               confirm_all=False):
    """依確認後的路由表歸檔。回傳 (manifest, 錯誤訊息 list)。"""
    root = Path(root)
    batch_date = batch_date or date.today().isoformat()
    batch_name = f"{batch}-{batch_date.replace('-', '')}"
    batch_rel = f"{TRAINING_DIR}/{batch_name}"

    errors = []
    unconfirmed = []
    for item in items:
        blocked = check_destination(item["destination"])
        if blocked:
            errors.append(f"[{item['source_name']}] {blocked}")
        if item.get("needs_confirmation") and not (confirm_all or item.get("confirmed_by")):
            unconfirmed.append(f"[{item['source_name']}] {item['reason']}")
    if unconfirmed:
        errors.append("以下項目需人工確認路由後才可歸檔（嚴禁以推測歸檔）：\n  - "
                      + "\n  - ".join(unconfirmed))
    if errors:
        return None, errors

    batch_dir = root / batch_rel
    recorded = []
    for item in items:
        source = Path(item["source_path"])
        if not source.is_absolute():
            source = root / source
        # 原始素材不可變副本（追溯用）
        archive = batch_dir / "sources" / item["source_name"]
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, archive)

        destination = item["destination"].replace(f"{TRAINING_DIR}/{{批次}}", batch_rel)
        target = root / destination
        if target.resolve() != archive.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        recorded.append({
            "source_name": item["source_name"],
            "sha256": item["sha256"],
            "size": item["size"],
            "kind": item["kind"],
            "destination": Path(destination).as_posix(),
            "archived_copy": archive.relative_to(root).as_posix(),
            "reason": item["reason"],
            "confirmed_by": item.get("confirmed_by") or (operator if item.get("needs_confirmation") else "auto"),
        })

    manifest = {
        "schema_version": 1,
        "batch": batch_name,
        "created": batch_date,
        "operator": operator,
        "items": recorded,
        "downstream": {
            "regulation_index_rebuilt": False,
            "new_tests": [],
            "new_rules": [],
            "corrections_appended": [],
            "graph_rebuilt": False,
        },
        "unverified_notice": "本批次新增規則一律 verified: false，須走 governance 核定後方可作為審查依據。",
    }
    write_json(batch_dir / "manifest.json", manifest)
    (batch_dir / "NOTES.md").write_text(
        NOTES_TEMPLATE.format(batch=batch_name, date=batch_date, operator=operator,
                              count=len(recorded)),
        encoding="utf-8",
    )

    registry = load_registry(root)
    registry["batches"] = [b for b in registry.get("batches", []) if b.get("batch") != batch_name]
    registry["batches"].append({
        "batch": batch_name,
        "date": batch_date,
        "operator": operator,
        "path": batch_rel,
        "items": len(recorded),
        "kinds": sorted({r["kind"] for r in recorded}),
        "graph_rebuilt": False,
    })
    registry["batches"].sort(key=lambda b: (b.get("date", ""), b.get("batch", "")))
    registry["latest_batch"] = registry["batches"][-1]["batch"]
    templates = {t["path"]: t for t in registry.setdefault("assets", {}).setdefault("format_templates", [])}
    for r in recorded:
        if r["kind"] == "format-template":
            templates[r["destination"]] = {"name": r["source_name"], "path": r["destination"],
                                           "batch": batch_name}
    registry["assets"]["format_templates"] = sorted(templates.values(), key=lambda t: t["path"])
    write_json(root / REGISTRY_PATH, registry)

    if clear_inbox:
        for item in items:
            source = Path(item["source_path"])
            if not source.is_absolute():
                source = root / source
            if source.is_file():
                source.unlink()

    return manifest, []


# ---------------------------------------------------------------------------
# 狀態（工作流程前置檢查）

def count_active_corrections(root="."):
    path = Path(root) / CORRECTIONS_PATH
    if not path.is_file():
        return 0
    return len(re.findall(r"^\s*-\s*Status:\s*Active\s*$",
                          path.read_text(encoding="utf-8"), re.MULTILINE))


def count_unverified_rules(root="."):
    total = 0
    for rel in RULE_DOCS:
        path = Path(root) / rel
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        total += sum(1 for r in doc.get("rules", []) if not r.get("verified"))
    return total


def count_practice_notes(root="."):
    """回傳 (active 註解數, staging 待確認草案數)。"""
    index = load_json_or_none(Path(root) / PRACTICE_INDEX_PATH) or {}
    staging = Path(root) / PRACTICE_STAGING_DIR
    pending = len(list(staging.glob("*.json"))) if staging.is_dir() else 0
    return index.get("count", len(index.get("notes", []))), pending


def status(root="."):
    registry = load_registry(root)
    graph = graph_status.evaluate(root)
    pending = (Path(root) / GRAPH_PENDING_PATH).is_file()
    active_notes, staging_notes = count_practice_notes(root)
    return {
        "latest_batch": registry.get("latest_batch"),
        "batch_count": len(registry.get("batches", [])),
        "last_batch_date": registry["batches"][-1]["date"] if registry.get("batches") else None,
        "format_templates": registry.get("assets", {}).get("format_templates", []),
        "active_corrections": count_active_corrections(root),
        "unverified_rules": count_unverified_rules(root),
        "practice_notes_active": active_notes,
        "practice_notes_staging": staging_notes,
        "graph": graph,
        "graph_pending": pending,
        # 兩個圖譜都要跟上才算可續行——但它們各自獨立，訊息會分開講是哪一個卡住。
        "ready": graph["exit_code"] == 0 and not pending,
    }


def format_status(result):
    lines = ["== 訓練成果狀態（工作流程前置檢查）=="]
    if result["latest_batch"]:
        lines.append(f"最新訓練批次：{result['latest_batch']}"
                     f"（{result['last_batch_date']}，累計 {result['batch_count']} 批）")
    else:
        lines.append("最新訓練批次：尚無（training/registry.json 無紀錄）")
    lines.append(f"已確認修正筆記（Status: Active）：{result['active_corrections']} 則"
                 " —— 審圖前必讀 rules/review_corrections.md")
    lines.append(f"規則庫：{result['unverified_rules']} 條尚未逐條確認（verified: false）"
                 " —— 跑 python3 tools/verification_sheet.py list 列給使用者確認")
    notes_state = (result["graph"].get("notes") or {}).get("state", "covered")
    merged_mark = {"covered": "✅ 已納入訓練圖譜",
                   "not_built": "⚠️ 訓練圖譜尚未建置",
                   "absent": "⛔ 訓練圖譜尚未建置（查圖譜查不到）",
                   "uncovered": "⛔ 訓練圖譜未跟上（查圖譜查不到）"}
    mark = f"（{merged_mark.get(notes_state, notes_state)}）" if result["practice_notes_active"] else ""
    lines.append(f"實務註解（active）：{result['practice_notes_active']} 則{mark}"
                 " —— check-gap 會自動比對；引用時須同時列出所補充的法條與註解 ID")
    if result["practice_notes_staging"]:
        lines.append(f"⚠️ practice_notes/staging/ 有 {result['practice_notes_staging']} 則草案"
                     "未經使用者「確認納入」，尚未生效")
    for t in result["format_templates"]:
        lines.append(f"格式範本：{t['name']} → {t['path']}")

    graph = result["graph"]
    if graph["state"] == "fresh":
        lines.append(f"法規圖譜：✅ 新鮮（{graph['source_count']} 個來源檔，"
                     f"蓋章 {graph['stamped_at'] or '未記錄'}）")
    elif graph["state"] == "no_baseline":
        lines.append("法規圖譜：⚠️ 尚未建立指紋基準 —— 先確認圖譜為當前規則庫所建，"
                     "再跑 python3 tools/graph_status.py stamp --graph regulation")
    else:
        total = sum(len(v) for v in graph["diff"].values())
        lines.append(f"法規圖譜：⛔ 已過期（{total} 個來源檔異動）"
                     " —— 查圖譜會查到舊資料，續行前先補建")
        lines.append(f"  → {graph_status.REBUILD_HINT}")

    training = (graph.get("training") or {}).get("coverage") or {}
    if training.get("state") == "covered":
        lines.append(f"訓練圖譜：✅ 跟上（實務註解 {training['active']} 則、"
                     f"markdown 筆記 {training['entries']} 則）")
    elif training.get("state") == "not_built":
        lines.append(f"訓練圖譜：⚠️ 尚未建置（倉庫已有 {training['entries']} 則筆記可入圖譜）"
                     " —— python3 tools/training_graph_build.py build")
    elif training:
        lines.append("訓練圖譜：⛔ 未跟上素材 —— 審圖查圖譜會查不到這些訓練成果")
        lines.append(f"  → {graph_status.TRAINING_HINT}")

    if result["graph_pending"]:
        lines.append(f"⛔ 存在 {GRAPH_PENDING_PATH}：上次訓練的圖譜自動重建未完成，必須補建後刪除此旗標")

    lines.append("✅ 可續行後續工作流程" if result["ready"]
                 else "⛔ 有圖譜未跟上素材：依上方指示補建該圖譜後再續行"
                      "（兩個圖譜各自獨立，通常只需要更新其中一個）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 指令

def format_classify(items):
    if not items:
        return f"{INBOX_DIR}/ 沒有待歸檔素材。"
    lines = [f"== 路由建議（乾跑，未動任何檔案）：{len(items)} 件 =="]
    for i, item in enumerate(items, 1):
        mark = "⚠️ 需人工確認" if item["needs_confirmation"] else "✅ 可自動歸檔"
        lines.append(f"\n{i}. {item['source_name']}  [{item['kind']}]  {mark}")
        lines.append(f"   目的地：{item['destination']}")
        lines.append(f"   理由：{item['reason']}")
        lines.append(f"   sha256：{item['sha256'][:16]}…")
    need = sum(1 for i in items if i["needs_confirmation"])
    if need:
        lines.append(f"\n⚠️ {need} 件需人工確認：逐項與使用者確認後，"
                     "以 --plan 提供已填 confirmed_by 的路由表再執行 apply。")
    return "\n".join(lines)


def cmd_classify(args):
    items = classify_inbox(args.root, args.inbox)
    print(json.dumps(items, ensure_ascii=False, indent=2) if args.format == "json"
          else format_classify(items))
    return 0


def cmd_apply(args):
    if args.plan:
        with open(args.plan, encoding="utf-8") as f:
            plan = json.load(f)
        items = plan["items"] if isinstance(plan, dict) else plan
    else:
        items = classify_inbox(args.root, args.inbox)
    if not items:
        print(f"{args.inbox or INBOX_DIR}/ 沒有待歸檔素材，未建立批次。")
        return 0

    manifest, errors = apply_plan(
        items, args.batch, args.operator, root=args.root, batch_date=args.date,
        clear_inbox=args.clear_inbox, confirm_all=args.confirm_all,
    )
    if errors:
        print("⛔ 歸檔中止，未動任何檔案：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    batch_rel = f"{TRAINING_DIR}/{manifest['batch']}"
    print(f"✅ 已歸檔 {len(manifest['items'])} 件到批次 {manifest['batch']}")
    for r in manifest["items"]:
        print(f"  [{r['kind']}] {r['source_name']} → {r['destination']}")
    print(f"\n批次紀錄：{batch_rel}/manifest.json、{batch_rel}/NOTES.md")
    print("\n接續步驟（見 skills/training-mode.md）：")
    print("  1. rules/core/ 有變更 → python3 tools/regulation_index.py build")
    print("  2. 法規參數入庫 → 走 skills/red-green.md（RED → Verify RED → GREEN → Verify GREEN）")
    print("  3. 回饋筆記 → 依 rules/review_corrections.md 既有格式，經使用者確認後追加")
    print("  4. 更新圖譜（兩個各自獨立，先跑 graph_status.py check 看是哪一個）→ "
          "python3 tools/training_graph_build.py build；動到 rules/core/ 才需要 "
          "python3 tools/regulation_graph_build.py rebuild --commit → graph_status.py stamp")
    print("  5. 綠燈驗收 → python3 tools/fire_code_calc.py self-test && "
          "python3 tools/fire_code_calc.py run-tests --strict")
    return 0


def cmd_status(args):
    result = status(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_status(result))
    return 0 if result["ready"] else 2


def build_parser():
    p = argparse.ArgumentParser(description="訓練模式歸檔工具（素材自動歸類、訓練成果狀態）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("classify", help="乾跑：印出 inbox 素材的路由建議，不動任何檔案")
    s.add_argument("--inbox", default=None, help=f"投放資料夾（預設 {INBOX_DIR}）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_classify)

    s = sub.add_parser("apply", help="依確認後的路由表歸檔並建立訓練批次")
    s.add_argument("--batch", required=True, help="批次名（會自動附加 -YYYYMMDD）")
    s.add_argument("--operator", required=True, help="歸檔人（責任追溯，必填）")
    s.add_argument("--inbox", default=None)
    s.add_argument("--plan", default=None, help="已確認的路由表 JSON（classify --format json 的輸出加上 confirmed_by）")
    s.add_argument("--date", default=None, help="批次日期（預設今天）")
    s.add_argument("--clear-inbox", action="store_true", help="歸檔後清空 inbox 內已處理的素材")
    s.add_argument("--confirm-all", action="store_true",
                   help="把所有 needs_confirmation 項視為由 --operator 確認（僅供非互動批次；互動流程請逐項確認）")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("status", help="訓練成果狀態與圖譜新鮮度（0=可續行 2=圖譜需補建）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_status)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
