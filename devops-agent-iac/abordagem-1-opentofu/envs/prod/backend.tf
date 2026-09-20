terraform {
  required_version = ">= 1.8.0"

  # Backend remoto S3 + DynamoDB (state locking).
  # Valores parametrizados via -backend-config no CI (partial configuration).
  backend "s3" {
    key     = "prod/base-infra.tfstate"
    encrypt = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}
