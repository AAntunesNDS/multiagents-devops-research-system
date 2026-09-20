variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "agentes-devops"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "hml", "prod"], var.environment)
    error_message = "environment deve ser dev, hml ou prod."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "single_nat_gateway" {
  type    = bool
  default = true
}

variable "enable_interface_endpoints" {
  type    = bool
  default = false
}

variable "github_repository" {
  type    = string
  default = "seu-usuario/agentes-devops-iac"
}

variable "cost_center" {
  type    = string
  default = "tcc-arquitetura-dados"
}
