# Results

Scored on 2026-11-06: 50 synthetic invoices, model claude-sonnet-5-5. Text and dates must match exactly. Amounts can be off by 0.01 at most.

## Run 1

Outcome: 45 posted, 5 exceptions.
Upload to bill took 7.7 s on average.

### Planted errors

| File | Planted | Flagged as | Caught |
| --- | --- | --- | --- |
| inv_005.pdf | bad_dates | bad_dates | yes |
| inv_022.pdf | sum_mismatch | sum_mismatch | yes |
| inv_024.pdf | duplicate | duplicate | yes |
| inv_032.pdf | unknown_vendor | unknown_vendor | yes |
| inv_041.pdf | bad_tax_id | bad_tax_id | yes |

Caught 5 of 5.

### False alarms

None: all 45 clean invoices posted.

### Field accuracy

| Field | Correct | Accuracy |
| --- | --- | --- |
| vendor_name | 50/50 | 100.0% |
| vendor_tax_id | 50/50 | 100.0% |
| invoice_number | 50/50 | 100.0% |
| invoice_date | 50/50 | 100.0% |
| due_date | 50/50 | 100.0% |
| currency | 50/50 | 100.0% |
| subtotal | 50/50 | 100.0% |
| tax | 50/50 | 100.0% |
| total | 50/50 | 100.0% |
| line item count | 50/50 | 100.0% |
| line values (qty, unit price, amount) | 165/165 | 100.0% |
| line descriptions | 165/165 | 100.0% |

Claude API cost: 2,957 input and 449 output tokens per invoice on average, about $0.01 each ($0.52 for the 50), from the token counts the API returned in this run.

No field was under 95%, so I kept the first extraction prompt and there is only one run.

These PDFs are generated, not scanned, so real invoices will score lower on extraction. A misread amount still fails the sum check and a misread vendor name fails the QuickBooks lookup, so those go to the exception list instead of the books.
