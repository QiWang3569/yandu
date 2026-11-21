"""Export the pinned M3E-small encoder, mean pooling and unit normalization."""
import argparse
import shutil
from pathlib import Path

import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoModel


class Encoder(torch.nn.Module):
    def __init__(self, path):
        super().__init__()
        self.bert = AutoModel.from_pretrained(path, local_files_only=True, attn_implementation='eager')

    def forward(self, input_ids, attention_mask):
        hidden = self.bert(input_ids=input_ids, attention_mask=attention_mask)[0]
        weights = attention_mask.unsqueeze(-1).to(hidden.dtype)
        pooled = (hidden * weights).sum(1) / weights.sum(1).clamp_min(1)
        return torch.nn.functional.normalize(pooled, dim=1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    model = Encoder(args.model).eval()
    ids = torch.tensor([[101, 800, 102], [101, 102, 0]])
    axes = {key: {0: 'batch', 1: 'length'} for key in ['input_ids', 'attention_mask']}
    axes['embedding'] = {0: 'batch'}
    fp = args.output / 'float.onnx'
    torch.onnx.export(model, (ids, (ids != 0).long()), str(fp), input_names=['input_ids','attention_mask'],
                      output_names=['embedding'], dynamic_axes=axes, opset_version=17, dynamo=False)
    quantize_dynamic(str(fp), str(args.output / 'model.onnx'), weight_type=QuantType.QInt8)
    shutil.copyfile(args.model / 'tokenizer.json', args.output / 'tokenizer.json')
