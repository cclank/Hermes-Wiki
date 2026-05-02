#!/usr/bin/env python3
"""
Enhanced translation service v2.1
- Local & Cloud modes
- Batch processing & GitHub integration
- Web UI for management
- Skip already translated files logic
"""

import os
import json
import uuid
import shutil
import tempfile
import subprocess
import hashlib
from datetime import datetime
from functools import wraps
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
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
app = Flask(__name__, template_folder='templates', static_folder='static')

# Configuration
LOCAL_MODE = os.getenv('LOCAL_MODE', 'false').lower() == 'true'
LOCAL_STORAGE_PATH = Path(os.getenv('LOCAL_STORAGE_PATH', './translations'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '10'))
TRANSLATION_MODEL = os.getenv('TRANSLATION_MODEL', 'claude-3-5-sonnet-20241022')
MAX_TOKENS = int(os.getenv('MAX_TOKENS', '4096'))
SKIP_EXISTING = os.getenv('SKIP_EXISTING', 'true').lower() == 'true'

# Initialize Claude client
claude_api_key = os.getenv('CLAUDE_API_KEY')
if not claude_api_key:
    logger.warning("CLAUDE_API_KEY not set. Translation will fail.")
    client = None
else:
    client = Anthropic(api_key=claude_api_key)

# Initialize GCS client
storage_client = None
bucket_name = os.getenv('GCS_BUCKET_NAME', 'hermes-wiki-translations')

if not LOCAL_MODE:
    try:
        storage_client = storage.Client()
        logger.info(f"GCS client initialized for bucket: {bucket_name}")
    except Exception as e:
        logger.warning(f"GCS client initialization failed: {e}. Falling back to local mode.")
        LOCAL_MODE = True

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

# In-memory task storage
tasks_store = {}
translation_cache = {}

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
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def check_exists_in_storage(owner: str, repo: str, relative_path: str) -> bool:
    """Check if a translated file already exists in storage"""
    target_path = f"translations/{owner}/{repo}/latest/{relative_path}"
    
    if LOCAL_MODE:
        local_file = LOCAL_STORAGE_PATH / target_path
        return local_file.exists()
    else:
        if not storage_client: return False
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(target_path)
        return blob.exists()

def translate_content(content: str, filename: str = 'document.md') -> Tuple[str, bool]:
    if not client:
        raise ValueError("Claude API client not initialized")
    
    cache_key = get_cache_key(content)
    if cache_key in translation_cache:
        logger.info(f"Cache hit for {filename}")
        return translation_cache[cache_key], True
    
    terminology_str = json.dumps(terminology_map, ensure_ascii=False, indent=2)
    system_prompt = SYSTEM_PROMPT.format(terminology=terminology_str)
    
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
        translation_cache[cache_key] = translated_content
        return translated_content, False
    except Exception as e:
        logger.error(f"Translation error for {filename}: {str(e)}")
        raise

def clone_github_repo(owner: str, repo: str, branch: str = 'main') -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix='hermes-wiki-'))
    github_token = os.getenv('GITHUB_TOKEN')
    repo_url = f"https://{github_token}@github.com/{owner}/{repo}.git" if github_token else f"https://github.com/{owner}/{repo}.git"
    
    try:
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, repo_url, str(temp_dir)], check=True, capture_output=True, text=True)
        return temp_dir
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clone failed: {e.stderr}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

def find_markdown_files(repo_path: Path) -> List[Path]:
    md_files = []
    for md_file in repo_path.rglob('*.md'):
        if any(part.startswith('.') for part in md_file.parts): continue
        if any(part in ['node_modules', 'vendor', '__pycache__'] for part in md_file.parts): continue
        md_files.append(md_file)
    return md_files

def translate_file(file_path: Path, repo_root: Path, owner: str, repo: str, force: bool = False) -> Dict:
    try:
        relative_path = str(file_path.relative_to(repo_root))
        
        # SKIP LOGIC
        if SKIP_EXISTING and not force:
            if check_exists_in_storage(owner, repo, relative_path):
                logger.info(f"Skipping {relative_path} - already exists")
                return {'file': relative_path, 'status': 'skipped', 'reason': 'exists'}

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            return {'file': relative_path, 'status': 'skipped', 'reason': 'empty'}
        
        translated_content, from_cache = translate_content(content, relative_path)
        return {
            'file': relative_path, 'status': 'success',
            'original_length': len(content), 'translated_length': len(translated_content),
            'translated_content': translated_content, 'from_cache': from_cache
        }
    except Exception as e:
        return {'file': str(file_path.relative_to(repo_root)), 'status': 'error', 'error': str(e)}

