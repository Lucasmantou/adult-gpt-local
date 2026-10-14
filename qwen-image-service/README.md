# Qwen-Image-2.1 本地部署（RTX 4090D / Windows）

2026-09-21 开源的 **Qwen-Image-2.1**：统一文生图 + 图像编辑模型，视觉生成部分仅 7B 参数（32 层 Single-Stream DiT）。
官方发布页：[ModelScope](https://modelscope.cn/models/Qwen/Qwen-Image-2.1) | [HuggingFace](https://huggingface.co/Qwen/Qwen-Image-2.1) | [博客](https://qwen.ai/blog?id=qwen-image-2.1)

## 目录结构

```
E:\Qwen_image2.1\
├── venv\                    # Python 虚拟环境 (Python 3.12)
├── diffusers-main\          # diffusers 开发版源码（含 QwenImage21Pipeline）
├── models\Qwen-Image-2.1\   # 模型权重（33.1 GB，bf16）
├── generate.py              # 命令行生成/编辑工具
├── download_model.py        # 断点续传下载器（下载中断后重跑即可）
└── test_install.py          # 安装自检脚本
```

## 已安装的环境

| 组件 | 版本 | 说明 |
|---|---|---|
| torch | 2.14.0+cu130 | CUDA 12.8/13.0 均可，匹配驱动 CUDA 13.1 |
| transformers | 5.17.0 | 模型卡要求 >= 5.17（Qwen3-VL 文本编码器） |
| diffusers | git main | PyPI 0.40.0 尚无 QwenImage21Pipeline，必须用源码版 |
| accelerate / pillow / modelscope | 最新 | |

本机 48GB 显存可全量 bf16 直载显卡，无需 offload 和量化。

## 快速开始

### 方式一：GUI 网页界面（推荐）

双击 `启动界面.bat`（或手动运行 `venv\Scripts\python server.py`），浏览器自动打开 **http://127.0.0.1:7860**：

- 写提示词 → 选比例/画质/分辨率 → 点「开始生成」，带实时进度条
- 传参考图即进入编辑模式（可拖拽，最多 10 张）
- 顶部状态栏实时显示显存占用、模型状态、设备模式、2K 优化状态
- **设备模式**：自动（推荐）/ 全速（需 ≥41GB 空闲显存）/ 省显存（需 ≥35GB 空闲内存）
- **「卸载模型」** 按钮一键释放显存还给 ollama / llama-server
- **作品集**：右侧独立滚动的预览图墙（页面自身不滚动，左侧生成按钮始终可见）
  - 鼠标悬停图片右上角「×」可**删除单张**；「清空全部」一键清理释放磁盘空间
  - 标题栏实时显示**图片数量与磁盘占用**（MB）
  - 重启服务后历史图片会**自动从磁盘恢复**，不会丢失
  - 点图片可看大图（带透明背景棋盘格预览）

关闭 bat 窗口即停止服务。仅监听 127.0.0.1，局域网不可访问。

### 方式二：命令行

先激活虚拟环境（PowerShell）：

```powershell
E:\Qwen_image2.1\venv\Scripts\activate
cd E:\Qwen_image2.1
```

### 1. 文生图

```bash
python generate.py "一只戴着宇航员头盔的橘猫漂浮在星空中，电影感打光" -o cat.png
```

- `--ratio 16:9` 使用官方推荐分辨率（见下表）；或 `--width 2752 --height 1536` 自定义
- `--seed 42` 固定种子复现；`--steps 40` 默认步数（20~50 之间调节画质与速度）
- `--num 4` 一次出 4 张

### 2. 图像编辑（传 `-i` 即进入编辑模式）

```bash
# 单图编辑
python generate.py "把背景换成黄昏的海滩" -i photo.jpg -o edited.png

# 多参考图（最多 10 张）：人物合影 / 商品合成 / 风格迁移
python generate.py "让这两个人在樱花树下合影" -i person_a.png -i person_b.png -o group.png
```

编辑时可不指定尺寸，默认跟随参考图宽高比。支持圈选局部、涂鸦标注等方式指定编辑区域。

### 3. RGBA 透明图生成（贴纸/素材）

```bash
python generate.py "一只可爱的卡通小龙贴纸" --rgba -o dragon.png
```

`--rgba` 会自动套用官方推荐的透明图提示词格式，输出带 alpha 通道的 PNG。

### 4. 官方推荐分辨率

| 比例 | 分辨率 | 比例 | 分辨率 |
|---|---|---|---|
| 1:1 | 2048×2048 | 3:2 | 2528×1696 |
| 4:3 | 2400×1792 | 2:3 | 1696×2528 |
| 3:4 | 1792×2400 | 16:9 | 2752×1536 |
| 9:16 | 1536×2752 | | |

查看：`python generate.py --ratios`

## Python API 调用

```python
import torch
from diffusers import QwenImage21Pipeline

pipe = QwenImage21Pipeline.from_pretrained(
    r"E:\Qwen_image2.1\models\Qwen-Image-2.1", torch_dtype=torch.bfloat16
).to("cuda")

# 文生图（2.1 官方推荐不开 CFG 引导，true_cfg_scale 保持默认 1.0）
image = pipe(
    prompt="A neon shop sign that reads \"QWEN IMAGE 2.1\", rainy night",
    width=2048, height=2048,
    num_inference_steps=40,
    generator=torch.Generator("cuda").manual_seed(42),
).images[0]
image.save("t2i.png")

# 图像编辑：传入 image 即可；最多 10 张参考图
# pipe(prompt="Change the background to a sunset beach", image=input_image, ...)
```

要点：
- `true_cfg_scale` 默认 1.0 = 无引导采样（2.1 官方推荐方式）。需要更强提示词遵循时可设 2~4 并配 `negative_prompt`。
- `use_kv_cache=True`（默认）利用前缀 KV 缓存加速。
- 显存 < 24GB 时用 `pipe.enable_model_cpu_offload()`。

## 在 Python 代码里使用本地 diffusers

方式一（推荐）：把源码包装进环境

```bash
E:\Qwen_image2.1\venv\Scripts\python -m pip install -e E:\Qwen_image2.1\diffusers-main --no-deps
```

方式二：脚本里手动加路径（本目录脚本已采用类似方式，无需安装）

```python
import sys; sys.path.insert(0, r"E:\Qwen_image2.1\diffusers-main\src")
```

## 常见问题

- **下载中断**：直接重跑 `python download_model.py`，支持断点续传；若开启 Clash 等代理，下载器会自动检测并走代理加速。torch wheel 同理：`python download_torch_wheel.py`。
- **下载完成后**：先跑 `python test_install.py` 自检（自动加载模型、生成一张测试图）。
- **网络被代理卡住**：本机系统代理指向 127.0.0.1:7890，若代理软件未运行，给命令加环境变量 `NO_PROXY=*`（本目录脚本已内置处理）。
- **代理启动注意**：`E:\JEV\启动代理.bat` 用 `start` 拉起 mihomo，**关闭那个最小化窗口代理就会断**。mihomo 正确启动方式（保持窗口或后台）：
  ```
  E:\JEV\bin\mihomo-windows-amd64.exe -d E:\JEV\proxy -f E:\JEV\proxy\sub_config.yaml
  ```
  管理面板 http://127.0.0.1:19090/ui ，可手动切换节点。
- **网速慢排查**（本机 2026-09-21 实测直连仅 ~0.5 MB/s）：
  1. 检查夸克网盘等同步软件是否在后台上传/下载，暂停后再试
  2. 重启光猫/路由器，或改插网线排除 WiFi 拥堵
  3. 浏览器打开 speedtest.cn 对照，若同样慢则是线路问题，找运营商
  4. 线路恢复后下载器会自动提速，无需重启（单块下载失败有 10 次重试）
- **提示词**：中英文均可，长句描述效果更好；文字渲染类提示词把要渲染的文字用引号包住。
- **许可证**：Qwen Research License Agreement，研究用途免费，商用需遵守协议条款（详见 models/Qwen-Image-2.1/LICENSE）。
