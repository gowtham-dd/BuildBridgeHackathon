"""
Test Suite — 15 evaluation cases for hackathon scoring
Each test covers: summary (2pts) + entities (4pts) + sentiment (4pts) = 10pts per test

Usage:
    python tests/test_api.py --url http://localhost:8000 --key your_api_key

Scoring:
    - summary  : checks for non-empty, min length, and relevant keywords
    - entities : checks each category has at least expected minimum count
    - sentiment: exact match against expected value
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Literal

import requests


# ── Test Case Definition ───────────────────────────────────────────────────────

@dataclass
class TestCase:
    id: int
    name: str
    file_type: Literal["pdf", "docx", "image"]
    description: str
    # Minimum expected entity counts per category (0 = don't check)
    min_names: int = 0
    min_dates: int = 0
    min_orgs: int = 0
    min_amounts: int = 0
    min_locations: int = 0
    expected_sentiment: str = ""        # empty = don't check
    summary_keywords: list[str] = field(default_factory=list)
    min_summary_length: int = 50
    _doc_content: str = ""              # internal: text content to embed in test doc


# ── Synthetic Document Generator ──────────────────────────────────────────────

def _make_pdf_bytes(text: str) -> bytes:
    """Create a minimal valid PDF containing the given text."""
    lines = text.split("\n")
    pdf_lines = []
    y = 750
    for line in lines[:60]:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        pdf_lines.append(f"BT /F1 11 Tf 50 {y} Td ({safe}) Tj ET")
        y -= 16
        if y < 50:
            break
    content = "\n".join(pdf_lines)

    objects = [
        b"",  # placeholder index 0
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj",
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj".encode(),
        f"4 0 obj\n<< /Length {len(content)} >>\nstream\n{content}\nendstream\nendobj".encode(),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj",
    ]

    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects):
        if i == 0:
            continue
        offsets.append(len(pdf))
        pdf += obj + b"\n"

    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return pdf


def _make_docx_bytes(text: str) -> bytes:
    """Create a minimal valid DOCX containing the given text."""
    from docx import Document as DocxDocument

    doc = DocxDocument()
    for para in text.split("\n"):
        if para.strip():
            doc.add_paragraph(para.strip())
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── Test Case Definitions ──────────────────────────────────────────────────────

def build_test_cases() -> list[TestCase]:
    return [
        TestCase(
            id=1, name="Corporate Earnings Report", file_type="pdf",
            description="Q3 2024 financial results",
            min_orgs=1, min_dates=1, min_amounts=2,
            expected_sentiment="positive",
            summary_keywords=["revenue", "growth", "quarter"],
            _doc_content="""Q3 2024 Earnings Report – TechNova Corporation
Date: October 15, 2024

TechNova Corporation reported record revenue of $2.4 billion for Q3 2024,
representing a 32% year-over-year growth. CEO Sarah Mitchell announced the
results in a press conference held in San Francisco, California.

Net income reached $480 million, up from $320 million in Q3 2023.
The company expanded into European markets with a new office in Berlin, Germany,
and acquired DataStream Analytics for $150 million on September 2, 2024.

CFO James Rodriguez confirmed guidance for FY2024 at $9.2 billion in revenue.
The board of directors approved a quarterly dividend of $0.85 per share.""",
        ),
        TestCase(
            id=2, name="Employment Contract", file_type="docx",
            description="Job offer and employment terms",
            min_names=2, min_dates=1, min_amounts=1, min_orgs=1,
            expected_sentiment="neutral",
            summary_keywords=["employment", "contract", "position"],
            _doc_content="""EMPLOYMENT AGREEMENT
Between: GlobalTech Solutions Inc. ("Employer")
And: Dr. Priya Sharma ("Employee")

Position: Senior Data Scientist
Start Date: January 6, 2025
Location: Austin, Texas

Compensation:
- Annual Salary: $145,000
- Signing Bonus: $10,000 (payable on February 1, 2025)
- Annual Performance Bonus: up to 20% of base salary

