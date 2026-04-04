###############################################################################
# Chapter 16: DevOps for Snowflake – Terraform Configuration
# Snowflake Master Course
###############################################################################
# Provider: Snowflake Terraform Provider v0.87+
# https://registry.terraform.io/providers/Snowflake-Labs/snowflake/latest
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    snowflake = {
      source  = "Snowflake-Labs/snowflake"
      version = "~> 0.87"
    }
  }

  # Recommended: use remote state (S3, GCS, or Terraform Cloud)
  # backend "s3" {
  #   bucket = "my-terraform-state-bucket"
  #   key    = "snowflake/master-course/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

###############################################################################
# Provider
###############################################################################
provider "snowflake" {
  account  = var.snowflake_account
  username = var.snowflake_user
  role     = var.snowflake_role

  # Recommended: use key-pair authentication in CI/CD
  private_key_path = var.snowflake_private_key_path

  # For development only – prefer key-pair auth in production
  # password = var.snowflake_password
}

###############################################################################
# Databases
###############################################################################
resource "snowflake_database" "analytics" {
  name                        = upper("${var.environment}_ANALYTICS")
  comment                     = "Primary analytics database – ${var.environment} environment"
  data_retention_time_in_days = var.environment == "prod" ? 14 : 1
}

resource "snowflake_database" "dev" {
  name                        = "DEV_ANALYTICS"
  comment                     = "Developer sandbox – cloned from prod on each sprint"
  data_retention_time_in_days = 1
}

###############################################################################
# Schemas
###############################################################################
resource "snowflake_schema" "raw" {
  database = snowflake_database.analytics.name
  name     = "RAW"
  comment  = "Raw ingestion layer – data lands here via Snowpipe / COPY"

  data_retention_days = 7
  is_transient        = false
}

resource "snowflake_schema" "staging" {
  database = snowflake_database.analytics.name
  name     = "STAGING"
  comment  = "Staging / cleaning layer – dbt stg_ models"

  data_retention_days = 3
}

resource "snowflake_schema" "marts" {
  database = snowflake_database.analytics.name
  name     = "MARTS"
  comment  = "Business-ready dimensional models – dbt fct_ and dim_ models"

  data_retention_days = 14
}

resource "snowflake_schema" "ml_features" {
  database = snowflake_database.analytics.name
  name     = "ML_FEATURES"
  comment  = "Feature store and ML model artifacts"

  data_retention_days = 7
}

###############################################################################
# Warehouses
###############################################################################

# dbt / ELT transform warehouse – scales with workload
resource "snowflake_warehouse" "transform" {
  name                        = upper("${var.environment}_TRANSFORM_WH")
  comment                     = "Used by dbt and ELT pipelines"
  warehouse_size              = "SMALL"
  auto_suspend                = var.warehouse_auto_suspend_seconds
  auto_resume                 = true
  initially_suspended         = true
  max_concurrency_level       = 8
  statement_timeout_in_seconds = 3600  # 1 hour

  # Snowflake Optimized Warehouse (optional, for large dbt runs)
  # enable_query_acceleration = true
}

# BI / analytics query warehouse – multi-cluster for concurrency
resource "snowflake_warehouse" "analytics" {
  name                        = upper("${var.environment}_ANALYTICS_WH")
  comment                     = "Used by BI tools and ad-hoc analysts"
  warehouse_size              = "MEDIUM"
  auto_suspend                = var.warehouse_auto_suspend_seconds
  auto_resume                 = true
  initially_suspended         = true
  max_concurrency_level       = 4

  # Multi-cluster configuration for handling concurrent BI users
  min_cluster_count = 1
  max_cluster_count = var.max_cluster_count_analytics
  scaling_policy    = "ECONOMY"  # STANDARD or ECONOMY
}

# Reporting warehouse – lightweight, for scheduled report queries
resource "snowflake_warehouse" "reporting" {
  name                = upper("${var.environment}_REPORTING_WH")
  comment             = "Lightweight warehouse for scheduled dashboard refreshes"
  warehouse_size      = "X-SMALL"
  auto_suspend        = 60
  auto_resume         = true
  initially_suspended = true
}

# Developer warehouse – used by engineers for ad-hoc development
resource "snowflake_warehouse" "dev" {
  name                = "DEV_WH"
  comment             = "Developer warehouse – individual contributor use"
  warehouse_size      = "X-SMALL"
  auto_suspend        = 60
  auto_resume         = true
  initially_suspended = true
}

###############################################################################
# Roles
###############################################################################
resource "snowflake_role" "data_engineer" {
  name    = "DATA_ENGINEER"
  comment = "Full access to raw, staging, and marts schemas. Manages pipelines."
}

resource "snowflake_role" "data_analyst" {
  name    = "DATA_ANALYST"
  comment = "Read access to marts schema. Can use analytics warehouse."
}

resource "snowflake_role" "data_scientist" {
  name    = "DATA_SCIENTIST"
  comment = "Read access to marts and ml_features. Can create models."
}

resource "snowflake_role" "dbt_role" {
  name    = "DBT_ROLE"
  comment = "Service account role for dbt Cloud / dbt Core CI runs."
}

