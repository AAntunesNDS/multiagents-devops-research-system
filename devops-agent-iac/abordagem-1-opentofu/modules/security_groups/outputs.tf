output "lambda_sg_id" { value = aws_security_group.lambda.id }
output "glue_sg_id" { value = aws_security_group.glue.id }
output "microservices_sg_id" { value = aws_security_group.microservices.id }
