"""
MN PDF Scraper - Extracts bidding data from Minnesota DOT PDF documents
"""

import re
import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from sqlalchemy import create_engine, Column, String, Float, Integer, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import pandas as pd

Base = declarative_base()


class Proposal(Base):
    """SQL table for proposals"""
    __tablename__ = 'proposals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    source_file = Column(String(255), nullable=False)
    letting_date = Column(String(100), nullable=True)  # Date from document header
    
    # Relationships
    counties = relationship("ProposalCounty", back_populates="proposal", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="proposal", cascade="all, delete-orphan")


class ProposalCounty(Base):
    """SQL table for proposal-county relationships (many-to-many)"""
    __tablename__ = 'proposal_counties'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(Integer, ForeignKey('proposals.id'), nullable=False)
    county = Column(String(100), nullable=False)
    
    # Relationships
    proposal = relationship("Proposal", back_populates="counties")


class Bid(Base):
    """SQL table for bids"""
    __tablename__ = 'bids'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(Integer, ForeignKey('proposals.id'), nullable=False)
    bidder_name = Column(String(255), nullable=False)
    bid_amount = Column(Float, nullable=False)
    bidder_id = Column(String(50), nullable=True)  # For old format
    comment = Column(Text, nullable=True)
    
    # Relationships
    proposal = relationship("Proposal", back_populates="bids")


