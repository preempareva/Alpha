# Knowledge Assistant data card

## Dataset

The local demonstration corpus contains thirty fictional Markdown documents and one synthetic scanned-document review fixture. The authored documents cover general, finance, HR, procurement, and security topics. Access groups and effective dates are part of the fixture so that access filtering, expired versions, and abstention can be exercised.

## Collection and permissions

All corpus material is authored for this demo. No employer policy, customer record, public web crawl, or external dataset is included. The seed script creates three local demo accounts with generated or environment-provided credentials. The database and session secret are local runtime assets and are ignored by Git.

## Intended use

Use this corpus to demonstrate lexical retrieval, citation display, effective-date filtering, group filtering, and safe abstention. It is not an approved source of real company policy. Replace it only with documents whose owner has authorized ingestion and only after a real identity and access mapping is configured.

## Known limits

The small hand-authored corpus has narrow vocabulary and intentionally simple access groups. It does not represent enterprise document volume, policy conflicts, multilingual search, OCR quality, or production authorization systems. The retrieval evaluation is a regression check over authored questions, not a measure of real-user answer quality.
