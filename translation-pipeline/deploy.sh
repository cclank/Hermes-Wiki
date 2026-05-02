#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Hermes Wiki Translation Pipeline - Easy Setup           ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo ""

# Check if running in the correct directory
if [ ! -f "app.py" ] && [ ! -f "app_enhanced.py" ]; then
    echo -e "${RED}Error: Please run this script from the translation-pipeline directory${NC}"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to prompt for input with default
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    
    read -p "$(echo -e ${YELLOW}${prompt}${NC} [${default}]: )" input
    eval ${var_name}="${input:-$default}"
}

# Function to prompt for secret input
prompt_secret() {
    local prompt="$1"
    local var_name="$2"
    
    read -sp "$(echo -e ${YELLOW}${prompt}${NC}: )" input
    echo ""
    eval ${var_name}="${input}"
}

echo -e "${GREEN}Step 1: Checking prerequisites...${NC}"
echo ""

# Check Python
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "  ✓ Python 3 found: ${PYTHON_VERSION}"
else
    echo -e "${RED}  ✗ Python 3 not found. Please install Python 3.8+${NC}"
    exit 1
fi

# Check pip
if command_exists pip3; then
    echo -e "  ✓ pip3 found"
else
    echo -e "${RED}  ✗ pip3 not found. Please install pip${NC}"
    exit 1
fi

# Check git
if command_exists git; then
    echo -e "  ✓ git found"
else
    echo -e "${RED}  ✗ git not found. Please install git${NC}"
    exit 1
fi

# Check gcloud (optional)
if command_exists gcloud; then
    echo -e "  ✓ gcloud found (Cloud Run deployment available)"
    GCLOUD_AVAILABLE=true
else
    echo -e "  ⚠ gcloud not found (local mode only)"
    GCLOUD_AVAILABLE=false
fi

echo ""
echo -e "${GREEN}Step 2: Choose deployment mode...${NC}"
echo ""
echo "  1) Local Mode - Run translation service locally (no GCP needed)"
echo "  2) Cloud Run - Deploy to Google Cloud Run (requires GCP account)"
echo ""

read -p "$(echo -e ${YELLOW}Select mode${NC} [1]: )" MODE_CHOICE
MODE_CHOICE=${MODE_CHOICE:-1}

if [ "$MODE_CHOICE" = "1" ]; then
    DEPLOY_MODE="local"
    echo -e "${BLUE}Selected: Local Mode${NC}"
elif [ "$MODE_CHOICE" = "2" ]; then
    if [ "$GCLOUD_AVAILABLE" = false ]; then
        echo -e "${RED}Error: gcloud CLI not found. Install it or choose local mode.${NC}"
        exit 1
    fi
    DEPLOY_MODE="cloud"
    echo -e "${BLUE}Selected: Cloud Run Mode${NC}"
else
    echo -e "${RED}Invalid choice${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Step 3: Configuration...${NC}"
echo ""

# Claude API Key (required for both modes)
if [ -f ".env" ] && grep -q "CLAUDE_API_KEY" .env; then
    EXISTING_KEY=$(grep "CLAUDE_API_KEY" .env | cut -d'=' -f2)
    if [ -n "$EXISTING_KEY" ] && [ "$EXISTING_KEY" != "sk-ant-your-api-key-here" ]; then
        echo -e "  Found existing Claude API key in .env"
        read -p "$(echo -e ${YELLOW}Use existing key?${NC} [Y/n]: )" USE_EXISTING
        if [ "$USE_EXISTING" != "n" ] && [ "$USE_EXISTING" != "N" ]; then
            CLAUDE_API_KEY="$EXISTING_KEY"
        else
            prompt_secret "Enter Claude API Key (from console.anthropic.com)" CLAUDE_API_KEY
        fi
    else
        prompt_secret "Enter Claude API Key (from console.anthropic.com)" CLAUDE_API_KEY
    fi
else
    prompt_secret "Enter Claude API Key (from console.anthropic.com)" CLAUDE_API_KEY
fi

if [ -z "$CLAUDE_API_KEY" ]; then
    echo -e "${RED}Error: Claude API key is required${NC}"
    exit 1
fi

# GitHub Token (optional)
echo ""
read -p "$(echo -e ${YELLOW}Do you want to add GitHub token for private repos?${NC} [y/N]: )" ADD_GITHUB
if [ "$ADD_GITHUB" = "y" ] || [ "$ADD_GITHUB" = "Y" ]; then
    prompt_secret "Enter GitHub Personal Access Token" GITHUB_TOKEN
else
    GITHUB_TOKEN=""
fi

# Cloud-specific configuration
if [ "$DEPLOY_MODE" = "cloud" ]; then
    echo ""
    echo -e "${BLUE}Cloud Run Configuration${NC}"
    
    # Get current gcloud project
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
    
    if [ -n "$CURRENT_PROJECT" ]; then
        prompt_with_default "GCP Project ID" "$CURRENT_PROJECT" GCP_PROJECT_ID
    else
        read -p "$(echo -e ${YELLOW}GCP Project ID${NC}: )" GCP_PROJECT_ID
    fi
    
    prompt_with_default "GCP Region" "us-central1" GCP_REGION
    prompt_with_default "GCS Bucket Name" "hermes-wiki-translations" GCS_BUCKET_NAME
    
    LOCAL_MODE_VAR="false"
