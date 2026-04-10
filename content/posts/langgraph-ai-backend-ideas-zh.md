---
title: "LangGraph AI 後端創意應用：10 個生產級案例和未來方向"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "LangGraph", "applications"]
tags: ["LangGraph", "應用案例", "創意", "行業解決方案", "未來趨勢"]
summary: "探索 LangGraph AI 後端在 10 個不同行業和場景的創意應用，從客服系統到內容創作、從數據分析到程式碼生成，展示 LangGraph 的真正潛力和未來發展方向。"
readTime: "52 min"
---

LangGraph 最強大的地方不是它能做什麼，而是**它開啟了什麼**。本文探討 10 個生產級的創意應用案例，展示如何用 LangGraph 構建明天的 AI 系統。

---

## 1. 智能內容審核和分類系統

### 應用場景
社交媒體平台、論壇、UGC 社區都面臨內容審核的挑戰。傳統方案要麼依賴人工，要麼規則過於死板。LangGraph 能構建**多層次的智能審核系統**。

### 工作流設計

```
用戶上傳內容
    ↓
[快速過濾] - 明顯違規內容
    │
    ├→ 違規 → 直接刪除
    │
    └→ 可疑 → 深度分析
        ↓
    [語境分析] - 理解上下文
        ├→ 色情內容識別
        ├→ 暴力內容識別
        ├→ 仇恨言論檢測
        └→ 垃圾廣告檢測
        ↓
    [優先級評分] - 確定處理優先級
        ↓
    [人工審核隊列] - 將爭議內容分配給人工
        ↓
    [持續學習] - 從人工審核結果改進模型
```

### 核心實現

```python
from dataclasses import dataclass
from enum import Enum
from langgraph.graph import StateGraph, START, END

class ContentRisk(str, Enum):
    SAFE = "safe"
    WARN = "warn"
    REMOVE = "remove"
    REVIEW = "review"

@dataclass
class ContentModerationState:
    content_id: str
    content_text: str
    user_id: str
    
    # 審核結果
    risk_level: ContentRisk = None
    risk_score: float = 0.0  # 0-1
    risk_categories: list[str] = None
    context_analysis: str = None
    human_review_needed: bool = False
    confidence: float = 0.0

class ContentModerationWorkflow:
    def rapid_filter(self, state: ContentModerationState) -> ContentModerationState:
        """快速過濾明顯違規內容"""
        illegal_keywords = ["枪", "炸弹", "毒药"]  # 簡化示例
        
        if any(kw in state.content_text for kw in illegal_keywords):
            state.risk_level = ContentRisk.REMOVE
            state.risk_score = 0.99
            return state
        
        # 進入深度分析
        return state
    
    def deep_analysis(self, state: ContentModerationState) -> ContentModerationState:
        """深度內容分析"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        分析以下內容的風險等級。
        
        內容：{state.content_text}
        
        返回 JSON：
        {{
            "risk_categories": ["色情", "暴力", "垃圾", "仇恨", "其他"],
            "risk_score": 0.0-1.0,
            "context": "簡短說明",
            "requires_human_review": true/false
        }}
        """
        
        response = model.invoke(prompt)
        result = eval(response.content)
        
        state.risk_score = result["risk_score"]
        state.risk_categories = result["risk_categories"]
        state.context_analysis = result["context"]
        state.human_review_needed = result["requires_human_review"]
        state.confidence = 0.95  # 基於模型配置
        
        return state
    
    def decide_action(self, state: ContentModerationState) -> str:
        """決定審核動作"""
        if state.risk_score >= 0.9:
            return "remove"
        elif state.risk_score >= 0.7:
            return "warn"
        elif state.human_review_needed:
            return "review"
        else:
            return "approve"
    
    def build_workflow(self):
        workflow = StateGraph(ContentModerationState)
        
        workflow.add_node("rapid_filter", self.rapid_filter)
        workflow.add_node("deep_analysis", self.deep_analysis)
        
        workflow.add_edge(START, "rapid_filter")
        
        def should_analyze(state):
            return state.risk_level is None  # 如果已判定為直接刪除，不分析
        
        workflow.add_conditional_edges(
            "rapid_filter",
            lambda s: "deep_analysis" if s.risk_level is None else "decide",
            {"deep_analysis": "deep_analysis"}
        )
        
        workflow.add_node("decide", lambda s: s)
        workflow.add_edge("deep_analysis", "decide")
        workflow.add_edge("decide", END)
        
        return workflow.compile()
```

