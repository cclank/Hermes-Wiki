"""
Python CLI client for Cloud Run Translation Service
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.id_token import fetch_id_token
import google.auth

class TranslationClient:
    def __init__(self, service_url: str, use_auth: bool = True):
        self.service_url = service_url.rstrip('/')
        self.use_auth = use_auth
        self.token = None
        
        if use_auth:
            self._refresh_token()
    
    def _refresh_token(self):
        """Refresh authentication token"""
        try:
            # Get credentials from environment or gcloud
            credentials, _ = google.auth.default()
            request = Request()
            self.token = credentials.token
        except Exception as e:
            print(f"Warning: Could not get auth token: {e}")
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
            response = requests.get(f"{self.service_url}/health")
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
                headers=self._get_headers()
            )
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
                headers=self._get_headers()
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
                headers=self._get_headers()
            )
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def list_translations(self) -> dict:
        """List all translations"""
        try:
            response = requests.get(
                f"{self.service_url}/list-translations",
                headers=self._get_headers()
            )
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def download(self, path: str, output_file: Optional[str] = None) -> bool:
        """Download a translated file"""
        try:
            response = requests.get(
                f"{self.service_url}/download/{path}",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                if output_file is None:
                    output_file = Path(path).name
                
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

def main():
    parser = argparse.ArgumentParser(
        description='Cloud Run Translation Pipeline Client'
    )
    parser.add_argument(
        '--service-url',
        required=False,
        help='Cloud Run service URL'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Health check command
    subparsers.add_parser('health', help='Check service health')
    
    # Translate command
    translate_parser = subparsers.add_parser('translate', help='Translate content')
    translate_parser.add_argument('--file', help='Input file to translate')
    translate_parser.add_argument('--owner', help='GitHub repo owner')
    translate_parser.add_argument('--repo', help='GitHub repo name')
    translate_parser.add_argument('--branch', default='main', help='Git branch')
    translate_parser.add_argument('--monitor', action='store_true', help='Monitor progress')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check task status')
    status_parser.add_argument('--task-id', required=True, help='Task ID')
    
    # List command
    subparsers.add_parser('list', help='List translations')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download translation')
    download_parser.add_argument('--path', required=True, help='File path')
    download_parser.add_argument('--output', help='Output file')
    
    args = parser.parse_args()
    
    if not args.service_url:
        print("Error: --service-url is required")
        sys.exit(1)
    
    client = TranslationClient(args.service_url)
    
    if args.command == 'health':
        result = client.health()
        print(json.dumps(result, indent=2))
    
    elif args.command == 'translate':
        if args.file:
            # Translate single file
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"Translating {args.file}...")
            result = client.translate(content, args.file)
            
            if 'translated' in result:
                output_file = args.file.replace('.md', '-en.md')
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result['translated'])
                print(f"✓ Translation saved to {output_file}")
            else:
                print(f"✗ Translation failed: {result.get('error', 'Unknown error')}")
        
        elif args.owner and args.repo:
            # Translate repository
            print(f"Starting translation of {args.owner}/{args.repo}...")
            result = client.translate_repo(args.owner, args.repo, args.branch)
            
            if 'task_id' in result:
                task_id = result['task_id']
                print(f"✓ Task created: {task_id}")
                
                if args.monitor:
                    print("Monitoring progress...")
                    while True:
                        status = client.task_status(task_id)
                        
                        if 'error' not in status:
                            task_status = status.get('status', 'unknown')
                            completed = status.get('progress', {}).get('completed', 0)
                            total = status.get('progress', {}).get('total', 0)
                            
                            print(f"Status: {task_status} | Progress: {completed}/{total}")
                            
                            if task_status in ['completed', 'failed']:
                                print(f"Task {task_status}")
                                break
                        
                        time.sleep(5)
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")
        else:
            print("Error: Provide either --file or --owner and --repo")
    
    elif args.command == 'status':
        result = client.task_status(args.task_id)
        print(json.dumps(result, indent=2))
    
    elif args.command == 'list':
        result = client.list_translations()
        if isinstance(result, list):
            for item in result:
                print(f"  {item['path']} ({item['size']} bytes)")
        else:
            print(json.dumps(result, indent=2))
    
    elif args.command == 'download':
        client.download(args.path, args.output)
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
