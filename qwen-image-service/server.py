# -*- coding: utf-8 -*-
"""Qwen-Image-2.1 本地 Web GUI 服务。运行后访问 http://127.0.0.1:7860"""
import gc
import json
import os
import re
import sys
import time
import threading
import traceback
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "diffusers-main", "src"))

# 若被用系统 Python 启动（例如直接双击 server.py），自动切换到项目虚拟环境
_VENV_PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
if os.path.exists(_VENV_PY) and os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(_VENV_PY):
    import subprocess
    print("检测到未使用虚拟环境启动，正在切换到 venv 环境 ...", flush=True)
    subprocess.Popen([_VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit(0)

from flask import Flask, jsonify, request, send_from_directory
import torch
from PIL import Image
from diffusers import QwenImage21Pipeline

MODEL_DIR = os.environ.get("QWEN_IMAGE_MODEL", os.path.join(ROOT, "models", "Qwen-Image-2.1"))
OUT_DIR = os.path.join(ROOT, "outputs")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 模型版本：std=官方原版；uc=社区无审核版（仅替换 abliterated 文本编码器，其余组件链接官方目录）
MODEL_VARIANTS = {
    "std": {"dir": MODEL_DIR, "label": "官方版"},
    "uc": {"dir": os.path.join(ROOT, "models", "Qwen-Image-2.1-UC"), "label": "无审核版"},
}
VARIANT_FILE = os.path.join(ROOT, "qwen_variant.json")

def _variant_ready(v):
    return os.path.isdir(os.path.join(MODEL_VARIANTS[v]["dir"], "transformer"))

def _load_default_variant():
    try:
        v = json.load(open(VARIANT_FILE, encoding="utf-8")).get("variant")
        if v in MODEL_VARIANTS and _variant_ready(v):
            return v
    except Exception:
        pass
    return "std"

DEFAULT_VARIANT = _load_default_variant()

# 风格 LoRA：2026-10-08 实测社区写实 LoRA 均非 2.1 底模（2512 尺寸不匹配 / Edit 模块缺失），暂无可用项。
# 机制保留：将来出现 2.1 原生 LoRA 时在 LORAS 注册并放文件到 models/loras/ 即可。
LORA_DIR = os.path.join(ROOT, "models", "loras")
LORAS = {
    "none": {"label": "无"},
}

def _lora_path(lora_id):
    info = LORAS.get(lora_id) or {}
    f = info.get("file")
    if not f:
        return None
    p = os.path.join(LORA_DIR, f)
    return p if os.path.exists(p) else None

ASPECT_RATIOS = {
    "auto": None,
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}
RGBA_PROMPT_PREFIX = "This is an RGBA image with transparency. "
RGBA_PROMPT_SUFFIX = " The image has alpha channel and the background is transparent."

# 全速模式需要权重 ~33GB + 激活显存，预留 41GB 空闲才允许
FULL_MODE_MIN_FREE_GB = 41
# 把文本编码器（~17GB）编码后卸载到内存所需的最小空闲内存
TEXT_ENCODER_OFFLOAD_MIN_RAM_GB = 18


def free_ram_gb():
    """当前可用物理内存（GB）。"""
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = _MS()
        st.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullAvailPhys / 2**30
    except Exception:
        return 0.0

app = Flask(__name__, static_folder=None)
jobs = {}
jobs_lock = threading.Lock()
gen_lock = threading.Lock()


class PipelineManager:
    """按需加载/卸载 pipeline，并根据空闲显存选择全速或省显存模式。"""

    def __init__(self):
        self.pipe = None
        self.mode = None  # 'full' | 'offload'
        self.variant = None  # 当前已加载的模型版本 'std' | 'uc'
        self.lora = "none"  # 当前已挂载的 LoRA id
        self.te_offload = False  # 文本编码器是否已启用“编码后卸载到内存”
        self.lock = threading.Lock()

    def _ensure_lora_locked(self, lora, strength=None):
        """在已加载的 pipe 上挂/换/卸 LoRA（不重载主模型）；强度用 set_adapters 设置"""
        if self.pipe is None:
            return
        req = lora if (lora in LORAS and _lora_path(lora)) else "none"
        if req == "none" and self.lora == "none":
            return
        if req != "none" and req == self.lora:
            # 同一 LoRA 只调强度（不重复挂载）
            try:
                self.pipe.set_adapters(["style"], adapter_weights=[float(strength or LORAS[req].get("strength") or 0.8)])
            except Exception:
                pass
            return
        if self.lora != "none":
            try:
                self.pipe.unload_lora_weights()
            except Exception as e:
                print(f"[lora] 卸载旧 LoRA 失败(忽略): {e}", flush=True)
            self.lora = "none"
        if req != "none":
            try:
                self.pipe.load_lora_weights(_lora_path(req), adapter_name="style")
                self.pipe.set_adapters(["style"], adapter_weights=[float(strength or LORAS[req].get("strength") or 0.8)])
                self.lora = req
                print(f"[lora] loaded: {req} ({LORAS[req]['label']})", flush=True)
            except Exception as e:
                print(f"[lora] 加载失败，跳过: {e}", flush=True)

    @staticmethod
    def _patch_text_encoder_offload(pipe):
        """让文本编码器只在编码提示词时上显卡，编码完立刻回内存，省下约 17GB 显存。
        这样 2K 分辨率（需要 ~13GB 激活显存）才能跑得动。"""
        original = pipe.encode_prompt

        def encode_on_gpu_then_offload(*args, **kwargs):
            te = pipe.text_encoder
            te.to("cuda")
            try:
                return original(*args, **kwargs)
            finally:
                te.to("cpu")
                gc.collect()
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        pipe.encode_prompt = encode_on_gpu_then_offload
        print("[model] 已启用文本编码器动态卸载（编码后释放约 17GB 显存，支持 2K 出图）", flush=True)

    @staticmethod
    def free_gb():
        try:
            free, total = torch.cuda.mem_get_info()
            return free / 2**30, total / 2**30
        except Exception:
            return None, None

    def load(self, mode="auto", variant=None, lora="none", lora_strength=None):
        global DEFAULT_VARIANT
        variant = variant if variant in MODEL_VARIANTS else DEFAULT_VARIANT
        if not _variant_ready(variant):
            variant = "std"
        with self.lock:
            # 换版本：先卸载再按新目录重载
            if self.pipe is not None and variant != self.variant:
                self._unload_locked()
            # 已加载时只切 LoRA，不重载主模型
            if self.pipe is not None:
                self._ensure_lora_locked(lora, lora_strength)
            # 已经加载就复用，不因空闲显存变化在 full/offload 之间来回切换
            if self.pipe is not None:
                if mode == "auto" or mode == self.mode:
                    # 内存条件刚满足时，无需重载即可补上 2K 优化
                    if (self.mode == "full" and not self.te_offload
                            and free_ram_gb() >= TEXT_ENCODER_OFFLOAD_MIN_RAM_GB):
                        self._patch_text_encoder_offload(self.pipe)
                        self.pipe.text_encoder.to("cpu")
                        gc.collect()
                        try:
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                        self.te_offload = True
                    return self.mode
                self._unload_locked()  # 仅当用户显式切换模式时才重载
            if mode == "auto":
                free, _ = self.free_gb()
                mode = "full" if (free or 0) >= FULL_MODE_MIN_FREE_GB else "offload"
            t0 = time.time()
            pipe = QwenImage21Pipeline.from_pretrained(MODEL_VARIANTS[variant]["dir"], dtype=torch.bfloat16)
            if mode == "offload":
                pipe.enable_model_cpu_offload()
                self.te_offload = False
            else:
                pipe.to("cuda")
                ram = free_ram_gb()
                if ram >= TEXT_ENCODER_OFFLOAD_MIN_RAM_GB:
                    self._patch_text_encoder_offload(pipe)
                    self.te_offload = True
                else:
                    self.te_offload = False
                    print(f"[model] 空闲内存仅 {ram:.1f}GB（需 ≥{TEXT_ENCODER_OFFLOAD_MIN_RAM_GB}GB 才能启用 2K 优化），"
                          f"文本编码器将常驻显存；2K 分辨率可能显存不足，建议用「预览½」或关闭本地大模型后重启服务",
                          flush=True)
            self.pipe, self.mode, self.variant = pipe, mode, variant
            self._ensure_lora_locked(lora, lora_strength)
            print(f"[model] loaded variant={variant} mode={mode} in {time.time()-t0:.1f}s", flush=True)
            return mode

    def unload(self):
        with self.lock:
            self._unload_locked()

    def _unload_locked(self):
        if self.pipe is not None:
            del self.pipe
            self.pipe = None
            self.mode = None
            self.variant = None
            self.lora = "none"
            self.te_offload = False
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            print("[model] unloaded", flush=True)


mgr = PipelineManager()


def run_job(job):
    t0 = time.time()
    pipe = None
    try:
        p = job["params"]
        lora_id = p.get("lora") if (p.get("lora") in LORAS and _lora_path(p.get("lora"))) else "none"
        lora_info = LORAS[lora_id]
        mode = mgr.load(p.get("mode", "auto"), p.get("variant"), lora_id, p.get("lora_strength"))
        job["mode_used"] = mode
        pipe = mgr.pipe

        prompt = p["prompt"]
        cond = [Image.open(x).convert("RGB") for x in p.get("image_paths", [])] or None
        # 修图 LoRA：有参考图时改用它训练用的固定提示词与推荐参数
        override = lora_info.get("kind") == "edit" and cond and lora_info.get("prompt")
        if override:
            prompt = lora_info["prompt"]
        lora_strength = float(p.get("lora_strength") or lora_info.get("strength") or 0.8)
        if p.get("rgba"):
            prompt = RGBA_PROMPT_PREFIX + prompt + RGBA_PROMPT_SUFFIX

        # 分辨率档位：standard=官方推荐边长，half=半分辨率快速预览
        scale = 0.5 if p.get("resolution") == "half" else 1.0

        def snap16(v):
            return max(256, int(v * scale) // 16 * 16)

        w, h = p.get("width"), p.get("height")
        if not (w and h):
            ar = ASPECT_RATIOS.get(p.get("ratio") or "auto")
            if ar:
                w, h = snap16(ar[0]), snap16(ar[1])
            elif cond:
                w = h = None  # 编辑模式跟随参考图宽高比
            else:
                w = h = 1024 if scale == 0.5 else 2048

        seed = p.get("seed")
        gen = torch.Generator("cuda").manual_seed(seed) if seed is not None else None
        steps = int(p.get("steps") or 40)
        if override and lora_info.get("steps"):
            steps = int(lora_info["steps"])
        total_n = max(1, int(p.get("num") or 1))

        job["status"] = "running"
        stamp = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        names, size_str = [], None

        # 多张时逐张生成：避免批量让显存峰值成倍上涨，每张结束立即释放中间缓存
        for idx in range(total_n):
            def cb(_pipe, step, _ts, kw, _idx=idx):
                job["progress"] = int(((_idx + (step + 1) / steps) / total_n) * 100)
                job["elapsed"] = round(time.time() - t0, 1)
                return kw

            res = pipe(
                prompt=prompt,
                image=cond,
                width=w,
                height=h,
                num_inference_steps=steps,
                true_cfg_scale=float(lora_info.get("cfg") if override and lora_info.get("cfg") else (p.get("cfg") or 1.0)),
                negative_prompt=p.get("negative") or None,
                num_images_per_prompt=1,
                generator=gen,
                callback_on_step_end=cb,
            )
            size_str = f"{res.images[0].width}×{res.images[0].height}"
            for img in res.images:
                name = f"{stamp}_{len(names)}.png"
                img.save(os.path.join(OUT_DIR, name))
                names.append("/outputs/" + name)
            res = None
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

        job["size"] = size_str
        job.update(status="done", images=names, progress=100,
                   elapsed=round(time.time() - t0, 1))
    except torch.cuda.OutOfMemoryError:
        job.update(status="error",
                   error="显存不足（OOM）。2K 级分辨率需要约 13GB 额外显存。建议："
                         "① 把「分辨率」改为 预览½（最有效）；"
                         "② 若想跑 2K，请关闭本地大模型（llama-server 占约 17GB 内存）后重启本服务，"
                         "服务会自动启用「文本编码器卸载」省出约 17GB 显存；"
                         "③ 或点「卸载模型」后重试。")
        pipe = None            # 必须先解除引用，否则权重仍被持有、显存无法真正释放
        mgr.unload()
    except Exception as e:
        traceback.print_exc()
        job.update(status="error", error=f"{type(e).__name__}: {e}")
        pipe = None
    finally:
        pipe = None            # 解除对管道的本地引用
        gc.collect()
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        gen_lock.release()


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/favicon.ico")
def favicon():
    return "", 204


THUMB_DIR = os.path.join(OUT_DIR, "_thumbs")
FAV_DIR = os.path.join(ROOT, "favorites")
os.makedirs(FAV_DIR, exist_ok=True)
FAV_FILE = os.path.join(ROOT, "favorites.json")

def fav_load():
    try:
        return json.load(open(FAV_FILE, encoding="utf-8")).get("items", [])
    except Exception:
        return []

def fav_save(items):
    json.dump({"items": items}, open(FAV_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def _send_thumb(fn, w, base_dir=None):
    """画廊缩略图：按需生成、落盘缓存（文件名唯一，可永久缓存）"""
    base_dir = base_dir or OUT_DIR
    src = os.path.join(base_dir, fn)
    if not os.path.isfile(src):
        return jsonify(error="not found"), 404
    os.makedirs(THUMB_DIR, exist_ok=True)
    base = ("fav_" if base_dir == FAV_DIR else "") + os.path.splitext(os.path.basename(fn))[0]
    tf = os.path.join(THUMB_DIR, "%s_%d.jpg" % (base, w))
    if not os.path.isfile(tf):
        im = Image.open(src)
        im.thumbnail((w, 4096), Image.LANCZOS)
        im.convert("RGB").save(tf, "JPEG", quality=72)
    resp = send_from_directory(THUMB_DIR, os.path.basename(tf))
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

@app.get("/outputs/<path:fn>")
def outputs(fn):
    w = request.args.get("w", type=int)
    if w and 16 <= w <= 1280:
        try:
            return _send_thumb(fn, w)
        except Exception:
            pass  # 缩略图生成失败（文件损坏等）时退回原图
    resp = send_from_directory(OUT_DIR, fn)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    if request.args.get("dl"):
        resp.headers["Content-Disposition"] = "attachment; filename=\"%s\"" % os.path.basename(fn)
    return resp


@app.get("/api/status")
def api_status():
    free, total = mgr.free_gb()
    with jobs_lock:
        counts = {}
        for j in jobs.values():
            counts[j["status"]] = counts.get(j["status"], 0) + 1
    return jsonify(
        loaded=mgr.pipe is not None,
        mode=mgr.mode,
        te_offload=mgr.te_offload,
        variant=mgr.variant or DEFAULT_VARIANT,
        variants={k: {"label": v["label"], "available": _variant_ready(k)} for k, v in MODEL_VARIANTS.items()},
        lora=mgr.lora,
        loras={k: {"label": v["label"], "available": k == "none" or bool(_lora_path(k)),
                   "kind": v.get("kind", ""), "strength": v.get("strength")} for k, v in LORAS.items()},
        free_ram_gb=round(free_ram_gb(), 1),
        busy=gen_lock.locked(),
        free_gb=None if free is None else round(free, 1),
        total_gb=None if total is None else round(total, 1),
        jobs=counts,
    )


@app.post("/api/variant")
def api_variant():
    global DEFAULT_VARIANT
    v = (request.form.get("variant") or "").strip()
    if v not in MODEL_VARIANTS:
        return jsonify(error="未知版本"), 400
    if not _variant_ready(v):
        return jsonify(error="该版本尚未部署完成"), 400
    if not gen_lock.acquire(blocking=False):
        return jsonify(error="生成中，请等本次出图结束后再切换"), 409
    try:
        DEFAULT_VARIANT = v
        json.dump({"variant": v}, open(VARIANT_FILE, "w", encoding="utf-8"))
        mgr.unload()  # 立即释放，下次生成时按新版本加载
    finally:
        gen_lock.release()
    return jsonify(ok=True, variant=v, label=MODEL_VARIANTS[v]["label"])


@app.post("/api/generate")
def api_generate():
    if not gen_lock.acquire(blocking=False):
        return jsonify(error="已有任务正在生成，请稍候"), 409

    try:
        f = request.form
        prompt = (f.get("prompt") or "").strip()
        if not prompt:
            gen_lock.release()
            return jsonify(error="提示词不能为空"), 400

        image_paths = []
        for fs in request.files.getlist("images"):
            if not fs or not fs.filename:
                continue
            if len(image_paths) >= 10:
                break
            path = os.path.join(UPLOAD_DIR, uuid.uuid4().hex[:8] + "_" + os.path.basename(fs.filename))
            fs.save(path)
            image_paths.append(path)

        params = dict(
            prompt=prompt,
            ratio=f.get("ratio") or "auto",
            steps=int(f.get("steps") or 40),
            seed=int(f["seed"]) if f.get("seed") else None,
            num=int(f.get("num") or 1),
            cfg=float(f.get("cfg") or 1.0),
            negative=(f.get("negative") or "").strip() or None,
            rgba=f.get("rgba") in ("1", "true", "on"),
            resolution=f.get("resolution") or "standard",
            mode=f.get("mode") or "auto",
            variant=f.get("variant") or None,
            lora=f.get("lora") or "none",
            lora_strength=float(f["lora_strength"]) if f.get("lora_strength") else None,
            width=int(f["width"]) if f.get("width") else None,
            height=int(f["height"]) if f.get("height") else None,
            image_paths=image_paths,
        )
        job = dict(
            id=uuid.uuid4().hex[:12],
            status="queued",
            progress=0,
            created=time.time(),
            images=[],
            error=None,
            elapsed=None,
            size=None,
            mode_used=None,
            params=params,
        )
        with jobs_lock:
            jobs[job["id"]] = job
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        client = dict(job)
        client["params"] = {k: v for k, v in params.items() if k != "image_paths"}
        client["params"]["image_count"] = len(image_paths)
        return jsonify(client)
    except Exception as e:
        gen_lock.release()
        traceback.print_exc()
        return jsonify(error=f"{type(e).__name__}: {e}"), 500


@app.get("/api/jobs")
def api_jobs():
    with jobs_lock:
        ordered = sorted(jobs.values(), key=lambda x: x.get("created", 0), reverse=True)[:40]
        out = []
        for j in ordered:
            c = dict(j)
            c["params"] = {k: v for k, v in j["params"].items() if k != "image_paths"}
            c["params"]["image_count"] = len(j["params"].get("image_paths", []))
            out.append(c)
    return jsonify(out)


@app.post("/api/unload")
def api_unload():
    if gen_lock.locked():
        return jsonify(error="生成中，无法卸载"), 409
    mgr.unload()
    return jsonify(ok=True)


@app.post("/api/load")
def api_load():
    """手动预加载模型到显存（「启动模型」按钮），避免第一次生图干等加载。"""
    if not gen_lock.acquire(blocking=False):
        return jsonify(error="生成中，请等本次出图结束"), 409
    try:
        f = request.form
        mode = (f.get("mode") or "auto").strip() or "auto"
        variant = (f.get("variant") or "").strip() or None
        used = mgr.load(mode, variant)
        free, total = mgr.free_gb()
        return jsonify(ok=True, mode=used, variant=mgr.variant,
                       te_offload=mgr.te_offload, loaded=mgr.pipe is not None,
                       free_gb=None if free is None else round(free, 1),
                       total_gb=None if total is None else round(total, 1))
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    finally:
        gen_lock.release()


def load_history_from_disk():
    """服务重启后从 outputs 目录重建历史记录，保证画廊不丢图、可删除。"""
    try:
        files = [f for f in os.listdir(OUT_DIR)
                 if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    except OSError:
        return
    groups = {}
    for fn in files:
        stem, dot, tail = fn.rpartition(".")
        key = stem.rsplit("_", 1)[0] if tail.isdigit() and "_" in stem else fn
        groups.setdefault(key, []).append(fn)
    for key, names in groups.items():
        names.sort()
        created = None
        m = re.match(r"(\d{8})_(\d{6})", key)
        if m:
            try:
                created = time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
            except ValueError:
                created = None
        if created is None:
            try:
                created = os.path.getmtime(os.path.join(OUT_DIR, names[0]))
            except OSError:
                created = time.time()
        size_str = None
        try:
            with Image.open(os.path.join(OUT_DIR, names[0])) as im:
                size_str = f"{im.width}×{im.height}"
        except Exception:
            pass
        jid = "disk_" + key
        jobs[jid] = dict(
            id=jid, status="done", progress=100, created=created,
            images=["/outputs/" + n for n in names], error=None, elapsed=None,
            size=size_str, mode_used=None,
            params=dict(prompt="（历史图片·服务重启后从磁盘恢复）", ratio="auto", steps=0,
                        seed=None, num=len(names), cfg=1.0, negative=None, rgba=False,
                        resolution="standard", mode="auto", image_paths=[], image_count=0),
        )


def _output_size_mb():
    total = 0
    try:
        for fn in os.listdir(OUT_DIR):
            p = os.path.join(OUT_DIR, fn)
            if os.path.isfile(p):
                total += os.path.getsize(p)
    except OSError:
        pass
    return round(total / 2**20, 1)


@app.get("/api/storage")
def api_storage():
    count = 0
    try:
        count = sum(1 for fn in os.listdir(OUT_DIR)
                    if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    except OSError:
        pass
    return jsonify(count=count, size_mb=_output_size_mb())


@app.post("/api/jobs/delete")
def api_jobs_delete():
    """删除一条任务记录（失败卡片等无图任务用）"""
    data = request.get_json(silent=True) or {}
    jid = str(data.get("id") or "")
    with jobs_lock:
        removed = jobs.pop(jid, None)
    return jsonify(ok=bool(removed))

@app.post("/api/favorite/add")
def api_fav_add():
    """收藏：图片从 outputs 移入 favorites，并从作品集记录中移除"""
    data = request.get_json(silent=True) or {}
    name = os.path.basename(str(data.get("name") or ""))
    src = os.path.join(OUT_DIR, name)
    if not (name and os.path.isfile(src)):
        return jsonify(error="图片不存在"), 404
    if gen_lock.locked():
        return jsonify(error="生成中，稍后再收藏"), 409
    dst = os.path.join(FAV_DIR, name)
    stem, ext = os.path.splitext(name)
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(FAV_DIR, "%s_%d%s" % (stem, n, ext))
        n += 1
    os.replace(src, dst)
    _purge_thumbs(stem)
    with jobs_lock:
        for jid, j in list(jobs.items()):
            if "/outputs/" + name in j.get("images", []):
                j["images"].remove("/outputs/" + name)
                if not j["images"]:
                    del jobs[jid]
    items = fav_load()
    items.insert(0, {"name": os.path.basename(dst), "ts": time.time()})
    fav_save(items)
    return jsonify(ok=True, count=len(items))

@app.get("/api/favorite/list")
def api_fav_list():
    items = []
    for it in fav_load():
        if os.path.isfile(os.path.join(FAV_DIR, it["name"])):
            items.append({"name": it["name"], "ts": it.get("ts")})
    return jsonify(items=items)

@app.post("/api/favorite/remove")
def api_fav_remove():
    """取消收藏：unfav=放回作品集 / delete=直接删除文件"""
    data = request.get_json(silent=True) or {}
    name = os.path.basename(str(data.get("name") or ""))
    act = data.get("action", "unfav")
    p = os.path.join(FAV_DIR, name)
    if not os.path.isfile(p):
        return jsonify(error="收藏里没有这张图"), 404
    if act == "delete":
        os.remove(p)
    else:
        os.replace(p, os.path.join(OUT_DIR, name))
        with jobs_lock:
            jobs["fav_" + name] = {"id": "fav_" + name, "status": "done", "created": time.time(),
                                   "images": ["/outputs/" + name], "error": None,
                                   "elapsed": None, "size": None,
                                   "params": {"prompt": "（从收藏放回）"}}
    fav_save([it for it in fav_load() if it["name"] != name])
    _purge_thumbs("fav_" + os.path.splitext(name)[0])
    return jsonify(ok=True)

@app.get("/favorites/<path:fn>")
def favorites(fn):
    w = request.args.get("w", type=int)
    if w and 16 <= w <= 1280:
        try:
            return _send_thumb(fn, w, FAV_DIR)
        except Exception:
            pass
    resp = send_from_directory(FAV_DIR, fn)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    if request.args.get("dl"):
        resp.headers["Content-Disposition"] = "attachment; filename=\"%s\"" % os.path.basename(fn)
    return resp

def _purge_thumbs(base):
    """删除原图后清理对应缩略图；base=None 清空全部"""
    try:
        for fn in os.listdir(THUMB_DIR):
            if base is None or fn.startswith(base + "_"):
                try:
                    os.remove(os.path.join(THUMB_DIR, fn))
                except OSError:
                    pass
    except OSError:
        pass

@app.post("/api/delete")
def api_delete():
    """删除单张/多张已生成图片，或清空全部（仅限 outputs 目录内的文件）。"""
    if gen_lock.locked():
        return jsonify(error="生成中，稍后再删除"), 409
    data = request.get_json(silent=True) or {}
    removed = 0

    def drop_from_jobs(url):
        with jobs_lock:
            for jid, j in list(jobs.items()):
                if url in j.get("images", []):
                    j["images"].remove(url)
                    if not j["images"]:
                        del jobs[jid]
                    return

    if data.get("all"):
        with jobs_lock:
            names = []
            for j in jobs.values():
                names.extend(j.get("images", []))
            jobs.clear()
        for name in names:
            p = os.path.join(OUT_DIR, os.path.basename(name))
            if os.path.isfile(p):
                try:
                    os.remove(p)
                    removed += 1
                except OSError:
                    pass
        _purge_thumbs(None)
        # 兜底：清掉目录里所有遗留图片
        try:
            for fn in os.listdir(OUT_DIR):
                if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    p = os.path.join(OUT_DIR, fn)
                    if os.path.isfile(p):
                        try:
                            os.remove(p)
                            removed += 1
                        except OSError:
                            pass
        except OSError:
            pass
    else:
        for name in data.get("names", []):
            safe = os.path.basename(str(name))
            p = os.path.join(OUT_DIR, safe)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                    removed += 1
                except OSError:
                    pass
            _purge_thumbs(os.path.splitext(safe)[0])
            drop_from_jobs("/outputs/" + safe)

    return jsonify(ok=True, removed=removed, size_mb=_output_size_mb())


def open_browser_when_ready(port=7860, timeout=90):
    """等待服务真正可访问后再打开浏览器，避免浏览器开得太早显示“无法访问”。"""
    import webbrowser
    t0 = time.time()
    while time.time() - t0 < timeout:
        if existing_server_running(port, timeout=1.5):
            webbrowser.open(f"http://127.0.0.1:{port}")
            return
        time.sleep(0.5)


def existing_server_running(port=7860, timeout=2.5):
    """向端口发一个真实请求判断服务是否已在运行。
    不用 bind 测试：Windows 允许两个进程同时绑定同一端口（都设了 SO_REUSEADDR），会误判。"""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


LOCK_FILE = os.path.join(ROOT, ".server.lock")


def _pid_alive(pid):
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _pid_is_qwen(pid):
    """锁里的 PID 不仅要活着，还得真是本服务进程（PID 会被系统复用，否则僵尸锁冒充活锁，
    之后每次启动都误判'另一个实例正在启动中'而拒绝启动，界面上永远开不起来——2026-10-14 实翻车）。"""
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(buf))
            qipf = getattr(ctypes.windll.kernel32, 'QueryFullProcessImageNameW', None)
            if qipf and qipf(handle, 0, buf, ctypes.byref(size)):
                path = buf.value.lower()
                if ('python' not in path) or ('qwen_image' not in path):
                    return False
            cmdline = ''
            try:
                import subprocess
                out = subprocess.run(['powershell', '-NoProfile', '-Command',
                                      f'(Get-CimInstance Win32_Process -Filter "ProcessId={int(pid)}").CommandLine'],
                                     capture_output=True, text=True, timeout=10).stdout
                cmdline = out.lower()
            except Exception:
                pass
            return 'server.py' in cmdline and 'qwen_image' in cmdline.replace(chr(92), '/')
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


def acquire_singleton_lock():
    """原子锁文件：防止两个实例同时启动（HTTP 探测在启动窗口内有竞态，Windows 还允许双绑定）。"""
    import atexit
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            with open(LOCK_FILE) as f:
                old = f.read().strip()
            if old.isdigit() and _pid_is_qwen(old):
                return False  # 另一个本服务实例活着 → 我退出
            os.remove(LOCK_FILE)  # 残留锁（含 PID 被复用的僵尸锁）→ 接管
        except OSError:
            pass
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return True
    except OSError:
        return True
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    atexit.register(lambda: os.remove(LOCK_FILE) if os.path.exists(LOCK_FILE) else None)
    return True


if __name__ == "__main__":
    if existing_server_running():
        print("检测到本机已有生图服务在运行，本次不再启动新实例。")
        print("已经为你打开页面；若打不开，请手动访问 http://127.0.0.1:7860")
        print("若要重启服务，先运行 停止服务.bat 再启动。")
        import webbrowser
        webbrowser.open("http://127.0.0.1:7860")
        sys.exit(0)
    if not acquire_singleton_lock():
        print("另一个实例正在启动中（启动锁被占用），本次退出。")
        print("等服务就绪后浏览器会自动打开页面。")
        sys.exit(0)
    print(f"Qwen-Image-2.1 WebUI 启动中... 地址: http://127.0.0.1:7860  (Ctrl+C 停止)", flush=True)
    load_history_from_disk()
    print(f"[history] 已从磁盘恢复 {len(jobs)} 组历史图片", flush=True)
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    app.run(host="127.0.0.1", port=7860, threaded=True)
