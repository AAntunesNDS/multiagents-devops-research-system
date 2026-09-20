###############################################################################
# Bootstrap do backend remoto (executado UMA ÚNICA VEZ, com state local).
# Cria: bucket S3 versionado/criptografado + tabela DynamoDB de state locking.
###############################################################################
terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "OpenTofu"
      Component = "tfstate-backend"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "agentes-devops"
}

resource "aws_kms_key" "tfstate" {
  description             = "CMK para criptografia do state do OpenTofu"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "tfstate" {
  name          = "alias/${var.project_name}-tfstate"
  target_key_id = aws_kms_key.tfstate.key_id
}

resource "aws_s3_bucket" "tfstate" {
  bucket        = "${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.tfstate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_dynamodb_table" "tflock" {
  name         = "${var.project_name}-tflock"
  billing_mode = "PAY_PER_REQUEST"   # custo ~US$ 0 em volume de CI
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
  server_side_encryption { enabled = true }
  point_in_time_recovery { enabled = true }
}

output "state_bucket" { value = aws_s3_bucket.tfstate.id }
output "lock_table" { value = aws_dynamodb_table.tflock.name }
