output "vpc_id" { value = aws_vpc.this.id }
output "vpc_cidr" { value = aws_vpc.this.cidr_block }
output "public_subnet_ids" { value = [for s in aws_subnet.public : s.id] }
output "private_subnet_ids" { value = [for s in aws_subnet.private : s.id] }
output "private_route_table_ids" { value = [for rt in aws_route_table.private : rt.id] }
output "nat_gateway_ids" { value = [for n in aws_nat_gateway.this : n.id] }
output "s3_gateway_endpoint_id" { value = aws_vpc_endpoint.s3.id }
