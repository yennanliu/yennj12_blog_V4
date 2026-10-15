---
title: "24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線"
date: 2026-10-15T09:00:00+08:00
draft: false
description: "一套可重用的 24/7 音樂直播維運堆疊：OBS 編碼參數、主機選擇、obs-websocket 看門狗、疊加層、Discord、Shorts 批次與贊助信範本，三個系列共用。"
categories: ["all", "creative", "engineering"]
tags: ["YouTube", "Streaming", "OBS", "24/7直播", "自動化", "Discord"]
authors: ["yen"]
readTime: "17 min"
---

> 多數人把 24/7 音樂頻道當成內容專案：先做 50 首曲子、再畫一張好看的背景，
> 然後按下 Start Streaming，以為事情結束了。
> 真正的差別出現在第四天凌晨三點：OBS 卡死、串流離線六小時、沒有人收到通知。
> 直播頻道是一個維運問題，內容只是它載運的貨物。

本站有三個音樂直播系列：[ADHD 專注音樂](/posts/adhd-focus-music-streaming-implementation-guide-zh/)、[深海／太空環境音](/posts/ai-ocean-space-ambient-streaming-part1-foundation-zh/)、[Synthwave 讀書會](/posts/synthwave-study-streaming-part1-market-culture-zh/)。它們的音樂、視覺和受眾完全不同，但底層那一層——編碼器設定、會自己爬起來的串流、監控告警、Discord 骨架、Shorts 批次流程、贊助提案信——是同一套。這篇把那一層抽出來，寫成一份可以直接照抄的維運手冊；三個系列只保留各自的利基參數，其餘都指回這裡。

讀完你會知道：位元率怎麼選、主機該放在家裡還是雲端、看門狗怎麼寫才不會半夜漏接、Discord 第一天該開哪幾個頻道，以及這整套每個月大概要花多少錢（示意估算）。

---

## 一、為什麼 24/7 直播是維運問題

一支影片上傳後就不會壞；一條直播每秒都可能壞。它的輸入是一台持續運轉的電腦、一條持續上傳的網路、一個會記憶體洩漏的應用程式，輸出是一條 YouTube 只給你幾十秒寬限的 RTMPS 連線。只要其中任何一環停了，頻道就從「24/7」變成「上次直播：6 小時前」，搜尋排名和觀眾習慣會跟著一起掉。

把整條管線攤開來看，會發現內容只佔最左邊一格：

```
 素材                 OBS Studio                     YouTube
┌──────────┐   ┌──────────────────────────┐   ┌──────────────────┐
│ 音樂播放  │──▶│ Scene                    │   │ RTMPS ingest     │
│ 列表(VLC)│   │  ├ Media Source(影片循環) │   │                  │
├──────────┤   │  ├ Browser Source(時鐘)  │──▶│ 轉碼 → 播放器     │
│ 視覺循環  │──▶│  ├ Image(Logo)          │   │                  │
│ 影片 mp4 │   │  └ Text(標題)           │   └────────┬─────────┘
└──────────┘   │ Encoder: NVENC/x264      │            │
               │ CBR 6000 kbps, 1080p30   │            ▼
               └────────────┬─────────────┘   ┌──────────────────┐
                            │ obs-websocket   │ YouTube Studio   │
                            ▼ :4455           │ Stream health    │
               ┌──────────────────────────┐   └──────────────────┘
               │ watchdog.py              │
               │  每 60s 查狀態 → 自動重啟 │──▶ Discord #alerts
               │  每日 04:00 排程重啟      │
               └──────────────────────────┘
```

左邊兩格是三個系列各自處理的事；從 OBS 往右，到看門狗和告警，就是這篇的範圍。

---

## 二、編碼器與位元率

### 直覺

位元率是你每秒送出多少資料。太低畫面糊、太高家裡的上傳頻寬撐不住而掉幀。音樂直播的畫面幾乎靜止（緩慢的循環影片），所以不需要遊戲直播那種高位元率，但 YouTube 轉碼時希望看到**穩定**的輸入，所以寧可固定、不要浮動。

### 設定

