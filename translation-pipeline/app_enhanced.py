#!/usr/bin/env python3
"""
Enhanced translation service with local mode, batch processing, and GitHub integration
"""

import os
import json
import uuid
import shutil
import tempfile
import subprocess
from datetime import datetime
from functools import wraps
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

from flask import Flask, request, jsonify, send_file
from anthropic import Anthropic
from google.cloud import storage
import logging

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration
LOCAL_MODE = os.getenv('LOCAL_MODE', 'false').lower() == 'true'
LOCAL_STORAGE_PATH = Path(os.getenv('LOCAL_STORAGE_PATH', './translations'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '10'))
TRANSLATION_MODEL = os.getenv('TRANSLATION_MODEL', 'claude-3-5-sonnet-20241022')
MAX_TOKENS = int(os.getenv('MAX_TOKENS', '4096'))

# Initialize Claude client
claude_api_key = os.getenv('CLAUDE_API_KEY')
if not claude_api_key:
    logger.warning("CLAUDE_API_KEY not set. Translation will fail.")
    client = None
else:
    client = Anthropic(api_key=claude_api_key)

# Initialize GCS client (only if not in local mode)
storage_client = None
bucket_name = os.getenv('GCS_BUCKET_NAME', 'hermes-wiki-translations')

if not LOCAL_MODE:
    try:
        storage_client = storage.Client()
        logger.info(f"GCS client initialized for bucket: {bucket_name}")
    except Exception as e:
        logger.warning(f"GCS client initialization failed: {e}. Falling back to local mode.")
        LOCAL_MODE = True

# Create local storage directory if in local mode
if LOCAL_MODE:
    LOCAL_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    logger.info(f"Running in LOCAL MODE. Storage path: {LOCAL_STORAGE_PATH}")

# Load terminology map
try:
    terminology_path = Path(__file__).parent / 'terminology_map.json'
    with open(terminology_path, 'r', encoding='utf-8') as f:
        terminology_map = json.load(f)
    logger.info(f"Loaded {len(terminology_map)} terminology mappings")
except FileNotFoundError:
    logger.warning("terminology_map.json not found. Using empty terminology map.")
    terminology_map = {}

# In-memory task storage (in production, use Redis or Firestore)
tasks_store = {}

# Translation cache to avoid re-translating identical content
translation_cache = {}

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


def get_cache_key(content: str) -> str:
    """Generate cache key for content"""
    import hashlib
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def translate_content(content: str, filename: str = 'document.md') -> Tuple[str, bool]:
    """
    Translate markdown content using Claude API
    Returns: (translated_content, from_cache)
    """
    if not client:
        raise ValueError("Claude API client not initialized")
    
    # Check cache
    cache_key = get_cache_key(content)
    if cache_key in translation_cache:
        logger.info(f"Cache hit for {filename}")
        return translation_cache[cache_key], True
    
    # Prepare system prompt with terminology
    terminology_str = json.dumps(terminology_map, ensure_ascii=False, indent=2)
    system_prompt = SYSTEM_PROMPT.format(terminology=terminology_str)
    
    # Call Claude API
    try:
        message = client.messages.create(
            model=TRANSLATION_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    'role': 'user',
                    'content': f"Translate the following markdown content to English:\n\n{content}"
                }
            ]
        )
        
        translated_content = message.content[0].text
        
        # Cache the result
        translation_cache[cache_key] = translated_content
        
        return translated_content, False
        
    except Exception as e:
        logger.error(f"Translation error for {filename}: {str(e)}")
        raise