---

## 2. 實時數據分析和報告生成系統

### 應用場景
金融機構需要即時分析市場數據並生成報告，數據分析平台需要自動洞察和警報。

### 工作流設計

```
數據流入
    ↓
[異常檢測] - 識別異常數據點
    ↓
[特徵提取] - 提取關鍵特徵
    ↓
[因果分析] - AI 分析原因
    ├→ 是否預示趨勢變化？
    ├→ 與歷史對比如何？
    └→ 相關外部事件？
    ↓
[報告生成] - 生成自然語言報告
    ↓
[優先級評分] - 決定是否立即告警
    ↓
[多渠道分發] - 郵件、Slack、儀表板
```

### 核心實現

```python
@dataclass
class DataAnalysisState:
    data_point: dict  # {"metric": "CPU", "value": 95, "timestamp": ...}
    historical_data: list[dict]
    analysis_result: dict = None
    confidence: float = 0.0
    requires_alert: bool = False

class DataAnalysisAgent:
    def anomaly_detection(self, state: DataAnalysisState) -> DataAnalysisState:
        """異常檢測"""
        import statistics
        
        values = [d["value"] for d in state.historical_data[-100:]]
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0
        
        # 如果超過 3 個標準差
        z_score = (state.data_point["value"] - mean) / stdev if stdev > 0 else 0
        
        state.is_anomaly = abs(z_score) > 3
        state.z_score = z_score
        
        return state
    
    def ai_root_cause_analysis(self, state: DataAnalysisState) -> DataAnalysisState:
        """AI 根因分析"""
        if not state.is_anomaly:
            return state
        
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        分析以下異常的根本原因：
        
        指標：{state.data_point['metric']}
        當前值：{state.data_point['value']}
        歷史均值：{statistics.mean([d['value'] for d in state.historical_data[-100:]])}
        時間戳：{state.data_point['timestamp']}
        
        可能的原因和建議的行動：
        """
        
        response = model.invoke(prompt)
        state.analysis_result = {
            "root_cause": response.content,
            "confidence": 0.85
        }
        
        return state
    
    def decide_alert(self, state: DataAnalysisState) -> str:
        """決定是否告警"""
        if state.is_anomaly and state.z_score > 5:
            return "critical_alert"
        elif state.is_anomaly:
            return "warning_alert"
        else:
            return "no_alert"
```

---

## 3. 個性化教育內容生成系統

### 應用場景
在線教育平台、企業培訓、個性化學習路徑。

### 工作流設計

```
學生提交問題
    ↓
[理解能力評估] - 評估學生當前水平
    ↓
[內容匹配] - 找到合適難度的解釋
    ├→ 太簡單？提高複雜度
    ├→ 太難？簡化概念
    └→ 剛好？深化理解
    ↓
[多角度解釋] - 用不同方式解釋
    ├→ 代碼示例
    ├→ 類比說明
    ├→ 視覺圖表
    └→ 實際應用案例
    ↓
[互動練習生成] - 創建個性化練習
    ↓
[反饋和調整] - 根據表現調整策略
```

### 核心實現

