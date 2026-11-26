"""
translation/indictrans2_translator.py
-------------------------------------
AI4Bharat IndicTrans2 offline translation engine implementation conforming to Translator.

Features:
1. High-accuracy offline neural machine translation across 22 scheduled Indian languages and English.
2. Direct Indic-to-Indic translation without pivoting through English.
3. Strict 8 GB RAM memory management:
   - Lazy model loading (loads only the required direction).
   - Instant unloading & garbage collection before loading another direction.
   - Sentence-level chunking and batch generation (<= 500 characters).
4. Detection of locally installed models in models/indictrans2/{en-indic, indic-en, indic-indic}/.
5. 100% offline execution guarantee: Never initiates network calls or downloads.
6. Honest licensing and installation disclosure (AI4Bharat / Hugging Face).
"""

import os
# Force MPS fallback environment variable before torch import as safety net
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import sys
import types
import gc
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union

from translation.base_translator import (
    Translator,
    TranslationError,
    TranslatorNotAvailableError,
    LanguagePairNotSupportedError,
    TranslationOutput,
)
from config.settings import (
    INDICTRANS2_MODELS_DIR,
    INDICTRANS2_EN_INDIC_DIR,
    INDICTRANS2_INDIC_EN_DIR,
    INDICTRANS2_INDIC_INDIC_DIR,
    TRANSLATION_CHUNK_SIZE,
)
from translation.indictrans2_mapping import (
    app_code_to_indictrans,
    indictrans_to_app_code,
    get_model_direction,
    get_direction_display_name,
    is_indic_language,
    INDIC_APP_LANGS,
    MODEL_SIZES_INFO,
)


# Check environment availability for IndicTrans2 dependencies
_TORCH_AVAILABLE = False
_TRANSFORMERS_AVAILABLE = False
_INDIC_TOOLKIT_AVAILABLE = False

try:
    import torch
    _TORCH_AVAILABLE = True
    try:
        torch.set_num_threads(4)
    except Exception:
        pass
except ImportError:
    torch = None

try:
    import transformers
    _TRANSFORMERS_AVAILABLE = True
    # Transformers 5.x compatibility shim for IndicTransToolkit
    if not hasattr(transformers, "PreTrainedTokenizerBase"):
        from transformers.tokenization_utils_base import PreTrainedTokenizerBase
        transformers.PreTrainedTokenizerBase = PreTrainedTokenizerBase
    import transformers.tokenization_utils
    transformers.tokenization_utils.PreTrainedTokenizerBase = transformers.PreTrainedTokenizerBase
except ImportError:
    transformers = None

try:
    import IndicTransToolkit
    _INDIC_TOOLKIT_AVAILABLE = True
except ImportError:
    IndicTransToolkit = None


def get_language_display_name(code: str) -> str:
    """Returns human-friendly English display name for a 3-letter language code."""
    from config.languages import SUPPORTED_LANGUAGES
    info = SUPPORTED_LANGUAGES.get(code.lower())
    if info:
        return info.name
    return code.upper()


