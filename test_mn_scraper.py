"""Quick test script for MN PDF scraper"""
from pathlib import Path
from scrapers.MN_pdf_scraper import MNPdfScraper

# Test on a single file
scraper = MNPdfScraper(db_path="data/test_mn_bids.db")
scraper.debug_mode = True
test_file = Path("data/downloads/MN/MN_36620527.0.pdf")

if test_file.exists():
    print(f"Testing on: {test_file.name}")
    scraper.process_pdf(test_file, debug=True)
    
    # Check what was saved
    summary = scraper.get_summary()
    print(f"\nSummary: {summary['proposals']} proposals, {summary['bids']} bids")
    
    scraper.close()
else:
    print(f"File not found: {test_file}")

