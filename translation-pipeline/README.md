# Translation Pipeline - v2.2

Automated translation service for converting Hermes-Wiki documentation from Chinese to English.

## 🚀 One-Click Deploy to Cloud Run

Deploy this pipeline to Google Cloud instantly with the button below:

[![Run on Google Cloud](https://deploy.cloud.google.com/networks/cloud-run/button.svg)](https://deploy.cloud.google.com/apps?repo=https://github.com/scapedotes/Hermes-Wiki&directory=translation-pipeline)

## ✨ New in v2.2

- 🖥️ **Robust Web UI**: Manage all translations, browse documents, and download files from the browser.
- 🔍 **Document Browser**: Check which documents are already translated and download them directly.
- ⏭️ **Perfect Skip Logic**: Automatically detects if a file is already translated in storage (GCS/Local) to save API costs.
- 📤 **Quick Upload**: Translate individual markdown files without cloning a whole repo.

## 📋 Features

- 🏠 **Local Mode**: Run entirely on your machine without a cloud account.
- 📦 **Batch Processing**: Parallel translation with real-time progress tracking.
- 💾 **Smart Caching**: SHA256 content-based caching for efficiency.
- 🔄 **GitHub Integration**: Clone and translate entire repositories (master/main/custom branches).

## 🚀 Local Setup

1.  **Configure Environment**:
    Get a Claude API Key from [Anthropic](https://console.anthropic.com).
2.  **Run Deploy Script**:
    ```bash
    cd translation-pipeline
    ./deploy.sh
    ```
3.  **Access Web UI**:
    Open your browser to `http://localhost:8080`.

## 📖 Using the Web UI

-   **Run Tab**: Enter GitHub Owner/Repo and start the batch translation process.
-   **Browse Tab**: See all repositories you've translated. Select one to see all available English files and download them.
-   **Upload Tab**: Drag and drop any `.md` file to get an instant English translation.

## 🔧 Configuration (.env)

-   `SKIP_EXISTING=true`: (Default) Skip files that already have a translation in storage.
-   `LOCAL_MODE=true`: (Default) Use local disk for storage instead of Google Cloud Storage.
-   `CLAUDE_API_KEY`: Your Anthropic API key.
-   `GCS_BUCKET_NAME`: Target bucket if `LOCAL_MODE=false`.