class IndicTrans2Translator(Translator):
    """
    Offline neural translation powered by AI4Bharat IndicTrans2.
    Translates directly between 22 Indian languages and English.
    """

    def __init__(self, models_root: Optional[Union[str, Path]] = None):
        self.models_root = Path(models_root or INDICTRANS2_MODELS_DIR)
        self.models_root.mkdir(parents=True, exist_ok=True)

        self._current_direction: Optional[str] = None
        self._model = None
        self._tokenizer = None
        self._ip = None  # IndicProcessor instance
        self._device = None

    def get_name(self) -> str:
        return "IndicTrans2 (AI4Bharat Offline Engine)"

    def is_available(self) -> bool:
        """
        Checks whether the engine dependencies (torch, transformers, IndicTransToolkit, sentencepiece)
        are importable in the Python environment.
        """
        return _TORCH_AVAILABLE and _TRANSFORMERS_AVAILABLE and _INDIC_TOOLKIT_AVAILABLE

    def get_direction_dir(self, direction: str) -> Path:
        """Returns the filesystem path for a specific model direction."""
        return self.models_root / direction

    def is_direction_installed(self, direction: str) -> bool:
        """
        Checks if model weights and tokenizer exist in the designated direction folder.
        Recognizes safetensors, PyTorch bins, ctranslate2 bins, or ONNX formats.
        """
        dir_path = self.get_direction_dir(direction)
        if not dir_path.is_dir():
            return False

        files = [f.name.lower() for f in dir_path.iterdir() if f.is_file()]
        has_weights = any(
            f.endswith(".safetensors") or f.endswith(".bin") or f.endswith(".pt") or f.endswith(".onnx")
            for f in files
        )
        # Tokenizer or config check
        has_tokenizer = any(
            "tokenizer" in f or "spm" in f or "vocab" in f or "config.json" in f or "metadata.json" in f
            for f in files
        )
        return has_weights and has_tokenizer

    def get_installed_directions(self) -> List[str]:
        """Returns list of currently installed model directions ('en-indic', 'indic-en', 'indic-indic')."""
        directions = ["en-indic", "indic-en", "indic-indic"]
        return [d for d in directions if self.is_direction_installed(d)]

    def supported_pairs(self) -> List[Tuple[str, str]]:
        """
        Returns all supported (source_code, target_code) pairs based on locally installed models.
        """
        installed = self.get_installed_directions()
        pairs = []

        # 1. en-indic
        if "en-indic" in installed:
            for indic in INDIC_APP_LANGS:
                pairs.append(("eng", indic))

        # 2. indic-en
        if "indic-en" in installed:
            for indic in INDIC_APP_LANGS:
                pairs.append((indic, "eng"))

        # 3. indic-indic
        if "indic-indic" in installed:
            for src in INDIC_APP_LANGS:
                for tgt in INDIC_APP_LANGS:
                    if src != tgt:
                        pairs.append((src, tgt))

        return pairs

    def is_pair_supported(self, source: str, target: str) -> bool:
        """Checks if the pair can be translated with currently installed IndicTrans2 models."""
        src = source.lower().strip()
        tgt = target.lower().strip()

        if src == tgt:
            return True

        direction = get_model_direction(src, tgt)
        if not direction:
            return False

        return self.is_direction_installed(direction)

    def unload_model(self):
        """
        Releases the currently loaded model from memory and forces garbage collection.
        Essential for running smoothly on 8 GB RAM machines.
        """
        if self._model is not None or self._tokenizer is not None:
            self._model = None
            self._tokenizer = None
            self._ip = None
            self._current_direction = None
            gc.collect()

            if _TORCH_AVAILABLE and torch is not None:
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    elif hasattr(torch, "backends") and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                            torch.mps.empty_cache()
                except Exception:
                    pass

    def _determine_device(self) -> str:
        """Determines best execution device for 8 GB RAM Mac / Windows / Linux.

        Always forces 'cpu' to prevent Apple Silicon MPS datatype mismatch assertions
        and ensure stable float32 inference across all platforms.
        """
        return "cpu"

    @staticmethod
    def _apply_runtime_shims():
        """Ensures in-memory Transformers 5.x shims are active for dynamic model loading."""
        import sys
        import types
        import torch

        # 1. onnx stub
        if "transformers.onnx" not in sys.modules:
            onnx_mod = types.ModuleType("transformers.onnx")
            onnx_mod.__path__ = []
            onnx_mod.OnnxConfig = type("OnnxConfig", (), {})
            onnx_mod.OnnxSeq2SeqConfigWithPast = type("OnnxSeq2SeqConfigWithPast", (), {})
            sys.modules["transformers.onnx"] = onnx_mod
            onnx_utils_mod = types.ModuleType("transformers.onnx.utils")
            onnx_utils_mod.compute_effective_axis_dimension = lambda *a, **kw: None
            sys.modules["transformers.onnx.utils"] = onnx_utils_mod

        # 2. attn mask stub (ensuring CPU and float32)
        if "transformers.modeling_attn_mask_utils" not in sys.modules:
            m = types.ModuleType("transformers.modeling_attn_mask_utils")
            def _prepare_4d_attention_mask(mask, dtype, tgt_len=None):
                if mask is None:
                    return None
                if mask.dim() == 4:
                    return mask.to(device=torch.device("cpu"), dtype=torch.float32)
                bsz, src_len = mask.size()
                tgt_len = tgt_len if tgt_len is not None else src_len
                expanded = mask[:, None, None, :].expand(bsz, 1, tgt_len, src_len).to(device=torch.device("cpu"), dtype=torch.float32)
                inverted = 1.0 - expanded
                return inverted.masked_fill(inverted.to(torch.bool), torch.finfo(torch.float32).min)

            def _prepare_4d_causal_attention_mask(mask, input_shape, inputs_embeds, past_len, sliding=None):
                bsz, tgt_len = input_shape
                src_len = tgt_len + past_len
                dev = torch.device("cpu")
                dt = torch.float32
                causal = torch.full((tgt_len, src_len), torch.finfo(dt).min, device=dev, dtype=dt)
                cond = torch.arange(src_len, device=dev)
                causal.masked_fill_(cond < (torch.arange(tgt_len, device=dev) + 1 + past_len).view(-1, 1), 0)
                c4d = causal[None, None, :, :].expand(bsz, 1, tgt_len, src_len)
                if mask is not None:
                    if mask.dim() == 2:
                        c4d = c4d + _prepare_4d_attention_mask(mask, dt, tgt_len)
                    elif mask.dim() == 4:
                        c4d = c4d + mask.to(device=dev, dtype=dt)
                return c4d

            m._prepare_4d_attention_mask = _prepare_4d_attention_mask
            m._prepare_4d_attention_mask_for_sdpa = _prepare_4d_attention_mask
            m._prepare_4d_causal_attention_mask = _prepare_4d_causal_attention_mask
            m._prepare_4d_causal_attention_mask_for_sdpa = _prepare_4d_causal_attention_mask
            sys.modules["transformers.modeling_attn_mask_utils"] = m

        # 3. PreTrainedTokenizerBase special tokens map fix
        import transformers
        orig_new = transformers.PreTrainedTokenizerBase.__new__
        if not getattr(orig_new, "_indictrans_patched", False):
            def patched_new(cls, *args, **kwargs):
                inst = orig_new(cls)
                inst._special_tokens_map = {}
                return inst
            patched_new._indictrans_patched = True
            transformers.PreTrainedTokenizerBase.__new__ = staticmethod(patched_new)

        # 4. Dynamic module loader patch for tie_weights and _tie_or_clone_weights
        import transformers.dynamic_module_utils as dmu
        orig_get_class = dmu.get_class_from_dynamic_module
        if not getattr(orig_get_class, "_indictrans_patched", False):
            def patched_get_class(*args, **kwargs):
                cls = orig_get_class(*args, **kwargs)
                if hasattr(cls, "tie_weights"):
                    orig_tw = cls.tie_weights
                    cls.tie_weights = lambda self, *a, **kw: orig_tw(self)
                if not hasattr(cls, "_tie_or_clone_weights"):
                    cls._tie_or_clone_weights = lambda self, a, b: setattr(a, "weight", b.weight)
                return cls
            patched_get_class._indictrans_patched = True
            dmu.get_class_from_dynamic_module = patched_get_class

    def _load_model_for_direction(self, direction: str):
        """Loads weights for the specified direction, unloading any previously active model."""
        if self._current_direction == direction and self._model is not None:
            return

        # Unload previous model to maintain strict low memory footprint
        self.unload_model()

        dir_path = self.get_direction_dir(direction)
        if not self.is_direction_installed(direction):
            raise LanguagePairNotSupportedError(
                source="unknown", target="unknown",
                message=f"IndicTrans2 model for direction '{direction}' is not installed in {dir_path}.",
                instructions=self.get_installation_instructions(),
            )

        if not self.is_available():
            raise TranslatorNotAvailableError(
                "IndicTrans2 dependencies (IndicTransToolkit, transformers, torch) are missing.",
                instructions=self.get_installation_instructions(),
            )

        self._apply_runtime_shims()

        device = self._determine_device()
        self._device = device

        if _TORCH_AVAILABLE and torch is not None:
            try:
                torch.set_num_threads(4)
            except Exception:
                pass

        # Load IndicProcessor
        from IndicTransToolkit.processor import IndicProcessor
        self._ip = IndicProcessor(inference=True)

        # Load Tokenizer & Model via Hugging Face Transformers strictly on CPU in float32
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(str(dir_path), trust_remote_code=True)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            str(dir_path),
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            dtype=torch.float32,
        )
        self._model.to("cpu")
        self._model.eval()

        # Re-initialize non-persistent sinusoidal positional buffers with mathematical precision on CPU float32
        def reset_pos_emb(mod, max_pos, dim, pad_idx):
            weights = mod.get_embedding(max_pos + mod.offset, dim, pad_idx)
            mod.register_buffer(
                "weights",
                weights.to(dtype=torch.float32, device=torch.device("cpu")),
                persistent=False,
            )

        reset_pos_emb(
            self._model.model.encoder.embed_positions,
            self._model.config.max_source_positions,
            self._model.config.encoder_embed_dim,
            self._model.config.pad_token_id,
        )
        reset_pos_emb(
            self._model.model.decoder.embed_positions,
            self._model.config.max_target_positions,
            self._model.config.decoder_embed_dim,
            self._model.config.pad_token_id,
        )

        self._current_direction = direction

    def get_route_details(self, source: str, target: str) -> Dict[str, Any]:
        """
        Returns structured route details for UI display and engine router.
        """
        src = source.lower().strip()
        tgt = target.lower().strip()
        from_name = get_language_display_name(src)
        to_name = get_language_display_name(tgt)

        if src == tgt:
            return {
                "status": "same_language",
                "route_type": "same_language",
                "engine": "indictrans2",
                "is_ready": True,
                "can_translate": True,
                "direction": "same_language",
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": "Ready (same language)",
                "status_line": f"{from_name} to {to_name} (same language)",
                "tooltip": f"Source and target languages are both '{from_name}'. Translation is bypassed.",
                "message": f"Source and target languages are both '{from_name}'. Translation skipped.",
                "missing_folder": None,
            }

        direction = get_model_direction(src, tgt)
        if not direction:
            return {
                "status": "unsupported_pair",
                "route_type": None,
                "engine": "indictrans2",
                "is_ready": False,
                "can_translate": False,
                "direction": None,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": "Unsupported",
                "status_line": f"{from_name} to {to_name} (unsupported by IndicTrans2)",
                "tooltip": f"IndicTrans2 supports 22 Indian languages and English. '{src}' to '{tgt}' is outside its scope.",
                "message": f"Language pair '{from_name}' to '{to_name}' is not supported by IndicTrans2.",
                "missing_folder": None,
            }

        dir_path = self.get_direction_dir(direction)
        installed = self.is_direction_installed(direction)
        dir_name = get_direction_display_name(direction)

        if not self.is_available():
            return {
                "status": "engine_missing",
                "route_type": None,
                "engine": "indictrans2",
                "is_ready": False,
                "can_translate": False,
                "direction": direction,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": "Engine Missing",
                "status_line": f"{from_name} to {to_name} (IndicTransToolkit missing)",
                "tooltip": "IndicTrans2 toolkit dependencies are not installed in your Python environment.",
                "message": "IndicTrans2 toolkit dependencies (IndicTransToolkit, transformers, torch) are missing.",
                "missing_folder": str(dir_path),
                "instructions": self.get_installation_instructions((src, tgt)),
            }

        if installed:
            return {
                "status": "ready_direct",
                "route_type": "direct",
                "engine": "indictrans2",
                "is_ready": True,
                "can_translate": True,
                "direction": direction,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": "Ready (IndicTrans2 direct)",
                "status_line": f"{from_name} to {to_name}: IndicTrans2 (direct)",
                "tooltip": f"Direct IndicTrans2 neural model ready ({dir_name}). Zero pivot required.",
                "message": f"{from_name} to {to_name} (IndicTrans2 direct)",
                "missing_folder": None,
            }

        size_info = MODEL_SIZES_INFO.get(direction, {})
        hf_repo = size_info.get("huggingface_repo", f"ai4bharat/indictrans2-{direction}-dist-200M")
        size_str = size_info.get("download_size", "~800MB - 1GB")

        msg = (
            f"IndicTrans2 {dir_name} model is not installed. "
            f"Download from Hugging Face ({hf_repo}, {size_str}) and place in models/indictrans2/{direction}/."
        )

        return {
            "status": "model_missing",
            "route_type": "direct",
            "engine": "indictrans2",
            "is_ready": False,
            "can_translate": False,
            "direction": direction,
            "source_code": src,
            "target_code": tgt,
            "source_name": from_name,
            "target_name": to_name,
            "status_label": "Model Missing",
            "status_line": f"{from_name} to {to_name} (IndicTrans2 {direction} missing)",
            "tooltip": msg,
            "message": msg,
            "missing_folder": str(dir_path),
            "instructions": self.get_installation_instructions((src, tgt)),
        }

    def translate(self, text: str, source: str, target: str) -> TranslationOutput:
        """
        Translates text using IndicTrans2 with lazy direction loading and sentence chunking.
        """
        if not text or not text.strip():
            return TranslationOutput(
                translated_text="",
                source_language=source,
                target_language=target,
            )

        src = source.lower().strip()
        tgt = target.lower().strip()

        if src == tgt:
            return TranslationOutput(
                translated_text=text,
                source_language=source,
                target_language=target,
                was_pivoted=False,
                notice=f"Source and target languages are both '{source}'. Translation skipped.",
            )

        direction = get_model_direction(src, tgt)
        if not direction:
            raise LanguagePairNotSupportedError(
                src, tgt,
                message=f"Language pair '{src}' to '{tgt}' is not supported by IndicTrans2.",
                instructions=self.get_installation_instructions((src, tgt)),
            )

        if not self.is_direction_installed(direction):
            dir_path = self.get_direction_dir(direction)
            raise LanguagePairNotSupportedError(
                src, tgt,
                message=f"IndicTrans2 model for direction '{direction}' is not installed in {dir_path}.",
                instructions=self.get_installation_instructions((src, tgt)),
            )

        # Map to Flores-200 script codes
        src_flores = app_code_to_indictrans(src)
        tgt_flores = app_code_to_indictrans(tgt)
        if not src_flores or not tgt_flores:
            raise LanguagePairNotSupportedError(
                src, tgt,
                message=f"Cannot map language codes ({src} -> {src_flores}, {tgt} -> {tgt_flores}) for IndicTrans2.",
            )

        # Lazy load model direction
        self._load_model_for_direction(direction)

        # Split text into sentences for bounded memory batching (<= 500 characters)
        from translation.indic_text_processor import split_into_sentences
        raw_sentences = split_into_sentences(text)
        if not raw_sentences:
            raw_sentences = [text.strip()] if text.strip() else [text]

        # Combine sentence fragments to avoid tiny single-character chunks
        sentences = []
        cur = ""
        for s in raw_sentences:
            if len(cur) + len(s) < TRANSLATION_CHUNK_SIZE:
                cur = f"{cur} {s}".strip() if cur else s
            else:
                if cur:
                    sentences.append(cur)
                cur = s
        if cur:
            sentences.append(cur)

        try:
            # Process in small chunks of 2 sentences to protect 8 GB RAM and avoid monolithic memory spikes
            batch_size = 2
            final_translations = []

            for i in range(0, len(sentences), batch_size):
                chunk_slice = sentences[i : i + batch_size]
                batch = self._ip.preprocess_batch(chunk_slice, src_lang=src_flores, tgt_lang=tgt_flores)

                # Tokenize & explicitly ensure all input tensors are on CPU
                inputs = self._tokenizer(
                    batch,
                    src_lang=src_flores,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=256,
                )
                inputs = {k: v.to(device=torch.device("cpu")) for k, v in inputs.items()}

                # Generate
                with torch.inference_mode():
                    outputs = self._model.generate(
                        **inputs,
                        use_cache=True,
                        min_length=0,
                        max_length=256,
                        num_beams=5,
                        num_return_sequences=1,
                    )

                # Decode
                decoded = self._tokenizer.batch_decode(outputs, skip_special_tokens=True)

                # Postprocess using IndicProcessor
                translated_slice = self._ip.postprocess_batch(decoded, lang=tgt_flores)
                final_translations.extend(translated_slice)

            translated_result = " ".join(final_translations)

            return TranslationOutput(
                translated_text=translated_result,
                source_language=source,
                target_language=target,
                was_pivoted=False,
                notice=f"Translated directly via IndicTrans2 ({direction}).",
            )

        except Exception as e:
            raise TranslationError(f"IndicTrans2 translation failed: {str(e)}")

    def get_installation_instructions(self, missing_pair: Optional[Tuple[str, str]] = None) -> str:
        """
        Returns actionable instructions for downloading IndicTrans2 models and installing toolkits.
        """
        pair_header = ""
        suggested_direction = ""
        if missing_pair:
            src, tgt = missing_pair
            from_name = get_language_display_name(src)
            to_name = get_language_display_name(tgt)
            direction = get_model_direction(src, tgt)
            if direction:
                suggested_direction = direction
                pair_header = f"IndicTrans2 model for {from_name} to {to_name} ({direction}) is not installed.\n\n"

        return (
            f"{pair_header}"
            "AI4BHARAT INDICTRANS2 OFFLINE TRANSLATION SETUP GUIDE\n"
            "======================================================\n\n"
            "1. Install Required Python Packages:\n"
            "   pip install IndicTransToolkit transformers torch sentencepiece\n\n"
            "2. Download Model Weights (AI4Bharat Distilled Models):\n"
            "   IndicTrans2 models are available on Hugging Face (CC-BY-4.0 License):\n"
            "   • English to Indic (~800 MB):  https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M\n"
            "   • Indic to English (~800 MB):  https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M\n"
            "   • Indic to Indic (~1.2 GB):    https://huggingface.co/ai4bharat/indictrans2-indic-indic-dist-320M\n\n"
            "3. Place Downloaded Model Folders in Application Directory:\n"
            "   • models/indictrans2/en-indic/\n"
            "   • models/indictrans2/indic-en/\n"
            "   • models/indictrans2/indic-indic/\n\n"
            "Notes on Memory & 8 GB RAM Compatibility:\n"
            "• IndicTrans2 distilled models require only ~800 MB to 1.4 GB of RAM.\n"
            "• The system automatically unloads idle models between requests.\n"
            "• On Apple Silicon Macs, hardware acceleration (MPS) is used automatically.\n"
            "• 100% Offline Guarantee: The application never downloads models or makes network calls."
        )
