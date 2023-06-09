import sys

import fire
import torch
from peft import PeftModel
import transformers
import gradio as gr

assert (
    "LlamaTokenizer" in transformers._import_structure["models.llama"]
), "LLaMA is now in HuggingFace's main branch.\nPlease reinstall it: pip uninstall transformers && pip install git+https://github.com/huggingface/transformers.git"
from transformers import LlamaTokenizer, LlamaForCausalLM
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForCausalLM, GenerationConfig

if torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"

try:
    if torch.backends.mps.is_available():
        device = "mps"
except:
    pass


def main(
    load_8bit: bool = False,
    base_model: str = "decapoda-research/llama-7b-hf",
    lora_weights: str = "",
    model_type: str = "causal",
    use_instruction: bool = False
):
    assert base_model, (
        "Please specify a --base_model, e.g. --base_model='decapoda-research/llama-7b-hf'"
    )
    
    # Check if the model is something else
    if model_type == "causal": 
        TokenizerClass = AutoTokenizer
        ModelClass = AutoModelForCausalLM
    elif model_type == 'seq2seq':
        TokenizerClass = AutoTokenizer
        ModelClass = AutoModelForSeq2SeqLM

    # Load Tokenizer
    tokenizer = TokenizerClass.from_pretrained(base_model)
    
    if device == "cuda":
        # Adjust max_memory depending on number of GPUs if loading 8 bit
        if load_8bit:
            model = ModelClass.from_pretrained(
                base_model,
                load_in_8bit=load_8bit,
                torch_dtype=torch.float16,
                device_map="auto",
                max_memory={i: "14GiB" if i == 0 else "20GiB" for i in range(torch.cuda.device_count())}
            )
        else:
            model = ModelClass.from_pretrained(
                base_model,
                load_in_8bit=load_8bit,
                torch_dtype=torch.float16,
                device_map="auto",
            )
        
        model_type = type(model)
        if lora_weights != '':
            # Map the adapters to GPU as needed if loading 8 bit
            if load_8bit:
                device_map = {f"base_model.model.{k}": v for k, v in model.hf_device_map.items()}
                model = PeftModel.from_pretrained(
                    model,
                    lora_weights,
                    torch_dtype=torch.float16,
                    device_map=device_map
                )
            else:
                model = PeftModel.from_pretrained(
                    model,
                    lora_weights,
                    torch_dtype=torch.float16,
                )
    
    elif device == "mps":
        model = ModelClass.from_pretrained(
            base_model,
            device_map={"": device},
            torch_dtype=torch.float16,
        )
        model_type = type(model)
        if lora_weights != '':
            model = PeftModel.from_pretrained(
                model,
                lora_weights,
                device_map={"": device},
                torch_dtype=torch.float16,
            )
    
    else:
        model = ModelClass.from_pretrained(
            base_model, device_map={"": device}, low_cpu_mem_usage=True
        )
        model_type = type(model)
        if lora_weights != '':
            model = PeftModel.from_pretrained(
                model,
                lora_weights,
                device_map={"": device},
            )

    # unwind broken decapoda-research config
    if model_type is LlamaForCausalLM:
        model.config.pad_token_id = tokenizer.pad_token_id = 0  # unk
        model.config.bos_token_id = 1
        model.config.eos_token_id = 2

    if not load_8bit:
        model.half()  # seems to fix bugs for some users.

    model.eval()
    if torch.__version__ >= "2" and sys.platform != "win32":
        model = torch.compile(model)

    def evaluate(
        instruction,
        input=None,
        temperature=0.1,
        top_p=0.75,
        top_k=40,
        num_beams=4,
        max_new_tokens=128,
        **kwargs,
    ):
        prompt = generate_prompt(instruction, input=input, use_instruction=use_instruction)
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"].to(device)
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            num_beams=num_beams,
            **kwargs,
        )
        with torch.no_grad():
            generation_output = model.generate(
                input_ids=input_ids,
                generation_config=generation_config,
                return_dict_in_generate=True,
                output_scores=True,
                max_new_tokens=max_new_tokens,
            )
        s = generation_output.sequences[0]
        output = tokenizer.decode(s)
        output = post_process(output, prompt=prompt)
        
        return output
    
    desc = [
        "**Model:** {}".format(base_model.split('/')[-1])
    ]
    
    if lora_weights != '': desc.append("**Adapter**: {}".format(lora_weights.split('/')[-1]))
    if use_instruction: desc.append("**Instruct Model?**: Yes") 
    else: desc.append("**Instruct Model?**: No")
    if load_8bit: desc.append("**Inference Mode**: 8-bit Int")
    else: desc.append("**Inference Mode**: 16-bit Float")
    
    gr.Interface(
        fn=evaluate,
        inputs=[
            gr.components.Textbox(
                lines=2, label="Input", placeholder="Prompt for all models go here."
            ),
            gr.components.Textbox(lines=2, label="Context", placeholder="Input for Instruction Models go here."),
            gr.components.Slider(minimum=0, maximum=1, value=0.7, label="Temperature"),
            gr.components.Slider(minimum=0, maximum=1, value=0.93, label="Top p"),
            gr.components.Slider(
                minimum=0, maximum=100, step=1, value=50, label="Top k"
            ),
            gr.components.Slider(minimum=1, maximum=5, step=1, value=5, label="Beams"),
            gr.components.Slider(
                minimum=1, maximum=2000, step=1, value=128, label="Max tokens"
            ),
        ],
        outputs=[
            gr.inputs.Textbox(
                lines=5,
                label="Output",
            )
        ],
        title="LLM Generation",
        description='\n'.join(desc),
    ).launch()

def generate_prompt(instruction, input=None, use_instruction=False):
    if use_instruction and input is not None:
        return f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

        ### Instruction:
        {instruction}

        ### Input:
        {input}

        ### Response:
        """
    elif use_instruction and input is None:
        return f"""Below is an instruction that describes a task. Write a response that appropriately completes the request.

        ### Instruction:
        {instruction}

        ### Response:
        """
    else:
        return instruction
    
def post_process(output, prompt=""):
    # For instruct models
    if ("### Response:") in output:
        output = output.split("### Response:")[1]
    
    # For LMs that succeed the prompt
    if prompt in output:
        output =  output.replace(prompt, "")
    
    # For models that start with <pad>
    if output.startswith("<pad>"):
        output =  output.replace("<pad>",  "")
        
    # Additionally remove the end of sequence token if present then strip
    output = output.replace("</s>", "").strip()
    
    return output


if __name__ == "__main__":
    fire.Fire(main)
