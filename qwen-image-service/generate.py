# -*- coding: utf-8 -*-
"""Qwen-Image-2.1 命令行工具：文生图 / 图像编辑 / RGBA 透明图生成。

用法示例：
  文生图:   python generate.py "一只戴宇航员头盔的橘猫，电影感打光" -o cat.png
  指定尺寸: python generate.py "prompt" --width 2752 --height 1536
  图像编辑: python generate.py "把背景换成黄昏的海滩" -i input.png -o edited.png
  多参考图: python generate.py "让两个人合影" -i a.png -i b.png
  RGBA:     python generate.py "一只可爱的卡通龙贴纸" --rgba -o dragon.png
"""
import argparse
import os
import sys

import torch
from PIL import Image

# 优先使用本目录的 diffusers 开发版源码（QwenImage21Pipeline 仅存在于 git main）
_LOCAL_DIFFUSERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diffusers-main", "src")
if os.path.isdir(_LOCAL_DIFFUSERS):
    sys.path.insert(0, _LOCAL_DIFFUSERS)

from diffusers import QwenImage21Pipeline

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("QWEN_IMAGE_MODEL", os.path.join(ROOT, "models", "Qwen-Image-2.1"))

RGBA_PROMPT_PREFIX = "This is an RGBA image with transparency. "
RGBA_PROMPT_SUFFIX = " The image has alpha channel and the background is transparent."

# 官方推荐的宽高比（长边 2048~2752）
ASPECT_RATIOS = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}


def main():
    parser = argparse.ArgumentParser(description="Qwen-Image-2.1 生成/编辑工具", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("prompt", nargs="?", help="提示词，支持中英文")
    parser.add_argument("-o", "--out", default="output.png", help="输出文件路径（默认 output.png）")
    parser.add_argument("-i", "--image", action="append", default=[],
                        help="参考图 / 待编辑图片路径，可传多次（最多 10 张）")
    parser.add_argument("--ratio", choices=sorted(ASPECT_RATIOS), help="官方推荐宽高比，设置后忽略 --width/--height")
    parser.add_argument("--width", type=int, default=2048, help="宽（默认 2048）")
    parser.add_argument("--height", type=int, default=2048, help="高（默认 2048）")
    parser.add_argument("--steps", type=int, default=40, help="去噪步数（默认 40）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现")
    parser.add_argument("--cfg", type=float, default=1.0,
                        help="true_cfg_scale（默认 1.0=官方推荐的无引导采样；>1 时建议配 --negative）")
    parser.add_argument("--negative", default=None, help="负向提示词（仅 --cfg > 1 时生效）")
    parser.add_argument("--rgba", action="store_true", help="生成带透明通道的 PNG")
    parser.add_argument("--offload", action="store_true", help="显存不足时启用 CPU offload")
    parser.add_argument("--num", type=int, default=1, help="每个提示词生成几张图")
    parser.add_argument("--ratios", action="store_true", help="仅打印官方推荐分辨率表")
    args = parser.parse_args()

    if args.ratios:
        for name, (w, h) in ASPECT_RATIOS.items():
            print(f"{name:>5}: {w} x {h}")
        return
    if not args.prompt:
        parser.error("请提供提示词，例如: python generate.py \"一只橘猫\"")

    width, height = ASPECT_RATIOS[args.ratio] if args.ratio else (args.width, args.height)
    prompt = args.prompt
    if args.rgba:
        prompt = RGBA_PROMPT_PREFIX + prompt + RGBA_PROMPT_SUFFIX

    print(f"加载模型: {MODEL_DIR}")
    pipe = QwenImage21Pipeline.from_pretrained(MODEL_DIR, torch_dtype=torch.bfloat16)
    if args.offload:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")

    generator = torch.Generator("cuda").manual_seed(args.seed) if args.seed is not None else None
    condition_images = [Image.open(p).convert("RGB") for p in args.image] if args.image else None

    print(f"生成中: {width}x{height}, {args.steps} 步, {args.num} 张 ...")
    result = pipe(
        prompt=prompt,
        image=condition_images,
        width=width,
        height=height,
        num_inference_steps=args.steps,
        true_cfg_scale=args.cfg,
        negative_prompt=args.negative,
        num_images_per_prompt=args.num,
        generator=generator,
    )
    images = result.images
    if args.num == 1:
        images[0].save(args.out)
        print(f"已保存: {args.out}")
    else:
        stem, ext = os.path.splitext(args.out)
        for idx, img in enumerate(images):
            path = f"{stem}_{idx}{ext}"
            img.save(path)
            print(f"已保存: {path}")


if __name__ == "__main__":
    main()
