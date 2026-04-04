# Chapter 12 Exercise: CI/CD & Production Deployment

## Exercise 12.1 — Slim CI with State
Run a full production build into a "prod" target (or simulate with a separate schema).
Save the manifest: `cp target/manifest.json prod_manifest.json`

Now make a small change to `stg_customers.sql` (e.g. add a comment).
Run Slim CI — only changed models + their children:
```bash
dbt run --select state:modified+ --defer --state ./prod_manifest.json
```

Which models ran? Which were deferred to the production manifest?

## Exercise 12.2 — Write a GitHub Actions Workflow
Create `.github/workflows/ci.yml` that:
1. Installs dbt
2. Runs `dbt deps`
3. Runs `dbt build --select state:modified+ --defer --state ./prod_manifest`
4. Uploads `target/manifest.json` as an artifact

Use environment variables for warehouse credentials (stored as GitHub Secrets).

## Exercise 12.3 — Pre/Post Hooks
Add a `post-hook` to `fct_orders` that grants SELECT to a BI service role:
```sql
post-hook: "grant select on {{ this }} to role bi_reader"
```

Verify it runs after the model build by checking warehouse audit logs.

## Exercise 12.4 — Exposures
Add an `exposures:` block to `models/marts/core/_core.yml` that documents
a "Revenue Dashboard" Tableau workbook that depends on `fct_orders` and
`dim_customers`. Run `dbt docs generate` and find the exposure in the DAG.
