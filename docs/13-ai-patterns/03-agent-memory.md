# 03. Agent Memory — LLM Agent 의 단기/장기 기억

> **학습 목표**: LLM Agent가 (1) 최근 대화 (단기), (2) 의미 기반 과거 사실 검색 (장기), (3) 도구 호출 이력을 Redis 의 List/Stream/Hash/Vector Set 으로 어떻게 모델링하는지 이해한다.
> **예상 소요**: 35분

---

## 1. Agent Memory 의 종류

| 유형 | 무엇 | 적합한 자료형 |
|---|---|---|
| **Short-term** (working memory) | 현재 conversation 의 최근 N개 turn | List 또는 Stream |
| **Long-term semantic** | 과거 모든 사실 / 사용자 선호 / 학습 내용 | Vector Set + Hash |
| **Episodic** | 특정 시점 이벤트 / 도구 호출 이력 | Stream (시간순 + ID) |
| **Procedural** | 워크플로우 상태 / 진행 중 task | Hash + List |

---

## 2. 단기 메모리 — 최근 N turn

### 2.1 List 기반 (단순)

```python
import json, redis
r = redis.Redis(decode_responses=True)

MAX_TURNS = 20

def append_turn(session_id, role, content):
    r.rpush(f"chat:{session_id}", json.dumps({
        "role": role,
        "content": content,
        "ts": time.time(),
    }))
    r.ltrim(f"chat:{session_id}", -MAX_TURNS, -1)
    r.expire(f"chat:{session_id}", 3600)   # 1시간 idle TTL

def get_recent(session_id):
    raw = r.lrange(f"chat:{session_id}", 0, -1)
    return [json.loads(x) for x in raw]
```

LLM 호출 시:
```python
history = get_recent(session_id)
messages = [{"role": "system", "content": "..."}]
messages.extend({"role": h["role"], "content": h["content"]} for h in history)
messages.append({"role": "user", "content": user_input})
```

### 2.2 Stream 기반 (영속 + ID)

```python
def append_turn_stream(session_id, role, content):
    r.xadd(
        f"chat-stream:{session_id}",
        {"role": role, "content": content},
        maxlen=("~", 100),   # 약 100개 유지
    )

def get_recent_stream(session_id, count=20):
    entries = r.xrevrange(f"chat-stream:{session_id}", count=count)
    return list(reversed([{
        "id": id_, "role": fields["role"], "content": fields["content"]
    } for id_, fields in entries]))
```

장점: ID 가 순서 보장, replay / pagination, Consumer Group 으로 분석 분기.

---

## 3. Sliding Window vs Summarization

대화가 길어질 때:

### 3.1 Sliding window (앞부터 자르기)
- LTRIM 으로 자동.
- 단점: 옛 정보 영영 손실.

### 3.2 Summarization (압축)
- 일정 turn 후 옛 부분을 LLM 으로 요약 → summary 키에 저장.

```python
def maybe_summarize(session_id):
    turns = get_recent(session_id)
    if len(turns) < 30: return
    
    old = turns[:20]
    summary = call_llm(f"Summarize: {json.dumps(old)}")
    r.set(f"chat:{session_id}:summary", summary)
    
    # 옛 turn 삭제
    r.ltrim(f"chat:{session_id}", -10, -1)
```

LLM 호출 시:
```python
summary = r.get(f"chat:{session_id}:summary") or ""
recent = get_recent(session_id)

messages = [{"role": "system", "content": f"Previous summary: {summary}"}]
messages.extend(...)
```

---

## 4. 장기 메모리 — Semantic memory

> **"이 사용자가 과거에 한 모든 의미 있는 발화를 임베딩으로 저장. 새 질문에 관련 있는 과거 사실을 검색해서 LLM 에 주기."**

### 4.1 자료 모델

```
mem:vec:user:<user_id>           # Vector Set (멤버 = mem_id, 벡터 = fact 임베딩)
mem:fact:<mem_id>                # Hash (text, ts, source)
```

