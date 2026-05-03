---
title: 语音模式架构
created: 2026-04-10
updated: 2026-05-04
type: concept
tags: [voice, stt, tts, architecture]
sources: [tools/voice_mode.py, tools/tts_tool.py, tools/transcription_tools.py, cli.py]
---

# 语音模式架构

## 概述

Hermes 支持 Push-to-talk 语音交互：用户按键录音 → STT 转文字 → LLM 处理 → TTS 语音播报回复。整个链路在 CLI 中完成，依赖可选的音频库。

## 依赖

```bash
pip install sounddevice numpy   # 或
pip install hermes-agent[voice]
```

音频库**按需懒加载**，不装也不影响文本模式。在无音频设备的环境（SSH、Docker、WSL）中自动检测并禁用。

## 流程

```text
用户按 Ctrl+B 开始录音
    ↓
sounddevice 采集音频 → WAV 临时文件
    ↓
再按 Ctrl+B 停止录音
    ↓
STT 转文字（3 个 Provider 可选）:
  - local: faster-whisper（本地，无需 API Key）
  - groq: Whisper via Groq（免费额度）
  - openai: Whisper via OpenAI
    ↓
转录文本作为用户消息发送给 LLM
    ↓
LLM 回复（自动注入简洁指令："respond concisely, 2-3 sentences max"）
    ↓
TTS 语音播报（10+ Provider，可选）:
  - Edge TTS（默认，免费，无 API key，Microsoft 神经语音）
  - ElevenLabs（流式，边生成边播放）
  - OpenAI TTS
  - MiniMax TTS（语音克隆）
  - Mistral Voxtral TTS（多语言、原生 Opus）
  - Google Gemini TTS（30 预置音色）
  - xAI TTS（Grok 音色）
  - NeuTTS（本地，自托管）
  - KittenTTS（本地，25MB 模型）
  - Piper（本地，44 语种 VITS，v2026.4.30+）
  - Custom command（自定义命令型 provider，v2026.4.30+）
```

## STT 配置

```yaml
# config.yaml
stt:
  provider: local   # local | groq | openai（优先级：local > groq > openai）
  model: base       # faster-whisper 模型大小（base ~150MB，首次自动下载）
```

```bash
# .env
GROQ_API_KEY=...              # Groq Whisper（免费）
VOICE_TOOLS_OPENAI_KEY=...    # OpenAI Whisper
```

## TTS 配置

TTS Provider 选择和语音设置通过 `tools/tts_tool.py` 管理，支持 ElevenLabs 的流式播报——LLM 生成一句就播一句，不用等完整回复。

### 新增 TTS Provider

| Provider | 来源 |
|----------|------|
| ElevenLabs | 原有 |
| OpenAI | 原有 |
| **Google Gemini TTS** | v0.10.0，通过 Gemini API |
| **xAI TTS** | v0.10.0，xAI Responses API 升级引入 |
| **KittenTTS（本地）** | v2026.4.18+，CPU 运行，无 GPU/API key，默认模型 `KittenML/kitten-tts-nano-0.8-int8`（25MB），默认声音 `Jasper` |
| **Piper（本地）** | v2026.4.30+（commit `8d302e3` #17885），OHF-Voice/piper1-gpl 神经 VITS，44 语种。`pip install piper-tts` 跨平台 CPU 运行；`pip install piper-tts[gpu]` 启用 GPU。Voice 缓存：`_piper_voice_cache: Dict[str, Any]` 按 voice id 模块级缓存（`tts_tool.py:1319`）。可参考 #8508 |

这些 provider 也可通过 Nous Tool Gateway 统一访问（无需自备 API key）。

### Custom Command Provider Registry（v2026.4.30+）

`commit 2facea7 feat(tts): add command-type provider registry under tts.providers.<name>`：

```yaml
tts:
  provider: piper-en   # 选用自定义 provider 名
  providers:
    piper-en:
      type: command
      command: "piper -m ~/model.onnx -f {output_path} < {input_path}"
      # Hermes 把文本写到 {input_path}，命令必须把音频生成到 {output_path}
```

可以接 VoxCPM、Kokoro CLI、本地 Piper 自己编译的版本等任何外部 TTS 工具。代码：`tools/tts_tool.py:290-326`。

### STT Provider 扩展（v2026.4.18+）

| Provider | 说明 |
|----------|------|
| Groq Whisper（免费） | 原有 |
| OpenAI Whisper | 原有 |
| Deepgram | 原有 |
| **xAI Grok STT** | 新增，POST `/v1/stt`，支持 ITN（Inverse Text Normalization）+ 可选 diarization |

## 语音模式特殊行为

- LLM 收到语音输入时，系统自动注入前缀指令要求简短回复
- 该前缀仅用于 API 调用，**不持久化到会话历史**（通过 `persist_user_message` 参数保存原始转录文本）
- 持续语音模式下遇到持久错误（如 429）会自动停止，防止错误 → 录音 → 错误的死循环

## 相关页面

- [[cli-architecture]] — CLI 中的语音模式集成
- [[auxiliary-client-architecture]] — STT/TTS 使用 auxiliary 模型配置

## 关键源码

| 文件 | 职责 |
|------|------|
| `tools/voice_mode.py`（812 行）| 录音、STT 调度、音频播放 |
| `tools/tts_tool.py`（983 行）| TTS Provider 路由、流式播报 |
| `tools/transcription_tools.py` | STT Provider 统一接口 |
| `cli.py` | Push-to-talk 键绑定（Ctrl+B） |
