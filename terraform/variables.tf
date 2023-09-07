
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

variable "api_gateway_lambda_role_arn" {
  type = string
}

# TODO: this may go away when API is deployed as REGIONAL instead of PRIVATE
variable "api_gateway_policy_source_vpc" {
  type = string
}

variable "lambda_ingress_service_iam_role_arn" {
  type = string
}

variable "lambda_authorizer_iam_role_arn" {
  type = string
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
}

variable "nucleus_dum_client_cloudwatch_log_group" {
  type    = string
  default = "/pds/nucleus/dum/client-log-group"
}
