# ============================================
# Milvus IRSA
# ============================================
resource "aws_iam_role" "milvus" {
  name = "${var.cluster_name}-milvus"

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
          "${replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:sub" = "system:serviceaccount:milvus:milvus-sa",
          "${replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_policy" "milvus_s3" {
  name = "${var.cluster_name}-milvus-s3"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
      ],
      Resource = [
        "arn:aws:s3:::${var.vectordb_bucket_name}",
        "arn:aws:s3:::${var.vectordb_bucket_name}/*",
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "milvus_s3" {
  role       = aws_iam_role.milvus.name
  policy_arn = aws_iam_policy.milvus_s3.arn
}

output "milvus_role_arn" {
  value = aws_iam_role.milvus.arn
}
