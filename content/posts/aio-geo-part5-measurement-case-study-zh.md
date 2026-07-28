---
title: "AIO / GEO - Part 5 - 量測與案例篇：建立監測系統與六個月實戰復盤"
date: 2026-08-01T09:00:00+08:00
draft: false
weight: 5
description: "GEO 的最後一哩：設計 prompt set、用 Python 建置多引擎引用監測系統、計算 AI Visibility Score、從伺服器日誌與 GA4 辨識 AI 流量，最後以一個 B2B SaaS 站的六個月完整復盤（含失敗的部分）與 ROI 試算收尾。"
categories: ["AI", "SEO", "GEO", "Analytics", "Case Study", "all"]
tags: ["GEO", "AIO", "監測", "Analytics", "Python", "GA4", "ROI", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
---

> 大多數人的做法：改完網站，等三個月，然後憑感覺說「好像有效」。
> 真正該做的事：在改之前先量基線，改之後每週量一次，把「哪一次改動讓哪一題上升」講清楚。
>
> GEO 最大的風險不是做錯，是做完不知道有沒有用，
> 於是第二季預算被砍掉。

---

## 一、為什麼傳統分析工具在這裡失效

```
你想知道的                     GA4 能告訴你          GSC 能告訴你
──────────────────────────────────────────────────────────────────
ChatGPT 提到我幾次？            ✘                    ✘
Perplexity 引用了我哪一頁？      部分（有 referrer）    ✘
AI Overview 有沒有引用我？       ✘                    ✘（曝光混在一起）
模型怎麼描述我的產品？           ✘                    ✘
競品的引用份額是多少？           ✘                    ✘
```

核心問題：**AI 引用大多不產生可歸因的流量**。

```
使用者旅程的真實樣貌

Day 1   問 ChatGPT「台灣有哪些 OMS 系統」
        → 答案中提到 OrderFlow，附連結
        → 使用者沒有點連結，只是記住了名字
        → GA4：無任何紀錄

Day 4   在 Perplexity 問「OrderFlow 好用嗎」
        → 讀了摘要，點了一個連結
        → GA4：referrer = perplexity.ai（唯一看得到的一次）

Day 11  直接 Google 搜尋「OrderFlow 價格」
        → 點進官網定價頁
        → GA4：Organic Search，query = 品牌詞

Day 14  填表單
        → GA4 歸因：Organic Search / 品牌詞

真正的第一因是 Day 1 的 ChatGPT，但它在報表上完全不存在。
```

**結論**：你必須主動去問模型，而不是被動等流量。這就是監測系統要做的事。

---

## 二、指標體系

### 2.1 主指標：AI Visibility Score

```
AVS = 0.30 × 引用頻率
    + 0.30 × 引用份額
    + 0.25 × 位置加權分
    + 0.15 × 描述正確率

其中：
  引用頻率   = 被引用的題數 / 總題數
  引用份額   = Σ(你的引用數) / Σ(所有品牌的引用數)
  位置加權分 = 平均 1/log2(提及位置 + 1)，位置以「第幾個被提到的品牌」計
  描述正確率 = 對你的事實陳述中正確的比例（需人工或 LLM 標註）
```

### 2.2 輔助指標

```
指標                    定義                          健康值      用途
────────────────────────────────────────────────────────────────────────
Coverage Gap            prompt set 中你完全沒有        < 15%      找內容缺口
                        對應頁面的題數比例

Answer Leakage          被引用但描述有誤的比例          < 10%      找內容歧義
                                                                （比不被引用更嚴重）

Competitor Delta        你的份額 - 最大競品的份額       > 0        競爭態勢

Page Concentration      引用集中在前 3 個 URL 的比例    < 60%      過度集中代表
                                                                其他頁沒發揮

Engine Variance         各引擎間引用率的標準差          < 15pp     差異大代表
                                                                某引擎有技術問題

Brand Search Lift       品牌詞搜尋量的月成長            > 0        GEO 的下游效果
```

**Engine Variance 特別有用**：如果 Perplexity 引用率 32%、ChatGPT 引用率 4%，那幾乎一定是 OAI-SearchBot 被擋了，而不是內容問題。這個指標能把「內容問題」和「技術問題」分開。

---

## 三、Prompt Set 設計

監測系統的品質上限，取決於 prompt set 的品質。

### 3.1 五類問題，各有配額

```
類別            佔比    範例                              量什麼
──────────────────────────────────────────────────────────────────────
① 品類發現      30%    「台灣有哪些訂單管理系統？」          你在不在名單裡
                       「多通路電商用什麼工具管訂單？」       ← 最重要的一類

② 問題解決      25%    「蝦皮和 momo 的訂單怎麼統一管理？」   你的內容有沒有被引用
                       「電商庫存超賣怎麼解決？」

③ 品牌直問      20%    「OrderFlow 是什麼？」               描述正確率
                       「OrderFlow 的定價？」               ← 錯誤最傷的一類

④ 競品比較      15%    「OrderFlow vs 易普印 哪個好？」      競爭位置
                       「OMS 選型該看什麼？」

⑤ 長尾具體      10%    「OrderFlow 支援蝦皮直播訂單嗎？」    深度內容是否被讀到
                       「OMS 導入要多少錢？」
```

### 3.2 數量與變體

```
建議規模：40-60 題（含變體後 120-180 次查詢／輪）

每題要有 2-3 個變體：
  基本：「台灣有哪些訂單管理系統？」
  口語：「我開網店，訂單太多管不動，有什麼系統推薦？」
  英文：「What are the best OMS platforms in Taiwan?」

  → 變體能測出你的語意覆蓋廣度（Part 3 §2 規則 1 的驗證）
```

### 3.3 定義檔格式

```yaml
# prompts.yaml
brand: "OrderFlow"
aliases: ["OrderFlow", "orderflow.tw", "訂單流"]
competitors:
  - { name: "易普印", aliases: ["易普印", "EasyPrint"] }
  - { name: "SHOPLINE", aliases: ["SHOPLINE", "shopline.tw"] }
  - { name: "91APP", aliases: ["91APP", "九一"] }

prompts:
  - id: DISC-001
    category: discovery
    text: "台灣有哪些多通路電商訂單管理系統（OMS）？請列出主要選項。"
    variants:
      - "我在台灣做電商，蝦皮 momo 官網都有賣，有什麼系統可以統一管訂單？"
      - "What OMS platforms are available for Taiwanese e-commerce sellers?"
    target_url: "/product/"

  - id: PROB-014
    category: problem
    text: "多通路電商如何避免庫存超賣？"
    variants:
      - "蝦皮和官網同時賣，庫存不同步怎麼辦？"
    target_url: "/blog/inventory-sync/"

  - id: BRAND-003
    category: brand
    text: "OrderFlow 的定價方案是什麼？"
    facts:                      # 用於描述正確率評分
      - "基本版每月 NT$500"
      - "專業版每月 NT$1,500"
      - "提供 14 天免費試用"
    target_url: "/pricing/"
```

---

## 四、監測系統實作

### 4.1 架構

```
┌──────────────┐
│ prompts.yaml │
└──────┬───────┘
       ▼
┌────────────────────────────────────────────────────┐
│  Runner（每週一次，或改版後立即跑）                   │
│  ┌──────────┬──────────┬──────────┬──────────┐    │
│  │ OpenAI   │ Anthropic│Perplexity│  手動     │    │
│  │ (web     │ (web     │ (Sonar   │  AI       │    │
│  │  search) │  search) │  API)    │  Overview │    │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┘    │
└───────┼──────────┼──────────┼──────────┼──────────┘
        └──────────┴────┬─────┴──────────┘
                        ▼
        ┌───────────────────────────────┐
        │  Parser：抽取答案文字 + 引用 URL │
        └───────────────┬───────────────┘
                        ▼
        ┌───────────────────────────────┐
        │  Scorer：品牌命中、位置、份額    │
        │          + LLM 判斷描述正確率   │
        └───────────────┬───────────────┘
                        ▼
        ┌───────────────────────────────┐
        │  Store：SQLite / BigQuery      │
        │  一列 = (日期, 引擎, 題目, 結果) │
        └───────────────┬───────────────┘
                        ▼
        ┌───────────────────────────────┐
        │  Report：AVS 趨勢圖 + 逐題明細  │
        └───────────────────────────────┘
```

### 4.2 核心程式碼

```python
#!/usr/bin/env python3
"""geo_monitor.py —— 多引擎 GEO 引用監測。

用法：
  python3 geo_monitor.py run    --config prompts.yaml --db geo.db
  python3 geo_monitor.py report --db geo.db --weeks 12
"""
from __future__ import annotations
import argparse, json, os, re, sqlite3, math, datetime as dt
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

import yaml  # pip install pyyaml


# ────────────────────────────── 資料模型 ──────────────────────────────
@dataclass
class Result:
    run_date: str
    engine: str
    prompt_id: str
    category: str
    prompt_text: str
    answer: str
    citations: str          # JSON list of URLs
    brand_mentioned: int
    brand_cited: int
    mention_position: int   # 第幾個被提到的品牌，0 = 未提及
    competitor_hits: str    # JSON dict
    accuracy: float         # 0-1，-1 表示不適用


# ────────────────────────────── 引擎介接 ──────────────────────────────
def ask_openai(prompt: str) -> tuple[str, list[str]]:
    """使用 OpenAI Responses API 的 web_search 工具。"""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r = client.responses.create(
        model="gpt-4.1",
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    text = r.output_text
    urls = []
    for item in getattr(r, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            for ann in getattr(c, "annotations", []) or []:
                u = getattr(ann, "url", None)
                if u:
                    urls.append(u)
    return text, list(dict.fromkeys(urls))


def ask_anthropic(prompt: str) -> tuple[str, list[str]]:
    """使用 Claude 的 web_search 工具。"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
        messages=[{"role": "user", "content": prompt}],
    )
    text, urls = [], []
    for block in msg.content:
        if block.type == "text":
            text.append(block.text)
            for cit in (getattr(block, "citations", None) or []):
                u = getattr(cit, "url", None)
                if u:
                    urls.append(u)
        elif block.type == "web_search_tool_result":
            for item in (block.content or []):
                u = getattr(item, "url", None)
                if u:
                    urls.append(u)
    return "\n".join(text), list(dict.fromkeys(urls))


def ask_perplexity(prompt: str) -> tuple[str, list[str]]:
    import requests
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}"},
        json={"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], d.get("citations", [])


ENGINES = {
    "openai": ask_openai,
    "anthropic": ask_anthropic,
    "perplexity": ask_perplexity,
}


# ────────────────────────────── 評分 ──────────────────────────────
def first_position(answer: str, brand_aliases: list[str],
                   competitors: list[dict]) -> int:
    """回傳品牌在答案中是第幾個被提到的（1-based），未提及回 0。"""
    def first_idx(aliases):
        idxs = [answer.find(a) for a in aliases if answer.find(a) >= 0]
        return min(idxs) if idxs else math.inf

    mine = first_idx(brand_aliases)
    if mine is math.inf:
        return 0
    others = [first_idx(c["aliases"]) for c in competitors]
    return 1 + sum(1 for o in others if o < mine)


def cited(urls: list[str], domain: str) -> bool:
    return any(domain in (urlparse(u).netloc or "") for u in urls)


def judge_accuracy(answer: str, facts: list[str]) -> float:
    """用 LLM 判斷答案中對本品牌的陳述是否與已知事實一致。"""
    if not facts:
        return -1.0
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = (
        "以下是一段 AI 回答，以及一組已知為真的事實。\n"
        "請判斷回答中關於該品牌的陳述，有多少比例與事實一致。\n"
        "只輸出一個 0 到 1 之間的小數，不要其他文字。\n"
        "若回答完全沒有提及該品牌，輸出 -1。\n\n"
        f"【已知事實】\n" + "\n".join(f"- {f}" for f in facts) +
        f"\n\n【AI 回答】\n{answer[:4000]}"
    )
    m = client.messages.create(
        model="claude-sonnet-5", max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return float(re.search(r"-?\d*\.?\d+", m.content[0].text).group())
    except (AttributeError, ValueError):
        return -1.0


# ────────────────────────────── 儲存 ──────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
  run_date TEXT, engine TEXT, prompt_id TEXT, category TEXT,
  prompt_text TEXT, answer TEXT, citations TEXT,
  brand_mentioned INT, brand_cited INT, mention_position INT,
  competitor_hits TEXT, accuracy REAL,
  PRIMARY KEY (run_date, engine, prompt_id)
);
"""


def save(db: str, rows: list[Result]):
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT OR REPLACE INTO results VALUES "
        "(:run_date,:engine,:prompt_id,:category,:prompt_text,:answer,"
        ":citations,:brand_mentioned,:brand_cited,:mention_position,"
        ":competitor_hits,:accuracy)",
        [asdict(r) for r in rows],
    )
    con.commit()
    con.close()


# ────────────────────────────── 執行 ──────────────────────────────
def run(cfg_path: str, db: str, engines: list[str]):
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    domain = cfg.get("domain", "orderflow.tw")
    aliases = cfg["aliases"]
    comps = cfg["competitors"]
    today = dt.date.today().isoformat()
    rows: list[Result] = []

    for p in cfg["prompts"]:
        texts = [p["text"]] + p.get("variants", [])
        for engine in engines:
            fn = ENGINES[engine]
            for vi, text in enumerate(texts):
                pid = p["id"] if vi == 0 else f"{p['id']}-v{vi}"
                try:
                    answer, urls = fn(text)
                except Exception as e:
                    print(f"  ! {engine} {pid}: {e}")
                    continue

                pos = first_position(answer, aliases, comps)
                hits = {
                    c["name"]: any(a in answer for a in c["aliases"])
                    for c in comps
                }
                acc = judge_accuracy(answer, p.get("facts", [])) if pos else -1.0

                rows.append(Result(
                    run_date=today, engine=engine, prompt_id=pid,
                    category=p["category"], prompt_text=text, answer=answer,
                    citations=json.dumps(urls, ensure_ascii=False),
                    brand_mentioned=int(pos > 0),
                    brand_cited=int(cited(urls, domain)),
                    mention_position=pos,
                    competitor_hits=json.dumps(hits, ensure_ascii=False),
                    accuracy=acc,
                ))
                print(f"  {engine:<11} {pid:<14} 提及={'✔' if pos else '✘'} "
                      f"位置={pos} 引用={'✔' if cited(urls, domain) else '✘'}")

    save(db, rows)
    print(f"\n已寫入 {len(rows)} 筆　→ {db}")


# ────────────────────────────── 報表 ──────────────────────────────
def report(db: str, weeks: int):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT run_date FROM results ORDER BY run_date DESC LIMIT ?",
        (weeks,))][::-1]

    print(f"\n{'日期':<12}{'題數':>6}{'提及率':>9}{'引用率':>9}"
          f"{'位置分':>9}{'正確率':>9}{'AVS':>8}")
    print("─" * 64)

    for d in dates:
        rs = list(con.execute("SELECT * FROM results WHERE run_date=?", (d,)))
        n = len(rs)
        if not n:
            continue
        mention = sum(r["brand_mentioned"] for r in rs) / n
        citation = sum(r["brand_cited"] for r in rs) / n
        positions = [r["mention_position"] for r in rs if r["mention_position"] > 0]
        posscore = (sum(1 / math.log2(p + 1) for p in positions) / len(positions)
                    if positions else 0.0)
        accs = [r["accuracy"] for r in rs if r["accuracy"] >= 0]
        acc = sum(accs) / len(accs) if accs else 0.0

        # 引用份額：本品牌提及數 / (本品牌 + 所有競品) 提及數
        comp_total = 0
        for r in rs:
            comp_total += sum(1 for v in json.loads(r["competitor_hits"]).values() if v)
        mine = sum(r["brand_mentioned"] for r in rs)
        share = mine / (mine + comp_total) if (mine + comp_total) else 0.0

        avs = 100 * (0.30 * citation + 0.30 * share + 0.25 * posscore + 0.15 * acc)
        print(f"{d:<12}{n:>6}{mention:>8.0%}{citation:>9.0%}"
              f"{posscore:>9.2f}{acc:>9.0%}{avs:>8.1f}")

    # 逐題：最近一次 vs 上一次
    if len(dates) >= 2:
        cur, prev = dates[-1], dates[-2]
        print(f"\n逐題變化（{prev} → {cur}）")
        print("─" * 64)
        q = ("SELECT prompt_id, category, AVG(brand_cited) c "
             "FROM results WHERE run_date=? GROUP BY prompt_id")
        a = {r["prompt_id"]: r for r in con.execute(q, (prev,))}
        b = {r["prompt_id"]: r for r in con.execute(q, (cur,))}
        deltas = sorted(
            ((k, b[k]["c"] - a.get(k, {"c": 0})["c"], b[k]["category"]) for k in b),
            key=lambda x: x[1])
        for pid, d_, cat in deltas[:5]:
            if d_ < 0:
                print(f"  ↓ {pid:<16} {cat:<12} {d_:+.0%}")
        for pid, d_, cat in deltas[-5:]:
            if d_ > 0:
                print(f"  ↑ {pid:<16} {cat:<12} {d_:+.0%}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--config", default="prompts.yaml")
    ap.add_argument("--db", default="geo.db")
    ap.add_argument("--engines", default="openai,anthropic,perplexity")
    ap.add_argument("--weeks", type=int, default=12)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.config, a.db, a.engines.split(","))
    else:
        report(a.db, a.weeks)
```

### 4.3 成本

```
規模：50 題 × 2.4 變體 × 3 引擎 = 360 次查詢／輪

項目                      單價（概估）      每輪成本
──────────────────────────────────────────────────
帶 web search 的生成       $0.02-0.05／次   $7-18
準確率評分（小模型）        $0.002／次       $0.7
──────────────────────────────────────────────────
每輪合計                                    約 $8-19
每週一次 → 每月                              約 $32-76
```

**這是整個 GEO 專案中最便宜、也最不該省的一筆。** 沒有它，你無法向管理層證明任何事。

### 4.4 AI Overview 的處理

AI Overview 沒有官方 API。三個選擇：

```
方法                    可靠度    成本      建議
────────────────────────────────────────────────────────
第三方 SERP API          高       $50-300/月  推薦，多數已支援 AI Overview 欄位
自建瀏覽器自動化          中       工程時間     易被反爬，維護成本高
人工每月抽查 20 題        中       2 小時/月    小團隊的務實選擇
```

務實建議：**API 監測涵蓋 ChatGPT / Claude / Perplexity（可程式化的部分），AI Overview 用人工每月抽查 20 題**。趨勢方向通常一致，不需要三個都自動化。

---

## 五、從流量側辨識 AI 曝光

程式化監測看的是「模型怎麼說」，流量側看的是「有沒有人來」。兩者互補。

### 5.1 伺服器日誌：AI crawler 活動

crawler 抓取頻率是「引擎對你有多少興趣」的領先指標，通常領先引用率變化 2-4 週。

```bash
# 從 nginx log 統計各 AI bot 的抓取量與熱門頁
awk '{print $0}' /var/log/nginx/access.log \
| grep -Ei "GPTBot|OAI-SearchBot|ClaudeBot|Claude-SearchBot|PerplexityBot|Applebot|Bytespider" \
| awk '{
    ua="other";
    if ($0 ~ /OAI-SearchBot/) ua="OAI-SearchBot";
    else if ($0 ~ /GPTBot/) ua="GPTBot";
    else if ($0 ~ /Claude-SearchBot/) ua="Claude-SearchBot";
    else if ($0 ~ /ClaudeBot/) ua="ClaudeBot";
    else if ($0 ~ /PerplexityBot/) ua="PerplexityBot";
    else if ($0 ~ /Applebot/) ua="Applebot";
    print ua, $9, $7
  }' \
| sort | uniq -c | sort -rn | head -40
```

要盯的三件事：

```
訊號                        意義
──────────────────────────────────────────────────────────
某 bot 的 4xx/5xx 比例上升    存取層出問題 → 立刻查 CDN
某 bot 抓取量歸零             被封鎖或被降級 → 查 WAF 規則變更
抓取集中在少數頁              其他頁沒被發現 → 查 sitemap 與內部連結
抓取量在改版後大增             正向訊號，通常 2-4 週後反映在引用率
```

### 5.2 GA4：AI referral 流量

AI 引用帶來的點擊會有 referrer，只是量小、且預設被歸到「Referral」裡看不清楚。

建立一個自訂維度來分流：

```javascript
// 在 GTM 或 gtag 設定中，把 AI 來源標記出來
(function () {
  var ref = document.referrer || '';
  var AI_SOURCES = {
    'chatgpt.com': 'ChatGPT',
    'chat.openai.com': 'ChatGPT',
    'perplexity.ai': 'Perplexity',
    'claude.ai': 'Claude',
    'copilot.microsoft.com': 'Copilot',
    'gemini.google.com': 'Gemini',
    'you.com': 'You.com',
    'phind.com': 'Phind',
  };
  var src = null;
  for (var host in AI_SOURCES) {
    if (ref.indexOf(host) !== -1) { src = AI_SOURCES[host]; break; }
  }
  // 部分引擎會帶 utm 參數
  var params = new URLSearchParams(location.search);
  if (!src && /chatgpt|perplexity|claude|copilot/i.test(params.get('utm_source') || '')) {
    src = params.get('utm_source');
  }
  if (src) {
    gtag('event', 'ai_referral', {
      ai_source: src,
      landing_page: location.pathname,
      // 設為 user property，讓後續轉換也能歸因
      send_to: 'G-XXXXXXX',
    });
    gtag('set', 'user_properties', { first_ai_source: src });
  }
})();
```

GA4 探索報表的設定：

```
維度：ai_source, landing_page
指標：工作階段、參與率、平均參與時間、轉換
篩選：ai_referral 事件不為空

要看的是：AI 來的流量「品質」通常明顯高於一般 organic
  ——因為使用者已經在 AI 那邊被預先篩選過一輪。
```

### 5.3 品牌詞搜尋量：真正的下游指標

因為多數 AI 曝光是零點擊的，**品牌詞搜尋量的成長才是 GEO 生效的最強證據**。

```
在 GSC 建立一個「品牌詞」篩選（query 包含 brand 名稱及變體），
每月記錄：
  • 品牌詞曝光數
  • 品牌詞點擊數
  • 品牌詞佔總 organic 的比例

搭配 Direct 流量的變化一起看。

如果：AI 引用率 ↑ + 品牌詞搜尋 ↑ + Direct ↑，而一般關鍵字流量持平或微降
→ 這就是 GEO 生效的典型形狀（流量結構在轉移，不是消失）
```

---

## 六、實戰案例 A：B2B SaaS 站的六個月

### 6.1 起點

```
公司：一家台灣的 B2B 排程／派工 SaaS（30 人，年營收約 NT$8,000 萬）
網站：Next.js（App Router，但大量 client component）
內容：87 篇部落格、12 個產品頁、1 個文件站

基線量測（2026 年 1 月第 1 週，50 題 × 3 引擎）
──────────────────────────────────────────────
提及率            18%
引用率             6%
引用份額          11%
位置加權分         0.31
描述正確率        52%   ← 模型講的定價是兩年前的
AVS               17.4

Coverage Gap      42%   ← 一半的題目沒有對應頁面
Engine Variance   21pp  ← Perplexity 19%、ChatGPT 2% ← 紅旗
```

**Engine Variance 21pp 立刻指向技術問題**，不是內容問題。

### 6.2 診斷（Week 1-2）

```bash
$ ./ai-crawler-check.sh https://example.com/blog/scheduling-guide/
USER-AGENT             CODE   BYTES      SERVER
GPTBot/1.0             403    0          cloudflare
OAI-SearchBot/1.0      403    0          cloudflare
ChatGPT-User/1.0       403    0          cloudflare
ClaudeBot/1.0          403    0          cloudflare
PerplexityBot/1.0      200    148231     cloudflare
Googlebot/2.1          200    148231     cloudflare
bingbot/2.0            200    148231     cloudflare
```

原因：Cloudflare 的「Block AI Scrapers and Crawlers」開著，而 PerplexityBot 因為當時走另一個判定路徑漏過去了。**這個開關是半年前某次資安檢視時打開的，沒有人記得。**

第二個問題：

```
瀏覽器文字量：4,180 字
curl 文字量（Googlebot）：1,090 字（26%）
```

主要內容包在 `'use client'` 元件裡，靠 `useEffect` 抓資料。Googlebot 因為會執行 JS 所以看得到，但即使是 Googlebot 也只拿到部分。

### 6.3 執行時序與逐月數據

```
月份    主要動作                                    AVS    引用率  正確率
──────────────────────────────────────────────────────────────────────
1月     基線量測                                    17.4    6%     52%
        關閉 Cloudflare AI 封鎖 + 加 WAF skip 規則

2月     內容頁改 SSG（generateStaticParams）         24.1   11%     55%
        Organization / Article / FAQPage JSON-LD
        修正 dateModified（原本是 build time）

3月     20 篇核心文章重寫（九條規則）                 31.8   17%     58%
        標題改問句、加 TL;DR、補數據與日期

4月     補 9 篇內容缺口（Coverage Gap 42% → 19%）    38.2   22%     61%
        每篇加比較表 + FAQ

5月     定價頁大改：把價格寫成 HTML 表格（原本是      44.6   26%     84%
        設計稿圖片）+ Product schema
        ← 正確率從 61% 跳到 84%，單一改動效果最大

6月     Wikidata 條目、G2 檔案、3 篇產業媒體投稿      49.3   29%     86%
        Reddit / 社群的真實討論開始出現
```

### 6.4 哪些有效、哪些沒效

```
動作                            AVS 貢獻    成本(人天)   投報率
────────────────────────────────────────────────────────────────
解除 Cloudflare AI 封鎖          +6.7        0.5         ★★★★★
定價表從圖片改成 HTML 表格        +6.4        1           ★★★★★
20 篇核心文章重寫                +7.7        22          ★★★☆☆
內容頁改 SSG                     +3.2        6           ★★★★☆
補 9 篇內容缺口                  +6.4        14          ★★★★☆
JSON-LD 全套                     +2.1        3           ★★★☆☆
實體層（Wikidata / G2 / 媒體）    +4.7        12（+持續）  ★★★☆☆
────────────────────────────────────────────────────────────────
沒有可測量效果的動作：
  • 把 87 篇舊文全部加 FAQ（只有核心 20 篇有效，長尾無感）  -8 人天
  • Core Web Vitals 從 72 分優化到 94 分                    -5 人天
  • llms.txt / llms-full.txt                               -0.5 人天
  • 大量內部連結補強                                        -3 人天
```

**兩個最重要的教訓**：

1. **最大的兩筆收益來自「修 bug」，不是「做內容」**。半天的 Cloudflare 設定，效果超過三週的內容重寫。先做 Layer 1 這件事不是理論，是實測。

2. **「全站一起做」是浪費**。87 篇文章全加 FAQ 花了 8 人天，效果為零；20 篇核心文章的重寫才有效。**用 prompt set 決定要改哪些頁**，不要平均分配資源。

### 6.5 商業結果

```
指標                    1 月        6 月       變化
────────────────────────────────────────────────────
AI referral 工作階段     310        2,840     +816%
AI referral 轉換率       —          4.8%      （一般 organic 為 1.9%）
品牌詞曝光（GSC）        12,400     29,600    +139%
Direct 工作階段          8,900      14,200    +60%
一般關鍵字 organic       41,200     38,700    -6%
──────────────────────────────────────────────────
MQL 總數                 142        219       +54%
其中「來源不明／直接」    38%        51%       ← 歸因困難度上升
```

最後一列值得注意：**GEO 成功的副作用是歸因變差**。越多人因為 AI 而認識你，越多轉換會被歸到 Direct。這在向管理層報告時必須先講清楚，否則會被質疑「這些是自然成長」。

**應對方法**：在表單加一題「您怎麼知道我們的？」，選項包含「ChatGPT / Claude / Perplexity 等 AI 工具」。這是最便宜也最可靠的歸因補強。該公司加了這一題之後，6 月有 17% 的 MQL 選了 AI 工具。

---

## 七、實戰案例 B：本地服務業（對照組）

不是每個產業的結果都一樣。這是一個效果較弱的案例，用來校準期待。

```
公司：北部一家連鎖牙醫（6 家分院）
起點 AVS：8.2
6 個月後：19.4（+11.2）

有效的：
  ✔ LocalBusiness / Dentist schema + 每家分院獨立頁
  ✔ 診療項目頁改成問句式標題（「植牙一顆多少錢？」）
  ✔ 明確標示價格區間（原本寫「請來電洽詢」）  ← 效果最大
  ✔ Google Business Profile 與官網資訊完全一致

無效的：
  ✘ 大量衛教文章（醫療 YMYL 主題，模型強烈偏好
     衛福部、醫學會、大型醫院的內容——這是合理的）
  ✘ 醫師介紹頁（除非醫師本人有學會職務或論文）

結論：YMYL 領域（醫療、金融、法律）的 GEO 天花板明顯較低，
      權威來源的優先權遠高於任何內容優化。
      資源應該放在「交易型與在地型查詢」，不是「知識型查詢」。
```

**這個對照很重要**：如果你在 YMYL 領域，設定「引用率 30%」的目標是不切實際的。合理目標是在「XX 地區有哪些 XX」這類在地與交易型查詢上取得高份額。

---

## 八、ROI 試算

```
六個月投入（案例 A）
────────────────────────────────────────────────
工程                 12 人天 × NT$8,000  =  NT$ 96,000
內容                 48 人天 × NT$5,000  =  NT$240,000
實體層 / PR          12 人天 × NT$6,000  =  NT$ 72,000
監測 API 費用        6 個月 × NT$1,800   =  NT$ 10,800
SERP API（AI Overview）6 個月 × NT$3,000 =  NT$ 18,000
────────────────────────────────────────────────
合計                                       NT$436,800

六個月產出
────────────────────────────────────────────────
新增 MQL             +77 個（142 → 219，月均）
MQL → 成交率         8%（該公司歷史值）
新增成交             ≈ 6 個
平均客戶首年營收      NT$180,000
────────────────────────────────────────────────
新增年營收           ≈ NT$1,080,000
首年 ROI             ≈ 147%
（含續約的三年 LTV 計算，ROI 約 380%）
```

**必須誠實標注的假設**：

1. 這 77 個 MQL 中，有多少是 GEO 帶來、有多少是同期其他行銷活動的貢獻，**無法完全切乾淨**。表單自陳的 17% 是下限，實際可能在 25-40%。
2. 若只算表單自陳的 17%，新增成交約 1 個，首年 ROI 為負，需要三年 LTV 才轉正。
3. **不要在提案時只講樂觀版本**。給區間，說明假設，比事後被質疑好。

保守版本的講法：

```
「六個月投入約 44 萬。可直接歸因的新增營收約 18 萬（首年），
  三年 LTV 約 54 萬 → 三年 ROI 約 23%。
  加上無法直接歸因但高度相關的品牌詞成長 139%，
  實際回報應高於此數，但我們不會用無法驗證的數字提案。」
```

---

## 九、常見的量測陷阱

```
陷阱                          後果                      解法
──────────────────────────────────────────────────────────────────────
只測一次就下結論               LLM 有隨機性，單次結果      同一題跑 3 次取多數；
                              波動可達 ±15pp            或固定 temperature=0

prompt set 都是品牌詞          看起來分數很高但無意義      品類發現題要佔 30%
                              （問你的名字當然提到你）

沒有記基線                     無法證明任何改動有效        改之前一定先跑一輪

改太多東西才量一次             不知道哪一項有效            每月只推 1-2 個大改動，
                                                       量完再推下一批

用不同的 prompt set 比較        趨勢完全失真               prompt set 一旦定案就凍結；
                                                       要擴充就另開一組並行

忽略 Engine Variance          花三個月改內容，其實是       每輪報表都看各引擎分項
                              某個引擎被 CDN 擋了

把「提及」當「引用」            高估成效                   分開記錄：提及 ≠ 附連結引用

沒有量描述正確率               被引用但被講錯，            brand 類題目一定要有
                              比不被引用更傷              facts 欄位做評分
```

---

## 十、系統效應：整個系列做完之後

```
面向              改造前                        改造後
──────────────────────────────────────────────────────────────────────
AI crawler 存取   4/8 被擋，無人知曉             8/8 通過，CI 每週自動驗
內容可見度        無 JS 時只有 26%               98%
被引用單位        整頁（且多半是首頁）            段落級（帶錨點的深層引用）
結構化資料        零散或缺失                     四類 schema 互相 @id 引用
內容標準          憑寫手個人習慣                  九條規則 + CI 分數門檻
新內容品質        上線後才發現問題                PR 階段就被擋下
量測能力          憑感覺                         AVS 週報 + 逐題變化
歸因能力          AI 流量完全隱形                 ai_source 維度 + 表單自陳
組織能力          一次性專案                     六個角色的固定職責

量化（案例 A，六個月）
──────────────────────────────────────────────────────────────────────
AVS               17.4                          49.3        +183%
引用率            6%                            29%         +23pp
描述正確率        52%                           86%         +34pp
Coverage Gap      42%                           11%         -31pp
Engine Variance   21pp                          4pp         技術問題消失
AI referral       310 sessions/月                2,840       +816%
品牌詞曝光        12,400                        29,600      +139%
MQL               142/月                        219/月      +54%
```

### 最後三句話

1. **先修管線，再寫內容。** 案例 A 中投報率最高的兩件事都是「修 bug」，總共花了 1.5 人天，貢獻了 27% 的 AVS 成長。在你確認 8 個 bot 都能拿到完整內容之前，不要開始寫任何新文章。

2. **用 prompt set 決定資源分配。** 平均用力是最貴的做法。87 篇文章全改的效果，不如 20 篇對的文章改到位。

3. **量測不是為了報告，是為了下一次決策。** 每週的 AVS 數字本身沒有意義；有意義的是「這一題上升了，因為上週我們改了那一頁」——這條因果鏈，才是讓 GEO 從專案變成能力的東西。

---

*本系列文章：*
- [Part 1：概念篇 — 當搜尋結果不再是十條藍色連結](/posts/aio-geo-part1-concepts-zh/)
- [Part 2：原理篇 — AI 引擎如何檢索、選擇與引用你的內容](/posts/aio-geo-part2-how-engines-work-zh/)
- [Part 3：方法篇 — 內容、結構、技術三層優化策略](/posts/aio-geo-part3-strategies-zh/)
- [Part 4：實作篇 — 把一個網站改造成 AI 可引用](/posts/aio-geo-part4-implementation-zh/)
- **Part 5（本篇）：量測與案例篇 — 建立監測系統與六個月實戰復盤**
- [Part 6：實戰案例 — 大型企業官網（多語系 + AWS + 法遵）](/posts/aio-geo-part6-case-enterprise-site-zh/)
- [Part 7：實戰案例 — 電商網站（12,000 SKU + 價格新鮮度）](/posts/aio-geo-part7-case-ecommerce-zh/)
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- [Part 9：實戰案例 — 線上課程平台（付費牆 + 影片）](/posts/aio-geo-part9-case-course-platform-zh/)
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
