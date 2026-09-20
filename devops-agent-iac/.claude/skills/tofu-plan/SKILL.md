---
name: tofu-plan
description: Roda fmt, validate, tflint, checkov e tofu plan na Abordagem 1 (OpenTofu), com estimativa de custo via infracost. Use quando o usuario pedir para "planejar", "validar" ou "ver o que vai mudar" na infraestrutura OpenTofu.
allowed-tools: Bash(tofu:*), Bash(tflint:*), Bash(checkov:*), Bash(infracost:*), Read, Grep
---

# tofu-plan

Execute nesta ordem, dentro de `abordagem-1-opentofu/`:

1. `tofu fmt -recursive` na raiz da abordagem.
2. `tflint --recursive --minimum-failure-severity=error`.
3. `checkov -d . --framework terraform --compact` — reporte achados mas NAO
   pare no primeiro erro; separe o que e decisao consciente ja documentada no
   README (ex.: CKV_AWS_111 nas acoes de ENI) do que e real.
4. Dentro de `envs/dev/`: `tofu init` (se `.terraform/` nao existir, avise que
   precisa do backend do bootstrap — nao rode `tofu init` sem backend-config
   em ambiente ja inicializado).
5. `tofu plan -out=tfplan`.
6. `tofu show -json tfplan | jq '.resource_changes | length'` e resuma quantos
   recursos mudam, por tipo.
7. Se `infracost` estiver configurado: `infracost breakdown --path tfplan --format table`.

Nunca rode `tofu apply` a partir desta skill — isso e responsabilidade da
skill `tofu-apply`, que exige confirmacao humana.

Reporte no final: resumo do plano (create/update/destroy por tipo), achados
do checkov, custo estimado, e se algo está fora do padrão descrito no
CLAUDE.md (ex.: NAT count errado, key policy sem condição de logs).
