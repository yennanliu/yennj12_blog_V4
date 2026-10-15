---
title: "AI 工程從零開始｜Phase 6 Part 2：語音合成與音訊模型 — 讓機器開口說話"
date: 2026-06-21T15:00:00+08:00
draft: false
weight: 13
description: "深入解析 TTS 工程架構：Tacotron/FastSpeech/VITS 聲學模型、聲碼器設計、情感語音合成、音樂生成與即時語音克隆系統"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Speech", "TTS", "Audio", "Voice Cloning", "Music Generation", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "12 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師把 TTS 當成「呼叫 API、播放音訊」的黑箱。*
> *真正的 AI 工程師理解聲學模型與聲碼器的分工、延遲來源、以及為何同一句話用不同架構品質差距達 0.8 MOS。*
> *他們能設計零樣本語音克隆系統、控制情感韻律、並在 200ms 內完成整條推論鏈。*
> *本文帶你從模型架構到線上服務，逐層拆解語音合成工程的每一個決策點。*

---

這篇給用過 TTS API、但還沒拆開過聲學模型與聲碼器分工的工程師看。讀完你會能說明 Tacotron2 → FastSpeech2 → VITS 各自解決了什麼問題、聲碼器為什麼從 WaveNet 走到 HiFi-GAN 與 Vocos、零樣本語音克隆的 speaker embedding 是怎麼注入的，並能為一個「繁中／英文雙語、30 秒樣本克隆、端對端延遲 < 300ms」的有聲書產品切出延遲預算，決定該把哪個環節做成串流。

---

## 一、核心問題：語音合成的工程挑戰

語音合成表面上是「文字轉音訊」，但工程挑戰遠比想像中複雜：

**三大矛盾張力**

| 維度 | 極端 A | 極端 B | 工程取捨 |
|------|--------|--------|----------|
| 自然度 vs 延遲 | Tortoise-TTS（MOS 約 4.2）推論 30s | FastSpeech2 < 50ms | 互動場景選速度，有聲書選品質 |
| 個人化 vs 資料量 | 傳統 clone 需 1 小時錄音 | XTTS v2 只需 6 秒樣本 | 零樣本 clone 改變商業模式 |
| 表達力 vs 穩定度 | 情感模型偶爾產生雜音 | 平坦語調安全但無趣 | 情感強度需可調參數 |

**延遲分解（300ms 預算）**

```
文字前處理（正規化/分詞）：  ~10ms
G2P（字素轉音素）：          ~15ms
聲學模型（Mel 頻譜生成）：   ~80ms   ← 最大瓶頸
聲碼器（Mel → 波形）：       ~60ms
音訊編碼/傳輸：              ~30ms
緩衝播放首包：               ~20ms
─────────────────────────────────
總計：                       ~215ms  ✓ 低於 300ms
```

**核心工程問題清單**

1. 聲學模型如何從 Tacotron 自回歸演進到 FastSpeech 非自回歸？
2. 聲碼器 WaveNet vs HiFi-GAN：品質差多少、速度差多少？
3. 零樣本克隆的 speaker embedding 如何注入？
4. 情感控制向量（VAE latent）如何不破壞音素對齊？
5. 串流輸出（chunked TTS）如何降低首包延遲至 < 100ms？

---

## 二、何時該升級：從預訓練 VITS Demo 到串流 TTS 服務的觸發條件

一台 GPU 上跑 Hugging Face 的預訓練 VITS（或 Coqui TTS），整句生成完再回傳 wav，就足以驗證音質能不能接受、克隆功能跑不跑得通；它的代價是首包延遲等於整句的生成時間（1–3 秒），而且沒有串流、沒有情感控制、克隆只支援固定幾個說話人。該升級的訊號不是日活數字，而是**延遲預算被整句生成吃光**：一旦產品要求首包 < 300ms，或使用者要邊聽邊生成，就必須把聲學模型換成非自回歸的 FastSpeech2（所有 Mel 幀可並行）、把聲碼器換成能逐 chunk 輸出的 HiFi-GAN，讓首包只等第一個 chunk 而不是整句——這一步同時把重複句子的 Mel 頻譜與 speaker embedding 放進 Redis，省掉重算。

