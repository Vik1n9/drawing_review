#!/usr/bin/env python3
"""圖譜 label 與條號的**唯一**解析器（法規圖譜與訓練圖譜共用）。

只用 Python 標準庫。本模組不提供 CLI——它是給其他工具 import 的基礎層。

為什麼要有這個模組：原本「驗證抽取檔」與「實際建邊」各有一份判定，
而且兩者對「解析不到」的反應**相反**——`validate_extraction` 報錯擋下，
`build_layer` 卻靜默 `continue` 把邊丟掉。結果是驗證時綠燈、合併後圖譜悄悄少了邊。
所有寫入路徑一律走 `LabelIndex.resolve()`，讓兩邊的判定在定義上就不可能分岔。

三條紀律（呼應 AGENTS.md 底線 3「不確定就標需人工判讀」）：

1. **只做字面與條號的正規化，不做語意近似。** 不做子字串比對、不做編輯距離。
   `第19條之1` 不會解析到 `第19條`；`排煙` 不會解析到 `排煙設備`。
   `regulation_graph.py` 查詢時的子字串 fallback 是給人看的**查詢**行為，
   與**寫入**行為分開，不併入本模組。
2. **`ambiguous` 與 `missing` 一律回報，不得靜默取第一個候選。**
   目前只有一部法典所以 `ambiguous` 幾乎不會觸發，但行為先定死，
   避免日後多法典時 `setdefault` 悄悄選錯節點。
3. **正規化只收斂寫法，不改變指涉。** `§19`／`第 19 條`／`第十九條`／`19`
   是同一條條文的不同寫法，收斂成正典 `第19條`；而 `第19條之1` 是**另一條**。
"""

import re
from collections import namedtuple

# ---------------------------------------------------------------------------
# 文字正規化

# 看不見卻會讓字串比對失敗的字元：全形空格、NBSP、窄 NBSP、零寬字元。
# 零寬字元特別重要——它從 PDF／網頁複製條文時很常混進來，肉眼完全看不出來，
# 卻會讓 label 對不上而整條邊被丟掉。
_INVISIBLE = "　  ​‌‍﻿"

