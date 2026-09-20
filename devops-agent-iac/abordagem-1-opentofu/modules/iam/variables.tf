variable "name_prefix" { type = string }

variable "data_bucket_arns" {
  description = "ARNs dos buckets de dados que as workloads poderão acessar"
  type        = list(string)
}

variable "athena_results_bucket_arn" { type = string }

variable "kms_key_arns" {
  description = "ARNs das CMKs utilizáveis pelas workloads"
  type        = list(string)
}

variable "github_oidc" {
  description = "Configuração da role de deploy assumida pelo GitHub Actions via OIDC"
  type = object({
    enabled              = bool
    repository           = string       # ex.: "usuario/agentes-devops"
    allowed_refs         = list(string) # ex.: ["refs/heads/main"]
    allow_pull_requests  = optional(bool, true)
    create_oidc_provider = optional(bool, true)
  })
}

variable "vpc_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
