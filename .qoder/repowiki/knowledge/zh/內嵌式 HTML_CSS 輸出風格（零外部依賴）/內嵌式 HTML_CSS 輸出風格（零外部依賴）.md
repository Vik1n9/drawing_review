---
kind: frontend_style
name: 內嵌式 HTML/CSS 輸出風格（零外部依賴）
category: frontend_style
scope:
    - '**'
source_files:
    - tools/checklist_html.py
    - tools/dxf_svg_review.py
    - tests/test_standard_checklist_html.py
---

本專案為 Python CLI 工具集合，不具備傳統前端框架或設計系統；所有使用者介面皆以「Python 字串模板」直接產出單一 HTML 檔案，CSS 與 JavaScript 全部以模組內的字串常數內嵌於 `<style>` / `<script>` 區塊中。以下為觀察到的前端風格模式：

1. **樣式載入方式**
   - 每個產生 HTML 的 tools 模組（`checklist_html.py`、`dxf_svg_review.py`）都在模組頂層定義 `CSS = """..."""` 字串，渲染時以 `<style>{CSS}</style>` 注入頁面 `<head>`。
   - 無任何 `.css`、`.scss`、Tailwind、Bootstrap 等外部樣式檔或套件引用，完全依賴 Python stdlib 與瀏覽器原生能力。

2. **CSS 方法與設計語法**
   - 使用現代 CSS 變數（`:root { --ink: #1f2933; --muted: #667085; --line: #d0d5dd; --panel: #f8fafc; }`）集中管理色彩與排版。
   - 採用 Flexbox 與 CSS Grid 佈局（`display: grid; grid-template-columns: minmax(0, 1fr) 360px;`），並搭配 `@media (max-width: 900px)` 做響應式切換。
   - 色彩系統以色調區分嚴重度：重大缺失 `#d71920`、一般缺失 `#e66b00`、配置疑義 `#b08b00`、需人工判讀 `#666666`，對應 class `critical`、`major`、`question`、`manual`。
   - 字型統一指定 `"Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif`，確保繁體中文顯示一致性。

3. **HTML 結構與命名慣例**
   - 檢核清單頁面使用表格結構（`<table>` + `<tr class="pass|fail|manual|na">`），每列以狀態 class 控制背景色。
   - DXF 審查頁面採用左右分欄：`<section class="viewer-panel">` 放置 SVG 圖面，`<aside>` 放置缺失導覽列表。
   - SVG 元素一律加上 `class="cad-entity"`、`class="cad-text"`、`class="cad-block"` 等類別，並附帶 `data-layer`、`data-issue-id`、`data-drawing-id` 等 data-* 屬性供 JS 操作。
   - 問題標記以 `<g class="issue-marker {severity-class}">` 包圍，內含橢圓框、編號徽章與文字。

4. **互動邏輯（JavaScript）**
   - 所有 JS 同樣以模組內 `JS = """..."""` 字串內嵌，提供縮放（`zoomBy`）、平移（pointer drag）、重設視窗（`resetView`）與問題點選取（`selectIssue`）功能。
   - 事件處理直接使用 `addEventListener` 綁定到 SVG 元素，無任何框架。

5. **列印與可存取性**
   - 檢核清單包含 `@media print` 規則，強制保留 fail 背景色以便列印。
   - DXF 審查頁面加入 `aria-label`、`tabindex="0"`、`role="button"` 等無障礙屬性。

6. **約束與限制**
   - 所有輸出 HTML 皆為單檔、零外部相依，適合在隔離環境（如 Windows SFX 安裝包、沙盒）中直接開啟。
   - 無版本化 CSS 架構、無元件庫、無構建步驟；樣式修改直接在 Python 字串中編輯。
   - 測試（`tests/test_standard_checklist_html.py`）透過斷言 HTML 字串中的 class（如 `red-check`）來驗證渲染結果，反映樣式變更會直接影響測試期望。