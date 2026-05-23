---
title: 语音模式架构
created: 2026-04-10
updated: 2026-05-14
type: concept
tags: [voice, stt, tts, architecture, piper]
sources: [tools/voice_mode.py, tools/tts_tool.py, tools/transcription_tools.py, cli.py]
---

> **v2026.5.7 增量**：
>
> - **xAI Custom Voices —— 语音克隆**（@alt-glitch, #18776）。源码 `tools/tts_tool.py:861` `_generate_xai_tts` + line 875 `voice_id = str(xai_config.get("voice_id", DEFAULT_XAI_VOICE_ID))`，与 ElevenLabs / MiniMax / Mistral TTS 并列。
> - **`video_analyze` 工具**（@alt-glitch, #19301）。Gemini 等多模态 model 上原生视频理解。源码 `tools/vision_tools.py:915` `async def video_analyze_tool`，name 在 line 1123，与 line 759 `vision_analyze` 平级。
> - **TUI voice push-to-talk parity 恢复**（salvage #16189，#20897）。

# 语音模式架构

## 概述

Hermes 支持 Push-to-talk 语音交互：用户按键录音 → STT 转文字 → LLM 处理 → TTS 语音播报回复。整个链路在 CLI 中完成，依赖可选的音频库。**v2026.5.7+ 还支持视频理解**（`video_analyze`）和**语音克隆**（xAI Custom Voices）。

## 依赖

```bash
pip install sounddevice numpy   # 或
pip install hermes-agent[voice]
```

音频库**按需懒加载**，不装也不影响文本模式。在无音频设备的环境（SSH、Docker、WSL）中自动检测并禁用。

> WSL 改进（v0.12.0，081f936）：`sd.query_devices()` 返回空列表但 `PULSE_SERVER` env 已设置时，仍判定为有音频可用（之前直接禁用，跑 WSL + PulseAudio 的用户没法用语音）。

## 流程

```text
用户按 Ctrl+B 开始录音
    ↓
sounddevice 采集音频 → WAV 临时文件
    ↓
再按 Ctrl+B 停止录音
    ↓
STT 转文字（6 个 Provider 可选，源：tools/transcription_tools.py）:
  - local: faster-whisper（本地，无需 API Key，默认）
  - local_command: 任意本地 STT 二进制
  - groq: Whisper via Groq（免费额度）
  - openai: Whisper via OpenAI
  - mistral: Voxtral Transcribe API
  - xai: xAI Grok STT（ITN + diarization + 21 语言）
    ↓
转录文本作为用户消息发送给 LLM
    ↓
LLM 回复（自动注入简洁指令："respond concisely, 2-3 sentences max"）
    ↓
TTS 语音播报（10 个内置 Provider + 任意命令型自定义 provider）:
  - Edge TTS（默认、免费、无需 API key）
  - ElevenLabs（流式，边生成边播放）
  - OpenAI TTS
  - MiniMax TTS（含 voice cloning）
  - Mistral Voxtral TTS（多语种，原生 Opus）
  - Google Gemini TTS（30 prebuilt voices）
  - xAI TTS（Grok voices）
  - NeuTTS（本地）
  - KittenTTS（本地 25MB）
  - Piper（本地，OHF-Voice/piper1-gpl 神经 VITS，44 语种）—— v0.12.0+
  - 任意 `tts.providers.<name>` 命令型自定义 provider（v0.12.0+）
```

## STT 配置

```yaml
# config.yaml
stt:
  provider: local   # local | local_command | groq | openai | mistral | xai
                    # 自动模式优先级：local > groq > openai > mistral > xai
  model: base       # faster-whisper 模型大小（base ~150MB，首次自动下载）
```

```bash
# .env
GROQ_API_KEY=...              # Groq Whisper（免费）
VOICE_TOOLS_OPENAI_KEY=...    # OpenAI Whisper
MISTRAL_API_KEY=...           # Mistral Voxtral
XAI_API_KEY=...               # xAI Grok STT
```

## TTS 配置

TTS Provider 选择和语音设置通过 `tools/tts_tool.py` 管理，支持 ElevenLabs 的流式播报——LLM 生成一句就播一句，不用等完整回复。

### TTS Provider 演进

| Provider | 来源 |
|----------|------|
| ElevenLabs | 原有 |
| OpenAI | 原有 |
| **Google Gemini TTS** | v0.10.0 新增，通过 Gemini API |
| **xAI TTS** | v0.10.0 随 xAI Responses API 升级引入 |
| **KittenTTS（本地）** | v2026.4.18+ 引入，本地 CPU 运行，无需 GPU 和 API key，默认模型 `KittenML/kitten-tts-nano-0.8-int8`（25MB），默认声音 `Jasper`，其他声音由 KittenTTS 包提供（25-80MB 模型范围） |
| **Piper（本地）** | v0.12.0 新增（`#17885`），作为 native local TTS provider 通过 `tts.providers.<name>` registry 注册，closes #8508 |
| **xAI Custom Voices** | v0.13.0 新增（`#18776`，@alt-glitch），**voice cloning** 支持 |

这些 provider 也可通过 Nous Tool Gateway 统一访问（无需自备 API key）。

### TTS Provider Registry（v0.12.0+）

`#17843` 把 TTS provider 改成 *pluggable* —— `tts.providers.<name>` 注册表，第三方可以新增 provider 而不改 hermes 核心。Piper 是第一个 native local provider 走这套机制。

### STT Provider 扩展（v2026.4.18+）

| Provider | 说明 |
|----------|------|
| local（faster-whisper） | 原有，默认；模型自动下载到 `~/.hermes/cache/` |
| local_command | 调用任意本地 STT 二进制（v0.12.0 时已有） |
| Groq Whisper（免费） | 原有 |
| OpenAI Whisper | 原有 |
| **Mistral Voxtral** | v0.12.0 阶段已并入 |
| **xAI Grok STT** | v2026.4.18 引入，支持 ITN、可选 diarization、21 语言 |

> 注：源码 `tools/transcription_tools.py` 模块 docstring 自述 "six providers"，与 `_get_provider()` 的分支一致（local / local_command / groq / openai / mistral / xai）。

## 语音模式特殊行为

- LLM 收到语音输入时，系统自动注入前缀指令要求简短回复
- 该前缀仅用于 API 调用，**不持久化到会话历史**（通过 `persist_user_message` 参数保存原始转录文本）
- 持续语音模式下遇到持久错误（如 429）会自动停止，防止错误 → 录音 → 错误的死循环

## TUI Voice Mode（v2026.4.30+）

VAD 循环 + TTS + crash 取证全部在 Ink-based TUI 里实现 parity（之前只有 classic CLI 支持 push-to-talk）。`hermes --tui` 下 Ctrl+B 行为与 classic CLI 一致。Vision cache 改用 `HERMES_HOME` 而非 cwd（PR #17719），避免在不同项目目录下重复下载模型。

## 相关页面

- [[cli-architecture]] — CLI 中的语音模式集成
- [[auxiliary-client-architecture]] — STT/TTS 使用 auxiliary 模型配置

## 关键源码

| 文件 | 职责 |
|------|------|
| `tools/voice_mode.py`（1018 行）| 录音、STT 调度、音频播放 |
| `tools/tts_tool.py`（2225 行）| TTS Provider 路由（10 内置 + 命令型自定义）、流式播报 |
| `tools/transcription_tools.py`（921 行）| STT Provider 统一接口 |
| `cli.py` | Push-to-talk 键绑定（Ctrl+B） |