### 4.2 저장
```python
def remember(user_id, text):
    mem_id = str(uuid.uuid4())
    emb = model.encode(text)
    
    args = ["VADD", f"mem:vec:user:{user_id}", "VALUES", str(DIM)]
    args.extend(str(x) for x in emb)
    args.append(mem_id)
    r.execute_command(*args)
    
    r.hset(f"mem:fact:{mem_id}", mapping={
        "text": text, "ts": int(time.time()), "user_id": str(user_id),
    })
```

### 4.3 검색
```python
def recall(user_id, query, top_k=5):
    q_emb = model.encode(query)
    args = ["VSIM", f"mem:vec:user:{user_id}", "VALUES", str(DIM)]
    args.extend(str(x) for x in q_emb)
    args.extend(["COUNT", str(top_k), "WITHSCORES"])
    res = r.execute_command(*args)
    
    facts = []
    for i in range(0, len(res), 2):
        mem_id, score = res[i], float(res[i+1])
        if score < 0.7: continue   # 너무 동떨어진 건 무시
        text = r.hget(f"mem:fact:{mem_id}", "text")
        facts.append({"text": text, "score": score})
    return facts
```

### 4.4 사용 예
```python
def chat(user_id, message):
    # 1) 단기
    short = get_recent(user_id)
    # 2) 장기 (관련 사실)
    long_facts = recall(user_id, message, top_k=3)
    
    facts_text = "\n".join(f"- {f['text']}" for f in long_facts)
    system = f"""You are a helpful assistant.
Known facts about this user:
{facts_text}
"""
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": h["role"], "content": h["content"]} for h in short)
    messages.append({"role": "user", "content": message})
    
    response = call_llm(messages)
    
    # 3) 새 사실 추출 (간단: 사용자 발화 자체)
    remember(user_id, message)
    
    # 단기 업데이트
    append_turn(user_id, "user", message)
    append_turn(user_id, "assistant", response)
    
    return response
```

---

## 5. Episodic — 도구 호출 이력 (Stream)

LLM Agent 가 도구 호출 시:

```python
def log_tool_call(session_id, tool_name, args, result, success):
    r.xadd(f"agent-log:{session_id}", {
        "tool": tool_name,
        "args": json.dumps(args),
        "result": json.dumps(result)[:1000],  # truncate
        "success": "1" if success else "0",
    })
```

분석:
```python
# 마지막 10개 도구 호출
r.xrevrange(f"agent-log:{session_id}", count=10)

# 실패한 호출만 (xreadgroup 활용)
# 또는 별도 Bloom filter / Hash 로 실패 카운트
```

---

## 6. Procedural — Task 진행 상태

다단계 task 의 상태:

```python
TASK_KEY = f"agent:task:{task_id}"

# 시작
r.hset(TASK_KEY, mapping={
    "goal": "사용자 환불 처리",
    "status": "in_progress",
    "current_step": "verify_purchase",
    "started_at": str(int(time.time())),
})
r.rpush(f"{TASK_KEY}:steps", "verify_purchase")

# 단계 완료
r.hset(TASK_KEY, "current_step", "issue_refund")
r.rpush(f"{TASK_KEY}:steps", "issue_refund")

# 종료
r.hset(TASK_KEY, "status", "completed")
r.expire(TASK_KEY, 86400 * 30)
```

---

## 7. 장기 메모리 의 사실 추출

위 §4.4 는 사용자 발화 통째로 저장. 더 정교한 방법:

```python
def extract_facts(text):
    """LLM 으로 'fact' 추출"""
    prompt = f"""Extract atomic facts from this user message. 
Return as JSON list of strings, each a single fact.

Message: {text}
"""
    response = call_llm(prompt)
    return json.loads(response)

def remember_with_extraction(user_id, message):
    facts = extract_facts(message)
    for fact in facts:
        remember(user_id, fact)
```

