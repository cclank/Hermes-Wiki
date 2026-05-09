#!/usr/bin/env python3
"""
Quick start script - translate the Hermes Wiki repository locally
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Hermes Wiki - Quick Translation                         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    # Check if .env exists
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠ No .env file found. Running setup...")
        print()
        
        # Run deploy.sh in setup mode
        result = subprocess.run(['bash', 'deploy.sh'], check=False)
        if result.returncode != 0:
            print()
            print("✗ Setup failed. Please run ./deploy.sh manually")
            sys.exit(1)
    else:
        print("✓ Configuration found")
    
    # Check if service is running
    print()
    print("Checking if translation service is running...")
    
    try:
        import requests
        response = requests.get('http://localhost:8080/health', timeout=5)
        if response.status_code == 200:
            print("✓ Service is running")
        else:
            print("⚠ Service returned unexpected status")
    except:
        print("⚠ Service not running. Starting local service...")
        print()
        print("Please run in another terminal:")
        print("  cd translation-pipeline")
        print("  source venv/bin/activate")
        print("  python3 app_enhanced.py")
        print()
        sys.exit(1)
    
    # Start translation
    print()
    print("Starting translation of scapedotes/Hermes-Wiki...")
    print()
    
    # Run client
    result = subprocess.run([
        'python3', 'client_enhanced.py', 'translate',
        '--owner', 'scapedotes',
        '--repo', 'Hermes-Wiki',
        '--monitor'
    ])
    
    if result.returncode == 0:
        print()
        print("✓ Translation complete!")
        print()
        print("Next steps:")
        print("  1. List translations: python3 client_enhanced.py list")
        print("  2. Download files: python3 client_enhanced.py download --path <path>")
    else:
        print()
        print("✗ Translation failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
