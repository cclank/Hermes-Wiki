# Translation Pipeline API Reference

Complete API documentation for the Cloud Run Translation Service.

## Base URL

```
https://hermes-wiki-translator-{random}-{region}.a.run.app
```

## Authentication

All requests must include authentication:

```bash
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer $TOKEN" \
  https://your-service-url/endpoint
```

---

## Endpoints

### 1. Health Check

**Endpoint**: `GET /health`

**Description**: Check service health and version

**Request**:
```bash
curl https://your-service-url/health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-05-02T12:34:56.789Z"
}
```

---

### 2. Service Status

**Endpoint**: `GET /status`

**Description**: Get detailed service status and statistics

**Request**:
```bash
curl https://your-service-url/status
```

**Response** (200 OK):
```json
{
  "translations_count": 42,
  "gcs_bucket": "hermes-wiki-translations-project-id",
  "timestamp": "2026-05-02T12:34:56.789Z"
}
```

---

### 3. Synchronous Translation

**Endpoint**: `POST /translate`

**Description**: Translate markdown content synchronously

**Request**:
```bash
curl -X POST https://your-service-url/translate \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# 标题\n这是内容。",
    "filename": "example.md"
  }'
```

**Parameters**:
- `content` (string, required): Markdown content to translate
- `filename` (string, optional): Original filename for context

**Response** (200 OK):
```json
{
  "original": "# 标题\n这是内容。",
  "translated": "# Title\nThis is content.",
  "filename": "example.md"
}
```

**Error Response** (400 Bad Request):
```json
{
  "error": "Content required"
}
```

---

### 4. Asynchronous Repository Translation

**Endpoint**: `POST /translate-repo`

**Description**: Translate entire GitHub repository asynchronously

**Request**:
```bash
curl -X POST https://your-service-url/translate-repo \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "scapedotes",
    "repo": "Hermes-Wiki"
  }'
```

**Parameters**:
- `owner` (string, required): GitHub repository owner
- `repo` (string, required): GitHub repository name
- `branch` (string, optional): Branch to translate (default: main)

**Response** (202 Accepted):
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

**Usage**: Save the `task_id` and use it with the `/task-status` endpoint

---

### 5. Task Status

**Endpoint**: `GET /task-status/<task_id>`

**Description**: Get status of an async translation task

**Request**:
```bash
curl https://your-service-url/task-status/550e8400-e29b-41d4-a716-446655440000
```

**Response** (200 OK - In Progress):
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "owner": "scapedotes",
  "repo": "Hermes-Wiki",
  "created_at": "2026-05-02T12:30:00Z",
  "progress": {
    "completed": 15,
    "total": 42
  }
}
```

**Response** (200 OK - Completed):
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "owner": "scapedotes",
  "repo": "Hermes-Wiki",
  "created_at": "2026-05-02T12:30:00Z",
  "completed_at": "2026-05-02T12:45:30Z",
  "progress": {
    "completed": 42,
    "total": 42
  },
  "result": {
    "output_path": "gs://hermes-wiki-translations-xxx/scapedotes/Hermes-Wiki/",
    "files_count": 42,
    "total_size_bytes": 1048576
  }
}
```

**Status Values**:
- `pending` - Task created, waiting to start
- `processing` - Actively translating files
- `completed` - Successfully completed
- `failed` - Task failed with error

---

### 6. List Translations

**Endpoint**: `GET /list-translations`

**Description**: List all completed translations in storage

**Request**:
```bash
curl https://your-service-url/list-translations
```

**Response** (200 OK):
```json
[
  {
    "path": "scapedotes/Hermes-Wiki/README-en.md",
    "size": 12345,
    "created": "2026-05-02T12:45:30Z",
    "download_url": "https://storage.googleapis.com/..."
  },
  {
    "path": "scapedotes/Hermes-Wiki/concepts/agent-loop-en.md",
    "size": 8765,
    "created": "2026-05-02T12:45:35Z",
    "download_url": "https://storage.googleapis.com/..."
  }
]
```

---

### 7. Download Translation

**Endpoint**: `GET /download/<path>`

**Description**: Download a translated file from storage

**Request**:
```bash
curl https://your-service-url/download/scapedotes/Hermes-Wiki/README-en.md \
  -o README-en.md
```

**Response**: 
- (200 OK): File content
- (404 Not Found): File does not exist

---

## Error Handling

### Common Error Responses

**400 Bad Request**:
```json
{
  "error": "Content required"
}
```

**404 Not Found**:
```json
{
  "error": "Task not found"
}
```

**500 Internal Server Error**:
```json
{
  "error": "Internal server error. Check logs."
}
```

**503 Service Unavailable**:
```json
{
  "error": "Service temporarily unavailable. Try again later."
}
```

---

## Examples

