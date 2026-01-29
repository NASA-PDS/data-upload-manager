
variable "project" {
  type        = string
  description = "Project name"
  default     = "pds-en"
}

variable "cicd" {
  type        = string
  description = "CI/CD environment name"
  default     = "pds-github"
}

variable "region" {
  type        = string
  default     = "us-west-2"
  description = "AWS region to allocate AWS resources to"
}

variable "profile" {
  type        = string
  description = "Name of the AWS account profile"
}

variable "credential_file" {
  type        = string
  description = "Path to an AWS credentials file on the local machine"
}

variable "venue" {
  type        = string
  description = "Name of the venue to be deployed to. Should be one of [dev,test,prod]"
}

variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to upload Lambda artifacts to"
}

variable "cloudwatch_iam_role_name" {
  type        = string
  description = "IAM Role name used for CloudWatch Logging"
}

variable "api_gateway_endpoint_type" {
  type        = string
  default     = "PRIVATE"
  description = "The endpoint type to assign to the API Gateway. Should be one of PRIVATE or REGIONAL"
}

variable "api_gateway_lambda_role_arn" {
  type        = string
  description = "ARN for an IAM role which has permissions for both API Gateway and Lambda"
}

# TODO: this may go away when API is deployed as REGIONAL instead of PRIVATE
variable "api_gateway_policy_source_vpc" {
  type        = string
  description = "ID of the VPC which is allowed to talk to the Private API Gateway deployment"
}

variable "lambda_ingress_service_iam_role_arn" {
  type        = string
  description = "IAM role ARN to allocate to the Ingress Service Lambda function"
}

variable "lambda_authorizer_iam_role_arn" {
  type        = string
  description = "IAM role ARN to allocate to the Lambda Authorizer function"
}

variable "localstack_context" {
  type        = bool
  default     = false
  description = "Flag indicating whether DUM is to be deployed to a Localstack instance"
}

variable "nucleus_dum_cognito_initial_users" {
  type = list(
    object(
      {
        username = string
        password = string
        group    = string
        email    = string
      }
    )
  )
  description = "List of Cognito users to pre-populate the User Pool with"
}

variable "nucleus_dum_client_cloudwatch_log_group" {
  type        = string
  default     = "/pds/nucleus/dum/client-log-group"
  description = "Name of the CloudWatch Log Group for use with the DUM Ingress Client script"
}

variable "lambda_ingress_service_default_buckets" {
  type = list(
    object(
      {
        name        = string
        description = string
      }
    )
  )
  description = "List of the default S3 staging buckets to create for each PDS Node, each name will be appended with the designated venue name to form the final bucket name"
}

variable "expected_bucket_owner" {
  type        = string
  description = "The AWS Account ID that is expected to own the S3 buckets. Used for security verification."
  default     = ""
}

# Mandatory tag variables
variable "tag_tenant" {
  type        = string
  description = "Owner Discipline Node (en, sbn, img, atm etc.)"
  default     = "en"
}

variable "tag_venue" {
  type        = string
  description = "Environment (pds-cds-dev, pds-cds-prod)"
  default     = "pds-cds-dev"
}

variable "tag_component" {
  type        = string
  description = "Component name (dum, nucleus, registry, etc.)"
  default     = "dum"
}

variable "tag_cicd" {
  type        = string
  description = "Deployment method (iac, cd, etc.)"
  default     = "iac"
}

variable "tag_managedby" {
  type        = string
  description = "PDS Team Email"
}
