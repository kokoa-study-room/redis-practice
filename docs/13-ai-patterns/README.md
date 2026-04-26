# 13. AI 패턴 (Redis for AI)

> **이 챕터의 목표**: 2024-2026 LLM 시대에 Redis 가 어떻게 사용되는지 — RAG, Semantic Cache, Agent Memory 의 3대 패턴을 Vector Set / Hash 기반으로 직접 구현해본다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-rag-with-redis.md](01-rag-with-redis.md) | 임베딩 → Vector Set 저장 → 유사 문서 검색 → LLM context 주입 |
| 02 | [02-semantic-cache.md](02-semantic-cache.md) | "비슷한 질문은 같은 답으로" — 의미 기반 캐싱 |
| 03 | [03-agent-memory.md](03-agent-memory.md) | LLM Agent의 단기 / 장기 메모리 (Hash + Stream + Vector Set) |

---

## 사전 지식

- [01-data-types/10-vector-set.md](../01-data-types/10-vector-set.md) — Vector Set 기본
- [01-data-types/03-hash.md](../01-data-types/03-hash.md) — Hash 객체 저장
- [01-data-types/06-stream.md](../01-data-types/06-stream.md) — Stream 이벤트 로그
- 임베딩 모델 기초 (sentence-transformers, OpenAI text-embedding-3-small 등)

---

## 왜 Redis 인가? (다른 vector DB 대비)

| 항목 | Redis 8.x (Vector Set) | 전용 vector DB (Pinecone, Weaviate 등) |
|---|---|---|
| 별도 인프라 | ❌ (캐시 / 세션 함께) | ✅ |
| 메모리 안 latency | μs 단위 | ms~수십 ms |
| 추가 자료형 | String/Hash/Stream/...과 결합 | vector 만 |
| 운영 단순성 | docker compose 1개 | 별도 서비스 |
| 정확도 / 검색 풍부함 | HNSW (8.x), 메타 필터 약함 | 풍부한 필터 / 인덱스 |
| 비용 | 자체 호스팅 | 보통 SaaS |

→ **소규모 ~ 중규모 RAG / agent**: Redis 만으로 충분.
→ **대규모 메타 필터링 + 수억 벡터**: 전용 vector DB + Redis 캐시 조합.

---

## 핵심 개념 한 줄 정리

| 패턴 | 한 줄 |
|---|---|
| **RAG** | "사용자 질문을 임베딩 → 유사 문서 N개 → LLM 에게 context 로 주고 답변 받기" |
| **Semantic Cache** | "사용자 질문 임베딩이 이전 질문과 충분히 유사하면, 이전 답변 재사용" |
| **Agent Memory** | "단기는 최근 대화 (List/Stream), 장기는 의미 기반 검색 (Vector Set)" |
