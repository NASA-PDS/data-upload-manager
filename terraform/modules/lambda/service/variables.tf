
variable "project" {
  type        = string
  description = "Project name"
}

variable "cicd" {
  type        = string
  description = "CI/CD environment name"
}

variable "venue" {
  type        = string
  description = "Name of the venue to be deployed to. Should be one of [dev,test,prod]"
}

variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to upload Lambda artifacts to"
}

variable "lambda_s3_bucket_partition" {
  type    = string
  default = "aws"
}

variable "lambda_ingress_localstack_context" {
  type        = bool
  description = "Flag indicating whether the ingress service will execute in a localstack context or not"
}

variable "lambda_ingress_service_function_name" {
  type        = string
  default     = "nucleus-dum-ingress-service"
  description = "Name to assign to the Lambda Ingress Service function"
}

variable "lambda_status_service_function_name" {
  type        = string
  default     = "nucleus-dum-status-service"
  description = "Name to assign to the Lambda Status Service function"
}

variable "lambda_metadata_sync_service_function_name" {
  type        = string
  default     = "nucleus-dum-metadata-sync-service"
  description = "Name to assign to the Lambda Metadata Sync Service function"
}

variable "lambda_ingress_service_function_description" {
  type        = string
  default     = "PDS Data Upload Manager Ingress Service function"
  description = "Description for the Lambda Ingress Service function"
}

variable "lambda_status_service_function_description" {
  type        = string
  default     = "PDS Data Upload Mangager Status Service function"
  description = "Description for the Lambda Status Service function"
}

variable "lambda_metadata_sync_service_function_description" {
  type        = string
  default     = "PDS Data Upload Manager Metadata Sync Service function"
  description = "Description for the Lambda Metadata Sync Service function"
}

variable "lambda_ingress_service_iam_role_arn" {
  type        = string
  description = "IAM role ARN to allocate to the Ingress Service Lambda function"
}

variable "lambda_ingress_service_default_buckets" {
  description = "List of the default S3 staging buckets to create for each PDS Node, each name will be appended with designated venue name to form the final bucket name"
  type = list(
    object(
      {
        name        = string
        description = string
      }
    )
  )
  default = [
    {
      name        = "pds-atm-staging",
      description = "Default staging bucket for PDS Atmospheres Node"
    },
    {
      name        = "pds-eng-staging"
      description = "Default staging bucket for PDS Engineering Node"
    },
    {
      name        = "pds-geo-staging"
      description = "Default staging bucket for PDS Geosciences Node"
    },
    {
      name        = "pds-img-staging"
      description = "Default staging bucket for PDS Cartography and Imaging Sciences Discipline Node"
    },
    {
      name        = "pds-naif-staging"
      description = "Default staging bucket for PDS Navigational and Ancillary Information Facility Node"
    },
    {
      name        = "pds-ppi-staging"
      description = "Default staging bucket for PDS Planetary Plasma Interactions Node"
    },
    {
      name        = "pds-rs-staging"
      description = "Default staging bucket for PDS Radio Science Node"
    },
    {
      name        = "pds-rms-staging",
      description = "Default staging bucket for PDS Ring-Moon Systems Node"
    },
    {
      name        = "pds-sbn-staging",
      description = "Default staging bucket for PDS Small Bodies Node"
    }
  ]
}

variable "expected_bucket_owner" {
  type        = string
  description = "The AWS Account ID that is expected to own the S3 buckets. Used for security verification."
  default     = ""
}

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "skip_lambda_layers" {
  description = "When set to true, skips Lambda layer creation. Use this when applying tags to existing resources or when layer source files are not available."
  type        = bool
  default     = false
}
