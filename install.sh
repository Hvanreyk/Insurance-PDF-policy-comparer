#!/bin/bash
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends libgomp1
rm -rf /var/lib/apt/lists/*

pip install -r python-backend/requirements.txt
