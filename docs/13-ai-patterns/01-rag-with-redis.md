# 01. RAG (Retrieval-Augmented Generation) with Redis

> **학습 목표**: 임베딩 모델로 문서를 벡터화 → Redis Vector Set에 저장 → 사용자 질문 유사 검색 → LLM 에게 context 주입하는 end-to-end RAG 파이프라인을 직접 구현한다.
> **사전 지식**: 01-data-types/10-vector-set.md
> **예상 소요**: 40분

---

## 1. RAG 가 뭔가?

> **"LLM 에게 그 질문에 관련된 문서를 함께 줘서 환각(hallucination) 줄이고 도메인 지식 보강."**

```
질문 "Redis Vector Set이 뭐야?"
   │
   ▼
임베딩 모델 → [0.12, -0.43, ..., 0.88]  (768차원)
   │
   ▼
Redis Vector Set: 가장 유사한 문서 5개 검색
   │
   ▼
context = 5개 문서 본문
   │
   ▼
LLM 프롬프트:
  "다음 context 를 참고해서 답해라.
  context: {본문 5개}
  질문: Redis Vector Set이 뭐야?"
   │
   ▼
LLM 답변
```

> 출처 (개념): <https://redis.io/learn/howtos/solutions/vector/getting-started-vector>
> 참고 부분: RAG 정의와 흐름

---

## 2. 데이터 모델

각 문서를 두 곳에 저장:
- **Vector Set** `docs:vec` — 멤버 = doc_id, 벡터 = 임베딩
- **Hash** `docs:meta:<doc_id>` — title / content / source

```
VADD docs:vec VALUES 768 0.12 -0.43 ... doc:1
HSET docs:meta:doc:1 title "Vector Set 소개" content "..." source "01-data-types/10-vector-set.md"
```

검색 시:
```
VSIM docs:vec VALUES 768 <query_embedding> COUNT 5 WITHSCORES
→ ["doc:1", "0.95", "doc:42", "0.91", ...]

HMGET docs:meta:doc:1 title content
HMGET docs:meta:doc:42 title content
```

---

## 3. 인덱싱 — Python 예제

```python
import os
import redis
from sentence_transformers import SentenceTransformer
import glob

r = redis.Redis(decode_responses=True)
model = SentenceTransformer("all-MiniLM-L6-v2")  # 384 차원, 빠름
DIM = 384

def index_document(doc_id, title, content, source):
    embedding = model.encode(content)
    
    # Vector Set 에 추가
    args = ["VADD", "docs:vec", "VALUES", str(DIM)]
    args.extend(str(x) for x in embedding)
    args.append(doc_id)
    r.execute_command(*args)
    
    # 메타 저장
    r.hset(f"docs:meta:{doc_id}", mapping={
        "title": title,
        "content": content,
        "source": source,
    })

# 본 프로젝트의 docs/ markdown 들을 인덱싱
for path in glob.glob("docs/**/*.md", recursive=True):
    with open(path) as f:
        content = f.read()
    if not content: continue
    title = path.split("/")[-1].replace(".md", "").replace("-", " ")
    doc_id = "doc:" + path.replace("/", "_").replace(".md", "")
    index_document(doc_id, title, content[:5000], path)

print("indexed:", r.execute_command("VCARD", "docs:vec"))
```

---

## 4. 검색 + LLM 호출

```python
def search(query, top_k=5):
    q_emb = model.encode(query)
    
    args = ["VSIM", "docs:vec", "VALUES", str(DIM)]
    args.extend(str(x) for x in q_emb)
    args.extend(["COUNT", str(top_k), "WITHSCORES"])
    result = r.execute_command(*args)
    
    # result = ["doc:1", "0.95", "doc:42", "0.91", ...]
    docs = []
    for i in range(0, len(result), 2):
        doc_id = result[i].decode() if isinstance(result[i], bytes) else result[i]
        score = float(result[i+1])
        meta = r.hgetall(f"docs:meta:{doc_id}")
        docs.append({"id": doc_id, "score": score, **meta})
    return docs

def ask_llm(query, docs):
    context = "\n\n---\n\n".join(
        f"## {d['title']}\n(source: {d['source']})\n\n{d['content']}"
        for d in docs
    )
    prompt = f"""다음 context 를 참고해서 사용자 질문에 답하라.
모르면 모른다고 답하라.

[CONTEXT]
{context}

[QUESTION]
{query}
"""
    # OpenAI / Anthropic / 로컬 LLM 호출
    return openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content

# 사용
docs = search("Redis 의 영속성 옵션은?")
print(ask_llm("Redis 의 영속성 옵션은?", docs))
```

---

## 5. Chunking 전략

큰 문서 (한 markdown 파일 5000자+) 를 통째로 임베딩하면:
- 의미 희석 (한 벡터에 너무 많은 주제)
- LLM context window 압박

→ **chunking** (조각내기):

```python
def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks

def index_with_chunks(path, content, source):
    for idx, chunk in enumerate(chunk_text(content)):
        doc_id = f"doc:{path}:{idx}"
        index_document(doc_id, f"{path} chunk {idx}", chunk, source)
```