```
Settings → Output → Output Mode: Advanced

Encoder:        NVIDIA NVENC H.264（有 NVIDIA 顯卡）
                AMD AMF H.264（AMD 顯卡）
                x264（純 CPU；1080p30 約吃 30–50% CPU）
Rate Control:   CBR
Bitrate:        6000 Kbps（1080p30）；網路不穩降到 4500
Keyframe Int.:  2 s（YouTube 建議值）
Preset:         Quality（NVENC）／ veryfast（x264）
Profile:        high
B-frames:       2
Look-ahead:     關閉（增加延遲，對靜態畫面無益）

Settings → Video
Base / Output:  1920x1080 → 1920x1080；效能不足改 1280x720 + 3000–4500 Kbps
FPS:            30（音樂直播不需要 60）
Downscale:      Lanczos

Settings → Audio
Sample Rate:    48 kHz，Stereo
Mic/Aux:        Disabled（音樂頻道不需要麥克風）
Audio Bitrate:  160 Kbps

Audio Mixer → Filters（音樂來源上）
Compressor:     Ratio 3:1, Threshold -18 dB, Attack 6 ms, Release 60 ms
Limiter:        Threshold -1.0 dB（防止破音）
音量目標:        表頭在 -6 dB 附近擺動，峰值不碰 0 dB
```

兩個最常被改錯的值：Rate Control 選了 VBR（YouTube 會顯示「串流品質不穩」），和 Keyframe Interval 留 0（自動）讓 YouTube 轉碼切片不對齊。

### 數字：位元率換算成流量

6,000 kbps 聽起來不大，乘上 24 小時 × 30 天就是另一回事。這筆帳決定了下一節的主機選擇：

| 影像位元率 | 每秒 | 每日 | 每月（30 天） |
|---|---|---|---|
| 3,000 Kbps | 0.375 MB | 32 GB | ≈ 0.97 TB |
| 4,500 Kbps | 0.56 MB | 49 GB | ≈ 1.46 TB |
| **6,000 Kbps** | 0.75 MB | 65 GB | **≈ 1.94 TB** |

算法：6,000,000 bit/s ÷ 8 × 86,400 s × 30 ≈ 1.94 × 10¹² byte。音訊 160 Kbps 另外加約 52 GB/月。所以「1080p30 的 24/7 串流 ≈ 每月 2 TB 上傳」是你要記住的一個數。

### 限制

- 家用上傳頻寬要有**位元率的兩倍**餘裕（6 Mbps 串流 → 至少 12 Mbps 穩定上傳），否則晚間鄰居用網尖峰時會掉幀。
- 內容若是 4K 素材（深海系列的視覺管線），仍然輸出 1080p：YouTube 直播 4K 需要 13,000–34,000 Kbps，流量成本乘以 3–5 倍，而觀眾多半在手機上以 720p 收看。
- x264 在無獨顯的機器上跑 24/7 會持續佔用 CPU，溫度與風扇噪音都是維運成本；能用硬體編碼就用硬體編碼。

### 連上 YouTube

```
YouTube Studio → 建立 → 直播 → 串流
  Title / Description / Category: Music（各系列自己的 SEO 範本）
  Stream latency: Low latency；DVR: Enable
  第一次啟用直播需驗證電話，等待 24 小時
  複製串流金鑰（xxxx-xxxx-xxxx-xxxx）

OBS → Settings → Stream
  Service: YouTube - RTMPS
  Server:  Primary YouTube ingest server
  Stream Key: 貼上
  ☑ Enable Auto-Reconnect, Retry Delay 2 s, Maximum Retries 30

OBS → Settings → Advanced
  Stream Delay: 0；Automatically Reconnect: 啟用
```

第一次先把 Visibility 設為 Unlisted 跑 30 分鐘，用手機開連結確認畫面、音訊、時鐘與文字都正常，再改 Public。Auto-Reconnect 處理的是幾秒鐘的網路抖動；更長的中斷交給第五節的看門狗。

---

## 三、主機：家用電腦、Mac mini、Raspberry Pi 還是雲端

主機只有兩件事要做：穩定跑 OBS，和穩定把每月 2 TB 送出去。四個選項各自卡在不同的地方：

