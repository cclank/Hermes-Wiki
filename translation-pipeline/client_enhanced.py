#!/usr/bin/env python3
"""
Enhanced CLI client with improved UX and local mode support
"""

import argparse
import json
import sys
import time
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.id_token import fetch_id_token
import google.auth

# Load environment variables
load_dotenv()

class TranslationClient:
    def __init__(self, service_url: Optional[str] = None, use_auth: bool = True):
        # Auto-detect service URL from environment if not provided
        if service_url is None:
            service_url = os.getenv('TRANSLATION_SERVICE_URL', 'http://localhost:8080')
        
        self.service_url = service_url.rstrip('/')
        self.use_auth = use_auth and not service_url.startswith('http://localhost')
        self.token = None
        
        if self.use_auth:
            self._refresh_token()
    
    def _refresh_token(self):
        """Refresh authentication token"""
        try:
            # Get credentials from environment or gcloud
            credentials, _ = google.auth.default()
            request = Request()
            self.token = credentials.token
        except Exception as e:
            print(f"⚠ Warning: Could not get auth token: {e}")
            self.use_auth = False
    
    def _get_headers(self) -> dict:
        """Get request headers with authentication"""
        headers = {'Content-Type': 'application/json'}
        if self.use_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers
    
    def health(self) -> dict:
        """Check service health"""
        try:
            response = requests.get(f"{self.service_url}/health", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def status(self) -> dict:
        """Get service status"""
        try:
            response = requests.get(f"{self.service_url}/status", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def translate(self, content: str, filename: str = 'document.md') -> dict:
        """Translate markdown content"""
        try:
            data = {
                'content': content,
                'filename': filename
            }
            response = requests.post(
                f"{self.service_url}/translate",
                json=data,
                headers=self._get_headers(),
                timeout=300
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def translate_repo(self, owner: str, repo: str, branch: str = 'main') -> dict:
        """Start asynchronous repository translation"""
        try:
            data = {
                'owner': owner,
                'repo': repo,
                'branch': branch
            }
            response = requests.post(
                f"{self.service_url}/translate-repo",
                json=data,
                headers=self._get_headers(),
                timeout=30
            )
            if response.status_code == 202:
                return response.json()
            else:
                return {'error': f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {'error': str(e)}
    
    def task_status(self, task_id: str) -> dict:
        """Get status of a translation task"""
        try:
            response = requests.get(
                f"{self.service_url}/task-status/{task_id}",
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def list_translations(self) -> dict:
        """List all translations"""
        try:
            response = requests.get(
                f"{self.service_url}/list-translations",
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def download(self, owner: str, repo: str, filename: str, output_file: Optional[str] = None) -> bool:
        """Download a translated file"""
        try:
            response = requests.get(
                f"{self.service_url}/download-file/{owner}/{repo}/{filename}",
                headers=self._get_headers(),
                timeout=60
            )
            
            if response.status_code == 200:
                if output_file is None:
                    output_file = Path(path).name
                
                # Create output directory if needed
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                print(f"✓ Downloaded to {output_file}")
                return True
            else:
                print(f"✗ Download failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


def print_header():
    """Print CLI header"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Hermes Wiki Translation Pipeline - CLI Client           ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()


def print_status_bar(completed: int, total: int, status: str):
    """Print a progress bar"""
    if total == 0:
        percentage = 0
    else:
        percentage = int((completed / total) * 100)
    
    bar_length = 40
    filled = int((percentage / 100) * bar_length)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    print(f"\r  [{bar}] {percentage}% | {completed}/{total} files | Status: {status}", end='', flush=True)


def main():
    parser = argparse.ArgumentParser(
        description='Hermes Wiki Translation Pipeline Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check service health
  %(prog)s health
  
  # Translate a single file
  %(prog)s translate --file README.md
  
  # Translate entire repository
  %(prog)s translate --owner scapedotes --repo Hermes-Wiki --monitor
  
  # List all translations
  %(prog)s list
  
  # Download translation
  %(prog)s download --path translations/scapedotes/Hermes-Wiki/20260502_123456/README.md
        """
    )
    
    parser.add_argument(
        '--service-url',
        help='Translation service URL (default: from .env or http://localhost:8080)',
        default=None
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Health check command
    subparsers.add_parser('health', help='Check service health')
    
    # Status command
    subparsers.add_parser('status', help='Get service status')
    
    # Translate command
    translate_parser = subparsers.add_parser('translate', help='Translate content')
    translate_parser.add_argument('--file', help='Input file to translate')
    translate_parser.add_argument('--owner', help='GitHub repo owner')
    translate_parser.add_argument('--repo', help='GitHub repo name')
    translate_parser.add_argument('--branch', default='main', help='Git branch (default: main)')
    translate_parser.add_argument('--monitor', action='store_true', help='Monitor progress')
    translate_parser.add_argument('--output', help='Output file (for single file translation)')
    
    # Task status command
    task_status_parser = subparsers.add_parser('task-status', help='Check task status')
    task_status_parser.add_argument('task_id', help='Task ID')
    
    # List command
    subparsers.add_parser('list', help='List all translations')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download translation')
    download_parser.add_argument('--path', required=True, help='File path to download')
    download_parser.add_argument('--output', help='Output file path')
    
    args = parser.parse_args()
    
    if not args.command:
        print_header()
        parser.print_help()
        return
    
    # Initialize client
    client = TranslationClient(args.service_url)
    
    if args.command == 'health':
        print_header()
        print("Checking service health...")
        result = client.health()
        
        if 'error' in result:
            print(f"✗ Service unavailable: {result['error']}")
            sys.exit(1)
        else:
            print(f"✓ Service is healthy")
            print(f"  Version: {result.get('version', 'unknown')}")
            print(f"  Mode: {result.get('mode', 'unknown')}")
            print(f"  Timestamp: {result.get('timestamp', 'unknown')}")
    
    elif args.command == 'status':
        print_header()
        print("Getting service status...")
        result = client.status()
        
        if 'error' in result:
            print(f"✗ Error: {result['error']}")
            sys.exit(1)
        else:
            print(f"✓ Service Status:")
            print(f"  Mode: {result.get('mode', 'unknown')}")
            print(f"  Tasks in queue: {result.get('tasks_in_queue', 0)}")
            print(f"  Tasks completed: {result.get('tasks_completed', 0)}")
            print(f"  Tasks failed: {result.get('tasks_failed', 0)}")
            print(f"  Cache size: {result.get('cache_size', 0)}")
            print(f"  Storage: {result.get('storage', 'unknown')}")
    
    elif args.command == 'translate':
        print_header()
        
        if args.file:
            # Translate single file
            file_path = Path(args.file)
            
            if not file_path.exists():
                print(f"✗ File not found: {args.file}")
                sys.exit(1)
            
            print(f"Translating {args.file}...")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result = client.translate(content, args.file)
            
            if 'error' in result:
                print(f"✗ Translation failed: {result['error']}")
                sys.exit(1)
            
            if 'translated' in result:
                output_file = args.output or str(file_path).replace('.md', '-en.md')
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result['translated'])
                
                print(f"✓ Translation saved to {output_file}")
                print(f"  Original: {result['original_length']} chars")
                print(f"  Translated: {result['translated_length']} chars")
                if result.get('from_cache'):
                    print(f"  Source: Cache (instant)")
            else:
                print(f"✗ Translation failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)
        
        elif args.owner and args.repo:
            # Translate repository
            print(f"Starting translation of {args.owner}/{args.repo} (branch: {args.branch})...")
            print()
            
            result = client.translate_repo(args.owner, args.repo, args.branch)
            
            if 'error' in result:
                print(f"✗ Failed: {result['error']}")
                sys.exit(1)
            
            if 'task_id' in result:
                task_id = result['task_id']
                print(f"✓ Task created: {task_id}")
                print()
                
                if args.monitor:
                    print("Monitoring progress (Ctrl+C to stop monitoring)...")
                    print()
                    
                    try:
                        last_status = None
                        while True:
                            status = client.task_status(task_id)
                            
                            if 'error' not in status:
                                task_status_str = status.get('status', 'unknown')
                                completed = status.get('progress', {}).get('completed', 0)
                                total = status.get('progress', {}).get('total', 0)
                                
                                # Print progress bar
                                if task_status_str != last_status:
                                    if last_status is not None:
                                        print()  # New line after progress bar
                                    print(f"  Status: {task_status_str}")
                                
                                if total > 0:
                                    print_status_bar(completed, total, task_status_str)
                                
                                last_status = task_status_str
                                
                                if task_status_str == 'completed':
                                    print()  # New line after progress bar
                                    print()
                                    print("✓ Translation completed!")
                                    
                                    summary = status.get('summary', {})
                                    print(f"  Total files: {summary.get('total', 0)}")
                                    print(f"  Successful: {summary.get('successful', 0)}")
                                    print(f"  Failed: {summary.get('failed', 0)}")
                                    print(f"  Skipped: {summary.get('skipped', 0)}")
                                    print()
                                    print(f"  Output: {status.get('output_path', 'unknown')}")
                                    break
                                
                                elif task_status_str == 'failed':
                                    print()  # New line after progress bar
                                    print()
                                    print(f"✗ Translation failed: {status.get('error', 'Unknown error')}")
                                    sys.exit(1)
                            
                            time.sleep(2)
                    
                    except KeyboardInterrupt:
                        print()
                        print()
                        print("⚠ Monitoring stopped (task continues in background)")
                        print(f"  Check status: python3 client.py task-status {task_id}")
                else:
                    print(f"Task started. Check status with:")
                    print(f"  python3 client.py task-status {task_id}")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)
        
        else:
            print("✗ Error: Provide either --file or --owner and --repo")
            parser.print_help()
            sys.exit(1)
    
    elif args.command == 'task-status':
        print_header()
        print(f"Checking status of task {args.task_id}...")
        
        result = client.task_status(args.task_id)
        
        if 'error' in result:
            print(f"✗ Error: {result['error']}")
            sys.exit(1)
        
        print(json.dumps(result, indent=2))
    
    elif args.command == 'list':
        print_header()
        print("Listing translations...")
        
        result = client.list_translations()
        
        if isinstance(result, dict) and 'error' in result:
            print(f"✗ Error: {result['error']}")
            sys.exit(1)
        
        if isinstance(result, list):
            if len(result) == 0:
                print("  No translations found")
            else:
                print(f"  Found {len(result)} translation(s):")
                print()
                for item in result:
                    print(f"  📁 {item.get('owner')}/{item.get('repo')}")
                    print(f"     Timestamp: {item.get('timestamp')}")
                    print(f"     Files: {item.get('successful')}/{item.get('total_files')}")
                    print(f"     Path: {item.get('path')}")
                    print()
        else:
            print(json.dumps(result, indent=2))
    
    elif args.command == 'download':
        print_header()
        
        # Parse owner/repo/filename from path if provided as a single string
        # or require explicit flags. For simplicity in CLI, let's use flags.
        parser_dl = argparse.ArgumentParser(add_help=False)
        parser_dl.add_argument('--owner', required=True)
        parser_dl.add_argument('--repo', required=True)
        parser_dl.add_argument('--filename', required=True)
        dl_args, _ = parser_dl.parse_known_args(sys.argv[3:])

        print(f"Downloading {dl_args.filename} from {dl_args.owner}/{dl_args.repo}...")
        
        success = client.download(dl_args.owner, dl_args.repo, dl_args.filename, args.output)
        
        if not success:
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
