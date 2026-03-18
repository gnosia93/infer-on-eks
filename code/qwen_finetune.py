# finetune_qwen.py
# Qwen2.5-7B-Instruct QLoRA 파인튜닝 예제

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

# ============================================================
# 1. 모델 로드 
# ============================================================

# === 양자화 설정 (택 1) ===
# 4bit: ~13 GiB
# bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
# 8bit: ~25 GiB
# bnb_config = BitsAndBytesConfig(load_in_8bit=True)
# BF16: ~50 GiB (양자화 없음, 품질 최고)
model_name = "Qwen/Qwen3.5-27B"

# 4bit 양자화
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

# 8bit 양자화
bnb_config = BitsAndBytesConfig(
    load_in_8bit=True,
)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
#    quantization_config=bnb_config,
    torch_dtype=torch.bfloat16, 
    device_map="auto",
    trust_remote_code=True,
)

tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

# ============================================================
# 2. LoRA 설정
# ============================================================
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ============================================================
# 3. 학습 데이터 (DevOps/ML 도메인 샘플)
# ============================================================
train_data = [
    {"instruction": "GPU OOM이 발생했을 때 해결 방법을 알려줘",
     "output": "GPU OOM 해결 방법: 1) 배치 크기 줄이기 + Gradient Accumulation으로 effective batch size 유지 2) Mixed Precision(BF16) 사용으로 메모리 50% 절감 3) Activation Checkpointing 적용 4) 모델이 단일 GPU에 안 들어가면 ZeRO Stage 3 또는 FSDP 사용"},

    {"instruction": "Kubernetes Pod가 CrashLoopBackOff 상태일 때 디버깅 방법은?",
     "output": "CrashLoopBackOff 디버깅: 1) kubectl logs <pod> --previous로 이전 크래시 로그 확인 2) kubectl describe pod <pod>로 이벤트 확인 3) 리소스 제한(memory limit) 초과 여부 확인 4) liveness/readiness probe 설정 확인 5) 이미지 pull 실패 여부 확인"},

    {"instruction": "Docker 컨테이너에서 GPU를 사용하려면 어떻게 해야 해?",
     "output": "Docker에서 GPU 사용: 1) NVIDIA Container Toolkit 설치 2) docker run --gpus all 옵션 사용 3) nvidia-smi로 GPU 인식 확인 4) CUDA 버전과 PyTorch 호환성 확인"},

    {"instruction": "Prometheus에서 GPU 메트릭을 수집하는 방법은?",
     "output": "DCGM Exporter를 사용합니다. 1) dcgm-exporter 컨테이너 실행 (포트 9400) 2) prometheus.yml에 scrape target 추가 3) DCGM_FI_DEV_GPU_UTIL, DCGM_FI_DEV_FB_USED 등 메트릭 수집 4) Grafana 대시보드로 시각화"},

    {"instruction": "MLflow로 실험 추적하는 기본 코드를 보여줘",
     "output": "import mlflow\nmlflow.set_experiment('my-experiment')\nwith mlflow.start_run():\n    mlflow.log_param('lr', 0.001)\n    mlflow.log_param('batch_size', 32)\n    mlflow.log_metric('loss', 0.5)\n    mlflow.log_metric('accuracy', 0.92)\n    mlflow.pytorch.log_model(model, 'model')"},

    {"instruction": "Terraform으로 AWS VPC를 생성하는 기본 코드는?",
     "output": "resource \"aws_vpc\" \"main\" {\n  cidr_block = \"10.0.0.0/16\"\n  enable_dns_support = true\n  enable_dns_hostnames = true\n  tags = { Name = \"my-vpc\" }\n}\nresource \"aws_subnet\" \"public\" {\n  vpc_id = aws_vpc.main.id\n  cidr_block = \"10.0.1.0/24\"\n  map_public_ip_on_launch = true\n}"},

    {"instruction": "Ray를 사용한 분산 학습 기본 코드를 보여줘",
     "output": "import ray\nfrom ray import train\nfrom ray.train.torch import TorchTrainer\n\ndef train_func():\n    model = ...\n    optimizer = ...\n    for epoch in range(10):\n        loss = train_step(model, optimizer)\n        train.report({'loss': loss})\n\ntrainer = TorchTrainer(train_func, scaling_config=train.ScalingConfig(num_workers=4, use_gpu=True))\nresult = trainer.fit()"},

    {"instruction": "Slurm에서 멀티노드 GPU 학습 작업을 제출하는 sbatch 스크립트를 보여줘",
     "output": "#!/bin/bash\n#SBATCH --job-name=train\n#SBATCH --nodes=4\n#SBATCH --ntasks-per-node=8\n#SBATCH --gpus-per-node=8\n#SBATCH --cpus-per-task=12\n#SBATCH --exclusive\n\nsrun --gpu-bind=closest torchrun --nnodes=$SLURM_NNODES --nproc_per_node=8 --rdzv_backend=c10d --rdzv_endpoint=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n1):29400 train.py"},
]

# Alpaca → Chat 형식 변환
def format_chat(example):
    messages = [
        {"role": "system", "content": "You are a helpful DevOps and ML engineering assistant."},
        {"role": "user", "content": example["instruction"]},
        {"role": "assistant", "content": example["output"]},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False)
    return {"text": text}

dataset = Dataset.from_list(train_data)
dataset = dataset.map(format_chat)

# ============================================================
# 4. 학습
# ============================================================
training_args = TrainingArguments(
    output_dir="./qwen-devops-lora",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    bf16=True,
    logging_steps=1,
    save_strategy="epoch",
    optim="paged_adamw_8bit",
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer,
    dataset_text_field="text",
    max_seq_length=2048,
)

trainer.train()

# ============================================================
# 5. 저장
# ============================================================
model.save_pretrained("./qwen-devops-lora")
tokenizer.save_pretrained("./qwen-devops-lora")
print("Done!")