| 選項 | 月費（示意） | 編碼 | 流量 | 卡在哪 |
|---|---|---|---|---|
| 現有家用 PC + UPS | 電費 ≈ 70 kWh | NVENC 可用 | 家用網路免費 | 機器不能拿來做別的事；上傳頻寬 |
| Mac mini（M 系列） | 一次性約 $600 | 硬體 H.264 | 家用網路免費 | 低功耗、安靜；仍受家用上傳限制 |
| Raspberry Pi 5 | 一次性約 $80 | 軟體編碼，720p 極限 | 家用網路免費 | 只適合驗證概念，不建議正式 24/7 |
| 雲端 VPS | $5–40 + 流量 | 多半無 GPU，x264 | **2 TB 對外流量要算錢** | 流量費與 CPU 額度 |

### 雲端的兩個陷阱

**突發型 CPU。** AWS `t3.medium`（2 vCPU, 4 GB）看起來剛好，月費約 $35，但 t 系列是「突發型」執行個體：每顆 vCPU 的基準額度約 20%，超過的部分靠 CPU credit 支付。x264 1080p30 編碼持續吃 60% 以上，credit 幾小時內耗盡，之後執行個體被壓回基準額度，表現就是**掉幀持續上升、OBS 顯示 Encoding Lag**。要用雲端就選非突發型（c 系列、或 Hetzner / DigitalOcean 的專用 vCPU 方案），或接受 `unlimited` 模式的額外計費。

**對外流量。** 以 AWS 標準計價（前 10 TB 約 $0.09/GB，扣除每月免費額度）估，1.94 TB 對外流量約 $160–175/月，是主機費的四到五倍。歐洲 VPS 商（例如 Hetzner）多半含 20 TB 流量，同樣的串流流量費接近零。先用官方計價工具算流量，再看主機。

### 決策

```
有一台能插電 24 小時的機器 + 上傳 ≥ 12 Mbps？
├─ 是 → 家用 PC / Mac mini + UPS（最便宜，先從這裡開始）
└─ 否 → 雲端 VPS
        ├─ 選含流量的方案（Hetzner 類）→ x264 veryfast, 720p 或 1080p
        └─ 非得用 AWS → 非突發型執行個體 + 先算 egress
```

翻轉條件：當頻道月收入穩定超過主機費加流量費（示意：$200），或家中斷電／斷網已經造成兩次以上的離線事故，就值得搬到雲端。

---

## 四、obs-websocket：把 OBS 變成可程式化的東西

OBS 28 起內建 obs-websocket 5.x，不需要另外裝外掛。開啟：`工具 → WebSocket Server Settings → Enable WebSocket server`，預設 port **4455**，務必啟用驗證並設密碼。之後任何語言都能問 OBS「你在串流嗎」、「目前場景是什麼」，也能叫它「開始串流」、「切到 Scene B」。

Python 端用 `obsws-python`（`pip install obsws-python`）。幾個你會一直用到的呼叫：

```python
import obsws_python as obs

ws = obs.ReqClient(host="localhost", port=4455, password="…", timeout=5)

status = ws.get_stream_status()
status.output_active            # True = 正在串流
status.output_skipped_frames    # 編碼器累計掉幀
status.output_total_frames

stats = ws.get_stats()
stats.active_fps                # 應該貼著 30
stats.cpu_usage                 # OBS 行程的 CPU %
stats.render_skipped_frames

ws.start_stream()               # 等同按下 Start Streaming
ws.set_current_program_scene("Night Mode")
```

這層 API 的價值不在單一指令，而是讓第五節的看門狗能「先問、再修、修不好才重啟」，而不是每次異常都粗暴殺行程。

另外兩個不用寫程式的自動化：

- **多場景輪播**：Advanced Scene Switcher 外掛的 Sequence 功能，設定每個場景播放時間與淡入淡出，勾選 Loop。深海系列用它每 30 分鐘換一個海域。
- **命令列啟動旗標**：`obs --startstreaming --profile "<Profile>" --collection "<Scene Collection>" --scene "<Scene>"`，讓排程重啟後 OBS 自己開始串流，不需要人按按鈕。

---

## 五、看門狗與告警：讓串流自己爬起來

### 直覺

