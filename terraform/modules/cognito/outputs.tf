# Outputs for DUM Cognito Client Setup Using Shared Cognito Infrastructure

output "pds_common_cognito_user_pool_id" {
  description = "Shared PDS Cognito User Pool ID used by DUM"
  value       = data.aws_ssm_parameter.pds_common_cognito_user_pool_id.value
}

output "dum_cognito_auth_client_id" {
  description = "DUM Cognito app client ID"
  value       = aws_cognito_user_pool_client.dum_auth_client.id
}
