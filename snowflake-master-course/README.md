# Snowflake Master Course — Companion Repository

A complete, hands-on SQL and Python companion for the **Snowflake Master Course**. Every chapter maps directly to course lectures and contains working, well-commented exercises you can run against your own Snowflake trial account.

---

## What You Will Learn

- How Snowflake's multi-cluster shared-data architecture works — and why it matters
- Loading structured, semi-structured, and unstructured data at scale
- Advanced SQL: window functions, semi-structured queries, MATCH_RECOGNIZE, ASOF JOINs
- Role-based access control, column-level security, row access policies, and network policies
- Time Travel, Fail-safe, and zero-copy cloning for cost-efficient data management
- Secure Data Sharing and the Snowflake Marketplace
- Snowpark (Python/Java/Scala) for in-warehouse compute
- Streamlit in Snowflake for rapid data apps
- Snowflake Cortex for LLM-powered analytics
- Governance: data quality, object tagging, lineage, and access history
- Cost management, resource monitors, and warehouse right-sizing
- DevOps: schemachange migrations, dbt, CI/CD pipelines
- Monitoring, alerting, and operational dashboards

---

## Prerequisites

| Requirement | Details |
|---|---|
| SQL knowledge | Comfortable with SELECT, JOIN, GROUP BY, and basic DDL |
| Cloud account | Free Snowflake 30-day trial (link below) |
| Python (optional) | Python 3.9+ for Snowpark and Streamlit chapters |
| Git | To clone this repository |

No prior Snowflake experience is required. The course starts from zero.

---

## Quick Start

### 1. Get a Free Snowflake Trial

Sign up at **https://signup.snowflake.com** — no credit card required for 30 days / $400 in credits.

Recommended settings during signup:
- **Edition**: Enterprise (unlocks all features covered in this course)
- **Cloud Provider**: Any (AWS us-east-1 is a safe default)

### 2. Clone This Repository

```bash
git clone https://github.com/your-org/snowflake-master-course.git
cd snowflake-master-course
```

### 3. Set Up Your Python Environment (Optional — needed for Snowpark chapters)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r setup/requirements.txt
```

### 4. Run the Account Setup Script

Open `setup/00_account_setup.sql` in a Snowflake Worksheet (or SnowSQL) and run it top-to-bottom **as ACCOUNTADMIN**. This creates all roles, warehouses, databases, and schemas used throughout the course.

```bash
# SnowSQL example
snowsql -a <account_identifier> -u <username> -f setup/00_account_setup.sql
```

### 5. Work Through the Chapters

Each chapter folder contains an `exercises.sql` file. Open it in a Snowflake Worksheet and execute exercises one at a time. Every exercise has a numbered comment block explaining what it demonstrates.

---

## Folder Structure

```
snowflake-master-course/
├── README.md                        # This file
├── setup/
│   ├── 00_account_setup.sql         # Roles, warehouses, databases, schemas
│   └── requirements.txt             # Python dependencies
├── chapter_01_introduction/
│   └── exercises.sql                # Snowflake basics, system views, account info
├── chapter_02_architecture/
│   └── exercises.sql                # Micro-partitions, caching, query execution
├── chapter_03_setup/
│   └── exercises.sql                # Environment setup, session parameters
├── chapter_04_objects/
│   └── exercises.sql                # All Snowflake object types
├── chapter_05_loading/
│   └── exercises.sql                # Stages, COPY INTO, Snowpipe, semi-structured data
├── chapter_06_sql/
│   └── exercises.sql                # Advanced SQL: window functions, VARIANT, PIVOT, MERGE
├── chapter_07_warehouses/
│   └── exercises.sql                # Warehouse tuning, clustering, Query Acceleration
├── chapter_08_security/
│   └── exercises.sql                # RBAC, masking policies, row access, network policies
├── chapter_09_timetravel/
│   └── exercises.sql                # Time Travel, Fail-safe, zero-copy cloning
├── chapter_10_sharing/
│   └── exercises.sql                # Secure Data Sharing, Marketplace, reader accounts
├── chapter_11_snowpark/
│   └── exercises.sql                # Snowpark UDFs, stored procedures, DataFrames
├── chapter_12_streamlit/
│   └── exercises.sql                # Streamlit in Snowflake apps
├── chapter_13_cortex/
│   └── exercises.sql                # Cortex LLM functions, AI/ML features
├── chapter_14_governance/
│   └── exercises.sql                # Tags, data quality, lineage, access history
├── chapter_15_cost/
│   └── exercises.sql                # Cost management, resource monitors
├── chapter_16_devops/
│   └── exercises.sql                # schemachange, dbt, CI/CD
├── chapter_17_monitoring/
│   └── exercises.sql                # Query history, alerting, operational views
├── chapter_18_advanced/
│   └── exercises.sql                # External functions, Iceberg, advanced patterns
└── data/
    └── sample files for loading exercises
```

---

## Useful Links

| Resource | URL |
|---|---|
| Snowflake Trial Signup | https://signup.snowflake.com |
| Official Documentation | https://docs.snowflake.com |
| SnowSQL CLI | https://docs.snowflake.com/en/user-guide/snowsql |
| Snowflake Community | https://community.snowflake.com |
| SnowPro Core Certification | https://www.snowflake.com/certifications/ |
| SnowPro Advanced: Architect | https://www.snowflake.com/certifications/ |
| Snowflake University (free) | https://learn.snowflake.com |
| Snowflake Blog | https://www.snowflake.com/blog |
| Status Page | https://status.snowflake.com |

---

## How to Use Each Exercise File

1. Open the file in **Snowflake Worksheets** or **SnowSQL**.
2. Read the comment block above each exercise before running it.
3. Run exercises top-to-bottom — later exercises often depend on objects created earlier.
4. Some exercises have `-- TODO:` markers prompting you to fill in values or modify the query.
5. Exercises marked `-- INSTRUCTOR NOTE:` contain extra context from the course lectures.

---

## License

This repository is released under the **MIT License**. You are free to use, modify, and distribute this content for personal or commercial purposes with attribution.

```
MIT License

Copyright (c) 2024 Snowflake Master Course

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

*Built with care for everyone learning Snowflake. Questions? Open an issue or join the course community forum.*
