"""
Utility to download PDFs from the collected download links
"""

import sys
from pathlib import Path
import pandas as pd
import requests
from urllib.parse import urlparse
import time
from datetime import datetime


def download_pdf(pdf_url, output_dir, filename=None, timeout=30):
    """
    Download a single PDF file
    
    Args:
        pdf_url: URL of the PDF to download
        output_dir: Directory to save the PDF
        filename: Optional filename. If None, generates from URL
        timeout: Request timeout in seconds
    
    Returns:
        dict: Result with keys: success, file_path, error_message
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename if not provided
    if filename is None:
        # Extract filename from URL
        parsed = urlparse(pdf_url)
        filename = Path(parsed.path).name
        
        # If no filename in URL, use a default
        if not filename or filename == '/':
            filename = f"document_{int(time.time())}.pdf"
        
        # Ensure .pdf extension
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
    
    file_path = output_dir / filename
    
    try:
        # Download the PDF
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Save to file
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return {
            'success': True,
            'file_path': str(file_path),
            'error_message': None
        }
    
    except Exception as e:
        return {
            'success': False,
            'file_path': None,
            'error_message': str(e)
        }


def download_pdfs_from_dataframe(df, base_output_dir=None, state_subdirs=True, 
                                 delay=1.0, max_retries=3):
    """
    Download PDFs from a DataFrame containing pdf_link column
    
    Args:
        df: DataFrame with columns: state, pdf_link, and optionally doc_name, doc_number
        base_output_dir: Base directory for downloads. If None, uses data/downloads/
        state_subdirs: If True, creates subdirectories for each state
        delay: Delay between downloads in seconds (to be polite to servers)
        max_retries: Maximum number of retry attempts for failed downloads
    
    Returns:
        pandas.DataFrame: Original DataFrame with added columns:
            - download_status: 'success', 'failed', or 'skipped'
            - download_path: Path to downloaded file (if successful)
            - download_error: Error message (if failed)
            - downloaded_at: Timestamp of download attempt
    """
    if base_output_dir is None:
        base_output_dir = Path(__file__).parent.parent / "data" / "downloads"
    else:
        base_output_dir = Path(base_output_dir)
    
    # Initialize result columns
    result_df = df.copy()
    result_df['download_status'] = None
    result_df['download_path'] = None
    result_df['download_error'] = None
    result_df['downloaded_at'] = None
    
    total = len(df)
    print(f"\n{'='*60}")
    print(f"Starting PDF downloads")
    print(f"Total PDFs to download: {total}")
    print(f"Output directory: {base_output_dir}")
    print(f"{'='*60}\n")
    
    for idx, row in df.iterrows():
        pdf_url = row.get('pdf_link')
        state = row.get('state', 'unknown')
        doc_name = row.get('doc_name', '')
        doc_number = row.get('doc_number', '')
        
        if not pdf_url or pd.isna(pdf_url):
            result_df.at[idx, 'download_status'] = 'skipped'
            result_df.at[idx, 'download_error'] = 'No PDF link provided'
            result_df.at[idx, 'downloaded_at'] = datetime.now().isoformat()
            print(f"[{idx+1}/{total}] ⚠ Skipped: No PDF link")
            continue
        
        # Determine output directory
        if state_subdirs:
            output_dir = base_output_dir / state.upper()
        else:
            output_dir = base_output_dir
        
        # Generate filename
        filename = None
        if doc_number and not pd.isna(doc_number):
            # Use doc_number as filename if available
            filename = f"{state}_{doc_number}.pdf"
        elif doc_name and not pd.isna(doc_name):
            # Use doc_name, sanitized
            safe_name = "".join(c for c in doc_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_')[:100]  # Limit length
            filename = f"{state}_{safe_name}.pdf"
        
        # Download with retries
        success = False
        error_msg = None
        file_path = None
        
        for attempt in range(1, max_retries + 1):
            result = download_pdf(pdf_url, output_dir, filename)
            
            if result['success']:
                success = True
                file_path = result['file_path']
                break
            else:
                error_msg = result['error_message']
                if attempt < max_retries:
                    print(f"    Retry {attempt}/{max_retries-1}...")
                    time.sleep(delay * attempt)  # Exponential backoff
        
        # Update result
        result_df.at[idx, 'download_status'] = 'success' if success else 'failed'
        result_df.at[idx, 'download_path'] = file_path
        result_df.at[idx, 'download_error'] = error_msg
        result_df.at[idx, 'downloaded_at'] = datetime.now().isoformat()
        
        # Print status
        status_icon = "✓" if success else "✗"
        doc_id = doc_number if doc_number and not pd.isna(doc_number) else doc_name[:50] if doc_name else "unknown"
        print(f"[{idx+1}/{total}] {status_icon} {state}: {doc_id}")
        if not success:
            print(f"    Error: {error_msg}")
        
        # Delay between downloads
        if idx < total - 1:  # Don't delay after last download
            time.sleep(delay)
    
    # Print summary
    success_count = (result_df['download_status'] == 'success').sum()
    failed_count = (result_df['download_status'] == 'failed').sum()
    skipped_count = (result_df['download_status'] == 'skipped').sum()
    
    print(f"\n{'='*60}")
    print(f"Download Complete!")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"{'='*60}\n")
    
    return result_df


def download_pdfs_from_csv(csv_path, output_dir=None, **kwargs):
    """
    Load DataFrame from CSV and download PDFs
    
    Args:
        csv_path: Path to CSV file with scraped data
        output_dir: Base directory for downloads
        **kwargs: Additional arguments passed to download_pdfs_from_dataframe()
    
    Returns:
        pandas.DataFrame: DataFrame with download results
    """
    df = pd.read_csv(csv_path)
    return download_pdfs_from_dataframe(df, output_dir, **kwargs)


def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download PDFs from scraped data')
    parser.add_argument('input', type=str, 
                       help='Path to CSV file with scraped data, or "latest" to use most recent')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory for downloads (default: data/downloads/)')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='Delay between downloads in seconds (default: 1.0)')
    parser.add_argument('--no-state-dirs', action='store_true',
                       help='Do not create subdirectories for each state')
    
    args = parser.parse_args()
    
    # Determine input file
    if args.input.lower() == 'latest':
        data_dir = Path(__file__).parent.parent / "data"
        csv_files = list(data_dir.glob("all_states_documents.csv"))
        if not csv_files:
            print("✗ No all_states_documents.csv found. Run run_scrapers.py first.")
            return
        input_path = csv_files[0]
    else:
        input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"✗ Input file not found: {input_path}")
        return
    
    # Download PDFs
    result_df = download_pdfs_from_csv(
        input_path,
        output_dir=args.output_dir,
        state_subdirs=not args.no_state_dirs,
        delay=args.delay
    )
    
    # Save results
    output_csv = input_path.parent / f"{input_path.stem}_with_downloads.csv"
    result_df.to_csv(output_csv, index=False)
    print(f"✓ Saved download results to: {output_csv}")


if __name__ == "__main__":
    main()

