# -*- coding: utf-8 -*-
"""
无限制图片工人脚本（部署于卢卡斯工作站 E:\\Qwen_image2.1\\unlimited_worker.py）

职责：轮询 Z-Design 服务器取任务 → 调本机 Qwen-Image-2.1 server.py(127.0.0.1:7860) 生成 → 回传成品。
方向：始终由本机向外发起 HTTPS（无需公网IP/端口映射/隧道）。
配置：同目录 unlimited_worker_config.json（z_base/token/variant 等），由部署脚本生成。
常驻：计划任务 UnlimitedImageWorker（开机自启，SYSTEM 会话，参考 AdultGPT_AutoStart 先例）。

关键约定（2026-10-13 与老板确认）：
- variant 固定 "uc"（无审核版；std 官方版在本机加载从未成功）
- resolution 固定 "half"（半分辨率档；全分辨率显存不足 OOM）
- Z 端任务永不因 28 分钟超时被判失败（有独立 24 小时兜底）
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback

import requests

# Windows SYSTEM 会话默认 GBK 编码，日志含 ½ 等字符会 UnicodeEncodeError 崩溃（2026-10-13 实测踩坑）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "unlimited_worker_config.json")
LOG_PATH = os.path.join(ROOT, "unlimited_worker.log")

DEFAULTS = {
    "z_base": "https://8.163.28.192",
    "verify_tls": False,
    "token": "",
    "local_api": "http://127.0.0.1:7860",
    "variant": "uc",
    "resolution": "half",
    "poll_seconds": 10,
    "heartbeat_seconds": 30,
    "auto_start_server": True,
    "server_startup_wait": 600,
    "job_timeout": 1800,
}


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg)
    try:
        print(line, flush=True)
    except Exception:
        pass  # 双保险：stdout 编码异常绝不拖垮工人主循环
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (ValueError, OSError) as e:
            log(f"配置文件损坏，使用默认配置: {e}")
    return cfg


CFG = load_config()
Z = CFG["z_base"].rstrip("/")
TOKEN = CFG["token"]
# 家用宽带到 Z 域名的 TLS(SNI) 会被重置，走 IP + 关闭证书校验（自家服务器间通讯）
VERIFY = bool(CFG.get("verify_tls", True))


def z_headers():
    return {"X-Worker-Token": TOKEN}


def gpu_stats():
    """nvidia-smi 读显存（MB）。失败返回 None"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        total, used, free = out.stdout.strip().splitlines()[0].split(",")
        return int(total.strip()), int(used.strip()), int(free.strip())
    except Exception:
        return None


def local_status():
    try:
        r = requests.get(CFG["local_api"] + "/api/status", timeout=5)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return None


def heartbeat():
    st = local_status()
    gpu = gpu_stats()
    payload = {
        "model_loaded": bool(st and st.get("loaded")),
        "variant": (st or {}).get("variant") or CFG["variant"],
        "note": "本地服务运行中" if st else "本地服务未启动",
    }
    if gpu:
        payload["gpu_total_mb"], payload["gpu_used_mb"], payload["gpu_free_mb"] = gpu
    try:
        requests.post(Z + "/worker/api/heartbeat", json=payload, headers=z_headers(), timeout=15, verify=VERIFY)
    except requests.exceptions.RequestException as e:
        log(f"心跳上报失败: {e}")


