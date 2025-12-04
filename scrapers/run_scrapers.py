"""
Utility to run multiple state scrapers and collect results into a unified DataFrame
"""

import sys
from pathlib import Path
import pandas as pd

# Add parent directory to path to import scrapers
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.MN_scrape import MNDOTScraper
from scrapers.SD_scrape import SDDOTScraper
from scrapers.IA_scrape import IADOTScraper


def run_all_scrapers(states=None, headless=True, years=None):
    """
    Run scrapers for specified states and collect results into a unified DataFrame
    
    Args:
        states: List of state codes to scrape (e.g., ['MN', 'SD', 'IA']). 
                If None, runs all available scrapers (MN, SD, IA)
        headless: Whether to run browsers in headless mode
        years: Optional list of years to filter (passed to each scraper)
    
    Returns:
        pandas.DataFrame: Unified DataFrame with columns:
            - state: State code (MN, SD, IA)
            - year: Year of the document
            - doc_number: Document number (MN only, None for others)
            - doc_name: Document name/title
            - pdf_link: Direct download link to PDF
            - scraped_at: Timestamp when record was collected
    """
    if states is None:
        states = ['MN', 'SD', 'IA']
    
    # Map state codes to scraper classes
    scraper_classes = {
        'MN': MNDOTScraper,
        'SD': SDDOTScraper,
        'IA': IADOTScraper
    }
    
    all_records = []
    
    for state_code in states:
        state_code = state_code.upper()
        
        if state_code not in scraper_classes:
            print(f"⚠ Warning: No scraper found for state {state_code}. Skipping.")
            continue
        
        print(f"\n{'='*60}")
        print(f"Running {state_code} scraper...")
        print(f"{'='*60}")
        
        try:
            scraper_class = scraper_classes[state_code]
            scraper = scraper_class()
            
            # Run the scraper
            state_df = scraper.run(headless=headless, years=years)
            
            if state_df is None or len(state_df) == 0:
                print(f"⚠ No documents found for {state_code}")
                continue
            
            # Normalize column names across states
            # MN: [year, doc_number, doc_name, pdf_link]
            # SD: [year, document_title, pdf_link]
            # IA: [year, doc_name, pdf_link]
            
            normalized_df = pd.DataFrame()
            normalized_df['year'] = state_df['year']
            normalized_df['pdf_link'] = state_df['pdf_link']
            
            # Handle doc_name/document_title
            if 'doc_name' in state_df.columns:
                normalized_df['doc_name'] = state_df['doc_name']
            elif 'document_title' in state_df.columns:
                normalized_df['doc_name'] = state_df['document_title']
            else:
                normalized_df['doc_name'] = None
            
            # Handle doc_number (only MN has this)
            if 'doc_number' in state_df.columns:
                normalized_df['doc_number'] = state_df['doc_number']
            else:
                normalized_df['doc_number'] = None
            
            # Add state code
            normalized_df.insert(0, 'state', state_code)
            
            # Add timestamp
            from datetime import datetime
            normalized_df['scraped_at'] = datetime.now().isoformat()
            
            all_records.append(normalized_df)
            
            print(f"✓ {state_code}: Collected {len(normalized_df)} documents")
            
        except Exception as e:
            print(f"✗ Error running {state_code} scraper: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    # Combine all records
    if not all_records:
        print("\n⚠ No records collected from any scraper")
        return pd.DataFrame(columns=['state', 'year', 'doc_number', 'doc_name', 'pdf_link', 'scraped_at'])
    
    combined_df = pd.concat(all_records, ignore_index=True)
    
    print(f"\n{'='*60}")
    print(f"Scraping Complete!")
    print(f"Total documents collected: {len(combined_df)}")
    print(f"States: {combined_df['state'].unique().tolist()}")
    print(f"{'='*60}\n")
    
    return combined_df


def save_results(df, output_path=None):
    """
    Save the collected results to CSV
    
    Args:
        df: DataFrame from run_all_scrapers()
        output_path: Path to save CSV. If None, saves to data/all_states_documents.csv
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "all_states_documents.csv"
    else:
        output_path = Path(output_path)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"✓ Saved results to: {output_path}")
    return output_path


def main():
    """Example usage"""
    # Run all scrapers
    df = run_all_scrapers(states=['MN', 'SD', 'IA'], headless=False)
    
    # Save results
    if len(df) > 0:
        save_results(df)
        
        # Print summary
        print("\nSummary by State:")
        print(df.groupby('state').size())
        
        print("\nSummary by Year:")
        print(df.groupby('year').size())
    else:
        print("\nNo documents collected.")


if __name__ == "__main__":
    main()

