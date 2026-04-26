# 03. 영속성 (Persistence)

> **이 챕터의 목표**: RDB(스냅샷)와 AOF(append-only log)의 차이, 각자의 안전성·성능 트레이드오프를 이해하고 적절한 정책을 선택할 수 있다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-rdb-snapshot.md](01-rdb-snapshot.md) | BGSAVE / SAVE / fork + Copy-on-Write |
| 02 | [02-aof.md](02-aof.md) | appendfsync 정책, AOF 재작성, multi-part AOF |
| 03 | [03-hybrid-and-recovery.md](03-hybrid-and-recovery.md) | RDB+AOF 혼합 모드, 재시작 시 우선순위, 복구 시나리오 |

---

## 한눈에 비교

| 항목 | RDB | AOF |
|---|---|---|
| 무엇? | 메모리 전체를 주기적으로 .rdb 파일에 스냅샷 | 모든 쓰기 명령을 .aof 로그에 append |
| 손실 가능성 | 마지막 스냅샷 이후 변경분 (분 단위) | `appendfsync` 따라 0 ~ 1초 |
| 재시작 시간 | 빠름 (스냅샷 직접 로드) | 느림 (모든 명령 replay) |
| 파일 크기 | 작음 (압축, 메모리 표현 그대로) | 큼 (텍스트 명령) |
| 백업·전송 | 편함 (단일 파일) | 비교적 큼 |
| 운영 추천 | 백업·디재스터 리커버리용 | 데이터 손실 최소화 필요 시 |

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>
> 참고 부분: "RDB advantages" / "AOF advantages" 섹션 — 본 표 근거

---

## 추천 조합 (대부분의 경우)

```
save 3600 1 300 100 60 10000     # RDB는 켬 (백업/리스타트 빠름)
appendonly yes                    # AOF도 켬 (데이터 안전)
appendfsync everysec              # 1초마다 fsync (대부분의 균형)
aof-use-rdb-preamble yes          # 새 AOF 재작성 시 베이스에 RDB 형식 사용 (혼합)
```

> 운영에서는 위 조합이 사실상 표준. 예외: 캐시 전용(데이터 손실 OK) → AOF 끄고 RDB만.

---

준비됐으면 [01-rdb-snapshot.md](01-rdb-snapshot.md) 부터.
