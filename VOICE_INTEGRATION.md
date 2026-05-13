# Lapwing Voice Integration Guide

## 概述

本指南介绍如何为 Lapwing 集成 GPT SoVITS 语音合成功能，让 Lapwing 能够"说话"。

## 系统架构

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Lapwing API   │────▶│  TTS Client      │────▶│  GPT SoVITS     │
│   (FastAPI)     │     │  (Python)        │     │  (Docker)       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                        │
        │                        ▼                        │
        │               ┌──────────────────┐              │
        │               │  EII → 情感映射   │              │
        │               │  语速/音调/温度    │              │
        │               └──────────────────┘              │
        │                                                 │
        ▼                                                 ▼
┌─────────────────┐                            ┌─────────────────┐
│  Audio Manager  │                            │  GPU Inference  │
│  (文件存储/清理)  │                            │  (语音合成)      │
└─────────────────┘                            └─────────────────┘
```

## 快速开始

### 1. 环境准备

**硬件要求：**
- NVIDIA GPU（GTX 1060 6GB+ / RTX 系列）
- 8GB+ 显存
- Windows 11 + WSL2 或 Linux

**软件安装：**
```bash
# 1. 安装 WSL2 (Windows)
wsl --install

# 2. 安装 Docker Desktop
# 下载: https://www.docker.com/products/docker-desktop

# 3. 安装 NVIDIA Container Toolkit (WSL2)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# 4. 验证 GPU 支持
docker run --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 2. 启动 GPT SoVITS 服务

```bash
# 进入目录
cd gpt-sovits

# 创建必要目录
mkdir -p models/pretrained models/trained reference output workspace

# 下载预训练模型 (需要手动下载)
# 1. 访问 https://github.com/RVC-Boss/GPT-SoVITS/releases
# 2. 下载并放入 models/pretrained/

# 准备参考音频
# 在 reference/ 目录放入 Lapwing 的声音样本
# 建议: sad.wav, calm.wav, neutral.wav, happy.wav, excited.wav

# 启动服务
docker-compose up -d

# 检查日志
docker-compose logs -f
```

### 3. 启动 Lapwing (带语音)

```bash
# 回到项目根目录
cd ..

# 安装依赖
pip install -r requirements.txt
# 或
poetry install

# 启动 Lapwing API
uvicorn api:app --reload --port 8000
```

## API 使用

### 文字聊天（原有功能）

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，Lapwing！"}'
```

### 语音聊天（新功能）

```bash
curl -X POST http://localhost:8000/chat/voice \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，Lapwing！"}' \
  --output response.json

# 返回:
{
  "reply": "你好呀，见到你真开心~",
  "eii": 65.5,
  "audio_url": "/audio/generated/cache/2025-05-12/a1b2c3d4.wav"
}

# 播放音频
curl http://localhost:8000/audio/generated/cache/2025-05-12/a1b2c3d4.wav --output response.wav
```

### 直接 TTS

```bash
# 使用 EII 自动选择情感
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "今天天气真好，我们去散步吧！",
    "eii": 75
  }'

# 指定情感
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "我有点难过...",
    "emotion": "sad"
  }'
```

### 查看可用情感

```bash
curl http://localhost:8000/tts/emotions
```

## 情感映射

Lapwing 的 EII (0-100) 自动映射到语音情感：

| EII 范围 | 情感 | 语速 | 音调 | 温度 | 参考音频 |
|---------|------|------|------|------|----------|
| 0-20 | 悲伤 | 0.85x | 低 | 0.8 | sad.wav |
| 20-40 | 平静 | 0.95x | 正常 | 0.9 | calm.wav |
| 40-60 | 温和 | 1.0x | 正常 | 1.0 | neutral.wav |
| 60-80 | 开心 | 1.1x | 稍高 | 1.1 | happy.wav |
| 80-100 | 兴奋 | 1.2x | 高 | 1.2 | excited.wav |

## 训练 Lapwing 的声音

### 1. 准备训练数据

**音频要求：**
- 格式：WAV, 44.1kHz, 16bit, 单声道
- 时长：5-10 分钟总时长
- 质量：清晰无噪音，避免混响
- 内容：自然对话，包含多种情感

**录制建议：**
- 悲伤：轻柔、缓慢的语调
- 平静：平稳、放松的语调
- 开心：轻快、上扬的语调
- 兴奋：快速、高能量的语调

### 2. 使用 Web UI 训练

```bash
# 访问 GPT SoVITS Web UI
open http://localhost:9874