def save_translation(owner: str, repo: str, results: List[Dict]) -> str:
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    dirs = [f"translations/{owner}/{repo}/{timestamp}", f"translations/{owner}/{repo}/latest"]
    
    final_path = ""
    for output_dir in dirs:
        if LOCAL_MODE:
            local_output = LOCAL_STORAGE_PATH / output_dir
            local_output.mkdir(parents=True, exist_ok=True)
            for result in results:
                if result['status'] == 'success':
                    file_path = local_output / result['file']
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(result['translated_content'])
            final_path = str(LOCAL_STORAGE_PATH / dirs[0])
        else:
            bucket = storage_client.bucket(bucket_name)
            for result in results:
                if result['status'] == 'success':
                    blob = bucket.blob(f"{output_dir}/{result['file']}")
                    blob.upload_from_string(result['translated_content'], content_type='text/markdown')
            final_path = f"gs://{bucket_name}/{dirs[0]}"
            
    return final_path

def process_repository(task_id: str, owner: str, repo: str, branch: str = 'main', force: bool = False):
    try:
        tasks_store[task_id]['status'] = 'cloning'
        repo_path = clone_github_repo(owner, repo, branch)
        tasks_store[task_id]['status'] = 'scanning'
        md_files = find_markdown_files(repo_path)
        tasks_store[task_id]['progress']['total'] = len(md_files)
        
        results = []
        tasks_store[task_id]['status'] = 'translating'
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(translate_file, f, repo_path, owner, repo, force): f for f in md_files}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                tasks_store[task_id]['progress']['completed'] += 1
        
        tasks_store[task_id]['status'] = 'saving'
        output_path = save_translation(owner, repo, results)
        tasks_store[task_id]['status'] = 'completed'
        tasks_store[task_id]['output_path'] = output_path
        tasks_store[task_id]['summary'] = {
            'total': len(results),
            'successful': sum(1 for r in results if r['status'] == 'success'),
            'failed': sum(1 for r in results if r['status'] == 'error'),
            'skipped': sum(1 for r in results if r['status'] == 'skipped')
        }
        shutil.rmtree(repo_path, ignore_errors=True)
    except Exception as e:
        tasks_store[task_id]['status'] = 'failed'
        tasks_store[task_id]['error'] = str(e)

# --- Web UI Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'version': '2.1.0', 'mode': 'local' if LOCAL_MODE else 'cloud'}), 200

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'service': 'hermes-wiki-translator',
        'status': 'running',
        'mode': 'local' if LOCAL_MODE else 'cloud',
        'cache_size': len(translation_cache),
        'storage': str(LOCAL_STORAGE_PATH) if LOCAL_MODE else f'gs://{bucket_name}'
    }), 200

@app.route('/translate-repo', methods=['POST'])
def translate_repo():
    data = request.get_json() or {}
    owner = data.get('owner')
    repo = data.get('repo')
    force = data.get('force', False)
    if not owner or not repo: return jsonify({'error': 'Owner and repo required'}), 400
    
    task_id = str(uuid.uuid4())
    tasks_store[task_id] = {
        'id': task_id, 'status': 'pending', 'owner': owner, 'repo': repo,
        'progress': {'completed': 0, 'total': 0}, 'created_at': datetime.utcnow().isoformat()
    }
    
    import threading
    threading.Thread(target=process_repository, args=(task_id, owner, repo, data.get('branch', 'main'), force)).start()
    return jsonify({'task_id': task_id, 'status': 'pending'}), 202

@app.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id):
    if task_id not in tasks_store: return jsonify({'error': 'Task not found'}), 404
    return jsonify(tasks_store[task_id]), 200

@app.route('/list-translations', methods=['GET'])
def list_translations():
    # Simplification: list latest per repo
    results = []
    if LOCAL_MODE:
        if (LOCAL_STORAGE_PATH / "translations").exists():
            for owner_dir in (LOCAL_STORAGE_PATH / "translations").iterdir():
                if owner_dir.is_dir():
                    for repo_dir in owner_dir.iterdir():
                        if repo_dir.is_dir():
                            results.append({'owner': owner_dir.name, 'repo': repo_dir.name})
    else:
        # GCS list implementation...
        pass
    return jsonify(results), 200

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400
    content = file.read().decode('utf-8')
    translated, cached = translate_content(content, file.filename)
    return jsonify({'translated': translated, 'filename': file.filename}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
