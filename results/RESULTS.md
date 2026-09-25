# Results

Generated 2026-09-25 by `python run_benchmark.py --local-only --repeats 5` (median of 5 runs; Python 3.12.14, Windows-11-10.0.26200-SP0). Parsers: PyPDF (pypdf 6.19.0), PDFMiner (pdfminer.six 20260107), PDFPlumber (pdfplumber 0.11.10).

**Corpus** (reference characters after normalization; text that exists only inside images is out of reach for text-layer parsers)

| Document | Stresses | Reference chars | Only in images |
|---|---|---:|---:|
| multilingual-sample | multilingual, rtl, indic, table, image-only-text | 965 | 169 (18%) |
| fr-notice-3col | multi-column | 3,643 | 0 (0%) |
| fr-table | table, multi-column | 5,007 | 0 (0%) |
| naca-scan | scanned | 1,057 | 1,057 (100%) |

**Text fidelity** (lower CER/WER is better, higher BoW-F1 is better; seconds are wall-clock medians on the machine above)

| Document | Parser | CER | WER | BoW-F1 | Chars out / ref | Seconds |
|---|---|---:|---:|---:|---:|---:|
| multilingual-sample | PyPDF | 0.228 | 0.473 | 0.690 | 802 / 965 | 0.066 |
| multilingual-sample | PDFMiner | 0.348 | 0.445 | 0.702 | 817 / 965 | 0.126 |
| multilingual-sample | PDFPlumber | 0.279 | 0.377 | 0.697 | 781 / 965 | 0.132 |
| multilingual-sample | LlamaParse | not run (--local-only) | | | | |
| multilingual-sample | AWS Textract | not run (--local-only) | | | | |
| fr-notice-3col | PyPDF | 0.046 | 0.046 | 0.978 | 3,905 / 3,643 | 0.027 |
| fr-notice-3col | PDFMiner | 0.050 | 0.093 | 0.956 | 3,985 / 3,643 | 0.078 |
| fr-notice-3col | PDFPlumber | 0.786 | 0.945 | 0.964 | 3,787 / 3,643 | 0.226 |
| fr-notice-3col | LlamaParse | not run (--local-only) | | | | |
| fr-notice-3col | AWS Textract | not run (--local-only) | | | | |
| fr-table | PyPDF | 0.039 | 0.047 | 0.981 | 6,078 / 5,007 | 0.041 |
| fr-table | PDFMiner | 0.136 | 0.190 | 0.966 | 6,224 / 5,007 | 0.143 |
| fr-table | PDFPlumber | 0.433 | 0.496 | 0.968 | 5,945 / 5,007 | 0.286 |
| fr-table | LlamaParse | not run (--local-only) | | | | |
| fr-table | AWS Textract | not run (--local-only) | | | | |
| naca-scan | PyPDF | 1.000 | 1.000 | 0.000 | 0 / 1,057 | 0.204 |
| naca-scan | PDFMiner | 1.000 | 1.000 | 0.000 | 1 / 1,057 | 0.097 |
| naca-scan | PDFPlumber | 1.000 | 1.000 | 0.000 | 0 / 1,057 | 0.104 |
| naca-scan | LlamaParse | not run (--local-only) | | | | |
| naca-scan | AWS Textract | not run (--local-only) | | | | |

**Table structure** (rows whose cells all come out on one line, in order / cells found anywhere)

| Document | PyPDF | PDFMiner | PDFPlumber |
|---|---:|---:|---:|
| multilingual-sample | rows 0/4 · cells 8/8 | rows 0/4 · cells 8/8 | rows 4/4 · cells 8/8 |
| fr-table | rows 15/21 · cells 84/84 | rows 0/21 · cells 80/84 | rows 21/21 · cells 78/84 |

**Scripts in `multilingual-sample`** (RTL: reading order of the sentence; Indic: sentence intact, share of words exact)

| Script | PyPDF | PDFMiner | PDFPlumber |
|---|---|---|---|
| Arabic (RTL) | logical order | out of order, letters reversed | fully reversed |
| Urdu (RTL) | logical order | out of order, letters reversed | fully reversed |
| Hindi | broken, 75% of words exact | broken, 62% of words exact | broken, 50% of words exact |
| Bengali | broken, 43% of words exact | broken, 43% of words exact | broken, 43% of words exact |
| Lines out (words per line) | 141 (1.0) | 43 (2.84) | 22 (5.5) |

Not run in this table: LlamaParse: not run (--local-only); AWS Textract: not run (--local-only).
