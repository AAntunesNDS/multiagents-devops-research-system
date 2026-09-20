output "vpc_id" { value = module.vpc.vpc_id }
output "private_subnet_ids" { value = module.vpc.private_subnet_ids }
output "public_subnet_ids" { value = module.vpc.public_subnet_ids }
output "kms_key_arns" { value = module.kms.key_arns }
output "lambda_role_arn" { value = module.iam.lambda_role_arn }
output "glue_role_arn" { value = module.iam.glue_role_arn }
output "step_functions_role_arn" { value = module.iam.step_functions_role_arn }
output "github_deploy_role_arn" { value = module.iam.github_deploy_role_arn }
output "data_buckets" { value = { for k, b in aws_s3_bucket.data : k => b.bucket } }
output "platform_contract_parameter" { value = aws_ssm_parameter.platform_contract.name }
