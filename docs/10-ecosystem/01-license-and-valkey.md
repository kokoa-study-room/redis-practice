# 01. 라이선스 변천사 + Valkey

> **학습 목표**: 2024년 Redis 라이선스 변경 (BSD → RSAL/SSPL) 의 배경, Valkey 포크의 등장과 차이점, 어느 쪽을 골라야 하는가에 대한 판단 기준.
> **예상 소요**: 20분

---

## 1. 타임라인

| 시점 | 이벤트 |
|---|---|
| ~2024-03 | Redis Open Source = **BSD 3-Clause** |
| **2024-03-20** | Redis Inc. 라이선스 변경 발표: **RSAL v2 / SSPL v1 듀얼 라이선스** (7.4.0부터 적용) |
| **2024-03-28** | Linux Foundation 산하 **Valkey** 포크 발표 (Redis 7.2.4 기준) |
| 2024-04 ~ | AWS, Google Cloud, Oracle, Alibaba 등 Valkey 합류 |
| 2024-08 | Valkey 7.2.5 (첫 stable) |
| 2025 | Valkey 8.x 릴리즈 (Redis 8과 거의 같은 기능 + 일부 독자) |
| **2025-05-01** | Redis Inc. AGPLv3 옵션 추가 — Redis Open Source가 **OSI 인정 OSS로 회귀** |
| 2026-04 | Redis 8.6.x (AGPLv3/RSAL/SSPL 트리플), Valkey 9.0.x 안정화 |

> 출처:
> - <https://redis.io/blog/redis-adopts-dual-source-available-licensing/> (2024-03 발표)
> - <https://valkey.io/blog/announcing-valkey/> (2024-03 포크)
> - <https://redis.io/blog/agplv3/> (2025-05 AGPLv3 추가)

---

## 2. 라이선스 비교

| 라이선스 | OSI OSS? | 핵심 |
|---|---|---|
| BSD 3-Clause (구) | ✅ | 거의 모든 사용 자유 |
| **RSAL v2** | ❌ (Redis Inc. 정의) | "managed Redis service" 제공 금지 |
| **SSPL v1** | ❌ (OSI 거부) | 서비스로 제공 시 모든 부가 SW 공개 강제 |
| **AGPLv3** (2025-05+) | ✅ | 네트워크 사용도 source 공개 의무 (copyleft) |

**핵심 변화**:
- 2024년: Redis가 **AWS/Google 등 hyperscaler의 managed service** 를 막으려는 움직임.
- 2024년 말~2025년: Valkey 가 자리잡으면서 **Redis Inc. 가 AGPLv3를 추가** (OSI 인정 OSS로 회귀).

---

## 3. Valkey란?

```
"Valkey is a high-performance data structure server that primarily serves
 key/value workloads. It supports a wide range of native structures and an
 extensible plugin system for adding new data structures and access patterns."
```

> 출처: <https://valkey.io/>

특징:
- **Linux Foundation** 산하 (벤더 중립)
- **BSD 3-Clause**
- Redis 7.2.4 fork → 이후 독자 발전
- API/명령어 호환 유지 (적어도 Valkey 8까지는 Redis 7.2와 호환, 일부 신규는 분기 시작)

---

## 4. Redis vs Valkey 호환성

| 항목 | 호환성 |
|---|---|
| 명령 (string/list/hash/...) | 거의 100% |
| Cluster 프로토콜 | 호환 |
| Pub/Sub | 호환 |
| RDB / AOF 파일 형식 | 7.2 시점 호환, 8.x 신기능 (Vector Set 등) 은 분기 |
| **Vector Set** | Redis 8.x 에만 — Valkey는 별도 모듈 / 내장 진행 중 |
| **HOTKEYS** | Redis 8.6+ 에만 |
| **Hash field TTL (HEXPIRE)** | Valkey도 8.x에서 추가 |
| 모듈 (RediSearch 등) | Redis 8 이전: 별도 모듈, Redis 8+: 내장. Valkey는 별도 또는 자체 포크 |

> 일반 학습 / 캐시 / 큐 워크로드는 **둘 중 어느 것을 써도 동일** 하게 동작. 8.x 신기능은 Redis 가 앞서감.

---

## 5. 어느 것을 골라야 하나?

### Redis OSS 8.x 권장 시나리오
- AGPLv3 / RSAL / SSPL 중 하나로 운영 가능
- Vector Set / RediSearch / RedisJSON 등 8.x 통합 기능 필요
- Redis Inc. 의 빠른 신기능 도입 따라가고 싶음
- (Enterprise / Cloud) Redis Cloud 사용

### Valkey 권장 시나리오
- BSD 라이선스가 절대적으로 필요 (라이선스 위험 회피)
- AWS ElastiCache / GCP Memorystore에서 Valkey 옵션 사용
- Linux Foundation 거버넌스 선호
- 7.2~8.0 호환 기능만 사용

### "어느 쪽이든 OK" 시나리오
- 일반 캐시 / 세션 / 큐 (학습 포함)

---

## 6. 마이그레이션

Redis ↔ Valkey 양방향 마이그레이션은 RDB / AOF 파일 호환 + 같은 프로토콜이라 **드롭인 교체** 가능 (호환되는 기능에 한해). 단, Vector Set 같은 8.x 전용 기능은 마이그레이션 시점에 데이터 손실 가능.

---

## 7. 흔한 오해

| 오해 | 실제 |
|---|---|
| Redis는 더이상 OSS가 아니다 | 2025-05부터 AGPLv3 추가로 다시 OSI OSS. |
| Valkey는 Redis와 다른 명령어 | 거의 같음. 호환 노력 명시. |
| Valkey가 항상 더 안전한 라이선스 | 그렇지만 Vector Set 같은 신기능 부재. |
| Redis Stack은 죽었다 | 호환성/배포 편의 목적으로 여전히 배포 (8.x에 흡수된 기능을 별도 패키지로 받고 싶을 때). |

---

## 8. 직접 해보기

1. <https://valkey.io/> 에서 latest stable 버전 확인.
2. `docker pull valkey/valkey:latest` 후 `redis-cli -h 127.0.0.1 -p 6379 PING` 동일 동작.
3. Redis 8.6과 Valkey 8.x 양쪽에서 같은 자료형 명령 비교 (예: `HEXPIRE`, `XADD IDMP`, `VADD`).
4. 라이선스 파일 (`LICENSE.txt`) 읽어보기.

---

## 9. 참고 자료

- **[공식 발표] Redis adopts dual source-available licensing**
  - URL: <https://redis.io/blog/redis-adopts-dual-source-available-licensing/>
  - 참고 부분: 2024-03 발표 — §1, §2 근거

- **[공식 발표] Announcing Valkey**
  - URL: <https://valkey.io/blog/announcing-valkey/>
  - 참고 부분: 포크 동기 — §1, §3 근거

- **[공식 발표] Redis adds AGPLv3**
  - URL: <https://redis.io/blog/agplv3/>
  - 참고 부분: 2025-05 AGPLv3 추가 — §1 근거

- **[Valkey] valkey.io**
  - URL: <https://valkey.io/>
  - 참고 부분: 정의 / 거버넌스 — §3 근거
