#!bash

# Config
REGION="${1:-ap-northeast-2}"  # 첫번째 인자로 리전 전달 (기본값: ap-northeast-2)
echo -e "\n1. [SSM Query] Latest Official DLAMIs:"

# 1-1. PyTorch + NVIDIA Driver (Ubuntu 22.04)
PYTORCH_AMI=$(aws ssm get-parameter \
    --region "${REGION}" \
    --name "/aws/service/deeplearning/ami/x86_64/oss-nvidia-driver-gpu-pytorch-2.5-ubuntu-22.04/latest/ami-id" \
    --query "Parameter.Value" \
    --output text 2>/dev/null)
# 1-2. Deep Learning Base AMI (순수 CUDA/Driver만 설치된 기본 Ubuntu 22.04)
BASE_AMI=$(aws ssm get-parameter \
    --region "${REGION}" \
    --name "/aws/service/deeplearning/ami/x86_64/base-gpu-ubuntu-22.04/latest/ami-id" \
    --query "Parameter.Value" \
    --output text 2>/dev/null)

printf " - PyTorch 2.5 (Ubuntu 22.04) : %s\n" "${PYTORCH_AMI:-Not Found}"
printf " - Base GPU (CUDA/Driver Only): %s\n" "${BASE_AMI:-Not Found}"

# dry-run 실행에 필요한 최소 임시 값들 (실제 생성되지 않음)
# 만약 지정한 AMI가 해당 리전에 없으면 AMI 에러가 날 수 있으므로 기본 Amazon Linux 2023 AMI 권장
DUMMY_AMI="${PYTORCH_AMI}"

# 1. G 계열 인스턴스 목록 가져오기 (중복 제거 및 정렬)
INSTANCE_TYPES=$(aws ec2 describe-instance-type-offerings \
    --filters Name=instance-type,Values="g*" \
    --query "InstanceTypeOfferings[].InstanceType" \
    --output text \
    --region "${REGION}" | tr '\t' '\n' | sort -u)

if [ -z "$INSTANCE_TYPES" ]; then
    echo "No G-series instance types found or AWS CLI error."
    exit 1
fi

#echo -e "Found Instance Types:\n$INSTANCE_TYPES\n"
echo "=========================================================="
echo " Checking availability via --dry-run..."
echo "=========================================================="

printf "%-20s | %-12s | %-50s\n" "INSTANCE TYPE" "STATUS" "DETAILS / REASON"
printf "%s\n" "----------------------------------------------------------------------------------------"

# 기본 VPC와 상관없이, 현재 리전에 존재하는 '아무 사용 가능한 서브넷' 1개 자동 선택
SUBNET_ID=$(aws ec2 describe-subnets \
    --region ap-northeast-2 \
    --query "Subnets[0].SubnetId" \
    --output text)

# 2. 각 인스턴스 타입별로 dry-run 테스트 실행
for ITYPE in $INSTANCE_TYPES; do
    # dry-run 실행 및 에러 메시지 캡처
    ERROR_OUTPUT=$(aws ec2 run-instances \
        --image-id "${DUMMY_AMI}" \
        --instance-type "${ITYPE}" \
        --subnet-id "${SUBNET_ID}" \
        --dry-run \
        --region "${REGION}" 2>&1)

    EXIT_CODE=$?

    # AWS DryRun 성공 에러코드(DryRunOperation) 체크
    if echo "${ERROR_OUTPUT}" | grep -q "DryRunOperation"; then
        STATUS="✅ AVAILABLE"
        DETAILS="Ready to launch"
    elif echo "${ERROR_OUTPUT}" | grep -q "InsufficientInstanceCapacity"; then
        STATUS="❌ NO CAPACITY"
        DETAILS="AWS Capacity Exceeded (No Stock)"
    elif echo "${ERROR_OUTPUT}" | grep -q "VcpuLimitExceeded"; then
        STATUS="⚠️ QUOTA LIMIT"
        DETAILS="Account vCPU Limit Exceeded"
    elif echo "${ERROR_OUTPUT}" | grep -q "InvalidAMIID"; then
        STATUS="⚠️ INVALID AMI"
        DETAILS="Check DUMMY_AMI ID for region ${REGION}"
    else
        STATUS="❌ FAILED"
        # 에러 메시지의 첫 줄만 간략히 요약 출력
        DETAILS=$(echo "${ERROR_OUTPUT}" | head -n 1 | cut -c 1-50)
    fi

    printf "%-20s | %-12s | %-50s\n" "${ITYPE}" "${STATUS}" "${DETAILS}"
done

echo "=========================================================="
