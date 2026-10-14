# -*- coding: utf-8 -*-
"""组装 Qwen-Image-2.1-UC 目录：组件 junction 到官方，text_encoder 用 Heretic 权重"""
import os, shutil, subprocess, sys, json

ROOT = r"E:\Qwen_image2.1"
OFFICIAL = os.path.join(ROOT, "models", "Qwen-Image-2.1")
UC = os.path.join(ROOT, "models", "Qwen-Image-2.1-UC")
HERETIC = os.path.join(ROOT, "models", "heretic-te")

def junction(link, target):
    if os.path.exists(link):
        return True
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"New-Item -ItemType Junction -Path '{link}' -Target '{target}'"],
                       capture_output=True, text=True)
    return r.returncode == 0

os.makedirs(UC, exist_ok=True)

# 1) 根文件
for f in ("model_index.json", "configuration.json"):
    src, dst = os.path.join(OFFICIAL, f), os.path.join(UC, f)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        print("copy", f)

# 2) 组件 junction
for comp in ("processor", "scheduler", "transformer", "vae"):
    link, target = os.path.join(UC, comp), os.path.join(OFFICIAL, comp)
    if os.path.isdir(link) and not os.path.islink(link) and not os.path.isdir(os.path.join(link, ".")):
        pass  # 占位，正常不会走到
    if not os.path.exists(link):
        if junction(link, target):
            print("junction", comp)
        else:
            sys.exit(f"junction 失败: {comp}")

# 3) text_encoder：官方 config（字段名兼容旧 transformers）+ heretic 权重
te = os.path.join(UC, "text_encoder")
os.makedirs(te, exist_ok=True)
shutil.copy2(os.path.join(OFFICIAL, "text_encoder", "config.json"), os.path.join(te, "config.json"))
shutil.copy2(os.path.join(OFFICIAL, "text_encoder", "generation_config.json"),
             os.path.join(te, "generation_config.json"))
for f in os.listdir(HERETIC):
    if f.startswith("model-") or f == "model.safetensors.index.json":
        dst = os.path.join(te, f)
        if not os.path.exists(dst):
            shutil.move(os.path.join(HERETIC, f), dst)
            print("move", f)

# 4) 校验
need = {"model_index.json", "processor", "scheduler", "transformer", "vae", "text_encoder"}
missing = [x for x in need if not os.path.exists(os.path.join(UC, x))]
idx = json.load(open(os.path.join(te, "model.safetensors.index.json"), encoding="utf-8"))
shards = sorted(set(idx["weight_map"].values()))
shard_ok = all(os.path.exists(os.path.join(te, s)) for s in shards)
total = sum(os.path.getsize(os.path.join(te, s)) for s in shards)
print("缺失:", missing or "无", "| 分片:", len(shards), "个齐全" if shard_ok else "不齐!",
      f"| 权重合计 {total/2**30:.2f}GB")
print("=== UC 目录就绪 ===" if not missing and shard_ok else "=== 不完整 ===")
