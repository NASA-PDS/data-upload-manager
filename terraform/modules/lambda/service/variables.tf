
variable "lambda_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to upload Lambda artifacts to"
}

variable "lambda_ingress_service_function_name" {
  type        = string
  default     = "nucleus-dum-ingress-service"
  description = "Name to assign to the Lambda Ingress Service function"
}

variable "lambda_ingress_service_function_description" {
  type        = string
  default     = "PDS Data Upload Manager Ingress Service function"
  description = "Description for the Lambda Ingress Service function"
}

variable "lambda_ingress_service_iam_role_arn" {
  type        = string
  description = "IAM role ARN to allocate to the Ingress Service Lambda function"
}
