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
  description = "AWS region for deployed resources"
  default     = "us-west-2"
}

variable "profile" {
  type        = string
  description = "AWS account profile name"
}

variable "credential_file" {
  type        = string
  description = "Path to the AWS credentials file on the local machine"
}

variable "venue" {
  type        = string
  description = "Deployment environment. Expected values: dev, test, or prod"
}

variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket used to upload Lambda artifacts"
}

variable "api_gateway_endpoint_type" {
  type        = string
  description = "API Gateway endpoint type. Expected values: PRIVATE or REGIONAL"
  default     = "PRIVATE"
}

variable "api_gateway_lambda_role_arn" {
  type        = string
  description = "ARN of the IAM role with permissions required for API Gateway and Lambda"
}

# TODO: Remove if API is always REGIONAL
variable "api_gateway_policy_source_vpc" {
  type        = string
  description = "VPC ID allowed to access the private API Gateway deployment"
}

variable "lambda_ingress_service_iam_role_arn" {
  type        = string
  description = "IAM role ARN assigned to the ingress service Lambda function"
}

variable "lambda_authorizer_iam_role_arn" {
  type        = string
  description = "IAM role ARN assigned to the Lambda authorizer function"
}

variable "localstack_context" {
  type        = bool
  description = "Whether DUM is being deployed to a Localstack instance"
  default     = false
}

# Cognito (shared + DUM client)
variable "pds_common_cognito_user_pool_id_ssm_parameter_name" {
  type        = string
  description = "SSM parameter name that stores the shared PDS common Cognito user pool ID"
  default     = "/pds/cds-infra/cognito/user-pool/user-pool-id"
}

variable "dum_cognito_auth_client_id_ssm_parameter_name" {
  type        = string
  description = "SSM parameter name used to store the DUM Cognito app client ID"
  default     = "/pds/dum/cognito-auth-client-id"
}

variable "cognito_user_pool_client_name" {
  type        = string
  description = "Name of the DUM Cognito app client"
  default     = "pds-dum-auth-client"
}

variable "nucleus_dum_client_cloudwatch_log_group" {
  type        = string
  description = "Name of the CloudWatch log group used by the DUM ingress client script"
  default     = "/pds/nucleus/dum/client-log-group"
}

variable "lambda_ingress_service_default_buckets" {
  type = list(object({
    name        = string
    description = string
  }))
  description = "List of default S3 staging buckets to create for each PDS node. Each bucket name is suffixed with the selected venue"
}

variable "expected_bucket_owner" {
  type        = string
  description = "AWS account ID expected to own the S3 buckets, used for security verification"
  default     = ""
}

# Tags
variable "tag_tenant" {
  type        = string
  description = "Owner discipline node, such as en, sbn, img, or atm"
  default     = "en"
}

variable "tag_venue" {
  type        = string
  description = "Environment tag, such as pds-cds-dev or pds-cds-prod"
  default     = "pds-cds-dev"
}

variable "tag_component" {
  type        = string
  description = "Component name, such as dum, nucleus, or registry"
  default     = "dum"
}

variable "tag_cicd" {
  type        = string
  description = "Deployment method tag, such as iac or cd"
  default     = "iac"
}

variable "tag_managedby" {
  type        = string
  description = "PDS team email address"
}
