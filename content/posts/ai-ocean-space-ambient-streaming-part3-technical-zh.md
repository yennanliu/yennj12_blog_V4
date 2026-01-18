---
title: "AI 深海/太空環境音串流實戰（三）：OBS 設定、串流上線與自動化監控"
date: 2026-01-18T18:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "business", "streaming", "technical"]
tags: ["OBS", "串流", "技術設定", "自動化", "監控", "YouTube直播", "24/7"]
summary: "系列第三篇：完整的 OBS Studio 設定指南、YouTube 串流配置、自動化腳本開發，以及 24/7 穩定運行的監控系統。從技術小白到專業串流者的完整路徑。"
readTime: "32 min"
---

在前兩篇中，我們掌握了音頻生成和視覺製作。本篇將進入技術實作階段：如何將所有素材整合到 OBS Studio，設定最佳串流參數，建立自動化系統，並確保 24/7 穩定運行。

## 🖥️ 硬體需求與成本分析

### 最低配置（$0 - 使用現有電腦）

```yaml
CPU:
  最低: Intel i5-6代或 AMD Ryzen 3
  推薦: Intel i5-8代或 AMD Ryzen 5
  原因: 需要編碼影片流

RAM:
  最低: 8GB
  推薦: 16GB
  原因: OBS + 瀏覽器 Source 吃記憶體

GPU:
  推薦: NVIDIA GTX 1050 或更高
  原因: 硬體編碼（NVENC）效能好、CPU 佔用低
  可選: AMD GPU 或 Intel 內顯（使用 CPU 編碼）

儲存空間:
  最低: 20GB 可用空間
  推薦: 100GB SSD
  原因: 素材儲存 + 系統緩存

網路:
  最低: 上傳速度 5 Mbps
  推薦: 上傳速度 10 Mbps 以上
  測試: speedtest.net

電源:
  UPS 不斷電系統（強烈建議）: $50-150
  原因: 避免斷電導致直播中斷
```

### 升級配置（$500-1,000）

```yaml
方案 A: 二手工作站
  • Dell OptiPlex 或 HP EliteDesk
  • Intel i5-9代 / AMD Ryzen 5 3600
  • 16GB RAM
  • 加裝 GTX 1650 顯卡
  • 價格: $400-600

方案 B: 樹莓派（極限低成本）
  • Raspberry Pi 5（8GB）
  • 價格: $80
  • 優勢: 功耗極低（<15W）
  • 劣勢: 效能有限，僅 720p
  • 適合: 驗證概念階段

方案 C: 雲端串流（AWS/GCP）
  • EC2 t3.medium（2 vCPU, 4GB RAM）
  • 價格: ~$35/月
  • 優勢: 不佔用家用電腦、穩定性高
  • 適合: 月收入 >$500 後投資
```

### 推薦策略

```
階段 1（前 3 個月）:
  使用現有電腦
  投資 UPS ($100)
  總成本: $100

階段 2（4-6 個月，月收入 $500+）:
  購買二手工作站專用串流
  或訂閱雲端服務
  總成本: $400-600 或 $35/月

階段 3（7-12 個月，月收入 $2000+）:
  建置專業伺服器
  多頻道、自動化系統
  總成本: $1,500-3,000
```

---

## 🎬 OBS Studio 完整設定指南

### 安裝與基礎設定

```markdown
Step 1: 下載安裝

1. 前往 https://obsproject.com/
2. 下載對應系統版本:
   • Windows: OBS-Studio-30.x.x-Windows.exe
   • macOS: OBS-Studio-30.x.x-macOS.dmg
   • Linux: 使用套件管理器

3. 安裝（預設選項即可）

4. 首次啟動會出現「自動設定精靈」
   → 暫時跳過，我們手動設定

Step 2: 介面認識

OBS 主介面區域:

┌─────────────────────────────────────────┐
│        預覽視窗（Preview）                │
│    （即時顯示將串流的畫面）               │
│                                          │
│                                          │
└─────────────────────────────────────────┘
┌─────────┬─────────┬─────────┬──────────┐
│ Scenes  │ Sources │ Mixer   │ Controls │
│(場景)   │(來源)   │(混音器) │(控制)    │
│         │         │         │          │
│ Scene 1 │ Video   │ Desktop │ Start    │
│ Scene 2 │ Image   │ Mic     │ Record   │
│         │ Browser │         │ Settings │
└─────────┴─────────┴─────────┴──────────┘

關鍵概念:
  • Scene: 場景（如：深海場景、太空場景）
  • Source: 來源（如：影片、圖片、文字）
  • 一個 Scene 可包含多個 Sources
  • 可隨時切換 Scenes
```

