#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${REPO_NAME:-pressbox-war-room-agent}"
GITHUB_USER="${GITHUB_USER:-pielen}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Usage: GITHUB_TOKEN=<your_github_pat> $0"
  echo ""
  echo "To get a token in 30 seconds:"
  echo "  1. Open https://github.com/settings/tokens/new"
  echo "  2. Select 'repo' (or 'public_repo') scope and click 'Generate token'"
  echo "  3. Run: GITHUB_TOKEN=ghp_xxx $0"
  exit 1
fi

echo "==> 1/2 Creating public GitHub repository '${GITHUB_USER}/${REPO_NAME}' via GitHub API..."
HTTP_CODE=$(curl -s -o /tmp/gh_create_resp.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/user/repos \
  -d "{
    \"name\": \"${REPO_NAME}\",
    \"description\": \"Multi-Agent MLB & NHL Scouting & Matchup War Room built with Google ADK\",
    \"private\": false,
    \"has_issues\": true
  }")

if [[ "${HTTP_CODE}" == "201" ]]; then
  echo "    Created https://github.com/${GITHUB_USER}/${REPO_NAME}"
elif [[ "${HTTP_CODE}" == "422" ]]; then
  echo "    Repository https://github.com/${GITHUB_USER}/${REPO_NAME} already exists; proceeding to push."
else
  echo "    GitHub API returned HTTP ${HTTP_CODE}:"
  cat /tmp/gh_create_resp.json
  exit 1
fi

echo "==> 2/2 Pushing 'main' branch to https://github.com/${GITHUB_USER}/${REPO_NAME}.git..."
git -C "${REPO_DIR}" push -u "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git" main

echo ""
echo "✅ Successfully published! View your repo at:"
echo "   https://github.com/${GITHUB_USER}/${REPO_NAME}"
