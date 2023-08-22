
variable "region" {
  type        = string
  default     = "us-west-2"
}

variable "profile" {
  type = string
}

variable "credential_file" {
  type = string
}

variable "lambda_s3_bucket_name" {
  type = string
}

variable "lambda_ingress_service_iam_role_arn" {
  type = string
}