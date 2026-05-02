#!/usr/bin/env python3
"""
Test suite for the translation pipeline
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Test configuration
TEST_CONTENT = """# 测试文档

这是一个测试文档，用于验证翻译管道。

## 功能

- 智能体架构
- 工具集成
- 技能系统

## 代码示例

```python
def translate(content):
    return client.translate(content)
```

## 链接

访问 [Hermes Agent](https://github.com/nous-research/hermes) 了解更多。
"""

EXPECTED_KEYWORDS = ['test', 'document', 'agent', 'tool', 'skill', 'code', 'example']

def test_imports():
    """Test that all required packages are installed"""
    print("Testing imports...")
    try:
        import flask
        import anthropic
        import requests
        from dotenv import load_dotenv
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False

def test_env_file():
    """Test that .env file exists and has required variables"""
    print("\nTesting environment configuration...")
    
    env_file = Path('.env')
    if not env_file.exists():
        print("  ⚠ No .env file found (run ./deploy.sh first)")
        return False
    
    with open(env_file, 'r') as f:
        content = f.read()
    
    required_vars = ['CLAUDE_API_KEY', 'LOCAL_MODE']
    missing = []
    
    for var in required_vars:
        if var not in content:
            missing.append(var)
    
    if missing:
        print(f"  ✗ Missing variables: {', '.join(missing)}")
        return False
    
    print("  ✓ Environment configuration valid")
    return True

def test_terminology_map():
    """Test that terminology map exists and is valid JSON"""
    print("\nTesting terminology map...")
    
    term_file = Path('terminology_map.json')
    if not term_file.exists():
        print("  ✗ terminology_map.json not found")
        return False
    
    try:
        with open(term_file, 'r', encoding='utf-8') as f:
            terms = json.load(f)
        
        if not isinstance(terms, dict):
            print("  ✗ Terminology map is not a dictionary")
            return False
        
        if len(terms) == 0:
            print("  ✗ Terminology map is empty")
            return False
        
        print(f"  ✓ Terminology map loaded ({len(terms)} terms)")
        return True
    except json.JSONDecodeError as e:
        print(f"  ✗ Invalid JSON: {e}")
        return False

def test_service_health():
    """Test that the service is running and healthy"""
    print("\nTesting service health...")
    
    try:
        import requests
        response = requests.get('http://localhost:8080/health', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Service is healthy")
            print(f"    Version: {data.get('version', 'unknown')}")
            print(f"    Mode: {data.get('mode', 'unknown')}")
            return True
        else:
            print(f"  ✗ Service returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("  ⚠ Service not running (start with: python3 app_enhanced.py)")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def test_translation():
    """Test actual translation functionality"""
    print("\nTesting translation...")
    
    try:
        import requests
        
        response = requests.post(
            'http://localhost:8080/translate',
            json={'content': TEST_CONTENT, 'filename': 'test.md'},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            translated = data.get('translated', '')
            
            # Check that translation contains expected keywords
            found_keywords = [kw for kw in EXPECTED_KEYWORDS if kw.lower() in translated.lower()]
            
            if len(found_keywords) >= len(EXPECTED_KEYWORDS) // 2:
                print(f"  ✓ Translation successful")
                print(f"    Original: {data.get('original_length', 0)} chars")
                print(f"    Translated: {data.get('translated_length', 0)} chars")
                print(f"    From cache: {data.get('from_cache', False)}")
                return True
            else:
                print(f"  ⚠ Translation may be incomplete")
                print(f"    Found keywords: {found_keywords}")
                return False
        else:
            print(f"  ✗ Translation failed: {response.status_code}")
            print(f"    {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("  ⚠ Service not running")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def test_client():
    """Test that the client works"""
    print("\nTesting client...")
    
    client_file = Path('client_enhanced.py')
    if not client_file.exists():
        print("  ✗ client_enhanced.py not found")
        return False
    
    try:
        # Import the client module
        sys.path.insert(0, str(Path.cwd()))
        from client_enhanced import TranslationClient
        
        client = TranslationClient('http://localhost:8080', use_auth=False)
        result = client.health()
        
        if 'error' not in result:
            print("  ✓ Client works correctly")
            return True
        else:
            print(f"  ✗ Client error: {result['error']}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def test_files_exist():
    """Test that all required files exist"""
    print("\nTesting file structure...")
    
    required_files = [
        'app_enhanced.py',
        'client_enhanced.py',
        'deploy.sh',
        'quick_start.py',
        'terminology_map.json',
        '.env.example',
        'requirements.txt',
        'Dockerfile',
        'README_v2.md',
        'IMPROVEMENTS.md',
        'terraform/main.tf',
        'terraform/variables.tf'
    ]
    
    missing = []
    for file in required_files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        print(f"  ✗ Missing files: {', '.join(missing)}")
        return False
    
    print(f"  ✓ All required files present ({len(required_files)} files)")
    return True

def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Translation Pipeline - Test Suite                       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    tests = [
        ("File Structure", test_files_exist),
        ("Imports", test_imports),
        ("Environment", test_env_file),
        ("Terminology Map", test_terminology_map),
        ("Client", test_client),
        ("Service Health", test_service_health),
        ("Translation", test_translation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status:8} {name}")
    
    print("="*60)
    print(f"  {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n✓ All tests passed! Pipeline is ready to use.")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Please review the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
