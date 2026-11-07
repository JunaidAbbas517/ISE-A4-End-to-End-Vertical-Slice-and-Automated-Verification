# Report

- `ISE-A4-Final-Report.pdf`: main readable report (8 pages)
- `ISE-A4-Final-Report.docx`: editable source

## Rebuild from source
```bash
python make_figures.py          # figures/*.png (matplotlib)
npm ci                          # docx 9.0.2, pinned in package-lock.json
node build_report.js            # ISE-A4-Final-Report.docx
```
Then export to PDF from Word (*File → Save As → PDF*). The recorded PDF was exported with Microsoft Word on Windows 11.
