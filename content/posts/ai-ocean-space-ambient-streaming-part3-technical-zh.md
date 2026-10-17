---
title: "AI 深海/太空環境音串流實戰（三）：OBS 設定、串流上線與自動化監控"
date: 2026-01-18T18:00:00+08:00
draft: false
weight: 3
authors: ["yen"]
categories: ["all", "business", "creative"]
tags: ["OBS", "串流", "技術設定", "自動化", "監控", "YouTube直播", "24/7", "Streaming"]
description: "系列第三篇：把音頻與 4K 視覺組裝成 OBS 場景、設定多場景輪播並完成上線檢查；編碼參數、自動重啟與監控見共用基礎建設篇。"
readTime: "14 min"
---

在前兩篇中，我們掌握了音頻生成和視覺製作。本篇把素材組裝成 OBS 場景、設定多場景輪播，並完成上線前的檢查。編碼參數、主機選擇、自動重啟與監控這些跨系列相同的部分，已獨立成 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/)，本篇只保留深海／太空頻道自己的設定。

## 🖥️ 硬體需求

家用 PC + UPS、Mac mini、Raspberry Pi 與雲端 VPS 的比較、t3.medium 突發型 CPU 的陷阱、以及 6,000 Kbps 換算成每月約 1.9 TB 對外流量的計算，見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「主機」一節。深海／太空頻道的差別只有一個：視覺素材是 4K 影片，解碼比 1080p 素材更吃 CPU／GPU，Media Source 請勾選「Use hardware decoding when available」，而輸出仍維持 1080p30——YouTube 直播 4K 的流量成本是 3–5 倍，手機觀眾多半以 720p 收看。

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

`clock.html` 與 Browser Source 的設定（300×100、FPS 30、Shutdown when not visible）見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「疊加層」一節。深海頻道用純時鐘版本，放右上角；四個場景共用同一個 Browser Source（在 Sources 面板「Add Existing」），不要各做一份。

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

### 輸出、影片與音頻設定

Encoder（NVENC／AMF／x264）、CBR 6,000 Kbps、Keyframe 2 s、1080p30、48 kHz、Compressor 3:1 與 Limiter -1 dB 的完整設定，見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「編碼器與位元率」一節。環境音沒有鼓點與瞬態，Compressor 幾乎不會動作；真正要盯的是 Limiter——層疊的低頻海流聲在某些曲目會把峰值推到 0 dB。

---

## 📡 連接 YouTube

串流金鑰、RTMPS 設定、Auto-Reconnect 與先用 Unlisted 測試 30 分鐘的流程，見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「連上 YouTube」一節。建立串流時 Title 用「Deep Ocean Ambience 24/7 🌊 …」、Description 用系列第一篇的 SEO 範本、Category 選 Music、DVR 開啟，並且不要勾選自動開始——多場景輪播要先在 OBS 裡確認四個場景都切得過去。

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

### 自動重啟與健康監控

每日 04:00 的排程重啟、`--startstreaming --profile "Ocean Space" --scene "Deep Ocean"` 啟動旗標、obs-websocket（OBS 28+，port 4455）看門狗、Discord `#alerts` 告警與 CloudWatch 選項，見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「看門狗與告警」一節。深海頻道唯一要加的檢查：看門狗重啟 OBS 之後，Advanced Scene Switcher 的輪播不一定會自己恢復，請在外掛的 General 分頁勾選隨 OBS 啟動（autostart），否則重啟後會停在單一場景。

---

## 🔧 故障排除

掉幀、Encoding lag、畫面凍結、音畫不同步、「串流品質不穩」等症狀對應的原因與處理，整理成一張症狀→診斷表放在 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/) 的「看門狗與告警」一節。深海頻道特有的一條：4K 循環影片在場景切換瞬間 Render lag 會短暫上升，屬正常；若持續不降，先把 Media Source 改為硬體解碼，再考慮把素材先轉成 1080p 再丟進 OBS。

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

## 🎓 進階與效能基準

雙 PC／NDI、Restream 多平台、低延遲設定，以及 OBS 效能的健康門檻（CPU < 60%、Render／Encoding lag 0%、Dropped frames < 0.5%、FPS 貼著 30），見 [24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/)。深海頻道以 4K 素材解碼 + NVENC 編碼為前提，GPU 使用率的目標放寬到 < 70%。

---

## 🔄 系列文章導航

1. [市場分析、科學原理與 AI 工具選擇](/posts/ai-ocean-space-ambient-streaming-part1-foundation-zh/)
2. [視覺製作：4K 深海/太空場景生成](/posts/ai-ocean-space-ambient-streaming-part2-visual-zh/)
3. **【當前】技術實作：OBS 設定、串流上線與自動化** ✅
4. [內容策略：Shorts 導流、社群經營與變現](/posts/ai-ocean-space-ambient-streaming-part4-growth-zh/)
- 共用基礎建設：[24/7 音樂直播共用基礎建設：編碼器、自癒串流、監控與社群管線](/posts/music-streaming-247-infrastructure-zh/)

下一篇也是最終篇，我們將探討如何透過 Shorts 導流、社群經營、以及多元變現策略，將你的頻道從 0 發展到月入數千美元。

---

## 延伸閱讀

- [AI 深海/太空環境音串流實戰（一）：市場分析、科學原理與 AI 工具選擇](/posts/ai-ocean-space-ambient-streaming-part1-foundation-zh/)
- [AI 深海/太空環境音串流實戰（二）：4K 視覺製作與動態場景生成](/posts/ai-ocean-space-ambient-streaming-part2-visual-zh/)
