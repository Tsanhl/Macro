# Macro

市場 board：一個入口，四頁。本地版在 http://localhost:8770；公開靜態版在 https://tsanhl.github.io/Macro/ 。
A market board: one entry point, four pages. Local: http://localhost:8770. Public static snapshot: https://tsanhl.github.io/Macro/

```bash
# 在本資料夾（dashboard/）執行 / run from this folder
pip install -r macro/requirements.txt -r institutional/requirements.txt
python3 server/serve.py                    # http://localhost:8770
python3 macro/refresh.py                   # 更新宏觀數據（下載、核對、建置）
python3 macro/refresh.py --render-only     # 只用已存數據及人手檔案重建頁面
python3 institutional/build.py             # 更新機構持倉數據（約一分鐘）
python3 export_site.py --publish           # 用現有本地數據重建並發布公開靜態版
```

| 頁 Page | 內容 Content |
|---|---|
| 機構持倉 | NQ／ES／VIX／VIX1D：CFTC 持倉、CTA 趨勢模型、波動率控制模型、期權定價的波幅及水平階梯 |
| 宏觀（及油價） | 每日摘要、TGA、MOVE、聯儲淨流動性、美債拍賣及孳息、信用總表、AI／半導體相對強弱、輪動、市寬；油價：期貨曲線、持倉、OVX、事件機率、戰事進展 |
| 新聞與連接 | 按議題分組的最新新聞（只收官方來源及具名媒體），以及人手撰寫的議題 |
| AI 追蹤 | 階段定義、現時階段、要留意的事件、已核實的證據 |

## 資料夾 Folders

| 位置 Path | 作用 Role |
|---|---|
| `server/` | 8770 入口（`serve.py`）：外殼頁、宏觀版面（`macro_view.py`）、摘要（`macro_summary.py`）、新聞與 AI 頁（`pages.py`）；啟動另外兩個內部來源 |
| `macro/` | 宏觀數據的下載、計算及頁面（內部來源 8766）；`refresh.py` 更新；測試在 `macro/tests/` |
| `institutional/` | 機構持倉數據及頁面（內部來源 8768）；`build.py` 更新，`live.py` 盤中報價 |
| `evidence/` | 人手維護的 JSON：AI 追蹤、新聞議題、油價及戰事紀錄、借款人信用；公開網站會顯示 |
| `ai_cycle_watch/` | AI 週期分層讀數的數據（由更新程序複製及保留；不入 repo） |
| `logs/` | 每次更新的執行紀錄（只保留最新一次；不入 repo） |
| `board_maintenance.md` | 更新程序及追蹤內容 |
| `export_site.py` | 公開靜態版：輸出到 `site/`（不入 main），檢查私人資料，`--publish` 推送到 `gh-pages` |

## 公開靜態版 Public site

`python3 export_site.py --publish` 用本地 server 的同一套程式在本機生成四頁（外觀、深淺色與本地版相同），連同數據 JSON 寫入 `site/`，掃描輸出（持倉、名單、研究檔案、價位提示、本機路徑、人名、電郵、webhook、token），有任何一項即停止；通過後以新的單一 commit 取代 `gh-pages` 分支。靜態版沒有更新按鈕、盤中報價及自動新聞擷取，頁面註明匯出時間（英國時間）。每次本地更新後要公開最新數據時執行一次。

## 私隱 Privacy

持倉、名單、估值、價位提示及研究在 `../valuation and research/`，不進入此 repo 或公開網站。宏觀頁只顯示數據及摘要；CTA 及波動率控制數字是模型估算，不是實際持倉。
Tests: `cd macro && python3 -m unittest discover -s tests`. Not investment advice.
