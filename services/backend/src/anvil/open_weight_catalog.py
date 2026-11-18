"""User-supplied catalog metadata, never repository or execution qualification."""

import json
from pathlib import Path

WORKBOOK_SHA256 = "2065695f88e3fdb34439df1c20d09c7b354dd5d3b81aa46d208eb73cc1532380"
GROUP = "open-weight-models"
ROWS = (
    ("Alibaba (Qwen)", "Qwen/Qwen3.6-35B-A3B", "MoE (35B total / 3B active)", "Apache 2.0"),
    ("Alibaba (Qwen)", "Qwen/Qwen3.8-27B / Qwen3.5-27B", "Dense (27B)", "Apache 2.0"),
    ("Alibaba (Qwen)", "Qwen3.5-122B-A10B", "MoE (122B total / 10B active)", "Apache 2.0"),
    ("Alibaba (Qwen)", "Qwen3-235B-A22B", "MoE (235B total / 22B active)", "Apache 2.0"),
    ("DeepSeek", "DeepSeek-V4-Flash", "MoE (284B total / 13B active)", "MIT"),
    ("DeepSeek", "DeepSeek-R1-Distill-32B", "Dense (32B)", "MIT"),
    (
        "Google",
        "Gemma 4 31B / Gemma 4 26B-A4B",
        "Dense (31B) / MoE (26B total, 4B active)",
        "Apache 2.0",
    ),
    ("Google", "Gemma 4 12B Unified", "Dense Multimodal (12B)", "Apache 2.0"),
    (
        "Meta",
        "Llama 4 Scout / Llama 4 Maverick",
        "MoE (Long-context / Enterprise)",
        "Llama Community",
    ),
    ("Meta", "Llama-3.3-70B", "Dense (70B)", "Llama Community"),
    (
        "Meta",
        "Muse Spark Open / Muse-Glimmer-30B",
        "MoE (816B / 42B active) / Dense (29.6B)",
        "Muse License / Apache 2.0",
    ),
    (
        "Mistral AI",
        "Mistral Large 3 (mistral-large-2512)",
        "MoE (675B total / 41B active)",
        "Apache 2.0",
    ),
    ("Mistral AI", "Mistral Small 4", "MoE (119B total / 6B active)", "Apache 2.0"),
    (
        "OpenAI",
        "openai/gpt-oss-120b / openai/gpt-oss-20b",
        "MoE (117B / 5.1B active & 21B / 3.6B active)",
        "Apache 2.0",
    ),
    (
        "NVIDIA",
        "Nemotron 3.5 Super-VL / Bolt 74B-A9B",
        "Hybrid Mamba-2/MoE (120B / 74B)",
        "OpenMDW-1.1",
    ),
    ("Zhipu AI", "GLM-4.7-Flash / GLM-4.5-Air", "MoE (30B / 3B active & 106B / 12B active)", "MIT"),
    ("MiniMax", "MiniMax M2.7", "MoE (230B total / 10B active)", "MIT"),
)


def catalog():
    metadata = json.loads(Path(__file__).with_name("open_weight_repositories.json").read_text())
    return {
        "id": GROUP,
        "name": "Open Weight Models",
        "workbook_sha256": WORKBOOK_SHA256,
        "live_available": False,
        "metadata_observed_at": metadata["observed_at"],
        "items": [
            {
                "id": f"ow-r{row}-v{variant}",
                "source_row": row,
                "publisher": publisher,
                "label": label,
                "source_label": labels,
                "architecture_claim": architecture,
                "license_claim": license_name,
                "repository_state": "public_metadata_observed",
                "repositories": metadata["items"][f"ow-r{row}-v{variant}"],
                "access_state": "not_checked",
                "execution_state": "not_configured",
            }
            for row, (publisher, labels, architecture, license_name) in enumerate(ROWS, 2)
            for variant, label in enumerate(labels.split(" / "), 1)
        ],
    }


def entry(identifier):
    return next((item for item in catalog()["items"] if item["id"] == identifier), None)