예: "내 이름은 김철수이고 서울에 살아" → ["사용자 이름: 김철수", "사용자 거주지: 서울"]

---

## 8. 메모리 관리

| 종류 | 보존 정책 |
|---|---|
| Short-term | LTRIM N + idle TTL (1h~24h) |
| Long-term | TTL 없음 + 정기 evict (오래된 + low confidence) |
| Episodic | XADD MAXLEN ~ + 30일 TTL |
| Procedural | 완료 후 30일 |

→ user 별 메모리 폭증 방지를 위해 **VCARD 임계** 도달 시 LRU evict.

---

## 9. 보안 / 프라이버시

- 사용자별 분리 (`mem:vec:user:<id>`) — 다른 사용자에게 누설 X
- PII (전화번호 / 이메일 / 주민번호) 별도 정책 — 저장 시 마스킹 / 별도 vault
- 사용자가 "내 데이터 모두 삭제" → user 관련 모든 키 일괄 SCAN+DEL
- GDPR right to be forgotten 대응 가능해야 함

---

## 10. 흔한 함정

| 함정 | 설명 |
|---|---|
| 모든 발화 무차별 저장 | 메모리 폭증 + 검색 품질 저하. fact 추출 후 저장. |
| Short-term 만 사용 | 옛 정보 손실 → 매번 자기소개 반복. Long-term 결합. |
| LLM 호출마다 모든 사실 주입 | context window 폭증. recall 로 top_k 만. |
| user_id 분리 안 함 | privacy 사고. namespace 필수. |
| stream maxlen 없음 | 무한 누적. `~ 1000` 권장. |
| 사실 중복 저장 | 같은 사실 여러 번 → 검색 결과 편향. dedup (Bloom filter / hash 체크). |

---

## 11. RedisVL Agent Memory + LangGraph

Redis 공식 RedisVL 가 LangChain / LangGraph 와 통합된 agent memory 추상화 제공.
Redis Agent Memory Server (별도 프로젝트):
- 단기: 세션별 chat history
- 장기: 의미 기반 facts
- consolidation: LLM 으로 정리

> 출처: <https://redis.io/tutorials/build-a-car-dealership-agent-with-google-adk-and-redis-agent-memory/>

---

## 12. 직접 해보기

1. 단순 List 기반 단기 메모리 + LTRIM 으로 N=10 turn 유지.
2. 30 turn 넘으면 summarize 동작 확인.
3. Long-term: 5개 사실 remember → 관련 질문 recall → score 분포.
4. user_id 별 분리 → 두 사용자 메모리 격리 검증.
5. (도전) LangGraph + Redis Agent Memory 로 multi-turn agent.

---

## 13. 참고 자료

- **[Redis Tutorial] Build a car dealership agent with Google ADK + Redis Agent Memory** — <https://redis.io/tutorials/build-a-car-dealership-agent-with-google-adk-and-redis-agent-memory/>
  - 참고 부분: agent memory 모델 — §1, §11 근거

- **[Redis YouTube] Long-Term Memory with LangGraph** — <https://www.youtube.com/watch?v=fsENEq4F55Q>
  - 참고 부분: 단기/장기 메모리 분리 — §1 근거

- **[Redis YouTube] Short-Term Memory with LangGraph** — <https://www.youtube.com/watch?v=k3FUWWEwgfc>
  - 참고 부분: 단기 메모리 패턴 — §2 근거

- **[GitHub] redis/redis-vl-python** — <https://github.com/redis/redis-vl-python>
  - 참고 부분: 메모리 / cache extensions — §11 근거

- **[공식 문서] Streams + Vector Sets** — <https://redis.io/docs/latest/develop/data-types/streams/>, <https://redis.io/docs/latest/develop/data-types/vector-sets/>
  - 참고 부분: 자료형 사용 근거 — §2.2, §4 근거
