"""Reviewable summary facts from the validated board snapshot.

No second download, publishing or AI generation. The existing after-close task
reviews this output under board_maintenance.md before saving a dated summary.
"""

def main():
    from daily_summary import build
    print(build())
    print("\n缺數或要核實（不要放入摘要，先處理）：")
    print("- 大市取態須使用同一收市快照的既有風險模型；不可把單日改善稱為已確認轉強。")
    print("- 檢查AI融資壓力資料；只有新的可核對CDS／指定債券息差才更新結論及圖表，缺報價仍未確認。")
    print("- 按 board_maintenance.md 的總結格式：一句市場摘要、模型、完整每日板塊數據及英國日程；不加入取態、三項檢查或圖表標記。完整週結才加本週變化及最多三點CFTC解讀，不重建每週回顧頁。")
    print("- 日期須逐項核對；未完成交易日不能當收市，舊報價不能當連續改善。")


if __name__ == "__main__":
    main()
