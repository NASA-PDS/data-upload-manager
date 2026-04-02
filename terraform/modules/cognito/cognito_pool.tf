# DUM Cognito Client Setup Using Shared Cognito Infrastructure
#
# NOTE:
# This module uses a PDS common Cognito user pool managed by a separate
# Terraform stack and does NOT create or manage the user pool, domain,
# users, or groups.
#
# It reads the existing user pool ID from SSM Parameter Store and creates
# only a DUM-specific Cognito app client. The client ID is stored in a
# DUM-specific SSM parameter for use by downstream services such as the
# Lambda authorizer.
#
# This ensures clear separation of ownership:
# - Shared infrastructure manages the user pool and user lifecycle
# - DUM manages only its own authentication client configuration
#
# IMPORTANT:
# This module must not modify or impact the shared user pool or any
# existing users/groups within it.

data "aws_ssm_parameter" "pds_common_cognito_user_pool_id" {
  name = var.pds_common_cognito_user_pool_id_ssm_parameter_name
}

resource "aws_cognito_user_pool_client" "dum_auth_client" {
  name         = var.cognito_user_pool_client_name
  user_pool_id = data.aws_ssm_parameter.pds_common_cognito_user_pool_id.value

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  callback_urls                        = var.callback_urls
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid"]

  explicit_auth_flows = [
    "ALLOW_CUSTOM_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  supported_identity_providers = ["COGNITO"]

  refresh_token_validity = 30
  access_token_validity  = 60
  id_token_validity      = 60

  token_validity_units {
    refresh_token = "days"
    access_token  = "minutes"
    id_token      = "minutes"
  }
}

resource "aws_ssm_parameter" "dum_cognito_auth_client_id_parameter" {
  name  = var.dum_cognito_auth_client_id_ssm_parameter_name
  type  = "String"
  value = aws_cognito_user_pool_client.dum_auth_client.id

  tags = var.tags
}