---

### 場景架構設計

**方案 A：簡單單場景（推薦新手）**

```yaml
[Scene: Ocean Ambience]
└── Source 1: Video（深海循環影片）
    └── Source 2: Image（Logo 浮水印）
        └── Source 3: Browser Source（即時時鐘）
            └── Source 4: Text（標題）

優勢:
  • 簡單易管理
  • 穩定性高
  • CPU 占用低

劣勢:
  • 無法切換主題
  • 內容單一
```

**方案 B：多場景輪播（推薦）**

```yaml
[Scene 1: Deep Ocean]
├── Video: deep_ocean_loop.mp4
├── Image: logo.png
├── Browser: clock.html
└── Text: "Deep Ocean Ambience 24/7"

[Scene 2: Coral Reef]
├── Video: coral_reef_loop.mp4
├── Image: logo.png
├── Browser: clock.html
└── Text: "Coral Reef Sounds 24/7"

[Scene 3: Deep Space]
├── Video: deep_space_loop.mp4
├── Image: logo.png
├── Browser: clock.html
└── Text: "Deep Space Ambience 24/7"

[Scene 4: Nebula]
├── Video: nebula_loop.mp4
├── Image: logo.png
├── Browser: clock.html
└── Text: "Nebula Soundscape 24/7"

輪播策略:
  • 每個場景播放 30 分鐘
  • 使用 Advanced Scene Switcher 外掛自動切換
  • 提供視覺多樣性，降低觀眾疲勞

優勢:
  • 內容豐富
  • 觀眾停留時間長
  • SEO 友善（多關鍵字）

劣勢:
  • 設定較複雜
  • 需要更多素材
```

---

### 詳細設定流程

#### Step 1: 創建第一個場景

```markdown
1. 在 "Scenes" 區域點擊 "+"
2. 命名: "Deep Ocean"
3. 點擊 OK

場景已創建，但目前是空白的
```

#### Step 2: 添加影片來源

```markdown
1. 在 "Sources" 區域點擊 "+"
2. 選擇 "Media Source"（媒體來源）
3. 命名: "Ocean Video Loop"
4. 點擊 OK

設定視窗:
  ☑ Local File（本機檔案）
  Browse: 選擇你的 deep_ocean_loop.mp4

  ☑ Loop（循環播放）← 非常重要！
  ☑ Restart playback when source becomes active
  ☐ Show nothing when playback ends

  ☐ Use hardware decoding when available
    （如有效能問題可勾選）

5. 點擊 OK

調整大小:
  • 在預覽視窗中，影片會出現紅框
  • 拖曳角落調整大小
  • 或右鍵 → Transform → Fit to screen
```

#### Step 3: 添加 Logo 浮水印

```markdown
1. Sources → "+" → "Image"
2. 命名: "Logo"
3. Browse: 選擇你的 logo.png

重要:
  • Logo 必須是 PNG 格式（透明背景）
  • 建議尺寸: 200x200 px
  • 不要太大，遮蔽畫面

定位:
  • 拖曳到右下角或左下角
  • 縮小到適當大小

透明度調整:
  • 右鍵 Logo → Filters
  • "+" → Color Correction
  • Opacity: 70%（不要太搶眼）
```

#### Step 4: 添加即時時鐘

```markdown
1. 創建 HTML 時鐘檔案

開啟文字編輯器，貼上:

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      margin: 0;
      padding: 20px;
      background: transparent;
      font-family: 'Arial', sans-serif;
    }
    #clock {
      font-size: 48px;
      color: white;
      text-shadow: 2px 2px 8px rgba(0,0,0,0.8);
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div id="clock"></div>
  <script>
    function updateClock() {
      const now = new Date();
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      document.getElementById('clock').textContent = hours + ':' + minutes;
    }
    setInterval(updateClock, 1000);
    updateClock();
  </script>
</body>
</html>
```