# 全形英數 → 半形。**刻意不用 NFKC**：NFKC 會連全形標點一起轉掉
# （`，`→`,`、`；`→`;`、`：`→`:`），而本專案的產出是繁體中文審圖報告，
# 標點被改成半形是品質倒退。這裡只收斂「同一個字的不同寬度」，不動標點。
_WIDTH_TABLE = str.maketrans(
    "０１２３４５６７８９"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz")

# 括號寫法統一——圖譜既有 label 用全形（例：`甲類（一）電影片映演場所`）。
# 只在**比對鍵**上做，不動原文，免得顯示用的文字被改寫。
_PAREN_TABLE = str.maketrans({"(": "（", ")": "）"})


def normalize_text(value):
    """一般文字正規化：全形英數轉半形 → 去除不可見字元 → 摺疊空白為單一半形空格。

    **標點原樣保留**——這個函式的輸出會直接顯示給使用者看。
    給「要保留詞間空白」的場合用（例：`第 18 條官方完整條文附件，第 1 頁`）。
    """
    text = str(value).translate(_WIDTH_TABLE)
    for ch in _INVISIBLE:
        text = text.replace(ch, " ")
    return re.sub(r"\s+", " ", text).strip()


def label_key(value):
    """label 的比對鍵：正規化後**移除所有空白**、統一括號、轉小寫。

    `第 19 條` 與 `第19條` 必須是同一個鍵；`甲類（一）` 與 `甲類(一)` 也是；
    ASCII 大小寫差異（`README` vs `readme`）同樣不該讓 label 對不上。
    """
    text = normalize_text(value).translate(_PAREN_TABLE)
    return re.sub(r"\s+", "", text).lower()


# ---------------------------------------------------------------------------
# 中文數字

_CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def parse_cn_number(text):
    """`十九` → 19、`一百四十六` → 146、`九十七` → 97；解析不了回 None。

    條文裡的條號寫法（`第十九條`）與索引裡的阿拉伯數字（`19`）必須對得起來，
    否則從條文全文抽出的引用永遠掛不上節點。
    """
    text = str(text).strip()
    if not text:
        return None
    if all(ch in _CN_DIGITS for ch in text) and len(text) > 1:
        # `二三` 這種逐字唸法不是法條寫法，拒絕——寧可解析不到，也不要猜錯條號。
        return None

    total, section, seen = 0, 0, False
    for ch in text:
        if ch in _CN_DIGITS:
            section = _CN_DIGITS[ch]
            seen = True
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            # `十九` 的十前面沒有數字，代表 1×10。
            section = section or 1
            total += section * unit
            section = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + section


# ---------------------------------------------------------------------------
# 條號

# `第146-5條`／`第146條之5`／`第一百四十六條之五` 都是同一條。
# 正典內部表示法一律是 `146-5`（與 rules/regulation_articles/article-146-5.json 一致）。
_ARTICLE_STRIP = re.compile(r"^[§第\s]+|[\s條]+$")
_ARABIC_ARTICLE = re.compile(r"^(\d+)(?:[-之](\d+))?$")


def parse_article_ref(value):
    """任何條號寫法 → 正典條號字串（`19`／`146-5`）；解析不到回 None。

    支援：`§19`、`19`、`第19條`、`第 １９ 條`、`第十九條`、`第146-5條`、
    `第146條之5`、`第一百四十六條之五`。

    中文數字寫法**必須帶條號標記**（`§`／`第`／`條`）：裸 `19` 是使用者慣用的輸入，
    但裸 `十九` 太容易把條文內文的數字誤讀成條號，寧可解析不到（底線 3）。
    """
    if value is None:
        return None
    text = re.sub(r"\s+", "", normalize_text(value))
    if not text:
        return None

    has_marker = bool(re.search(r"[§第條]", text))
    # `第146條之5` → `第146之5條`，讓「之N」與主條號一起處理
    text = re.sub(r"條之", "之", text)
    text = _ARTICLE_STRIP.sub("", text)
    if not text:
        return None

    match = _ARABIC_ARTICLE.match(text)
    if match:
        head, tail = match.group(1), match.group(2)
        return f"{int(head)}-{int(tail)}" if tail else str(int(head))

    # 中文數字：`一百四十六之五`（僅限帶條號標記者）
    if not has_marker:
        return None
    head, _, tail = text.partition("之")
    head_no = parse_cn_number(head)
    if head_no is None:
        return None
    if not tail:
        return str(head_no)
    tail_no = parse_cn_number(tail)
    if tail_no is None:
        return None
    return f"{head_no}-{tail_no}"


def article_label(value):
    """任何條號寫法 → 圖譜 label 的正典寫法 `第19條`／`第146-5條`；解析不到回 None。"""
    number = parse_article_ref(value)
    return f"第{number}條" if number else None


# 條文與筆記裡會引用「別部法規」的條號。`本標準依消防法第六條第一項規定訂定之`
# 若照抽，會生出一條指向本標準第6條的假邊——那是完全不同的一條條文。
EXTERNAL_LAW_NAMES = ("消防法", "本法", "建築法", "建築技術規則", "公寓大廈管理條例",
                      "災害防救法", "石油管理法", "民法", "刑法", "行政程序法",
                      "公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法")

# 自由文字中的條號引用。中文數字與阿拉伯數字都要抓，並允許「之N」子條號。
_ARTICLE_MENTION = re.compile(
    r"(?:§\s*\d+(?:\s*[-之]\s*\d+)?"
    r"|第\s*(?:[0-9０-９]+|[〇零一二三四五六七八九十百千]+)\s*條(?:\s*之\s*(?:[0-9０-９]+|[〇零一二三四五六七八九十百千]+))?)"
)

# 判斷「這個條號是不是掛在別部法規底下」時，往前看的字數。
# 法名與條號之間最多隔幾個字（例：`依消防法第六條`、`建築技術規則第九十九條`）。
_EXTERNAL_LOOKBEHIND = 12


def find_article_refs(text, exclude_external=True):
    """從自由文字中找出**本法典**的條號引用，回傳正典條號清單（去重、保序）。

    `exclude_external` 會濾掉掛在別部法規名稱底下的條號（見 EXTERNAL_LAW_NAMES）——
    這是確定性引用抽取最容易出的錯：`本標準依消防法第六條…` 會生出一條假的內部引用。
    """
    if not text:
        return []
    text = normalize_text(text)
    found = []
    for match in _ARTICLE_MENTION.finditer(text):
        if exclude_external:
            window = text[max(0, match.start() - _EXTERNAL_LOOKBEHIND):match.start()]
            if any(name in window for name in EXTERNAL_LAW_NAMES):
                continue
        number = parse_article_ref(match.group(0))
        if number and number not in found:
            found.append(number)
    return found


def article_sort_key(value):
    """條號排序鍵：`146-5` → (146, 5)、`19` → (19, 0)。解析不到排到最後。"""
    number = parse_article_ref(value)
    if number is None:
        return (float("inf"), 0)
    head, _, tail = number.partition("-")
    return (int(head), int(tail) if tail else 0)


# ---------------------------------------------------------------------------
# 節點 id 片段

def norm_id(label):
    """概念 label → 節點 id 片段（保留中日文字，其餘收斂為底線）。

    原本住在 practice_note_graph.py，搬過來讓兩個圖譜的建置工具共用同一份規則。
    """
    slug = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", str(label)).strip("_")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# label → 節點 id 的解析

EXACT = "exact"                        # label 完全相符
NORMALIZED = "normalized"              # 正規化後相符（全半形／空白／大小寫差異）
ARTICLE = "article"                    # 經條號解析對到條文節點
CONCEPT_DECLARED = "concept_declared"  # 對到本次抽取檔宣告的新概念
AMBIGUOUS = "ambiguous"                # 多個候選——拒絕猜
MISSING = "missing"                    # 全無

RESOLVED_HOWS = (EXACT, NORMALIZED, ARTICLE, CONCEPT_DECLARED)

Resolution = namedtuple("Resolution", "node_id matched_label how candidates")


class LabelIndex:
    """圖譜 label → node id 的解析索引。

    `declared` 是「本次抽取檔自己宣告、但圖譜裡還不存在」的概念 label，
    讓抽取檔可以先宣告概念、同一份檔案內的邊就能指向它。
    """

    def __init__(self, nodes=(), declared=()):
        self._by_label = {}
        self._by_key = {}
        self._by_article = {}
        self._label_by_id = {}
        self._declared = {}
        for node in nodes:
            self.add_node(node)
        for label in declared:
            self.declare(label)

    # -- 建索引 ------------------------------------------------------------

    def add_node(self, node):
        label = node.get("label")
        node_id = node.get("id")
        if not label or not node_id:
            return
        self._by_label.setdefault(str(label), []).append(node_id)
        self._by_key.setdefault(label_key(label), []).append(node_id)
        self._label_by_id.setdefault(node_id, str(label))
        number = parse_article_ref(label)
        # 只有「整個 label 就是一個條號」才建條號索引。`第18條官方完整條文附件，第1頁`
        # 這種附表圖 label 不該被 `§18` 解析到——那會讓引用掛到圖檔而不是條文。
        if number and article_label(label) == normalize_text(label).replace(" ", ""):
            self._by_article.setdefault(number, []).append(node_id)

    def declare(self, label):
        """宣告一個尚未進圖譜的概念 label（由抽取檔的 concepts[] 提供）。"""
        if label:
            self._declared.setdefault(str(label), None)

    def bind_declared(self, label, node_id):
        """概念節點實際建出來之後，把 id 綁回索引，後續的邊才解析得到。"""
        self._declared[str(label)] = node_id
        self.add_node({"label": label, "id": node_id})

    # -- 解析 --------------------------------------------------------------

    def resolve(self, target):
        """回 `Resolution`。`how` 落在 RESOLVED_HOWS 之外就代表解析失敗。"""
        if target is None:
            return Resolution(None, None, MISSING, [])
        target = str(target)

        hit = self._by_label.get(target)
        if hit:
            return self._one(hit, target, EXACT)

        hit = self._by_key.get(label_key(target))
        if hit:
            return self._one(hit, self._label_of(hit[0]) or target, NORMALIZED)

        number = parse_article_ref(target)
        if number:
            hit = self._by_article.get(number)
            if hit:
                return self._one(hit, article_label(number), ARTICLE)

        if target in self._declared:
            return Resolution(self._declared[target], target, CONCEPT_DECLARED, [])

        return Resolution(None, None, MISSING, [])

    def _one(self, ids, matched_label, how):
        unique = sorted(set(ids))
        if len(unique) > 1:
            return Resolution(None, matched_label, AMBIGUOUS, unique)
        return Resolution(unique[0], matched_label, how, [])

    def _label_of(self, node_id):
        return self._label_by_id.get(node_id)

    # -- 便利 --------------------------------------------------------------

    def labels(self):
        return set(self._by_label) | set(self._declared)

    def with_declared(self, labels):
        """衍生一份索引，額外認得這些「尚未進圖譜」的概念 label。

        驗證抽取檔時要用：抽取檔自己宣告的 concepts 也是合法的 edge target，
        但那些概念還不在圖譜裡，不該污染呼叫端持有的索引。
        """
        derived = LabelIndex()
        derived._by_label = {k: list(v) for k, v in self._by_label.items()}
        derived._by_key = {k: list(v) for k, v in self._by_key.items()}
        derived._by_article = {k: list(v) for k, v in self._by_article.items()}
        derived._label_by_id = dict(self._label_by_id)
        derived._declared = dict(self._declared)
        for label in labels:
            derived.declare(label)
        return derived

    @classmethod
    def from_labels(cls, labels):
        """只有 label 沒有 id 的場合（既有測試以 set 傳入）——id 用 label 本身頂替。"""
        return cls({"label": label, "id": label} for label in labels if label)


def describe(resolution, target):
    """解析失敗時給人看的一行說明（validate 與 build 共用同一套措辭）。"""
    if resolution.how == AMBIGUOUS:
        return (f"「{target}」在圖譜中對應到 {len(resolution.candidates)} 個節點"
                f"（{'、'.join(resolution.candidates)}）——請改用更明確的 label，不得由工具代選")
    return (f"「{target}」在圖譜與本抽取檔的 concepts 都找不到"
            "——請改用既有節點 label，或先在 concepts 宣告這個概念")
