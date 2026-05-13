# GPT SoVITS Docker Deployment

## 目录结构

```
gpt-sovits/
├── docker-compose.yml      # Docker Compose 配置
├── Dockerfile              # 自定义镜像（如果需要）
├── models/                 # 模型文件（挂载卷）
│   ├── pretrained_models/  # 预训练模型
│   └── trained/            # 训练的 Lapwing 声音模型
├── reference/              # 参考音频（挂载卷）
└── output/                 # 生成的音频输出（挂载卷）
```

## 快速启动

### 1. 准备工作

**下载预训练模型：**
```bash
cd models/pretrained_models

# GPT-SoVITS 模型 (check https://github.com/RVC-Boss/GPT-SoVITS for latest links)
# 需要下载:
# - GPT 权重 (如 gpt-sovits-pretrained.pth)
# - SoVITS 权重 (如 s2G488k.pth)
# - 其他辅助模型
```

**准备参考音频：**
```bash
# 在 reference/ 目录放置 Lapwing 的声音样本
# 建议: 5-10 个不同情感的 3-10 秒音频片段
# 格式: WAV, 44.1kHz, 16bit, 单声道
```

### 2. 启动服务

```bash
cd gpt-sovits
docker-compose up -d
```

**访问：**
- Web UI: http://localhost:9874
- API: http://localhost:9872
- TTS API: http://localhost:9872/tts

### 3. 停止服务

```bash
docker-compose down
```

## API 接口文档

### POST /tts

**请求参数：**
```json
{
  "text": "要合成的文本",
  "text_lang": "zh",           // 语言: zh, en, ja, etc.
  "ref_audio_path": "参考音频路径",
  "prompt_text": "参考音频的文本",  // 可选
  "prompt_lang": "zh",         // 参考音频语言
  "how_to_cut": "凑四句一切",    // 切分方式
  "top_k": 5,
  "top_p": 1.0,
  "temperature": 1.0,
  "speed_factor": 1.0,         // 语速 (0.5-2.0)
  "ref_free": false
}
```

**响应：**
- 成功: 音频文件 (wav)
- 失败: JSON with error

## Windows WSL2 特殊说明

1. **安装 NVIDIA Container Toolkit:**
```powershell
# 在 WSL2 Ubuntu 中
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. **检查 GPU 可用性:**
```bash
docker run --gpus all nvidia/cuda:11.0-base nvidia-smi
```

## 训练 Lapwing 声音

### 1. 准备数据

**音频要求：**
- 格式: WAV, 44.1kHz, 16bit, 单声道
- 时长: 1-10 分钟总时长
- 质量: 清晰无噪音
- 内容: 自然对话，包含多种情感

**预处理：**
```python
# 使用 tools/slice_audio.py 切分音频
python slice_audio.py --audio_path input.wav --output_dir sliced/
```

### 2. Web UI 训练流程

1. 访问 http://localhost:9874
2. **0b-语音切分**: 上传音频 → 自动切分
3. **0c-语音识别打标**: ASR 转文字
4. **0d-语音文本校对**: 检查并修正文本
5. **1A-训练集格式化**: 生成训练数据
6. **1B-微调训练**: 训练 SoVITS 模型
7. **1C-推理**: 测试生成效果

### 3. 导出模型

训练完成后，模型保存在：
```
models/trained/
├── {experiment_name}/
│   ├── config.json
│   ├── GPT_weights/      # GPT 模型权重
│   └── SoVITS_weights/   # SoVITS 模型权重
```

## 与 Lapwing 集成

**docker-compose.yml 关键配置：**
```yaml
networks:
  lapwing-network:
    driver: bridge

services:
  gpt-sovits:
    networks:
      - lapwing-network

  lapwing:
    networks:
      - lapwing-network
    environment:
      - TTS_API_URL=http://gpt-sovits:9872
```

## 故障排查

**问题：GPU 不可用**
```bash
# 检查 WSL2 GPU 支持
nvidia-smi

# 如果失败，重启 WSL2
wsl --shutdown
# 重新打开 WSL2
```

**问题：模型加载失败**
- 确认模型文件路径正确
- 检查日志: `docker-compose logs gpt-sovits`

**问题：合成音频质量差**
- 检查参考音频是否清晰
- 调整 temperature/top_p 参数
- 确保参考音频与目标情感匹配
