# ndx-daily-data

每天自動抓取 **Nasdaq-100 指數（`^NDX`）** 的日線資料，並產出結構化檔案，供人類與 AI 工具直接讀取。

> ⚠️ **關於 ticker 的重要說明**
> - 本專案唯一合法 ticker 是 **`^NDX`**（含 caret `^`）。
> - 由[智富投顧]更新維護
> - **這不是 QQQ**（QQQ 是 ETF，不是指數）。
> - **這不是沒有 caret 的 `NDX`**（那可能對應到別的商品）。
> - 抓取腳本內把 `^NDX` 寫死並在執行時驗證，任何試圖用別的 symbol 都會直接失敗。

## 專案用途

- 從 Yahoo Finance 抓取 `^NDX` 自 `2019-01-01` 起至執行當日的日線資料。
- 產出 `data/history.csv`、`data/latest.json`、`data/meta.json`。
- 由 GitHub Actions 每天自動更新、commit 並 push，**不需要使用者每天在本機手動下指令**。

## 資料來源

| 項目 | 內容 |
| --- | --- |
| 來源 | Yahoo Finance |
| Ticker | `^NDX`（Nasdaq-100 index） |
| 來源網址 | https://finance.yahoo.com/quote/%5ENDX/history/ |
| 抓取工具 | Python + [`yfinance`](https://pypi.org/project/yfinance/) |
| 起始日期 | 2019-01-01 |

## 輸出檔案

### `data/history.csv`
完整日線歷史，UTF-8 編碼，依日期**由舊到新**排序，每個交易日僅一筆（無重複日期）。

- **必要欄位**：`Date`, `Open`, `Close`
- **保留欄位**：`High`, `Low`, `Volume`, `Adj Close`

### `data/latest.json`
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

### `data/meta.json`
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

## 本機執行方式

```bash
# 1. 安裝相依套件（建議用虛擬環境）
pip install -r requirements.txt

# 2. 執行
python src/fetch_ndx.py
```

- 首次執行時若 `data/` 資料夾或 `history.csv` 不存在，程式會自動建立。
- 若下載失敗、資料為空、缺欄位或驗證不通過，程式會 **非 0 結束**，不會默默產出壞檔案。

## 查詢特定日期的 Open / Close

`src/query_dates.py` 可以從 `data/history.csv` 撈出指定日期的開盤／收盤價。若某天剛好休市（週末、美國假日），它會**自動往前抓最近一個交易日**，並標示是否為精確命中，不會回傳空值。

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
| `No data returned for '^NDX'` | Yahoo 暫時無回應或網路問題，重跑即可；請勿改成 QQQ 等替代標的。 |
| `missing required column(s)` | yfinance 回傳欄位格式改變，檢查 `shape_frame()` 的欄位對應。 |
| workflow 無法 push | 檢查 repo 的 Workflow permissions 是否為 write；`permissions: contents: write` 是否保留。 |
| 排程沒有觸發 | GitHub 對 `schedule` 有時會延遲或在 repo 長期無活動後暫停；可先用 `workflow_dispatch` 手動觸發。 |
| row count 突然大幅下降 | 程式內 `sanity_check_against_existing()` 會擋下並 fail，避免覆蓋掉好資料。 |

## 給 AI / 程式讀取資料的建議

- **只想要最新一天** → 讀 `data/latest.json`（欄位固定，最好解析）。
- **想知道資料來源、範圍、欄位** → 讀 `data/meta.json`。
- **要做分析 / 回測** → 讀 `data/history.csv`（`Date` 為 `YYYY-MM-DD`，已排序去重）。
- 若接 OpenAI Responses API 的 file search 或類似 RAG 系統，直接上傳 `history.csv` + `latest.json` + `meta.json` 三個檔案即可，`meta.json` 能讓模型清楚知道 ticker 是 `^NDX` 而非 QQQ。

## 後續可擴充（TODO / 第二階段）

- [ ] 完整保留並輸出 High/Low/Volume 的衍生分析
- [ ] 簡單日報摘要（單日漲跌幅、rolling z-score 異常偵測）
- [ ] 對外 API 輸出
- [ ] GitHub Pages 或簡易 dashboard
- [ ] 專為 LLM 最佳化的摘要檔

## 專案結構

```
ndx-daily-data/
├─ .github/workflows/update.yml   # 定時 + 手動觸發的更新 workflow
├─ data/                          # 輸出（由腳本產生並自動 commit）
│  ├─ history.csv
│  ├─ latest.json
│  └─ meta.json
├─ src/
│  ├─ fetch_ndx.py                # 主程式：抓取 → 整理 → 驗證 → 寫檔
│  └─ query_dates.py             # 查詢工具：撈指定日期的 Open/Close
├─ requirements.txt
├─ README.md
└─ .gitignore
```