Benefits include health insurance, 401(k) with 4% employer match, and 20 days PTO.
This agreement is governed by the laws of the State of Texas.
Both parties, John Walker (HR Director) and Dr. Priya Sharma, must sign by December 20, 2024.""",
        ),
        TestCase(
            id=3, name="Negative Product Review", file_type="pdf",
            description="Customer complaint about software product",
            min_orgs=1,
            expected_sentiment="negative",
            summary_keywords=["review", "product", "issue"],
            _doc_content="""Customer Feedback Report – ProjectFlow Pro v4.2
Submitted: March 8, 2024
Customer: Marcus Johnson, Acme Logistics LLC

This software has been an absolute disaster for our team.
Since upgrading to version 4.2 on February 14, 2024, we have experienced:
- Constant crashes when importing Excel files larger than 50MB
- Data loss incidents on 3 separate occasions totaling 40 hours of lost work
- Completely unresponsive support team despite paying $3,200/year for Enterprise tier

We have lost approximately $25,000 in productivity over the past three weeks.
Our office in Chicago, Illinois has reverted to manual spreadsheets.
This is unacceptable and we demand a full refund from TechBridge Software Inc.""",
        ),
        TestCase(
            id=4, name="Medical Research Abstract", file_type="pdf",
            description="Clinical trial results",
            min_names=1, min_dates=1, min_orgs=1, min_amounts=1,
            expected_sentiment="positive",
            summary_keywords=["trial", "patients", "treatment"],
            _doc_content="""Clinical Trial Results: Phase III Study of CardioShield-X
Published: May 22, 2024 | Journal of Cardiovascular Medicine
Principal Investigator: Dr. Elena Vasquez, Johns Hopkins University

Abstract:
This Phase III randomized controlled trial enrolled 2,847 patients across 12 hospitals
in New York, Boston, and Los Angeles between January 2022 and December 2023.

The CardioShield-X treatment group showed a 67% reduction in major adverse cardiac events
compared to the placebo group (p < 0.001). Funded by the National Institutes of Health
with a grant of $4.2 million.

Conclusion: CardioShield-X demonstrates significant clinical efficacy with a favorable
safety profile. Dr. Michael Chen and Dr. Aisha Patel co-authored this study.
FDA approval submission is planned for Q3 2024.""",
        ),
        TestCase(
            id=5, name="Real Estate Lease Agreement", file_type="docx",
            description="Commercial property lease",
            min_names=2, min_dates=2, min_amounts=2, min_locations=1,
            expected_sentiment="neutral",
            summary_keywords=["lease", "property", "rent"],
            _doc_content="""COMMERCIAL LEASE AGREEMENT

Landlord: Harbor Properties LLC, represented by Thomas Bennett
Tenant: Sunrise Café & Bakery, represented by Anna Kowalski

Property: 1842 Ocean Drive, Suite 101, Miami, Florida 33139
Lease Term: February 1, 2025 to January 31, 2028

Monthly Rent: $4,500 for first 12 months
             $4,725 (months 13–24)
             $4,961 (months 25–36)
Security Deposit: $9,000 due by January 15, 2025

Permitted Use: Restaurant and bakery operations only.
Utilities: Tenant responsible for electricity and internet.
This agreement signed on December 28, 2024.""",
        ),
        TestCase(
            id=6, name="News Article – Natural Disaster", file_type="pdf",
            description="Breaking news about hurricane damage",
            min_dates=1, min_locations=2, min_amounts=1,
            expected_sentiment="negative",
            summary_keywords=["hurricane", "damage", "evacuated"],
            _doc_content="""BREAKING: Hurricane Marlene Causes Catastrophic Damage
Gulf Coast Daily | September 18, 2024

Hurricane Marlene made landfall near Tampa, Florida at 3:15 AM on September 17, 2024,
bringing 145 mph winds and a record storm surge of 18 feet.

The cities of Tampa, Clearwater, and St. Petersburg suffered catastrophic flooding.
Governor Rebecca Holloway declared a state of emergency across 14 counties.
FEMA Director Carlos Espinoza stated that estimated damages exceed $8.7 billion.

