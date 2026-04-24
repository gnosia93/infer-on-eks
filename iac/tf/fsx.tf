# ---------------------------------------------------
# Security Group for FSx Lustre
# ---------------------------------------------------
resource "aws_security_group" "fsx_lustre" {
  name        = "fsx-sg"
  description = "FSx Lustre access"
  vpc_id      = var.vpc_id
}

# Lustre 포트 988 (self-referencing)
resource "aws_security_group_rule" "fsx_lustre_988_self" {
  type              = "ingress"
  from_port         = 988
  to_port           = 988
  protocol          = "tcp"
  security_group_id = aws_security_group.fsx_lustre.id
  self              = true
  description       = "Lustre traffic within SG"
}

# Lustre 포트 1018-1023 (self-referencing)
resource "aws_security_group_rule" "fsx_lustre_1018_1023_self" {
  type              = "ingress"
  from_port         = 1018
  to_port           = 1023
  protocol          = "tcp"
  security_group_id = aws_security_group.fsx_lustre.id
  self              = true
  description       = "Lustre traffic within SG"
}

# EKS 노드 SG에서 FSx SG로의 접근 허용
resource "aws_security_group_rule" "eks_to_fsx_988" {
  type                     = "ingress"
  from_port                = 988
  to_port                  = 988
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fsx_lustre.id
  source_security_group_id = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  description              = "EKS nodes to FSx Lustre"
}

resource "aws_security_group_rule" "eks_to_fsx_1018_1023" {
  type                     = "ingress"
  from_port                = 1018
  to_port                  = 1023
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fsx_lustre.id
  source_security_group_id = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  description              = "EKS nodes to FSx Lustre"
}

# FSx가 EKS 노드로 응답 트래픽 (반대 방향)
resource "aws_security_group_rule" "fsx_to_eks_988" {
  type                     = "ingress"
  from_port                = 988
  to_port                  = 988
  protocol                 = "tcp"
  security_group_id        = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  source_security_group_id = aws_security_group.fsx_lustre.id
  description              = "FSx Lustre to EKS nodes"
}

resource "aws_security_group_rule" "fsx_to_eks_1018_1023" {
  type                     = "ingress"
  from_port                = 1018
  to_port                  = 1023
  protocol                 = "tcp"
  security_group_id        = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  source_security_group_id = aws_security_group.fsx_lustre.id
  description              = "FSx Lustre to EKS nodes"
}

# ---------------------------------------------------
# FSx for Lustre File System
# ---------------------------------------------------
resource "aws_fsx_lustre_file_system" "this" {
  storage_capacity                = var.storage_capacity
  subnet_ids                      = [var.subnet_id]
  security_group_ids              = [aws_security_group.fsx_lustre.id]
  deployment_type                 = var.deployment_type
  per_unit_storage_throughput     = var.throughput_per_unit
  file_system_type_version        = var.lustre_version
  data_compression_type           = var.data_compression
  automatic_backup_retention_days = 0
  storage_type                    = "SSD"

  # S3 연동 (선택)
  dynamic "log_configuration" {
    for_each = []  # 필요 시 로깅 설정
    content {
      level = "WARN_ERROR"
    }
  }

  tags = merge(var.tags, {
    Name = var.fsx_name
  })

  lifecycle {
    ignore_changes = [
      # S3 import path는 생성 후 수정 불가
      # 의도적 재생성 방지
    ]
  }
}

# S3 Data Repository Association (선택)
resource "aws_fsx_data_repository_association" "s3_import" {
  count = var.s3_import_path != null ? 1 : 0

  file_system_id       = aws_fsx_lustre_file_system.this.id
  data_repository_path = var.s3_import_path
  file_system_path     = "/s3data"
  batch_import_meta_data_on_create = true

  s3 {
    auto_export_policy {
      events = var.s3_export_path != null ? ["NEW", "CHANGED", "DELETED"] : []
    }
    auto_import_policy {
      events = ["NEW", "CHANGED", "DELETED"]
    }
  }

  tags = var.tags
}
