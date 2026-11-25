# One small VPC with one public subnet in a zone that offers the instance type: no inbound, HTTPS and Radicle's 8776 out,
# no NAT (as v2's). No inbound for Radicle either: the validator's node dials the seed, and patches, issues and the
# delegates' signed refs travel both ways over that connection (tests/integration/kit_radicle.py, scenario O).
# Or, with subnet_id, an existing public subnet shared by several kits in one account (an account has 5 VPCs a region
# by default): the kit then makes no VPC, gateway or route table, only its security group in that subnet's VPC.

data "aws_ec2_instance_type_offerings" "here" {
  location_type = "availability-zone"
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

data "aws_subnet" "shared" {
  count = var.subnet_id != "" ? 1 : 0
  id    = var.subnet_id
}

data "aws_vpc" "shared" {
  count = var.subnet_id != "" ? 1 : 0
  id    = data.aws_subnet.shared[0].vpc_id
}

locals {
  own_network = var.subnet_id == ""
  vpc_id      = local.own_network ? aws_vpc.main[0].id : data.aws_vpc.shared[0].id
  subnet_id   = local.own_network ? aws_subnet.public[0].id : var.subnet_id
  # The VPC's resolver (its base address + 2) is in the VPC's CIDR, which may be wider than the shared subnet's.
  vpc_cidr = local.own_network ? var.vpc_cidr : data.aws_vpc.shared[0].cidr_block
}

# The kit's own network had no count before subnet_id: these keep an existing state's objects where they are.
moved {
  from = aws_vpc.main
  to   = aws_vpc.main[0]
}

moved {
  from = aws_internet_gateway.main
  to   = aws_internet_gateway.main[0]
}

moved {
  from = aws_subnet.public
  to   = aws_subnet.public[0]
}

moved {
  from = aws_route_table.public
  to   = aws_route_table.public[0]
}

moved {
  from = aws_route_table_association.public
  to   = aws_route_table_association.public[0]
}

resource "aws_vpc" "main" {
  count                = local.own_network ? 1 : 0
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "main" {
  count  = local.own_network ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  tags   = { Name = var.name }
}

resource "aws_subnet" "public" {
  count                   = local.own_network ? 1 : 0
  vpc_id                  = aws_vpc.main[0].id
  cidr_block              = var.vpc_cidr
  availability_zone       = sort(data.aws_ec2_instance_type_offerings.here.locations)[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-public" }
}

resource "aws_route_table" "public" {
  count  = local.own_network ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  tags   = { Name = "${var.name}-public" }

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }
}

resource "aws_route_table_association" "public" {
  count          = local.own_network ? 1 : 0
  subnet_id      = aws_subnet.public[0].id
  route_table_id = aws_route_table.public[0].id
}

# Its description is the first apply's ("HTTPS out"): changing it would replace the group under the stopped instance. The
# egress rules below are what it allows: egress_ports (443 and 8776).
resource "aws_security_group" "node" {
  name        = "${var.name}-node"
  description = "proof-of-fix SEV-SNP validator: no inbound, HTTPS out"
  vpc_id      = local.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "node" {
  for_each          = toset([for p in var.egress_ports : tostring(p)])
  security_group_id = aws_security_group.node.id
  description       = "egress tcp ${each.value}"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}

# DNS (the VPC resolver) is UDP/TCP 53 inside the VPC (the kit's own or the shared subnet's); NTP is Amazon's
# link-local service. Neither needs a rule here.
resource "aws_vpc_security_group_egress_rule" "dns" {
  for_each          = toset(["udp", "tcp"])
  security_group_id = aws_security_group.node.id
  description       = "DNS to the VPC resolver (${each.value})"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = local.vpc_cidr
}