一條 24/7 串流有三種死法：OBS 行程還在但串流輸出停了（最常見，網路抖一下）、OBS 整個卡死或崩潰、機器本身重開機。一支看門狗要能分辨這三種，用最輕的手段修復，並且**只在狀態改變時**通知你——每五分鐘一則「串流正常」的訊息，一週後你就會把頻道靜音，然後錯過真正的事故。

### 機制

```
          ┌──────────────── 每 60 s ────────────────┐
          ▼                                         │
   ┌─────────────┐  連不上   ┌──────────────────┐   │
   │ 連 websocket │─────────▶│ OBS 行程存在？    │   │
   └──────┬──────┘          └───┬──────────┬───┘   │
          │ 連上               否│          │是(卡死) │
          ▼                     ▼          ▼        │
   ┌─────────────┐        ┌──────────────────┐      │
   │ output_     │  否    │ 重啟 OBS 行程     │      │
   │ active?     │───┐    │ (--startstreaming)│      │
   └──────┬──────┘   │    └────────┬─────────┘      │
          │是        ▼             │                │
          │   ┌─────────────┐      │                │
          │   │ start_stream│      │                │
          │   │ 失敗 3 次 → │──────┘                │
          │   │ 重啟行程     │                       │
          │   └─────────────┘                       │
          ▼                                         │
   ┌─────────────┐  狀態改變時                       │
   │ 記錄狀態     │────────────▶ Discord #alerts     │
   └──────┬──────┘  (OK→DOWN, DOWN→OK)              │
          └─────────────────────────────────────────┘
```

兩條獨立的防線：

1. **排程重啟**（每日 04:00，流量最低時段）：OBS 長時間運行會累積記憶體，與其等它崩，不如每天主動重開一次，整個中斷約 20 秒。
2. **看門狗迴圈**：每 60 秒查一次狀態，處理排程之外的意外。

### 排程重啟

macOS / Linux 用 cron：

```bash
# crontab -e
0 4 * * * /usr/local/bin/restart_obs.sh >> /var/log/obs_restart.log 2>&1
```

```bash
#!/bin/bash
# restart_obs.sh — 每日定時重啟，重啟後自動開始串流
PROFILE="Music 24/7"
SCENE="Main"

pkill -x OBS 2>/dev/null || pkill -x obs 2>/dev/null
sleep 10

if [[ "$(uname)" == "Darwin" ]]; then
  open -a OBS --args --startstreaming --profile "$PROFILE" --scene "$SCENE"
else
  nohup obs --startstreaming --profile "$PROFILE" --scene "$SCENE" >/dev/null 2>&1 &
fi
echo "$(date -Is) restarted"
```

Windows 用工作排程器（Task Scheduler）每天 04:00 執行同樣邏輯的批次檔：

```batch
@echo off
taskkill /IM obs64.exe /F
timeout /t 10
start "" "C:\Program Files\obs-studio\bin\64bit\obs64.exe" --startstreaming --profile "Music 24/7" --scene "Main"
```

### 看門狗（示範用，未在生產環境驗證）

```python
# watchdog.py — 每 60 s 檢查 OBS 串流，先軟修復、再硬重啟，狀態改變才告警
import os, subprocess, sys, time
from datetime import datetime
import requests
import obsws_python as obs

OBS = dict(host="localhost", port=4455, password=os.environ["OBS_PASSWORD"], timeout=5)
WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]      # Discord #alerts 頻道的 webhook
RESTART_SCRIPT = "/usr/local/bin/restart_obs.sh"
INTERVAL = 60
MAX_SOFT_RETRIES = 3

def alert(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        requests.post(WEBHOOK, json={"content": f"[{ts}] {msg}"}, timeout=10)
    except requests.RequestException as e:
        print(f"alert failed: {e}", file=sys.stderr)

def hard_restart() -> None:
    subprocess.run([RESTART_SCRIPT], check=False)

def check() -> str:
    """回傳 'OK' / 'RECOVERED' / 'DOWN'。"""
    try:
        ws = obs.ReqClient(**OBS)
    except Exception:
        hard_restart()                       # 連不上 websocket：行程不在或卡死
        return "DOWN"

    status = ws.get_stream_status()
    if status.output_active:
        stats = ws.get_stats()
        if stats.active_fps < 25 or stats.cpu_usage > 85:
            alert(f"degraded: fps={stats.active_fps:.0f} cpu={stats.cpu_usage:.0f}% "
                  f"skipped={status.output_skipped_frames}")
        return "OK"

    for _ in range(MAX_SOFT_RETRIES):        # 行程在、串流停：先軟修復
        try:
            ws.start_stream()
            time.sleep(15)
            if ws.get_stream_status().output_active:
                return "RECOVERED"
        except Exception:
            time.sleep(5)
    hard_restart()
    return "DOWN"

def main() -> None:
    last = "OK"
    alert("watchdog started")
    while True:
        state = check()
        if state != last:                    # 只在狀態改變時打擾人
            alert({"DOWN": "stream DOWN, restart issued",
                   "RECOVERED": "stream recovered via start_stream()",
                   "OK": "stream back to OK"}[state])
        last = "OK" if state == "RECOVERED" else state
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
```

