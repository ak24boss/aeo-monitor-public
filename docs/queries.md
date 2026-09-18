# AEO Monitor — Query Configuration

## QueryConfig Schema

Each query entry in `config/queries.yaml` maps to a `QueryConfig` object:

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `text` | str | any | The literal search query string |
| `intent` | str | see below | User intent classification |
| `vertical` | str | see below | Industry/vertical context |
| `priority` | str | `high`, `medium`, `low` | `high` → also sent to Perplexity AE phase |
| `category` | str | see below | Logical grouping within the YAML |

### Intent values

- `tool discovery` — user looking for a tool in this space
- `use case` — user exploring a workflow or use case
- `comparison` — user comparing tools
- `workflow` — user looking for process/workflow guidance
- `competitor displacement` — user experiencing pain with an existing tool

### Vertical values

`finance`, `accounting`, `healthcare`, `logistics`, `insurance`, `legal`, `construction`, `general`

## Current Categories (23)

As of 2026-08-31, `config/queries.yaml` has 23 categories (~170 queries total):

| Category | Description |
|----------|-------------|
| `commercial` | Core commercial intent: "best document extraction software", "lido alternatives" |
| `vertical` | Vertical-specific use cases: accounting, healthcare, logistics, etc. |
| `alternatives` | Named competitor alternatives: "nanonets alternatives", "Parseur alternatives" |
| `long_tail` | Specific long-tail discovery queries |
| `competitor_comparison` | Direct competitor comparisons: "Lido vs Nanonets" |
| `solution_aware` | Queries from users who know IDP/OCR/extraction exists |
| `problem_aware_accounting` | Pain-first accounting queries: "automate invoice data entry" |
| `problem_aware_legal` | Pain-first legal queries |
| `problem_aware_healthcare` | Pain-first healthcare queries: "EOB data extraction" |
| `problem_aware_insurance` | Pain-first insurance queries |
| `problem_aware_construction` | Pain-first construction queries |
| `problem_aware_logistics` | Pain-first logistics queries: "automate BOL data entry" |
| `integration_erp` | ERP integration queries: "extract invoices to SAP" |
| `integration_spreadsheet` | Spreadsheet integration: "PDF to Excel extraction" |
| `integration_api` | API/no-code integration: "document extraction Zapier" |
| `integration_reliability` | Volume/reliability queries: "high volume document processing" |
| `roi_build_vs_buy` | Build vs buy ROI queries: "true cost of manual data entry" |
| `vertical_accounting` | Accounting-specific products |
| `vertical_legal` | Legal-specific products |
| `vertical_healthcare` | Healthcare-specific products |
| `vertical_insurance` | Insurance-specific products |
| `vertical_construction` | Construction-specific products |
| `vertical_logistics` | Logistics-specific products |

## Pending Categories (NOT YET ADDED)

Seven categories identified from `~/Lido Content/lido-rundown.md` but not yet added to the YAML:

| Category key | Example queries | GTM connection |
|---|---|---|
| `email_triage` | "email to document extraction workflow", "automate pre-processing email attachments" | Explicit qualification trigger |
| `form_filling` | "auto fill PDF forms from extracted data", "populate claim forms automatically" | First upsell tier |
| `document_splitting` | "automatically split multi-patient PDF", "split combined PDF by document type" | Named pain point |
| `bpo_reshoring` | "bring data entry back in-house from BPO", "replace offshore data entry team with AI" | Explicit qualification trigger |
| `font_rex_alternatives` | "Font Rex alternative", "Font Rex vs AI extraction" | Named competitor (accounting vertical) |
| `commerce_industry` | "PO line item extraction ERP", "smart lookup item master matching" | Named vertical in GTM matrix |
| `rules_logic_layer` | "conditional document routing rules", "document type detection auto-stop" | Named product tier |

## How to Add a New Query

Edit `config/queries.yaml`. No code changes needed.

```yaml
categories:
  my_category:
    - text: "your search query here"
      intent: "tool discovery"      # tool discovery | use case | comparison | workflow | competitor displacement
      vertical: "finance"           # finance | accounting | healthcare | logistics | insurance | legal | construction | general
      priority: high                # high | medium | low
```

**Note**: `priority: high` queries are also sent to the Perplexity AE phase (Phase 4). Use `high` sparingly — it costs ~$0.001/query.

**Note**: `--queries N` takes the first N queries in file order. Put high-priority categories near the top of the YAML if you use `--queries` for dev runs.

## `--queries N` behavior

When you pass `--queries 5`, the pipeline uses the first 5 queries in YAML parse order. YAML order is: `categories` dict iteration (insertion order), then queries within each category in list order. This means the first 5 queries will always come from the first category.