else
    GCP_PROJECT_ID=""
    GCP_REGION="us-central1"
    GCS_BUCKET_NAME="hermes-wiki-translations"
    LOCAL_MODE_VAR="true"
fi

# Translation settings
echo ""
echo -e "${BLUE}Translation Settings${NC}"
prompt_with_default "Max parallel workers" "5" MAX_WORKERS
prompt_with_default "Translation model" "claude-3-5-sonnet-20241022" TRANSLATION_MODEL

echo ""
echo -e "${GREEN}Step 4: Creating configuration files...${NC}"

# Create .env file
cat > .env << EOF
# Google Cloud Configuration
GCP_PROJECT_ID=${GCP_PROJECT_ID}
GCP_REGION=${GCP_REGION}
GCS_BUCKET_NAME=${GCS_BUCKET_NAME}

# Claude API Configuration
CLAUDE_API_KEY=${CLAUDE_API_KEY}

# Service Configuration
PORT=8080
FLASK_ENV=production
LOG_LEVEL=INFO

# GitHub Configuration (optional)
GITHUB_TOKEN=${GITHUB_TOKEN}

# Translation Settings
MAX_WORKERS=${MAX_WORKERS}
BATCH_SIZE=10
TRANSLATION_MODEL=${TRANSLATION_MODEL}
MAX_TOKENS=4096

# Local Mode
LOCAL_MODE=${LOCAL_MODE_VAR}
LOCAL_STORAGE_PATH=./translations
EOF

echo -e "  ✓ Created .env file"

# Install Python dependencies
echo ""
echo -e "${GREEN}Step 5: Installing Python dependencies...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "  Installing packages..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo -e "  ✓ Dependencies installed"

# Deploy based on mode
echo ""
if [ "$DEPLOY_MODE" = "local" ]; then
    echo -e "${GREEN}Step 6: Starting local service...${NC}"
    echo ""
    
    # Use enhanced app if it exists
    if [ -f "app_enhanced.py" ]; then
        APP_FILE="app_enhanced.py"
    else
        APP_FILE="app.py"
    fi
    
    echo -e "${BLUE}Starting translation service on http://localhost:8080${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    # Start the service
    python3 ${APP_FILE}
    
else
    echo -e "${GREEN}Step 6: Deploying to Cloud Run...${NC}"
    echo ""
    
    # Set gcloud project
    gcloud config set project ${GCP_PROJECT_ID}
    
    # Enable required APIs
    echo "  Enabling required APIs..."
    gcloud services enable run.googleapis.com \
        cloudbuild.googleapis.com \
        storage.googleapis.com \
        --quiet
    
    # Create GCS bucket
    echo "  Creating GCS bucket..."
    gsutil mb -p ${GCP_PROJECT_ID} -l ${GCP_REGION} gs://${GCS_BUCKET_NAME} 2>/dev/null || echo "  Bucket already exists"
    
    # Build and deploy
    echo "  Building and deploying to Cloud Run..."
    
    # Use enhanced app
    if [ -f "app_enhanced.py" ]; then
        cp app_enhanced.py app.py
    fi
    
    gcloud run deploy hermes-wiki-translator \
        --source . \
        --platform managed \
        --region ${GCP_REGION} \
        --allow-unauthenticated \
        --set-env-vars "CLAUDE_API_KEY=${CLAUDE_API_KEY},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},LOCAL_MODE=false,MAX_WORKERS=${MAX_WORKERS},TRANSLATION_MODEL=${TRANSLATION_MODEL}" \
        --memory 2Gi \
        --cpu 2 \
        --timeout 3600 \
        --max-instances 10 \
        --quiet
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe hermes-wiki-translator --region ${GCP_REGION} --format 'value(status.url)')
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Deployment Complete!                                     ║${NC}"
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo ""
    echo -e "${BLUE}Service URL:${NC} ${SERVICE_URL}"
    echo ""
    echo -e "${YELLOW}Save this URL to use with the client:${NC}"
    echo "  export TRANSLATION_SERVICE_URL=\"${SERVICE_URL}\""
    echo ""
    
    # Save URL to config
    echo "TRANSLATION_SERVICE_URL=${SERVICE_URL}" >> .env
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Setup Complete!                                          ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo ""

if [ "$DEPLOY_MODE" = "local" ]; then
    echo -e "${BLUE}Next steps:${NC}"
    echo ""
    echo "  1. Test the service:"
    echo "     curl http://localhost:8080/health"
    echo ""
    echo "  2. Translate a repository:"
    echo "     python3 client.py translate --owner scapedotes --repo Hermes-Wiki --service-url http://localhost:8080"
    echo ""
else
    echo -e "${BLUE}Next steps:${NC}"
    echo ""
    echo "  1. Test the service:"
    echo "     curl ${SERVICE_URL}/health"
    echo ""
    echo "  2. Translate a repository:"
    echo "     python3 client.py translate --owner scapedotes --repo Hermes-Wiki --service-url ${SERVICE_URL}"
    echo ""
fi

echo -e "${YELLOW}Documentation:${NC}"
echo "  - README.md - Quick start guide"
echo "  - API.md - API reference"
echo "  - DEPLOY_GUIDE.md - Detailed deployment guide"
echo ""
