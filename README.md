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

### Future Enhancements (Coming Soon)

- 📋 PDF report generation with detailed comparisons
- 📝 Wording and clause comparison
- 📊 Historical trend analysis across multiple years
- 🔍 OCR support for image-based PDFs

## Technology Stack

- **Frontend**: React 18 with TypeScript
- **Styling**: Tailwind CSS
- **Build Tool**: Vite
- **Icons**: Lucide React
- **Deployment**: Static site (can be hosted on any web server)

## Getting Started

### Prerequisites

- Node.js 18+ and npm

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Usage

1. **Upload Policy A**: Click the left upload area and select the older policy PDF
2. **Upload Policy B**: Click the right upload area and select the newer policy PDF
3. **View Comparison**: The tool will automatically extract data and display the comparison
4. **Download Data**: Click "Download JSON" to export the extracted data for further analysis
5. **New Comparison**: Click "New Comparison" to start over with different files

## How It Works

### PDF Parsing

The tool uses client-side JavaScript to parse PDF text content. It searches for common patterns and keywords to extract:

- Policy metadata (policy number, insurer, insured, dates)
- Sums insured amounts
- Premium components

### Pattern Matching

The parser uses regex patterns to identify key values:

```typescript
// Example patterns
- "Contents Replacement Value: $598,708"
- "Turnover: $1,980,000"
- "Total Premium: $ 4,091.30"
```

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
src/
├── components/
│   ├── PolicyUpload.tsx      # File upload component
│   └── ComparisonView.tsx    # Comparison table and results
├── types/
│   └── policy.ts              # TypeScript interfaces
├── utils/
│   ├── pdfParser.ts           # PDF text extraction logic
│   └── comparison.ts          # Comparison calculations
├── App.tsx                    # Main application component
└── index.css                  # Global styles
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

This MVP has the following limitations:

1. **Text-Only PDFs**: Works best with text-based PDFs. Image-based or scanned PDFs may not parse correctly without OCR.
2. **Pattern Matching**: Relies on common policy document patterns. Custom or unusual formats may require parser updates.
3. **Client-Side Only**: All processing happens in the browser. Large PDFs may take time to process.
4. **No OCR**: Currently does not support optical character recognition for scanned documents.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Security & Privacy

- All PDF processing happens locally in your browser
- No data is sent to any server
- No data is stored or logged
- Safe to use with confidential policy documents

## License

This project is provided as-is for demonstration purposes.

## Support

For questions or issues, please refer to the project documentation or contact the development team.

---

**Note**: This is an MVP (Minimum Viable Product) focused on demonstrating the core concept of automated policy comparison. Future versions will include enhanced features like wording comparison, PDF report generation, and multi-year trend analysis.