讓它跟著開機啟動：Linux 用 systemd service（`Restart=always`），macOS 用 launchd plist，Windows 用工作排程器「登入時」觸發。看門狗自己也會死，所以第三道防線是 YouTube 端：YouTube Studio 的「串流健康狀態」和你手機上的頻道訂閱通知，都是免費的外部監控。

### 症狀 → 診斷

看門狗只會告訴你「壞了」；以下是 OBS 底部狀態列和 YouTube Studio 上能看到的訊號與對應原因：

| 看到什麼 | 多半是 | 先試 |
|---|---|---|
| Dropped frames (network) 持續 > 1% | 上傳頻寬不足、WiFi | 降 Bitrate 500–1000；改有線 |
| Encoding lag、FPS 掉到 20 以下 | CPU 不夠（x264、突發型 VPS） | 改 NVENC；720p；換非突發型執行個體 |
| Render lag | 太多 Browser Source、GPU 驅動 | 關掉不必要的 Browser Source；更新驅動 |
| 畫面凍結但 YouTube 顯示在線 | OBS 卡死、Media Source 檔案問題 | 看門狗硬重啟；檢查循環影片檔 |
| 音畫不同步 | Media Source 與音訊來源不同步 | 改用 VLC Video Source；調 Sync Offset |
| YouTube「串流品質不穩」 | VBR、Keyframe 不是 2 s | 回到第二節的設定 |
| 每天固定時間離線 | 自己的排程重啟撞到 ISP 維護或系統更新 | 改時間；關閉自動更新 |

---

## 六、疊加層：時鐘與資訊卡

OBS 的 Browser Source 可以載入本機 HTML，等於一塊可以用 CSS/JS 畫的透明畫布。時鐘是最常見的用途，也是觀眾判斷「這是不是真的直播」的視覺線索。

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { margin: 0; padding: 20px; background: transparent;
           font-family: Arial, sans-serif; }
    #clock { font-size: 48px; font-weight: bold; color: #fff;
             text-shadow: 2px 2px 8px rgba(0,0,0,.8); }
  </style>
</head>
<body>
  <div id="clock"></div>
  <script>
    function tick() {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      document.getElementById('clock').textContent = hh + ':' + mm;
    }
    setInterval(tick, 1000);
    tick();
  </script>
</body>
</html>
```

Browser Source 設定：`Local file` 勾選並指向 `clock.html`，Width 300、Height 100、FPS 30，勾 `Shutdown source when not visible` 與 `Refresh browser when scene becomes active`，放右上角。

同一個骨架改幾行就是 25/5 番茄鐘倒數：把 `tick()` 換成每秒遞減 `remaining`，歸零時在 `25 * 60` 與 `5 * 60` 之間切換並更新標籤文字（Focus / Break）。ADHD 系列用這個版本；深海系列用純時鐘；Synthwave 系列把字型換成 Orbitron 並加霓虹外框。

一個維運面的提醒：每個 Browser Source 都是一個 Chromium 行程，吃記憶體也可能吃 GPU。時鐘加標題卡兩個就夠，不要為了裝飾開到五個——第五節的 Render lag 多半從這裡來。

---

## 七、Discord：伺服器骨架與機器人

三個系列的 Discord 伺服器長得幾乎一樣，因為音樂直播社群的需求一樣：知道直播在哪、聊天、點歌、一起專注、以及一個付費會員才看得到的角落。先開這個最小骨架，等某個頻道每天有十則以上訊息再拆分：

```
📢 公告
├── #announcements   直播更新、新曲發佈（只有管理員能發）
├── #rules           社群規則
└── #faq

