"""Reference: docs/07-performance/04-pipeline-and-batching.md

Pipeline 으로 RTT 절감 효과 측정. 1000개 SET.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402

N = 1000


def time_it(fn, *a, **kw):
    t0 = time.perf_counter()
    fn(*a, **kw)
    return time.perf_counter() - t0


def naive(r):
    for i in range(N):
        r.set(f"pipe:naive:{i}", i)


def pipeline(r):
    with r.pipeline(transaction=False) as pipe:
        for i in range(N):
            pipe.set(f"pipe:pipe:{i}", i)
        pipe.execute()


def transaction(r):
    with r.pipeline(transaction=True) as pipe:
        for i in range(N):
            pipe.set(f"pipe:tx:{i}", i)
        pipe.execute()


def main():
    r = get_client()
    for prefix in ("pipe:naive:", "pipe:pipe:", "pipe:tx:"):
        for k in r.scan_iter(prefix + "*"):
            r.delete(k)

    with section(f"{N}개 SET — 세 가지 방법 비교"):
        t_naive = time_it(naive, r)
        t_pipe = time_it(pipeline, r)
        t_tx = time_it(transaction, r)

        print(f"  naive (각각 RTT): {t_naive*1000:8.1f} ms ({N/t_naive:>9.0f} ops/sec)")
        print(f"  pipeline (1 RTT): {t_pipe*1000:8.1f} ms ({N/t_pipe:>9.0f} ops/sec)")
        print(f"  transaction     : {t_tx*1000:8.1f} ms ({N/t_tx:>9.0f} ops/sec)")
        print(f"  → pipeline 이 naive 대비 {t_naive/t_pipe:.1f}x 빠름")

    # 정리
    for prefix in ("pipe:naive:", "pipe:pipe:", "pipe:tx:"):
        for k in r.scan_iter(prefix + "*"):
            r.delete(k)


if __name__ == "__main__":
    main()
