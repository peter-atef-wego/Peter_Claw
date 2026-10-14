---
name: sql-plsql-bigquery
description: SQL, PL/SQL, and BigQuery best practices for analytics and automation. Use for query design, optimization, and data pipeline correctness.
---

# SQL + PL/SQL + BigQuery

This skill focuses on correctness‑first SQL, Oracle PL/SQL practices, and BigQuery‑specific optimization patterns.

## 1) Core SQL principles

- **Define grain**: know whether your query is at row, customer, transaction, or day level.
- **Validate joins**: confirm keys and cardinality to avoid duplication.
- **Be explicit**: avoid `SELECT *` in production.

## 2) Query correctness checklist

- Validate filters (date ranges, status values).
- Confirm null handling and default values.
- Compare row counts before/after major joins.

## 3) PL/SQL practices

- Keep procedures small and testable.
- Log procedure inputs and outputs for auditability.
- Avoid hidden side effects; prefer explicit commits.

## 4) BigQuery performance

- Use **partitioning** and **clustering**.
- Filter by partition early.
- Avoid large cross joins; pre‑aggregate if needed.
- Materialize intermediate results for heavy joins.

## 5) Cost control

- Restrict scanned data size.
- Use table sampling for exploratory work.
- Cache repeated queries where possible.

## 6) Data pipeline reliability

- Use incremental loads.
- Add data‑quality checks (row count, null checks, schema validation).
- Log data lineage and timestamps.

## 7) Debugging tips

- Use stepwise validation: build query incrementally.
- Compare outputs with known small samples.
- When in doubt, isolate the join causing inflation.

## Official references

- Oracle SQL / PL/SQL Docs: https://docs.oracle.com/en/database/
- BigQuery Docs: https://cloud.google.com/bigquery/docs
- BigQuery Best Practices: https://cloud.google.com/bigquery/docs/best-practices-performance
