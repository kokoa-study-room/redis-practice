# 11. 모니터링 스택 (Monitoring) — 선택 / 고급

> **이 챕터의 목표**: redis_exporter + Prometheus + Grafana 로 Redis를 그래프로 들여다본다. SLOWLOG / --latency 만으로 부족할 때 다음 단계.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-monitoring-stack-setup.md](01-monitoring-stack-setup.md) | docker-compose.monitoring.yml 으로 redis_exporter + Prometheus + Grafana 한 번에 띄우기 |
| 02 | [02-grafana-dashboard.md](02-grafana-dashboard.md) | 자동 provisioning 대시보드 + Grafana.com ID 763 import 방법 |
| 03 | [03-key-metrics.md](03-key-metrics.md) | redis_exporter 가 노출하는 핵심 메트릭 12개와 의미 / 알람 규칙 예 |

---

## 환경

본 챕터는 [docker/docker-compose.monitoring.yml](../../docker/docker-compose.monitoring.yml) 을 사용한다.
기본 학습 환경(`docker-compose.yml`) 과 **포트가 다른 별도 Redis 인스턴스 (`redis-mon:6390`)** 를 사용해 충돌하지 않는다.

| 컴포넌트 | 호스트 포트 | 용도 |
|---|---|---|
| redis-mon | 6390 | 모니터링 대상 Redis |
| redis-exporter | 9121 | `/metrics` 엔드포인트 |
| Prometheus | 9090 | 메트릭 수집 / 쿼리 (PromQL) |
| Grafana | 3000 | 대시보드 (admin/admin) |

---

## 사용 흐름

1. 환경 기동 → `01-monitoring-stack-setup.md`
2. Grafana 접속 + 대시보드 확인 → `02-grafana-dashboard.md`
3. 부하 발생 + 메트릭 해석 → `03-key-metrics.md`
4. (심화) Alertmanager + 알람 규칙 → 본 챕터 너머의 운영 영역
