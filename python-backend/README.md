# Insurance Policy Parser - Python Backend

FastAPI backend for parsing insurance policy PDFs and comparing them.

## Setup

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Run the server:
```bash
python main.py
```

Server runs on http://localhost:8000

## API Endpoints

### POST /api/parse-policy
Upload a single PDF to parse
- Body: multipart/form-data with `file` field
- Returns: JSON with extracted policy data

### POST /api/compare-policies
Upload two PDFs to compare
- Body: multipart/form-data with `policy_a` and `policy_b` files
- Returns: JSON with both policies and comparison results

## Deployment Options

### Option 1: Railway.app (Recommended)
1. Push code to GitHub
2. Connect Railway to your repo
3. Railway auto-detects Python and deploys

### Option 2: Render.com
1. Push code to GitHub
2. Create new Web Service on Render
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `python main.py`

### Option 3: Fly.io
```bash
fly launch
fly deploy
```

### Option 4: Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```
