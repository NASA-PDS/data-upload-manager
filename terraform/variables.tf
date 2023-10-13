
variable "region" {
  type        = string
  default     = "us-west-2"
  description = "AWS region to allocate AWS resources to"
}

# variable "profile" {
#   type        = string
#   description = "Name of the AWS account profile"
# }

# variable "credential_file" {
#   type        = string
#   description = "Path to an AWS credentials file on the local machine"
# }

variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to upload Lambda artifacts to"
}

variable "iam_role" {
  type        = string
  description = "IAM Role for CloudWatch Logging"
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
