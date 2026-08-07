#!/usr/bin/env bash
cd "$(dirname "$0")"
./cpbl-server.sh start
echo
echo "Open this URL in your browser:"
echo "http://127.0.0.1:8787/"
echo
read -r -p "Press Enter to close this window..."
