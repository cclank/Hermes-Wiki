# Translation Pipeline - v2.1

Automated translation service for converting Hermes-Wiki documentation from Chinese to English.

## ✨ New in v2.1

- 🖥️ **Web UI** - Manage translations from your browser.
- ⏭️ **Skip Existing** - Automatically skips files that are already translated in storage (configurable).
- ☁️ **One-Click Deploy** - Click the button below to deploy to Google Cloud Run instantly.

## 🚀 One-Click Deploy

[![Run on Google Cloud](https://deploy.cloud.google.com/networks/cloud-run/button.svg)](https://deploy.cloud.google.com/apps?repo=https://github.com/scapedotes/Hermes-Wiki&directory=translation-pipeline)

## 📋 Features

- 🏠 **Local Mode** - Run entirely on your machine.
- 📦 **Batch Processing** - Parallel translation with progress tracking.
- 💾 **Smart Caching** - SHA256 content-based caching.
- 🔄 **GitHub Integration** - Clone and translate entire repositories.

## 🚀 Setup

1. Get Claude API Key from [Anthropic](https://console.anthropic.com).
2. Run `./deploy.sh` to configure and start.
3. Access Web UI at `http://localhost:8080`.

## 📖 Usage

### Web UI
Access the interface to:
- Translate entire repositories by owner/repo name.
- Upload individual markdown files and download the translation.
- Monitor active task progress in real-time.

### CLI
```bash
python3 client_enhanced.py translate --owner scapedotes --repo Hermes-Wiki --monitor
```

## 🔧 Configuration

In `.env`:
- `SKIP_EXISTING=true`: Enable/disable skipping of already translated files in GCS/Local storage.
- `MAX_WORKERS=5`: Control parallelism.
- `LOCAL_MODE=true`: Switch between Cloud and Local storage.