```python
@dataclass
class StudentLearningState:
    student_id: str
    current_question: str
    learning_history: list[dict]  # [{"topic": "...", "score": 0.8}]
    proficiency_level: float  # 0-1
    
    # 生成的內容
    explanation: str = None
    examples: list[str] = None
    exercises: list[dict] = None

class AdaptiveLearningAgent:
    def assess_proficiency(self, state: StudentLearningState) -> StudentLearningState:
        """評估學生水平"""
        if not state.learning_history:
            state.proficiency_level = 0.5  # 新用戶
            return state
        
        # 基於過往記錄計算水平
        recent_scores = [h["score"] for h in state.learning_history[-10:]]
        state.proficiency_level = sum(recent_scores) / len(recent_scores)
        
        return state
    
    def generate_explanation(self, state: StudentLearningState) -> StudentLearningState:
        """生成個性化解釋"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        # 根據水平選擇難度
        difficulty = "simple" if state.proficiency_level < 0.3 else \
                   "medium" if state.proficiency_level < 0.7 else "advanced"
        
        prompt = f"""
        用{difficulty}難度解釋以下概念。
        
        問題：{state.current_question}
        
        包含：
        1. 簡潔定義
        2. 實際例子
        3. 常見誤區
        """
        
        response = model.invoke(prompt)
        state.explanation = response.content
        
        return state
    
    def generate_practice(self, state: StudentLearningState) -> StudentLearningState:
        """生成個性化練習"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        為水平為 {state.proficiency_level:.1%} 的學生生成 3 道練習題。
        
        主題：{state.current_question}
        
        返回 JSON：
        [
            {{"question": "...", "options": [...], "correct_answer": "..."}},
            ...
        ]
        """
        
        response = model.invoke(prompt)
        import json
        state.exercises = json.loads(response.content)
        
        return state
```

---

## 4. 智能代碼審查和優化系統

### 應用場景
GitHub Actions、GitLab CI/CD、IDE 插件。開發者推送代碼時自動審查。

### 工作流設計

```
代碼變更
    ↓
[靜態分析] - 檢查常見問題
    ├→ 安全漏洞
    ├→ 性能問題
    └→ 代碼風格
    ↓
[AI 代碼審查] - 深度代碼理解
    ├→ 邏輯是否正確？
    ├→ 邊界情況是否處理？
    ├→ 是否有更好的實現？
    └→ 文檔是否充分？
    ↓
[測試覆蓋分析] - 是否有必要的測試？
    ↓
[自動優化建議] - 性能和可讀性優化
    ↓
[報告生成] - 生成 PR 審查注釋
```

### 核心實現

```python
@dataclass
class CodeReviewState:
    pr_id: str
    files_changed: list[dict]  # [{"filename": "...", "diff": "..."}]
    security_issues: list[dict] = None
    performance_issues: list[dict] = None
    suggestions: list[str] = None
    test_coverage: float = 0.0

class CodeReviewAgent:
    def analyze_security(self, state: CodeReviewState) -> CodeReviewState:
        """安全性分析"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        all_code = "\n\n".join([
            f"# {f['filename']}\n{f['diff']}"
            for f in state.files_changed
        ])
        
        prompt = f"""
        分析以下代碼的安全問題。
        
        代碼：
        {all_code}
        
        返回 JSON：
        {{
            "issues": [
                {{"type": "SQL Injection", "severity": "high", "location": "line X"}},
                ...
            ],
            "recommendations": ["..."]
        }}
        """
        
        response = model.invoke(prompt)
        import json
        result = json.loads(response.content)
        state.security_issues = result["issues"]
        
        return state
    
    def suggest_improvements(self, state: CodeReviewState) -> CodeReviewState:
        """建議改進"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        建議代碼改進（性能、可讀性、最佳實踐）。
        
        當前代碼缺陷：
        - 安全問題：{len(state.security_issues or [])} 個
        - 性能問題：{len(state.performance_issues or [])} 個
        
        建議優化的 TOP 3：
        """
        
        response = model.invoke(prompt)
        state.suggestions = response.content.split("\n")
        
        return state
```

---

## 5. 多語言客服系統

### 應用場景
全球化業務，客戶來自不同國家和語言背景。

### 工作流設計

```
用戶提交工單（任意語言）
    ↓
[語言檢測和翻譯]
    ├→ 檢測源語言
    ├→ 翻譯為工作語言（英文）
    └→ 保存原始語言
    ↓
[智能分類和路由]
    ├→ 識別問題類型
    ├→ 匹配最適合的服務代表（可能需要語言技能）
    └→ 評估優先級
    ↓
[生成回應（原始語言）]
    └→ 在源語言中回覆
    ↓
[質量檢查]
    ├→ 確保翻譯準確
    └→ 驗證上下文適當性
```

