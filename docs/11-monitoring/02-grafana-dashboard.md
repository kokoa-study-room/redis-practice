# 02. Grafana 대시보드

> **학습 목표**: 자동 provisioning 된 미니 대시보드의 패널을 이해하고, Grafana.com 의 더 완성된 대시보드 (ID 763) 를 import 해서 비교한다.
> **예상 소요**: 20분

---

## 1. 자동 provisioning 된 미니 대시보드

본 프로젝트는 **`docker/grafana/dashboards/redis.json`** 을 자동 로딩한다.

| 패널 | PromQL | 의미 |
|---|---|---|
| Redis Up | `redis_up` | 1=살아있음, 0=내려감 |
| Connected Clients | `redis_connected_clients` | 현재 연결 수 |
| Used Memory | `redis_memory_used_bytes` | 메모리 사용량 (bytes) |
| Total Keys (db0) | `sum(redis_db_keys)` | 모든 db의 키 합 |
| Hit Ratio (5m) | `rate(...hits_total[5m]) / (hits + misses)` | 캐시 효율 |
| Uptime | `redis_uptime_in_seconds` | 마지막 시작부터 |
| Commands/sec | `rate(redis_commands_processed_total[1m])` | 처리량 |
| Memory used vs maxmemory | 두 메트릭 비교 | maxmemory 도달 위험 |
| Hits / Misses | rate of each | 히트/미스 절대치 |
| Connected / Blocked | `connected_clients` / `blocked_clients` | 블로킹 클라이언트 추적 |
| Net I/O | `rate(...net_input/output_bytes_total[1m])` | 네트워크 |
| Expired / Evicted | rate of each | TTL 만료 vs eviction |

대시보드 JSON 출처: 본 프로젝트 자체 작성. ID 763 의 핵심 패널을 단순화 / 1 인스턴스 학습 환경에 맞춤.

---

## 2. ID 763 import — 더 완성된 대시보드

### 2.1 import

1. Grafana 좌측 메뉴 → **Dashboards** → 우측 상단 **New** → **Import**
2. **Import via grafana.com** 입력란에 `763` → **Load**
3. Datasource: **Prometheus** 선택 → **Import**

### 2.2 ID 763 vs 미니 대시보드

| 항목 | 미니 (자체) | ID 763 |
|---|---|---|
| 패널 수 | 12개 | 25+개 |
| 단일 인스턴스 가정 | ✅ | 다중 인스턴스 지원 |
| 8.x 신규 메트릭 | 일부 | (작성 시점 기준 6.x/7.x) |
| 학습 친화성 | ✅ (제목·단위 한국 학습용) | △ (영문, 변수 많음) |
| 영구 유지 | ✅ (provisioning) | UI에서 삭제 가능 |

> ID 763 출처: <https://grafana.com/grafana/dashboards/763>
> "Redis - Prometheus Redis Exporter 1.x" / by oliver006 / Updated periodically

---

## 3. 대시보드 패널 직접 추가

미니 대시보드를 편집해서 8.6 신규 메트릭을 추가:

```promql
# HOTKEYS 가 보여주는 hot key 수 (8.6+, redis_exporter가 지원하면)
redis_keyspace_hits_total

# Streams idempotency 추적 수
# (redis_exporter가 XINFO STREAM 메트릭을 노출한다면)
```

새 패널:
1. 우측 상단 **Add** → **Visualization**
2. PromQL 입력
3. Title / Unit 설정 → **Apply**

provisioning 으로 등록된 대시보드는 `allowUiUpdates: true` 옵션으로 UI 편집 허용 (저장은 메모리에만 — `redis.json` 파일을 직접 수정해야 영속).

---

## 4. Grafana → Explore (즉석 PromQL)

좌측 **Explore** 메뉴는 대시보드 없이 즉석 쿼리:

```promql
# 메모리 추세 (1시간)
redis_memory_used_bytes[1h]

# 평균 latency 추정 (commands_total 변화)
rate(redis_commands_processed_total[1m])

# 키 개수 변화 (DB별)
redis_db_keys

# eviction 일어나는지
rate(redis_evicted_keys_total[5m]) > 0
```

---

## 5. 알람 (간단 예)

운영에서는 Prometheus의 **alerting rules** 를 별도 파일로 정의:

```yaml
# prometheus/alerts.yml (예)
groups:
  - name: redis-alerts
    rules:
      - alert: RedisDown
        expr: redis_up == 0
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "Redis instance {{ $labels.instance }} is down"

      - alert: RedisMemoryHigh
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "Redis memory > 90% on {{ $labels.instance }}"

      - alert: RedisHitRatioLow
        expr: |
          rate(redis_keyspace_hits_total[5m]) /
          clamp_min(rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]), 1)
          < 0.5
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "Cache hit ratio < 50% on {{ $labels.instance }}"
```

본 학습 환경에는 추가하지 않음 (학습 흐름을 위해 Alertmanager 까지 띄우진 않음). 운영 가이드: <https://prometheus.io/docs/alerting/latest/overview/>

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| ID 763 import 후 No data | datasource 이름 확인. provisioning 은 "Prometheus" 라는 이름으로 등록 (yaml 의 `name` 필드). |
| 대시보드 변수 (`$instance`) 안 보임 | redis_exporter가 메트릭에 instance 라벨을 넣지 않으면 안 보임. 본 프로젝트 prometheus.yml은 `instance: "redis-mon"` 라벨 명시. |
| 패널이 안 그려짐 | scrape 간격 (5초) + Grafana refresh (10초)에 맞춰 시간 범위 늘리기 (now-30m 기본). |
| Edit 후 저장 안 됨 | provisioning 대시보드는 file이 source. UI 저장은 임시. JSON 파일 직접 수정. |
| Grafana 11.x → 옛 schema | 대시보드 JSON의 `schemaVersion` 호환성 확인 (본 프로젝트는 39). |

---

## 7. 직접 해보기

1. ID 763 import → 미니 대시보드와 어느 패널이 겹치고 어느 게 더 풍부한지.
2. Explore에서 `topk(5, rate(redis_commands_processed_total[1m]))` 실행.
3. 미니 대시보드에 패널 추가: `redis_blocked_clients` 단일 stat.
4. Grafana 시간 범위를 1시간 / 6시간으로 바꿔보기.
5. PromQL `redis_db_keys` 로 키 증가 추이 확인 (DEBUG POPULATE 부하 후).

---

## 8. 참고 자료

- **[Grafana Dashboard 763] Redis - Prometheus Redis Exporter 1.x**
  - URL: <https://grafana.com/grafana/dashboards/763>
  - 참고 부분: 25+ 패널 — §2 비교 근거

- **[공식 문서] Grafana provisioning**
  - URL: <https://grafana.com/docs/grafana/latest/administration/provisioning/>
  - 참고 부분: dashboards / datasources 자동 등록, allowUiUpdates — §1, §3 근거

- **[공식 문서] Prometheus alerting**
  - URL: <https://prometheus.io/docs/alerting/latest/overview/>
  - 참고 부분: alerting rules — §5 근거

- **[GitHub] oliver006/redis_exporter — metric reference**
  - URL: <https://github.com/oliver006/redis_exporter#whats-exported>
  - 참고 부분: 메트릭 이름 / 라벨 — §1 표 근거