def ensure_local_server():
    """本地 server.py 没开且允许自启时拉起它，等 /api/status 就绪（模型加载需数分钟）"""
    if local_status():
        return True
    if not CFG["auto_start_server"]:
        return False
    log("本地生成服务未运行，尝试自动拉起 server.py …")
    venv_py = os.path.join(ROOT, "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        log(f"找不到 venv python: {venv_py}")
        return False
    subprocess.Popen(
        [venv_py, os.path.join(ROOT, "server.py")],
        cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    deadline = time.time() + CFG["server_startup_wait"]
    while time.time() < deadline:
        time.sleep(10)
        if local_status():
            log("本地生成服务已就绪")
            return True
        log("等待本地生成服务启动（模型加载中）…")
    log("本地生成服务启动超时")
    return False


def process_job(job):
    job_id = job["id"]
    log(f"取到任务 #{job_id}：ratio={job.get('ratio')} 参考图{len(job.get('refs') or [])}张")
    if not ensure_local_server():
        raise RuntimeError("本地生成服务不可用（未运行且自动拉起失败）")

    tmpdir = tempfile.mkdtemp(prefix="zw_")
    try:
        files = []
        for i, ref_url in enumerate(job.get("refs") or []):
            url = ref_url if ref_url.startswith("http") else Z + ref_url
            r = requests.get(url, timeout=60, verify=VERIFY)
            r.raise_for_status()
            p = os.path.join(tmpdir, f"ref_{i}{os.path.splitext(url.split('?')[0])[1] or '.png'}")
            with open(p, "wb") as f:
                f.write(r.content)
            files.append(p)

        form = {
            "prompt": job["prompt"],
            "ratio": job.get("ratio") or "auto",
            "resolution": CFG["resolution"],
            "variant": CFG["variant"],
            "num": "1",
        }
        file_handles = [("images", (os.path.basename(p), open(p, "rb"), "application/octet-stream")) for p in files]
        try:
            r = requests.post(CFG["local_api"] + "/api/generate", data=form, files=file_handles, timeout=30)
        finally:
            for _, h in file_handles:
                try:
                    h[1].close()
                except Exception:
                    pass
        if r.status_code == 409:
            # 本地正被别的任务占用：把任务放回 Z 端稍后再取（直接报临时错误）
            raise TemporaryBusy("本地生成服务正忙")
        r.raise_for_status()
        local_job = r.json()
        jid = local_job["id"]

        deadline = time.time() + CFG["job_timeout"]
        while time.time() < deadline:
            time.sleep(3)
            jr = requests.get(f"{CFG['local_api']}/api/jobs", timeout=10).json()
            # /api/jobs 返回任务列表或字典，按 id 找
            target = None
            if isinstance(jr, dict):
                target = jr.get(jid)
                if target is None:
                    for v in (jr.get("jobs") or []):
                        if isinstance(v, dict) and v.get("id") == jid:
                            target = v
                            break
            elif isinstance(jr, list):
                for v in jr:
                    if isinstance(v, dict) and v.get("id") == jid:
                        target = v
                        break
            if not target:
                continue
            status = target.get("status")
            if status == "done":
                images = target.get("images") or []
                if not images:
                    raise RuntimeError("本地任务完成但没有图片")
                img_url = images[0]
                if not img_url.startswith("http"):
                    img_url = CFG["local_api"] + img_url
                ir = requests.get(img_url, timeout=120)
                ir.raise_for_status()
                out_path = os.path.join(tmpdir, "result" + os.path.splitext(img_url.split("?")[0])[1] or ".png")
                with open(out_path, "wb") as f:
                    f.write(ir.content)
                with open(out_path, "rb") as f:
                    rr = requests.post(
                        f"{Z}/worker/api/unlimited-image/{job_id}/result",
                        params={"token": TOKEN},
                        files={"file": ("result.png", f, "image/png")},
                        timeout=120, verify=VERIFY)
                if rr.status_code != 200:
                    raise RuntimeError(f"回传失败 HTTP{rr.status_code}: {rr.text[:200]}")
                log(f"任务 #{job_id} 完成，已回传 {len(ir.content) // 1024}KB")
                return
            if status == "error":
                raise RuntimeError("本地生成失败: " + str(target.get("error") or "")[:300])
            # queued/running → 继续等
        raise RuntimeError("本地生成超时")

    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TemporaryBusy(Exception):
    """本地正忙，任务应放回 Z 端队列稍后重试"""


def release_job(job_id):
    """把任务从 processing 放回 pending 重新排队（本地临时正忙场景）"""
    try:
        requests.post(f"{Z}/worker/api/unlimited-image/{job_id}/release",
                      params={"token": TOKEN}, timeout=20, verify=VERIFY)
        log(f"任务 #{job_id} 已放回队列（本地正忙）")
    except requests.exceptions.RequestException as e:
        log(f"任务 #{job_id} 放回失败(将等Z端24小时兜底): {e}")


BUSY_COUNT = {"n": 0}


def main():
    if not TOKEN:
        log("未配置 token（unlimited_worker_config.json），退出。请到 Z 管理后台-系统设置-本地模型 复制密钥")
        sys.exit(1)
    log(f"工人启动：Z={Z} 本地={CFG['local_api']} variant={CFG['variant']} resolution={CFG['resolution']}")
    last_hb = 0
    while True:
        now = time.time()
        if now - last_hb >= CFG["heartbeat_seconds"]:
            try:
                heartbeat()
            except Exception:
                pass
            last_hb = now
        try:
            r = requests.post(Z + "/worker/api/unlimited-image/claim", params={"token": TOKEN}, timeout=20, verify=VERIFY)
            if r.status_code == 401:
                log("Z 端鉴权失败：token 不匹配，请到管理后台系统设置重新复制密钥")
                time.sleep(60)
                continue
            r.raise_for_status()
            job = r.json().get("job")
        except requests.exceptions.RequestException as e:
            log(f"取件失败（网络）: {e}")
            time.sleep(CFG["poll_seconds"] * 3)
            continue

        if not job:
            time.sleep(CFG["poll_seconds"])
            continue

        try:
            process_job(job)
            BUSY_COUNT["n"] = 0
        except TemporaryBusy as e:
            BUSY_COUNT["n"] += 1
            log(f"本地正忙({BUSY_COUNT['n']}次): {e}")
            release_job(job["id"])
            if BUSY_COUNT["n"] >= 20:
                BUSY_COUNT["n"] = 0
            time.sleep(30)
        except Exception as e:
            traceback.print_exc()
            log(f"任务 #{job.get('id')} 失败: {e}")
            try:
                requests.post(f"{Z}/worker/api/unlimited-image/{job['id']}/fail",
                              json={"reason": f"{type(e).__name__}: {e}"}, headers=z_headers(), timeout=20, verify=VERIFY)
            except Exception:
                pass


if __name__ == "__main__":
    main()
