# Insurance Policy Comparison Tool

A web-based tool for comparing two versions of the same insurance policy PDF, extracting key dollar amounts, and displaying differences side-by-side.

## Overview

This MVP tool is designed for insurance brokers and clients to quickly compare policies year-over-year. It focuses on extracting and comparing key numerical data:

- **Sums Insured**: Contents, Theft, Business Interruption, Public Liability, Property in Control
- **Premium Components**: Base Premium, FSL/ESL, GST, Stamp Duty, Total Premium
- **Visual Comparison**: Color-coded increases and decreases with percentage changes

## Features

### Current Implementation

- ✅ Upload two policy PDFs for comparison
- ✅ Automatic extraction of key dollar amounts
- ✅ Side-by-side comparison table with:
  - Color-coded changes (red for premium increases, blue for coverage increases)
  - Absolute dollar changes
  - Percentage changes
- ✅ JSON export of extracted data and comparison results
- ✅ Responsive design for desktop and mobile
- ✅ Clean, modern UI with clear visual hierarchy

### Advanced Features

- ✅ Wording and clause comparison (UCC - Universal Clause Comparer)
- 📋 PDF report generation with detailed comparisons (planned)
- 📊 Historical trend analysis across multiple years (planned)
- 🔍 OCR support for image-based PDFs (planned)

## Technology Stack

- **Frontend**: React 18 with TypeScript
- **Backend**: Python FastAPI with pdfplumber
- **Styling**: Tailwind CSS
- **Build Tool**: Vite
- **Icons**: Lucide React

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Python 3.11+

### Installation

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.

**Quick Setup:**

1. **Start Python Backend:**
```bash
cd python-backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

2. **Start Frontend (new terminal):**
```bash
npm install
npm run dev
```

### Usage

1. **Upload Policy A**: Click the left upload area and select the older policy PDF
2. **Upload Policy B**: Click the right upload area and select the newer policy PDF
3. **View Comparison**: The tool will automatically extract data and display the comparison
4. **Download Data**: Click "Download JSON" to export the extracted data for further analysis
5. **New Comparison**: Click "New Comparison" to start over with different files

## How It Works

### PDF Parsing

The tool uses a Python FastAPI backend with pdfplumber to parse PDF documents. The backend extracts:

- Policy metadata (policy number, insurer, insured, dates)
- Sums insured amounts
- Premium components
- Clause-level text blocks for wording comparison

### API Endpoints

- `POST /api/parse-policy`: Parse a single policy PDF
- `POST /api/compare-policies`: Compare two policy PDFs (numeric)
- `POST /api/compare-clauses`: Compare policy wordings at clause level (UCC)

### Comparison Logic

For each extracted field, the tool calculates:

- **Delta (Absolute)**: Year B value - Year A value
- **Delta (Percentage)**: ((Year B - Year A) / Year A) × 100

### Color Coding

- **Red**: Premium increases (bad for client)
- **Green**: Premium decreases (good for client)
- **Blue**: Coverage/sum insured increases (good for client)
- **Orange**: Coverage/sum insured decreases (bad for client)

## Project Structure

```
├── src/                                    # React Frontend
│   ├── components/
│   │   ├── PolicyUpload.tsx               # PDF upload component
│   │   ├── ComparisonView.tsx             # Numeric comparison table
│   │   ├── PolicyWordingComparator.tsx    # Clause comparison UI
│   │   ├── ClauseComparerUpload.tsx       # Clause comparer upload
│   │   ├── EditablePolicyData.tsx         # Editable policy data
│   │   └── clause/                        # Clause comparison components
│   ├── types/
│   │   ├── policy.ts                      # Policy data interfaces
│   │   └── clauseComparison.ts            # UCC interfaces
│   ├── utils/
│   │   ├── pythonApiClient.ts             # Backend API client
│   │   ├── comparison.ts                  # Comparison calculations
│   │   └── clauseFilters.ts               # Clause filtering logic
│   ├── App.tsx                            # Main application component
│   └── index.css                          # Global styles
│
└── python-backend/                         # Python FastAPI Backend
    ├── main.py                            # FastAPI application
    ├── pdf_parser.py                      # PDF extraction
    ├── comparison.py                      # Policy comparison
    ├── requirements.txt                   # Python dependencies
    └── ucc/                               # Universal Clause Comparer
        ├── pipeline.py                    # UCC pipeline
        ├── models_ucc.py                  # UCC data models
        └── ...                            # Additional UCC modules
```

## Data Format

### PolicyData Interface

```typescript
interface PolicyData {
  policy_year?: string;
  insurer?: string;
  insured?: string;
  policy_number?: string;
  period_of_insurance?: {
    from: string;  // YYYY-MM-DD
    to: string;    // YYYY-MM-DD
  };
  sums_insured: {
    contents?: number;
    theft_total?: number;
    bi_turnover?: number;
    public_liability?: number;
    property_in_your_control?: number;
  };
  premium: {
    base?: number;
    fsl?: number;
    gst?: number;
    stamp?: number;
    total?: number;
  };
}
```

## Limitations

1. **Text-Only PDFs**: Works best with text-based PDFs. Image-based or scanned PDFs may not parse correctly without OCR.
2. **Pattern Matching**: Relies on common policy document patterns. Custom or unusual formats may require parser updates.
3. **No OCR**: Currently does not support optical character recognition for scanned documents.

## Troubleshooting

### Build fails with “no space left on device”

The development dependencies occupy a significant amount of disk space (roughly 150 MB in `node_modules` alone).【0fcb97†L1-L23】 When running the project inside a constrained container or CI environment the build cache can exhaust the available storage, triggering errors such as:

```
copy_file_range: no space left on device
```

To resolve this:

- Remove cached build layers or prune Docker/BuildKit storage before retrying the build.
- Ensure the environment provides sufficient free disk space (at least several hundred megabytes) before starting `npm install` or `npm run build`.
- If space is tight, consider using `npm ci --prefer-offline` or a remote build cache to minimise duplicate downloads.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Security & Privacy

- PDFs are processed by the backend and not persisted to disk
- No data is permanently stored or logged
- Suitable for confidential policy documents in a trusted deployment environment

## License

This project is provided as-is for demonstration purposes.

## Support

For questions or issues, please refer to the project documentation or contact the development team.

---

**Note**: This is an MVP (Minimum Viable Product) focused on demonstrating the core concept of automated policy comparison. Future versions will include enhanced features like wording comparison, PDF report generation, and multi-year trend analysis.
