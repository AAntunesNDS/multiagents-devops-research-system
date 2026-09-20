###############################################################################
# Módulo Security Groups: SGs de workload sem egress 0.0.0.0/0 aberto por
# padrão. O tráfego sai apenas via 443 (VPC Endpoints / NAT) — regra mínima
# necessária para Lambda, Glue e futuros microserviços.
###############################################################################
resource "aws_security_group" "lambda" {
  name        = "${var.name_prefix}-lambda-sg"
  description = "SG das funcoes Lambda em subnets privadas"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-lambda-sg" })

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_egress_rule" "lambda_https" {
  security_group_id = aws_security_group.lambda.id
  description       = "HTTPS para servicos AWS (VPC Endpoints / NAT)"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "glue" {
  name        = "${var.name_prefix}-glue-sg"
  description = "SG das Glue Connections (exige self-referencing rule)"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-glue-sg" })

  lifecycle { create_before_destroy = true }
}

# Requisito da AWS: Glue exige regra self-referencing all-TCP
resource "aws_vpc_security_group_ingress_rule" "glue_self" {
  security_group_id            = aws_security_group.glue.id
  description                  = "Self-referencing exigido pelo AWS Glue"
  referenced_security_group_id = aws_security_group.glue.id
  ip_protocol                  = "-1"
}

resource "aws_vpc_security_group_egress_rule" "glue_self" {
  security_group_id            = aws_security_group.glue.id
  description                  = "Self-referencing exigido pelo AWS Glue"
  referenced_security_group_id = aws_security_group.glue.id
  ip_protocol                  = "-1"
}

resource "aws_vpc_security_group_egress_rule" "glue_https" {
  security_group_id = aws_security_group.glue.id
  description       = "HTTPS para S3/Glue/KMS"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "microservices" {
  name        = "${var.name_prefix}-microservices-sg"
  description = "SG reservado para os proximos agentes (microservicos)"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-microservices-sg" })

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "microservices_vpc" {
  security_group_id = aws_security_group.microservices.id
  description       = "HTTP interno a partir da VPC"
  cidr_ipv4         = var.vpc_cidr
  from_port         = 8080
  to_port           = 8080
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "microservices_https" {
  security_group_id = aws_security_group.microservices.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}
