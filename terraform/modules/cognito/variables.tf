# Variables for DUM Cognito Client Setup Using Shared Cognito Infrastructure

variable "pds_common_cognito_user_pool_id_ssm_parameter_name" {
  type        = string
  description = "SSM parameter name that stores the shared PDS Cognito User Pool ID"
  default     = "/pds/cds-infra/cognito/user-pool/user-pool-id"
}

variable "dum_cognito_auth_client_id_ssm_parameter_name" {
  type        = string
  description = "SSM parameter name used by DUM to store its Cognito app client ID"
  default     = "/pds/dum/cognito-auth-client-id"
}

variable "cognito_user_pool_client_name" {
  type        = string
  description = "Name of the DUM Cognito app client"
  default     = "pds-dum-auth-client"
}

variable "callback_urls" {
  type        = list(string)
  description = "Callback URLs for the DUM Cognito app client"
  default     = ["http://localhost:3000"]
}

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}
