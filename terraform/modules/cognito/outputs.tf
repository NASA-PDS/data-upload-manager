
output "nucleus_dum_cognito_user_pool_id" {
  value = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
}

output "nucleus_dum_cognito_user_pool_client_id" {
  value = aws_ssm_parameter.nucleus_dum_cognito_user_pool_client_id_parameter.value
}

output "nucleus_dum_cognito_users" {
  value = [var.nucleus_dum_cognito_initial_users.*.username]
}