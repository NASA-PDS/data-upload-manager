# Terraform module for the Data Upload Manager (DUM) Cognito User Pool

resource "aws_cognito_user_pool" "nucleus_dum_cognito_user_pool" {
  name = var.user_pool_name

  admin_create_user_config {
    invite_message_template {
      email_subject = var.email_invitation_subject
      email_message = var.email_invitation_message
      sms_message   = var.sms_text_invitation_message
    }

    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  auto_verified_attributes = ["email"]

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}

resource "aws_ssm_parameter" "nucleus_dum_cognito_user_pool_id_parameter" {
  name       = format(var.ssm_param_cognito_user_pool_id)
  type       = "String"
  value      = aws_cognito_user_pool.nucleus_dum_cognito_user_pool.id
  depends_on = [aws_cognito_user_pool.nucleus_dum_cognito_user_pool]
}

resource "aws_cognito_user_pool_client" "nucleus_dum_cognito_user_pool_client" {
  name                                 = "nucleus-dum-cognito-user-pool-client"
  user_pool_id                         = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  callback_urls                        = ["http://localhost:3000"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid"]
  explicit_auth_flows                  = ["ALLOW_CUSTOM_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH"]
  supported_identity_providers         = ["COGNITO"]

  refresh_token_validity = 30
  access_token_validity  = 60
  id_token_validity      = 60
  token_validity_units {
    refresh_token = "days"
    access_token  = "minutes"
    id_token      = "minutes"
  }
}

resource "aws_ssm_parameter" "nucleus_dum_cognito_user_pool_client_id_parameter" {
  name       = format(var.ssm_param_cognito_user_pool_client_id)
  type       = "String"
  value      = aws_cognito_user_pool_client.nucleus_dum_cognito_user_pool_client.id
  depends_on = [aws_cognito_user_pool_client.nucleus_dum_cognito_user_pool_client]
}

resource "aws_cognito_user_pool_domain" "nucleus_dum_cognito_user_pool_domain" {
  domain       = var.user_pool_domain
  user_pool_id = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
}

resource "aws_cognito_user_group" "nucleus_dum_cognito_user_groups" {
  count = length(var.nucleus_dum_cognito_user_groups)

  name         = var.nucleus_dum_cognito_user_groups[count.index].name
  description  = var.nucleus_dum_cognito_user_groups[count.index].description
  user_pool_id = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
}

resource "aws_cognito_user" "nucleus_dum_cognito_initial_users" {
  count = length(var.nucleus_dum_cognito_initial_users)

  username                 = var.nucleus_dum_cognito_initial_users[count.index].username
  user_pool_id             = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
  desired_delivery_mediums = ["EMAIL"]
  enabled                  = true
  message_action           = "SUPPRESS"
  password                 = var.nucleus_dum_cognito_initial_users[count.index].password

  attributes = {
    email          = var.nucleus_dum_cognito_initial_users[count.index].email
    email_verified = true
  }
}

resource "aws_cognito_user_in_group" "nucleus_dum_cognito_initial_user_group_assignment" {
  count      = length(var.nucleus_dum_cognito_initial_users)
  depends_on = [aws_cognito_user.nucleus_dum_cognito_initial_users]

  username     = var.nucleus_dum_cognito_initial_users[count.index].username
  group_name   = var.nucleus_dum_cognito_initial_users[count.index].group
  user_pool_id = aws_ssm_parameter.nucleus_dum_cognito_user_pool_id_parameter.value
}
