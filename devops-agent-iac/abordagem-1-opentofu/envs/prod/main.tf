###############################################################################
# Root module do ambiente DEV — apenas composição de módulos.
# Toda a lógica vive em modules/; aqui ficam somente valores do ambiente.
###############################################################################
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "OpenTofu"
      CostCenter  = var.cost_center
      Layer       = "base-infra"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ------------------------------- KMS -------------------------------
# Nota de design: as key policies delegam à conta (root) + service principals.
# As roles de workload recebem permissão pelo lado IAM — isso evita a
# dependência circular KMS <-> IAM.
module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix

  keys = {
    data = {
      description        = "CMK para dados em repouso (S3, Glue, Athena)"
      service_principals = ["s3.amazonaws.com", "glue.amazonaws.com", "athena.amazonaws.com"]
    }
    messaging = {
      description        = "CMK para SQS e Step Functions"
      service_principals = ["sqs.amazonaws.com", "states.amazonaws.com", "sns.amazonaws.com"]
    }
    logs = {
      description        = "CMK para CloudWatch Logs"
      service_principals = ["logs.${var.aws_region}.amazonaws.com"]
    }
  }
}

# ------------------------------- Rede -------------------------------
module "vpc" {
  source = "../../modules/vpc"

  name                       = local.name_prefix
  cidr_block                 = var.vpc_cidr
  azs                        = var.azs
  single_nat_gateway         = var.single_nat_gateway
  enable_interface_endpoints = var.enable_interface_endpoints
  flow_logs_kms_key_arn      = module.kms.key_arns["logs"]
  flow_logs_retention_days   = var.environment == "prod" ? 90 : 14
}

# --------------------------- Security Groups ---------------------------
module "security_groups" {
  source      = "../../modules/security_groups"
  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  vpc_cidr    = module.vpc.vpc_cidr
}

# ------------------------- Buckets de dados -------------------------
resource "aws_s3_bucket" "data" {
  for_each = toset(["raw", "curated", "athena-results"])
  bucket   = "${local.name_prefix}-${each.key}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = module.kms.key_arns["data"]
    }
    bucket_key_enabled = true # reduz custo de chamadas KMS em até 99%
  }
}

resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "data" {
  for_each                = aws_s3_bucket.data
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.data["athena-results"].id
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {}
    expiration { days = 30 } # controle direto de custo de armazenamento
  }
}

# -------------------------------- IAM --------------------------------
module "iam" {
  source      = "../../modules/iam"
  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id

  data_bucket_arns          = [aws_s3_bucket.data["raw"].arn, aws_s3_bucket.data["curated"].arn]
  athena_results_bucket_arn = aws_s3_bucket.data["athena-results"].arn
  kms_key_arns              = values(module.kms.key_arns)

  github_oidc = {
    enabled              = true
    repository           = var.github_repository
    allowed_refs         = ["refs/heads/main"]
    allow_pull_requests  = true
    create_oidc_provider = true
  }
}

# ---------------- Contrato para os próximos agentes ----------------
# Publicado em SSM Parameter Store: os agentes seguintes leem daqui em vez de
# depender de outputs de state (desacoplamento entre camadas).
resource "aws_ssm_parameter" "platform_contract" {
  name  = "/${var.project_name}/${var.environment}/base-infra"
  type  = "String"
  tier  = "Advanced"
  value = jsonencode({
    vpc_id                  = module.vpc.vpc_id
    private_subnet_ids      = module.vpc.private_subnet_ids
    public_subnet_ids       = module.vpc.public_subnet_ids
    lambda_sg_id            = module.security_groups.lambda_sg_id
    glue_sg_id              = module.security_groups.glue_sg_id
    microservices_sg_id     = module.security_groups.microservices_sg_id
    kms_data_key_arn        = module.kms.key_arns["data"]
    kms_messaging_key_arn   = module.kms.key_arns["messaging"]
    kms_logs_key_arn        = module.kms.key_arns["logs"]
    lambda_role_arn         = module.iam.lambda_role_arn
    glue_role_arn           = module.iam.glue_role_arn
    step_functions_role_arn = module.iam.step_functions_role_arn
    raw_bucket              = aws_s3_bucket.data["raw"].bucket
    curated_bucket          = aws_s3_bucket.data["curated"].bucket
    athena_results_bucket   = aws_s3_bucket.data["athena-results"].bucket
  })
}
