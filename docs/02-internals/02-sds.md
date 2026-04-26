# 02. SDS — Simple Dynamic String

> **학습 목표**: SDS가 C의 일반 문자열보다 무엇이 좋은지(O(1) 길이, 바이너리 안전, 확장 비용 절감), 헤더 종류 5가지가 왜 있는지 설명할 수 있다.
> **예상 소요**: 20분

---

## 1. 왜 C의 char* 가 아닌가?

C 표준 문자열의 단점:

| 문제 | 결과 |
|---|---|
| 길이 = strlen → O(N) | `STRLEN` 한 번에 N 비례 비용 |
| `\0` 종료 → 바이너리 안전 X | JPEG, 임베딩 같은 바이너리 저장 못 함 |
| append 시 매번 alloc | 자주 자라는 문자열 비효율 |
| 버퍼 오버플로우 | 보안 사고 |

Redis는 이 모두를 해결하려고 **SDS** 를 만들었다.

> 출처: <https://github.com/redis/redis/blob/8.6/src/sds.h>
> 참고 부분: 파일 상단 주석 — SDS 설계 의도

---

## 2. 구조 (8.6 기준)

```c
struct sdshdr8 {
    uint8_t  len;       // 현재 길이
    uint8_t  alloc;     // 실제 할당 크기 (헤더 + 문자 + '\0' 제외)
    unsigned char flags;// 헤더 종류 (3 bit)
    char buf[];         // 실제 문자열 (FAM, flexible array member)
};
```

핵심:

- **len**: 길이를 헤더에 직접 저장 → `STRLEN` 이 O(1)
- **alloc**: 사전 할당된 크기 → append 시 빈 공간이 있으면 alloc 안 함
- **buf**: 실제 데이터. 끝에 `\0` 도 두지만, 길이는 len으로 안다 → 바이너리 안전

---

## 3. 헤더 종류 5가지

| 헤더 | len 표현 | 적합 |
|---|---|---|
| `sdshdr5` | 5비트 | 매우 짧은 문자열 |
| `sdshdr8` | 8비트 (255자) | 짧은 |
| `sdshdr16` | 16비트 | 보통 |
| `sdshdr32` | 32비트 | 큰 |
| `sdshdr64` | 64비트 | 매우 큰 |

**왜 5가지나?** 작은 문자열에 큰 헤더를 쓰면 메모리가 아깝다.
8자 문자열에 64-bit len 헤더 = 헤더가 본문보다 큼.

> 출처: <https://github.com/redis/redis/blob/8.6/src/sds.h> 헤더 정의 부분

---

## 4. embstr vs raw 다시 보기

```
SET k "hi"
OBJECT ENCODING k       # "embstr"
```

- `embstr`: redisObject 와 sds가 **하나의 메모리 블록** (단일 alloc).
  - 캐시 친화적 (CPU 캐시 라인 한 번에 둘 다 들어옴).
  - 단, **불변** — APPEND 등으로 길이가 변하면 raw로 변환.

```
SET k "$(python -c 'print("a"*50)')"
OBJECT ENCODING k       # "raw" — 별도 alloc
```

`raw`: redisObject 와 sds가 별도 alloc.

embstr → raw 전환 임계: 44 byte (`OBJ_ENCODING_EMBSTR_SIZE_LIMIT`).

---

## 5. 사전 할당 (Preallocation) 전략

```c
// sdsMakeRoomFor (의역)
if (avail >= addlen) return;          // 빈 공간 충분
new_len = len + addlen;
if (new_len < SDS_MAX_PREALLOC) {     // 1MB 미만
    new_len *= 2;                     // 두 배 alloc
} else {
    new_len += SDS_MAX_PREALLOC;      // 1MB 추가
}
```

결과: APPEND를 반복해도 **amortized O(1)**.

> 출처: <https://github.com/redis/redis/blob/8.6/src/sds.c> `sdsMakeRoomFor` 함수

---

## 6. 바이너리 안전 예제

```python
import redis
r = redis.Redis()  # decode_responses=False

with open("photo.jpg", "rb") as f:
    r.set("photo:1", f.read())

print(r.strlen("photo:1"))   # 정확한 byte 수
data = r.get("photo:1")
with open("out.jpg", "wb") as f:
    f.write(data)            # 같은 파일이 복원됨
```

C string이라면 JPEG 안의 `\0` 바이트에서 끊겼을 것. SDS는 안전.

---

## 7. 흔한 오해

| 오해 | 실제 |
|---|---|
| "Redis String 은 그냥 char*" | SDS, 헤더 5종 |
| "embstr가 raw보다 항상 빠름" | **읽기는 보통 그렇다.** APPEND 등 변형이 잦으면 raw가 나음 |
| "STRLEN 은 O(N)" | O(1) (헤더 len) |
| "\0 가 들어가면 못 저장" | **저장 가능**, 바이너리 안전 |

---

## 8. 직접 해보기

1. `SET k "hello"` → `STRLEN k` → 5가 즉시 반환됨을 인지 (속도 측정 의미 X, 하지만 O(1)).
2. `SET k "abc"; APPEND k "def"` 100회 반복 → 마지막 `STRLEN k`.
3. 50자 String SET → encoding이 raw인지 확인.
4. `r.set("img", open("any.jpg","rb").read())` 후 다시 GET → byte-for-byte 일치하는지.

---

## 9. 참고 자료

- **[GitHub] redis/redis — src/sds.h (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/sds.h>
  - 참고 부분: SDS 헤더 5종 정의 + `OBJ_ENCODING_EMBSTR_SIZE_LIMIT` — §2, §3, §4 근거

- **[GitHub] redis/redis — src/sds.c (8.6)** `sdsMakeRoomFor`
  - URL: <https://github.com/redis/redis/blob/8.6/src/sds.c>
  - 참고 부분: 두 배 사전할당 로직 — §5 근거

- **[블로그] Redis SDS internals — antirez 옛 글 (Salvatore Sanfilippo)**
  - URL: <http://antirez.com/news/95>
  - 참고 부분: SDS 도입 동기 — §1 근거 보충

> 옛 글이지만 SDS의 본질은 8.x에서도 같다. 다만 헤더 종류가 5가지로 늘어난 것은 SDS 2.0 (Redis 3.2)부터 반영된 변화.
