# -*- coding: utf-8 -*-
"""导出作业交付材料：提示词全文、知识库压缩包、截图归档。"""
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import prompts  # noqa: E402

DOCS_OUT = ROOT / "docs"
DIST = ROOT / "dist"
SHOTS_OUT = DOCS_OUT / "screenshots"

PROMPT_FILES = {
    "01_系统提示词.txt": prompts.SYSTEM_PROMPT,
    "02_风险分级提示词.txt": prompts.RISK_CLASSIFIER_PROMPT,
    "03_危机干预固定脚本.txt": prompts.CRISIS_SCRIPT,
    "04_图片讨论引导提示词.txt": prompts.IMAGE_GUIDE_PROMPT,
    "05_知识注入模板.txt": prompts.KNOWLEDGE_INJECT_TEMPLATE + "\n\n" + prompts.YELLOW_HINT_TEMPLATE,
}


def main() -> None:
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    SHOTS_OUT.mkdir(parents=True, exist_ok=True)

    for name, content in PROMPT_FILES.items():
        (DOCS_OUT / name).write_text(content.strip() + "\n", encoding="utf-8")

    kb_docs = sorted((ROOT / "app" / "knowledge" / "docs").glob("*.md"))
    zip_path = DIST / "知识库-66篇.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in kb_docs:
            zf.write(doc, arcname=f"knowledge/{doc.name}")
    print(f"knowledge zip: {zip_path} ({len(kb_docs)} docs, {zip_path.stat().st_size // 1024} KB)")

    keep = [
        "01-mobile-welcome.png",
        "02-mobile-chat.png",
        "03-mobile-voice.png",
        "04-mobile-image.png",
        "05-mobile-crisis.png",
        "06-desktop-chat.png",
        "07-image-preview.png",
        "08-image-sent.png",
        "10-voice-transcript.png",
        "14-yellow-strip.png",
        "16-desktop-modal.png",
    ]
    copied = 0
    for name in keep:
        src = ROOT / "shots" / name
        if src.exists():
            shutil.copyfile(src, SHOTS_OUT / name)
            copied += 1
    print(f"screenshots copied: {copied}")
    print(f"prompts exported: {len(PROMPT_FILES)}")


if __name__ == "__main__":
    main()
