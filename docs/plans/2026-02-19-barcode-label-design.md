# ML Barcode Generator - Design Document

## Problem

Diego Mexico Bike downloads daily PDF shipping labels from Mercado Libre. They need to add a scannable Code 128 barcode (encoding the Pack ID) to each label. Currently using ChatGPT which is unreliable and requires a specific account.

## Solution

Web application that takes a Mercado Libre shipping label PDF, extracts Pack ID / Venta ID from each label, generates Code 128 barcodes, overlays them onto the original PDF, and returns the modified PDF for download.

## Architecture

```
Browser (HTML/JS) ──POST /process──► FastAPI Backend (Python)
                  ◄─GET /download──
```

### Backend Stack
- **FastAPI** - async web framework
- **pdfplumber** - PDF text extraction with positions
- **python-barcode** - Code 128 barcode generation
- **reportlab** + **PyPDF2** - PDF overlay/modification

### Frontend
- Static HTML/CSS/JS
- Drag & drop file upload
- Spanish language UI
- Footer: `© 2026 Codezuno. All rights reserved. · Crafted & Designed & Built with ♥ by codezuno.com`

## Page Classification

| Type | Detection | Action |
|------|-----------|--------|
| 2-column (2 labels) | Pack ID / Venta ID appears 2x | Insert 2 barcodes (left + right) |
| 1-column + product panel | 1x Pack ID + "productos"/"unidades" on right | Insert 1 barcode (left side) |
| 1-column full width | 1x Pack ID/Venta ID, no product panel | Insert 1 barcode |
| J&T Express | Text "J&T" or "JTMLM" or "JMX" | Insert barcode (different position, above date) |
| Summary/checklist page | Text "Identificación" + "Productos" header | **Skip** |

## Pack ID Extraction

1. Extract all text with positions from page (pdfplumber)
2. Regex: `Pack ID:?\s*(\d{5}\s?\d{11})` or `Venta:?\s*(\d{5}\s?\d{11})`
3. Remove spaces from number to get full ID (e.g., `2000011633126699`)
4. For 2-column pages: split by x-coordinate (left < 300, right >= 300)
5. For J&T Express: search for `Venta:` in upper section

## Barcode Positioning

Standard ML label - barcode placed **below the CP/date line**, above the recipient address section:

```
┌──────────────────────┐
│ Pack ID / info       │  tear-off
│ ✂️ ────────────────── │
│ Remitente / XGD1     │
│ Barcode (ML)         │
│ Number               │
│ ┌────────┐           │
│ │ SLE1   │  22:30    │  routing
│ └────────┘           │
│ XGD1>SLE1>SLE1_S0    │
│ CP: 37669  SAB 21/02 │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  ← OUR BARCODE
│ 2000011633126699     │  ← number below barcode
│                      │
│ Recipient data       │
│ QR code          [R] │
└──────────────────────┘
```

J&T Express label - barcode placed above the date line.

## Frontend UI (Spanish)

```
┌─────────────────────────────────────────┐
│  Generador de Códigos de Barras ML      │
│                                          │
│  ┌─────────────────────────────────┐    │
│  │                                 │    │
│  │   Arrastra tu PDF aquí          │    │
│  │   o haz clic para seleccionar   │    │
│  │                                 │    │
│  └─────────────────────────────────┘    │
│                                          │
│  [Procesar PDF]                         │
│                                          │
│  Estado: Se procesaron 14 etiquetas     │
│  - 12 etiquetas estándar ML             │
│  -  1 etiqueta J&T Express              │
│  -  2 páginas de resumen (omitidas)     │
│                                          │
│  [⬇ Descargar PDF con códigos]          │
│                                          │
│  © 2026 Codezuno. All rights reserved.  │
│  Crafted & Designed & Built with ♥      │
│  by codezuno.com                        │
└─────────────────────────────────────────┘
```

## Error Handling

| Situation | Response |
|-----------|----------|
| No labels found | "No se encontraron etiquetas" |
| Corrupt/unreadable PDF | "Error al procesar el archivo" |
| Label without Pack/Venta ID | Skip label, show warning |
| File is not PDF | Validate on frontend + backend |
| Large PDF (50+ pages) | Handle normally, show progress |

## Samples

5 sample PDFs available in `samples/` directory for testing:
- `01 Complex example.pdf` (26 pages, includes J&T Express)
- `02 Simple example.pdf` (2 pages, single multi-product label)
- `03 example.pdf` (3 pages, 4 standard labels)
- `04 example.pdf` (10 pages, mixed Pack ID/Venta ID)
- `05 example with surprise.pdf` (10 pages, includes J&T Express)
- `CCCD421811E8D1BA12F6692C0D4CB895_labels_barcodes (1).pdf` (ChatGPT output reference)
