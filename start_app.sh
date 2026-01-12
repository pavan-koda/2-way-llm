
#!/bin/bash

# Define project directory
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Local AI System - Startup Script     ${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. Navigate to project directory
if [ -d "$BASE_DIR" ]; then
    cd "$BASE_DIR"
    echo -e "${GREEN}✅ Directory found: $BASE_DIR${NC}"
else
    echo -e "${RED}❌ Error: Directory $BASE_DIR not found.${NC}"
    exit 1
fi

# 2. Activate Virtual Environment
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  venv not found. Creating one...${NC}"
    python3 -m venv venv
fi

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✅ Virtual Environment Activated${NC}"
else
    echo -e "${RED}❌ Error: venv creation failed.${NC}"
    exit 1
fi

if ! pip freeze | grep -q "fastapi"; then
    if [ -f "requirements.txt" ]; then
        echo -e "${BLUE}📥 Installing dependencies...${NC}"
        pip install -r requirements.txt
    fi
fi

# 3. Check for Documents
count=$(ls documents/*.pdf 2>/dev/null | wc -l)
if [ "$count" -eq "0" ]; then
    echo -e "${YELLOW}⚠️  Warning: No PDFs found in 'documents' folder.${NC}"
else
    echo -e "${GREEN}📄 Found $count PDF(s).${NC}"
fi

# 4. Ingestion Prompt
echo ""
read -p "❓ Run ingestion? (y/N): " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🚀 Starting Ingestion...${NC}"
    python ingest.py
    echo -e "${GREEN}✅ Ingestion Finished.${NC}"
else
    echo -e "${YELLOW}⏩ Skipping Ingestion.${NC}"
fi

# 5. Start Server
echo ""
echo -e "${BLUE}🚀 Starting Web Server...${NC}"
echo -e "   Access at: ${GREEN}http://localhost:8000${NC}"
echo -e "${BLUE}========================================${NC}"
python server.py
