variable "name_prefix" {
  type = string
}

variable "keys" {
  description = <<-EOT
    Mapa de chaves a criar. Ex.:
    {
      data = { description = "Dados S3/Glue/Athena", service_principals = ["s3.amazonaws.com","glue.amazonaws.com"] }
    }
  EOT
  type = map(object({
    description         = string
    service_principals  = optional(list(string), [])
    additional_role_arns = optional(list(string), [])
    deletion_window     = optional(number, 30)
    enable_rotation     = optional(bool, true)
    multi_region        = optional(bool, false)
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}
