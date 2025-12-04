"""
Minnesota DOT Bid Results Scraper
Scrapes apparent bid results PDFs from MN DOT website for years 2023-2025
"""

import time
from datetime import datetime
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from base_scraper import BaseDOTScraper
import pandas as pd


class MNDOTScraper(BaseDOTScraper):
    def __init__(self, data_dir=None):
        """Initialize the MN DOT scraper"""
        # Set default data_dir to CSI/data if not provided
        if data_dir is None:
            # Get the CSI directory (two levels up from scrapers/)
            csi_dir = Path(__file__).parent.parent
            data_dir = csi_dir / "data"
        
        super().__init__(
            state_code='MN',
            base_url='https://www.dot.state.mn.us/bidlet/postletting.html',
            data_dir=data_dir
        )
    
    
    def scrape(self, years=None):
        """
        Main scraping method - collects metadata without downloading
        Two-layer strategy:
        1. Get year folders (layer 1) 
        2. For each year, get all documents (layer 2)
        3. For each document, get PDF link
        
        Args:
            years: List of years to scrape (defaults to all available)
        
        Returns:
            pandas.DataFrame: DataFrame with columns [year, doc_number, doc_name, pdf_link]
        """
        all_records = []
        
        # Layer 1: Get year folders
        self.click_apparent_bid_results()
        year_folders = self.get_table_data()
        
        print(f"\n{'='*60}")
        print(f"Found {len(year_folders)} year folders")
        print(f"{'='*60}\n")
        
        # Layer 2: Process each year folder
        for idx, year_row in year_folders.iterrows():
            year_name = year_row['doc_name']
            year_link = year_row['link_url']
            
            print(f"\n[{idx+1}/{len(year_folders)}] Processing: {year_name}")
            
            # Navigate to year folder in new tab
            self.driver.execute_script(f"window.open('{year_link}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            try:
                # Get all documents in this year
                documents_df = self.get_table_data()
                
                print(f"  → Found {len(documents_df)} documents in {year_name}")
                
                # Collect document info (no need to open each page)
                for doc_idx, doc_row in documents_df.iterrows():
                    doc_number = doc_row['doc_number']
                    doc_name = doc_row['doc_name']
                    doc_link = doc_row['link_url']
                    
                    print(f"    [{doc_idx+1}/{len(documents_df)}] {doc_number}: {doc_name}")
                    
                    # Extract year as integer (first 4 characters)
                    year_int = int(year_name[:4])
                    
                    # Add to records - use the document page link directly
                    all_records.append({
                        'year': year_int,
                        'doc_number': str(doc_number),
                        'doc_name': doc_name,
                        'pdf_link': doc_link  # Link from the table
                    })
            
            except Exception as e:
                print(f"  ✗ Error processing {year_name}: {str(e)}")
            
            finally:
                # Close year tab and return to main window
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                time.sleep(1)
        
        # Create final DataFrame
        result_df = pd.DataFrame(all_records)
        
        print(f"\n{'='*60}")
        print(f"Scraping Complete!")
        print(f"Total documents collected: {len(result_df)}")
        print(f"{'='*60}\n")
        
        return result_df


    def click_apparent_bid_results(self):
        """Navigate to main page and click Apparent bid results link"""
        self.driver.get(self.base_url)
        time.sleep(2)  # Wait for page to load
        
        # Use the exact XPath from your CSV - note lowercase 'bid results'
        link = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[normalize-space()='Apparent bid results']")
            )
        )
        link.click()
        print("✓ Clicked 'Apparent bid results'")
        
        # Switch to new window if it opened one
        time.sleep(2)
        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
            print("✓ Switched to new window")

    def get_table_data(self):
        """
        Get table data using pandas AND selenium to capture both text and links
        Returns: DataFrame with columns [doc_number, doc_name, link_url]
        """
        time.sleep(2)  # Wait for page to load
        
        # Get table text data with pandas - use first row as header
        df = pd.read_html(self.driver.page_source, header=0)[0]
        print("\nTable data from pandas:")
        print(df)
        print(f"DataFrame has {len(df)} rows and {len(df.columns)} columns")
        print(f"Column names: {list(df.columns)}")
        
        # Get the actual link URLs with Selenium
        table = self.driver.find_element(By.XPATH, "//table")
        all_rows = table.find_elements(By.XPATH, ".//tr")
        
        print(f"Table has {len(all_rows)} total rows (including header)")
        
        # Get links from data rows only (skip header)
        # Need to get the current base URL to convert relative links to absolute
        current_url = self.driver.current_url
        base_url = '/'.join(current_url.split('/')[:3])  # Get https://domain.com
        print(f"Current URL: {current_url}")
        print(f"Base URL for converting relative links: {base_url}")
        
        links = []
        for row in all_rows[1:]:  # Skip header row
            link_elements = row.find_elements(By.TAG_NAME, "a")
            if link_elements:
                href = link_elements[0].get_attribute('href')
                original_href = href
                
                # If href doesn't start with http, it's relative - make it absolute
                if href and not href.startswith('http'):
                    if href.startswith('/'):
                        href = base_url + href
                    print(f"  Converted relative link: {original_href} -> {href}")
                
                links.append(href)
            else:
                links.append(None)
        
        print(f"Found {len(links)} links")
        
        # Make sure lengths match
        if len(df) != len(links):
            print(f"⚠ Warning: DataFrame has {len(df)} rows but found {len(links)} links")
            # Trim to shortest length
            min_len = min(len(df), len(links))
            df = df.iloc[:min_len]
            links = links[:min_len]
        
        # Add links to dataframe
        df['link_url'] = links
        
        # Handle different table structures
        # Keep only first two columns (doc number and name) plus our link column
        if len(df.columns) > 3:
            print(f"⚠ Table has {len(df.columns)} columns, keeping first 2 + link")
            # Keep first two columns plus the link_url we just added
            df = df.iloc[:, [0, 1, -1]]
        
        # Rename columns for consistency
        df.columns = ['doc_number', 'doc_name', 'link_url']
        
        # Remove rows without links
        df = df[df['link_url'].notna()].reset_index(drop=True)
        
        print(f"Final DataFrame has {len(df)} rows with links\n")
        
        return df


def main():
    """Run the scraper standalone"""
    scraper = MNDOTScraper()
    documents_df = scraper.run(headless=True)
    documents_df.insert(0, 'state', 'MN')
    
    # Display the results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(documents_df) # this object will be what is returned to other functions for adding to the all state database
    
    # Save to CSV
    output_file = scraper.data_dir / "mn_dot_documents.csv"
    documents_df.to_csv(output_file, index=False)
    print(f"\n✓ Saved to: {output_file}")
    
    # Display summary by year
    print("\nSummary by Year:")
    print(documents_df.groupby('year').size())


if __name__ == "__main__":
    main()