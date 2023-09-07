
output "aws_profile" {
  value = var.profile
}

output "nucleus_dum_api_id" {
  value = module.nucleus_dum_api.nucleus_dum_api_id
}

output "nucleus_dum_api_stages" {
  value = module.nucleus_dum_api.nucleus_dum_api_stages
}

output "nucleus_dum_cognito_user_pool_client_id" {
  value = nonsensitive(module.nucleus_dum_cognito.nucleus_dum_cognito_user_pool_client_id)
}

output "nucleus_dum_cognito_users" {
  value = module.nucleus_dum_cognito.nucleus_dum_cognito_users
}

output "ingress_client_cloudwatch_log_group_name" {
  value = aws_cloudwatch_log_group.ingress_client_cloudwatch_log_group.name
}
