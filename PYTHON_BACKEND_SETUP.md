# Python Backend Setup Guide

Your app now uses a Python FastAPI backend for PDF parsing instead of TypeScript. This gives you much better control for complex regex and semantic extraction.

## Architecture

- **Frontend**: React + TypeScript (UI only)
- **Backend**: Python + FastAPI (PDF parsing, comparison)
- **Communication**: REST API calls from frontend to backend

## Local Development Setup

### 1. Install Python Backend

```bash
cd python-backend

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux
# OR
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Python Backend

```bash
# Make sure you're in python-backend/ and venv is activated
python main.py
```

Backend runs on: http://localhost:8000

### 3. Run Frontend (in separate terminal)

```bash
# Back to project root
cd ..

# Start frontend
npm run dev
```

Frontend runs on: http://localhost:5173

## How It Works

1. User uploads PDF in React frontend
2. Frontend sends PDF to Python API: `POST /api/parse-policy`
3. Python extracts data using `pdfplumber` (way better than PDF.js!)
4. Python returns structured JSON
5. Frontend displays the data

## Customizing PDF Extraction

Edit `python-backend/pdf_parser.py`:

```python
def extract_premium_table(text: str, pages: list):
    # Your custom extraction logic here
    # Use pdfplumber's table extraction
    # Use regex, semantic analysis, etc.

    for page in pages:
        tables = page.extract_tables()
        # Process tables...
```

## Benefits of Python Backend

1. **Better PDF parsing** - pdfplumber handles complex tables perfectly
2. **Powerful regex** - Python regex is cleaner than TypeScript
3. **NLP libraries** - Easy to add spaCy, transformers, etc.
4. **Faster iteration** - Easier to test and debug extraction logic
5. **Production ready** - Easy to deploy FastAPI

## Deployment

### Option 1: Railway.app (Easiest)
1. Push `python-backend/` to GitHub
2. Connect Railway to repo
3. Set root directory to `python-backend`
4. Railway auto-deploys

### Option 2: Render.com
1. New Web Service → Connect repo
2. Root directory: `python-backend`
3. Build: `pip install -r requirements.txt`
4. Start: `python main.py`

### Option 3: Fly.io
```bash
cd python-backend
fly launch
fly deploy
```

### After Deployment
Update `.env` in your frontend:
```
VITE_PYTHON_API_URL=https://your-backend.railway.app
```

## API Endpoints

### GET /
Health check

### POST /api/parse-policy
Upload single PDF
- Body: `multipart/form-data` with `file` field
- Returns: Structured policy data

### POST /api/compare-policies
Upload two PDFs
- Body: `multipart/form-data` with `policy_a` and `policy_b` files
- Returns: Both policies + comparison

## Next Steps

1. Improve `extract_premium_table()` in `pdf_parser.py`
2. Add more extraction patterns
3. Add semantic analysis (spaCy, transformers)
4. Store parsed data in Supabase
5. Add caching layer (Redis)
6. Deploy backend to production

## Testing Locally

```bash
# Terminal 1: Python backend
cd python-backend
source venv/bin/activate
python main.py

# Terminal 2: Frontend
npm run dev

# Upload PDFs and check:
# - Browser Network tab for API calls
# - Python terminal for logs
# - Console for extracted data
```
