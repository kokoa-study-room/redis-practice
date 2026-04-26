# 06. Feed / Timeline (Fan-out 패턴)

> **학습 목표**: SNS 피드 / 알림 / 타임라인을 구현하는 두 가지 접근(Fan-out on Write vs Fan-out on Read)의 트레이드오프, Redis ZSET / Stream으로 모델링.
> **예상 소요**: 25분

---

## 1. 문제

```
사용자 A가 글을 게시 → A의 팔로워 1만 명의 피드에 이 글이 보여야 한다.
```

두 접근:
- **Fan-out on Write (Push)**: 게시 시 1만 명의 피드 큐에 push.
- **Fan-out on Read (Pull)**: 피드를 볼 때 팔로잉 사용자들의 글을 합쳐서 보여줌.

---

## 2. Fan-out on Write

```
posts:<post_id>           # 게시물 본문 (Hash 또는 JSON)
user:<user_id>:feed       # 사용자별 피드 ZSET (score = timestamp)
user:<user_id>:followers  # 팔로워 Set
```

게시 시:
```python
def post(user_id, content):
    post_id = generate_id()
    r.hset(f"posts:{post_id}", mapping={
        "author": user_id,
        "content": content,
        "ts": time.time(),
    })
    
    followers = r.smembers(f"user:{user_id}:followers")
    pipe = r.pipeline()
    for fid in followers:
        pipe.zadd(f"user:{fid}:feed", {post_id: time.time()})
        # 길이 제한 (최근 1000개만)
        pipe.zremrangebyrank(f"user:{fid}:feed", 0, -1001)
    pipe.execute()
```

읽기 (피드 보기):
```python
def get_feed(user_id, limit=20):
    post_ids = r.zrevrange(f"user:{user_id}:feed", 0, limit - 1)
    pipe = r.pipeline()
    for pid in post_ids:
        pipe.hgetall(f"posts:{pid}")
    return pipe.execute()
```

| 장점 | 단점 |
|---|---|
| 읽기 매우 빠름 | 게시 비용 = 팔로워 수 (큰 인플루언서 비용 폭발) |
| 피드 미리 정렬 | 잘못된 push 정정 비용 (deletion 등) |

---

## 3. Fan-out on Read

```
user:<user_id>:posts     # 자기가 쓴 글 ZSET
user:<user_id>:following # 팔로잉 Set
```

읽기 시:
```python
def get_feed(user_id, limit=20):
    following = r.smembers(f"user:{user_id}:following")
    
    # 각 팔로잉의 최근 글들 합쳐서 정렬
    keys = [f"user:{fid}:posts" for fid in following]
    
    # ZUNIONSTORE 임시 키 (또는 라이브러리에서 제공)
    r.zunionstore("tmp:feed", keys)
    post_ids = r.zrevrange("tmp:feed", 0, limit - 1)
    r.delete("tmp:feed")
    
    pipe = r.pipeline()
    for pid in post_ids: pipe.hgetall(f"posts:{pid}")
    return pipe.execute()
```

| 장점 | 단점 |
|---|---|
| 게시 비용 일정 (자기 ZSET 1번) | 읽기 비용 = 팔로잉 수 (활성 사용자 비용) |
| 정정 쉬움 | 인기 사용자의 글을 보는 부담 분산 |

---

## 4. Hybrid (실제 SNS 모델)

대부분의 SNS는 두 방식을 혼합.

```
일반 사용자: Fan-out on Write
인플루언서 (팔로워 100만+): Fan-out on Read
```

피드를 만들 때:
1. 자기 피드 ZSET에서 일반 사용자 글 가져오기 (push 방식)
2. 팔로잉 인플루언서들의 ZSET에서 최근 글 합치기 (pull 방식)
3. 두 결과 머지 + 정렬

이렇게 하면 인플루언서의 게시 비용 폭발도, 일반 사용자 읽기의 N개 ZUNION 비용도 피한다.

---

## 5. Stream으로 영속 이벤트 로그

```
stream:user:<user_id>:events   # 모든 활동 이벤트 (글, 좋아요, 팔로우, ...)
```

```
XADD stream:user:1 * type "post" id <post_id>
```

장점:
- 영속, 트림 가능
- Consumer Group으로 후속 처리 (이메일 알림 등)

---

## 6. 알림 (Notifications)

피드와 비슷하지만 작은 규모. user별 ZSET:
```
user:<user_id>:notifications   # ZSET (score=timestamp, member=notif_id)
notif:<notif_id>               # Hash (type, from_user, content)
user:<user_id>:notif:unread    # 미읽은 카운트 (INCR/RESET)
```

읽음 처리:
```python
def mark_read(user_id, notif_id):
    r.hset(f"notif:{notif_id}", "read", "1")
    r.decr(f"user:{user_id}:notif:unread")
```

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| Fan-out on Write 만 사용 | 인플루언서 게시 시 수십만 push → 단일 스레드 점유 |
| 피드 길이 무한 | 메모리 폭증. ZREMRANGEBYRANK으로 1000~5000개 제한 |
| Cluster에서 user별 키 분산 | hashtag로 같은 슬롯 강제 (예: `{u:1}:feed`) |
| 정렬 안정성 | 같은 timestamp 동률 → 멤버 사전순. ID에 timestamp 포함하면 유일성 + 정렬 동시. |
| 본문(`posts:<id>`) 영원 보관 | 별도 archival 정책 |

---

## 8. 직접 해보기

1. 사용자 3명, 팔로우 관계 만들고 Fan-out on Write 구현.
2. 한 명 인플루언서 시뮬레이션 (팔로워 1000) → 게시 시간 측정.
3. 같은 시나리오 Fan-out on Read.
4. Hybrid 구현해서 두 방법의 평균 비용 비교.
5. RedisInsight에서 user feed ZSET 시각화.

---

## 9. 참고 자료

- **[블로그] Twitter — Timelines at scale**
  - URL: <https://www.infoq.com/presentations/Twitter-Timeline-Scalability/>
  - 참고 부분: hybrid push/pull 모델 — §4 근거

- **[블로그] Instagram — Storage at scale**
  - URL: <https://instagram-engineering.com/storing-hundreds-of-millions-of-simple-key-value-pairs-in-redis-1091ae80f74c>
  - 참고 부분: Hash 메모리 효율 — §3 근거 보충

- **[공식 문서] Sorted Sets / Streams**
  - URL: <https://redis.io/docs/latest/develop/data-types/sorted-sets/>, <https://redis.io/docs/latest/develop/data-types/streams/>
  - 참고 부분: ZSET range / Stream — §2, §5 근거
