# State DOT Bidding Data Scraper

This project scrapes public bidding information from state Department of Transportation (DOT) websites and processes the data into a structured format. The system collects bid documents, downloads PDF files, and extracts bidding data into a SQL database for analysis.

## Overview

The project consists of three main components:

1. **Web Scrapers**: Automatically collect bid document metadata from state DOT websites
2. **PDF Downloader**: Downloads the actual PDF documents from the scraped links
3. **PDF Processor**: Extracts structured data from PDFs and stores it in a SQL database

## Implemented Scrapers

The following state scrapers are currently implemented:

- **Minnesota (MN)**: Scrapes bid results from the Minnesota DOT website
- **South Dakota (SD)**: Scrapes bid documents from the South Dakota DOT website
- **Iowa (IA)**: Scrapes bid tabulations from the Iowa DOT website

Each scraper collects document metadata including document numbers, titles, publication dates, and direct links to PDF files.

## Setup

### Prerequisites

- Python 3.7 or higher
- Google Chrome browser (required for web scraping)
- ChromeDriver (automatically managed by Selenium)

### Installation

1. Clone this repository or download the project files

2. Install the required Python packages:
```bash
pip install -r requirements.txt
```

The main dependencies include:
- Selenium (for web scraping)
- SQLAlchemy (for database operations)
- Pandas (for data manipulation)
- pdfplumber (for PDF text extraction)

## Usage

### Step 1: Scrape State Websites

Run the scrapers to collect bid document information from state websites. This will create a CSV file with document metadata and PDF links.

To scrape all available states:
```bash
python scrapers/run_scrapers.py
```

To scrape specific states, modify the `main()` function in `scrapers/run_scrapers.py` or run individual scrapers:
```bash
python scrapers/MN_scrape.py
python scrapers/SD_scrape.py
python scrapers/IA_scrape.py
```

The scraped data is saved to `data/all_states_documents.csv`.

### Step 2: Download PDF Files

After scraping, download the actual PDF documents:

```bash
python scrapers/download_pdfs.py data/all_states_documents.csv
```

Or use "latest" to automatically use the most recent scraped data:
```bash
python scrapers/download_pdfs.py latest
```

PDFs are organized by state in the `data/downloads/` directory:
- `data/downloads/MN/` - Minnesota PDFs
- `data/downloads/SD/` - South Dakota PDFs
- `data/downloads/IA/` - Iowa PDFs

### Step 3: Process PDFs into Database

Currently, only Minnesota PDFs can be processed into the SQL database. To process MN PDFs:

```bash
python scrapers/MN_pdf_scraper.py
```

This will:
- Read all PDF files from `data/downloads/MN/`
- Extract proposal information, bidder names, bid amounts, and county data
- Store the structured data in a SQLite database at `data/mn_bids.db`

To export the database contents to CSV files:
```bash
python scrapers/MN_pdf_scraper.py --export-csv
```

## Data Storage

### CSV Files

Scraped document metadata is stored in CSV format:
- `data/all_states_documents.csv` - Combined results from all state scrapers
- `data/mn_dot_documents.csv` - Minnesota-specific results
- `data/sd_dot_documents.csv` - South Dakota-specific results
- `data/ia_dot_documents.csv` - Iowa-specific results

### PDF Files

Downloaded PDFs are stored in:
- `data/downloads/[STATE]/` - Organized by state abbreviation

### SQL Database

The Minnesota bidding data is stored in a SQLite database:
- **Location**: `data/mn_bids.db`
- **Tables**:
  - `proposals` - Bid proposal information
  - `bids` - Individual bids submitted for each proposal
  - `proposal_counties` - County associations for each proposal

You can view and query the database using any SQLite browser or command-line tool. The database contains structured data extracted from Minnesota bid tabulation PDFs, including proposal IDs, descriptions, bidder names, bid amounts, and associated counties.

## Current Limitations

- **PDF Processing**: Only Minnesota PDFs can be processed into the SQL database at this time. PDF parsers for South Dakota and Iowa are not yet implemented.
- **Database**: The SQL database currently only contains Minnesota bidding data. Other states' data remains in CSV format until PDF processors are developed.

## Project Structure

```
CSI_Proj/
├── scrapers/          # Web scraping modules
│   ├── MN_scrape.py   # Minnesota website scraper
│   ├── SD_scrape.py   # South Dakota website scraper
│   ├── IA_scrape.py   # Iowa website scraper
│   ├── MN_pdf_scraper.py  # Minnesota PDF processor
│   ├── download_pdfs.py   # PDF download utility
│   └── run_scrapers.py    # Main scraper runner
├── data/              # Data storage directory
│   ├── downloads/     # Downloaded PDF files
│   └── *.csv         # Scraped metadata files
│   └── mn_bids.db    # SQLite database (MN data only)
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

## Notes

- The scrapers use Selenium to automate web browsers, so Chrome must be installed on your system
- Scraping may take some time depending on the number of documents and your internet connection
- The PDF processing step only works with Minnesota bid tabulation documents in the expected format
- All scraped data is publicly available information from state DOT websites