第二道門檻是**單一路線無法同時滿足兩種 SLA**：互動語音要 < 100ms 首包，有聲書要 MOS > 4.3，而 VITS2 + Vocos 的高品質線（120–200ms）與 FastSpeech2 的高速線（< 50ms）本來就是不同模型。當兩種請求都成為正式產品、且任一種的 P99 開始違約時，才值得把路由層、音樂生成線與 Spot GPU 混合機型一起補上；在那之前，多養一套模型只是多一倍維運。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| 單機預訓練 VITS，整句生成後回傳 | FastSpeech2 + HiFi-GAN，逐 chunk 串流輸出 | 首包延遲要求 < 300ms；整句 1–3 秒的等待成為使用者抱怨主因；同一句子被重複合成（可快取 Mel） |
| 固定說話人 | Speaker encoder（ECAPA-TDNN）+ embedding 快取的零樣本克隆 | 用戶上傳聲音樣本成為產品需求；每次請求重算 embedding（約 150ms）成為延遲主因 |
| 單一路線服務所有請求 | 依任務分流：互動高速線／有聲書高品質線／音樂線 | 互動請求要 < 100ms 首包而有聲書要 MOS > 4.3，單一模型無法兼顧；任一路線 P99 違約 |

---

## 三、聲學模型演進：Tacotron2 → FastSpeech2 → VITS

### 3.1 自回歸瓶頸：Tacotron2

Tacotron2 以 Seq2Seq + Attention 生成 Mel 頻譜，每個時間步依賴前一步輸出，造成：
- 推論時間 O(T)，T = 輸出幀數（典型 5–8 秒文字需 800ms 推論）
- Attention 偶爾錯位（missing/repeating phonemes），品質不穩定
- 無法並行化

### 3.2 非自回歸突破：FastSpeech2

```
┌────────────────────────────────────────────────────────────┐
│  FastSpeech2 架構                                          │
│                                                            │
│  文字/音素序列                                             │
│       │                                                    │
│       ▼                                                    │
│  ┌──────────────┐                                          │
│  │  FFT Block   │  × 4  (Feed-Forward Transformer)        │
│  │  自注意力     │                                          │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐   預測每個音素的持續時間                 │
│  │ Duration     │   → 決定 Mel 幀對齊                      │
│  │ Predictor    │   (Phoneme → Duration lookup)           │
│  └──────┬───────┘                                          │
│         │ 長度調節（可控語速）                              │
│         ▼                                                  │
│  ┌──────────────┐   預測 F0（基頻）和 Energy               │
│  │ Pitch/Energy │   ← 情感控制入口                         │
│  │ Predictor    │                                          │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  FFT Block   │  × 4                                    │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│      Mel 頻譜（可並行生成所有幀）                           │
│                                                            │
│  推論時間：< 50ms（A10G GPU，10 秒文字）                   │
│  vs Tacotron2：~800ms → 16× 加速                          │
└────────────────────────────────────────────────────────────┘
```

**FastSpeech2 關鍵數字**
- Duration predictor 誤差 < 5%，消除 Attention 失對問題
- 語速控制：直接縮放 duration，0.5× – 2.0× 無失真
- MOS：約 4.0（與 Tacotron2 相當，但穩定性更高）

### 3.3 端對端整合：VITS

VITS（Variational Inference with adversarial learning for end-to-end TTS）消除聲學模型與聲碼器的分離訓練問題：

- **VAE**：隱空間 z 對齊文字與音訊，同時捕捉韻律變化
- **Flow**：可逆正規化流，提升 Mel 頻譜品質
- **GAN**：對抗訓練，輸出接近真實波形
- 推論：文字 → 一步到位輸出波形，MOS 4.36（VCTK 基準）
- 代價：推論時間約 120–200ms，比 FastSpeech2 慢 3–4×

