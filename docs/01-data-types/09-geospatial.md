# 09. Geospatial

> **학습 목표**: Geospatial이 Sorted Set 위의 Geohash라는 사실, 근처 검색 / 거리 계산 명령을 사용할 수 있다.
> **예상 소요**: 20분

---

## 1. 개념

Geospatial은 **(longitude, latitude) 좌표를 키에 추가하고 반경/박스 검색**.
내부적으로는 **Sorted Set + Geohash** — 좌표를 52-bit Geohash로 인코딩해서 score로 사용.

용도:
- 근처 매장 찾기
- 배달 라이더 매칭
- 지오펜싱

> 출처: <https://redis.io/docs/latest/develop/data-types/geospatial/>

---

## 2. 기본 사용법

```
# 추가 (lon, lat, member)
GEOADD stores 126.9784 37.5665 "seoul-city-hall"   # 서울시청
GEOADD stores 127.0276 37.4979 "gangnam-station"   # 강남역
GEOADD stores 126.9244 37.5563 "yeouido"           # 여의도

# 옵션 (Redis 6.2+)
GEOADD stores NX 126.9784 37.5665 "seoul-city-hall"   # 없을 때만
GEOADD stores XX 126.9784 37.5665 "seoul-city-hall"   # 있을 때만
GEOADD stores CH 127.0 37.5 "test"                    # CH = changed 개수 반환

# 좌표 조회
GEOPOS stores "seoul-city-hall"
# 1) 1) "126.97840"
#    2) "37.56650"

# 두 점 사이 거리
GEODIST stores "seoul-city-hall" "gangnam-station" km   # ~7.6 km
GEODIST stores "seoul-city-hall" "gangnam-station" m
GEODIST stores "seoul-city-hall" "gangnam-station" mi
GEODIST stores "seoul-city-hall" "gangnam-station" ft

# 근처 검색 (Redis 6.2+ 권장: GEOSEARCH; 그 이전: GEORADIUS)
GEOSEARCH stores FROMLONLAT 126.98 37.56 BYRADIUS 10 km ASC COUNT 10
GEOSEARCH stores FROMMEMBER "seoul-city-hall" BYRADIUS 5 km ASC WITHCOORD WITHDIST

# 박스 검색
GEOSEARCH stores FROMLONLAT 126.98 37.56 BYBOX 20 20 km ASC

# 검색 결과를 다른 키에 저장
GEOSEARCHSTORE result stores FROMLONLAT 126.98 37.56 BYRADIUS 10 km

# Geohash 문자열 (Geohash.org 호환)
GEOHASH stores "seoul-city-hall"
# 1) "wydm9q08m1"
```

> `GEORADIUS`/`GEORADIUSBYMEMBER` 는 deprecated. 신규 코드는 `GEOSEARCH` 사용.
> 출처: <https://redis.io/docs/latest/commands/georadius/> "deprecated"

---

## 3. 클라이언트 코드 예제

### Python — 가까운 매장 찾기

```python
import redis
r = redis.Redis(decode_responses=True)

# 등록
r.geoadd("stores", [
    126.9784, 37.5665, "seoul-city-hall",
    127.0276, 37.4979, "gangnam-station",
    126.9244, 37.5563, "yeouido",
])

# 사용자 위치 (강남역 근처) 기준 5km 내 매장
my_lon, my_lat = 127.030, 37.500
results = r.geosearch(
    "stores",
    longitude=my_lon, latitude=my_lat,
    radius=5, unit="km",
    sort="ASC",
    withcoord=True, withdist=True,
)
# [['gangnam-station', 0.5, (127.0276, 37.4979)], ...]
for name, dist, coord in results:
    print(f"{name}: {dist:.2f} km")
```

### Node.js

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.geoAdd("stores", [
  { longitude: 126.9784, latitude: 37.5665, member: "seoul-city-hall" },
  { longitude: 127.0276, latitude: 37.4979, member: "gangnam-station" },
]);

const results = await r.geoSearch(
  "stores",
  { longitude: 127.030, latitude: 37.500 },
  { radius: 5, unit: "km" },
  { SORT: "ASC", COUNT: { value: 10 } }
);
```

---

## 4. 내부 동작

### 4.1 인코딩

`TYPE stores` → `zset` (사실 Sorted Set이다).
`OBJECT ENCODING` → `listpack` 또는 `skiplist` (멤버 수에 따라).

좌표는 Geohash → 52-bit 정수 → ZSET score (double).

> 출처: <https://github.com/redis/redis/blob/8.6/src/geo.c>
> 참고 부분: `geoEncode` 함수 — Geohash 52-bit 인코딩 코드

### 4.2 Big-O

| 명령 | 복잡도 |
|---|---|
| `GEOADD` | O(log N) (ZADD와 동일) |
| `GEOPOS / GEODIST` | O(log N) per member |
| `GEOSEARCH BYRADIUS` | O(N + log M)  N=결과, M=총 멤버 |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **위/경도 순서 반대** | `GEOADD` 는 **(lon, lat)** 순서. 헷갈리면 한 번 검색 후 `GEOPOS` 로 검증. |
| **GEORADIUS 사용** | deprecated. 신규는 `GEOSEARCH`. |
| **WITHCOORD + WITHDIST 응답 파싱** | 클라이언트마다 표현이 약간 다름. Python은 list, Node는 object. |
| **거리 계산은 평면 가정** | Redis는 Haversine 사용 (지구는 구로 가정). 극지방/매우 큰 거리는 오차 가능. |
| **GEOHASH 결과를 표준 Geohash로 사용** | Redis의 GEOHASH는 표준 11-char Geohash. ZSET score(52-bit 정수)와는 다름. |

---

## 6. RedisInsight

Browser → ZSET 으로 보임. Workbench에서 `GEOSEARCH` 실행 → 결과를 표로.

---

## 7. 직접 해보기

1. 본인 동네 주요 지점 5개 GEOADD.
2. 지점 한 곳 기준 1km 내 다른 지점 GEOSEARCH FROMMEMBER.
3. `TYPE` 확인 → `zset` 임을 직접 보기.
4. `ZRANGE` 로 같은 키의 score 값을 보기 → 큰 정수가 나옴 (Geohash).

---

## 8. 참고 자료

- **[공식 문서] Geospatial**
  - URL: <https://redis.io/docs/latest/develop/data-types/geospatial/>
  - 참고 부분: GEOADD 인자 순서 (lon, lat) — §2 근거

- **[공식 문서] GEOSEARCH**
  - URL: <https://redis.io/docs/latest/commands/geosearch/>
  - 참고 부분: FROM*/BY* 옵션 — §2 근거

- **[공식 문서] GEORADIUS (deprecated)**
  - URL: <https://redis.io/docs/latest/commands/georadius/>
  - 참고 부분: "As of Redis version 6.2.0, this command is regarded as deprecated" — §2 근거

- **[GitHub] redis/redis — src/geo.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/geo.c>
  - 참고 부분: `geoEncode` (52-bit Geohash) — §4.1 근거
