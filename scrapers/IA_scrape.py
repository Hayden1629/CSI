"""
Iowa DOT Bid Tabulations Scraper
Scrapes bid tabulation PDFs from Iowa DOT website

HTML Structure Notes:
- Base URL: https://iowadot.gov/consultants-contractors/contracts/historical-completed-lettings/bid-tabulations
- Uses pagination: ?page=0, ?page=1, etc.
- Each document is in a <div class="views-row"> container
- Title/date in <h2> tag like "10/22/25 Bid Tabulations"
- Download link in <a> tag with href like "/media/12608/download?inline"
- Total count in <div class="view-header">: "Displaying X - Y of Z results"
"""

import time
import re
from datetime import datetime
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from base_scraper import BaseDOTScraper
import pandas as pd


class IADOTScraper(BaseDOTScraper):
    def __init__(self, data_dir=None):
        """Initialize the IA DOT scraper"""
        # Set default data_dir to CSI/data if not provided
        if data_dir is None:
            # Get the CSI directory (two levels up from scrapers/)
            csi_dir = Path(__file__).parent.parent
            data_dir = csi_dir / "data"
        
        super().__init__(
            state_code='IA',
            base_url='https://iowadot.gov/consultants-contractors/contracts/historical-completed-lettings/bid-tabulations',
            data_dir=data_dir
        )
    
    def scrape(self, years=None):
        """
        Main scraping method - collects metadata without downloading
        
        Strategy:
        1. Determine total number of results and pages needed
        2. Loop through each page
        3. Extract all document info from views-row containers
        
        Args:
            years: List of years to filter (optional)
        
        Returns:
            pandas.DataFrame: DataFrame with columns [year, doc_name, pdf_link]
        """
        all_records = []
        
        # Navigate to first page
        self.driver.get(self.base_url)
        time.sleep(3)  # Wait for page to load
        
        # Get total count and calculate pages
        total_results, items_per_page = self.get_result_count()
        
        if total_results == 0:
            print("No results found!")
            return pd.DataFrame()
        
        # Calculate number of pages
        num_pages = (total_results + items_per_page - 1) // items_per_page
        
        print(f"\n{'='*60}")
        print(f"Found {total_results} total documents across {num_pages} page(s)")
        print(f"{'='*60}\n")
        
        # Loop through all pages
        for page_num in range(num_pages):
            print(f"\n[Page {page_num + 1}/{num_pages}]")
            
            # Navigate to page (skip first since we're already there)
            if page_num > 0:
                page_url = f"{self.base_url}?page={page_num}"
                self.driver.get(page_url)
                time.sleep(2)
            
            # Extract documents from this page
            page_records = self.extract_page_documents()
            all_records.extend(page_records)
            
            print(f"  → Extracted {len(page_records)} documents from page {page_num + 1}")
        
        # Create final DataFrame
        result_df = pd.DataFrame(all_records)
        
        # Filter by years if specified
        if years and len(result_df) > 0:
            result_df = result_df[result_df['year'].isin(years)]
        
        print(f"\n{'='*60}")
        print(f"Scraping Complete!")
        print(f"Total documents collected: {len(result_df)}")
        print(f"{'='*60}\n")
        
        return result_df
    
    def get_result_count(self):
        """
        Parse the view-header to get total result count
        Example: "Displaying 1 - 20 of 33 results."
        
        Returns:
            tuple: (total_results, items_per_page)
        """
        try:
            view_header = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "view-header"))
            )
            header_text = view_header.text.strip()
            print(f"View header: {header_text}")
            
            # Parse "Displaying X - Y of Z results."
            match = re.search(r'Displaying\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)', header_text)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                total = int(match.group(3))
                items_per_page = end - start + 1
                return total, items_per_page
            else:
                # If no match, might be single page - count items directly
                print("Could not parse header, counting items directly...")
                return self.count_items_on_page(), 20  # Default to 20 per page
        
        except (TimeoutException, NoSuchElementException):
            print("Could not find view-header, counting items directly...")
            return self.count_items_on_page(), 20
    
    def count_items_on_page(self):
        """Count the number of views-row items on current page"""
        try:
            rows = self.driver.find_elements(By.CLASS_NAME, "views-row")
            return len(rows)
        except:
            return 0
    
    def extract_page_documents(self):
        """
        Extract all document information from current page
        
        Returns:
            list: List of document dictionaries
        """
        records = []
        
        try:
            # Find all views-row containers
            rows = self.driver.find_elements(By.CLASS_NAME, "views-row")
            print(f"  Found {len(rows)} document containers on page")
            
            for idx, row in enumerate(rows, 1):
                try:
                    # Extract link and title
                    link_element = row.find_element(By.CSS_SELECTOR, "a.link__link-collection-document")
                    pdf_link = link_element.get_attribute('href')
                    
                    # Get title from h2
                    title = row.find_element(By.TAG_NAME, "h2").text.strip()
                    
                    # Parse year from title (e.g., "10/22/25 Bid Tabulations")
                    year = self.parse_year_from_title(title)
                    
                    # Convert relative URL to absolute if needed
                    if pdf_link and not pdf_link.startswith('http'):
                        base_url = '/'.join(self.driver.current_url.split('/')[:3])
                        if pdf_link.startswith('/'):
                            pdf_link = base_url + pdf_link
                    
                    records.append({
                        'year': year,
                        'doc_name': title,
                        'pdf_link': pdf_link
                    })
                    
                    print(f"    [{idx}] {title} ({year})")
                
                except Exception as e:
                    print(f"    ✗ Error extracting document {idx}: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"  ✗ Error finding document containers: {str(e)}")
        
        return records
    
    def parse_year_from_title(self, title):
        """
        Extract year from title like "10/22/25 Bid Tabulations" or "11/19/2024 Bid Tabulation"
        
        Args:
            title: Document title string
        
        Returns:
            int: Four-digit year (e.g., 2025) or None
        """
        # First, look for date pattern MM/DD/YYYY (4-digit year)
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', title)
        if match:
            return int(match.group(3))
        
        # Then look for date pattern MM/DD/YY (2-digit year)
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2})(?!\d)', title)
        if match:
            year_2digit = int(match.group(3))
            # Convert 2-digit year to 4-digit (assume 20xx for years < 50, 19xx otherwise)
            year = 2000 + year_2digit if year_2digit < 50 else 1900 + year_2digit
            return year
        
        # Finally, look for 4-digit year anywhere in title
        match = re.search(r'(20\d{2})', title)
        if match:
            return int(match.group(1))
        
        return None


def main():
    """Run the scraper standalone"""
    scraper = IADOTScraper()
    documents_df = scraper.run(headless=False)
    
    # Add state column
    documents_df.insert(0, 'state', 'IA')
    
    # Display the results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(documents_df)
    
    # Save to CSV
    output_file = scraper.data_dir / "ia_dot_documents.csv"
    documents_df.to_csv(output_file, index=False)
    print(f"\n✓ Saved to: {output_file}")
    
    # Display summary by year
    if len(documents_df) > 0 and 'year' in documents_df.columns:
        print("\nSummary by Year:")
        print(documents_df.groupby('year').size())


if __name__ == "__main__":
    main()