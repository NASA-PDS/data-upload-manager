
variable "region" {
  type        = string
  default     = "us-west-2"
  description = "AWS region to allocate AWS resources to"
}

variable "rest_api_name" {
  type        = string
  default     = "nucleus-data-upload-manager-api"
  description = "Name to assign to the REST API Gateway for use with DUM"
}

variable "rest_api_description" {
  type        = string
  default     = "REST API Gateway for use with the PDS Data Upload Manager"
  description = "Description text for the DUM API Gateway"
}

variable "api_gateway_endpoint_type" {
  type        = string
  default     = "PRIVATE"
  description = "The endpoint type to assign to the API Gateway. Should be one of PRIVATE or REGIONAL. REGIONAL is publicly reachable and requires api_gateway_web_acl_arn."

  validation {
    condition     = contains(["PRIVATE", "REGIONAL"], var.api_gateway_endpoint_type)
    error_message = "api_gateway_endpoint_type must be PRIVATE or REGIONAL."
  }
}

variable "api_gateway_web_acl_arn" {
  type        = string
  default     = null
  description = "ARN of an existing REGIONAL WAFv2 web ACL to associate with each stage of the API Gateway. Required when api_gateway_endpoint_type is REGIONAL; the web ACL must restrict access."
}

variable "api_gateway_require_web_acl" {
  type        = bool
  default     = true
  description = "Require api_gateway_web_acl_arn for REGIONAL endpoints. Only disabled for LocalStack deployments, which cannot host a WAF."
}

variable "api_gateway_lambda_role_arn" {
  type        = string
  description = "ARN of the IAM role to assign to the API Gateway. Must have permission to access AWS Lambda."
}

variable "api_gateway_policy_source_vpc" {
  type        = string
  default     = ""
  description = "VPC ID to allow traffic from within the DUM API Gateway. Only used, and required, when api_gateway_endpoint_type is PRIVATE."
}

variable "lambda_authorizer_function_arn" {
  type        = string
  description = "ARN of the Lambda Authorizer function used to authenticate API Gateway requests"
}

variable "lambda_authorizer_function_name" {
  type        = string
  description = "Name of the Lambda Authorizer function used to authenticate API Gateway requests"
}

variable "lambda_ingress_service_function_arn" {
  type        = string
  description = "ARN of the Lambda Ingress Service function for use with the API Gateway request resource"
}

variable "lambda_ingress_service_function_name" {
  type        = string
  description = "Name of the DUM Lambda Ingress Service function"
}

variable "status_queue_arn" {
  type        = string
  description = "ARN of the SQS Queue used with the Status Service"
}

variable "api_deployment_stages" {
  type        = list(string)
  description = "List of stages to create initial API Gateway deployments for"
  default     = ["test"]
}

# CloudWatch IAM role variable removed as we're not configuring API Gateway account

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}