| 模型 | 推論延遲 | MOS | 情感控制 | 克隆難度 |
|------|---------|-----|----------|---------|
| Tacotron2 | 800ms | 3.9 | 弱 | 難 |
| FastSpeech2 | < 50ms | 4.0 | 中（F0/Energy） | 中 |
| VITS | 150ms | 4.36 | 強（VAE latent） | 易 |
| VITS2 | 120ms | 4.42 | 強 | 易 |

---

## 四、聲碼器：Griffin-Lim → WaveNet → HiFi-GAN → Vocos

聲碼器負責「Mel 頻譜 → 波形」，品質差距顯著：

| 聲碼器 | 推論速度 | MOS | 原理 | 適用場景 |
|--------|---------|-----|------|---------|
| Griffin-Lim | 即時（CPU） | 3.2 | 迭代相位估計 | 原型/Debug |
| WaveNet | 0.02× 即時 | 4.4 | 自回歸神經網路 | 已淘汰 |
| WaveGlow | 2× 即時 | 4.2 | 正規化流 | 次選 |
| HiFi-GAN V1 | 167× 即時 | 4.2 | GAN + 多週期判別器 | 生產首選 |
| HiFi-GAN V2 | 250× 即時 | 4.1 | 輕量版，精度換速度 | 邊緣設備 |
| Vocos | 200× 即時 | 4.3 | ConvNeXt + ISTFT | 新世代首選 |

**HiFi-GAN 為何是生產首選**
- 167× 即時意味著生成 1 秒音訊只需 6ms
- 多週期判別器（MPD）+ 多尺度判別器（MSD）消除高頻雜音
- 開源、生態完整、fine-tuning 資料需求低（1 小時錄音即可）

**Vocos 的優勢**
- 以 ISTFT（反短時傅立葉）取代直接波形生成，相位估計更穩定
- 在高音質場景 MOS 高於 HiFi-GAN 0.1 分
- 模型參數僅 13.5M，適合邊緣部署

---

## 五、零樣本語音克隆：XTTS/Tortoise 架構

### 5.1 Speaker Embedding 注入機制

傳統 TTS 克隆需要 > 30 分鐘錄音訓練新說話人模型。零樣本克隆的核心突破是將說話人特徵壓縮為向量，在推論時注入：

```
┌─────────────────────────────────────────────────────────┐
│  零樣本語音克隆流程                                      │
│                                                         │
│  ┌─────────────────┐   30秒參考音訊                     │
│  │  參考音訊輸入    │                                    │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐   d-vector / x-vector              │
│  │  Speaker Encoder│   (預訓練 ECAPA-TDNN)              │
│  │  (凍結權重)      │   輸出 256-dim speaker embedding   │
│  └────────┬────────┘                                    │
│           │ speaker_emb                                 │
│           │                        文字輸入             │
│           │                           │                 │
│           ▼                           ▼                 │
│  ┌────────────────────────────────────────────────┐     │
│  │  TTS 聲學模型（VITS/FastSpeech2）              │     │
│  │                                                │     │
│  │  cross-attention(text_enc, speaker_emb)        │     │
│  │  或 AdaIN(speaker_emb) 注入每個 FFT Block     │     │
│  └────────────────────────┬───────────────────────┘     │
│                           │ Mel 頻譜                     │
│                           ▼                             │
│                    HiFi-GAN / Vocos                     │
│                           │ 克隆音訊                     │
│                           ▼                             │
│               保留目標說話人音色的輸出                    │
│                                                         │
│  XTTS v2：6 秒參考音訊，MOS 3.8（克隆評估）             │
│  Tortoise：6 秒樣本，MOS 4.2，但推論 30 秒              │
└─────────────────────────────────────────────────────────┘
```

### 5.2 XTTS v2 vs Tortoise-TTS

| 指標 | XTTS v2 | Tortoise-TTS |
|------|---------|--------------|
| 最少參考音訊 | 6 秒 | 6 秒 |
| 推論時間 | ~2 秒（1 段落） | 30–60 秒 |
| 克隆 MOS | 3.8 | 4.2 |
| 多語言 | 17 種語言 ✓ | 英文為主 |
| 適用場景 | 互動/即時 | 離線有聲書 |

