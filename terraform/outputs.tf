output "aws_profile" {
  description = "AWS profile used for this deployment"
  value       = var.profile
}

output "nucleus_dum_api_id" {
  description = "API Gateway ID for the DUM service"
  value       = module.nucleus_dum_api.nucleus_dum_api_id
}

output "nucleus_dum_api_stages" {
  description = "List of API Gateway stages configured for the DUM service"
  value       = module.nucleus_dum_api.nucleus_dum_api_stages
}

output "pds_common_cognito_user_pool_id" {
  description = "Shared PDS Cognito User Pool ID used by DUM for authentication"
  value       = module.nucleus_dum_cognito.pds_common_cognito_user_pool_id
  sensitive   = true
}

output "dum_cognito_auth_client_id" {
  description = "Cognito app client ID created for DUM within the shared user pool"
  value       = module.nucleus_dum_cognito.dum_cognito_auth_client_id
  sensitive   = true
}

output "ingress_client_cloudwatch_log_group_name" {
  description = "CloudWatch log group name used by the DUM ingress client"
  value       = aws_cloudwatch_log_group.ingress_client_cloudwatch_log_group.name
}