💬 聊天
├── #general
├── #introductions
└── #off-topic

🎵 音樂
├── #requests        點歌
└── #feedback        回饋與建議

🎯 共學（語音）
├── 🔇 Silent Study 1 / 2    靜音共學
└── 🗣️ Casual Hangout

💎 會員專屬（YouTube Membership / Patreon 連動）
├── #vip-lounge
└── #early-access    新曲提前試聽、獨家下載

🤖 系統
├── #bot-commands    避免洗版
└── #alerts          看門狗告警（私人，只有管理員）
```

每個系列再加自己的主題頻道：ADHD 加 `#adhd-support` 與 `#productivity-tips`；深海系列加 `#ocean-lovers`、`#space-enthusiasts`；Synthwave 加整個開發者專區（`#code-help`、`#project-showcase`、`#algorithm-challenge`）。

### 機器人

| 機器人 | 做什麼 | 設定重點 |
|---|---|---|
| MEE6 | 等級系統，獎勵活躍 | 每分鐘活躍 15–25 XP；Lv 5 給 @Active Member、Lv 10 點歌優先 |
| Dyno | 歡迎訊息、自動身份組、垃圾訊息過濾、自訂指令 | `!stream` 回直播連結、`!music` 回播放列表 |
| 番茄鐘 bot（任一款） | `/pomodoro start 25` 集體計時、語音頻道自動靜音、個人統計 | 綁在共學語音頻道 |
| Webhook | 看門狗告警進 `#alerts`；YouTube 新影片／開播通知進 `#announcements` | 一條 URL 就夠，不需要自己寫 bot |

規則只要五條，放在 `#rules` 並要求新成員先讀：尊重所有人、禁廣告、不提供醫療或法律建議（鼓勵諮詢專業）、保持主題相關、尊重版權。管理團隊先是你自己，社群超過幾百人後從最活躍成員中找 2–3 位 moderator，依時區輪班。

---

## 八、Shorts 批次流程

Shorts 是這三個系列共同的導流引擎，而做 Shorts 的瓶頸從來不是創意，是每天打開剪輯軟體的那股阻力。解法是把一週的量壓進一個下午：

```
週日批次日（約 7 小時）

上午 3 h  ┌ 從素材庫挑 21 段 15–20 s 的畫面（直播畫面截取或視覺庫）
          ├ 寫 21 句文字覆蓋（同一主題換不同切入句）
          └ 每段配 15–20 s 的音樂片段

下午 3 h  ┌ CapCut 建一個 9:16 模板專案：文字樣式、音量、淡出、色調
          ├ 複製模板 21 次，只換畫面與文字
          └ 匯出 1080×1920、30 fps、MP4

晚上 1 h  ┌ 逐一確認音畫同步與文字出現時機（關鍵字在前 3 秒）
          └ 上傳到 YouTube Studio，用「排程發佈」排到下週
```

發佈節奏固定在每天 3 則、三個時段（例如目標市場的早晨通勤、午休、晚間），而不是追求某個「最佳時間」；上線兩週後用 YouTube Studio 的「觀眾何時在線上」報表調整時段。每則描述固定帶直播間連結與 Discord 邀請。

內容類型的配比（氛圍、科普、共鳴、對比）是每個系列自己的事，請回各系列的 Shorts 章節。這裡只管「21 則怎麼在一天內做完、怎麼排一週」。

---

## 九、贊助提案：媒體包與第一封信

品牌贊助是三個系列變現路徑的最後一站，而第一封信的結構在任何利基都一樣：誰、多少人、他們是誰、為什麼適合你的產品、下一步。先備妥媒體包（Media Kit，一份 5–7 頁的 PDF），信本身只要能讓對方想打開附件就夠。

