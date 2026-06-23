# Complete Deployment Guide

Step-by-step guide to deploy the Hermes Wiki translation pipeline to Google Cloud Run.

## Prerequisites

### Required Software

- **gcloud CLI** - Google Cloud command-line tool
- **Terraform** - Infrastructure as Code tool
- **Docker** - Container runtime
- **git** - Version control
- **Python 3.8+** - Python runtime
- **curl** - HTTP client

### Accounts & Keys

1. **Google Cloud Account** with billing enabled
   - Create: https://console.cloud.google.com
   - Enable billing: Cloud Console → Billing

2. **Claude API Key** from Anthropic
   - Get key: https://console.anthropic.com
   - Format: `sk-ant-...`

3. **GitHub Access** (optional, for repo translation)
   - Personal access token: https://github.com/settings/tokens

---

## Installation

### macOS / Linux

```bash
# 1. Install gcloud
brew install google-cloud-sdk

# 2. Install Terraform
brew install terraform

# 3. Install Docker Desktop
brew install --cask docker

# 4. Install other tools
brew install git python3 curl
```

### Windows

```bash
# 1. Install gcloud
# Download from: https://cloud.google.com/sdk/docs/install-sdk#windows
# Or use scoop: scoop install gcloud

# 2. Install Terraform
choco install terraform
# Or download: https://www.terraform.io/downloads

# 3. Install Docker Desktop
# Download from: https://docs.docker.com/desktop/install/windows-install/

# 4. Install git, Python, curl
choco install git python curl
```

---

## Configuration

### Step 1: Authenticate with GCP

```bash
# Initialize gcloud
gcloud init

# You'll be prompted to:
# 1. Sign in with Google account
# 2. Select/create a project
# 3. Set default region

# Verify authentication
gcloud auth list
gcloud config list
```

### Step 2: Set Project Variables

```bash
# Set your project ID
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"  # or your preferred region

# Verify
gcloud config set project $GCP_PROJECT_ID
echo "Project: $(gcloud config get-value project)"
echo "Region: $GCP_REGION"
```

### Step 3: Enable Required APIs

```bash
# Enable Cloud Run
gcloud services enable run.googleapis.com

# Enable Cloud Build
gcloud services enable cloudbuild.googleapis.com

# Enable Container Registry
gcloud services enable containerregistry.googleapis.com

# Enable Cloud Storage
gcloud services enable storage-api.googleapis.com

# Enable Cloud Tasks (for async processing)
gcloud services enable cloudtasks.googleapis.com

# Enable Cloud Logging
gcloud services enable logging.googleapis.com

# Verify all enabled
gcloud services list --enabled | grep -E "run|build|storage"
```

---

## Deployment

### Option A: Automated Deployment (Recommended)

```bash
cd translation-pipeline

# Make script executable
chmod +x deploy.sh

# Run interactive deployment
./deploy.sh
```

The script will guide you through:
1. ✅ Prerequisites check
2. ✅ GCP authentication
3. ✅ Configuration setup
4. ✅ Terraform provisioning
5. ✅ Docker build & push
6. ✅ Cloud Run deployment
7. ✅ Service testing

### Option B: Manual Step-by-Step

#### Step 1: Create Configuration

```bash
cd translation-pipeline/terraform

# Copy example config
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
nano terraform.tfvars  # or use your editor
```

Edit `terraform.tfvars`:
```hcl
project_id       = "your-gcp-project-id"
claude_api_key   = "sk-ant-your-api-key"
region           = "us-central1"
service_name     = "hermes-wiki-translator"
memory           = 1024
cpu              = "1"
max_instances    = 10
min_instances    = 1
timeout          = 3600
```

#### Step 2: Terraform Init & Plan

```bash
# Initialize Terraform
terraform init

# Review what will be created
terraform plan

# Should show: Plan: X to add, 0 to change, 0 to destroy
```

#### Step 3: Create Infrastructure

```bash
# Apply configuration
terraform apply

# Review the plan and type "yes" to confirm
# Takes 2-3 minutes

# Save outputs
terraform output > deployment-info.txt
```

#### Step 4: Build & Push Docker Image

```bash
cd ..  # Back to translation-pipeline

# Set variables
export GCP_PROJECT_ID=$(gcloud config get-value project)
export IMAGE_NAME="gcr.io/$GCP_PROJECT_ID/hermes-wiki-translator:latest"

# Build image
docker build -t $IMAGE_NAME .

# Authenticate Docker with GCP
gcloud auth configure-docker

# Push to Container Registry
docker push $IMAGE_NAME

# Verify
gcloud container images list | grep hermes-wiki-translator
```

#### Step 5: Deploy to Cloud Run

```bash
# Get values from Terraform
SERVICE_NAME=$(terraform output -raw service_name)
REGION=$(terraform output -raw region)

# Deploy
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --region $REGION \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10 \
  --min-instances 1 \
  --timeout 3600 \
  --set-env-vars CLAUDE_API_KEY=$(cat terraform/terraform.tfvars | grep claude_api_key | cut -d'"' -f2) \
  --allow-unauthenticated
```

#### Step 6: Get Service URL

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe hermes-wiki-translator \
  --region $REGION \
  --format='value(status.url)')

echo "Service URL: $SERVICE_URL"
echo "Save this for later use!"
```

---

## Verification

### Test Deployment

```bash
# 1. Test health endpoint
curl $SERVICE_URL/health

# Expected output:
# {"status": "healthy", "version": "1.0.0", ...}

# 2. Test with authentication
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer $TOKEN" $SERVICE_URL/status

