# 02. 내부 구현 (Internals)

> **이 챕터의 목표**: "Redis는 왜 빠른가?"의 진짜 답 — 같은 외부 자료형이 크기에 따라 어떻게 다른 인코딩으로 저장되는지, 각 인코딩의 자료구조 원리를 이해한다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-encoding-overview.md](01-encoding-overview.md) | 외부 자료형 ↔ 내부 인코딩 매핑 표 + 전환 규칙 |
| 02 | [02-sds.md](02-sds.md) | Simple Dynamic String — Redis의 문자열 표현 |
| 03 | [03-listpack-quicklist.md](03-listpack-quicklist.md) | listpack(촘촘한 바이트 배열) + quicklist(노드 링크) |
| 04 | [04-hashtable.md](04-hashtable.md) | dict + 점진적 rehashing |
| 05 | [05-skiplist.md](05-skiplist.md) | 스킵리스트 — Sorted Set의 본체 |
| 06 | [06-intset.md](06-intset.md) | 정수 전용 정렬 배열 |
| 07 | [07-rax-radix-tree.md](07-rax-radix-tree.md) | Stream에서 사용하는 라딕스 트리 |

---

## 인코딩 매핑 표 (한눈에)

| 외부 자료형 | 가능한 인코딩 (Redis 8.x) |
|---|---|
| String | `int`, `embstr`, `raw` |
| List | `listpack`, `quicklist` |
| Hash | `listpack`, `hashtable` |
| Set | `intset`, `listpack`, `hashtable` |
| Sorted Set | `listpack`, `skiplist` (= skiplist + hashtable) |
| Stream | `stream` (rax + listpack 노드) |
| Bitmap/HyperLogLog/Bitfield | (실은 String) → `raw` |
| Geospatial | (실은 ZSET) → `listpack` 또는 `skiplist` |
| Vector Set | `vectorset` (HNSW 그래프) |

> 출처: <https://redis.io/docs/latest/commands/object-encoding/>
> 참고 부분: 인코딩 목록 — 본 표 근거

---

## 왜 인코딩 전환이 의미 있는가?

| 인코딩 패밀리 | 메모리 | 명령 속도 | 적합 상황 |
|---|---|---|---|
| `int` / `intset` | 매우 작음 | 매우 빠름 | 정수 / 작은 정수 셋 |
| `listpack` | 작음, 캐시 친화적 | O(N) 탐색이지만 N이 작음 | 작은 List/Hash/Set/ZSET |
| `embstr` / `raw` | String 표현 | O(1) | 일반 문자열 |
| `hashtable` | 큼 (해시 테이블 구조) | O(1) 룩업 | 큰 Hash/Set |
| `skiplist` (+ ht) | 큼 | O(log N) range | 큰 ZSET |
| `quicklist` | 중간 | O(1) 양 끝 / O(N) 중간 | 큰 List |
| `rax` (+ listpack) | 효율적 (정렬+공유 prefix) | O(log N) lookup | Stream |

**핵심 통찰**: 학습자는 "외부 자료형(String/Hash/...)" 만 신경 쓰면 된다. Redis가 알아서 효율적인 내부 표현을 고른다.
하지만 **"왜 OBJECT ENCODING이 이렇게 나왔는가"** 를 이해하면 메모리/성능 분석에서 우위에 선다.

---

준비됐으면 [01-encoding-overview.md](01-encoding-overview.md) 부터.
