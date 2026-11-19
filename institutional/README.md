# Institution-tracker

機構持倉板：CTA 趨勢模型、CFTC 持倉、波動率控制基金及波動率訊號的本地 board。

```bash
pip install -r requirements.txt
python3 build.py                     # 首次建置 data/*.json（約一分鐘）
python3 serve.py                     # 內部來源 http://localhost:8768；平日開 http://localhost:8770（python3 server/serve.py）
```

頁頂：數據狀態（是哪一個收市、缺哪一個收市、CFTC 是否最新）連「更新數據」按鈕；之下一行單位及日期說明（兩頁共用）。每頁先是一行由數據生成的「意思」，之後按納指 NQ、標普 ES、其餘的次序，每項事實只寫一次。數據過時的部分標「過時」並淡化，盤中價暫不套用；未建置的部分顯示建置指示。

| 頁 | 內容 | 數據源 | 更新 |
|---|---|---|---|
| 今日 | 「意思」（包括下一交易日一個標準差：VIX1D ÷ √252 的 %，並按標普 500 指數、ES 期貨及 SPY 收市折算點數或美元及範圍；缺哪個價格就註明）；持倉及關鍵水平：納指 NQ、標普 ES 各一張卡（價格；CFTC 各類淨 long / short 及一週變化、CTA 模型位置及綜合翻轉價、波動率控制模型；一日一個標準差（標普只用 VIX1D ÷ √252，VIX1D 缺失時註明缺失，不改用 VIX；納指沒有一日指數，用 VXN ÷ √252）及跨式價格；水平階梯：CTA 翻轉價是模型的機械水平，前日高低位、均線只是價格參考，期權未平倉最多的行使價），之後是 VIX 水平階梯及 VIX 讀數（只有 30 日讀數：VIX 及一年百分位、VIX9D、VIX/VIX3M、VXN − VIX、VVIX、VIX 對標普的反應；VIX 收市高於 30 時加 R32 歷史參考），再之後是 VIX1D 水平（一年高位、中位數、低位、前一收市）及 VIX1D 讀數（VIX1D 及一年百分位、下一交易日一個標準差的 % 及標普點數、VIX1D 對 VIX 及 VIX9D、前一交易日實際波幅對前一晚 VIX1D 所定價的波幅；附 R33 回測附註一次）；槓桿 ETF 及波動率控制按單日升跌的資金估算。盤中價每 60 秒更新 | Yahoo 期貨、指數、Cboe 波動率指數、期權鏈及 ETF 資產；本板模型 | 每個交易日；盤中價延遲約 10 至 15 分鐘 |
| 本週 | 五日價格及「意思」（誰買誰賣、對手方、是否順價格方向、持倉日期是否早於價格窗口）；納指 NQ、標普 ES 各一張卡（CFTC 四類及相對一年平均、非交易商名義淨倉；CTA 模型；波動率控制）；其他市場的 CFTC 四類交易者；其他市場 CTA 五日買賣最多；波動率參考（近 20 日實際大過隱含的日數按前一晚 VIX1D 計，平均自 2023 年 4 月起）；未來三週財報 | CFTC TFF 及 Disaggregated；Yahoo；本板模型 | CFTC 通常每週五（週二持倉，假期週延後），其餘每個交易日 |

CTA 翻轉價是下一交易日模型信號由正轉負（或相反）的收市價；因回看窗口每日前移，它可以在上一收市的任何一邊（「持平即翻」）。
下一交易日只用 VIX1D 的根據是回測 R33（`../../valuation and research/Backtests/results/33_vix1d_vs_vix.txt`）。`levels.json` 的 `cash` 是 ^GSPC 及 SPY 收市，`vix1d_rv` 是標普實際波幅對前一晚 VIX1D ÷ √252；`strip` 每項附一年高位、低位、中位數及百分位。
`data/level_log.json` 保留每日的水平，日後用來檢驗。改了 `live.py` 或 `serve.py` 要重啟 `serve.py`；改 `index.html` 或 `data/` 只要重新整理頁面。

參數在 `build.py`：回看期 `LOOKBACKS`、波動率控制的 `VC_TARGET`、`VC_CAP`、`VC_AUM_BN`、槓桿 ETF 名單 `LEV_ETFS`。
CTA 和波動率控制是模型估算，金額取決於 AUM 假設。持倉及個人資料不放入此資料夾。
