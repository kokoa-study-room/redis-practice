# 01. 모니터링 스택 띄우기

> **학습 목표**: docker-compose.monitoring.yml 한 번으로 redis_exporter + Prometheus + Grafana 가 연결된 상태로 뜬다는 것을 확인하고, 메트릭이 흐르는 경로를 이해한다.
> **사전 지식**: 00-getting-started 완료
> **예상 소요**: 15분

---

## 1. 데이터 흐름 (Data Flow)

```
[redis-mon:6390]
   │ (Redis 프로토콜)
   ▼
[redis-exporter:9121]              ← INFO / CLUSTER INFO 등을 호출해 결과를 prometheus 형식으로 변환
   │ /metrics 엔드포인트
   ▼ (HTTP scrape, 기본 5초 간격)
[prometheus:9090]                  ← TSDB에 메트릭 저장 + PromQL 제공
   │
   ▼
[grafana:3000]                     ← Prometheus를 datasource로 등록, 대시보드 표시
   │
   ▼
브라우저 사용자
```

---

## 2. 기동

프로젝트 루트에서:
```bash
docker compose -f docker/docker-compose.monitoring.yml up -d
```

기대 출력:
```
[+] Running 8/8
 ✔ Network redis-monitoring-learning_mon-net   Created
 ✔ Volume "...prometheus-data"                 Created
 ✔ Volume "...grafana-data"                    Created
 ✔ Container redis-mon                         Healthy
 ✔ Container redis-exporter                    Started
 ✔ Container prometheus                        Started
 ✔ Container grafana                           Started
```

상태 확인:
```bash
docker compose -f docker/docker-compose.monitoring.yml ps
```

모두 `Up` (redis-mon은 `healthy`) 이어야 한다.

---

## 3. 각 컴포넌트 직접 확인

### 3.1 Redis 자체

```bash
docker exec redis-mon redis-cli -p 6390 PING
# PONG

docker exec redis-mon redis-cli -p 6390 SET hello "monitor"
docker exec redis-mon redis-cli -p 6390 INFO server | head -10
```

### 3.2 redis_exporter 의 /metrics

```bash
curl -s http://localhost:9121/metrics | grep "^redis_" | head -20
```

기대 출력 (일부):
```
redis_up{...} 1
redis_uptime_in_seconds{...} 12
redis_connected_clients{...} 2
redis_memory_used_bytes{...} 8.7e+06
redis_db_keys{db="db0",...} 1
redis_commands_processed_total{...} 25
...
```

> 출처: <https://github.com/oliver006/redis_exporter#whats-exported>
> 참고 부분: 노출 메트릭 종류 — 본 출력의 메트릭 이름 근거

### 3.3 Prometheus

브라우저: <http://localhost:9090>

상단 탭 → **Status → Targets** 클릭. `redis-exporter` 가 **UP** 인지 확인.

쿼리 (Graph 탭):
```promql
redis_up
```
→ 1 (살아있음)

```promql
rate(redis_commands_processed_total[1m])
```
→ 시간 따라 0~몇십 (현재 부하에 따라)

### 3.4 Grafana

브라우저: <http://localhost:3000>

- 익명 Viewer 접근 가능 (compose에서 `GF_AUTH_ANONYMOUS_ENABLED=true` 설정).
- 편집/삭제 같은 작업은 admin (admin/admin) 로그인.
- 좌측 메뉴 → Dashboards → "Redis Learning — Mini Dashboard" 자동 등록되어 있어야 함.

---

## 4. 부하 발생해서 그래프 보기

```bash
# Redis에 무언가 적재
docker exec redis-mon redis-cli -p 6390 DEBUG POPULATE 100000

# 100k 개 SET 명령 시뮬레이션 (1MB 페이로드 등)
docker run --rm --network redis-monitoring-learning_mon-net \
    redis:8.6-alpine \
    redis-benchmark -h redis-mon -p 6390 -n 100000 -c 50 -q
```

5~10초 대기 후 Grafana → "Commands per second" 패널 — 그래프 솟구침.

---

## 5. 종료 / 정리

```bash
# 컨테이너 종료 (메트릭 데이터는 볼륨에 남음)
docker compose -f docker/docker-compose.monitoring.yml down

# 볼륨까지 (TSDB / Grafana 설정 모두 초기화)
docker compose -f docker/docker-compose.monitoring.yml down -v
```

---

## 6. 흔한 함정

| 증상 | 원인 / 해결 |
|---|---|
| `redis-exporter` UP 안 됨 | Prometheus Status → Targets에서 에러 메시지 확인. 보통 컨테이너 이름 / 포트 매칭 문제. |
| Grafana에서 "No data" | `Datasource: Prometheus` 가 자동 등록됐는지 확인. 또는 Prometheus 가 막 시작했고 첫 scrape 안 끝남 — 5~10초 대기 |
| 대시보드가 비어있음 | `provisioning/dashboards/dashboards.yml` 또는 `dashboards/redis.json` 마운트 실패. 컨테이너 로그 확인 |
| 포트 충돌 (6390/9121/9090/3000) | 호스트의 다른 프로세스가 점유. compose의 `127.0.0.1:호스트:컨테이너` 변경 |
| Apple Silicon에서 일부 이미지 안 뜸 | `platform: linux/amd64` 추가 (대부분 multi-arch라 불필요) |

---

## 7. 직접 해보기

1. `curl http://localhost:9121/metrics | grep ^redis_ | wc -l` — 노출되는 메트릭 개수 확인.
2. Prometheus에서 `redis_db_keys` 그래프 → DEBUG POPULATE 후 변화.
3. `redis-benchmark` 60초 부하 → Grafana의 모든 패널 변동 관찰.
4. Grafana 좌측 메뉴 → Explore → 임의 PromQL 입력해보기.

---

## 8. 참고 자료

- **[GitHub] oliver006/redis_exporter v1.82.0**
  - URL: <https://github.com/oliver006/redis_exporter>
  - 참고 부분: README의 "What's exported" 섹션 — 메트릭 이름 / 라벨 근거

- **[Docker Hub] oliver006/redis_exporter:v1.82.0**
  - URL: <https://hub.docker.com/r/oliver006/redis_exporter/tags>
  - 참고 부분: v1.82.0 / latest / alpine 태그 (2026-03-08) — compose의 이미지 tag 근거

- **[공식 문서] Prometheus configuration**
  - URL: <https://prometheus.io/docs/prometheus/latest/configuration/configuration/>
  - 참고 부분: scrape_configs / static_configs — prometheus.yml 작성 근거

- **[공식 문서] Grafana provisioning**
  - URL: <https://grafana.com/docs/grafana/latest/administration/provisioning/>
  - 참고 부분: datasources / dashboards 자동 등록 — provisioning yml 작성 근거