Over 340,000 residents were evacuated before landfall. At least 23 fatalities have
been confirmed in Hillsborough County and Pinellas County.
President issued a federal disaster declaration for the region on September 18, 2024.
Red Cross shelters have been opened across Orlando and Gainesville.""",
        ),
        TestCase(
            id=7, name="Invoice Document", file_type="pdf",
            description="B2B invoice with line items",
            min_orgs=1, min_dates=1, min_amounts=3,
            expected_sentiment="neutral",
            summary_keywords=["invoice", "payment", "services"],
            _doc_content="""INVOICE #INV-2024-0847
Date: November 1, 2024
Due Date: November 30, 2024

From: Nexus Digital Agency
      350 5th Avenue, New York, NY 10118

To: BlueWave Marketing Solutions
    88 Market Street, San Francisco, CA 94105
    Attn: Finance Department

SERVICES RENDERED:
- Website redesign (October 2024): $12,000.00
- SEO optimization package: $3,500.00
- Social media campaign management: $2,200.00
- Analytics dashboard setup: $1,800.00

Subtotal: $19,500.00
Tax (8.875%): $1,730.63
TOTAL DUE: $21,230.63

Payment via bank transfer to Account #4521-8833, Routing #021000089.
Late fee of 1.5% per month applies after due date.""",
        ),
        TestCase(
            id=8, name="Academic Research Paper", file_type="pdf",
            description="Machine learning research paper",
            min_names=1, min_dates=1, min_orgs=1,
            expected_sentiment="positive",
            summary_keywords=["model", "accuracy", "learning"],
            _doc_content="""Transformer-Based Approach to Low-Resource Language Translation
Authors: Wei Zhang, Fatima Al-Hassan, Robert O'Brien
Affiliation: MIT Computer Science & Artificial Intelligence Laboratory (CSAIL)
Conference: NeurIPS 2024, December 10-15, Vancouver, Canada

Abstract:
We present TransLow, a novel transformer architecture achieving state-of-the-art results
on 47 low-resource language pairs. Our model achieves a BLEU score of 34.8 on the
standard benchmark, surpassing the previous best result of 29.3 by 18.8%.

The training was conducted on 4 NVIDIA A100 GPUs over 72 hours. The dataset comprised
2.3 million sentence pairs collected between January 2022 and August 2024.
Funding was provided by NSF Grant #2024-AI-7731 ($890,000) and Google Research.

Our approach uses only 0.4% of the training data required by competing methods,
making it accessible for communities with limited computational resources.""",
        ),
        TestCase(
            id=9, name="Court Legal Notice", file_type="docx",
            description="Legal summons document",
            min_names=2, min_dates=2, min_orgs=1, min_locations=1,
            expected_sentiment="negative",
            summary_keywords=["court", "legal", "defendant"],
            _doc_content="""SUPERIOR COURT OF CALIFORNIA
COUNTY OF LOS ANGELES

Case No.: 24-CV-108847
Filed: August 5, 2024

PLAINTIFF: Meridian Financial Group, Inc.
DEFENDANT: Alexander Petrov

SUMMONS AND COMPLAINT FOR:
1. Breach of Contract
2. Fraud and Misrepresentation
3. Unjust Enrichment

TO DEFENDANT Alexander Petrov of 4721 Sunset Boulevard, Los Angeles, California:

You are hereby summoned to appear before Judge Patricia Nguyen at the Los Angeles
Superior Court, 111 North Hill Street, on October 14, 2024 at 9:00 AM.

Plaintiff alleges defendant misappropriated funds totaling $2,350,000 between
March 15, 2023 and January 8, 2024, in violation of the partnership agreement
executed on February 1, 2022.

Attorney for Plaintiff: David Goldstein, Esq., Goldstein & Associates LLP.""",
        ),
        TestCase(
            id=10, name="Travel Itinerary", file_type="pdf",
            description="Business travel schedule",
            min_names=1, min_dates=3, min_locations=3, min_amounts=1,
            expected_sentiment="neutral",
            summary_keywords=["travel", "flight", "hotel"],
            _doc_content="""CORPORATE TRAVEL ITINERARY
Traveler: Jennifer Okafor | Employee ID: EMP-5521
Booking Reference: TRV-2024-9921
Travel Dates: November 18-22, 2024

OUTBOUND FLIGHT:
November 18 | Depart: New York JFK 8:45 AM → Arrive: London Heathrow 9:15 PM
Delta Airlines DL401 | Economy Class | Seat 24C
Cost: $1,247.00

