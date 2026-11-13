"""Download/verify the exact E5 snapshot used by the submitted experiments."""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Verify only the existing local cache")
    args = parser.parse_args()
    setup = json.loads((ROOT / "artifacts/local_setup.json").read_text(encoding="utf-8"))
    embedding = setup["embedding"]
    model = setup["model_files"][0]
    revision = Path(model["path"]).parents[1].name
    cache = ROOT / embedding["cache_dir"]
    folder = Path(snapshot_download(
        repo_id=embedding["model_name"], revision=revision, cache_dir=str(cache),
        allow_patterns=[embedding["model_file"], "config.json", "tokenizer.json",
                        "tokenizer_config.json", "special_tokens_map.json"],
        local_files_only=args.offline,
    ))
    digest = hashlib.sha256()
    with (folder / embedding["model_file"]).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != model["sha256"]:
        raise ValueError("Downloaded model hash differs from the submitted weights")
    # FastEmbed resolves main locally; point it to the verified immutable snapshot.
    refs = folder.parents[1] / "refs"
    refs.mkdir(exist_ok=True)
    (refs / "main").write_text(revision, encoding="utf-8")
    print(f"Model ready: {embedding['model_name']} | snapshot {revision} | SHA-256 verified")


if __name__ == "__main__":
    main()
