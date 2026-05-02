# Translation Pipeline - Enhanced Version

Automated translation service for converting Hermes-Wiki documentation from Chinese to English using Claude API. Now with **local mode** support - no Google Cloud account needed!

## ✨ What's New (v2.0)

- 🏠 **Local Mode** - Run entirely on your machine without GCP
- 🚀 **One-Command Setup** - Interactive deployment script
- 📦 **Batch Processing** - Parallel translation with progress tracking
- 💾 **Smart Caching** - Avoid re-translating identical content
- 🔄 **GitHub Integration** - Clone and translate entire repositories
- 📊 **Real-time Progress** - Live progress bars and status updates
- 🎯 **Enhanced CLI** - Beautiful, user-friendly command-line interface
- 🔧 **Auto-configuration** - Detects service URL from environment

## 🚀 Quick Start (3 Steps)

### 1. Get Claude API Key

Visit [console.anthropic.com](https://console.anthropic.com) and create an API key.

### 2. Run Setup

```bash
cd translation-pipeline
./deploy.sh
```

The script will:
- Check prerequisites
- Ask for your Claude API key
- Let you choose local or cloud mode
- Install dependencies
- Start the service (local mode) or deploy to Cloud Run

### 3. Translate

```bash
# Translate the Hermes Wiki
python3 client_enhanced.py translate --owner scapedotes --repo Hermes-Wiki --monitor

# Or use the quick start script
python3 quick_start.py
```

## 📋 Features

### Local Mode (No GCP Required)
- ✅ Run on your laptop/desktop
- ✅ No cloud costs
- ✅ Full privacy - data stays local
- ✅ Perfect for testing and development

### Cloud Run Mode (Production)
- ✅ Auto-scaling (0-10 instances)
- ✅ High availability
- ✅ Automatic backups to GCS
- ✅ Pay only for what you use (~$1-2 per repo)

### Translation Features
- ✅ Preserves markdown formatting
- ✅ Maintains code blocks and links
- ✅ Consistent terminology mapping
- ✅ Parallel file processing
- ✅ Progress tracking
- ✅ Error recovery
- ✅ Translation caching

## 📖 Usage

### Health Check

```bash
python3 client_enhanced.py health
```

### Translate Single File

```bash
python3 client_enhanced.py translate --file README.md --output README-en.md
```

### Translate Repository

```bash
# With progress monitoring
python3 client_enhanced.py translate \
  --owner scapedotes \
  --repo Hermes-Wiki \
  --monitor

# Specific branch
python3 client_enhanced.py translate \
  --owner scapedotes \
  --repo Hermes-Wiki \
  --branch develop \
  --monitor
```

### Check Task Status

```bash
python3 client_enhanced.py task-status <task-id>
```

### List Translations

```bash
python3 client_enhanced.py list
```

### Download Translation

```bash
python3 client_enhanced.py download \
  --path translations/scapedotes/Hermes-Wiki/20260502_123456/README.md \
  --output README-en.md
```

## 🔧 Configuration

### Environment Variables

The `.env` file is created automatically by `deploy.sh`. You can edit it manually:

```bash
# Claude API (required)
CLAUDE_API_KEY=sk-ant-your-key-here

# Mode
LOCAL_MODE=true  # or false for Cloud Run

# Local storage (local mode only)
LOCAL_STORAGE_PATH=./translations

# GCP settings (cloud mode only)
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1
GCS_BUCKET_NAME=hermes-wiki-translations

# Translation settings
MAX_WORKERS=5
TRANSLATION_MODEL=claude-3-5-sonnet-20241022
MAX_TOKENS=4096

# GitHub (optional, for private repos)
GITHUB_TOKEN=ghp_your-token-here
```

### Service URL

The client auto-detects the service URL:
1. From `TRANSLATION_SERVICE_URL` in `.env`
2. Falls back to `http://localhost:8080`

Or specify manually:
```bash
python3 client_enhanced.py --service-url https://your-service.run.app health
```

## 🏗️ Architecture

### Local Mode
```
Your Machine
    ↓
[Flask Service] ← Claude API
    ↓
Local Filesystem (./translations/)
```

### Cloud Run Mode
```
Your Machine
    ↓
[Cloud Run Service] ← Claude API
    ↓
Google Cloud Storage
```

## 📁 File Structure

```
translation-pipeline/
├── deploy.sh                    # 🆕 One-click deployment script
├── app_enhanced.py              # 🆕 Enhanced Flask service with local mode
├── client_enhanced.py           # 🆕 Enhanced CLI client
├── quick_start.py               # 🆕 Quick start helper
├── terminology_map.json         # 🆕 Translation terminology
├── .env.example                 # 🆕 Environment template
├── requirements.txt             # Updated dependencies
├── Dockerfile                   # Updated container image
├── cloudbuild.yaml             # CI/CD pipeline
├── terraform/
│   ├── main.tf                 # 🆕 Complete infrastructure code
│   ├── variables.tf            # 🆕 Terraform variables
│   └── terraform.tfvars.example # Configuration template
├── README.md                    # This file
├── API.md                       # API reference
└── DEPLOY_GUIDE.md             # Detailed deployment guide
```

## 🎯 Examples

### Example 1: Quick Local Translation

```bash
# Setup (first time only)
./deploy.sh
# Choose option 1 (Local Mode)
# Enter your Claude API key

# Translate
python3 quick_start.py
```

### Example 2: Cloud Deployment

```bash
# Setup (first time only)
./deploy.sh
# Choose option 2 (Cloud Run)
# Enter GCP project ID and Claude API key

# The script deploys and gives you a URL
# Use that URL with the client:
export TRANSLATION_SERVICE_URL="https://your-service.run.app"

# Translate
python3 client_enhanced.py translate --owner scapedotes --repo Hermes-Wiki --monitor
```

### Example 3: Batch Translation

```bash
# Translate multiple repos
for repo in Hermes-Wiki Hermes-Docs Hermes-Examples; do
  python3 client_enhanced.py translate \
    --owner scapedotes \
    --repo $repo \
    --monitor
done
```

## 💰 Costs

### Local Mode
- **Compute**: Free (uses your machine)
- **Storage**: Free (local filesystem)
- **Claude API**: ~$1-2 per repository
- **Total**: ~$1-2 per repository

### Cloud Run Mode
- **Compute**: ~$0.05 per translation (free tier: 180K vCPU-seconds/month)
- **Storage**: ~$0.01 per month (free tier: 5GB)
- **Claude API**: ~$1-2 per repository
- **Total**: ~$1-2 per repository (mostly API costs)

## 🔍 Monitoring

### Local Mode
```bash
# Check service status
python3 client_enhanced.py status

# View logs
tail -f app.log  # if you redirect output
```

### Cloud Run Mode
```bash
# View logs
gcloud run logs read hermes-wiki-translator --region us-central1

# Visit console
open https://console.cloud.google.com/run/
```

## 🐛 Troubleshooting

### Service won't start (local mode)
```bash
# Check if port 8080 is in use
lsof -i :8080

# Use a different port
PORT=8081 python3 app_enhanced.py
```

### Translation fails
```bash
# Check Claude API key
python3 -c "import os; from anthropic import Anthropic; print(Anthropic(api_key=os.getenv('CLAUDE_API_KEY')).messages.create(model='claude-3-5-sonnet-20241022', max_tokens=10, messages=[{'role':'user','content':'hi'}]))"

# Check service health
python3 client_enhanced.py health
```

### Git clone fails
```bash
# For private repos, set GitHub token
export GITHUB_TOKEN=ghp_your_token_here

# Or add to .env file
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
```

### Out of memory (local mode)
```bash
# Reduce parallel workers
# Edit .env:
MAX_WORKERS=2
```

## 📚 Documentation

- **[API.md](API.md)** - Complete API reference
- **[DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)** - Detailed deployment guide
- **[terminology_map.json](terminology_map.json)** - Translation terminology

## 🆘 Support

- 📖 Read the [Deployment Guide](DEPLOY_GUIDE.md)
- 🐛 [Report Issues](https://github.com/scapedotes/Hermes-Wiki/issues)
- 💬 Ask questions in GitHub Discussions

## 🎉 What's Improved

### Before (v1.0)
- ❌ Cloud Run only (GCP account required)
- ❌ Manual configuration
- ❌ No progress tracking
- ❌ No caching
- ❌ Incomplete implementation
- ❌ Complex setup

### After (v2.0)
- ✅ Local mode (no GCP needed)
- ✅ One-command setup
- ✅ Real-time progress bars
- ✅ Smart caching
- ✅ Complete GitHub integration
- ✅ Beautiful CLI
- ✅ Auto-configuration

## 📝 License

MIT

---

**Ready to translate?** Run `./deploy.sh` to get started! 🚀
