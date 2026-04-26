"""Reference: docs/01-data-types/03-hash.md

Hash 객체 + Redis 7.4+ field-level TTL (HEXPIRE).
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


def main():
    r = get_client()

    KEY = "user:1001"

    with section("HSET / HGETALL"):
        r.delete(KEY)
        r.hset(KEY, mapping={
            "name": "Kim",
            "email": "k@example.com",
            "level": 10,
        })
        print(r.hgetall(KEY))

    with section("HINCRBY / HMGET"):
        r.hincrby(KEY, "level", 5)
        print(r.hmget(KEY, ["name", "level"]))

    with section("Field-level TTL (Redis 7.4+) — token 30초 후 자동 삭제"):
        r.hset(KEY, "session_token", "xyz789")
        try:
            r.hexpire(KEY, 5, "session_token")
            ttl = r.httl(KEY, "session_token")
            print("session_token TTL(s):", ttl)
            print("HGETALL 직후:", r.hgetall(KEY))
            time.sleep(6)
            print("6초 후 HGETALL (token만 사라져야 함):", r.hgetall(KEY))
        except redis.exceptions.ResponseError as e:  # noqa: F821
            print("HEXPIRE 미지원 (Redis 7.4 미만 또는 클라이언트 버전):", e)

    with section("HSCAN — 큰 Hash 안전 순회"):
        r.delete("big_hash")
        for i in range(50):
            r.hset("big_hash", f"f{i}", i)
        cursor = 0
        seen = 0
        while True:
            cursor, batch = r.hscan("big_hash", cursor, count=10)
            seen += len(batch)
            if cursor == 0:
                break
        print(f"순회 끝 (seen={seen})")

    with section("Encoding 전환 (listpack → hashtable)"):
        r.delete("h_small")
        r.hset("h_small", mapping={"a": 1, "b": 2})
        print("작은 Hash:", r.object("encoding", "h_small"))
        r.hset("h_small", "big", "x" * 200)
        print("긴 값 추가 후:", r.object("encoding", "h_small"))

    with section("정리"):
        import redis  # for type only
        r.delete(KEY, "big_hash", "h_small")
        print("done.")


if __name__ == "__main__":
    import redis  # noqa: F401
    main()
