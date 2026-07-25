# nasdaq100-data

每天自動抓取 **Nasdaq-100** 的市場資料——**指數 `^NDX`** 與 **E-mini 期貨 `NQ=F`**，涵蓋**日線**與**1 分K**——並產出結構化檔案，供人類與 AI 工具直接讀取。由[智富投顧]更新維護。

> ⚠️ **關於 ticker 的重要說明**
> - **指數**只用 **`^NDX`**（含 caret `^`）：**不是 QQQ**（QQQ 是 ETF）、**不是無 caret 的 `NDX`**。
> - **期貨**用 **`NQ=F`**（E-mini 那斯達克100，每點 US$20），是可交易標的；指數 `^NDX` 本身不可直接交易。
> - 每個標的的 ticker 在抓取腳本中寫死並於執行時驗證，避免誤抓替代標的。

## 專案用途

- 從 Yahoo Finance 抓取 `^NDX` 與 `NQ=F` 自 `2019-01-01` 起的日線，以及最近可得的 1 分K。
- 產出四個資料集於 `data/`（見下方「資料集一覽」），並有一份總索引 `data/manifest.json`。
- 由 GitHub Actions 每天自動更新、commit 並 push，**不需要使用者每天在本機手動下指令**。

## 資料來源

| 項目 | 內容 |
| --- | --- |
| 來源 | Yahoo Finance |
| Ticker | `^NDX`（Nasdaq-100 index） |
| 來源網址 | https://finance.yahoo.com/quote/%5ENDX/history/ |
| 抓取工具 | Python + [`yfinance`](https://pypi.org/project/yfinance/) |
| 起始日期 | 2019-01-01 |

## 輸出檔案（以 `^NDX` 日線為例，`nq_daily/` 結構相同）

### `data/ndx_daily/history.csv`
完整日線歷史，UTF-8 編碼，依日期**由舊到新**排序，每個交易日僅一筆（無重複日期）。

- **必要欄位**：`Date`, `Open`, `Close`
- **保留欄位**：`High`, `Low`, `Volume`, `Adj Close`

### `data/ndx_daily/latest.json`
最近一個交易日的快照：

```json
{
  "ticker": "^NDX",
  "source": "Yahoo Finance",
  "last_trading_date": "2026-07-21",
  "open": 29059.44,
  "close": 28604.23,
  "updated_at_utc": "2026-07-21T22:15:00Z"
}
```

### `data/ndx_daily/meta.json`
資料集後設資料，是「未來 AI 或人類交接時避免誤解資料來源」的關鍵檔案：

```json
{
  "ticker": "^NDX",
  "source_name": "Yahoo Finance",
  "source_url": "https://finance.yahoo.com/quote/%5ENDX/history/",
  "start_date": "2019-01-01",
  "last_updated_utc": "2026-07-21T22:15:00Z",
  "row_count": 1880,
  "fields": ["Date", "Open", "Close", "High", "Low", "Volume", "Adj Close"]
}
```

## 資料集一覽

本專案抓 **兩個標的**（指數 `^NDX` 與 E-mini 期貨 `NQ=F`）、**兩種頻率**（日線、1 分K），全部由 GitHub Actions 每天自動更新：

| 資料集 | 路徑 | 內容 | Raw 連結（給 AI／程式） |
| --- | --- | --- | --- |
| **^NDX 日線** | `data/ndx_daily/` | 2019→今，OHLCV | `.../main/data/ndx_daily/history.csv` |
| **NQ 日線** | `data/nq_daily/` | 2019→今，OHLCV | `.../main/data/nq_daily/history.csv` |
| **^NDX 1 分K** | `data/ndx_1m/` | 日盤，逐日累積 | `.../main/data/ndx_1m/history.csv` |
| **NQ 1 分K** | `data/nq_1m/` | 近 24 小時，逐日累積 | `.../main/data/nq_1m/history.csv` |

> Raw 連結前綴為 `https://raw.githubusercontent.com/Chief-rich/nasdaq100-data/`。
> **想一次看懂全部** → 讀總索引 `data/manifest.json`，裡面列出四個資料集的路徑、筆數、涵蓋範圍、raw 連結與更新時間。

### 關於 1 分K 的重要限制
Yahoo 的 1m 資料**只保留最近約 30 天**（每次請求最多 ~8 天）。因此 `fetch_1m.py` 每次執行會抓「當下可得的最近 ~30 天」並**去重 append** 進 `history.csv`——**從第一次執行起，這個檔會隨時間累積、超越 Yahoo 的 30 天上限**。換言之，2019 起的深度 1m 歷史 Yahoo 給不了，只能從現在開始往後累積（要補回舊資料需外部付費資料源）。

### 標的差異（回測請注意）
- `^NDX` 是**指數，不能直接交易**；1m 只有美股日盤（約 390 根/日）。
- `NQ=F` 是**可交易的 E-mini 那斯達克100 期貨**（每點 US$20）；1m 近 24 小時、含夜盤。
- 回測交易邏輯應使用**你實際下單的標的**（NQ 期貨或 QQQ），而非指數本身。

## 本機執行方式

```bash
# 1. 安裝相依套件（建議用虛擬環境）
pip install -r requirements.txt

# 2. 抓日線（^NDX + NQ=F，2019→今）
python src/fetch_daily.py

# 3. 抓／累積 1 分K（^NDX + NQ=F）
python src/fetch_1m.py
```

- 首次執行時若對應的資料夾或檔案不存在，程式會自動建立。
- 日線若下載失敗、資料為空、缺欄位或驗證不通過，程式會 **非 0 結束**，不會默默產出壞檔案。
- 1m 步驟中單一標的失敗（例如 Yahoo 一時抽風）只會記錄警告、不影響另一個標的。

## 查詢特定日期的 Open / Close

`src/query_dates.py` 可以從 `data/ndx_daily/history.csv` 撈出指定日期的開盤／收盤價。若某天剛好休市（週末、美國假日），它會**自動往前抓最近一個交易日**，並標示是否為精確命中，不會回傳空值。

```bash
# 用內建的 10 個範例日期
python src/query_dates.py

# 查自己的日期（YYYY-MM-DD，可帶任意數量，用空白分隔）
python src/query_dates.py 2020-03-16 2021-11-22 2024-07-04
```

輸出範例：

```
Requested    Trading day  Exact?          Open        Close
-----------------------------------------------------------
2020-03-16   2020-03-16   yes         7,502.26     7,020.38
2021-11-22   2021-11-22   yes        16,644.77    16,380.98
2024-07-04   2024-07-03   no         19,995.28    20,186.63   # 7/4 美國國慶休市，自動抓前一交易日
```

- 每次執行也會把結果另存成 `data/query_result.json`，方便程式或 AI 讀取。
- `Exact?` 欄為 `no` 時，代表當天休市，實際採用的是 `Trading day` 欄顯示的前一個交易日。

## GitHub Actions 自動更新

Workflow 定義於 `.github/workflows/update.yml`：

- **觸發方式**：
  - `schedule`：每天 `07:15 UTC` 自動執行（cron 使用 UTC 時間）。
  - `workflow_dispatch`：可在 GitHub → **Actions** 頁面手動按 **Run workflow** 測試。
- **權限**：workflow 設定 `permissions: contents: write`，讓 `GITHUB_TOKEN` 能把更新後的檔案 push 回本 repo。
- **提交行為**：
  - 若 `git diff` 顯示無變更 → 輸出 `No changes to commit` 並結束。
  - 若有變更 → 自動 commit（訊息 `chore: update ^NDX daily data`）並 push。
- **為何不拆成多條 workflow**：用 `GITHUB_TOKEN` 產生的 push 通常**不會**再觸發其他以 `push` 為條件的 workflow，因此所有關鍵流程都放在同一條 workflow 內。

### 啟用步驟
1. 把本專案推上 GitHub。
2. 到 repo 的 **Settings → Actions → General → Workflow permissions**，確認為 **Read and write permissions**（或依賴 workflow 內已宣告的 `permissions: contents: write`）。
3. 到 **Actions** 頁面手動跑一次 `Update ^NDX daily data` 驗證。

## 常見錯誤與排查

| 症狀 | 可能原因 / 解法 |
| --- | --- |
| `No daily data returned` | Yahoo 暫時無回應或網路問題，重跑即可；請勿改成 QQQ 等替代標的。 |
| `missing required column(s)` | yfinance 回傳欄位格式改變，檢查 `market_lib.py` 的 `shape_daily()` 欄位對應。 |
| 1m 資料抓不到 | Yahoo 只保留最近約 30 天 1m；超過範圍會回空，屬正常。單一標的失敗不影響另一個。 |
| workflow 無法 push | 檢查 repo 的 Workflow permissions 是否為 write；`permissions: contents: write` 是否保留。 |
| 排程沒有觸發 | GitHub 對 `schedule` 有時會延遲或在 repo 長期無活動後暫停；可先用 `workflow_dispatch` 手動觸發。 |

## 給 AI / 程式讀取資料的建議

- **先讀總索引（最推薦）** → `data/manifest.json`。一個檔就列出四個資料集有什麼、在哪、多少筆、涵蓋哪段、raw 連結是什麼。最適合 Claude Code、Cowork、OpenAI file-search 等工具的入口。
- **讀某標的整份日線** → `data/ndx_daily/history.json`（或 `nq_daily/`）。自描述格式：外層帶 `ticker` / `source` / `fields`，內層 `data` 每個交易日一筆。
- **只要最近一段（省 token）** → `data/ndx_daily/recent_30d.json`（最近 30 個交易日）。
- **只想要最新一筆** → `data/{dataset}/latest.json`（日線最新交易日；1m 為最新一根 K）。
- **要做分析 / 回測** → `data/{dataset}/history.csv`（日線 `Date` 為 `YYYY-MM-DD`；1m 的 `Datetime` 為含時區的 ISO 8601，已排序去重）。

> **給 AI 工具的連結請用 raw 純文字版**（不是 `/blob/` 網頁版），前綴：
> `https://raw.githubusercontent.com/Chief-rich/nasdaq100-data/main/`
> 例如總索引：`.../main/data/manifest.json`

## 後續可擴充（TODO / 第二階段）

- [ ] 完整保留並輸出 High/Low/Volume 的衍生分析
- [ ] 簡單日報摘要（單日漲跌幅、rolling z-score 異常偵測）
- [ ] 對外 API 輸出
- [ ] GitHub Pages 或簡易 dashboard
- [ ] 專為 LLM 最佳化的摘要檔

## 專案結構

```
nasdaq100-data/
├─ .github/workflows/update.yml   # 定時 + 手動觸發的更新 workflow
├─ data/                          # 輸出（由腳本產生並自動 commit）
│  ├─ manifest.json               # 總索引：四個資料集的路徑/筆數/範圍/連結
│  ├─ ndx_daily/                  # ^NDX 日線  { history.csv/.json, recent_30d, latest, meta }
│  ├─ nq_daily/                   # NQ=F 日線  { 同上結構 }
│  ├─ ndx_1m/                     # ^NDX 1 分K { history.csv, latest, meta }（逐日累積）
│  └─ nq_1m/                      # NQ=F 1 分K { history.csv, latest, meta }（逐日累積）
├─ src/
│  ├─ market_lib.py               # 共用邏輯：下載 / 整理 / 驗證 / 寫檔
│  ├─ fetch_daily.py              # 日線：^NDX + NQ=F（2019→今）
│  ├─ fetch_1m.py                 # 1 分K：^NDX + NQ=F（累積）
│  ├─ build_manifest.py           # 產生 data/manifest.json 總索引
│  └─ query_dates.py              # 查詢工具：撈指定日期的 Open/Close
├─ requirements.txt
├─ README.md
└─ .gitignore
```
