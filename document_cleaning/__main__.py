import argparse
from . import parse_document

parser = argparse.ArgumentParser(description="Explicitly run an optional document engine")
parser.add_argument("file")
parser.add_argument("--engine", default="auto", choices=["auto", "mineru", "docling", "paddleocr", "qwen-asr"])
parser.add_argument("--output-dir", default="outputs")
parser.add_argument("--tier", choices=["standard", "advanced"])
args = parser.parse_args()
options = {"tier": args.tier} if args.tier else {}
result = parse_document(args.file, engine=args.engine, output_dir=args.output_dir, **options)
print(result.output_dir)
