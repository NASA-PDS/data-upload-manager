# Main Terraform module for automated deployment of the PDS Data Upload Manager (DUM)
provider "aws" {
  region  = var.region
  profile = var.profile
  shared_credentials_files = [var.credential_file]
}

module "nucleus_dum_ingress_service_lambda" {
  source = "./modules/lambda/service"

  lambda_s3_bucket_name               = var.lambda_s3_bucket_name
  lambda_ingress_service_iam_role_arn = var.lambda_ingress_service_iam_role_arn
}

module "nucleus_dum_cognito" {
  source = "./modules/cognito"

  nucleus_dum_cognito_initial_users = var.nucleus_dum_cognito_initial_users
}

module "nucleus_dum_lambda_authorizer" {
  source = "./modules/lambda/authorizer"

  lambda_s3_bucket_name               = var.lambda_s3_bucket_name
  lambda_authorizer_iam_role_arn      = var.lambda_authorizer_iam_role_arn
  lambda_authorizer_cognito_pool_id   = module.nucleus_dum_cognito.nucleus_dum_cognito_user_pool_id
  lambda_authorizer_cognito_client_id = module.nucleus_dum_cognito.nucleus_dum_cognito_user_pool_client_id

  depends_on = [module.nucleus_dum_cognito]
}
