# FinanceNarrate AI

Executive Financial Insight Engine that transforms raw financial data into board-ready narratives using AI.

## Overview

FinanceNarrate AI is a web application that processes financial CSV/Excel files and generates executive-level insights and recommendations. It combines data analysis with AI-powered narrative generation to create comprehensive financial reports.

## Features

- **File Upload & Validation**: Supports CSV, XLSX, and XLS files with required columns (Date, Revenue, Expenses, Category)
- **Financial Metrics**: Automated calculation of key financial indicators and trends
- **Anomaly Detection**: Identifies unusual patterns in financial data
- **AI Narratives**: Generates executive summaries, trend analysis, and recommendations using Google Gemini
- **Interactive Dashboard**: Visual charts and data preview with modern web interface
- **Report Export**: Copy or download complete reports

## Project Structure

```
finance-narrate-ai-main/
├── finance_narrate/
│   ├── backend/
│   │   ├── main.py              # FastAPI application
│   │   ├── models.py            # Pydantic data models
│   │   ├── processor.py         # Financial data processing
│   │   ├── llm_client.py        # Gemini AI integration
│   │   ├── requirements.txt     # Python dependencies
│   │   ├── .env.example         # Environment variables template
│   │   └── tests/               # Test suite
│   ├── frontend/
│   │   ├── index.html           # Main dashboard
│   │   ├── dashboard.js         # Frontend logic
│   │   └── styles.css           # Styling
│   └── sample_data/
│       └── sample_finance.csv   # Example data file
```

## Setup

### Prerequisites

- Python 3.8+
- Google Gemini API key

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd finance-narrate-ai-main
   ```

2. **Install Python dependencies**
   ```bash
   cd finance_narrate/backend
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

4. **Start the backend server**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Open the frontend**
   - Open `finance_narrate/frontend/index.html` in your browser
   - Or serve it with a local web server for better CORS handling

## Usage

1. **Upload Data**: Drag and drop or select a CSV/Excel file with columns: Date, Revenue, Expenses, Category
2. **View Analysis**: Automatic processing generates financial metrics and charts
3. **Generate Narrative**: AI creates executive summary with insights and recommendations
4. **Export Report**: Copy to clipboard or download as text file

## API Endpoints

- `GET /health` - Health check
- `POST /upload` - Upload and validate financial data file
- `POST /analyze/{file_id}` - Process data and calculate metrics
- `POST /generate-narrative/{file_id}` - Generate AI narrative
- `GET /report/{file_id}` - Get complete report (metrics + narrative)

## Required Data Format

Your CSV/Excel file must contain these columns:
- **Date**: Transaction date
- **Revenue**: Revenue amount
- **Expenses**: Expense amount  
- **Category**: Expense/revenue category

## Development

### Running Tests
```bash
cd finance_narrate/backend
pytest
```

### Environment Variables
- `GEMINI_API_KEY`: Your Google Gemini API key (required for narrative generation)

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]