class MNPdfScraper:
    """Scraper for Minnesota DOT PDF bidding documents"""
    
    def __init__(self, db_path: str = "data/mn_bids.db"):
        """
        Initialize the scraper
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        # Create tables if they don't exist
        # Note: If schema changes, you may need to delete the DB file to recreate tables
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        
        # Pattern to match old format: "Call order: XXX Proposal: XXXXXX"
        self.old_format_pattern = re.compile(r'Call\s+order:\s*(\d+)\s+Proposal:\s*(\d{6})', re.IGNORECASE)
        
        # Pattern to match new format: "Proposal: XXX--XXXXXX"
        self.new_format_pattern = re.compile(r'Proposal:\s*(\d{3}--\d{6})', re.IGNORECASE)
        
        # Pattern to match counties line
        self.counties_pattern = re.compile(r'Counties?:\s*(.+?)(?:\n|$)', re.IGNORECASE)
        
        # Pattern to match bid amounts (handles various formats)
        self.bid_amount_pattern = re.compile(r'\$?\s*([\d,]+\.?\d*)')
        
        self.processed_files = []
        self.failed_files = []
        self.skipped_files = []
        self.debug_mode = False
    
    def extract_text_from_pdf(self, pdf_path: Path, debug: bool = False) -> Optional[str]:
        """Extract text from PDF file"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                # Check if any text was extracted
                if not text or len(text.strip()) == 0:
                    print(f"  ⚠ No text found in {pdf_path.name} (may be image-based PDF requiring OCR)")
                    return None
                
                if debug:
                    print(f"\n{'='*60}")
                    print(f"EXTRACTED TEXT FROM {pdf_path.name}")
                    print(f"{'='*60}")
                    print(text[:2000])  # Print first 2000 chars
                    if len(text) > 2000:
                        print(f"\n... (truncated, total length: {len(text)} chars)")
                    print(f"{'='*60}\n")
                
                return text
        except Exception as e:
            print(f"  ✗ Error reading PDF {pdf_path.name}: {str(e)}")
            return None
    
    def extract_letting_date(self, text: str) -> Optional[str]:
        """Extract letting date from document header"""
        # Pattern to match: "Apparent Bids for Letting of [DATE]"
        # Examples:
        # - "Apparent Bids for Letting of February 24, 2023"
        # - "Apparent Bids for Letting of October 27, 2023"
        
        patterns = [
            r'Apparent\s+Bids\s+for\s+Letting\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',
            r'Letting\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',
            r'for\s+Letting\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',
        ]
        
        # Look in first 500 characters (header is usually at the top)
        header_text = text[:500] if len(text) > 500 else text
        
        for pattern in patterns:
            match = re.search(pattern, header_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def parse_counties(self, counties_text: str) -> List[str]:
        """Parse counties from text (handles multiple counties separated by commas, spaces, etc.)"""
        if not counties_text:
            return []
        
        # Clean up the text
        counties_text = counties_text.strip()
        
        # Split by common delimiters
        counties = re.split(r'[,;]\s*|\s+AND\s+', counties_text, flags=re.IGNORECASE)
        
        # Clean each county name
        cleaned_counties = []
        for county in counties:
            county = county.strip()
            if county:
                # Remove common prefixes/suffixes
                county = re.sub(r'^(county|co\.?)\s*', '', county, flags=re.IGNORECASE)
                cleaned_counties.append(county)
        
        return cleaned_counties if cleaned_counties else [counties_text]
    
    def parse_bid_amount(self, amount_text: str) -> Optional[float]:
        """Parse bid amount from text"""
        if not amount_text:
            return None
        
        # Remove currency symbols, LaTeX escapes, and whitespace
        amount_text = amount_text.replace('$', '').replace('\\$', '').replace(',', '').strip()
        
        # Try to extract number (handle both integer and decimal)
        match = re.search(r'(\d+\.?\d*)', amount_text)
        if match:
            try:
                value = float(match.group(1))
                # Sanity check: bid amounts should be reasonable (at least $100)
                if value >= 100:
                    return value
            except ValueError:
                return None
        return None
    
    def extract_proposals(self, text: str, source_file: str, letting_date: Optional[str] = None) -> List[Dict]:
        """Extract all proposals from PDF text - handles both old and new formats"""
        proposals = []
        
        # Try to find all proposal sections
        # First, try old format (Call order + Proposal)
        old_matches = list(self.old_format_pattern.finditer(text))
        new_matches = list(self.new_format_pattern.finditer(text))
        
        # Combine and sort by position
        all_matches = []
        for match in old_matches:
            all_matches.append(('old', match))
        for match in new_matches:
            all_matches.append(('new', match))
        
        all_matches.sort(key=lambda x: x[1].start())
        
        if not all_matches:
            return proposals
        
        # Extract each proposal section
        for idx, (format_type, match) in enumerate(all_matches):
            # Determine end of this proposal (start of next, or end of text)
            if idx + 1 < len(all_matches):
                next_start = all_matches[idx + 1][1].start()
                proposal_text = text[match.start():next_start]
            else:
                proposal_text = text[match.start():]
            
            if format_type == 'old':
                call_order = match.group(1)
                proposal_num = match.group(2)
                proposal_id = f"{call_order}--{proposal_num}"
                format_type_str = 'old'
            else:
                proposal_id = match.group(1)
                format_type_str = 'new'
            
            # Extract counties
            counties_match = self.counties_pattern.search(proposal_text)
            counties = []
            if counties_match:
                counties_text = counties_match.group(1).strip()
                counties = self.parse_counties(counties_text)
            
            # Extract description (text between counties and bid table)
            description = ""
            if counties_match:
                counties_end = counties_match.end()
                # Look for table header - more flexible pattern
                table_start = re.search(
                    r'Bidder\s+(?:Name.*Bid\s+Amount|ID|ID\s+Total)',
                    proposal_text[counties_end:],
                    re.IGNORECASE
                )
                if table_start:
                    description = proposal_text[counties_end:counties_end + table_start.start()].strip()
                else:
                    description = proposal_text[counties_end:].strip()
            else:
                # No counties found
                table_start = re.search(
                    r'Bidder\s+(?:Name.*Bid\s+Amount|ID|ID\s+Total)',
                    proposal_text,
                    re.IGNORECASE
                )
                if table_start:
                    description = proposal_text[:table_start.start()].strip()
            
            # Clean up description
            description = re.sub(r'\s+', ' ', description).strip()
            
            # Extract bids based on format
            if format_type_str == 'old':
                bids = self.extract_bids_old_format(proposal_text)
            else:
                bids = self.extract_bids_new_format(proposal_text)
            
            if self.debug_mode and bids:
                print(f"    Debug: Found {len(bids)} bids for proposal {proposal_id}")
                for bid in bids[:3]:  # Show first 3 bids
                    print(f"      - {bid['bidder_name']}: ${bid['bid_amount']:,.2f}")
            
            proposals.append({
                'proposal_id': proposal_id,
                'counties': counties,
                'description': description,
                'bids': bids,
                'source_file': source_file,
                'format': format_type_str,
                'letting_date': letting_date
            })
        
        return proposals
    
    def extract_bids_old_format(self, proposal_text: str) -> List[Dict]:
        """Extract bids from old format: Bidder | Bidder ID | Total"""
        bids = []
        lines = proposal_text.split('\n')
        
        in_bid_table = False
        header_found = False
        
        for line in lines:
            original_line = line
            line = line.strip()
            if not line:
                continue
            
            # Check if we're entering the bid table
            if re.search(r'Bidder.*ID.*Total|Bidder\s+ID', line, re.IGNORECASE):
                in_bid_table = True
                header_found = True
                continue
            
            # Check if we've left the bid table
            if in_bid_table and re.search(r'\(\d+\s+apparent\s+bids?\)', line, re.IGNORECASE):
                break
            
            # Check if we've hit a new proposal
            if in_bid_table and re.match(r'Proposal:\s*\d', line, re.IGNORECASE):
                break
            
            if in_bid_table and header_found:
                # Skip separator lines
                if re.match(r'^[-|=\s]+$', line):
                    continue
                
                # Skip header/metadata lines
                if re.search(r'Letting ID|Cut-off Time|Bid Express|Copyright', line, re.IGNORECASE):
                    continue
                
                # Old format: Bidder Name | Bidder ID | Total
                # Try to find bidder ID (usually a long number like 0000192910, at least 10 digits)
                bidder_id_match = re.search(r'\b(\d{10,})\b', line)
                
                # Find dollar amount - try multiple patterns
                amount = None
                amount_match = None
                
                # Try regular dollar format first
                amount_match = re.search(r'\$\s*([\d,]+\.?\d*)', line)
                if amount_match:
                    amount = self.parse_bid_amount(amount_match.group(0))
                else:
                    # Try without dollar sign
                    amount_match = re.search(r'\b([\d,]+\.\d{2})\b', line)
                    if amount_match:
                        amount = self.parse_bid_amount(amount_match.group(1))
                
                if amount and bidder_id_match:
                    bidder_id = bidder_id_match.group(1)
                    
                    # Extract bidder name (everything before the bidder ID)
                    bidder_name = line[:bidder_id_match.start()].strip()
                    bidder_name = re.sub(r'\s+', ' ', bidder_name).strip()
                    
                    # Skip if bidder name is too short or looks like metadata
                    if len(bidder_name) < 2:
                        continue
                    
                    if bidder_name and not re.match(r'^(Bidder|ID|Total)', bidder_name, re.IGNORECASE):
                        bids.append({
                            'bidder_name': bidder_name,
                            'bid_amount': amount,
                            'bidder_id': bidder_id,
                            'comment': None
                        })
        
        return bids
    
    def extract_bids_new_format(self, proposal_text: str) -> List[Dict]:
        """Extract bids from new format: Bidder Name | Bid Amount | Comment"""
        bids = []
        lines = proposal_text.split('\n')
        
        in_bid_table = False
        header_found = False
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            if not line:
                continue
            
            # Check if we're entering the bid table - more flexible pattern
            # Match "Bidder Name Bid Amount" or "Bidder Name Bid Amount Comment"
            if re.search(r'Bidder\s+Name.*Bid\s+Amount', line, re.IGNORECASE):
                in_bid_table = True
                header_found = True
                continue
            
            # Check if we've left the bid table
            if in_bid_table and re.search(r'\(\d+\s+apparent\s+bids?\)', line, re.IGNORECASE):
                break
            
            # Check if we've hit a new proposal (starts with "Proposal:")
            if in_bid_table and re.match(r'Proposal:\s*\d', line, re.IGNORECASE):
                break
            
            # Check if we've hit a new section (like "Copyright" or page header)
            if in_bid_table and (re.search(r'Copyright|Minnesota Department of Transportation', line, re.IGNORECASE) or
                                 re.match(r'^\d+\s+of\s+\d+$', line)):
                # This might be a page break, continue but be careful
                continue
            
            if in_bid_table and header_found:
                # Skip separator lines
                if re.match(r'^[-|=\s]+$', line):
                    continue
                
                # Skip lines that are clearly headers or metadata
                if re.search(r'Letting ID|Cut-off Time|Bid Express', line, re.IGNORECASE):
                    continue
                
                # New format: Bidder Name | Bid Amount | Comment
                # Look for dollar amount - try multiple patterns
                amount = None
                amount_start = None
                amount_end = None
                
                # Pattern 1: LaTeX format $\$ X,XXX.XX$
                latex_amount_match = re.search(r'\$\\\$?\s*([\d,]+\.?\d*)', line)
                if latex_amount_match:
                    amount_text = latex_amount_match.group(0)
                    amount = self.parse_bid_amount(amount_text.replace('\\$', '$'))
                    amount_start = latex_amount_match.start()
                    amount_end = latex_amount_match.end()
                else:
                    # Pattern 2: Regular dollar format $X,XXX.XX
                    amount_match = re.search(r'\$\s*([\d,]+\.?\d*)', line)
                    if amount_match:
                        amount_text = amount_match.group(0)
                        amount = self.parse_bid_amount(amount_text)
                        amount_start = amount_match.start()
                        amount_end = amount_match.end()
                    else:
                        # Pattern 3: Just numbers with commas (fallback)
                        amount_match = re.search(r'\b([\d,]+\.\d{2})\b', line)
                        if amount_match:
                            amount = self.parse_bid_amount(amount_match.group(1))
                            amount_start = amount_match.start()
                            amount_end = amount_match.end()
                
                if amount and amount_start is not None:
                    # Extract bidder name (everything before the amount)
                    bidder_name = line[:amount_start].strip()
                    bidder_name = re.sub(r'\s+', ' ', bidder_name).strip()
                    bidder_name = bidder_name.replace('\\&', '&')
                    
                    # Skip if bidder name is too short or looks like metadata
                    if len(bidder_name) < 2:
                        continue
                    
                    # Skip if it looks like a header or metadata line
                    if re.match(r'^(Bidder|Name|Amount|Comment|Total|ID)', bidder_name, re.IGNORECASE):
                        continue
                    
                    # Extract comment (everything after the amount)
                    comment = None
                    if amount_end < len(line):
                        after_amount = line[amount_end:].strip()
                        # Look for comment in parentheses
                        comment_match = re.search(r'\(([^)]+)\)', after_amount)
                        if comment_match:
                            comment = comment_match.group(1).strip()
                        elif after_amount and not re.match(r'^\d+', after_amount):
                            # Only use as comment if it doesn't look like another number
                            if not re.match(r'^\d+[\d,\.]+', after_amount):
                                comment = after_amount.strip()
                    
                    # Final validation: bidder name should not be just numbers
                    if bidder_name and not re.match(r'^\d+$', bidder_name) and amount > 0:
                        bids.append({
                            'bidder_name': bidder_name,
                            'bid_amount': amount,
                            'bidder_id': None,
                            'comment': comment
                        })
        
        return bids
    
    def validate_proposal_format(self, proposal: Dict) -> bool:
        """Validate that proposal matches expected format"""
        # Must have proposal_id
        if not proposal.get('proposal_id'):
            return False
        
        # Must have at least one county or description
        if not proposal.get('counties') and not proposal.get('description'):
            return False
        
        # Should have at least one bid
        if not proposal.get('bids'):
            return False
        
        return True
    
    def save_to_database(self, proposals: List[Dict]) -> Tuple[int, int]:
        """Save proposals to database"""
        saved_count = 0
        skipped_count = 0
        
        for proposal_data in proposals:
            try:
                # Check if proposal already exists
                existing = self.session.query(Proposal).filter_by(
                    proposal_id=proposal_data['proposal_id']
                ).first()
                
                if existing:
                    # Update existing proposal
                    proposal = existing
                    proposal.description = proposal_data.get('description')
                    proposal.source_file = proposal_data['source_file']
                    if proposal_data.get('letting_date'):
                        proposal.letting_date = proposal_data['letting_date']
                    
                    # Clear existing relationships
                    self.session.query(ProposalCounty).filter_by(proposal_id=proposal.id).delete()
                    self.session.query(Bid).filter_by(proposal_id=proposal.id).delete()
                else:
                    # Create new proposal
                    proposal = Proposal(
                        proposal_id=proposal_data['proposal_id'],
                        description=proposal_data.get('description'),
                        source_file=proposal_data['source_file'],
                        letting_date=proposal_data.get('letting_date')
                    )
                    self.session.add(proposal)
                    self.session.flush()  # Get the ID
                
                # Add counties
                for county_name in proposal_data.get('counties', []):
                    county = ProposalCounty(
                        proposal_id=proposal.id,
                        county=county_name
                    )
                    self.session.add(county)
                
                # Add bids
                for bid_data in proposal_data.get('bids', []):
                    bid = Bid(
                        proposal_id=proposal.id,
                        bidder_name=bid_data['bidder_name'],
                        bid_amount=bid_data['bid_amount'],
                        bidder_id=bid_data.get('bidder_id'),
                        comment=bid_data.get('comment')
                    )
                    self.session.add(bid)
                
                self.session.commit()
                saved_count += 1
                
                if self.debug_mode:
                    print(f"    Debug: Saved proposal {proposal_data['proposal_id']} with {len(proposal_data.get('bids', []))} bids")
                
            except Exception as e:
                self.session.rollback()
                print(f"  ✗ Error saving proposal {proposal_data.get('proposal_id')}: {str(e)}")
                skipped_count += 1
        
        return saved_count, skipped_count
    
    def process_pdf(self, pdf_path: Path, debug: bool = False) -> bool:
        """Process a single PDF file"""
        print(f"  Processing: {pdf_path.name}")
        
        # Extract text
        text = self.extract_text_from_pdf(pdf_path, debug=debug)
        if not text:
            self.failed_files.append(str(pdf_path))
            return False
        
        # Extract letting date from document header
        letting_date = self.extract_letting_date(text)
        if self.debug_mode and letting_date:
            print(f"    Debug: Found letting date: {letting_date}")
        
        # Extract proposals
        proposals = self.extract_proposals(text, pdf_path.name, letting_date=letting_date)
        
        if not proposals:
            print(f"    ⚠ No proposals found in {pdf_path.name}")
            if debug:
                print(f"    Debug: Text length: {len(text)}, first 500 chars: {text[:500]}")
            self.skipped_files.append(str(pdf_path))
            return False
        
        # Validate and filter proposals
        valid_proposals = []
        invalid_proposals = []
        
        for proposal in proposals:
            if self.validate_proposal_format(proposal):
                valid_proposals.append(proposal)
            else:
                invalid_proposals.append(proposal)
                if debug:
                    print(f"    Debug: Invalid proposal {proposal.get('proposal_id')}: "
                          f"counties={len(proposal.get('counties', []))}, "
                          f"bids={len(proposal.get('bids', []))}, "
                          f"description={bool(proposal.get('description'))}")
        
        if not valid_proposals:
            print(f"    ⚠ {len(invalid_proposals)} proposal(s) in {pdf_path.name} don't match expected format")
            self.skipped_files.append(str(pdf_path))
            return False
        
        # Save to database
        saved, skipped = self.save_to_database(valid_proposals)
        print(f"    ✓ Saved {saved} proposal(s), skipped {skipped}")
        
        self.processed_files.append(str(pdf_path))
        return True
    
    def process_directory(self, directory: Path, debug: bool = False) -> Dict[str, int]:
        """Process all PDF files in a directory"""
        pdf_files = list(directory.glob("*.pdf"))
        
        print(f"\n{'='*60}")
        print(f"Processing {len(pdf_files)} PDF files from {directory}")
        print(f"{'='*60}\n")
        
        for pdf_path in pdf_files:
            self.process_pdf(pdf_path, debug=debug)
        
        return {
            'processed': len(self.processed_files),
            'failed': len(self.failed_files),
            'skipped': len(self.skipped_files),
            'total': len(pdf_files)
        }
    
    def export_to_csv(self, output_dir: Path = None):
        """Export database to CSV files"""
        if output_dir is None:
            output_dir = Path("data/mn_bids_export")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export proposals (already includes letting_date from SELECT *)
        proposals_df = pd.read_sql(
            "SELECT * FROM proposals ORDER BY letting_date, proposal_id",
            self.engine
        )
        proposals_df.to_csv(output_dir / "proposals.csv", index=False)
        
        # Export counties with proposal_id string
        counties_df = pd.read_sql("""
            SELECT 
                p.proposal_id,
                pc.id,
                pc.county
            FROM proposal_counties pc
            JOIN proposals p ON pc.proposal_id = p.id
            ORDER BY p.proposal_id, pc.county
        """, self.engine)
        counties_df.to_csv(output_dir / "proposal_counties.csv", index=False)
        
        # Export bids with proposal_id string
        bids_df = pd.read_sql("""
            SELECT 
                p.proposal_id,
                b.id,
                b.bidder_name,
                b.bid_amount,
                b.bidder_id,
                b.comment
            FROM bids b
            JOIN proposals p ON b.proposal_id = p.id
            ORDER BY p.proposal_id, b.bid_amount
        """, self.engine)
        bids_df.to_csv(output_dir / "bids.csv", index=False)
        
        # Export combined view
        combined_df = pd.read_sql("""
            SELECT 
                p.proposal_id,
                p.letting_date,
                p.description,
                p.source_file,
                GROUP_CONCAT(pc.county, ', ') as counties,
                b.bidder_name,
                b.bid_amount,
                b.bidder_id,
                b.comment
            FROM proposals p
            LEFT JOIN proposal_counties pc ON p.id = pc.proposal_id
            LEFT JOIN bids b ON p.id = b.proposal_id
            GROUP BY p.id, b.id
            ORDER BY p.proposal_id, b.bid_amount
        """, self.engine)
        combined_df.to_csv(output_dir / "combined_bids.csv", index=False)
        
        print(f"\n✓ Exported data to {output_dir}")
        print(f"  - proposals.csv")
        print(f"  - proposal_counties.csv")
        print(f"  - bids.csv")
        print(f"  - combined_bids.csv")
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        proposal_count = self.session.query(Proposal).count()
        bid_count = self.session.query(Bid).count()
        county_count = self.session.query(ProposalCounty).count()
        
        return {
            'proposals': proposal_count,
            'bids': bid_count,
            'counties': county_count,
            'processed_files': len(self.processed_files),
            'failed_files': len(self.failed_files),
            'skipped_files': len(self.skipped_files)
        }
    
    def close(self):
        """Close database session"""
        self.session.close()


def main():
    """Main function to run the scraper"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape MN DOT PDF bidding documents')
    parser.add_argument('--input-dir', type=str, default='data/downloads/MN',
                       help='Directory containing MN PDF files')
    parser.add_argument('--db-path', type=str, default='data/mn_bids.db',
                       help='Path to SQLite database file')
    parser.add_argument('--export-csv', action='store_true',
                       help='Export results to CSV files')
    parser.add_argument('--csv-dir', type=str, default='data/mn_bids_export',
                       help='Directory for CSV exports')
    parser.add_argument('--debug', action='store_true',
                       help='Print extracted text for inspection')
    
    args = parser.parse_args()
    
    # Initialize scraper
    scraper = MNPdfScraper(db_path=args.db_path)
    scraper.debug_mode = args.debug
    
    try:
        # Process PDFs
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            print(f"✗ Error: Directory {input_dir} does not exist")
            return
        
        results = scraper.process_directory(input_dir, debug=args.debug)
        
        # Print summary
        print(f"\n{'='*60}")
        print("Processing Summary")
        print(f"{'='*60}")
        print(f"Total files: {results['total']}")
        print(f"Processed: {results['processed']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped (non-matching format): {results['skipped']}")
        
        # Database summary
        summary = scraper.get_summary()
        print(f"\nDatabase Summary")
        print(f"{'='*60}")
        print(f"Proposals: {summary['proposals']}")
        print(f"Bids: {summary['bids']}")
        print(f"County entries: {summary['counties']}")
        
        # Export to CSV if requested
        if args.export_csv:
            scraper.export_to_csv(Path(args.csv_dir))
        
        # Print skipped files if any
        if scraper.skipped_files:
            print(f"\n{'='*60}")
            print("Skipped Files (non-matching format):")
            print(f"{'='*60}")
            for file in scraper.skipped_files:
                print(f"  - {Path(file).name}")
        
    finally:
        scraper.close()


if __name__ == "__main__":
    main()

