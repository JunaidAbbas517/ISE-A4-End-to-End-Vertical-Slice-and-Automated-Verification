# Report

- `ISE-A4-Final-Report.pdf`: main readable report (8 pages)
- `ISE-A4-Final-Report.docx`: editable source

## Before submitting
The yellow-highlighted passages (peer review, user task test, AC10, two rows on page 1) are **placeholders**. Replace them with your real results in Word, remove the highlight, then use *File → Save As → PDF* to overwrite the PDF. Do not leave "PENDING" in the submitted version unless that step truly was not done. If so, say so.

## Rebuild from source (optional)
```bash
python make_figures.py          # figures/*.png (matplotlib)
npm ci                          # docx 9.0.2, pinned in package-lock.json
node build_report.js            # ISE-A4-Final-Report.docx
```
Then export to PDF from Word. A rebuild overwrites manual edits to the `.docx`, so after editing in Word either stop rebuilding or copy your text into `build_report.js`.
