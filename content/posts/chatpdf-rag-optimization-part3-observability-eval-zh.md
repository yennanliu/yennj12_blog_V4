---
title: "ChatPDF RAG 優化（三）：可觀測性與評估 —— Langfuse 追蹤、評估歷史、即時評分"
date: 2026-06-30T11:00:00+08:00
draft: false
description: "沒有量測就沒有優化。本篇拆解 chatPDF 如何補上 RAG 的可觀測性最後一塊:opt-in 零開銷的 Langfuse 追蹤、執行緒安全的 singleton、評估歷史持久化、即時答案評分(faithfulness/relevance)、relevance gate,以及無外部依賴的 SVG 趨勢圖表。"
categories: ["engineering", "ai", "all"]
tags: ["RAG", "LLM", "ChatPDF", "Observability", "Langfuse", "Evaluation", "Tracing", "LLM-as-judge", "Metrics"]
authors: ["yen"]
readTime: "16 min"
---

> 多數 RAG 專案上線後,優化全憑「感覺答案變好了」。
> 但你說不出 faithfulness 是 0.6 還是 0.9,也不知道上次調 alpha 是讓 nDCG 上升還是下降。
> 這篇講的就是把「感覺」換成「數字」:追蹤每一次 LLM 呼叫、持久化每一次評估、即時評每一個答案——讓優化變成可被驗證的循環。

---

## 一、為什麼可觀測性是 RAG 的最後一哩

[第一篇](../chatpdf-rag-optimization-part1-chunking-retrieval-zh/)解決切塊與檢索品質,[第二篇](../chatpdf-rag-optimization-part2-backend-hardening-zh/)補上 production 防線。但還缺一塊:**你怎麼知道這些優化真的有效?**

RAG 的恐怖之處在於它「永遠會給出一個看起來合理的答案」。沒有量測,你根本分不清:

- 調了 `hybrid_alpha`,到底是變好還是變壞?
- 某個答案是基於檢索內容,還是 LLM 自己編的(hallucination)?
- 這次改動,整體 nDCG@k 的趨勢是上升還是下降?

