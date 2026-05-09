#!/bin/bash
# Quick guide to push the improved translation pipeline to GitHub

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Push Translation Pipeline v2.0 to GitHub                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if we're in a git repo
if [ ! -d ".git" ]; then
    echo "Error: Not in a git repository"
    echo "Please run this from the Hermes-Wiki root directory"
    exit 1
fi

echo "Step 1: Review changes"
echo "======================"
git status
echo ""

echo "Step 2: Stage new and modified files"
echo "====================================="
git add translation-pipeline/

echo ""
echo "Files staged:"
git diff --cached --name-only
echo ""

echo "Step 3: Commit changes"
echo "======================"
read -p "Enter commit message [Translation Pipeline v2.0 - Complete overhaul]: " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"Translation Pipeline v2.0 - Complete overhaul"}

git commit -m "$COMMIT_MSG" -m "
Major improvements:
- Added local mode (no GCP required)
- One-command deployment script (deploy.sh)
- Complete GitHub integration with batch processing
- Smart caching to avoid re-translation
- Enhanced CLI with progress bars
- Real-time progress tracking
- Comprehensive terminology mapping (164 terms)
- Complete Terraform infrastructure code
- Better error handling and logging
- Updated documentation

New files:
- app_enhanced.py - Enhanced Flask service
- client_enhanced.py - Enhanced CLI client
- deploy.sh - Interactive deployment script
- quick_start.py - Quick start helper
- test_pipeline.py - Test suite
- terminology_map.json - Translation terminology
- .env.example - Environment template
- terraform/main.tf - Infrastructure code
- terraform/variables.tf - Terraform variables
- README_v2.md - Updated documentation
- IMPROVEMENTS.md - Detailed improvement summary

See IMPROVEMENTS.md for complete details.
"

echo ""
echo "Step 4: Push to GitHub"
echo "======================"
echo "Current branch: $(git branch --show-current)"
echo ""
read -p "Push to origin? [Y/n]: " PUSH_CONFIRM

if [ "$PUSH_CONFIRM" != "n" ] && [ "$PUSH_CONFIRM" != "N" ]; then
    git push origin $(git branch --show-current)
    echo ""
    echo "✓ Changes pushed successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Visit: https://github.com/scapedotes/Hermes-Wiki"
    echo "  2. Review the changes"
    echo "  3. Create a pull request if needed"
    echo "  4. Test the deployment: cd translation-pipeline && ./deploy.sh"
else
    echo ""
    echo "Push cancelled. You can push later with:"
    echo "  git push origin $(git branch --show-current)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Done!                                                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
