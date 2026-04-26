# 06. 복제 & 고가용성 (Replication & HA)

> **이 챕터의 목표**: master-replica 복제 동작, Sentinel 자동 failover, Cluster의 16384 슬롯 sharding을 이해하고 직접 띄워본다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-replication.md](01-replication.md) | REPLICAOF, full vs partial sync, replica의 역할 |
| 02 | [02-sentinel.md](02-sentinel.md) | Sentinel 3개로 quorum / failover 실습 |
| 03 | [03-cluster.md](03-cluster.md) | 16384 슬롯, CRC16, hashtag, 재샤딩 |

---

## 환경

- 기본 환경: [docker/docker-compose.yml](../../docker/docker-compose.yml) (단일 노드)
- Sentinel 실습: [docker/docker-compose.sentinel.yml](../../docker/docker-compose.sentinel.yml)
- Cluster 실습: [docker/docker-compose.cluster.yml](../../docker/docker-compose.cluster.yml)

각 compose는 별도 포트 사용해서 기본 환경과 함께 띄울 수 있다.

---

## 한눈에 비교

| 모드 | 단일 노드 | Replica 포함 | Sentinel | Cluster |
|---|---|---|---|---|
| HA (자동 failover) | ❌ | ❌ | ✅ | ✅ |
| 데이터 sharding | ❌ | ❌ | ❌ | ✅ |
| 복잡도 | 가장 낮음 | 낮음 | 중간 | 높음 |
| 어울리는 케이스 | 학습 / 캐시 단일 | 읽기 부하 분산 | HA만 필요 | 데이터 양 / TPS 가 한 노드를 넘음 |
