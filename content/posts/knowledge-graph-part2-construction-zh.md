---
title: "Knowledge Graph 知識圖譜（二）：從零建構 — NER、關係抽取與 Neo4j 實作"
date: 2026-06-29T10:00:00+08:00
draft: false
weight: 2
description: "動手建知識圖譜：命名實體辨識（NER）、實體消歧、關係抽取的完整管線，並用 Python + spaCy + Neo4j + Cypher 把純文字變成可查詢的圖。"
categories: ["engineering", "ai", "all"]
tags: ["Knowledge Graph", "知識圖譜", "Neo4j", "Cypher", "NER", "spaCy", "Graph Database"]
authors: ["yen"]
readTime: "23 min"
series: ["knowledge-graph"]
---

> *大多數人以為建知識圖譜就是把資料倒進圖資料庫。*
> *正確答案是：難的不是儲存，是把非結構化文字「抽」成乾淨的三元組。*
> *大多數人忽略實體消歧，於是「蘋果公司」和「蘋果（水果）」變成同一個節點。*
> *正確答案是：消歧與對齊，決定了圖的品質上限。*

---

## 接續 Part 1

[Part 1](/posts/knowledge-graph-part1-fundamentals-zh/) 我們建立了概念：三元組、本體、RDF 與屬性圖。這一篇要從一段純文字開始，走完整條**建構管線（construction pipeline）**，最後把成果存進 Neo4j、用 Cypher 查詢。

---

## 一、核心問題：知識從哪裡來？

知識圖譜的三元組不會憑空出現。來源大致兩類：

- **結構化資料**：資料庫、CSV、API。相對容易，做欄位映射（mapping）即可。
- **非結構化資料**：文章、新聞、PDF、網頁。佔現實世界 80% 以上的知識，但要先「抽取」。

本篇聚焦最難也最有價值的後者。整條管線如下：

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  原始文本     │──▶│  命名實體辨識  │──▶│  實體消歧/對齊 │──▶│  關係抽取      │
│  (Raw Text)  │   │  (NER)        │   │ (Disambig.)  │   │ (Relation)   │
└──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
                                                                 │
                  ┌──────────────┐   ┌──────────────┐           │
                  │  圖查詢       │◀──│  寫入圖資料庫  │◀──────────┘
                  │  (Cypher)    │   │  (Neo4j)     │
                  └──────────────┘   └──────────────┘
```

---

## 二、Top-Down vs Bottom-Up：兩種建構策略

在動手前，先決定整體策略。這是個影響後續所有工作量的根本選擇。

| 策略 | 做法 | 優點 | 缺點 | 適用 |
|------|------|------|------|------|
| **Top-Down（自頂向下）** | 專家先設計本體（schema），再把資料往裡填 | 品質高、語意嚴謹、好推理 | 啟動慢、需領域專家、彈性低 | 生醫、金融、法規等嚴謹領域 |
| **Bottom-Up（自底向上）** | 先從資料自動抽取，再歸納出 schema | 快速、覆蓋廣、適合大規模 | 雜訊多、需大量清洗與驗證 | 開放領域、探索性專案、LLM 抽取 |

**為什麼選 Bottom-Up 不選 Top-Down（在 LLM 時代）**：過去 Bottom-Up 的最大痛點是抽取品質差，需要大量人工校驗。但 LLM 大幅降低了抽取門檻（Part 5 會展示），讓「先抽再歸納」變得實際可行。**翻轉條件**：當你的領域有法律/醫療責任、錯誤代價極高時，仍應回到 Top-Down，由專家先定義嚴格本體。

---

## 三、命名實體辨識（NER）

NER 的任務：從文字中找出**實體**並分類（人名、組織、地點、時間…）。先用 spaCy 看最快的入門：

```python
# pip install spacy && python -m spacy download zh_core_web_trf
import spacy

nlp = spacy.load("zh_core_web_trf")
text = "克里斯多福·諾蘭執導的《全面啟動》於 2010 年上映，由李奧納多主演。"

doc = nlp(text)
for ent in doc.ents:
    print(f"{ent.text:12} → {ent.label_}")

# 輸出（示意）：
# 克里斯多福·諾蘭   → PERSON
# 全面啟動          → WORK_OF_ART
# 2010 年           → DATE
# 李奧納多          → PERSON
```

傳統 NER 模型（spaCy、BERT-NER）的限制是**只能辨識預先訓練過的類別**。遇到「導演」「主演」這種領域關係，或冷門實體類型，往往力不從心。這也是後面我們轉向 LLM 抽取的動機。

---

## 四、實體消歧與對齊（Entity Disambiguation & Linking）

這是最容易被新手跳過、卻最影響品質的一步。同一個實體在文本中可能有多種寫法，不同實體又可能同名：

```
問題一：同實體多別名（要合併成同一節點）
  「諾蘭」「克里斯多福·諾蘭」「Christopher Nolan」 → 都是同一人

