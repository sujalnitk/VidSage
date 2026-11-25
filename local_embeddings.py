"""Pinned MiniLM inference using the lightweight ONNX CPU runtime."""
import numpy as np


class MiniLM:
    max_seq_length = 256

    def __init__(self, revision):
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        import onnxruntime as ort

        repo = "sentence-transformers/all-MiniLM-L6-v2"
        tokenizer_path = hf_hub_download(repo, "tokenizer.json", revision=revision, token=False)
        weights = hf_hub_download(repo, "onnx/model.onnx", revision=revision, token=False)
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(weights, options, providers=["CPUExecutionProvider"])

    def tokenizer(self, texts, add_special_tokens=True, **kwargs):
        single = isinstance(texts, str)
        encoded = self._tokenizer.encode_batch([texts] if single else texts, add_special_tokens=add_special_tokens)
        ids = [e.ids for e in encoded]
        offsets = [e.offsets for e in encoded]
        return {"input_ids": ids[0] if single else ids, "offset_mapping": offsets[0] if single else offsets}

    def encode(self, texts):
        vectors = []
        for start in range(0, len(texts), 32):
            encoded = self._tokenizer.encode_batch(texts[start:start + 32])
            if any(len(e.ids) > self.max_seq_length for e in encoded):
                raise ValueError("MiniLM input exceeds 256 tokens.")
            width = max(len(e.ids) for e in encoded)
            ids = np.array([e.ids + [0] * (width - len(e.ids)) for e in encoded], dtype=np.int64)
            mask = np.array([[1] * len(e.ids) + [0] * (width - len(e.ids)) for e in encoded], dtype=np.int64)
            inputs = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            hidden = self.session.run(None, {i.name: inputs[i.name] for i in self.session.get_inputs()})[0]
            weights = mask[:, :, None].astype(np.float32)
            pooled = (hidden * weights).sum(axis=1) / weights.sum(axis=1)
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            vectors.extend(pooled.astype(np.float32))
        return np.asarray(vectors, dtype=np.float32)
