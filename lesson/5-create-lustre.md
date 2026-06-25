## 러스터(Lustre) ##
러스터(Lustre) 파일 시스템은 높은 처리량, 낮은 지연 시간, 뛰어난 확장성을 제공하는 병렬 분산 파일 시스템으로, 대규모 데이터셋을 처리해야 하는 AI 시스템에 필수적이다.
AWS 에서 Lustre 파일 시스템을 사용하는 가장 빠른 방법은 완전 관리형 서비스인 Amazon FSx for Lustre 와 FSx for Lustre CSI(Container Storage Interface) 드라이버를 활용하여 쿠버네티스 클러스터에 통합하는 것이다.

```
export CLUSTER_NAME="training-on-eks"
export AWS_REGION=$(aws ec2 describe-availability-zones --query "AvailabilityZones[0].RegionName" --output text)
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export VPC_ID=$(aws eks describe-cluster --name $CLUSTER_NAME --query "cluster.resourcesVpcConfig.vpcId" --output text)
export FSX_ROLE="FSxLustreRole"
export FSX_S3Policy="FSxLustreS3Policy"
export S3_BUCKET="training-on-eks-lustre-${ACCOUNT_ID}"
```

### 1. lustre 파일시스템 조회 ###

테라폼으로 이미 생성된 러스터 파일 시스템을 조회한다.  
```
aws fsx describe-file-systems \
    --query "FileSystems[?Tags[?Key=='Name' && Value=='trainng-on-eks']].\
             {ID:FileSystemId, MountName:LustreConfiguration.MountName, DNS:DNSName, Status:Lifecycle}" \
    --output table
```
[결과]
```
-------------------------------------------------------------------------------------------------------------
|                                            DescribeFileSystems                                            |
+--------------------------------------------------------+-----------------------+------------+-------------+
|                           DNS                          |          ID           | MountName  |   Status    |
+--------------------------------------------------------+-----------------------+------------+-------------+
|  fs-0261bb15621d24e21.fsx.ap-northeast-1.amazonaws.com |  fs-0261bb15621d24e21 |  rycutbev  |  AVAILABLE  |
+--------------------------------------------------------+-----------------------+------------+-------------+
```

아래의 스크립트는 러스터 파일 시스템 상세 정보를 출력해 준다.
```
aws fsx describe-file-systems --query "FileSystems[?FileSystemType=='LUSTRE']" --output json | jq -r '
  ["ID", "Status", "Storage_GiB", "Unit_MB/s", "Total_MB/s", "MountName", "Type"],
  (.[] | 
    (.LustreConfiguration.PerUnitStorageThroughput // 0 | tonumber) as $unit |
    [
      .FileSystemId, 
      .Lifecycle, 
      .StorageCapacity, 
      (if $unit == 0 then "Default" else $unit end), 
      (if $unit == 0 then "Variable" else (($unit * .StorageCapacity / 1024) | floor) end), 
      .LustreConfiguration.MountName, 
      .LustreConfiguration.DeploymentType
    ]
  ) | @tsv' | column -t -s $'\t'
```
[결과]
```
ID                    Status     Storage_GiB  Unit_MB/s  Total_MB/s  MountName  Type
fs-0261bb15621d24e21  AVAILABLE  1200         Default    Variable    rycutbev   SCRATCH_2
```
워크샵에서 생성된 러스터 파일 시스템은 SCRATCH_2 로 EFA 를 지원하지 않는다. 실제 분산훈련 환경에서는 배포 유형 (Deployment Type)을 반드시 PERSISTENT_2를 선택해야 한다.
다음은 러스터에서 EFA 인터페이스와 연관된 설정들 이다.
   
* deployment_type: 반드시 PERSISTENT_2
* storage_capacity: 최소 1.2 TiB(1200 GiB) 이상이어야 하며, 1.2의 배수 단위로 설정
* throughput_capacity: 최소 125 MB/s/TiB 이상 권장.

### 2. IAM 역할(IRSA) 생성 ###
fsx 용 서비스 어카운트를 생성한다.  
```
kubectl create namespace fsx-csi-driver

eksctl create iamserviceaccount \
    --name fsx-csi-sa \
    --namespace fsx-csi-driver \
    --cluster ${CLUSTER_NAME} \
    --role-name "${FSX_ROLE}" \
    --attach-policy-arn arn:aws:iam::aws:policy/AmazonFSxFullAccess \
    --approve \
    --override-existing-serviceaccounts
```

FSxLustreRole 에 S3 접근 권한을 부여한다. 
```
cat <<EOF > s3-policy.json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "s3:GetBucketLocation",
            "s3:ListBucket",
            "s3:GetBucketAcl",
            "s3:GetObject",
            "s3:GetObjectTagging",
            "s3:PutObject",
            "s3:DeleteObject"
        ],
        "Resource": ["arn:aws:s3:::${BUCKET_NAME}","arn:aws:s3:::${BUCKET_NAME}/*"]
    }]
}
EOF

S3_POLICY_ARN=$(aws iam create-policy --policy-name ${FSX_S3Policy} --policy-document file://s3-policy.json --query Policy.Arn --output text)
aws iam attach-role-policy --role-name ${FSX_ROLE} --policy-arn $S3_POLICY_ARN
```

