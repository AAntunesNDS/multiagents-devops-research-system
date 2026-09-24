###############################################################################
# Módulo KMS: cria N chaves gerenciadas pelo cliente (CMK) com rotação anual,
# alias e key policy de menor privilégio (sem "kms:*" para "*").
###############################################################################
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  key_admin_principals = [
    "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root",
    "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:user/DevopsAgent"
  ]
}

data "aws_iam_policy_document" "key" {
  for_each = var.keys

  # Administração da chave permanece com a conta (via IAM), não com "*"
  statement {
    sid     = "EnableIAMUserPermissions"
    actions = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = local.key_admin_principals
    }
    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  # Serviços AWS autorizados a usar a chave, restritos à própria conta
  dynamic "statement" {
    for_each = length(each.value.service_principals) > 0 ? [1] : []
    content {
      sid = "AllowServiceUse"
      actions = [
        "kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
        "kms:GenerateDataKey*", "kms:DescribeKey", "kms:CreateGrant"
      ]
      resources = ["*"]
      principals {
        type        = "Service"
        identifiers = each.value.service_principals
      }
      condition {
        test     = "StringEquals"
        variable = "aws:SourceAccount"
        values   = [data.aws_caller_identity.current.account_id]
      }
    }
  }

  # Roles de workload (Lambda, Glue, Step Functions) autorizadas ao uso de dados
  dynamic "statement" {
    for_each = length(each.value.additional_role_arns) > 0 ? [1] : []
    content {
      sid = "AllowWorkloadRoles"
      actions = [
        "kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
        "kms:GenerateDataKey*", "kms:DescribeKey"
      ]
      resources = ["*"]
      principals {
        type        = "AWS"
        identifiers = each.value.additional_role_arns
      }
    }
  }
}

resource "aws_kms_key" "this" {
  for_each                = var.keys
  description             = each.value.description
  deletion_window_in_days = each.value.deletion_window
  enable_key_rotation     = each.value.enable_rotation
  multi_region            = each.value.multi_region
  policy                  = data.aws_iam_policy_document.key[each.key].json
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

resource "aws_kms_alias" "this" {
  for_each      = aws_kms_key.this
  name          = "alias/${var.name_prefix}-${each.key}"
  target_key_id = each.value.key_id
}
