---
title: 语音模式架构
created: 2026-04-10
updated: 2026-04-17
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
TTS 语音播报（5 个 Provider 可选）:
  - ElevenLabs（流式，边生成边播放）
  - OpenAI TTS
  - Google TTS
  - macOS say 命令
  - NeuTTS（自托管）
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

### 新增 TTS Provider（v0.10.0）

| Provider | 来源 |
|----------|------|
| ElevenLabs | 原有 |
| OpenAI | 原有 |
| **Google Gemini TTS** | v0.10.0 新增，通过 Gemini API |
| **xAI TTS** | v0.10.0 新增，随 xAI Responses API 升级一起引入 |

这些 provider 也可通过 Nous Tool Gateway 统一访问（无需自备 API key）。

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
