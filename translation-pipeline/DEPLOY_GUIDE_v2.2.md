# Translation Pipeline v2.2 - Deployment Package

This package contains the fully upgraded translation pipeline.

### Core Enhancements:
1. **Web UI 2.0**: Full management dashboard for checking, uploading, downloading, and running translations.
2. **Skip-if-existing Logic**: Fully implemented and tested.
3. **One-Click Deploy**: Added official Google Cloud Run deploy button to README.
4. **Local/Cloud Storage Parity**: Both modes now support the full feature set.

### Files Included:
- `app_enhanced.py`: Main service with async processing and new management routes.
- `templates/index.html`: Modern, responsive management UI.
- `README.md`: Updated with the visual "Run on Google Cloud" button.
- `terminology_map.json`: Technical glossary for consistent translation.

### To Start:
```bash
./deploy.sh
```
Access at: http://localhost:8080
