###############################################################################
# Chapter 16: Terraform Outputs
# Snowflake Master Course
###############################################################################

output "analytics_database_name" {
  description = "The fully-qualified name of the analytics database."
  value       = snowflake_database.analytics.name
}

output "dev_database_name" {
  description = "The name of the developer sandbox database."
  value       = snowflake_database.dev.name
}

output "transform_warehouse_name" {
  description = "The name of the ELT / dbt transform warehouse."
  value       = snowflake_warehouse.transform.name
}

output "analytics_warehouse_name" {
  description = "The name of the multi-cluster BI analytics warehouse."
  value       = snowflake_warehouse.analytics.name
}

output "reporting_warehouse_name" {
  description = "The name of the lightweight reporting warehouse."
  value       = snowflake_warehouse.reporting.name
}

output "data_engineer_role_name" {
  description = "The name of the DATA_ENGINEER role."
  value       = snowflake_role.data_engineer.name
}

output "data_analyst_role_name" {
  description = "The name of the DATA_ANALYST role."
  value       = snowflake_role.data_analyst.name
}

output "data_scientist_role_name" {
  description = "The name of the DATA_SCIENTIST role."
  value       = snowflake_role.data_scientist.name
}

output "dbt_role_name" {
  description = "The name of the dbt service account role."
  value       = snowflake_role.dbt_role.name
}

output "resource_monitor_name" {
  description = "The name of the monthly resource monitor."
  value       = snowflake_resource_monitor.monthly.name
}

output "raw_schema_full_name" {
  description = "Fully-qualified name of the RAW schema."
  value       = "${snowflake_database.analytics.name}.${snowflake_schema.raw.name}"
}

output "marts_schema_full_name" {
  description = "Fully-qualified name of the MARTS schema."
  value       = "${snowflake_database.analytics.name}.${snowflake_schema.marts.name}"
}

output "dbt_service_account_name" {
  description = "Login name of the dbt service account user."
  value       = snowflake_user.dbt_service_account.name
  sensitive   = false
}
