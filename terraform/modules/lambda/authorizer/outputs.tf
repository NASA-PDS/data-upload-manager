
output "lambda_authorizer_function_arn" {
  value = aws_lambda_function.lambda_authorizer.arn
}

output "lambda_authorizer_function_name" {
  value = aws_lambda_function.lambda_authorizer.function_name
}