권장:
- chunk size: 200~500 토큰 (대략 500~1500자)
- overlap: 10~20% (경계 정보 손실 방지)
- 마크다운 / 코드는 의미 단위 (heading) 로 자르는 게 더 좋음

---

## 6. 성능 / 비용

### 6.1 임베딩 모델 비교

| 모델 | 차원 | 속도 | 품질 | 비용 |
|---|---|---|---|---|
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 매우 빠름 | 중상 | 무료 (로컬) |
| sentence-transformers/all-mpnet-base-v2 | 768 | 빠름 | 상 | 무료 |
| OpenAI text-embedding-3-small | 1536 | 보통 | 상 | $0.02/1M tokens |
| OpenAI text-embedding-3-large | 3072 | 보통 | 매우 상 | $0.13/1M tokens |

### 6.2 Vector Set 양자화

차원 1536 + 1만 문서 = 60MB 메모리 (NOQUANT).
`Q8` 옵션 사용 시 ~15MB. 정확도 미세 손실.

```python
args = ["VADD", "docs:vec", "Q8", "VALUES", str(DIM)]
```

### 6.3 검색 latency

HNSW 검색: 10만 벡터 기준 1~5ms (단일 노드).
LLM 호출: 500ms ~ 수 초 (병목은 보통 LLM).

---

## 7. RediSearch 와의 차이

| 항목 | Vector Set (OSS 8.x) | RediSearch (모듈) |
|---|---|---|
| 메타 필터링 (예: WHERE category="redis") | 어려움 (별도 키 / 클라이언트 필터) | 풍부한 FT.SEARCH 문법 |
| 인덱스 종류 | HNSW | HNSW + FLAT |
| 학습 곡선 | 낮음 | 중상 (FT.CREATE 문법) |
| 적합 | 단순 RAG / agent memory | 복잡한 메타 + 벡터 결합 |

복잡한 RAG (예: "Redis 카테고리의 2024년 이후 문서 중 가장 유사한 것"):
```
FT.SEARCH idx "(@category:{redis} @date:[2024 +inf]) =>[KNN 5 @vec $q]"
```

---

## 8. RedisVL — 고수준 라이브러리 (Python)

Redis 공식 RedisVL (`pip install redisvl`) 가 RAG 흐름을 추상화:

```python
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery

index = SearchIndex.from_yaml("schema.yaml")
index.connect("redis://localhost:6379")
index.create()

# 검색
query = VectorQuery(
    vector=embedding,
    vector_field_name="content_vec",
    return_fields=["title", "content"],
    num_results=5,
)
results = index.query(query)
```

> 출처: <https://github.com/redis/redis-vl-python>
> RedisVL 은 RediSearch 모듈을 사용. Redis 8.x OSS 의 Vector Set 직접 사용은 위 §3-§4 의 raw 패턴.

---

## 9. 흔한 함정

| 함정 | 설명 |
|---|---|
| chunk 없이 큰 문서 한 벡터 | 의미 희석 → 검색 품질 저하 |
| 모델 차원 불일치 | VADD 와 VSIM 의 차원 다르면 에러. VDIM 으로 확인. |
| 임베딩 정규화 안 함 | 일부 거리 함수는 정규화 가정. 모델 docs 확인. |
| 메타 변경 시 임베딩 재생성 안 함 | 검색 결과 stale. content 변경 = 재인덱싱. |
| LLM context 너무 큼 | 비용 + latency. top_k 조절 + chunk 압축 |
| RedisVL 없이 raw 만 사용 | 기능 한정. 복잡 메타 필터링은 RedisVL/RediSearch. |

---

## 10. 직접 해보기

1. 본 프로젝트의 모든 docs/*.md 를 인덱싱.
2. "Redis 가 왜 빠른가?" 질문 → 가장 유사한 5개 문서 출력 (LLM 호출 없이도 가능).
3. chunking 적용 vs 미적용 → 검색 품질 비교.
4. Q8 양자화 vs NOQUANT → 메모리 / 검색 시간 비교.
5. (도전) OpenAI API 와 결합해서 실제 답변 생성.

---

## 11. 참고 자료

- **[Redis Learn] Vector search getting started** — <https://redis.io/learn/howtos/solutions/vector/getting-started-vector>
  - 참고 부분: RAG 흐름 / 사용 사례 — §1 근거

- **[GitHub] redis/redis-vl-python** — <https://github.com/redis/redis-vl-python>
  - 참고 부분: RedisVL API — §8 근거

- **[공식 문서] Vector Sets (OSS 8.x)** — <https://redis.io/docs/latest/develop/data-types/vector-sets/>
  - 참고 부분: VADD / VSIM / 양자화 — §3, §4, §6.2 근거

- **[OpenAI Embeddings API]** — <https://platform.openai.com/docs/guides/embeddings>
  - 참고 부분: 모델 / 차원 / 가격 — §6.1 근거

- **[sentence-transformers]** — <https://www.sbert.net/>
  - 참고 부분: all-MiniLM-L6-v2, all-mpnet-base-v2 모델 정보 — §6.1 근거
