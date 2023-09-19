
variable "user_pool_name" {
  type        = string
  description = "Name of the Cognito User Pool"
  default     = "nucleus-dum-cognito-user-pool"
}

variable "user_pool_domain" {
  type        = string
  description = "Unique domain name for the DUM Cognito Pool"
  default     = "pds-nucleus-dum"
}

variable "email_invitation_subject" {
  type        = string
  description = "Subject line for use with invitation emails"
  default     = "PDS Data Upload Manager Temporary Credentials"
}

variable "email_invitation_message" {
  type        = string
  description = "Message body for use with invitation emails"
  default     = "Your PDS Data Upload Manager username is {username} and temporary password is {####}. You must change this password the next time you log in."
}

variable "sms_text_invitation_message" {
  type        = string
  description = "Message body for use with SMS text invitations"
  default     = "Your username is {username} and temporary password is {####}"
}

variable "ssm_param_cognito_user_pool_id" {
  type        = string
  description = "SSM Parameter location for securely storing the Cognito User Pool ID"
  default     = "/pds/dum/cognito/cognito-user-pool/user-pool-id"
}

variable "ssm_param_cognito_user_pool_client_id" {
  type        = string
  description = "SSM Parameter location for securely storing the Cognito User Pool Client ID"
  default     = "/pds/dum/cognito/cognito-user-pool/user-pool-client-id"
}

variable "nucleus_dum_cognito_user_groups" {
  description = "List of the PDS DUM Cognito User Groups"
  type = list(
    object(
      {
        name        = string
        description = string
      }
    )
  )
  default = [
    {
      name        = "PDS_ATM_USERS",
      description = "User group for PDS Atmospheres Node"
    },
    {
      name        = "PDS_ENG_USERS"
      description = "User group for PDS Engineering Node"
    },
    {
      name        = "PDS_GEO_NODE"
      description = "User group for PDS Geosciences Node"
    },
    {
      name        = "PDS_IMG_NODE"
      description = "User group for PDS Cartography and Imaging Sciences Discipline Node"
    },
    {
      name        = "PDS_NAIF_NODE"
      description = "User group for PDS Navigational and Ancillary Information Facility Node"
    },
    {
      name        = "PDS_PPI_NODE"
      description = "User group for PDS Planetary Plasma Interactions Node"
    },
    {
      name        = "PDS_RS_NODE"
      description = "User group for PDS Radio Science Node"
    },
    {
      name        = "PDS_RMS_NODE",
      description = "User group for PDS Ring-Moon Systems Node"
    },
    {
      name        = "PDS_SBN_NODE",
      description = "User group for PDS Small Bodies Node"
    }
  ]
}

variable "nucleus_dum_cognito_initial_users" {
  description = "Optional list of users and group to pre-populate the User Pool with"
  type = list(
    object(
      {
        username = string
        password = string
        group    = string
        email    = string
      }
    )
  )
  default = []
}