**工程建議**：有聲書場景用 Tortoise 離線批次生成，互動語音助理用 XTTS v2 即時回應。

> **授權與時效提醒（2026）**：Coqui 公司已於 2024 年初結束營運，XTTS v2 權重採 Coqui Public Model License（CPML），**僅限非商業使用**，不能直接用於商業有聲書產品；Tortoise 也已屬舊世代模型。商業專案應改評估授權明確的新一代開源模型（如 F5-TTS、CosyVoice 2、Fish Speech、Kokoro，逐一確認授權條款）或商用 TTS API。讓用戶上傳自己聲音的產品，另需處理本人同意驗證、說話人比對與浮水印，以防冒用他人聲音。
>
> 本文 MOS 數字多為示意估算或不同基準下的概略值，彼此不可直接比較。

### 5.3 Speaker Embedding 快取策略

用戶上傳 30 秒樣本後，提取 speaker embedding 並存入 Redis（TTL 24h），後續請求無需重新提取。提取一次約 150ms，快取命中後節省此延遲。

---

## 六、情感與韻律控制

### 6.1 情感控制的三個層次

**層次 1：F0/Energy 顯式控制（FastSpeech2）**
- 直接調整 pitch（+20% = 更興奮）、energy（+15% = 更有力）
- 可解釋，但情感不自然，像在「調參數」

**層次 2：GST（Global Style Token）**
- 從參考音訊提取全局風格向量，注入聲學模型
- 10–20 個 token，每個對應一種風格（朗讀、新聞播報、對話等）
- 無需情感標籤訓練

**層次 3：VAE 隱空間控制（VITS/NaturalSpeech2）**
- 情感作為 VAE 隱變數的一部分，採樣時可插值
- 「中性 → 喜悅」= 在隱空間線性插值，自然漸變
- MOS 在情感句比 GST 高 0.15 分

### 6.2 韻律控制實務

```python
# FastSpeech2 語速/音調控制範例（偽碼）
output = model.infer(
    text="今天天氣真好",
    speaker_id=0,
    speed=0.9,          # 0.5–2.0，不影響音質
    pitch_shift=+2,     # 半音單位，-12 到 +12
    energy_scale=1.1,   # 能量倍率
)
```

**情感強度校正**：用戶若感知過度誇張，提供 0–1 的情感強度滑桿，線性插值 neutral embedding 與 target emotion embedding。

---

## 七、音樂生成：MusicGen/AudioCraft 架構

### 7.1 AudioCraft 架構概覽

Meta 的 AudioCraft 包含三個子模型：

| 模型 | 用途 | 輸入 | 輸出長度 |
|------|------|------|---------|
| MusicGen | 文字→音樂 | 文字描述 + 可選旋律 | 最長 30 秒 |
| AudioGen | 文字→音效 | 文字描述 | 最長 5 秒 |
| EnCodec | 神經音訊編解碼器 | 波形 | 壓縮 token |

**MusicGen 核心設計**：
- 以 EnCodec 將音訊壓縮為 4 個量化 codebook 的 token 序列
- Transformer decoder 自回歸生成這些 token（類似語言模型）
- 文字條件透過 T5 encoder 提取特徵，以 cross-attention 注入
- 生成 10 秒音樂約需 15 秒（A100），30 秒音樂約需 45 秒

### 7.2 音樂生成工程挑戰

**一致性問題**：自回歸生成可能在 15 秒後轉換風格
→ 解法：使用 continuation 模式，以已生成的最後 2 秒作為 prompt

**版權問題**：生成音樂與訓練資料的相似度檢測
→ 部署前跑 fingerprinting（Shazam 演算法），相似度 > 0.85 拒絕輸出

**延遲不可接受**：45 秒生成不適合互動場景
→ 有聲書背景音樂預先批次生成，互動場景只用 5 秒音效（AudioGen < 3 秒）

---

## 八、為什麼選 X 不選 Y