### 3. Amazon FSx CSI (Container Storage Interface) 드라이버 설치 ### 
Helm을 사용하여 EKS 클러스터에 FSx for Lustre CSI 드라이버를 배포한다. 
```
helm repo add aws-fsx-csi-driver https://kubernetes-sigs.github.io/aws-fsx-csi-driver
helm repo update

helm install fsx-csi-driver aws-fsx-csi-driver/aws-fsx-csi-driver \
    --namespace fsx-csi-driver \
    --set image.repository=602401143452.dkr.ecr.${AWS_REGION}.amazonaws.com/eks/aws-fsx-csi-driver \
    --set controller.serviceAccount.create=false \
    --set controller.serviceAccount.name=fsx-csi-sa \
    --set controller.serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=arn:aws:iam::${ACCOUNT_ID}:role/FSxLustreRole
```

fsx 관련 컨트롤러와 Pod 를 조회한다. fsx-csi-controller 는 파일 시스템의 생성, 삭제, 볼륨 연결 등을 담당하는 컨트롤러이다. 
fsx-csi-node 는 실제 워커 노드마다 하나씩 실행되는 데몬셋으로, EC2 노드 위에서 Lustre 파일 시스템을 실제로 마운트(Mount)하는 역할을 수행한다.
```
kubectl get pods -n fsx-csi-driver
```
[결과]
```
NAME                                 READY   STATUS    RESTARTS   AGE
fsx-csi-controller-9fb564f88-44n89   4/4     Running   0          5m35s
fsx-csi-controller-9fb564f88-tvk5q   4/4     Running   0          5m35s
fsx-csi-node-6r59f                   3/3     Running   0          5m35s
fsx-csi-node-s79mz                   3/3     Running   0          5m35s
fsx-csi-node-st5fc                   3/3     Running   0          5m35s
fsx-csi-node-wj7lj                   3/3     Running   0          5m35s
```

만약 러스터 관련 오류가 발생하는 경우 아래의 명령어로 fsx-csi-node 로그를 조회하면 그 원인을 쉽게 파악할 수 있다.
```
kubectl logs -f -l app=fsx-csi-node -n fsx-csi-driver -c fsx-plugin
```


## EKS 연결하기 ##
### 1. PV/PVC 배포 ###
```
export FSx_ID=$(aws fsx describe-file-systems \
    --query "FileSystems[?Tags[?Key=='Name' && Value=='trainng-on-eks']].FileSystemId" --output text)
export FSx_DNS=$(aws fsx describe-file-systems \
    --query "FileSystems[?Tags[?Key=='Name' && Value=='trainng-on-eks']].DNSName" --output text)
export FSx_MOUNTNAME=$(aws fsx describe-file-systems \
    --query "FileSystems[?Tags[?Key=='Name' && Value=='trainng-on-eks']].LustreConfiguration.MountName" --output text)

echo ${FSx_ID} ${FSx_DNS} ${FSx_MOUNTNAME}
```

```
cat << EOF > fsx-pvc.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fsx-sc
provisioner: fsx.csi.aws.com
reclaimPolicy: Retain                     # PVC 삭제되어도 유지 (Retain 으로 설정)
volumeBindingMode: Immediate
---
apiVersion: v1
kind: PersistentVolume                    # 이미 생성한 러스터 클러스터를 연결하기 위한 정적 프로비저닝. vs. 동적 프로비저닝의 경우 PV 대신 SC 에 러스터 정보 선언
metadata:
  name: fsx-pv
spec:
  capacity:
    storage: 1200Gi                       # FSx 생성 용량과 일치시킴 - 운영용은 38400
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain   # PVC 삭제되어도 유지 (Retain 으로 설정)
  storageClassName: fsx-sc
  csi:
    driver: fsx.csi.aws.com
    volumeHandle: ${FSx_ID}
    volumeAttributes:
      dnsname: ${FSx_DNS}
      mountname: ${FSx_MOUNTNAME}
  mountOptions:
    - flock        # 파일 잠금 기능 활성화 (학습 시 필요)
    - lazystatfs   # 성능 최적화
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fsx-pvc
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: fsx-sc
  resources:
    requests:
      storage: 1200Gi                      # FSx 생성 용량과 일치시킴 - 운영용은 38400  
  volumeName: fsx-pv 
EOF

kubectl apply -f fsx-pvc.yaml
```

### 2. Pod 마운트 테스트 ###
```
cat <<EOF | kubectl apply -f - 
apiVersion: v1
kind: Pod
metadata:
  name: pod-fsx
spec:
  containers:
  - name: app
    image: public.ecr.aws/amazonlinux/amazonlinux:2023
    command: ["sleep", "infinity"]
    volumeMounts:
    - name: fsx
      mountPath: /data/fsx
  volumes:
    - name: fsx
      persistentVolumeClaim:
        claimName: fsx-pvc # 위에서 생성한 PVC 이름
EOF
```

S3 에 파일을 업로드 하고 Pod 에서 조회되는지 확인한다.  
```
echo "Hello FSx Lustre" > test-file.txt
aws s3 cp test-file.txt s3://${S3_BUCKET}/
kubectl exec -it pod-fsx -- bash -c "cd /data/fsx && ls -l"
```

### S3 연동 ###



* https://aws.amazon.com/ko/blogs/tech/lustre/