HOTEL LONDON:
November 18-20 | The Grand Kensington Hotel, London, UK
Confirmation: GK-884721 | Rate: £285/night

CONNECTING TRAVEL:
November 20 | Train from London St Pancras → Paris Gare du Nord (Eurostar)
Departure: 2:05 PM | Arrival: 5:22 PM | Ticket: £89.00

PARIS HOTEL:
November 20-22 | Hotel Le Marais, Paris, France
Confirmation: HLM-29031 | Rate: €220/night

RETURN FLIGHT:
November 22 | Paris CDG 7:30 PM → New York JFK 10:15 PM (local)
Air France AF007 | Business Class | Cost: $2,190.00

TOTAL TRIP COST: $4,890.00 + £570.00 + €440.00""",
        ),
        TestCase(
            id=11, name="Press Release – Product Launch", file_type="docx",
            description="New software product announcement",
            min_orgs=1, min_names=1, min_dates=1,
            expected_sentiment="positive",
            summary_keywords=["launch", "product", "new"],
            _doc_content="""FOR IMMEDIATE RELEASE
Date: June 3, 2024
Contact: Lisa Park, VP Marketing, InnovateTech Inc.

INNOVATETECH LAUNCHES CLOUDVAULT 3.0:
THE FUTURE OF ENTERPRISE DATA MANAGEMENT

SAN JOSE, California — InnovateTech Inc. today announced the launch of CloudVault 3.0,
its next-generation enterprise data management platform, at TechWorld Conference 2024.

CloudVault 3.0 features 10x faster query performance, AI-powered data governance,
and seamless integration with Salesforce, Microsoft Azure, and AWS.

"This is the most significant product release in our 12-year history," said CEO
Daniel Kim. "CloudVault 3.0 will redefine how Fortune 500 companies manage data."

Early adopters include Goldman Sachs and Toyota Motor Corporation.
The platform is available starting July 1, 2024, with pricing from $8,500/month.
Free 30-day trials available at innovatetech.com.""",
        ),
        TestCase(
            id=12, name="Bank Statement", file_type="pdf",
            description="Personal bank account statement",
            min_dates=2, min_amounts=3, min_orgs=1,
            expected_sentiment="neutral",
            summary_keywords=["account", "balance", "transaction"],
            _doc_content="""FIRST NATIONAL BANK
Account Statement
Account Holder: Christopher Williams
Account Number: ****7821
Statement Period: October 1 – October 31, 2024

TRANSACTIONS:
Oct 01 | Opening Balance                           $12,450.00
Oct 03 | Direct Deposit – Payroll                  +$4,850.00
Oct 05 | Mortgage Payment – Wells Fargo            -$1,920.00
Oct 07 | Grocery Store – Whole Foods               -$234.50
Oct 10 | Amazon Purchase                           -$89.99
Oct 14 | Utility Bill – Pacific Gas & Electric     -$178.00
Oct 15 | Transfer to Savings Account               -$1,000.00
Oct 18 | Restaurant – The Italian Place            -$67.50
Oct 22 | ATM Withdrawal – Chase Bank NYC           -$300.00
Oct 25 | Freelance Income – PayPal                 +$750.00
Oct 31 | Closing Balance                           $14,260.01

Monthly Summary:
Total Credits: $5,600.00 | Total Debits: $3,789.99
Average Daily Balance: $13,105.42""",
        ),
        TestCase(
            id=13, name="Resignation Letter", file_type="docx",
            description="Professional resignation letter",
            min_names=2, min_dates=1, min_orgs=1,
            expected_sentiment="positive",
            summary_keywords=["resignation", "position", "last"],
            _doc_content="""March 15, 2024

Dear Ms. Patricia Chen,

I am writing to formally resign from my position as Senior Marketing Manager at
Horizon Brands International, effective April 12, 2024.

This was not an easy decision. My three years at Horizon have been incredibly
rewarding, and I am deeply grateful for the opportunities for growth and the
relationships I have built with colleagues across our offices in Chicago and Toronto.

I have accepted a position as VP of Marketing at a startup company and am excited
about this new chapter. I am committed to ensuring a smooth transition and will
complete all current projects, including the Q2 campaign launch on March 30th.

