# feat: 增加Notification的冷卻時間機制
## 任務摘要
- **分支**: `feat/add-colddown-to-notification`
- **日期**: 2026-03-03
- **Summary**: 新增前端瀏覽器通知的冷卻時間機制，避免在自動刷新或是因為價格微小跳動時持續發送相同的系統通知，並解決由 Emoji 作為 Notification Icon 取向造成的 API 404 錯誤。

## 變更項目
- `app_v2.py`: 
  - 新增屬性 `NOTIFICATION_COOLDOWN_MS` (一分鐘冷卻)與 `notificationCooldowns` 用於追蹤各通知的最後發送時間。
  - 將 `sendNotification` 重構，新增 `customKey` 參數作為冷卻識別，取代單純的 `title + "|" + body`。
  - 移除 Web Notification API 內無效的 emoji (`icon` 及 `badge` 屬性)，修復 HTTP 404 請求錯誤。

## 技術細節
- 由於依賴 `title + body` 做為去重鍵 (Key) 會有問題（例如：價格條件警報的 body 會夾帶變動的報價），故加入 `customKey`，例如：`alert_{id}` 和 `quality_{symbol}`，確保同一警報類型與交易對的冷卻期能穩定運作。
- 無效的 icon emoji 字串會讓瀏覽器誤開一個 URL 發送 GET 請求 (如 `/📈`)，進而導致 404 Not Found 的警告，移除後能避免無用的網路請求。
