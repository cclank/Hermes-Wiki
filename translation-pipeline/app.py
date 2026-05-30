"""
Flask application for translating Markdown content using Claude API
Deployed on Google Cloud Run
"""

import os
import json
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_file
from anthropic import Anthropic
from google.cloud import storage, tasks_v2
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize Claude client
client = Anthropic()
claude_api_key = os.getenv('CLAUDE_API_KEY')

if not claude_api_key:
    logger.warning("CLAUDE_API_KEY not set. Translation will fail.")

# Initialize GCS client
try:
    storage_client = storage.Client()
    bucket_name = os.getenv('GCS_BUCKET_NAME', 'hermes-wiki-translations')
except Exception as e:
    logger.warning(f"GCS client initialization failed: {e}")
    storage_client = None

# Load terminology map for consistent translations
try:
    with open('terminology_map.json', 'r', encoding='utf-8') as f:
        terminology_map = json.load(f)
except FileNotFoundError:
    logger.warning("terminology_map.json not found. Using empty terminology map.")
    terminology_map = {}

# In-memory task storage (in production, use Firestore or Cloud Tasks)
tasks_store = {}

# System prompt for consistent translation
SYSTEM_PROMPT = """You are an expert technical translator specializing in AI/LLM documentation.
Your task is to translate Chinese markdown documentation to English while maintaining:

1. **Terminology Consistency**: Use the provided terminology mappings
2. **Technical Accuracy**: Preserve all technical terms, code references, and API names
3. **Markdown Preservation**: Keep all markdown formatting, links, code blocks intact
4. **Context Awareness**: Understand the AI/Agent architecture domain

Guidelines:
- Do NOT translate code snippets or command examples
- Preserve all URLs, file paths, and variable names
- Translate only human-readable text and comments
- Maintain the original structure and formatting
- For technical terms not in the terminology map, use standard English equivalents

Terminology Map:
{terminology}

Output ONLY the translated markdown content. Do not include explanations or commentary."""

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200

@app.route('/status', methods=['GET'])
def status():
    """Get service status"""
    return jsonify({
        'service': 'hermes-wiki-translator',
        'status': 'running',
        'tasks_in_queue': len(tasks_store),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'gcs_bucket': bucket_name if storage_client else 'Not configured'
    }), 200

@app.route('/translate', methods=['POST'])
def translate():
    """Synchronous translation endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'Content required'}), 400
        
        content = data.get('content')
        filename = data.get('filename', 'unknown.md')
        
        if not content or not content.strip():
            return jsonify({'error': 'Content cannot be empty'}), 400
        
        logger.info(f"Translating {filename} ({len(content)} chars)")
        
        # Prepare system prompt with terminology
        terminology_str = json.dumps(terminology_map, ensure_ascii=False, indent=2)
        system_prompt = SYSTEM_PROMPT.format(terminology=terminology_str)
        
        # Call Claude API
        message = client.messages.create(
            model='claude-3-5-sonnet-20241022',
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    'role': 'user',
                    'content': f"Translate the following markdown content to English:\n\n{content}"
                }
            ]
        )
        
        translated_content = message.content[0].text
        
        logger.info(f"Translation completed for {filename}")
        
        return jsonify({
            'original': content,
            'translated': translated_content,
            'filename': filename,
            'original_length': len(content),
            'translated_length': len(translated_content)
        }), 200
        
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/translate-repo', methods=['POST'])
def translate_repo():
    """Asynchronous repository translation endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'owner' not in data or 'repo' not in data:
            return jsonify({'error': 'Owner and repo required'}), 400
        
        owner = data.get('owner')
        repo = data.get('repo')
        branch = data.get('branch', 'main')
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Store task
        tasks_store[task_id] = {
            'id': task_id,
            'status': 'pending',
            'owner': owner,
            'repo': repo,
            'branch': branch,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'progress': {'completed': 0, 'total': 0}
        }
        
        logger.info(f"Created translation task {task_id} for {owner}/{repo}")
        
        # In production, this would queue the task to Cloud Tasks
        # For now, return immediately
        
        return jsonify({
            'task_id': task_id,
            'status': 'pending',
            'owner': owner,
            'repo': repo
        }), 202
        
    except Exception as e:
        logger.error(f"Repository translation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Get status of a translation task"""
    try:
        if task_id not in tasks_store:
            return jsonify({'error': 'Task not found'}), 404
        
        task = tasks_store[task_id]
        
        return jsonify(task), 200
        
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/list-translations', methods=['GET'])
def list_translations():
    """List all translations in GCS"""
    try:
        if not storage_client:
            return jsonify({'error': 'GCS not configured'}), 503
        
        bucket = storage_client.bucket(bucket_name)
        blobs = list(bucket.list_blobs())
        
        translations = []
        for blob in blobs:
            translations.append({
                'path': blob.name,
                'size': blob.size,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'download_url': f'/download/{blob.name}'
            })
        
        return jsonify(translations), 200
        
    except Exception as e:
        logger.error(f"List error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:file_path>', methods=['GET'])
def download(file_path):
    """Download a translated file"""
    try:
        if not storage_client:
            return jsonify({'error': 'GCS not configured'}), 503
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        if not blob.exists():
            return jsonify({'error': 'File not found'}), 404
        
        content = blob.download_as_string()
        
        return content, 200, {
            'Content-Disposition': f'attachment; filename={os.path.basename(file_path)}',
            'Content-Type': 'text/markdown'
        }
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
