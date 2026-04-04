###############################################################################
# Chapter 16: Terraform Variables
# Snowflake Master Course
###############################################################################

variable "snowflake_account" {
  description = "Snowflake account identifier (e.g. xy12345.us-east-1 or xy12345.us-east-1.aws)"
  type        = string
  # Never provide a default here – always supply via tfvars or environment variable
}

variable "snowflake_user" {
  description = "Snowflake username for the Terraform service account"
  type        = string
  # Set via TF_VAR_snowflake_user environment variable or terraform.tfvars
}

variable "snowflake_private_key_path" {
  description = "Path to the PEM-encoded RSA private key file used for key-pair authentication"
  type        = string
  default     = "~/.ssh/snowflake_terraform_key.p8"
}

variable "snowflake_role" {
  description = "Snowflake role assumed by Terraform. Must have SYSADMIN + SECURITYADMIN privileges."
  type        = string
  default     = "SYSADMIN"

  validation {
    condition     = contains(["SYSADMIN", "ACCOUNTADMIN", "SECURITYADMIN"], var.snowflake_role)
    error_message = "snowflake_role must be one of: SYSADMIN, ACCOUNTADMIN, SECURITYADMIN."
  }
}

variable "environment" {
  description = "Deployment environment. Controls resource naming prefixes and sizing."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "warehouse_auto_suspend_seconds" {
  description = "Number of seconds of inactivity before a warehouse auto-suspends."
  type        = number
  default     = 120

  validation {
    condition     = var.warehouse_auto_suspend_seconds >= 60 && var.warehouse_auto_suspend_seconds <= 3600
    error_message = "warehouse_auto_suspend_seconds must be between 60 and 3600."
  }
}

variable "max_cluster_count_analytics" {
  description = "Maximum number of clusters for the multi-cluster analytics warehouse."
  type        = number
  default     = 3

  validation {
    condition     = var.max_cluster_count_analytics >= 1 && var.max_cluster_count_analytics <= 10
    error_message = "max_cluster_count_analytics must be between 1 and 10."
  }
}

variable "data_retention_days_prod" {
  description = "Number of days to retain Time Travel data in the production environment."
  type        = number
  default     = 14

  validation {
    condition     = contains([0, 1, 7, 14, 30, 90], var.data_retention_days_prod)
    error_message = "data_retention_days_prod must be 0, 1, 7, 14, 30, or 90."
  }
}

variable "monthly_credit_quota_prod" {
  description = "Monthly credit quota for the production resource monitor."
  type        = number
  default     = 2000
}

variable "monthly_credit_quota_dev" {
  description = "Monthly credit quota for the development resource monitor."
  type        = number
  default     = 200
}

variable "tags" {
  description = "Common tags/labels to apply to all Terraform-managed resources (stored as Snowflake object comments)."
  type        = map(string)
  default = {
    managed_by  = "terraform"
    course      = "snowflake-master-course"
    chapter     = "16"
  }
}
