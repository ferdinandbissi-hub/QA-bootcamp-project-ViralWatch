#!/usr/bin/env bash
#
# setup.sh — ViralWatch Day 1 setup script
#
# What this does, in order:
#   1. Creates the project folder structure
#   2. Downloads the outbreak dataset from GitHub (INRB-UMIE/Ebola_DRC_2026)
#   3. Downloads WHO Disease Outbreak News PDFs
#   4. Checks that the downloads are not empty/broken
#   5. Creates a Python virtual environment and installs base packages
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -euo pipefail   # stop the script immediately if any command fails

echo "=== ViralWatch Day 1 setup ==="

# -----------------------------------------------------------------------
# STEP 1: Create the project folders
# -----------------------------------------------------------------------
# -p means "create parent folders too, and don't error if they already exist"
echo "[1/5] Creating project folders..."
mkdir -p data/raw
mkdir -p data/processed
mkdir -p data/who_bulletins
mkdir -p notebooks
mkdir -p src
mkdir -p sql
mkdir -p api
mkdir -p dashboard

# -----------------------------------------------------------------------
# STEP 2: Download the outbreak dataset
# -----------------------------------------------------------------------
# We clone the INRB-UMIE data repo into data/raw/.
# --depth 1 means "only get the latest snapshot, not the full history" —
# this keeps the download small and fast, which is all we need.
echo "[2/5] Downloading outbreak dataset from GitHub..."
DATA_REPO_URL="https://github.com/INRB-UMIE/Ebola_DRC_2026.git"
DATA_DEST="data/raw/Ebola_DRC_2026"

if [ -d "$DATA_DEST" ]; then
  echo "  -> Dataset already exists at $DATA_DEST, skipping clone."
  echo "     (delete this folder first if you want a fresh copy)"
else
  git clone --depth 1 "$DATA_REPO_URL" "$DATA_DEST"
fi

# -----------------------------------------------------------------------
# STEP 3: Download WHO Disease Outbreak News PDFs
# -----------------------------------------------------------------------
# WHO doesn't give clean direct PDF links, so this section is a template:
# fill WHO_BULLETIN_URLS in with the real PDF links your team finds by
# searching "DON602", "DON603" etc. on who.int/emergencies/disease-outbreak-news
echo "[3/5] Downloading WHO bulletin PDFs..."

WHO_BULLETIN_URLS=(
  # "https://www.who.int/emergencies/disease-outbreak-news/item/PUT-DON602-URL-HERE"
  # "https://www.who.int/emergencies/disease-outbreak-news/item/PUT-DON603-URL-HERE"
)

if [ ${#WHO_BULLETIN_URLS[@]} -eq 0 ]; then
  echo "  -> No WHO bulletin URLs configured yet."
  echo "     Add real PDF links to WHO_BULLETIN_URLS in this script, then re-run."
else
  for url in "${WHO_BULLETIN_URLS[@]}"; do
    filename=$(basename "$url").pdf
    dest="data/who_bulletins/$filename"
    echo "  -> Downloading $url"
    # -f = fail on server errors instead of saving an HTML error page
    # -L = follow redirects
    # -o = save to this path
    curl -f -L -o "$dest" "$url" || echo "     WARNING: failed to download $url"
  done
fi

# -----------------------------------------------------------------------
# STEP 4: Check downloaded files are not broken
# -----------------------------------------------------------------------
# A "broken" download is usually either missing or suspiciously small
# (e.g. an error page saved instead of the real file).
echo "[4/5] Checking downloaded files..."

check_file_size () {
  local file="$1"
  local min_bytes="$2"
  if [ ! -f "$file" ]; then
    echo "  WARNING: expected file missing: $file"
    return
  fi
  local size
  size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file")
  if [ "$size" -lt "$min_bytes" ]; then
    echo "  WARNING: $file is only $size bytes — looks broken/incomplete"
  else
    echo "  OK: $file ($size bytes)"
  fi
}

# Check the dataset actually has files in it
if [ -d "$DATA_DEST" ]; then
  data_file_count=$(find "$DATA_DEST" -type f | wc -l)
  echo "  Dataset contains $data_file_count files."
  if [ "$data_file_count" -eq 0 ]; then
    echo "  WARNING: dataset folder is empty — clone may have failed"
  fi
fi

# Check each WHO PDF (skip if none were downloaded)
shopt -s nullglob
for pdf in data/who_bulletins/*.pdf; do
  check_file_size "$pdf" 1000   # a real PDF should be at least ~1KB
done
shopt -u nullglob

# -----------------------------------------------------------------------
# STEP 5: Create Python virtual environment and install base packages
# -----------------------------------------------------------------------
echo "[5/5] Setting up Python virtual environment..."

if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "  -> Created venv/"
else
  echo "  -> venv/ already exists, skipping creation"
fi

# Write a requirements.txt with the packages we know we'll need this week
cat > requirements.txt << 'EOF'
pandas
numpy
matplotlib
scikit-learn
tensorflow
transformers
fastapi
uvicorn
pydantic
requests
EOF

# Activate venv and install (only works when script is run with 'bash setup.sh',
# note: activation does not persist after the script ends — see message below)
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Setup complete ==="
echo "Folders created: data/, notebooks/, src/, sql/, api/, dashboard/"
echo "Dataset cloned to: $DATA_DEST"
echo "Virtual environment created at: venv/"
echo ""
echo "IMPORTANT: this script's venv activation only applies inside the script."
echo "To activate it in your own terminal, run:"
echo "    source venv/bin/activate"