[PR #4](https://github.com/yennanliu/chatPDF/pull/4) 補上三層可觀測性:

```
┌──────────────────────────────────────────────────────┐
│  三層可觀測性                                          │
├──────────────────────────────────────────────────────┤
│  1. 即時聊天   每個回答附信心分數(faithfulness 等)   │
│  2. 評估工具   每次評估的彙總指標持久化,追蹤趨勢      │
│  3. Langfuse   所有 LLM 呼叫被追蹤(延遲/token/成本)  │
│                ── 設定才開,不設定零開銷               │
└──────────────────────────────────────────────────────┘
```

---

## 二、Langfuse 追蹤:opt-in 且零開銷

### 設計原則:不設定 = 完全無感

可觀測性工具最怕的就是「為了觀測而拖慢主流程」。chatPDF 的 Langfuse 整合是**完全 opt-in**:沒設定環境變數時,它是一個 no-op,零開銷、零風險。

```python
import threading

_client_instance = None
_init_attempted = False
_client_lock = threading.Lock()

def _client():
    global _client_instance, _init_attempted
    # 沒啟用 → 直接回 None,主流程完全無感
    if not settings.langfuse_enabled:
        return None
    if _init_attempted:
        return _client_instance
    # 雙重檢查鎖定:確保多執行緒下只初始化一次
    with _client_lock:
        if _init_attempted:
            return _client_instance
        _init_attempted = True
        try:
            _client_instance = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        except Exception:
            _client_instance = None   # 初始化失敗也不能拖垮主流程
    return _client_instance
```

### 三個設計重點

1. **零開銷 opt-in**:`langfuse_enabled` 為 false 時第一行就 return None。沒裝、沒設定的人完全不受影響。
2. **執行緒安全的 singleton(雙重檢查鎖定)**:在並發的 ASGI 環境下,多個請求可能同時觸發初始化。`threading.Lock` + 雙重檢查確保 client 只初始化一次,避免重複載入模型造成 race condition。
3. **所有呼叫 try-except 包覆**:追蹤失敗(網路抖動、Langfuse 掛了)**絕不能讓聊天或評估中斷**。觀測是附加價值,不是主流程依賴。

```
   LLM 呼叫(聊天/評估/judge/查詢改寫)
        │
        ├─ langfuse 未啟用 ──▶ 直接執行,零額外動作
        │
        └─ langfuse 啟用 ──▶ try: 附上 CallbackHandler
                                記錄延遲/token/成本
                             except: 吞掉,主流程照常
```

---

## 三、評估歷史持久化:把「這次比上次好嗎」變成可查詢

### 問題

跑一次 RAG 評估(不同 chunker/alpha/reranker 配置的對照),你會得到一堆 Hit@k、MRR、nDCG、faithfulness 數字。但跑完就沒了——下次調參,你無從比較「這次到底比上次好還是壞」。

### 解法:新增 `eval_run` 表,只存彙總指標

```python
def save_run(db: Session, result: dict) -> EvalRun:
    # 只存每個配置變體的彙總指標(不存逐題明細,保持輕量)
    summary = [
        {"label": r["label"], "config": r.get("config", {}), "metrics": r["metrics"]}
        for r in result.get("results", [])
    ]
    row = EvalRun(
        k=result.get("k", 0),
        n_questions=result.get("n_questions", 0),
        judge_enabled=bool(result.get("judge_enabled")),
        summary=json.dumps(summary),
    )
    db.add(row)
    db.commit()
    return row

def load_history(db: Session, limit: int = 30) -> list[dict]:
    rows = db.exec(
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
    ).all()
    # 回傳時轉成「舊→新」順序,方便趨勢圖由左到右畫
    return _chronological(rows)
```

搭配兩個端點:`GET /api/eval/history`(歷史趨勢)與 `GET /api/eval/tracing`(Langfuse 狀態)。

**設計重點:只存彙總,不存逐題明細。** 趨勢圖只需要每次跑的彙總指標,逐題明細又重又少用。存得輕,查得快——這是「為了趨勢追蹤」這個具體用途做的刻意取捨。

---

## 四、即時答案評分:每個回答都帶信心分數

### 想法

與其等到「跑評估」才知道品質,不如**每個聊天回答即時評分**。串流結束後,用一個非阻塞的 judge 呼叫評估這次回答:

```python
# chat_ws.py:串流結束後,非阻塞評分
if settings.chat_response_scoring and answer.strip():
    judge_llm = llm_gw.get_llm(session.provider, session.model, 0.0)
    metrics = await asyncio.to_thread(
        response_metrics.score_response,
        query, context, answer, judge_llm, trace_config,
    )
    await websocket.send_json({"type": "metrics", "data": metrics})
```

評分混合了「免標註」的多個面向:

```python
metrics = {
    "retrieval_confidence": retrieval_confidence(context),   # 最佳 chunk 的 CE logit 經 sigmoid
    "context_precision":    verdict.get("context_precision"),
    "faithfulness":         verdict.get("faithfulness"),      # 答案是否忠於檢索內容
    "answer_relevance":     verdict.get("answer_relevance"),
}
components = [v for v in metrics.values() if v is not None]
metrics["confidence"] = sum(components) / len(components) if components else None
```

最關鍵的是 **faithfulness**——它衡量「答案是否真的基於檢索內容,而不是 LLM 編的」。這是對抗 hallucination 最直接的信號。

**取捨**:每次回答多一個 judge LLM 呼叫(成本+延遲)。所以用 `CHAT_RESPONSE_SCORING` 開關控制,且用 `asyncio.to_thread` 非阻塞執行,不卡住串流回應。

---

## 五、Relevance Gate:用 cross-encoder 過濾,但永不清空

第二篇講過 `min_score` 過濾,這裡是更精準的版本:用 **cross-encoder**(比 bi-encoder 更準的相關度模型)給每個 chunk 重新打分,過濾掉低於門檻的:

```python
def apply_relevance_gate(query, chunks, threshold, scorer) -> list[dict]:
    """cross-encoder 丟掉低於門檻的 chunk;但永遠不清空 context。"""
    if not chunks:
        return chunks
    try:
        scores = scorer.score(query, chunks)
    except Exception:
        return chunks   # 評分器掛了就原樣放行,絕不中斷這一輪
    scored = sorted(
        ({**c, "relevance": float(s)} for c, s in zip(chunks, scores)),
        key=lambda c: c["relevance"], reverse=True,
    )
    kept = [c for c in scored if c["relevance"] >= threshold]
    return kept or scored[:1]   # ← 全被過濾掉時,至少保留最佳的一個
```

### 兩個關鍵防呆

1. **`kept or scored[:1]`**:如果門檻太嚴把所有 chunk 都濾掉了,**至少保留分數最高的那一個**——絕不讓 LLM 在「零 context」下硬答。
2. **評分器失敗就原樣放行**:cross-encoder 掛了(模型載入失敗等),直接回傳原 chunks,**不讓觀測性功能拖垮主流程**——這跟 Langfuse 的設計哲學一致。

門檻預設 0.0,約等於 sigmoid(0.5),也就是「相關的可能性大於不相關」這條邊界。

---

## 六、一個血淚細節:judge prompt 的大括號轉義

這是個容易被忽略、但上線必爆的 bug。

LLM-as-judge 的 prompt 是用 `str.format()` 把問題、context、答案填進模板的。但 **PDF chunk 裡常常含有字面的大括號**——程式碼、JSON、LaTeX 公式都有 `{` `}`。直接 `.format()` 會把它們當成佔位符,丟出 `KeyError` 讓整個評分靜默失效:

```python
def _esc(text: str | None) -> str:
    """轉義字面大括號,讓文件/答案內容不會破壞 str.format。"""
    if not text:
        return ""
    return text.replace("{", "{{").replace("}", "}}")

# 所有 judge 呼叫都先轉義
prompt = _JUDGE_PROMPT.format(
    question=_esc(question),
    context=_esc(context),
    answer=_esc(answer),
)
```

**設計重點:任何把「使用者/文件內容」塞進「格式化模板」的地方,都是注入點。** 含程式碼的 PDF 不轉義,評分就會在沒人發現的情況下默默掛掉。這個 PR 為它補了 4 個回歸測試。

---

## 七、無依賴 SVG 圖表:把數字畫成趨勢

有了歷史資料,前端用**純 SVG、零外部圖表套件**畫兩種圖:

```
   GroupedBarChart(同一次跑的配置對照)
   ┌─────────────────────────────────────┐
   │  nDCG  ██ ▓▓ ░░                      │
   │  MRR   ██ ▓▓ ░░    ██ 配置A          │
   │  Hit@k ██ ▓▓ ░░    ▓▓ 配置B  ░░ 配置C│
   └─────────────────────────────────────┘

   TrendChart(跨多次跑的趨勢,舊→新)
   faithfulness
    │        ╭──●
    │   ●───╯
    │  ╱
    │ ●
    └──────────────▶ 第1次  第2次  第3次
```

- **GroupedBarChart**:把同一次評估裡不同配置(chunker / alpha / reranker)的指標並排比較。
- **TrendChart**:把歷次評估的某指標畫成時間趨勢,一眼看出「改了之後到底是漲是跌」。

**為什麼不用 Chart.js / ECharts?** 對「就畫兩種簡單圖」的需求,引入一個重型圖表套件等於背一堆用不到的程式碼與版本風險。純 SVG 幾十行就搞定,輕量、可預測、零依賴——跟第一篇「自寫 BM25」是同一種取捨哲學。

---

## 八、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 追蹤啟用 | opt-in,零開銷 no-op | 不選預設開啟:會給不需要的人加負擔 |
| singleton 初始化 | 雙重檢查鎖定 | 不選無鎖:並發 ASGI 下會重複初始化、race condition |
| 觀測失敗 | try-except 吞掉 | 不選讓它拋出:觀測絕不能拖垮主流程 |
| 評估儲存 | 只存彙總指標 | 不選存逐題明細:趨勢圖用不到,徒增重量 |
| 答案評分 | 非阻塞 + 開關控制 | 不選同步必開:會卡串流、增成本 |
| relevance gate | 全濾掉時保留最佳 | 不選可清空:零 context 會逼 LLM 硬編 |
| judge prompt | 轉義大括號 | 不選直接 format:含程式碼的 PDF 會 KeyError |
| 圖表 | 純 SVG | 不選圖表套件:兩種簡單圖不值得背重依賴 |

**Flip condition**:

- 團隊已有成熟的可觀測平台(Datadog/自建),可直接接,不必用 Langfuse。
- 評估需要逐題 debug(找出哪一題退步),那就得存逐題明細,不能只存彙總。
- 圖表需求變複雜(互動、縮放、多軸),才值得引入 Chart.js 之類的套件。

---

## 九、系統效應:改動前 vs 改動後

| 面向 | 改動前 | 改動後 |
|------|--------|--------|
| LLM 呼叫追蹤 | 無 | Langfuse(延遲/token/成本),opt-in 零開銷 |
| 評估結果 | 跑完即丟 | `eval_run` 表持久化,可查歷史趨勢 |
| 答案品質 | 無即時信號 | 每答附 faithfulness / relevance / confidence |
| 噪音過濾 | min_score | cross-encoder relevance gate(預設開,永不清空) |
| judge 穩定性 | 含 `{}` 的 PDF 會崩 | 大括號轉義,+4 回歸測試 |
| 趨勢視覺化 | 無 | 純 SVG GroupedBar / Trend 圖表 |
| 測試 | — | +11 追蹤/歷史測試,後端 235 測試,覆蓋率 90.9% |

---

## 十、系列總結

三篇走下來,chatPDF 的 RAG 從「能跑」一路推到「能上線、能持續優化」:

```
   第一篇:品質核心  ──▶  切對(Semantic Chunking)、撈對(Hybrid Retrieval)
   第二篇:production ──▶  安全邊界、資源上限、進階 RAG 退路
   第三篇:可觀測性  ──▶  追蹤、評估、即時評分,讓優化可被驗證
```

貫穿三篇的設計哲學其實一致:

1. **附加功能絕不拖垮主流程**:Langfuse、relevance gate、評分,失敗時全都安靜放行。
2. **能自己寫的就不背依賴**:BM25、SVG 圖表——核心邏輯不多,自寫換來輕量與可控。
3. **每個取捨都對著一個具體用途**:只存彙總(為趨勢)、opt-in(為零開銷)、保留最佳 chunk(為不空答)。

> 一句話總結:RAG 優化不是一次性的調參,而是「量測 → 改動 → 再量測」的循環;沒有可觀測性,這個循環根本轉不起來。

---

**系列導覽**

- [第一部分:語意切塊與混合檢索](../chatpdf-rag-optimization-part1-chunking-retrieval-zh/)
- [第二部分:後端強化與進階 RAG](../chatpdf-rag-optimization-part2-backend-hardening-zh/)
- 第三部分:可觀測性與評估(本篇)

**參考連結**

- PR: [Langfuse tracing + in-app metric charts & run-history trends #4](https://github.com/yennanliu/chatPDF/pull/4)
- Repo: [yennanliu/chatPDF](https://github.com/yennanliu/chatPDF)
