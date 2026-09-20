###############################################################################
# Módulo IAM: roles de execução das workloads (Glue, Lambda, Step Functions,
# Athena) + role de deploy do GitHub Actions via OIDC (sem chaves estáticas).
# Todas as policies são escritas com escopo de recurso — nada de "Resource: *"
# exceto onde a API da AWS não suporta ARN.
###############################################################################
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name
  bucket_objects = [for arn in var.data_bucket_arns : "${arn}/*"]
}

# ------------------------------- Lambda -------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name                 = "${var.name_prefix}-lambda-exec"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  max_session_duration = 3600
  tags                 = var.tags
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*"]
  }

  statement {
    sid       = "S3Data"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = local.bucket_objects
  }

  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = var.data_bucket_arns
  }

  statement {
    sid       = "KMS"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = var.kms_key_arns
  }

  # ENI em VPC: a API exige Resource "*", restringimos por condição de VPC
  statement {
    sid = "VpcNetworking"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "lambda-least-privilege"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# -------------------------------- Glue --------------------------------
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.name_prefix}-glue-job"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "glue" {
  statement {
    sid       = "S3Data"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = local.bucket_objects
  }
  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = var.data_bucket_arns
  }
  statement {
    sid       = "Catalog"
    actions   = ["glue:Get*", "glue:BatchGet*", "glue:CreateTable", "glue:UpdateTable", "glue:CreatePartition", "glue:BatchCreatePartition"]
    resources = [
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:catalog",
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:database/${var.name_prefix}_*",
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:table/${var.name_prefix}_*/*"
    ]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:AssociateKmsKey"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws-glue/*"]
  }
  statement {
    sid       = "KMS"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = var.kms_key_arns
  }
  statement {
    sid     = "VpcConnections"
    actions = ["ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeVpcEndpoints", "ec2:DescribeRouteTables"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "glue" {
  name   = "glue-least-privilege"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

# ---------------------------- Step Functions ----------------------------
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${var.name_prefix}-stepfunctions"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    sid       = "InvokeLambda"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${var.name_prefix}-*"]
  }
  statement {
    sid       = "RunGlue"
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = ["arn:${local.partition}:glue:${local.region}:${local.account_id}:job/${var.name_prefix}-*"]
  }
  statement {
    sid       = "Queues"
    actions   = ["sqs:SendMessage"]
    resources = ["arn:${local.partition}:sqs:${local.region}:${local.account_id}:${var.name_prefix}-*"]
  }
  statement {
    sid       = "KMS"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = var.kms_key_arns
  }
  statement {
    sid       = "Telemetry"
    actions   = ["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups", "xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "step_functions" {
  name   = "sfn-least-privilege"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions.json
}

# -------------------------------- Athena --------------------------------
data "aws_iam_policy_document" "athena_analyst" {
  statement {
    sid       = "Athena"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"]
    resources = ["arn:${local.partition}:athena:${local.region}:${local.account_id}:workgroup/${var.name_prefix}-*"]
  }
  statement {
    sid       = "Results"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.athena_results_bucket_arn, "${var.athena_results_bucket_arn}/*"]
  }
  statement {
    sid       = "ReadData"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = concat(var.data_bucket_arns, local.bucket_objects)
  }
  statement {
    sid       = "Catalog"
    actions   = ["glue:GetDatabase*", "glue:GetTable*", "glue:GetPartition*"]
    resources = [
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:catalog",
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:database/${var.name_prefix}_*",
      "arn:${local.partition}:glue:${local.region}:${local.account_id}:table/${var.name_prefix}_*/*"
    ]
  }
  statement {
    sid       = "KMS"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = var.kms_key_arns
  }
}

resource "aws_iam_policy" "athena_analyst" {
  name   = "${var.name_prefix}-athena-analyst"
  policy = data.aws_iam_policy_document.athena_analyst.json
  tags   = var.tags
}

# ---------------------- GitHub Actions OIDC (deploy) ----------------------
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.github_oidc.enabled && var.github_oidc.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = var.tags
}

locals {
  oidc_provider_arn = var.github_oidc.enabled ? (
    var.github_oidc.create_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : "arn:${local.partition}:iam::${local.account_id}:oidc-provider/token.actions.githubusercontent.com"
  ) : null

  github_subs = concat(
    [for ref in var.github_oidc.allowed_refs : "repo:${var.github_oidc.repository}:ref:${ref}"],
    var.github_oidc.allow_pull_requests ? ["repo:${var.github_oidc.repository}:pull_request"] : []
  )
}

data "aws_iam_policy_document" "github_assume" {
  count = var.github_oidc.enabled ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_subs
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  count                = var.github_oidc.enabled ? 1 : 0
  name                 = "${var.name_prefix}-gha-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_assume[0].json
  max_session_duration = 3600
  tags                 = var.tags
}

# Nota acadêmica: a role de deploy usa PowerUser + IAM restrito ao prefixo do
# projeto. Em produção regulada, substituir por policy enumerada e/ou
# Permissions Boundary.
resource "aws_iam_role_policy" "github_deploy_iam" {
  count = var.github_oidc.enabled ? 1 : 0
  name  = "deploy-iam-scoped"
  role  = aws_iam_role.github_deploy[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "IamScopedToProject"
        Effect = "Allow"
        Action = ["iam:*"]
        Resource = [
          "arn:${local.partition}:iam::${local.account_id}:role/${var.name_prefix}-*",
          "arn:${local.partition}:iam::${local.account_id}:policy/${var.name_prefix}-*",
          "arn:${local.partition}:iam::${local.account_id}:oidc-provider/token.actions.githubusercontent.com"
        ]
      },
      {
        Sid      = "PassRoleToServices"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "arn:${local.partition}:iam::${local.account_id}:role/${var.name_prefix}-*"
        Condition = {
          StringEquals = {
            "iam:PassedToService" = ["lambda.amazonaws.com", "glue.amazonaws.com", "states.amazonaws.com"]
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_deploy_power" {
  count      = var.github_oidc.enabled ? 1 : 0
  role       = aws_iam_role.github_deploy[0].name
  policy_arn = "arn:${local.partition}:iam::aws:policy/PowerUserAccess"
}