問題二：同名不同實體（要拆成不同節點）
  「蘋果」在「蘋果發表新手機」 → Apple Inc.（組織）
  「蘋果」在「一天一蘋果」     → Apple（水果）
```

實務上的對齊（Entity Linking）做法是：把抽到的實體連到一個**權威 ID**（canonical ID），例如 Wikidata 的 QID：

```python
# 概念示意：把抽到的 mention 對齊到 Wikidata QID
ENTITY_REGISTRY = {
    "諾蘭":          "Q25191",   # Christopher Nolan
    "克里斯多福·諾蘭": "Q25191",
    "全面啟動":       "Q25188",   # Inception
}

def canonicalize(mention: str) -> str:
    """把不同別名映射到同一個權威 ID，避免重複節點。"""
    return ENTITY_REGISTRY.get(mention, f"_local:{mention}")
```

在生產系統中，這一步會用「候選生成 + 上下文消歧」模型（如 BLINK、ReFinED），或直接交給 LLM 判斷（Part 5）。記住一個原則：**消歧做不好，圖就是一團糊。**

---

## 五、關係抽取（Relation Extraction）

有了實體，接著要找出它們之間的**關係**，組成三元組。三種主流做法：

| 做法 | 原理 | 優點 | 缺點 |
|------|------|------|------|
| 規則 / 模式 | 寫 pattern：「X 執導 Y」 | 精準、可解釋 | 覆蓋率低、難維護 |
| 監督式模型 | 標註資料訓練分類器 | 品質穩定 | 需大量標註 |
| LLM 抽取 | 提示 LLM 輸出三元組 | 零標註、彈性高 | 需驗證、有幻覺風險 |

先看一個用 spaCy 依存句法（dependency parsing）的規則式範例，理解底層原理：

```python
import spacy
nlp = spacy.load("zh_core_web_trf")

def extract_svo(text):
    """抽取 主語-動詞-賓語 三元組（簡化版）。"""
    doc = nlp(text)
    triples = []
    for token in doc:
        if token.pos_ == "VERB":
            subj = [w for w in token.lefts  if w.dep_ in ("nsubj", "nsubjpass")]
            obj  = [w for w in token.rights if w.dep_ in ("dobj", "obj")]
            if subj and obj:
                triples.append((subj[0].text, token.lemma_, obj[0].text))
    return triples

print(extract_svo("諾蘭執導全面啟動"))
# [('諾蘭', '執導', '全面啟動')]
```

規則式適合小範圍、高精度需求；要規模化，Part 5 會用 LLM 一次完成 NER + 關係抽取。

---

## 六、用 Neo4j 落地：把三元組存成圖

抽出三元組後，存進圖資料庫。我們用 Neo4j（屬性圖模型，Cypher 查詢語言）。先啟動一個本機實例：

```bash
# 用 Docker 跑 Neo4j（最快的起步方式）
docker run -d --name neo4j-kg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 \
  neo4j:5
# 瀏覽器打開 http://localhost:7474 即可看圖
```

用 Python driver 寫入：

```python
# pip install neo4j
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687",
                              auth=("neo4j", "password123"))

# 我們的三元組（subject, predicate, object, 加上型別）
triples = [
    ("Nolan",    "Person", "DIRECTED", "Inception", "Movie"),
    ("DiCaprio", "Person", "ACTED_IN", "Inception", "Movie"),
    ("DiCaprio", "Person", "ACTED_IN", "TheRevenant", "Movie"),
    ("RDJ",      "Person", "ACTED_IN", "IronMan", "Movie"),
    ("IronMan",  "Movie",  "PART_OF",  "Marvel",   "Franchise"),
]

def upsert_triple(tx, s, s_type, rel, o, o_type):
    # MERGE 確保同一實體不會被重複建立（依賴前面的消歧結果）
    tx.run(f"""
        MERGE (s:{s_type} {{name: $s}})
        MERGE (o:{o_type} {{name: $o}})
        MERGE (s)-[:{rel}]->(o)
    """, s=s, o=o)

with driver.session() as session:
    for s, s_type, rel, o, o_type in triples:
        session.execute_write(upsert_triple, s, s_type, rel, o, o_type)

