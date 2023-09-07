
output "nucleus_dum_api_id" {
  value = aws_api_gateway_rest_api.nucleus_dum_api.id
}

output "nucleus_dum_api_stages" {
  value = [aws_api_gateway_deployment.nucleus_dum_api_deployments.*.stage_name]
}