### 核心實現

```python
from langdetect import detect
from langchain.chains import LLMChain

@dataclass
class MultilingualTicketState:
    ticket_id: str
    original_text: str
    source_language: str = None
    working_language_text: str = None  # 翻譯為英文
    category: str = None
    response_draft: str = None
    response_final: str = None  # 翻譯回源語言

class MultilingualAgent:
    async def detect_and_translate(self, state: MultilingualTicketState) -> MultilingualTicketState:
        """檢測語言並翻譯"""
        from langchain_anthropic import ChatAnthropic
        
        # 檢測語言
        state.source_language = detect(state.original_text)
        
        if state.source_language == "en":
            state.working_language_text = state.original_text
        else:
            # 翻譯
            model = ChatAnthropic()
            prompt = f"""
            將以下 {state.source_language} 文本翻譯為英文。
            
            文本：{state.original_text}
            
            只返回翻譯結果，不要其他說明。
            """
            
            response = model.invoke(prompt)
            state.working_language_text = response.content
        
        return state
    
    async def generate_response_in_target_language(self, state: MultilingualTicketState) -> MultilingualTicketState:
        """用源語言生成回應"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        # 先用英文生成
        prompt = f"""
        根據以下工單信息生成客服回應。
        
        工單：{state.working_language_text}
        類別：{state.category}
        """
        
        response = model.invoke(prompt)
        state.response_draft = response.content
        
        # 如果不是英文，翻譯回源語言
        if state.source_language != "en":
            translate_prompt = f"""
            將以下英文回應翻譯為 {state.source_language}，保持專業且友好的語氣。
            
            英文：{state.response_draft}
            """
            
            trans_response = model.invoke(translate_prompt)
            state.response_final = trans_response.content
        else:
            state.response_final = state.response_draft
        
        return state
```

---

## 6. 實時知識圖譜構建系統

### 應用場景
文檔管理、企業知識庫、自動化 Wiki 維護。

### 工作流設計

```
新文檔上傳
    ↓
[概念提取] - 識別關鍵概念和實體
    ↓
[關係發現] - 發現概念間的關係
    ├→ 包含關係（is-a）
    ├→ 因果關係（causes）
    └→ 相似關係（similar-to）
    ↓
[衝突檢測] - 檢查是否與現有知識衝突
    ↓
[圖譜更新] - 更新知識圖
    ↓
[自動交叉鏈接] - 連結相關文檔
```

### 核心實現

```python
@dataclass
class KnowledgeGraphState:
    document_id: str
    content: str
    extracted_entities: list[str] = None
    extracted_relations: list[tuple] = None  # [(entity1, relation, entity2)]
    conflicts: list[dict] = None
    new_links: list[dict] = None

class KnowledgeGraphAgent:
    def extract_entities(self, state: KnowledgeGraphState) -> KnowledgeGraphState:
        """提取實體"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        從以下文本中提取所有關鍵概念和實體。
        
        文本：{state.content[:1000]}...
        
        返回 JSON：
        ["entity1", "entity2", "entity3", ...]
        """
        
        response = model.invoke(prompt)
        import json
        state.extracted_entities = json.loads(response.content)
        
        return state
    
    def extract_relations(self, state: KnowledgeGraphState) -> KnowledgeGraphState:
        """提取關係"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        entities_str = ", ".join(state.extracted_entities)
        
        prompt = f"""
        識別以下實體之間的關係。
        
        實體：{entities_str}
        文本：{state.content[:1000]}...
        
        返回 JSON：
        [
            {{"entity1": "A", "relation": "causes", "entity2": "B"}},
            ...
        ]
        """
        
        response = model.invoke(prompt)
        import json
        state.extracted_relations = json.loads(response.content)
        
        return state
```

---

## 7. AI 驅動的故障排查系統

### 應用場景
IT 運維、應用診斷、客戶支持。

### 工作流設計

