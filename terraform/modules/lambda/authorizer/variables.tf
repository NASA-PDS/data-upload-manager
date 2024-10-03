
variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to upload Lambda artifacts to"
}

variable "lambda_authorizer_function_name" {
  type        = string
  default     = "nucleus-dum-authorizer"
  description = "Name to assign to the Lambda Authorizer function"
}

variable "lambda_authorizer_function_description" {
  type        = string
  default     = "JWT Authorizer function for use with the PDS Data Upload Manager API Gateway"
  description = "Description for the Lambda Authorizer function"
}

variable "lambda_authorizer_iam_role_arn" {
  type        = string
  description = "IAM role ARN to allocate to the Lambda Authorizer function"
}

variable "lambda_authorizer_cognito_pool_id" {
  type        = string
  description = "Cognito User Pool ID to assign to the Lambda Authorizer as an environment variable"
}

variable "lambda_authorizer_cognito_client_id" {
  type        = string
  description = "Cognito App Client ID to assign to the Lambda Authorizer as an environment variable"
}

variable "lambda_authorizer_localstack_context" {
    type        = bool
    description = "Flag indicating whether the authorizer will execute in a localstack context or not"
}
