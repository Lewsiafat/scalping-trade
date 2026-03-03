# feat: 增加Notification的冷卻時間機制

- **分支:** `feat/add-colddown-to-notification`
- **日期:** 2026-03-03

## 描述
增加瀏覽器通知 (Notification) 的冷卻時間機制，避免在自動刷新時，相同的高品質信號或警報設定連續不斷地觸發通知，造成干擾。冷卻時間設定為 1 分鐘，並以「通知標題 (title) + 通知內容 (body)」作為判斷是否重複的基準。

## 任務清單
- [x] 在 `app_v2.py` 中的前端 JavaScript 全域範圍新增 `notificationCooldowns` 物件，用於儲存各通知的最後發送時間。
- [x] 設定全域常數 `NOTIFICATION_COOLDOWN_MS = 60 * 1000` (1 分鐘)。
- [x] 修改 `sendNotification(title, body)` 函數，將 `title + "|" + body` 作為 key。
- [x] 在發送通知前，檢查該 key 的最後發送時間距今是否超過 `NOTIFICATION_COOLDOWN_MS`。
- [x] 若未超過，則不發送通知；若超過或未曾發送過，則發送通知並更新該 key 的時間。
