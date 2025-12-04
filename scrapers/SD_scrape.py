"""
South Dakota DOT Bid Results Scraper
Scrapes "Low Bid Final Report" PDFs from the SD DOT letting archive.
"""

import time
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from base_scraper import BaseDOTScraper


class SDDOTScraper(BaseDOTScraper):
    """South Dakota Department of Transportation scraper."""

    def __init__(self, data_dir=None):
        if data_dir is None:
            csi_dir = Path(__file__).parent.parent
            data_dir = csi_dir / "data"

        super().__init__(
            state_code="SD",
            base_url="https://apps.sd.gov/hc65bidletting/bidlettingscomplete.aspx",
            data_dir=data_dir,
        )

    def scrape(self, years=None):
        """
        Main scraping workflow.

        Args:
            years (iterable[int], optional): Filter results to specific years.

        Returns:
            pandas.DataFrame: Columns = ['year', 'document_title', 'pdf_link']
        """
        year_filter = set(years) if years else None
        records = []

        self.driver.get(self.base_url)
        time.sleep(2)

        rows = self._get_letting_rows()

        print(f"\n{'=' * 60}")
        print(f"Found {len(rows)} letting entries")
        print(f"{'=' * 60}\n")

        for idx, row in enumerate(rows, start=1):
            try:
                listing = self._extract_listing_info(row)
                if not listing:
                    continue

                letting_date = listing["document_title"]
                year = self._extract_year(letting_date)

                if year_filter and (year is None or year not in year_filter):
                    print(f"  → Skipping {letting_date} (year {year}) not in filter")
                    continue

                pdf_link = self._get_low_bid_report(listing["detail_url"])
                if not pdf_link:
                    print(f"  ✗ No 'Low Bid Final Report' found for {letting_date}")
                    continue

                records.append(
                    {
                        "year": year,
                        "document_title": letting_date,
                        "pdf_link": pdf_link,
                    }
                )

                print(f"  ✓ [{idx}] {letting_date} → {pdf_link}")

            except Exception as exc:
                print(f"  ✗ Error processing row {idx}: {exc}")
                continue

        result_df = pd.DataFrame(records)

        print(f"\n{'=' * 60}")
        print("Scraping Complete!")
        print(f"Total documents collected: {len(result_df)}")
        print(f"{'=' * 60}\n")

        return result_df

    def _get_letting_rows(self):
        """Return all letting table rows that contain data cells."""
        try:
            table = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//table")
                )
            )
            return table.find_elements(By.XPATH, ".//tr[td]")
        except TimeoutException:
            print("✗ Unable to locate letting table on the SD DOT page.")
            return []

    def _extract_listing_info(self, row):
        """Extract letting date and detail link from a table row."""
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells:
            return None

        letting_date = cells[0].text.strip()
        if not letting_date:
            return None

        try:
            link_element = row.find_element(By.XPATH, ".//a")
            detail_url = link_element.get_attribute("href")
        except NoSuchElementException:
            return None

        detail_url = self._to_absolute_url(detail_url, fallback=self.base_url)

        return {
            "document_title": letting_date,
            "detail_url": detail_url,
        }

    def _get_low_bid_report(self, detail_url):
        """Open a letting detail page and return the Low Bid Final Report link."""
        if not detail_url:
            return None

        self.driver.execute_script("window.open(arguments[0], '_blank');", detail_url)
        self.switch_to_new_window()
        time.sleep(2)

        pdf_url = None

        try:
            link = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        (
                            "//a[contains(translate(normalize-space(text()), "
                            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                            "'low bid final report')]"
                        ),
                    )
                )
            )
            pdf_url = self._to_absolute_url(link.get_attribute("href"), self.driver.current_url)

        except TimeoutException:
            print("    ✗ Could not locate 'Low Bid Final Report' link.")
        finally:
            self.close_current_tab_and_return()
            time.sleep(1)

        return pdf_url

    def _extract_year(self, text):
        """Attempt to parse a four-digit year from the letting date text."""
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.notna(parsed):
            return int(parsed.year)

        match = re.search(r"(20\d{2})", text)
        if match:
            return int(match.group(1))

        return None

    def _to_absolute_url(self, url, fallback):
        """Convert relative URLs to absolute using the fallback page URL."""
        if not url:
            return None
        if url.startswith("http"):
            return url

        if fallback:
            base = "/".join(fallback.split("/")[:3])
            if url.startswith("/"):
                return f"{base}{url}"
            return f"{base}/{url}"
        return url


def main():
    """Run the scraper standalone."""
    scraper = SDDOTScraper()
    documents_df = scraper.run(headless=False)
    documents_df.insert(0, "state", "SD")

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(documents_df)

    output_file = scraper.data_dir / "sd_dot_documents.csv"
    documents_df.to_csv(output_file, index=False)
    print(f"\n✓ Saved to: {output_file}")

    if len(documents_df) > 0:
        print("\nSummary by Year:")
        print(documents_df.groupby("year").size())


if __name__ == "__main__":
    main()