# 3. Test translation
curl -X POST $SERVICE_URL/translate \
  -H "Content-Type: application/json" \
  -d '{"content": "# 标题\n这是测试", "filename": "test.md"}'
```

### View Logs

```bash
# Tail service logs
gcloud run logs read hermes-wiki-translator --limit 50

# Or use Cloud Console
# https://console.cloud.google.com/run/
```

---

## Using the Service

### Python CLI Client

```bash
# Check service health
python3 client.py health --service-url $SERVICE_URL

# Translate a single file
python3 client.py translate \
  --file README.md \
  --service-url $SERVICE_URL

# Translate entire repository
python3 client.py translate \
  --owner scapedotes \
  --repo Hermes-Wiki \
  --monitor \
  --service-url $SERVICE_URL

# List translations
python3 client.py list --service-url $SERVICE_URL

# Download results
python3 client.py download \
  --path translations/scapedotes/Hermes-Wiki/ \
  --output results.zip \
  --service-url $SERVICE_URL
```

### Direct API Calls

```bash
SERVICE_URL="your-service-url"
TOKEN=$(gcloud auth print-identity-token)

# Translate repository
curl -X POST $SERVICE_URL/translate-repo \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "scapedotes",
    "repo": "Hermes-Wiki"
  }'

# Response includes task_id - save it!
# {"task_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued"}

# Check status
TASK_ID="550e8400-e29b-41d4-a716-446655440000"
curl $SERVICE_URL/task-status/$TASK_ID \
  -H "Authorization: Bearer $TOKEN"

# Download results
curl $SERVICE_URL/list-translations \
  -H "Authorization: Bearer $TOKEN"
```

---

## Monitoring & Costs

### Monitor Usage

```bash
# View current logs
gcloud run logs read hermes-wiki-translator --limit 100

# View service details
gcloud run services describe hermes-wiki-translator

# View metrics
# Cloud Console → Cloud Run → hermes-wiki-translator → Metrics
```

### Cost Estimation

| Component | Monthly Cost |
|-----------|-------------|
| Cloud Run (10 daily translations) | $0.50 |
| Cloud Storage (500MB) | $0.10 |
| Cloud Build (2 builds) | $0.50 |
| Claude API (42 translations) | $50-100 |
| **Total** | **$51-101** |

### Cost Optimization

```bash
# Reduce max instances
gcloud run services update hermes-wiki-translator \
  --max-instances 5

# Enable autoscaling
gcloud run services update hermes-wiki-translator \
  --min-instances 0 \
  --max-instances 10

# View current costs
# Cloud Console → Billing → Reports
```

---

## Troubleshooting

### Common Issues

#### Issue: "Permission denied" error

```bash
# Solution: Add IAM roles
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member=serviceAccount:hermes-wiki-translator@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member=serviceAccount:hermes-wiki-translator@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.admin
```

#### Issue: "Image not found" error

```bash
# Solution: Push image to registry
export GCP_PROJECT_ID=$(gcloud config get-value project)
export IMAGE_NAME="gcr.io/$GCP_PROJECT_ID/hermes-wiki-translator:latest"
docker build -t $IMAGE_NAME .
gcloud auth configure-docker
docker push $IMAGE_NAME
```

#### Issue: "API quota exceeded"

```bash
# Solution: Check quota usage
gcloud compute project-info describe --project=$GCP_PROJECT_ID | grep -A5 QUOTA

# Request quota increase through Cloud Console
# Cloud Console → IAM & Admin → Quotas
```

#### Issue: Translation is slow

```bash
# Solution: Increase memory/CPU
gcloud run services update hermes-wiki-translator \
  --memory 2Gi \
  --cpu 2

# Or check Claude API rate limits
# https://console.anthropic.com/account/billing/limits
```

#### Issue: Service keeps restarting

```bash
# Check logs
gcloud run logs read hermes-wiki-translator --limit 100

# Look for errors in output
# Common: Out of memory, API key invalid, network issues

# Fix API key issue
gcloud run services update hermes-wiki-translator \
  --set-env-vars CLAUDE_API_KEY="your-new-key"
```

---

## Cleanup & Deletion

### Remove Service

```bash
# Delete Cloud Run service
gcloud run services delete hermes-wiki-translator

# Delete infrastructure (Terraform)
cd terraform
terraform destroy

# Clear environment variables
unset GCP_PROJECT_ID GCP_REGION SERVICE_URL
```

### Free Up Storage

```bash
# List storage buckets
gsutil ls

# Delete specific bucket (with all contents)
gsutil -m rm -r gs://hermes-wiki-translations-xxxx
```

---

## Advanced Configuration

### Enable Authentication

```bash
# Require authentication for all requests
gcloud run services update hermes-wiki-translator \
  --no-allow-unauthenticated

# Only authenticated users can access
# Clients must include Bearer token
```

### Setup Custom Domain

```bash
# Map custom domain
gcloud beta run domain-mappings create \
  --service hermes-wiki-translator \
  --domain translate.example.com

# Verify DNS records
nslookup translate.example.com
```

### Enable VPC Connector

```bash
# Create VPC connector (for accessing private resources)
gcloud compute networks vpc-access connectors create hermes-connector \
  --region $GCP_REGION \
  --range 10.8.0.0/28

# Update service to use connector
gcloud run services update hermes-wiki-translator \
  --vpc-connector hermes-connector
```

---

## Support & Resources

- 📚 [API Reference](API.md)
- 🚀 [Quick Start](README.md)
- 🐛 [GitHub Issues](https://github.com/scapedotes/Hermes-Wiki/issues)
- ☁️ [GCP Documentation](https://cloud.google.com/run/docs)
- 🤖 [Claude API Docs](https://docs.anthropic.com)
