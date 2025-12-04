"""
Base scraper class for state DOT websites
All state-specific scrapers should inherit from this class
"""

import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class BaseDOTScraper(ABC):
    """Abstract base class for DOT scrapers"""
    
    def __init__(self, state_code, base_url, data_dir=None):
        """
        Initialize the scraper
        
        Args:
            state_code: Two-letter state code (e.g., 'MN', 'ND')
            base_url: Starting URL for the scraper
            data_dir: Directory to save downloaded files
        """
        self.state_code = state_code.upper()
        self.base_url = base_url
        
        if data_dir is None:
            data_dir = f"../data/{state_code.lower()}_dot"
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.driver = None
        self.wait = None
        self.documents_scraped = []
    
    def setup_driver(self, headless=False):
        """Initialize Selenium WebDriver with Chrome"""
        chrome_options = webdriver.ChromeOptions()
        
        # PDF download settings
        prefs = {
            "download.default_directory": str(self.data_dir.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        if headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
    
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def switch_to_new_window(self):
        """Switch to the most recently opened window"""
        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
    
    def close_current_tab_and_return(self):
        """Close current tab and return to main window"""
        if len(self.driver.window_handles) > 1:
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
    
    @abstractmethod
    def scrape(self, **kwargs):
        """
        Main scraping method - must be implemented by subclass
        
        Returns:
            list: List of dictionaries containing scraped document info
        """
        pass
    
    def run(self, headless=False, **kwargs):
        """
        Execute the scraper
        
        Args:
            headless: Run browser in headless mode
            **kwargs: Additional arguments passed to scrape()
        
        Returns:
            list: List of scraped documents
        """
        print(f"\n{'='*60}")
        print(f"Starting {self.state_code} DOT Scraper")
        print(f"{'='*60}")
        
        try:
            self.setup_driver(headless=headless)
            self.documents_scraped = self.scrape(**kwargs)
            
            print(f"\n{'='*60}")
            print(f"{self.state_code} scraping complete!")
            print(f"Total documents processed: {len(self.documents_scraped)}")
            print(f"{'='*60}\n")
            
            return self.documents_scraped
        
        except Exception as e:
            print(f"✗ Error during {self.state_code} scraping: {str(e)}")
            raise
        
        finally:
            self.close_driver()
    
    def download_pdf(self, pdf_url, filename=None):
        """
        Download a PDF file
        
        Args:
            pdf_url: URL of the PDF
            filename: Optional filename to save as
        
        Returns:
            str: Path to downloaded file
        """
        try:
            # Navigate to PDF URL to trigger download
            self.driver.get(pdf_url)
            time.sleep(2)  # Wait for download to start
            
            if filename:
                # Wait for download to complete and rename if needed
                time.sleep(3)
            
            return str(self.data_dir / (filename or "downloaded.pdf"))
        
        except Exception as e:
            print(f"✗ Error downloading PDF: {str(e)}")
            return None
    
    def create_document_record(self, doc_number, doc_name, url, year=None, 
                               additional_data=None):
        """
        Create a standardized document record
        
        Args:
            doc_number: Document identifier
            doc_name: Document name
            url: Document URL
            year: Year of document
            additional_data: Dict of additional fields
        
        Returns:
            dict: Standardized document record
        """
        record = {
            'state_code': self.state_code,
            'doc_number': doc_number,
            'doc_name': doc_name,
            'url': url,
            'year': year,
            'scraped_at': datetime.now().isoformat(),
            'file_path': None
        }
        
        if additional_data:
            record.update(additional_data)
        
        return record

