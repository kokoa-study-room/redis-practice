"""Reference: docs/01-data-types/01-string.md

String 자료형의 SET/GET, 만료 옵션, INCR, APPEND, MSET/MGET, embstr/raw 인코딩 차이.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


def main():
    r = get_client()

    with section("SET / GET / EX / NX"):
        r.set("greeting", "Hello", ex=10)
        print("greeting =", r.get("greeting"), "TTL=", r.ttl("greeting"))

        first = r.set("lock:demo", "client-1", nx=True, ex=30)
        second = r.set("lock:demo", "client-2", nx=True, ex=30)
        print("first lock acquire ->", first)
        print("second lock acquire (이미 있음) ->", second)

    with section("INCR / DECR / INCRBYFLOAT"):
        r.set("visits", 0)
        r.incr("visits")
        r.incrby("visits", 10)
        r.incrbyfloat("visits", 0.5)
        print("visits =", r.get("visits"))

    with section("APPEND / STRLEN / GETRANGE"):
        r.set("msg", "hello")
        r.append("msg", " world")
        print("msg =", r.get("msg"), "len=", r.strlen("msg"))
        print("msg[0:4] =", r.getrange("msg", 0, 4))

    with section("MSET / MGET"):
        r.mset({"a": 1, "b": 2, "c": 3})
        print(r.mget(["a", "b", "c", "missing"]))

    with section("Encoding 전환 (int / embstr / raw)"):
        for k, v in [("k_int", 42), ("k_emb", "short"), ("k_raw", "x" * 100)]:
            r.set(k, v)
            print(f"{k} ({v!r:>20}) -> {r.object('encoding', k)}")

    with section("정리"):
        r.delete("greeting", "lock:demo", "visits", "msg",
                 "a", "b", "c", "k_int", "k_emb", "k_raw")
        print("done.")


if __name__ == "__main__":
    main()