### Example 1: Translate Single File

```bash
#!/bin/bash

SERVICE_URL="https://your-service-url"
TOKEN=$(gcloud auth print-identity-token)

# Read markdown file
CONTENT=$(cat README.md)

# Translate
RESPONSE=$(curl -s -X POST $SERVICE_URL/translate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"$CONTENT\", \"filename\": \"README.md\"}")

# Save translated content
echo "$RESPONSE" | jq -r '.translated' > README-en.md

echo "Translation saved to README-en.md"
```

### Example 2: Translate Repository

```bash
#!/bin/bash

SERVICE_URL="https://your-service-url"
TOKEN=$(gcloud auth print-identity-token)

# Start translation
RESPONSE=$(curl -s -X POST $SERVICE_URL/translate-repo \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"owner": "scapedotes", "repo": "Hermes-Wiki"}')

TASK_ID=$(echo "$RESPONSE" | jq -r '.task_id')
echo "Task started: $TASK_ID"

# Poll status
while true; do
  STATUS=$(curl -s $SERVICE_URL/task-status/$TASK_ID \
    -H "Authorization: Bearer $TOKEN")
  
  TASK_STATUS=$(echo "$STATUS" | jq -r '.status')
  COMPLETED=$(echo "$STATUS" | jq -r '.progress.completed')
  TOTAL=$(echo "$STATUS" | jq -r '.progress.total')
  
  echo "[$TASK_STATUS] $COMPLETED/$TOTAL files"
  
  if [ "$TASK_STATUS" = "completed" ] || [ "$TASK_STATUS" = "failed" ]; then
    echo "Task $TASK_STATUS"
    break
  fi
  
  sleep 5
done
```

### Example 3: Batch Download Results

```bash
#!/bin/bash

SERVICE_URL="https://your-service-url"
TOKEN=$(gcloud auth print-identity-token)

# List translations
TRANSLATIONS=$(curl -s $SERVICE_URL/list-translations \
  -H "Authorization: Bearer $TOKEN")

# Download all
echo "$TRANSLATIONS" | jq -r '.[] | .path' | while read path; do
  echo "Downloading: $path"
  curl -s "$SERVICE_URL/download/$path" \
    -H "Authorization: Bearer $TOKEN" \
    -o "${path//\//_}"
done
```

---

## Rate Limiting

- **Default**: 1000 requests per hour per service
- **Burst**: Up to 100 requests per second

Exceeding limits returns `429 Too Many Requests`

---

## Pricing

| Operation | Cost |
|-----------|------|
| API call | ~$0.00006 |
| Cloud Run compute | $0.00005 per vCPU-second |
| Storage | $0.020 per GB/month |
| Data egress | $0.12 per GB |
| Claude API | $3 per 1M input tokens, $15 per 1M output tokens |

---

## SDK Clients

### Python Client

```python
import requests

class TranslationClient:
    def __init__(self, service_url):
        self.service_url = service_url
    
    def health(self):
        return requests.get(f"{self.service_url}/health").json()
    
    def translate(self, content, filename):
        return requests.post(
            f"{self.service_url}/translate",
            json={"content": content, "filename": filename}
        ).json()

# Usage
client = TranslationClient("https://your-service-url")
result = client.translate("# 标题", "README.md")
print(result['translated'])
```

### cURL Cheatsheet

```bash
# Set variables
SERVICE_URL="https://your-service-url"
TOKEN=$(gcloud auth print-identity-token)

# Health check
curl $SERVICE_URL/health

# Translate
curl -X POST $SERVICE_URL/translate \
  -H "Content-Type: application/json" \
  -d '{"content":"# 标题"}'

# List translations
curl $SERVICE_URL/list-translations

# Download
curl $SERVICE_URL/download/path/to/file.md -o file.md
```

---

## FAQ

**Q: How long does translation take?**  
A: ~1-2 seconds per 1000 tokens. A typical 42-page wiki takes 5-15 minutes.

**Q: Can I translate multiple repos simultaneously?**  
A: Yes, each repo gets its own task_id. Service auto-scales to handle multiple requests.

**Q: What happens if translation fails?**  
A: Check logs: `gcloud run logs read hermes-wiki-translator --grep="error"`

**Q: How are costs calculated?**  
A: Cloud Run charges for vCPU-seconds + Claude API per token. See [Cost Optimization](DEPLOY_GUIDE.md#cost-optimization).

**Q: Can I use a different LLM?**  
A: Edit `app.py` to use Gemini, GPT-4, or Cohere API instead of Claude.

---

## Support

- 📖 [Deployment Guide](DEPLOY_GUIDE.md)
- 🐛 [GitHub Issues](https://github.com/scapedotes/Hermes-Wiki/issues)
- 📞 [GCP Support](https://cloud.google.com/support)