```
故障報告
    ↓
[症狀分析] - 分析報錯消息和日誌
    ├→ 解析堆棧跟踪
    ├→ 識別異常模式
    └→ 提取關鍵信息
    ↓
[根因推理] - AI 推測根本原因
    ├→ 可能原因排序
    ├→ 置信度評分
    └→ 所需更多信息
    ↓
[自動解決步驟] - 如果可能的話自動修復
    ├→ 清理緩存？
    ├→ 重啟服務？
    ├→ 更新配置？
    └→ 需要人工介入？
    ↓
[驗證] - 確認問題解決
    ↓
[知識存儲] - 存儲此案例供未來參考
```

### 核心實現

```python
@dataclass
class TroubleshootingState:
    ticket_id: str
    error_message: str
    logs: str
    system_info: dict
    
    suspected_causes: list[dict] = None  # [{"cause": "...", "confidence": 0.8}]
    suggested_fixes: list[str] = None
    auto_resolution_attempted: bool = False
    resolution_successful: bool = False

class TroubleshootingAgent:
    def analyze_symptoms(self, state: TroubleshootingState) -> TroubleshootingState:
        """分析症狀"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        分析以下故障症狀。
        
        錯誤消息：{state.error_message}
        日誌摘錄：{state.logs[:500]}...
        系統信息：{state.system_info}
        
        可能的根本原因（按可能性排序）：
        """
        
        response = model.invoke(prompt)
        
        # 解析響應提取原因
        causes = response.content.split("\n")
        state.suspected_causes = [
            {"cause": cause.strip(), "confidence": 0.8 - i*0.1}
            for i, cause in enumerate(causes[:5])
        ]
        
        return state
    
    def suggest_fixes(self, state: TroubleshootingState) -> TroubleshootingState:
        """建議修復步驟"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        top_cause = state.suspected_causes[0]["cause"]
        
        prompt = f"""
        根據根本原因建議修復步驟。
        
        根本原因：{top_cause}
        
        返回具體的、可自動執行的步驟：
        1. 
        2.
        3.
        """
        
        response = model.invoke(prompt)
        state.suggested_fixes = response.content.split("\n")
        
        return state
```

---

## 8. 實時合同分析和風險評估系統

### 應用場景
法律科技、合同管理、合規檢查。

### 工作流設計

```
合同上傳
    ↓
[文本提取和結構化] - 識別合同的各個章節
    ↓
[條款分析]
    ├→ 支付條款
    ├→ 責任條款
    ├→ 終止條款
    ├→ 保密協議
    └→ 知識產權
    ↓
[風險識別] - 發現潛在風險
    ├→ 不利的支付條款
    ├→ 過度的責任承諾
    ├→ 不合理的終止條款
    └→ 模糊的定義
    ↓
[對標分析] - 與標準合同對比
    ↓
[建議修訂] - 生成修訂建議
    ↓
[優先級排序] - 重要問題優先
```

### 核心實現

```python
@dataclass
class ContractAnalysisState:
    contract_id: str
    contract_text: str
    contract_type: str  # NDA, SLA, Employment, etc.
    
    sections: dict = None  # {"terms": "...", "liability": "..."}
    risk_items: list[dict] = None
    estimated_exposure: str = None  # low, medium, high, critical
    recommendations: list[str] = None

class ContractAnalysisAgent:
    def extract_sections(self, state: ContractAnalysisState) -> ContractAnalysisState:
        """提取合同章節"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        識別 {state.contract_type} 合同的主要章節。
        
        合同（前 2000 字）：
        {state.contract_text[:2000]}...
        
        返回 JSON：
        {{
            "sections": {{
                "payment_terms": "...",
                "liability": "...",
                "termination": "...",
                "confidentiality": "...",
                "intellectual_property": "..."
            }}
        }}
        """
        
        response = model.invoke(prompt)
        import json
        state.sections = json.loads(response.content)["sections"]
        
        return state
    
    def identify_risks(self, state: ContractAnalysisState) -> ContractAnalysisState:
        """識別風險"""
        from langchain_anthropic import ChatAnthropic
        
        model = ChatAnthropic()
        
        prompt = f"""
        識別此合同的法律和商業風險。
        
        合同類型：{state.contract_type}
        支付條款：{state.sections.get('payment_terms')}
        責任：{state.sections.get('liability')}
        
        列出所有風險項（嚴重性: low/medium/high/critical）：
        
        返回 JSON：
        [
            {{"issue": "支付期限為 120 天", "severity": "high", "recommendation": "爭取改為 30 天"}},
            ...
        ]
        """
        
        response = model.invoke(prompt)
        import json
        state.risk_items = json.loads(response.content)
        
        # 評估總體風險
        severities = [item["severity"] for item in state.risk_items]
        if "critical" in severities:
            state.estimated_exposure = "critical"
        elif severities.count("high") >= 2:
            state.estimated_exposure = "high"
        else:
            state.estimated_exposure = "medium"
        
        return state
```

