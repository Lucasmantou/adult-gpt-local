# -*- coding: utf-8 -*-
"""安装自检脚本：模型权重下载完成后运行，验证环境可用。

用法: python test_install.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "diffusers-main", "src"))

import torch

print(f"torch {torch.__version__} | CUDA: {torch.cuda.is_available()}")
assert torch.cuda.is_available(), "torch 未检测到 CUDA！请确认已安装 cu130 版本（见 README）"
print(f"GPU: {torch.cuda.get_device_name(0)} | 显存: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

from diffusers import QwenImage21Pipeline
print("diffusers QwenImage21Pipeline 导入成功")

model_dir = os.path.join(ROOT, "models", "Qwen-Image-2.1")
required = [
    "model_index.json",
    "transformer/diffusion_pytorch_model-00001-of-00002.safetensors",
    "transformer/diffusion_pytorch_model-00002-of-00002.safetensors",
    "text_encoder/model-00001-of-00004.safetensors",
    "text_encoder/model-00002-of-00004.safetensors",
    "text_encoder/model-00003-of-00004.safetensors",
    "text_encoder/model-00004-of-00004.safetensors",
    "vae/diffusion_pytorch_model.safetensors",
]
missing = [f for f in required if not os.path.exists(os.path.join(model_dir, f))]
if missing:
    print(f"\n[未完成] 还有 {len(missing)} 个权重文件缺失（下载未完成或进行中）：")
    for f in missing:
        print("  -", f)
    print("重跑 python download_model.py 继续下载（断点续传）")
    sys.exit(1)

print("权重文件齐全，开始加载模型并生成 512x512 测试图（约 1-3 分钟）...")
pipe = QwenImage21Pipeline.from_pretrained(model_dir, torch_dtype=torch.bfloat16).to("cuda")
img = pipe(
    prompt="A cute orange cat, studio lighting",
    width=512, height=512,
    num_inference_steps=20,
    generator=torch.Generator("cuda").manual_seed(0),
).images[0]
out = os.path.join(ROOT, "smoke_test.png")
img.save(out)
print(f"✔ 自检通过！测试图已保存: {out}")
print("现在可以正常使用了，见 README.md 或运行 python generate.py --help")