Please let me know how I can best support the team during my remaining time.
I look forward to staying connected and wish Horizon Brands continued success.

Warm regards,
Nathan Brooks""",
        ),
        TestCase(
            id=14, name="NGO Impact Report", file_type="pdf",
            description="Annual report from non-profit organization",
            min_orgs=2, min_names=1, min_dates=1, min_amounts=2, min_locations=2,
            expected_sentiment="positive",
            summary_keywords=["impact", "community", "program"],
            _doc_content="""CLEAN WATER FOR ALL — 2023 ANNUAL IMPACT REPORT
Executive Director: Dr. Amara Diallo

MISSION IMPACT:
In 2023, Clean Water for All partnered with UNICEF and the World Health Organization
to bring clean water access to 847,000 people across sub-Saharan Africa.

KEY ACHIEVEMENTS:
- Installed 1,240 water wells in Ethiopia, Kenya, and Uganda
- Trained 3,500 local technicians in water system maintenance
- Completed Phase 2 of the Nairobi Water Initiative (December 15, 2023)
- Launched new operations in Mozambique and Tanzania (June 2023)

FINANCIALS:
Total funds raised in 2023: $12.4 million
  - Individual donors: $4.2 million
  - Corporate partners (Patagonia, Microsoft): $5.8 million
  - Government grants (USAID): $2.4 million
Program expenditure: $10.9 million (88% of total budget)

LOOKING AHEAD: Our 2024 goal is to reach 1.5 million people with a target budget
of $16 million, expanding to Malawi and Zambia.""",
        ),
        TestCase(
            id=15, name="Merger Announcement", file_type="pdf",
            description="Corporate merger/acquisition press release",
            min_orgs=2, min_names=2, min_dates=1, min_amounts=1, min_locations=1,
            expected_sentiment="positive",
            summary_keywords=["merger", "acquisition", "billion"],
            _doc_content="""STRATEGIC MERGER ANNOUNCEMENT
Date: April 2, 2024

NovaStar Technologies Inc. (NASDAQ: NVST) and Quantum Data Corp (NYSE: QDC)
today announced a definitive merger agreement creating a combined entity
valued at $14.8 billion, pending regulatory approval.

NovaStar CEO Victoria Huang and Quantum Data CEO Robert Castellano jointly announced
the all-stock merger in New York City. The combined company will be headquartered
in Seattle, Washington and will retain approximately 18,400 employees globally.

The merger is expected to generate annual cost synergies of $420 million within
two years and accelerate entry into the Asia-Pacific market, with existing operations
in Singapore, Tokyo, and Sydney.

NovaStar shareholders will receive 1.35 QDC shares per NovaStar share.
The transaction is expected to close by September 30, 2024, subject to approval
from the U.S. Department of Justice and European Commission.

"Together we will be unstoppable," said Victoria Huang. "This is a transformative
day for both companies and for our industry."

