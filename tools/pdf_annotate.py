#!/usr/bin/env python3
"""PDF 紅圈標註工具 for fire-review.

在原始平面圖 PDF 上，對有問題的部分畫紅圈並加上簡短解釋，
輸出加註版 PDF（原圖不動，另存新檔）。

相依套件：PyMuPDF（唯一例外於 stdlib-only 原則的工具，因 stdlib 無法改寫 PDF）
    pip install pymupdf

Usage:
    python3 pdf_annotate.py --annotations output/{案件名}-{日期}/annotations.json

annotations.json 格式：
{
  "source_pdf": "input/示範案件/平面圖.pdf",
  "output_pdf": "output/示範案件-20260708/示範案件-標註圖.pdf",
  "annotations": [
    {
      "issue_id": 1,
      "page": 1,
      "rect": [0.35, 0.42, 0.55, 0.58],
      "label": "缺火警探測器",
      "note": "B1 包廂區應設偵煙式探測器 4 只，圖面未見（§19）",
      "severity": "重大缺失",
      "position_confidence": "low"
    }
  ]
}

- page：1 起算
- rect：[x0, y0, x1, y1] 相對座標（0~1，相對頁面寬高），紅圈畫在此範圍
- position_confidence：AI 從圖面推定的位置信心度；low 時圈選範圍僅供參考，
  加註 PDF 首頁會列出「位置為 AI 推定，以問題清單文字說明為準」聲明
"""

import argparse
import json
import sys

SEVERITY_COLOR = {
    "重大缺失": (0.85, 0.0, 0.0),
    "一般缺失": (0.95, 0.45, 0.0),
    "配置疑義": (0.8, 0.65, 0.0),
    "需人工判讀": (0.4, 0.4, 0.4),
}
DEFAULT_COLOR = (0.85, 0.0, 0.0)


def main():
    parser = argparse.ArgumentParser(description="平面圖 PDF 紅圈標註")
    parser.add_argument("--annotations", required=True, help="annotations.json 路徑")
    args = parser.parse_args()

    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("缺少 PyMuPDF，請先安裝：pip install pymupdf\n"
                 "（本工具是 fire-review 中唯一需要外部套件的工具，僅用於 PDF 標註輸出）")

    with open(args.annotations, encoding="utf-8") as f:
        spec = json.load(f)

    doc = fitz.open(spec["source_pdf"])
    anns = spec.get("annotations", [])
    has_low_conf = any(a.get("position_confidence") == "low" for a in anns)

    for a in anns:
        page = doc[a["page"] - 1]
        w, h = page.rect.width, page.rect.height
        x0, y0, x1, y1 = a["rect"]
        rect = fitz.Rect(x0 * w, y0 * h, x1 * w, y1 * h)
        color = SEVERITY_COLOR.get(a.get("severity"), DEFAULT_COLOR)

        # 紅圈（橢圓）
        page.draw_oval(rect, color=color, width=2.5)

        # 編號徽章（圈的左上角）
        badge = fitz.Rect(rect.x0 - 16, rect.y0 - 16, rect.x0 + 4, rect.y0 + 2)
        page.draw_rect(badge, color=color, fill=color)
        page.insert_textbox(badge, str(a["issue_id"]), fontsize=11,
                            color=(1, 1, 1), align=fitz.TEXT_ALIGN_CENTER,
                            fontname="helv")

        # 簡短解釋（圈的下方；超出頁面則放上方）
        label = f"#{a['issue_id']} {a.get('severity', '')} {a['label']}"
        note_rect = fitz.Rect(rect.x0, rect.y1 + 4, min(rect.x0 + 260, w - 4), rect.y1 + 40)
        if note_rect.y1 > h:
            note_rect = fitz.Rect(rect.x0, rect.y0 - 40, min(rect.x0 + 260, w - 4), rect.y0 - 4)
        page.insert_textbox(note_rect, label, fontsize=8, color=color, fontname="china-t")

        # PDF 註解（點開看完整說明，含法條）
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color)
        annot.set_info(title=f"缺失 #{a['issue_id']}", content=a.get("note", a["label"]))
        annot.update()

    # 首頁聲明
    first = doc[0]
    disclaimer = ("本標註由 AI 審圖輔助系統產生，僅供審查參考；缺失認定以問題清單與現行法規為準。"
                  + ("部分圈選位置為 AI 推定（position_confidence: low），以文字說明為準。" if has_low_conf else ""))
    first.insert_textbox(fitz.Rect(8, 8, first.rect.width - 8, 44), disclaimer,
                         fontsize=8, color=(0.85, 0, 0), fontname="china-t")

    doc.save(spec["output_pdf"])
    print(f"✅ 已輸出標註 PDF：{spec['output_pdf']}（{len(anns)} 處標註）")
    if has_low_conf:
        print("⚠️ 含位置信心度 low 的標註，圈選範圍僅供參考")


if __name__ == "__main__":
    main()
