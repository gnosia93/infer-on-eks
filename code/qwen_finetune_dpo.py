# qwen_finetune_dpo.py
# Qwen3.5-27B DPO (Direct Preference Optimization) 파인튜닝 예제

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model
from trl import DPOTrainer, DPOConfig

# ============================================================
# 1. 모델 로드
# ============================================================
model_name = "Qwen/Qwen3.5-27B"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
#    quantization_config=bnb_config,
    torch_dtype=torch.bfloat16,
    device_map={"": 0},
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
    target_modules=[
        "q_proj", "v_proj", "k_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()


# ============================================================
# 3. DPO 학습 데이터 (chosen vs rejected 쌍)
# ============================================================
dpo_data = [
    {
        "prompt": "GPU OOM이 발생했을 때 해결 방법을 알려줘",
        "chosen": "GPU OOM 해결 방법: 1) 배치 크기 줄이기 + Gradient Accumulation 2) Mixed Precision(BF16) 사용 3) Activation Checkpointing 적용 4) ZeRO Stage 3 또는 FSDP 사용",
        "rejected": "GPU를 더 사세요. 메모리가 부족하면 더 큰 GPU를 쓰면 됩니다."
    },
    {
        "prompt": "Kubernetes Pod가 CrashLoopBackOff 상태일 때 디버깅 방법은?",
        "chosen": "kubectl logs <pod> --previous로 이전 크래시 로그 확인, kubectl describe pod로 이벤트 확인, 리소스 제한 초과 여부 확인, probe 설정 확인",
        "rejected": "Pod를 삭제하고 다시 만드세요."
    },
    {
        "prompt": "Docker 컨테이너에서 GPU를 사용하려면 어떻게 해야 해?",
        "chosen": "Docker에서 GPU 사용: 1) NVIDIA Container Toolkit 설치 2) docker run --gpus all 옵션 사용 3) nvidia-smi로 GPU 인식 확인 4) CUDA 버전과 PyTorch 호환성 확인",
        "rejected": "Docker는 GPU를 지원하지 않습니다. 호스트에서 직접 실행하세요."
    },
    {
        "prompt": "Prometheus에서 GPU 메트릭을 수집하는 방법은?",
        "chosen": "DCGM Exporter를 사용합니다. 1) dcgm-exporter 컨테이너 실행 (포트 9400) 2) prometheus.yml에 scrape target 추가 3) DCGM_FI_DEV_GPU_UTIL, DCGM_FI_DEV_FB_USED 등 메트릭 수집 4) Grafana 대시보드로 시각화",
        "rejected": "nvidia-smi를 cron으로 돌려서 파일에 저장하세요."
    },
]

# Chat 형식 변환
def format_dpo(example):
    system = "You are a helpful DevOps and ML engineering assistant."
    prompt_msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": example["prompt"]},
    ]
    return {
        "prompt": tokenizer.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True),
        "chosen": example["chosen"],
        "rejected": example["rejected"],
    }

dataset = Dataset.from_list(dpo_data)
dataset = dataset.map(format_dpo)

# ============================================================
# 4. DPO 학습
# ============================================================
training_args = DPOConfig(
    output_dir="./qwen-devops-dpo",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=5e-5,
    bf16=True,
    logging_steps=1,
    save_strategy="epoch",
    optim="adamw_torch",
    beta=0.1,
    max_length=2048,
    max_prompt_length=512,
)

trainer = DPOTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    processing_class=tokenizer,
)

trainer.train()

# ============================================================
# 5. 저장
# ============================================================
model.save_pretrained("./qwen-devops-dpo")
tokenizer.save_pretrained("./qwen-devops-dpo")
print("Done!")
