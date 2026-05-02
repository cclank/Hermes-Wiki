# Translation Pipeline README

Cloud Run-based translation service for converting Hermes-Wiki documentation from Chinese to English using Claude API.

## Features

✨ **One-Click Deployment** - Deploy to Cloud Run with single script  
🚀 **Auto-Scaling** - 1-10 instances based on load  
💡 **Smart Translation** - Claude API with terminology consistency  
📦 **Batch Processing** - Translate multiple files concurrently  
💾 **Cloud Storage** - Automatic backup to Google Cloud Storage  
📊 **Monitoring** - Built-in logging and metrics  
🔒 **Secure** - IAM authentication and encryption  
💰 **Cost Efficient** - ~$1-2 per full repository translation  

## Quick Start

### Deploy (5 minutes)

```bash
cd Hermes-Wiki
chmod +x translation-pipeline/deploy.sh
./translation-pipeline/deploy.sh
```

### Use

```bash
# Check status
python3 translation-pipeline/client.py health

# Translate repository
python3 translation-pipeline/client.py translate \
  --owner scapedotes --repo Hermes-Wiki --monitor

# Download results
python3 translation-pipeline/client.py list
python3 translation-pipeline/client.py download translations/scapedotes/Hermes-Wiki/...
```

## Architecture

```
Your Machine
    ↓
GitHub Repo
    ↓
[Cloud Run Service] ← Claude API
    ↓
Google Cloud Storage
```

## Prerequisites

- Google Cloud Account with billing enabled
- Claude API key (from anthropic.com)
- gcloud, terraform, docker, git, python3 installed

## Files

```
translation-pipeline/
├── deploy.sh                    # One-click deployment
├── app.py                       # Flask API service
├── client.py                    # CLI client
├── Dockerfile                   # Container image
├── requirements.txt             # Python dependencies
├── cloudbuild.yaml             # CI/CD pipeline
├── terminology_map.json         # Translation terms
├── terraform/
│   ├── main.tf                 # Infrastructure
│   ├── variables.tf            # Configuration
│   └── terraform.tfvars.example # Example config
├── DEPLOY_GUIDE.md             # Full deployment guide
└── API.md                       # API reference
```

## Configuration

Edit `terraform/terraform.tfvars`:

```hcl
project_id = "your-gcp-project"
claude_api_key = "sk-..."  # From anthropic.com
region = "us-central1"
```

## Usage

### CLI Commands

```bash
# Health check
python3 client.py health

# Translate
python3 client.py translate --owner OWNER --repo REPO --monitor

# Status
python3 client.py status

# List translations
python3 client.py list

# Download
python3 client.py download MANIFEST_PATH --output file.zip

# Configuration
python3 client.py config --show
```

### API Endpoints

- `GET /health` - Service health
- `GET /status` - Service status
- `POST /translate` - Sync translation
- `POST /translate-repo` - Async translation
- `GET /list-translations` - List results
- `GET /download/<path>` - Download files

See [API.md](API.md) for full documentation.

## Costs

**Free Tier Covers**:
- ~40 full wiki translations/month (180K vCPU-seconds)
- ~5GB storage

**Typical Cost**:
- Compute: $0.05
- Storage: $0.01
- Claude API: $1-2
- **Total: ~$1-2 per translation**

## Monitoring

```bash
# View logs
gcloud run logs read hermes-wiki-translator

# Visit console
https://console.cloud.google.com/run/
```

## Troubleshooting

See [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) troubleshooting section.

## Support

- 📖 [Deployment Guide](DEPLOY_GUIDE.md)
- 📚 [API Reference](API.md)
- 🐛 [GitHub Issues](https://github.com/scapedotes/Hermes-Wiki/issues)

## License

MIT