| 決策 | 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|------|-------------|---------------|----------------|
| **聲學模型** | FastSpeech2 | < 50ms 推論，穩定無 Attention 失對 | Tacotron2：800ms，自回歸無法並行 | 若品質要求 MOS > 4.3 且可接受 200ms，改用 VITS |
| **聲碼器** | HiFi-GAN V1 | MOS 4.2，167× 即時，開源生態完整 | WaveNet：0.02× 即時，生產不可用 | 若 MOS 需再高 0.1 分，改用 Vocos（需評估 fine-tuning 成本） |
| **克隆架構** | XTTS v2（注意：CPML 授權僅限非商業） | 6 秒參考音訊，多語言，~2 秒推論 | Tortoise：推論 30s，不適合即時 | 離線批次有聲書生成用 Tortoise（MOS 更高）；商業產品需改用授權允許商用的模型或 API |
| **情感控制** | VAE latent（VITS） | 自然情感漸變，無需顯式標籤 | GST：情感不夠自然，需手動挑 token | 若訓練資料無情感標注，GST 是唯一選擇 |

---

## 九、系統效應：Before vs After

### 9.1 延遲對比

| 指標 | 預訓練 VITS Demo | FastSpeech2 + HiFi-GAN 串流 | 分流 + VITS2/Vocos |
|------|--------------|--------------|----------------|
| 首包延遲（P50） | 2,000ms | 180ms | 80ms |
| 首包延遲（P95） | 5,000ms | 300ms | 150ms |
| 完整句子延遲（5秒文字） | 3,500ms | 350ms | 200ms |
| 串流支援 | ✗ | ✓ | ✓（chunk 50ms） |

*示意估算，非實測數據*

### 9.2 音質對比

| 指標 | 預訓練 VITS Demo | FastSpeech2 + HiFi-GAN 串流 | 分流 + VITS2/Vocos |
|------|---------|---------|---------|
| MOS（自然度，1–5） | 3.8 | 4.2 | 4.4 |
| MOS（克隆相似度） | N/A | 3.5 | 3.8 |
| 情感表達準確率 | 無 | 60% | 82% |
| 多語言支援 | 僅中文 | 中/英 | 17 語言 |

*示意估算，非實測數據*

### 9.3 成本對比

| 指標 | 預訓練 VITS Demo | FastSpeech2 + HiFi-GAN 串流 | 分流 + VITS2/Vocos |
|------|---------|---------|---------|
| 月成本 | $500 | $3,000 | $12,000 |
| 成本/千字 | $0.05 | $0.008 | $0.004 |
| GPU 使用率 | 15%（浪費） | 65% | 82%（Spot） |
| 快取命中率 | 0% | 30% | 45% |

*示意估算，非實測數據*

**關鍵洞察（示意）**：從串流 MVP 走到分流架構，月成本增加 4×，但日活增加 20×（10K → 200K），單位成本下降 50%。快取命中率每提升 10%，GPU 成本降低約 8%。

---

## 十、系列導航

← 上一篇：[Phase 6 Part 1：自動語音辨識 — 讓機器聽懂人類](/posts/ai-eng-from-scratch-phase6-part1-asr-zh/)

→ 下一篇：[Phase 7 Part 1：Transformer 架構深度解析 — 改變一切的注意力](/posts/ai-eng-from-scratch-phase7-part1-transformer-architecture-zh/)

---

**系列索引**

本文屬於「AI 工程從零開始」系列，涵蓋從基礎 ML 到生產級 AI 系統的完整工程路徑：

- Phase 1：數學基礎（線性代數、機率統計）
- Phase 2：傳統機器學習與集成學習
- Phase 3：深度學習核心
- Phase 4：電腦視覺
- Phase 5：自然語言處理
- **Phase 6：語音 AI**
  - Part 1：自動語音辨識（ASR）
  - **Part 2：語音合成與音訊模型**（本文）
- Phase 7：Transformer 架構與訓練
- Phase 8–19：生成模型、強化學習、從頭構建 LLM、推論與 RAG、多模態、Agent、AI 基礎設施、安全治理與 Capstone
