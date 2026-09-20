variable "name" {
  description = "Prefixo de nomes dos recursos de rede"
  type        = string
}

variable "cidr_block" {
  description = "CIDR da VPC"
  type        = string
  validation {
    condition     = can(cidrnetmask(var.cidr_block))
    error_message = "cidr_block deve ser um CIDR IPv4 válido."
  }
}

variable "azs" {
  description = "Availability Zones utilizadas"
  type        = list(string)
}

variable "public_subnet_bits" {
  type    = number
  default = 4
}

variable "private_subnet_bits" {
  type    = number
  default = 4
}

variable "single_nat_gateway" {
  description = "true = 1 NAT (dev, menor custo) | false = 1 NAT por AZ (prod, alta disponibilidade)"
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Cria VPC Endpoints de interface (reduz tráfego pelo NAT, aumenta custo fixo)"
  type        = bool
  default     = true
}

variable "interface_endpoint_services" {
  type    = list(string)
  default = ["sqs", "states", "glue", "lambda", "athena", "kms", "logs", "secretsmanager", "sts", "ssm"]
}

variable "flow_logs_kms_key_arn" {
  type    = string
  default = null
}

variable "flow_logs_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
