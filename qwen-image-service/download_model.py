# -*- coding: utf-8 -*-
"""Qwen-Image-2.1 模型多线程断点续传下载器。

- 从 ModelScope API 获取文件清单，24 线程分块下载，支持断点续传（.part 文件）。
- 自动跳过 assets/（官方示例图，非必需）。
- 每 30 秒探测 127.0.0.1:7890 代理：代理一旦可用自动切换走代理下载，掉线自动回直连。

用法: python download_model.py
"""
import os
import sys
import time
import socket
import threading
import urllib.request
import concurrent.futures as cf

REPO = "Qwen/Qwen-Image-2.1"
BASE = f"https://www.modelscope.cn/models/{REPO}/resolve/master/"
API = f"https://www.modelscope.cn/api/v1/models/{REPO}/repo/files?Recursive=true"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "Qwen-Image-2.1")
CHUNK = 32 * 1024 * 1024          # 每块 32MB
WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "12"))  # 并发线程数（线路差时过多反而互相挤占）
PROXY_ADDR = ("127.0.0.1", 7890)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download.log")

_opener_lock = threading.Lock()
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_use_proxy = False


def _probe_proxy_loop():
    global _opener, _use_proxy
    while True:
        alive = False
        try:
            socket.create_connection(PROXY_ADDR, timeout=2).close()
            alive = True
        except OSError:
            alive = False
        if alive != _use_proxy:
            with _opener_lock:
                handler = urllib.request.ProxyHandler(
                    {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"} if alive else {})
                _opener = urllib.request.build_opener(handler)
                _use_proxy = alive
            log(f"*** 代理{'已上线，切换为代理下载' if alive else '掉线，回退直连'} ***")
        time.sleep(30)


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def fetch(url, headers=None, timeout=90):
    req = urllib.request.Request(url, headers=headers or {})
    with _opener_lock:
        opener = _opener
    return opener.open(req, timeout=timeout)


def list_files():
    import json
    data = json.load(fetch(API, timeout=30))
    files = []
    for f in data["Data"]["Files"]:
        if f["Type"] != "blob" or f["Size"] == 0:
            continue
        if f["Path"].startswith("assets/"):
            continue
        files.append((f["Path"], f["Size"]))
    return files


def download_chunk(url, start, length, part_path, tries=10):
    for attempt in range(tries):
        try:
            r = fetch(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
            buf = b""
            while len(buf) < length:
                chunk = r.read(min(1 << 20, length - len(buf)))
                if not chunk:
                    break
                buf += chunk
            r.close()
            if len(buf) != length:
                raise IOError(f"short read {len(buf)}/{length}")
            with open(part_path, "r+b") as fp:
                fp.seek(start)
                fp.write(buf)
            return len(buf)
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(min(2 ** attempt, 30))


def download_file(path, size):
    url = BASE + path
    final = os.path.join(OUT_DIR, *path.split("/"))
    part = final + ".part"
    os.makedirs(os.path.dirname(final), exist_ok=True)

    if os.path.exists(final) and os.path.getsize(final) == size:
        return 0, "skip"

    if not (os.path.exists(part) and os.path.getsize(part) == size):
        with open(part, "wb") as fp:            # 预分配
            fp.truncate(size)
        if os.path.exists(part + ".done"):
            os.remove(part + ".done")

    if size <= CHUNK:                            # 小文件单请求
        download_chunk(url, 0, size, part)
    else:
        ranges = [(s, min(CHUNK, size - s)) for s in range(0, size, CHUNK)]
        done_file = part + ".done"
        try:
            with open(done_file) as fp:
                finished = {int(line) for line in fp if line.strip()}
        except FileNotFoundError:
            finished = set()
        pending = [rg for rg in ranges if rg[0] not in finished]
        t0 = time.time()

        def work(rg):
            download_chunk(url, rg[0], rg[1], part)
            with _opener_lock:                    # 借锁串行追加记录
                with open(done_file, "a") as fp:
                    fp.write(f"{rg[0]}\n")

        if len(pending) < len(ranges):
            log(f"    断点续传 {path}: 剩余 {len(pending)}/{len(ranges)} 块")
        with cf.ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(work, pending))
        dt = time.time() - t0
        speed = size / dt / 1e6 if dt > 0 else 0
        log(f"    {path}: {size/1e9:.2f} GB 用时 {dt/60:.1f} 分钟, {speed:.2f} MB/s")

    done_marker = part + ".done"
    if os.path.exists(done_marker):
        os.remove(done_marker)

    if os.path.getsize(part) != size:
        raise IOError(f"size mismatch for {path}")
    os.replace(part, final)
    return size, "ok"


def main():
    if os.environ.get("DOWNLOAD_NO_PROXY") != "1":
        threading.Thread(target=_probe_proxy_loop, daemon=True).start()
    else:
        log("已按要求强制直连（不探测代理）")
    files = list_files()
    total_gb = sum(s for _, s in files) / 1e9
    log(f"共 {len(files)} 个文件, {total_gb:.1f} GB, 输出目录: {OUT_DIR}")

    done_bytes = {"n": 0}
    t_start = time.time()

    def report_progress():
        while True:
            time.sleep(300)
            got = done_bytes["n"] / 1e9
            rate = done_bytes["n"] / max(time.time() - t_start, 1) / 1e6
            remain = (total_gb * 1e9 - done_bytes["n"])
            eta_min = remain / max(done_bytes["n"], 1) * (time.time() - t_start) / 60
            log(f"[进度] 已完成 {got:.2f}/{total_gb:.1f} GB, 平均 {rate:.2f} MB/s, 预计还需 ~{eta_min:.0f} 分钟")

    threading.Thread(target=report_progress, daemon=True).start()

    for i, (path, size) in enumerate(files):
        for attempt in range(5):
            try:
                download_file(path, size)
                done_bytes["n"] += size
                log(f"({i + 1}/{len(files)}) 完成 {path} ({size/1e9:.2f} GB)")
                break
            except Exception as e:
                log(f"!! {path} 第{attempt + 1}次失败: {e}")
                time.sleep(5)
        else:
            log(f"!!! 放弃 {path}")
            sys.exit(1)
    log("全部下载完成 ✔")


if __name__ == "__main__":
    main()