driver.close()
print("知識圖譜建構完成 ✅")
```

`MERGE` 是這裡的關鍵字：它「有則用、無則建」，避免同一個 `Nolan` 被建成多個節點——這也是為什麼 Part 5 的消歧那麼重要，因為 `MERGE` 是靠 `name` 比對的。

---

## 七、用 Cypher 查詢：回答 Part 1 的問題

還記得 Part 1 開頭那個問題嗎？「諾蘭的電影裡，有哪些演員也演過漫威電影？」現在用 Cypher 跑起來：

```cypher
MATCH (nolan:Person {name: "Nolan"})-[:DIRECTED]->(m:Movie)
MATCH (actor:Person)-[:ACTED_IN]->(m)
MATCH (actor)-[:ACTED_IN]->(other:Movie)-[:PART_OF]->(:Franchise {name: "Marvel"})
RETURN DISTINCT actor.name
```

Cypher 的語法幾乎就是「把圖畫出來」：`(節點)-[:關係]->(節點)`。對照 Part 1 的 SQL 七重 JOIN，這裡的可讀性差距一目了然。

幾個常用查詢模式：

```cypher
-- 1. 諾蘭執導了哪些電影？（一跳）
MATCH (:Person {name:"Nolan"})-[:DIRECTED]->(m) RETURN m.name;

-- 2. 最短路徑：諾蘭和小勞勃道尼透過哪些電影/人連在一起？
MATCH p = shortestPath(
  (:Person {name:"Nolan"})-[*..6]-(:Person {name:"RDJ"})
) RETURN p;

-- 3. 找出「橋樑演員」：同時連結諾蘭電影與漫威電影
MATCH (a:Person)-[:ACTED_IN]->(:Movie)<-[:DIRECTED]-(:Person {name:"Nolan"})
MATCH (a)-[:ACTED_IN]->(:Movie)-[:PART_OF]->(:Franchise {name:"Marvel"})
RETURN a.name, count(*) AS bridges ORDER BY bridges DESC;
```

`shortestPath` 與 `[*..6]`（變長路徑）是知識圖譜的殺手級功能——在關聯式資料庫裡實作「任意跳數的最短路徑」幾乎是惡夢。

---

## 八、品質保證：圖建好之後的驗收

抽取管線跑完不代表結束。一個沒人驗收的知識圖譜，雜訊會悄悄累積到無法使用。建議的檢查清單：

```
品質驗收 Checklist
├─ 實體層
│   ├─ [ ] 重複節點檢查：同實體是否被建成多個？（消歧失敗的信號）
│   ├─ [ ] 孤兒節點檢查：沒有任何邊的節點通常是抽取雜訊
│   └─ [ ] 型別一致性：同名節點是否被標成不同 Label？
├─ 關係層
│   ├─ [ ] 方向正確性：抽樣檢查「執導」沒被反向
│   ├─ [ ] 關係密度：節點平均連幾條邊？過低代表抽取漏很多
│   └─ [ ] 違反本體的關係：例如「電影執導了人」這種不合理三元組
└─ 整體
    ├─ [ ] 與權威來源抽樣比對（如 Wikidata）算準確率
    └─ [ ] 連通性：圖是一整塊還是碎成很多孤島？
```

用 Cypher 快速抓常見問題：

```cypher
-- 找孤兒節點（沒有任何關係）
MATCH (n) WHERE NOT (n)--() RETURN n LIMIT 25;

-- 找可能的重複實體（名稱相似但分屬不同節點）
MATCH (a), (b)
WHERE a.name CONTAINS b.name AND id(a) <> id(b)
RETURN a.name, b.name LIMIT 25;
```

---

## 九、本篇小結與下一步

這一篇我們走完了知識圖譜建構的完整管線：

1. **NER** 找出實體，**消歧/對齊** 把別名收斂到權威 ID（品質的關鍵）。
2. **關係抽取** 三種做法：規則、監督式、LLM。
3. 用 **Neo4j + MERGE** 把三元組存成圖，避免重複節點。
4. 用 **Cypher** 做多跳查詢、最短路徑——這是相對 SQL 的核心優勢。
5. 建完一定要做**品質驗收**，否則雜訊會吃掉整個圖的價值。

下一篇（Part 3），我們把知識圖譜放到擂台上，和**關聯式資料庫、向量資料庫、文件資料庫**正面比較：各自擅長什麼、什麼時候該用哪一個、又該如何混搭。

---

## 系列導航

← [Part 1：核心概念、三元組與語意網路](/posts/knowledge-graph-part1-fundamentals-zh/)

→ [Part 3：與關聯式 / 向量 / 文件資料庫的比較](/posts/knowledge-graph-part3-comparison-zh/)

---

*本文為「Knowledge Graph 知識圖譜」系列第 2 篇，共 5 篇。*
