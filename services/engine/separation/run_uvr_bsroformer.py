from __future__ import annotations

import argparse
from pathlib import Path

from services.engine.separation.uvr_bsroformer_adapter import separate_with_bsroformer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--vocals-out", required=True)
    parser.add_argument("--instrumental-out", required=True)
    parser.add_argument("--uvr-repo", required=True)
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--yaml", required=True)
    args = parser.parse_args()

    separate_with_bsroformer(
        Path(args.input),
        Path(args.vocals_out),
        Path(args.instrumental_out),
    )


if __name__ == "__main__":
    main()
