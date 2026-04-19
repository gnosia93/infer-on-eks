# IAM Role for S3 access (IRSA)
resource "aws_iam_role" "s3_access" {
  name = "${var.cluster_name}-s3-access"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      },
      Action = "sts:AssumeRoleWithWebIdentity",
      Condition = {
        StringEquals = {
          "${replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:sub" = "system:serviceaccount:default:s3-access-sa"
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  role       = aws_iam_role.s3_access.name
}


data "aws_caller_identity" "current" {}

locals {
  vectordb_bucket_name = "${var.cluster_name}-vectordb-milvus-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "milvus" {
  bucket = local.vectordb_bucket_name
  force_destroy = true             # terraform destroy 시 버켓에 데이터가 있어도 삭제처리

  tags = {
    Purpose = "Milvus vector storage"
    Cluster = var.cluster_name
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "milvus" {
  bucket = aws_s3_bucket.milvus.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "milvus" {
  bucket = aws_s3_bucket.milvus.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

