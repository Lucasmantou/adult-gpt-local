# -*- coding: utf-8 -*-
"""Heretic 文本编码器并行下载器（8 线程分块 + 断点续传 + 尺寸校验）"""
import os, sys, time, urllib.request, threading

BASE = "https://hf-mirror.com/pottokao/Qwen-Image-2.1-Text-Encoder-Heretic/resolve/main/"
OUT = r"E:\Qwen_image2.1\models\heretic-te"
FILES = [
    "model-00001-of-00004.safetensors",
    "model-00002-of-00004.safetensors",
    "model-00003-of-00004.safetensors",
    "model-00004-of-00004.safetensors",
    "model.safetensors.index.json",
    "config.json",
    "generation_config.json",
    "chat_template.jinja",
    "tokenizer.json",
    "tokenizer_config.json",
    "processor_config.json",
]
NTHREADS = 8

def head_len(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])

def fetch_range(url, start, end, path, log_prefix):
    """下载 [start, end] 到 path（已存在则续传）"""
    have = os.path.getsize(path) if os.path.exists(path) else 0
    want = end - start + 1
    while have < want:
        req = urllib.request.Request(url, headers={"Range": f"bytes={start+have}-{end}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "ab") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk: break
                    f.write(chunk)
                    have += len(chunk)
        except Exception as e:
            print(f"  {log_prefix} 重试({e.__class__.__name__})", flush=True)
            time.sleep(3)
            have = os.path.getsize(path) if os.path.exists(path) else 0

def concat(parts, out):
    with open(out, "wb") as w:
        for p in parts:
            with open(p, "rb") as r:
                while True:
                    chunk = r.read(1 << 22)
                    if not chunk: break
                    w.write(chunk)
    for p in parts: os.remove(p)

def download(fn):
    url = BASE + fn
    out = os.path.join(OUT, fn)
    if os.path.exists(out):
        print(f"[skip] {fn}", flush=True); return True
    total = head_len(url)
    if total < 50 << 20:  # 小文件直接下
        urllib.request.urlretrieve(url, out + ".tmp")
        os.replace(out + ".tmp", out)
        print(f"[ok] {fn} ({total}B)", flush=True); return True
    bounds = [total * i // NTHREADS for i in range(NTHREADS + 1)]
    parts, threads = [], []
    for i in range(NTHREADS):
        p = f"{out}.part{i}"
        parts.append(p)
        t = threading.Thread(target=fetch_range, args=(url, bounds[i], bounds[i+1]-1, p, f"{fn}#{i}"))
        t.start(); threads.append(t)
    for t in threads: t.join()
    if sum(os.path.getsize(p) for p in parts) != total:
        print(f"[FAIL] {fn} 尺寸不符", flush=True); return False
    concat(parts, out)
    print(f"[ok] {fn} ({total/2**30:.2f}GB)", flush=True)
    return True

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    fails = [f for f in FILES if not download(f)]
    print(f"=== {'全部完成' if not fails else '失败: ' + str(fails)}，耗时 {time.time()-t0:.0f}s ===", flush=True)
    sys.exit(1 if fails else 0)