def clone_github_repo(owner: str, repo: str, branch: str = 'main') -> Path:
    """Clone a GitHub repository to a temporary directory"""
    temp_dir = Path(tempfile.mkdtemp(prefix='hermes-wiki-'))
    
    github_token = os.getenv('GITHUB_TOKEN')
    if github_token:
        repo_url = f"https://{github_token}@github.com/{owner}/{repo}.git"
    else:
        repo_url = f"https://github.com/{owner}/{repo}.git"
    
    try:
        logger.info(f"Cloning {owner}/{repo} (branch: {branch}) to {temp_dir}")
        subprocess.run(
            ['git', 'clone', '--depth', '1', '--branch', branch, repo_url, str(temp_dir)],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Successfully cloned {owner}/{repo}")
        return temp_dir
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clone failed: {e.stderr}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def find_markdown_files(repo_path: Path) -> List[Path]:
    """Find all markdown files in a repository"""
    md_files = []
    for md_file in repo_path.rglob('*.md'):
        # Skip hidden directories and common non-content directories
        if any(part.startswith('.') for part in md_file.parts):
            continue
        if any(part in ['node_modules', 'vendor', '__pycache__'] for part in md_file.parts):
            continue
        md_files.append(md_file)
    
    logger.info(f"Found {len(md_files)} markdown files")
    return md_files


def translate_file(file_path: Path, repo_root: Path) -> Dict:
    """Translate a single markdown file"""
    try:
        relative_path = file_path.relative_to(repo_root)
        logger.info(f"Translating {relative_path}")
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            logger.info(f"Skipping empty file: {relative_path}")
            return {
                'file': str(relative_path),
                'status': 'skipped',
                'reason': 'empty'
            }
        
        # Translate
        translated_content, from_cache = translate_content(content, str(relative_path))
        
        return {
            'file': str(relative_path),
            'status': 'success',
            'original_length': len(content),
            'translated_length': len(translated_content),
            'translated_content': translated_content,
            'from_cache': from_cache
        }
        
    except Exception as e:
        logger.error(f"Error translating {file_path}: {str(e)}")
        return {
            'file': str(file_path.relative_to(repo_root)),
            'status': 'error',
            'error': str(e)
        }


def save_translation(owner: str, repo: str, results: List[Dict]) -> str:
    """Save translation results to storage"""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    output_dir = f"translations/{owner}/{repo}/{timestamp}"
    
    if LOCAL_MODE:
        # Save to local filesystem
        local_output = LOCAL_STORAGE_PATH / output_dir
        local_output.mkdir(parents=True, exist_ok=True)
        
        # Save translated files
        for result in results:
            if result['status'] == 'success':
                file_path = local_output / result['file']
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(result['translated_content'])
        
        # Save manifest
        manifest = {
            'owner': owner,
            'repo': repo,
            'timestamp': timestamp,
            'total_files': len(results),
            'successful': sum(1 for r in results if r['status'] == 'success'),
            'failed': sum(1 for r in results if r['status'] == 'error'),
            'skipped': sum(1 for r in results if r['status'] == 'skipped'),
            'results': results
        }
        
        manifest_path = local_output / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved translations to {local_output}")
        return str(local_output)
        
    else:
        # Save to GCS
        bucket = storage_client.bucket(bucket_name)
        
        for result in results:
            if result['status'] == 'success':
                blob_path = f"{output_dir}/{result['file']}"
                blob = bucket.blob(blob_path)
                blob.upload_from_string(
                    result['translated_content'],
                    content_type='text/markdown'
                )
        
        # Save manifest
        manifest = {
            'owner': owner,
            'repo': repo,
            'timestamp': timestamp,
            'total_files': len(results),
            'successful': sum(1 for r in results if r['status'] == 'success'),
            'failed': sum(1 for r in results if r['status'] == 'error'),
            'skipped': sum(1 for r in results if r['status'] == 'skipped'),
            'results': [
                {k: v for k, v in r.items() if k != 'translated_content'}
                for r in results
            ]
        }
        
        manifest_blob = bucket.blob(f"{output_dir}/manifest.json")
        manifest_blob.upload_from_string(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        
        logger.info(f"Saved translations to gs://{bucket_name}/{output_dir}")
        return f"gs://{bucket_name}/{output_dir}"


def process_repository(task_id: str, owner: str, repo: str, branch: str = 'main'):
    """Process a repository translation (runs in background)"""
    try:
        # Update task status
        tasks_store[task_id]['status'] = 'cloning'
        
        # Clone repository
        repo_path = clone_github_repo(owner, repo, branch)
        
        # Find markdown files
        tasks_store[task_id]['status'] = 'scanning'
        md_files = find_markdown_files(repo_path)
        tasks_store[task_id]['progress']['total'] = len(md_files)
        
        # Translate files in parallel
        tasks_store[task_id]['status'] = 'translating'
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(translate_file, file_path, repo_path): file_path
                for file_path in md_files
            }
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                tasks_store[task_id]['progress']['completed'] += 1
                
                # Log progress
                completed = tasks_store[task_id]['progress']['completed']
                total = tasks_store[task_id]['progress']['total']
                logger.info(f"Task {task_id}: {completed}/{total} files processed")
        
        # Save translations
        tasks_store[task_id]['status'] = 'saving'
        output_path = save_translation(owner, repo, results)
        
        # Update task with results
        tasks_store[task_id]['status'] = 'completed'
        tasks_store[task_id]['output_path'] = output_path
        tasks_store[task_id]['completed_at'] = datetime.utcnow().isoformat() + 'Z'
        tasks_store[task_id]['summary'] = {
            'total': len(results),
            'successful': sum(1 for r in results if r['status'] == 'success'),
            'failed': sum(1 for r in results if r['status'] == 'error'),
            'skipped': sum(1 for r in results if r['status'] == 'skipped')
        }
        
        # Cleanup
        shutil.rmtree(repo_path, ignore_errors=True)
        
        logger.info(f"Task {task_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}")
        tasks_store[task_id]['status'] = 'failed'
        tasks_store[task_id]['error'] = str(e)
        tasks_store[task_id]['failed_at'] = datetime.utcnow().isoformat() + 'Z'


# Flask routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': '2.0.0',
        'mode': 'local' if LOCAL_MODE else 'cloud',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200


@app.route('/status', methods=['GET'])
def status():
    """Get service status"""
    return jsonify({
        'service': 'hermes-wiki-translator',
        'status': 'running',
        'mode': 'local' if LOCAL_MODE else 'cloud',
        'tasks_in_queue': len([t for t in tasks_store.values() if t['status'] in ['pending', 'cloning', 'scanning', 'translating', 'saving']]),
        'tasks_completed': len([t for t in tasks_store.values() if t['status'] == 'completed']),
        'tasks_failed': len([t for t in tasks_store.values() if t['status'] == 'failed']),
        'cache_size': len(translation_cache),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'storage': str(LOCAL_STORAGE_PATH) if LOCAL_MODE else f'gs://{bucket_name}'
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
        
        translated_content, from_cache = translate_content(content, filename)
        
        logger.info(f"Translation completed for {filename} (from_cache: {from_cache})")
        
        return jsonify({
            'original': content,
            'translated': translated_content,
            'filename': filename,
            'original_length': len(content),
            'translated_length': len(translated_content),
            'from_cache': from_cache
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
        
        # Start background processing
        import threading
        thread = threading.Thread(
            target=process_repository,
            args=(task_id, owner, repo, branch)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'task_id': task_id,
            'status': 'pending',
            'owner': owner,
            'repo': repo,
            'monitor_url': f'/task-status/{task_id}'
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
    """List all translations"""
    try:
        if LOCAL_MODE:
            # List local translations
            translations = []
            if LOCAL_STORAGE_PATH.exists():
                for manifest_file in LOCAL_STORAGE_PATH.rglob('manifest.json'):
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    translations.append({
                        'path': str(manifest_file.parent.relative_to(LOCAL_STORAGE_PATH)),
                        'owner': manifest['owner'],
                        'repo': manifest['repo'],
                        'timestamp': manifest['timestamp'],
                        'total_files': manifest['total_files'],
                        'successful': manifest['successful']
                    })
            return jsonify(translations), 200
        else:
            # List GCS translations
            if not storage_client:
                return jsonify({'error': 'GCS not configured'}), 503
            
            bucket = storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix='translations/'))
            
            translations = []
            for blob in blobs:
                if blob.name.endswith('manifest.json'):
                    content = blob.download_as_string()
                    manifest = json.loads(content)
                    translations.append({
                        'path': blob.name.replace('/manifest.json', ''),
                        'owner': manifest['owner'],
                        'repo': manifest['repo'],
                        'timestamp': manifest['timestamp'],
                        'total_files': manifest['total_files'],
                        'successful': manifest['successful']
                    })
            
            return jsonify(translations), 200
        
    except Exception as e:
        logger.error(f"List error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/download/<path:file_path>', methods=['GET'])
def download(file_path):
    """Download a translated file or manifest"""
    try:
        if LOCAL_MODE:
            # Download from local filesystem
            local_file = LOCAL_STORAGE_PATH / file_path
            
            if not local_file.exists():
                return jsonify({'error': 'File not found'}), 404
            
            return send_file(
                local_file,
                as_attachment=True,
                download_name=local_file.name
            )
        else:
            # Download from GCS
            if not storage_client:
                return jsonify({'error': 'GCS not configured'}), 503
            
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            
            if not blob.exists():
                return jsonify({'error': 'File not found'}), 404
            
            content = blob.download_as_string()
            
            return content, 200, {
                'Content-Disposition': f'attachment; filename={os.path.basename(file_path)}',
                'Content-Type': 'text/markdown' if file_path.endswith('.md') else 'application/json'
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
