#!/bin/bash
huggingface-cli login --token <YOUR_HF_TOKEN>
python3 -m vllm.entrypoints.openai.api_server --model NousResearch/Meta-Llama-3-8B-Instruct --host 0.0.0.0 --port 8000 --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.85