存檔為: clock.html（放在容易找到的位置）

2. 在 OBS 中添加

Sources → "+" → "Browser"
命名: "Clock"

設定:
  ☑ Local file
  Browse: 選擇 clock.html

  Width: 300
  Height: 100

  ☑ Shutdown source when not visible
  ☑ Refresh browser when scene becomes active

  FPS: 30（不需要太高）

3. 定位到右上角
```

#### Step 5: 添加標題文字

```markdown
Sources → "+" → "Text (GDI+)"
命名: "Title"

Text 輸入:
  Deep Ocean Ambience 24/7
  Relaxing Sounds for Sleep, Study, Meditation

Font:
  Family: Arial 或 Montserrat
  Size: 48
  Style: Bold
  Color: White (#FFFFFF)

Background:
  ☑ Enable
  Color: Black (#000000)
  Opacity: 50
  Padding: 20

Outline:
  ☑ Enable
  Size: 2
  Color: Black
  （增加可讀性）

定位: 上方中央或左上角
```

#### Step 6: 音頻設定

```markdown
方案 A: 使用 Media Source（簡單）

1. Sources → "+" → "Media Source"
2. 命名: "Ocean Audio"
3. 選擇你的音頻檔案
4. ☑ Loop

缺點:
  • 影片和音頻可能不同步
  • 難以管理多首曲目

方案 B: 使用 VLC Video Source（推薦）

1. 安裝 VLC Player:
   https://www.videolan.org/

2. 重啟 OBS

3. Sources → "+" → "VLC Video Source"
4. 命名: "Audio Playlist"

5. 點擊 "+" 添加音頻檔案
   • 可添加多首
   • 會自動循環播放列表

6. 設定:
   ☑ Loop Playlist
   ☐ Shuffle Playlist（隨機，可選）
   ☐ Show video（不顯示影片，僅播放音頻）

優勢:
  • 管理 50 首音樂很容易
  • 不會中斷
  • 可隨機播放增加變化

音量調整:
  • 在 "Audio Mixer" 區域
  • 拖曳滑桿到適當音量
  • 建議: -6 dB（預留 headroom）

進階: 添加音頻濾鏡
  右鍵 Audio Source → Filters
  • Compressor: 平衡音量
  • Limiter: 防止破音
```

---

### 輸出設定（關鍵！）

```markdown
Settings → Output

Mode: Advanced

── Streaming Tab ──

Audio Track: 1

Encoder: 選擇最佳選項

  選項 1: NVIDIA NVENC H.264（如有 Nvidia 顯卡）
    • 優勢: GPU 硬體編碼，CPU 占用極低
    • 推薦: GTX 1050 以上

  選項 2: AMD AMF H.264（如有 AMD 顯卡）
    • 優勢: 類似 NVENC

  選項 3: x264（CPU 編碼）
    • 優勢: 不需獨立顯卡
    • 劣勢: CPU 占用高（30-50%）
    • 適合: CPU 強但無獨顯

推薦: NVIDIA NVENC H.264

詳細設定（NVENC）:

Rate Control: CBR（固定比特率）
  原因: 串流平台偏好穩定比特率

Bitrate: 6000 Kbps
  1080p@30fps 的最佳值
  如果網路不穩，降到 4500 Kbps

Keyframe Interval: 2 seconds
  YouTube 建議值

Preset: Quality
  可選: Max Quality（更好畫質，稍高 CPU）

Profile: high

Look-ahead: ☐ 不勾選
  會增加延遲

Psycho Visual Tuning: ☑ 勾選
  提升視覺品質

GPU: 0（預設）

Max B-frames: 2

── Recording Tab ──（可選）

如果想要本地備份:

Type: Standard

Recording Format: mp4

Encoder: 與 Streaming 相同

Recording Path: 選擇大容量硬碟
  （1 小時 1080p ≈ 2-3GB）
```

---

### 影片設定

```markdown
Settings → Video

Base (Canvas) Resolution: 1920x1080
  （這是 OBS 的工作畫布大小）

Output (Scaled) Resolution: 1920x1080
  （實際串流的解析度）

  如果效能不足:
    可降到 1280x720（720p）
    Bitrate 也相應降到 3000-4500 Kbps

Downscale Filter: Lanczos（最高品質）
  如果 CPU 吃緊，選 Bilinear

Common FPS Values: 30
  音樂直播不需要 60fps
  30fps 足夠且節省頻寬
```

---

### 音頻設定

```markdown
Settings → Audio

Sample Rate: 48 kHz
  （串流標準）

Channels: Stereo

Desktop Audio Device:
  • Windows: Default
  • macOS: BlackHole（需額外安裝）

Mic/Auxiliary Audio: Disabled
  （音樂頻道不需要麥克風）

進階設定（很重要）:

Settings → Advanced → Audio

Audio Monitoring Device: 選擇你的耳機/喇叭
  用於監聽直播音頻

Audio Buffering: Automatic
```

---

### 進階：音頻壓縮與限制器

```markdown
為什麼需要?
  • 確保音量一致
  • 避免某些音軌突然太大聲
  • 防止破音（Clipping）

設定步驟:

1. 在 Audio Mixer 中，右鍵音頻來源
2. Filters → "+" → Compressor

Compressor 設定:
  Ratio: 3:1（壓縮比例）
  Threshold: -18 dB（啟動閾值）
  Attack: 6 ms（反應速度）
  Release: 60 ms（釋放速度）
  Output Gain: 0 dB
  Sidechain/Ducking Source: None

3. 再添加 Limiter

Limiter 設定:
  Threshold: -1.0 dB
  （確保絕不超過 -1dB，避免破音）

測試:
  播放音頻，觀察 Audio Meter
  應該在 -6 dB 左右波動
  峰值不應觸及紅色區域（0 dB）
```

---

## 📡 連接 YouTube 並開始串流

### YouTube 串流金鑰設定

```markdown
Step 1: 啟用 YouTube 直播功能

1. 前往 YouTube Studio:
   https://studio.youtube.com

2. 左側選單 → 內容 → 直播

3. 如果是第一次:
   • 點擊 "開始使用"
   • 驗證電話號碼
   • 等待 24 小時（啟用期）

Step 2: 建立串流

1. 點擊 "建立" → "直播"
2. 選擇 "串流"（Stream）

3. 基本資訊:
   Title: Deep Ocean Ambience 24/7 🌊 Relaxing...
   Description: [使用系列第一篇的 SEO 範本]
   Category: Music
   Visibility: Public

4. 串流設定:
   Stream latency: Low latency（低延遲）
   DVR: ☑ Enable（允許觀眾回放）
   自動開始: ☐ 不勾選（手動控制）

5. 複製「串流金鑰」
   （會顯示為 xxxx-xxxx-xxxx-xxxx）

Step 3: 在 OBS 中設定

OBS → Settings → Stream

Service: YouTube - RTMPS
Server: Primary YouTube ingest server

Stream Key: [貼上剛才複製的金鑰]

☑ Enable Auto-Reconnect
  Retry Delay: 2 seconds
  Maximum Retries: 30
  （如果網路斷線，自動重連）

點擊 "OK"

Step 4: 開始串流！

1. 在 OBS 主視窗，點擊 "Start Streaming"

2. 等待 10-15 秒

3. 回到 YouTube Studio:
   • 會顯示 "Stream health: Good"
   • 預覽畫面會出現你的直播內容

4. 再次檢查:
   ☐ 視覺正常顯示?
   ☐ 音頻清晰?
   ☐ 標題文字可讀?
   ☐ 時鐘正常更新?

5. 如果一切正常，點擊 "Go Live"（上線）

6. 你的直播正式開始！🎉
```

---

### 測試與優化

```markdown
重要: 先進行測試串流！

測試方法:

1. 在 YouTube Studio 創建串流時:
   Visibility: Unlisted（不公開）

2. 開始串流

3. 用另一台設備或手機開啟直播連結

4. 檢查清單:
   ☐ 畫面品質（清晰? 模糊?）
   ☐ 音頻品質（清晰? 雜音?）
   ☐ 音畫同步（有延遲?）
   ☐ 有無卡頓（Buffering）
   ☐ 元素定位（Logo, 時鐘位置正確?）

常見問題與解決:

問題 1: 畫面模糊
  解決:
    • 提高 Bitrate（+1000 Kbps）
    • 檢查 Output Resolution 是否為 1080p
    • 確認 Encoder 使用 NVENC 或正確設定

問題 2: 音頻破音
  解決:
    • 在 Audio Mixer 降低音量（-3 dB）
    • 檢查 Limiter 設定
    • 確認原始音頻檔案品質

問題 3: 卡頓（Buffering）
  解決:
    • 降低 Bitrate（-1000 Kbps）
    • 確認網路上傳速度 >8 Mbps
    • 關閉其他佔用頻寬的程式

問題 4: CPU 占用過高（>80%）
  解決:
    • 改用 NVENC 硬體編碼
    • 降低解析度到 720p
    • 關閉不必要的 Browser Sources

問題 5: 影片與音頻不同步
  解決:
    • OBS → Settings → Advanced
    • Audio Monitoring: 關閉
    • 或調整 "Sync Offset"（+/- 毫秒）
```

---

## 🤖 自動化與監控系統

### 自動場景切換（多場景輪播）

```markdown
需求: 每 30 分鐘自動切換場景

解決方案: Advanced Scene Switcher 外掛

安裝步驟:

1. 下載 Advanced Scene Switcher:
   https://obsproject.com/forum/resources/advanced-scene-switcher.395/

2. 下載對應版本的 .zip

3. 解壓縮到 OBS 外掛資料夾:
   Windows: C:\Program Files\obs-studio\obs-plugins\
   macOS: ~/Library/Application Support/obs-studio/plugins/
   Linux: ~/.config/obs-studio/plugins/

4. 重啟 OBS

5. 工具 → Advanced Scene Switcher

設定輪播:

1. 在 Advanced Scene Switcher 視窗
2. 選擇 "Sequence" 標籤
3. 點擊 "Add"

4. 創建序列:
   Scene 1: Deep Ocean
   Duration: 30:00（30 分鐘）
   Transition: Fade（1 秒）

   Scene 2: Coral Reef
   Duration: 30:00
   Transition: Fade（1 秒）

   Scene 3: Deep Space
   Duration: 30:00
   Transition: Fade（1 秒）

   Scene 4: Nebula
   Duration: 30:00
   Transition: Fade（1 秒）

5. ☑ Loop（循環播放）

6. Start Sequence

結果:
  • 每 30 分鐘自動切換場景
  • 平滑淡入淡出過渡
  • 無限循環
  • 無需人工操作

進階: 隨機播放
  在 Sequence 設定中:
    ☑ Randomize order
  （增加不可預測性）
```

---

### 自動重啟系統（避免長時間運行崩潰）

```markdown
為什麼需要?
  • OBS 長時間運行可能記憶體洩漏
  • 定期重啟保持穩定
  • 建議: 每 24 小時重啟一次

Windows 自動重啟腳本:

Step 1: 創建批次檔案

開啟記事本，貼上:

```batch
@echo off
echo Stopping OBS...
taskkill /IM obs64.exe /F
timeout /t 10

echo Clearing temp files...
del /q "%TEMP%\*"

echo Restarting OBS...
start "" "C:\Program Files\obs-studio\bin\64bit\obs64.exe" --startstreaming --profile "Ocean Space" --scene "Deep Ocean"

echo OBS restarted successfully!
```

存檔為: restart_obs.bat

Step 2: 測試腳本

雙擊 restart_obs.bat
確認:
  • OBS 正確關閉
  • 自動重新啟動
  • 自動開始串流

Step 3: 設定排程

1. 開啟「工作排程器」(Task Scheduler)
2. 動作 → 建立基本工作
3. 名稱: "OBS Auto Restart"
4. 觸發程序: 每天
5. 時間: 04:00 AM（用戶流量最低時段）
6. 動作: 啟動程式
   Program: C:\path\to\restart_obs.bat
7. 完成

macOS / Linux 使用 Cron:

編輯 crontab:
```bash
crontab -e
```

添加:
```
0 4 * * * /path/to/restart_obs.sh
```

restart_obs.sh 內容:
```bash
#!/bin/bash
killall obs
sleep 10
/Applications/OBS.app/Contents/MacOS/OBS --startstreaming --profile "Ocean Space" --scene "Deep Ocean" &
```

給予執行權限:
```bash
chmod +x restart_obs.sh
```
```

---

### 健康監控系統（Python）

```markdown
目標: 即時監控直播狀態，異常時發送通知

需求:
  • Python 3.8+
  • obs-websocket 外掛
  • Discord Webhook（通知管道）

Step 1: 安裝 obs-websocket

1. 下載: https://github.com/obsproject/obs-websocket/releases
2. 安裝到 OBS
3. 重啟 OBS
4. 工具 → WebSocket Server Settings
   • ☑ Enable WebSocket server
   • Server Port: 4455（預設）
   • ☑ Enable Authentication
   • Server Password: 設定強密碼

Step 2: 設定 Discord Webhook

1. 開啟你的 Discord 伺服器
2. 伺服器設定 → 整合 → Webhooks
3. 新增 Webhook
4. 命名: "OBS Monitor"
5. 選擇頻道: #alerts
6. 複製 Webhook URL

Step 3: 安裝 Python 套件

```bash
pip install obs-websocket-py requests
```

Step 4: 監控腳本

創建 monitor.py:

```python
import obsws_python as obs
import requests
import time
from datetime import datetime

# 設定
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "your_password_here"

DISCORD_WEBHOOK_URL = "your_discord_webhook_url_here"

# YouTube API（可選）
YT_STREAM_URL = "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

def send_discord_alert(message):
    """發送 Discord 通知"""
    data = {
        "content": f"⚠️ **OBS Alert** ⚠️\n{message}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    }
    requests.post(DISCORD_WEBHOOK_URL, json=data)

def check_obs_streaming():
    """檢查 OBS 是否正在串流"""
    try:
        ws = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)

        # 獲取串流狀態
        status = ws.get_stream_status()

        if not status.output_active:
            send_discord_alert("❌ 串流已停止！")
            return False

        # 獲取統計數據
        stats = ws.get_stats()
        fps = stats.active_fps
        cpu = stats.cpu_usage
        dropped = status.output_skipped_frames

        print(f"✅ 串流正常 - FPS: {fps}, CPU: {cpu}%, Dropped: {dropped}")

        # 檢查 FPS 過低
        if fps < 25:
            send_discord_alert(f"⚠️ FPS 過低：{fps}")

        # 檢查 CPU 過高
        if cpu > 85:
            send_discord_alert(f"⚠️ CPU 使用率過高：{cpu}%")

        # 檢查掉幀過多
        if dropped > 100:
            send_discord_alert(f"⚠️ 掉幀過多：{dropped} frames")

        ws.disconnect()
        return True

    except Exception as e:
        send_discord_alert(f"❌ 錯誤：{str(e)}")
        return False

def check_youtube_live():
    """檢查 YouTube 直播是否在線（簡易版）"""
    try:
        response = requests.get(YT_STREAM_URL, timeout=10)
        if '"isLiveNow":true' in response.text:
            print("✅ YouTube 直播在線")
            return True
        else:
            send_discord_alert("❌ YouTube 直播離線！")
            return False
    except Exception as e:
        print(f"無法檢查 YouTube：{e}")
        return None

def main():
    print("開始監控 OBS...")
    send_discord_alert("✅ 監控系統已啟動")

    while True:
        check_obs_streaming()
        # check_youtube_live()  # 可選

        # 每 5 分鐘檢查一次
        time.sleep(300)

if __name__ == "__main__":
    main()
```

Step 5: 執行監控

```bash
python monitor.py
```

保持腳本運行（背景執行）:

Windows:
  創建 run_monitor.bat:
  ```batch
  @echo off
  python C:\path\to\monitor.py
  ```
  添加到啟動項或工作排程器

Linux/macOS:
  使用 screen 或 tmux:
  ```bash
  screen -S obs_monitor
  python monitor.py
  # Ctrl+A, D 離開但保持運行
  ```

  或使用 systemd（開機自動啟動）
```

---

### 雲端監控（AWS CloudWatch）

```markdown
適合場景:
  • 使用 AWS EC2 串流
  • 需要專業級監控
  • 團隊協作

設定步驟:

1. 安裝 CloudWatch Agent 到串流機器

2. 設定監控指標:
   • CPU 使用率
   • 記憶體使用率
   • 網路輸出
   • OBS 程序狀態

3. 設定 CloudWatch Alarms:
   • CPU > 85% for 5 minutes → SNS 通知
   • OBS 程序停止 → 自動重啟
   • 網路斷線 → Email 警報

4. 儀表板:
   創建 CloudWatch Dashboard
   即時查看所有指標

成本: ~$10/月
```

---

## 🔧 故障排除指南

```yaml
問題 1: 串流突然斷線

可能原因:
  • 網路不穩定
  • ISP 問題
  • YouTube 伺服器問題

診斷步驟:
  1. 檢查網路: speedtest.net
  2. 檢查 OBS 日誌: Help → Log Files
  3. 尋找關鍵字: "error", "disconnect", "timeout"

解決方案:
  • 啟用 Auto-Reconnect（應已設定）
  • 降低 Bitrate
  • 聯繫 ISP
  • 更換 YouTube 伺服器（Settings → Stream → Server）

──────────────────────────────────

問題 2: 畫面凍結但串流仍在線

可能原因:
  • OBS 卡死
  • 影片來源問題
  • GPU 驅動問題

診斷:
  • 檢查 OBS 視窗是否回應
  • 檢查 Task Manager CPU/GPU 使用率
  • 查看 Windows 事件檢視器

解決方案:
  • 更新 GPU 驅動程式
  • 減少 Browser Sources
  • 降低解析度
  • 重啟 OBS（腳本自動化）

──────────────────────────────────

問題 3: 音頻與視覺不同步

可能原因:
  • Audio Buffering 設定
  • Sync Offset 錯誤
  • 使用 Media Source 而非 VLC

診斷:
  • 錄製 30 秒測試
  • 檢查延遲程度

解決方案:
  • 改用 VLC Video Source
  • 調整 Sync Offset:
    右鍵 Audio Source → Advanced Audio Properties
    → Sync Offset: +/- 毫秒
  • 重新製作影片（確保音視頻同步）

──────────────────────────────────

問題 4: 高 CPU 使用率（>80%）

可能原因:
  • 使用 x264 CPU 編碼
  • 過多 Browser Sources
  • 影片解析度過高

解決方案:
  • 改用 NVENC 硬體編碼
  • 移除不必要的 Sources
  • 降低 Canvas Resolution 到 720p
  • 關閉預覽（右鍵 Preview → Disable）

──────────────────────────────────

問題 5: 掉幀（Dropped Frames）

可能原因:
  • 網路頻寬不足
  • Bitrate 設定過高
  • 編碼設定過於複雜

診斷:
  • OBS 底部狀態列會顯示 "Dropped Frames"
  • 如果 >1% 需要處理

解決方案:
  • 降低 Bitrate（-500 Kbps）
  • 改用 CBR Rate Control
  • 確認無其他程式佔用頻寬
  • 使用有線網路而非 WiFi
```

---

## 📋 上線前最終檢查清單

```markdown
硬體與網路:
  ☐ 電腦效能足夠（CPU <60%）
  ☐ 網路上傳速度 >8 Mbps
  ☐ UPS 不斷電系統已連接
  ☐ 散熱良好（風扇運作正常）

OBS 設定:
  ☐ 場景已正確設定
  ☐ 影片循環播放正常
  ☐ 音頻播放列表運作正常
  ☐ Logo 和文字定位正確
  ☐ 時鐘顯示並更新
  ☐ 編碼器設定正確（NVENC 或 x264）
  ☐ Bitrate: 4500-6000 Kbps
  ☐ Resolution: 1920x1080 或 1280x720
  ☐ FPS: 30
  ☐ Auto-Reconnect 已啟用

音頻:
  ☐ 音量適中（-6 dB 左右）
  ☐ Compressor 和 Limiter 已設定
  ☐ 無破音或雜音
  ☐ 音畫同步

YouTube:
  ☐ 串流金鑰已正確設定
  ☐ 標題、描述已優化（SEO）
  ☐ 標籤已添加
  ☐ 分類為 "Music"
  ☐ 縮圖已上傳（高品質）
  ☐ Visibility: Public

自動化:
  ☐ Advanced Scene Switcher 已設定（如使用）
  ☐ 自動重啟腳本已排程
  ☐ 監控腳本運行中
  ☐ Discord 通知測試成功

測試:
  ☐ 已進行 30 分鐘測試串流
  ☐ 用其他設備觀看確認品質
  ☐ 無卡頓、掉幀
  ☐ 音頻清晰

備份計畫:
  ☐ 素材已備份到外部硬碟
  ☐ OBS 設定已導出（Scene Collection Export）
  ☐ 備用網路方案（手機熱點）
  ☐ 緊急聯繫人（如需遠端協助）
```

---

## 🎓 進階優化技巧

```yaml
1. 雙 PC 串流（專業級）
   設定:
     • PC 1: 運行 OBS，處理編碼
     • PC 2: 遊戲/內容生成（你的情況是準備素材）
     • 使用 NDI 或 Capture Card 連接

   優勢:
     • 完全分離負載
     • 最佳效能
     • 主 PC 可做其他工作

   成本: +$500-1,000（第二台電腦）

2. NDI 串流（同網路多機）
   設定:
     • 安裝 NDI Tools
     • PC 1 使用 NDI Output
     • PC 2 OBS 使用 NDI Source

   優勢:
     • 透過網路傳輸
     • 無需實體線材
     • 靈活性高

   缺點:
     • 需要高速區網（Gigabit Ethernet）

3. 多平台同時串流（Restream.io）
   設定:
     • 註冊 Restream.io ($20/月)
     • OBS 串流到 Restream RTMP
     • Restream 轉播到 YT, Twitch, FB 等

   優勢:
     • 同時觸及多平台觀眾
     • 統一管理

   缺點:
     • 額外成本
     • 某些平台可能有限制

4. 動態 Bitrate 調整
   使用外掛: Bitrate Adjuster
     • 根據網路狀況自動調整
     • 避免掉幀

5. 低延遲優化
   OBS → Settings → Advanced
     • Stream Delay: 0
     • Automatically Reconnect: 啟用
     • Network Buffering: 關閉

   YouTube Studio:
     • Stream latency: Ultra-low latency

   結果: 延遲降到 2-3 秒
```

---

## 📊 效能基準測試

```yaml
你的目標數據:

OBS 效能:
  • CPU 使用率: <60%
  • GPU 使用率: <70%（如使用 NVENC）
  • RAM 使用: <4GB
  • Render Lag: 0%
  • Encoding Lag: 0%
  • Dropped Frames: <0.5%

串流品質:
  • Bitrate 穩定: 4500-6000 Kbps
  • FPS 穩定: 29-30 fps
  • Resolution: 1080p 或 720p

YouTube 健康:
  • Stream health: Good/Excellent
  • Latency: <5 seconds
  • 無緩衝（Buffering）

如何監控:
  • OBS 底部狀態列
  • YouTube Studio Live Dashboard
  • Windows Task Manager / Activity Monitor
  • CloudWatch（如使用 AWS）
```

---

## 🔄 系列文章導航

1. **【已完成】市場分析、科學原理與 AI 工具選擇**
2. **【已完成】視覺製作：8K 深海/太空場景生成**
3. **【當前】技術實作：OBS 設定、串流上線與自動化** ✅
4. **【下一篇】內容策略：Shorts 導流、社群經營與變現**

下一篇也是最終篇，我們將探討如何透過 Shorts 導流、社群經營、以及多元變現策略，將你的頻道從 0 發展到月入數千美元。

---

## 延伸閱讀

- [AI 深海/太空環境音串流實戰（一）：市場分析、科學原理與 AI 工具選擇](/ai-ocean-space-ambient-streaming-part1-foundation-zh)
- [AI 深海/太空環境音串流實戰（二）：8K 視覺製作與動態場景生成](/ai-ocean-space-ambient-streaming-part2-visual-zh)

**標籤**: #OBS #串流 #技術設定 #自動化 #YouTube直播 #監控系統 #24/7