媒體包的頁面順序：頻道概覽與定位 → 數據（訂閱、月觀看、平均 CCV、平均觀看時長，**全部取自 YouTube Studio 並標註日期**）→ 觀眾輪廓（年齡、地區、興趣）→ 參與度（留言率、Discord 活躍）→ 合作方案（三個層級：Logo 露出／描述欄連結、專屬 Shorts、整合套裝）→ 過往案例（如有）→ 聯絡方式。

```
Subject: Partnership Opportunity — [頻道名稱] ([主題] 24/7 community)

Hi [Name],

I'm [你的名字], creator of [頻道名稱], a 24/7 YouTube livestream for
[一句話描述受眾：e.g. ADHD listeners who need focus music /
developers who code to synthwave] with [X] subscribers and
[Y] monthly views (YouTube Studio, [月份 年份]).

Our audience:
• [年齡層] based mainly in [地區]
• Average watch time [Z] min per session
• [N] members in our Discord community

I think [品牌] 's [產品] fits what they are already doing while they
listen. Three ways we could work together:
1. [方案 A：Logo on stream + description link]
2. [方案 B：dedicated Shorts]
3. [方案 C：community integration / discount code]

The attached media kit has the full numbers. Would you be open to a
15-minute call next week?

Best regards,
[名字] · [Email] · [頻道連結]
```

談判時的三個不要：不要接受「曝光」當報酬、不要簽獨家條款、不要在第一封信就報價——先問對方的預算區間。報價以你實際的 CCV 與觀看時長為基礎，而不是訂閱數；合約期先談 3 個月，雙方都有退場空間。

---

## 十、成本表（示意估算）

以下是把整套堆疊跑起來的每月固定成本，依主機方案分三欄。**示意估算，2026 年 10 月的大致行情，非報價**；AI 音樂與視覺工具的訂閱屬於各系列的內容成本，不在此表。

| 項目 | 家用 PC / Mac mini | 含流量 VPS（Hetzner 類） | AWS t3.medium |
|---|---|---|---|
| 主機 | 電費 ≈ 70 kWh（≈ $10） | $10–25 | ≈ $35 |
| 對外流量 2 TB | 家用網路，$0 | 含 20 TB，$0 | ≈ $160–175 |
| UPS | 一次性 $80–150 | — | — |
| 看門狗 / 告警 | $0（自架） | $0 | $0（或 CloudWatch ≈ $10） |
| Discord + bots | $0 | $0 | $0 |
| Restream 多平台（可選） | $20 | $20 | $20 |
| **每月合計** | **≈ $10–30** | **≈ $10–45** | **≈ $200+** |

這張表說明了第三節的結論：對一個還沒有收入的頻道，家裡那台電腦加一顆 UPS 是正確起點；雲端只有在選對供應商、或頻道已經能付自己的帳單時才划算。

---

## 總結

- 24/7 直播是維運問題：內容做完只是開始，之後的每一天都在和記憶體洩漏、網路抖動和凌晨三點的離線對抗。
- 編碼器三個值記住就好：CBR、6,000 Kbps、Keyframe 2 s；它們換算成每月約 2 TB 上傳，主機要以這個數字來選。
- 自癒分三層：每日排程重啟、obs-websocket 看門狗先軟後硬、YouTube 端作為外部監控；告警只在狀態改變時發。
- Discord 骨架、Shorts 批次日、贊助信結構在三個利基之間完全可重用，差異只在主題頻道名稱和受眾描述。
- 先用家裡的電腦跑三個月，有收入再搬雲端，而且搬之前先算流量費。

## 相關文章

- [ADHD 友善專注音樂頻道實作指南](/posts/adhd-focus-music-streaming-implementation-guide-zh/)
- [AI 深海/太空環境音串流實戰（一）：市場分析、科學原理與 AI 工具選擇](/posts/ai-ocean-space-ambient-streaming-part1-foundation-zh/)
- [AI 深海/太空環境音串流實戰（三）：OBS 設定、串流上線與自動化監控](/posts/ai-ocean-space-ambient-streaming-part3-technical-zh/)
- [Synthwave 讀書會串流實戰（一）：80 年代復古文化、市場分析與目標受眾定位](/posts/synthwave-study-streaming-part1-market-culture-zh/)
- [AI 音樂生成基礎架構（AWS CDK）](/posts/ai-music-generation-aws-cdk-infrastructure/)
