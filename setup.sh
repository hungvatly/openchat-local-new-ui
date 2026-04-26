#!/bin/bash
# ─────────────────────────────────────────────
# OpenChat Local — Docker Setup
# ─────────────────────────────────────────────

set -e

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║       OpenChat Local Setup       ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "  ✗ Docker not found. Install it from https://docs.docker.com/get-docker/"
    exit 1
fi
echo "  ✓ Docker found"

if ! docker compose version &> /dev/null; then
    echo "  ✗ Docker Compose not found. Install it from https://docs.docker.com/compose/install/"
    exit 1
fi
echo "  ✓ Docker Compose found"

# Ask for documents folder
echo ""
DEFAULT_DOCS="$HOME/Documents"
read -p "  Documents folder to watch [$DEFAULT_DOCS]: " DOCS_FOLDER
DOCS_FOLDER="${DOCS_FOLDER:-$DEFAULT_DOCS}"

if [ ! -d "$DOCS_FOLDER" ]; then
    echo "  ✗ Folder not found: $DOCS_FOLDER"
    exit 1
fi
echo "  ✓ Will watch: $DOCS_FOLDER"

# Update docker-compose with the correct path
sed -i.bak "s|~/Documents:/documents:ro|$DOCS_FOLDER:/documents:ro|g" docker-compose.yml
rm -f docker-compose.yml.bak

# Create data directory
mkdir -p data

# Build and start
echo ""
echo "  Starting containers (this may take a few minutes on first run)..."
echo ""
docker compose up -d --build

# Wait for Ollama to be ready
echo ""
echo "  Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "  ✓ Ollama is ready"
        break
    fi
    sleep 2
done

# Pull the model
echo ""
echo "  Pulling qwen2.5:1.5b model (this will take a minute)..."
docker exec ollama ollama pull qwen2.5:1.5b

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║          Setup Complete!         ║"
echo "  ╠══════════════════════════════════╣"
echo "  ║                                  ║"
echo "  ║  Open: http://localhost:8000     ║"
echo "  ║                                  ║"
echo "  ║  Watching: $DOCS_FOLDER"
echo "  ║  Model: qwen2.5:1.5b            ║"
echo "  ║                                  ║"
echo "  ║  Commands:                       ║"
echo "  ║  Stop:    docker compose down    ║"
echo "  ║  Start:   docker compose up -d   ║"
echo "  ║  Logs:    docker compose logs -f ║"
echo "  ║                                  ║"
echo "  ╚══════════════════════════════════╝"
echo ""