# 训练流程：
# 1. 0b-语音切分：上传音频，自动切分为 3-10 秒片段
# 2. 0c-语音识别打标：ASR 自动转文字
# 3. 0d-语音文本校对：检查并修正转录错误
# 4. 1A-训练集格式化：生成训练数据
# 5. 1B-微调训练：
#    - SoVITS 训练：训练 10-20 epoch
#    - GPT 训练：训练 10-20 epoch
# 6. 1C-推理：测试生成效果
```

### 3. 导出模型

训练完成后，模型保存在：
```
gpt-sovits/models/trained/{experiment_name}/
├── config.json
├── GPT_weights/
│   └── lapwing-e15.ckpt
└── SoVITS_weights/
    └── lapwing_e15_s150.pth
```

### 4. 更新 Lapwing 配置

修改 `tts_client.py` 中的参考音频路径：
```python
self.emotion_references = {
    EmotionPreset.SAD: self.reference_dir / "sad.wav",
    EmotionPreset.CALM: self.reference_dir / "calm.wav",
    # ... 使用你训练时准备的参考音频
}
```

## 目录结构

```
.
├── api.py                    # FastAPI 入口（已更新）
├── tts_client.py            # TTS 客户端
├── audio_manager.py         # 音频文件管理
├── audio/                   # 音频存储
│   ├── generated/          # 生成的音频
│   │   └── cache/          # 缓存（按日期）
│   └── reference/          # 参考音频
│       ├── sad.wav
│       ├── calm.wav
│       ├── neutral.wav
│       ├── happy.wav
│       └── excited.wav
├── gpt-sovits/             # GPT SoVITS 部署
│   ├── docker-compose.yml
│   ├── models/
│   │   ├── pretrained/     # 预训练模型
│   │   └── trained/        # 训练的模型
│   ├── reference/          # 参考音频
│   └── output/             # 生成输出
└── ...
```

## 故障排查

### TTS 服务无法连接

```bash
# 检查 GPT SoVITS 是否运行
docker ps | grep gpt-sovits

# 检查日志
docker-compose -f gpt-sovits/docker-compose.yml logs

# 测试 API
curl http://localhost:9872/health
```

### GPU 不可用

```bash
# WSL2 中检查
nvidia-smi

# 如果失败，重启 WSL2
wsl --shutdown
# 重新打开 WSL2

# Docker 中检查
docker run --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 合成质量差

- 检查参考音频是否清晰
- 确认参考音频与目标情感匹配
- 调整 temperature 参数（0.5-1.5）
- 尝试不同的参考音频

### 音频文件未生成

```bash
# 检查目录权限
ls -la audio/

# 检查日志
tail -f logs/lapwing.log
```

## 性能优化

### 缓存策略

- 相同文本+情感组合会命中缓存
- 缓存保留 7 天
- 非缓存生成文件保留 24 小时
- 自动清理任务每 6 小时运行一次

### 并发控制

- TTS 请求默认最多 3 个并发
- 长文本自动分句处理
- 每句之间间隔 100ms 避免 GPU 过载

### 显存优化

如果显存不足（< 8GB）：
1. 降低 batch size（修改 docker-compose.yml）
2. 使用更小的基础模型
3. 限制并发 TTS 请求数

## 配置选项

环境变量（`.env`）：
```bash
# TTS 服务地址
TTS_API_URL=http://localhost:9872

# 音频存储配置
AUDIO_MAX_CACHE_DAYS=7
AUDIO_MAX_GENERATED_HOURS=24
AUDIO_CLEANUP_INTERVAL_HOURS=6
```

## 下一步

1. **录制参考音频**：准备 5-10 分钟的高质量音频
2. **训练声音模型**：使用 GPT SoVITS Web UI
3. **测试集成**：使用 `/chat/voice` 端点
4. **调优参数**：根据效果调整情感映射参数

---

**参考链接：**
- [GPT SoVITS GitHub](https://github.com/RVC-Boss/GPT-SoVITS)
- [GPT SoVITS 文档](https://github.com/RVC-Boss/GPT-SoVITS/wiki)
