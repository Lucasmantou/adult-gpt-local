# -*- coding: utf-8 -*-
"""下载 torch cu130 wheel（复用 download_model 的分块断点续传下载器）。"""
import os
import sys
import threading
import time
import urllib.request
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import download_model as dm

dm.OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wheels")
os.makedirs(dm.OUT_DIR, exist_ok=True)
# pytorch.org 走 mihomo 会被分到隧道节点（当前全都不通），强制直连
dm._probe_proxy_loop = lambda: None
dm._use_proxy = False

WHEEL = "torch-2.14.0%2Bcu130-cp312-cp312-win_amd64.whl"
URL = f"https://download.pytorch.org/whl/cu130/{WHEEL}"
FINAL = os.path.join(dm.OUT_DIR, WHEEL.replace("%2B", "+"))

req = urllib.request.Request(URL, method="HEAD")
size = int(dm.fetch(URL, timeout=60).headers["Content-Length"])
dm.log(f"torch wheel 大小: {size/1e9:.2f} GB")

part = FINAL + ".part"
donef = part + ".done"
if os.path.exists(FINAL) and os.path.getsize(FINAL) == size:
    dm.log("wheel 已存在，跳过")
    sys.exit(0)
if not (os.path.exists(part) and os.path.getsize(part) == size):
    with open(part, "wb") as fp:
        fp.truncate(size)
    if os.path.exists(donef):
        os.remove(donef)

ranges = [(s, min(dm.CHUNK, size - s)) for s in range(0, size, dm.CHUNK)]
try:
    with open(donef) as fp:
        finished = {int(l) for l in fp if l.strip()}
except FileNotFoundError:
    finished = set()
pending = [rg for rg in ranges if rg[0] not in finished]
dm.log(f"共 {len(ranges)} 块, 待下载 {len(pending)} 块")

t0 = time.time()
done_count = {"n": 0}


def work(rg):
    dm.download_chunk(URL, rg[0], rg[1], part)
    with dm._opener_lock:
        with open(donef, "a") as fp:
            fp.write(f"{rg[0]}\n")
    done_count["n"] += 1
    if done_count["n"] % 10 == 0:
        dt = time.time() - t0
        dm.log(f"wheel 进度: {done_count['n']}/{len(pending)} 块, {done_count['n']*dm.CHUNK/dt/1e6:.2f} MB/s")


with cf.ThreadPoolExecutor(dm.WORKERS) as ex:
    list(ex.map(work, pending))

if os.path.exists(donef):
    os.remove(donef)
os.replace(part, FINAL)
dm.log(f"wheel 下载完成: {FINAL}")
