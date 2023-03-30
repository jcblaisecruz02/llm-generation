# LLM Generation
Based on [alpaca-lora](https://github.com/tloen/alpaca-lora), modified to work with LLMs in general. This would open a small local web app for inference in your browser.

## LLaMA and Alpaca Generation
Please use the HuggingFace-based checkpoints instead of the original ones.

```
python generate.py \
    --base_model decapoda-research/llama-7b-hf \
    --model_type causal
```

You can add adapter weights for `Alpaca-LoRA` and specify `--use_instruction` for instruction-based prompting. The script should add the scaffolding prompts for Alpaca automatically.

```
python generate.py \
    --base_model decapoda-research/llama-7b-hf \
    --lora_weights tloen/alpaca-lora-7b \
    --model_type causal \
    --use_instruction 
```

## Seq2Seq Generation
The `generate.py` script works for any LLM. Here's an example for `MT0-xl`:

```
python generate.py \
    --base_model bigscience/mt0-xl \
    --model_type seq2seq
```
