output "lambda_role_arn" { value = aws_iam_role.lambda.arn }
output "glue_role_arn" { value = aws_iam_role.glue.arn }
output "step_functions_role_arn" { value = aws_iam_role.step_functions.arn }
output "athena_analyst_policy_arn" { value = aws_iam_policy.athena_analyst.arn }
output "github_deploy_role_arn" {
  value = try(aws_iam_role.github_deploy[0].arn, null)
}
output "workload_role_arns" {
  value = [aws_iam_role.lambda.arn, aws_iam_role.glue.arn, aws_iam_role.step_functions.arn]
}
