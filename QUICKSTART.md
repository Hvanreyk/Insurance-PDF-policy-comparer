# Quick Start Guide

## Important: Two-Service Architecture

This app requires **TWO services running**:
1. **Python Backend** (PDF parsing)
2. **React Frontend** (UI)

## Local Development Setup

### 1. Start Python Backend

```bash
cd python-backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Backend runs on: http://localhost:8000

### 2. Start Frontend (New Terminal)

```bash
# From project root
npm install
npm run dev
```

Frontend runs on: http://localhost:5173

### 3. Upload Two PDFs
- Click left panel → select older policy (Year A)
- Click right panel → select newer policy (Year B)

### 4. View Comparison
- See side-by-side comparison with color-coded changes
- Download JSON data for further analysis

## Deploy to Production

### Deploy Python Backend to Railway

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Add Python backend"
   git push
   ```

2. **In Railway Dashboard**:
   - New Project → Deploy from GitHub
   - Select your repo
   - Set **Root Directory**: `python-backend`
   - Deploy
   - Copy your Railway URL (e.g., `https://your-app.railway.app`)

3. **Update Frontend `.env`**:
   ```bash
   VITE_PYTHON_API_URL=https://your-app.railway.app
   ```

### Deploy Frontend

**Option A: Deploy to Railway (Same Project)**
- Add new service from same GitHub repo
- Root directory: `.` (project root)
- Build: `npm install && npm run build`
- Start: `npx vite preview --port $PORT --host`

**Option B: Deploy to Vercel/Netlify**
- Build command: `npm run build`
- Output directory: `dist`
- Add environment variable: `VITE_PYTHON_API_URL`

## What You'll See

### Upload Screen
```
┌─────────────────────────────────────────────────┐
│  Insurance Policy Comparison Tool               │
│  Compare policies side-by-side                  │
├─────────────────┬───────────────────────────────┤
│  Policy Year A  │  Policy Year B                │
│  (Older)        │  (Newer)                      │
│                 │                               │
│  [Upload PDF]   │  [Upload PDF]                 │
│                 │                               │
└─────────────────┴───────────────────────────────┘
```

### Comparison Screen
```
┌─────────────────────────────────────────────────┐
│  Policy Comparison                              │
│  2021 vs 2022                    [Download JSON]│
├─────────────┬─────────┬─────────┬────────┬──────┤
│ Field       │ Year A  │ Year B  │ Δ ($)  │ Δ(%) │
├─────────────┼─────────┼─────────┼────────┼──────┤
│ Contents    │ 578,462 │ 598,708 │ +20,246│ +3.5%│ (blue)
│ Theft       │  70,000 │  70,000 │      0 │  0.0%│ (gray)
│ BI Turnover │1,950,000│1,980,000│ +30,000│ +1.5%│ (blue)
│ Total Prem  │ 4,031.37│ 4,091.30│   +59.93│+1.5%│ (red)
└─────────────┴─────────┴─────────┴────────┴──────┘
```

## Color Coding

- 🔴 **Red** = Premium increased (bad)
- 🟢 **Green** = Premium decreased (good)
- 🔵 **Blue** = Coverage increased (good)
- 🟠 **Orange** = Coverage decreased (bad)
- ⚪ **Gray** = No change

## Commands

```bash
# Development
npm run dev          # Start dev server

# Building
npm run build        # Build for production
npm run preview      # Preview production build

# Quality
npm run lint         # Run ESLint
npm run typecheck    # Check TypeScript types
```

## Sample PDFs

The tool works with standard insurance policy PDFs. It extracts:

### Policy Metadata
- Policy number
- Insurer name
- Insured name
- Policy dates
- Policy year

### Sums Insured
- Contents
- Theft (Contents & Stock)
- Business Interruption (Turnover)
- Public Liability
- Property in Control

### Premium Components
- Base/Nett Premium
- FSL/ESL
- GST
- Stamp Duty
- Total Premium

## Troubleshooting

### PDF Not Parsing?
- Ensure PDF contains selectable text (not scanned image)
- Check PDF is from a standard insurer format
- Try exporting PDF as text to verify it's readable

### Values Not Extracted?
- PDF might use non-standard formatting
- Check raw JSON to see what was extracted
- May need to update parser patterns for your PDFs

### Build Errors?
```bash
# Clear cache and reinstall
rm -rf node_modules dist
npm install
npm run build
```

## Next Steps

1. **Test with your PDFs**: Upload real policy documents
2. **Check extraction accuracy**: Compare with actual policy values
3. **Customize colors**: Edit `ComparisonView.tsx` if needed
4. **Add features**: See IMPLEMENTATION.md for enhancement ideas
5. **Deploy**: Use Vercel, Netlify, or any static host

## Need Help?

- 📖 Read [README.md](README.md) for detailed documentation
- 🔧 Check [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details
- 📋 See [SUMMARY.md](SUMMARY.md) for project overview

---

**That's it! You're ready to compare insurance policies.**
