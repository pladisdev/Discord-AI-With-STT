from ctransformers import AutoModelForCausalLM
import torch

class LLM:
    def __init__(self):
        
        self.model = AutoModelForCausalLM.from_pretrained("TheBloke/Guanaco-3B-Uncensored-v2-GGML", model_file="guanaco-3b-uncensored-v2.ggmlv1.q4_0.bin") 

        self.chat_history = []

    def chat(self, user, text):
        chat_message = f'### {user}: {text}\n### Assistant: '

        if len(self.chat_history) > 5:
            self.chat_history.pop(0)

        prompt = "\n".join(self.chat_history)

        result = self.model(prompt).split("###")[0]

        print(result)

        self.chat_history.append(chat_message + result)

        return result