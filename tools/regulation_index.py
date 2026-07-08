#!/usr/bin/env python3
"""Build and query a lightweight fire-code article index.

The index intentionally stores only metadata and short snippets. Full article
text lives in one JSON file per article, so review workflows can load only the
legal basis relevant to a finding.
"""

import argparse
import json
import re
from pathlib import Path


ARTICLE_HEADING_RE = re.compile(r"^(#{2,6})\s*第\s*([0-9０-９]+(?:-[0-9０-９]+)?)\s*條\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
AMENDMENT_RE = re.compile(r"修正日期[：:]\s*(.+)")

EQUIPMENT_ALIASES = {
    "滅火器": ["滅火器", "消防砂"],
    "室內消防栓設備": ["室內消防栓", "室內消防栓設備"],
    "室外消防栓設備": ["室外消防栓", "室外消防栓設備"],
    "自動撒水設備": ["自動撒水", "撒水設備", "撒水頭", "補助撒水栓"],
    "水霧滅火設備": ["水霧滅火"],
    "泡沫滅火設備": ["泡沫滅火"],
    "二氧化碳滅火設備": ["二氧化碳"],
    "惰性氣體滅火設備": ["惰性氣體"],
    "鹵化烴滅火設備": ["鹵化烴"],
    "乾粉滅火設備": ["乾粉"],
    "火警自動警報設備": ["火警自動警報", "探測器", "偵煙式", "火焰式"],
    "手動報警設備": ["手動報警"],
    "緊急廣播設備": ["緊急廣播"],
    "瓦斯漏氣火警自動警報設備": ["瓦斯漏氣火警自動警報"],
    "一一九火災通報裝置": ["一一九火災通報", "119火災通報"],
    "標示設備": ["標示設備", "出口標示燈", "避難方向指示燈", "觀眾席引導燈", "避難指標"],
    "避難器具": ["避難器具", "避難梯", "緩降機", "救助袋", "滑臺", "避難橋", "避難繩索", "滑杆"],
    "緊急照明設備": ["緊急照明"],
    "連結送水管": ["連結送水管"],
    "消防專用蓄水池": ["消防專用蓄水池"],
    "排煙設備": ["排煙設備", "機械排煙", "防煙區劃"],
    "緊急電源插座": ["緊急電源插座"],
    "無線電通信輔助設備": ["無線電通信輔助"],
    "防災監控系統綜合操作裝置": ["防災監控系統綜合操作"],
}


def normalize_article_no(value):
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    value = str(value).translate(table)
    value = value.strip().removeprefix("§")
    value = value.replace("§", "").replace("第", "").replace("條", "")
    return re.sub(r"\s+", "", value)


def article_id(article_no):
    article_no = normalize_article_no(article_no)
    if "-" not in article_no and article_no.isdigit():
        return f"article-{int(article_no):03d}"
    return f"article-{article_no}"


def article_sort_key(article_no):
    parts = normalize_article_no(article_no).split("-")
    return tuple(int(p) if p.isdigit() else p for p in parts)


def compact_text(markdown, limit=180):
    text = re.sub(r"\s+", " ", markdown).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def detect_equipment_tags(markdown):
    tags = []
    for equipment, aliases in EQUIPMENT_ALIASES.items():
        if any(alias in markdown for alias in aliases):
            tags.append(equipment)
    return tags


def parse_regulation_markdown(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    law_name = ""
    version = ""
    hierarchy = {}
    articles = []
    current = None

    def flush_current():
        nonlocal current
        if current is None:
            return
        markdown = "\n".join(current.pop("body_lines")).strip()
        current["markdown"] = markdown
        current["snippet"] = compact_text(markdown)
        current["equipment_tags"] = detect_equipment_tags(current["title"] + "\n" + markdown)
        current["keywords"] = sorted(set(current["equipment_tags"] + current["hierarchy"]))
        articles.append(current)
        current = None

    for line in lines:
        heading = HEADING_RE.match(line)
        article_heading = ARTICLE_HEADING_RE.match(line)
        if heading and not article_heading:
            flush_current()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1 and not law_name:
                law_name = title
            elif level > 1:
                hierarchy[level] = title
                for key in list(hierarchy):
                    if key > level:
                        del hierarchy[key]

        amendment = AMENDMENT_RE.search(line)
        if amendment:
            version = amendment.group(1).strip()

        if article_heading:
            flush_current()
            level = len(article_heading.group(1))
            no = normalize_article_no(article_heading.group(2))
            current = {
                "id": article_id(no),
                "article_no": no,
                "legal_basis": f"§{no}",
                "title": f"第 {no} 條",
                "heading_level": level,
                "source_file": path.as_posix(),
                "hierarchy": [hierarchy[k] for k in sorted(hierarchy) if k < level],
                "body_lines": [],
            }
            continue

        if current is not None:
            current["body_lines"].append(line)

    flush_current()
    return law_name, version, articles


def build_regulation_index(source_dir, index_path, article_dir):
    source_dir = Path(source_dir)
    index_path = Path(index_path)
    article_dir = Path(article_dir)
    article_dir.mkdir(parents=True, exist_ok=True)
    for stale in article_dir.glob("article-*.json"):
        stale.unlink()

    all_articles = []
    regulation_name = ""
    regulation_version = ""
    for md_path in sorted(source_dir.glob("*.md")):
        name, version, articles = parse_regulation_markdown(md_path)
        regulation_name = regulation_name or name
        regulation_version = regulation_version or version
        all_articles.extend(articles)

    all_articles.sort(key=lambda item: article_sort_key(item["article_no"]))

    by_article = {}
    by_equipment = {}
    index_articles = []
    for article in all_articles:
        article["regulation"] = regulation_name
        article["regulation_version"] = regulation_version
        output_path = article_dir / f"{article['id']}.json"
        article["path"] = output_path.relative_to(index_path.parent).as_posix()
        output_path.write_text(
            json.dumps(article, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        by_article.setdefault(article["article_no"], []).append(article["id"])
        for tag in article["equipment_tags"]:
            by_equipment.setdefault(tag, []).append(article["id"])

        index_articles.append(
            {
                "id": article["id"],
                "article_no": article["article_no"],
                "legal_basis": article["legal_basis"],
                "title": article["title"],
                "path": article["path"],
                "source_file": article["source_file"],
                "hierarchy": article["hierarchy"],
                "equipment_tags": article["equipment_tags"],
                "keywords": article["keywords"],
                "snippet": article["snippet"],
            }
        )

    manifest = {
        "schema_version": 1,
        "regulation_name": regulation_name,
        "regulation_version": regulation_version,
        "source_dir": source_dir.as_posix(),
        "article_dir": article_dir.relative_to(index_path.parent).as_posix(),
        "article_count": len(index_articles),
        "articles": index_articles,
        "by_article": by_article,
        "by_equipment": by_equipment,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _load_index(index_path):
    index_path = Path(index_path)
    return index_path, json.loads(index_path.read_text(encoding="utf-8"))


def _article_ids_for_equipment(manifest, equipment):
    if not equipment:
        return set()
    exact = manifest["by_equipment"].get(equipment)
    if exact:
        return set(exact)
    matches = set()
    for canonical, aliases in EQUIPMENT_ALIASES.items():
        if equipment == canonical or equipment in aliases:
            matches.update(manifest["by_equipment"].get(canonical, []))
    return matches


def _article_ids_for_article_ref(manifest, article_ref):
    article_no = normalize_article_no(article_ref)
    exact = manifest["by_article"].get(article_no)
    if exact:
        return set(exact)

    compact = str(article_ref).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    compact = re.sub(r"\s+", "", compact)
    match = re.search(r"§?(\d+)(?:條)?[-~至到]§?(\d+)(?:條)?", compact)
    if not match:
        return set()

    start, end = int(match.group(1)), int(match.group(2))
    if end < start:
        return set()

    ids = set()
    for no in range(start, end + 1):
        ids.update(manifest["by_article"].get(str(no), []))
    return ids


def lookup_related_articles(index_path, article=None, equipment=None, keyword=None, limit=20):
    index_path, manifest = _load_index(index_path)
    wanted = set()

    if article:
        wanted.update(_article_ids_for_article_ref(manifest, article))

    wanted.update(_article_ids_for_equipment(manifest, equipment))

    if keyword:
        for item in manifest["articles"]:
            haystack = " ".join(
                [
                    item["title"],
                    item["legal_basis"],
                    item["snippet"],
                    " ".join(item["hierarchy"]),
                    " ".join(item["equipment_tags"]),
                    " ".join(item["keywords"]),
                ]
            )
            if keyword in haystack:
                wanted.add(item["id"])

    if not any([article, equipment, keyword]):
        wanted.update(item["id"] for item in manifest["articles"][:limit])

    by_id = {item["id"]: item for item in manifest["articles"]}
    selected = [by_id[i] for i in wanted if i in by_id]
    selected.sort(key=lambda item: article_sort_key(item["article_no"]))
    selected = selected[:limit]

    docs = []
    for item in selected:
        doc_path = index_path.parent / item["path"]
        docs.append(json.loads(doc_path.read_text(encoding="utf-8")))
    return docs


def build_parser():
    parser = argparse.ArgumentParser(description="法規 Markdown 逐條索引與查詢工具")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="將 rules/法規/*.md 轉為逐條 JSON 與索引")
    build.add_argument("--source-dir", default="rules/法規")
    build.add_argument("--index", default="rules/regulation_index.json")
    build.add_argument("--article-dir", default="rules/regulation_articles")

    lookup = sub.add_parser("lookup", help="按條號、設備或關鍵字載入相關條文")
    lookup.add_argument("--index", default="rules/regulation_index.json")
    lookup.add_argument("--article")
    lookup.add_argument("--equipment")
    lookup.add_argument("--keyword")
    lookup.add_argument("--limit", type=int, default=20)
    lookup.add_argument("--format", choices=["json", "markdown"], default="markdown")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "build":
        manifest = build_regulation_index(args.source_dir, args.index, args.article_dir)
        print(
            f"已建立 {manifest['article_count']} 條法規索引："
            f"{args.index}；逐條 JSON：{args.article_dir}"
        )
        return

    articles = lookup_related_articles(
        args.index,
        article=args.article,
        equipment=args.equipment,
        keyword=args.keyword,
        limit=args.limit,
    )
    if args.format == "json":
        print(json.dumps(articles, ensure_ascii=False, indent=2))
        return
    for article in articles:
        hierarchy = " > ".join(article["hierarchy"])
        print(f"## {article['legal_basis']} {hierarchy}")
        print(article["markdown"])
        print()


if __name__ == "__main__":
    main()