---

## 9. 實時個人化推薦系統

### 應用場景
電子商務、流媒體、內容平台。

### 核心特點

```
用戶行為流
    ↓
[實時特徵計算]
    ├→ 瀏覽歷史
    ├→ 購買行為
    ├→ 搜索查詢
    └→ 互動信號
    ↓
[AI 理解用戶意圖]
    ├→ 用戶想要什麼？
    ├→ 用戶在尋找什麼類型的產品？
    └→ 用戶有什麼痛點？
    ↓
[實時推薦生成]
    ├→ 精準匹配
    ├→ 多樣化
    └→ 新鮮度平衡
    ↓
[A/B 測試]
    └→ 持續優化
```

---

## 10. 智能研究助手系統

### 應用場景
學術研究、市場調研、競爭分析。

### 工作流設計

```
研究問題
    ↓
[文獻搜索] - 查找相關文獻
    ↓
[內容摘要] - 總結每篇文獻
    ↓
[共識提取] - 在文獻間尋找共識
    ↓
[分歧識別] - 識別不同觀點
    ↓
[見解綜合] - AI 生成新見解
    ↓
[報告生成] - 構建研究報告
    ├→ 執行摘要
    ├→ 背景
    ├→ 主要發現
    ├→ 矛盾的觀點
    ├→ 建議下一步研究
    └→ 參考文獻
```

---

## 未來方向：LangGraph 進階應用

### 1. 自適應工作流

```
根據中間結果動態調整工作流。

示例：
- 如果分類置信度低，自動增加驗證步驟
- 如果需要人工審核，自動路由給合適的人
- 根據歷史成功率調整 Agent 組合
```

### 2. 多 Agent 辯論系統

```
多個 Agent 對立場進行辯論，AI 仲裁。

優點：
- 更全面的分析
- 減少單一 Agent 的偏見
- 生成更有見地的結論
```

### 3. 人機混合工作流

```
AI 完成 70% 工作，人工審查 30%。

優勢：
- 充分利用 AI 的速度
- 保持人工的判斷力
- 持續學習和改進
```

### 4. 多模態工作流

```
不僅處理文本，還包括：
- 圖像分析
- 音視頻處理
- 表格數據
- 實時流數據
```

### 5. 跨組織工作流

```
多個組織的系統協作。

用例：
- 供應鏈協調
- 多方審批流程
- 去中心化決策
```

---

## 選擇合適的用例

| 場景 | 複雜度 | 價值 | 實現周期 |
|------|-------|------|--------|
| 客服分類 | 低 | 中 | 1-2 周 |
| 內容審核 | 中 | 高 | 2-4 周 |
| 代碼審查 | 中 | 高 | 3-6 周 |
| 合同分析 | 高 | 很高 | 4-8 周 |
| 知識圖譜 | 高 | 很高 | 6-12 周 |

---

## 總結

LangGraph 的威力在於它能將**複雜的決策邏輯**變成**可追蹤、可控制的工作流**。每個上述案例都代表著一個真實的商業價值——效率提升、成本降低、質量改善。

選擇一個靠近你的領域的案例，開始你的 LangGraph 之旅。未來屬於那些能夠將 AI 集成到業務流程中的公司。