###############################################################################
# Grants – DATA_ENGINEER role
###############################################################################
resource "snowflake_grant_privileges_to_role" "de_warehouse_usage" {
  role_name  = snowflake_role.data_engineer.name
  privileges = ["USAGE", "OPERATE", "MONITOR"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.transform.name
  }
}

resource "snowflake_grant_privileges_to_role" "de_database_usage" {
  role_name  = snowflake_role.data_engineer.name
  privileges = ["USAGE", "CREATE SCHEMA"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.analytics.name
  }
}

resource "snowflake_grant_privileges_to_role" "de_raw_schema" {
  role_name  = snowflake_role.data_engineer.name
  privileges = ["USAGE", "CREATE TABLE", "CREATE STAGE", "CREATE PIPE"]

  on_schema {
    schema_name = "${snowflake_database.analytics.name}.${snowflake_schema.raw.name}"
  }
}

resource "snowflake_grant_privileges_to_role" "de_all_tables_raw" {
  role_name  = snowflake_role.data_engineer.name
  privileges = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]

  on_schema_object {
    object_type = "TABLE"
    on_schema {
      schema_name = "${snowflake_database.analytics.name}.${snowflake_schema.raw.name}"
    }
  }
}

###############################################################################
# Grants – DATA_ANALYST role
###############################################################################
resource "snowflake_grant_privileges_to_role" "analyst_warehouse_usage" {
  role_name  = snowflake_role.data_analyst.name
  privileges = ["USAGE", "OPERATE"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.analytics.name
  }
}

resource "snowflake_grant_privileges_to_role" "analyst_database_usage" {
  role_name  = snowflake_role.data_analyst.name
  privileges = ["USAGE"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.analytics.name
  }
}

resource "snowflake_grant_privileges_to_role" "analyst_marts_schema" {
  role_name  = snowflake_role.data_analyst.name
  privileges = ["USAGE"]

  on_schema {
    schema_name = "${snowflake_database.analytics.name}.${snowflake_schema.marts.name}"
  }
}

resource "snowflake_grant_privileges_to_role" "analyst_marts_tables" {
  role_name  = snowflake_role.data_analyst.name
  privileges = ["SELECT"]

  on_schema_object {
    object_type = "TABLE"
    on_schema {
      schema_name = "${snowflake_database.analytics.name}.${snowflake_schema.marts.name}"
    }
  }
}

###############################################################################
# Grants – DBT role (mirrors DATA_ENGINEER but service-account scoped)
###############################################################################
resource "snowflake_grant_privileges_to_role" "dbt_warehouse" {
  role_name  = snowflake_role.dbt_role.name
  privileges = ["USAGE", "OPERATE"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.transform.name
  }
}

resource "snowflake_grant_privileges_to_role" "dbt_database" {
  role_name  = snowflake_role.dbt_role.name
  privileges = ["USAGE", "CREATE SCHEMA"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.analytics.name
  }
}

###############################################################################
# Example User (sensitive fields commented out – set via terraform.tfvars
# or a secrets manager, never hard-coded)
###############################################################################
resource "snowflake_user" "dbt_service_account" {
  name         = "SVC_DBT"
  display_name = "dbt Service Account"
  comment      = "Service account used by dbt Cloud for CI/CD pipeline runs."
  login_name   = "SVC_DBT"

  # Set these via var or secrets manager – never hard-code credentials
  # password             = var.dbt_service_account_password
  # rsa_public_key       = var.dbt_rsa_public_key

  default_role      = snowflake_role.dbt_role.name
  default_warehouse = snowflake_warehouse.transform.name
  default_namespace = "${snowflake_database.analytics.name}.${snowflake_schema.marts.name}"

  must_change_password = false
  disabled             = false
}

resource "snowflake_grant_privileges_to_role" "dbt_user_role_grant" {
  role_name  = snowflake_role.dbt_role.name
  privileges = []  # Roles are granted to users separately via GRANT ROLE

  # Note: use snowflake_role_grants resource for user-to-role assignments
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.transform.name
  }
}

###############################################################################
# Resource Monitor
###############################################################################
resource "snowflake_resource_monitor" "monthly" {
  name         = upper("${var.environment}_MONTHLY_MONITOR")
  credit_quota = var.environment == "prod" ? 2000 : 200
  frequency    = "MONTHLY"

  start_timestamp = "IMMEDIATELY"

  # Notification thresholds (account-level email must be configured separately)
  notify_triggers            = [75, 90]
  suspend_triggers           = [100]
  suspend_immediate_triggers = [110]
}

resource "snowflake_warehouse" "transform_monitor" {
  # Attach resource monitor to transform warehouse
  # (done via ALTER WAREHOUSE in SQL; Terraform uses the warehouse resource)
  name             = snowflake_warehouse.transform.name
  resource_monitor = snowflake_resource_monitor.monthly.name

  # Reuse settings from the main transform warehouse resource above
  warehouse_size   = "SMALL"
  auto_suspend     = var.warehouse_auto_suspend_seconds
  auto_resume      = true

  lifecycle {
    ignore_changes = [
      # Avoid drift from manual operational changes
      initially_suspended,
    ]
  }
}