Financial advisors: Goldman Sachs advised NovaStar; Morgan Stanley advised Quantum Data.""",
        ),
    ]


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_result(tc: TestCase, result: dict) -> dict:
    """Score a single test case result. Max 10 points per test."""
    pts = {"summary": 0, "entities": 0, "sentiment": 0, "total": 0, "notes": []}

    # ── Summary (2 pts) ───────────────────────────────────────────────────────
    summary = result.get("summary", "")
    if len(summary) >= tc.min_summary_length:
        pts["summary"] += 1
    else:
        pts["notes"].append(f"Summary too short ({len(summary)} < {tc.min_summary_length})")

    kw_hits = sum(1 for kw in tc.summary_keywords if kw.lower() in summary.lower())
    if tc.summary_keywords and kw_hits >= max(1, len(tc.summary_keywords) // 2):
        pts["summary"] += 1
    elif not tc.summary_keywords:
        pts["summary"] += 1  # no keywords required
    else:
        pts["notes"].append(f"Summary missing keywords: {tc.summary_keywords} (hits={kw_hits})")

    # ── Entities (4 pts) ──────────────────────────────────────────────────────
    entities = result.get("entities", {})
    entity_checks = [
        ("names",         tc.min_names,     entities.get("names", [])),
        ("dates",         tc.min_dates,     entities.get("dates", [])),
        ("organizations", tc.min_orgs,      entities.get("organizations", [])),
        ("amounts",       tc.min_amounts,   entities.get("amounts", [])),
        ("locations",     tc.min_locations, entities.get("locations", [])),
    ]
    required = [(name, mn, got) for name, mn, got in entity_checks if mn > 0]
    passed   = sum(1 for _, mn, got in required if len(got) >= mn)
    total_req = len(required) or 1
    pts["entities"] = round((passed / total_req) * 4, 2)
    failed = [name for name, mn, got in required if len(got) < mn]
    if failed:
        pts["notes"].append(f"Entity shortfall in: {failed}")

    # ── Sentiment (4 pts) ─────────────────────────────────────────────────────
    if not tc.expected_sentiment:
        pts["sentiment"] = 4  # no expected = full marks
    elif result.get("sentiment", "").lower() == tc.expected_sentiment.lower():
        pts["sentiment"] = 4
    else:
        pts["notes"].append(
            f"Sentiment mismatch: expected={tc.expected_sentiment} got={result.get('sentiment')}"
        )

    pts["total"] = round(pts["summary"] + pts["entities"] + pts["sentiment"], 2)
    return pts


# ── Runner ────────────────────────────────────────────────────────────────────

def run_tests(base_url: str, api_key: str, verbose: bool = True) -> None:
    cases = build_test_cases()
    total_score = 0.0
    max_score   = len(cases) * 10.0
    results_log = []

    print(f"\n{'='*65}")
    print(f"  DocuSense — Hackathon Eval Suite   ({len(cases)} tests, max {max_score:.0f} pts)")
    print(f"  Endpoint : {base_url}/api/document-analyze")
    print(f"{'='*65}\n")

    for tc in cases:
        sys.stdout.write(f"  [{tc.id:02d}] {tc.name:<35} ... ")
        sys.stdout.flush()

        # Build document bytes
        if tc.file_type == "pdf":
            doc_bytes = _make_pdf_bytes(tc._doc_content)
        elif tc.file_type == "docx":
            doc_bytes = _make_docx_bytes(tc._doc_content)
        else:
            continue  # image tests require real image files

        payload = {
            "fileName": f"test_{tc.id}.{tc.file_type}",
            "fileType": tc.file_type,
            "fileBase64": _b64(doc_bytes),
        }
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}

        t0 = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/document-analyze",
                json=payload,
                headers=headers,
                timeout=120,
            )
            elapsed = time.time() - t0

            if resp.status_code != 200:
                print(f"FAIL (HTTP {resp.status_code})")
                results_log.append({"id": tc.id, "name": tc.name, "score": 0, "error": resp.text[:200]})
                continue

            result = resp.json()
            score  = score_result(tc, result)
            total_score += score["total"]

            status = "✓" if score["total"] >= 8 else ("~" if score["total"] >= 5 else "✗")
            print(f"{status}  {score['total']:4.1f}/10  ({elapsed:.1f}s)")

            if verbose and score["notes"]:
                for note in score["notes"]:
                    print(f"         ↳ {note}")

            results_log.append({
                "id": tc.id, "name": tc.name,
                "score": score, "response": result,
            })

        except Exception as e:
            print(f"ERROR: {e}")
            results_log.append({"id": tc.id, "name": tc.name, "score": 0, "error": str(e)})

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  FINAL SCORE: {total_score:.1f} / {max_score:.0f}  ({(total_score/max_score*100):.1f}%)")
    print(f"{'─'*65}\n")

    # Save detailed report
    report_path = "test_report.json"
    with open(report_path, "w") as f:
        json.dump(results_log, f, indent=2)
    print(f"  Detailed report saved to: {report_path}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DocuSense Hackathon Test Suite")
    parser.add_argument("--url",  default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("--key",  default=os.getenv("API_KEY", "test"), help="API key (x-api-key header)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-test notes")
    args = parser.parse_args()

    # Ensure python-docx available for test doc generation
    try:
        from docx import Document  # noqa
    except ImportError:
        print("ERROR: python-docx not installed. Run: pip install python-docx")
        sys.exit(1)

    run_tests(args.url, args.key, verbose=not args.quiet)
