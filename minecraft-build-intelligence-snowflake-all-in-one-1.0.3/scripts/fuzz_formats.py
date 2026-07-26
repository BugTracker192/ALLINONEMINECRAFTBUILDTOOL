from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from mbi.errors import MBIError
from mbi.importer import import_build
from mbi.limits import NBTLimits


def mutate(data: bytes, randomizer: random.Random) -> bytes:
    output = bytearray(data)
    for _ in range(randomizer.randint(1, 12)):
        action = randomizer.choice(("flip", "delete", "insert", "truncate"))
        if action == "flip" and output:
            index = randomizer.randrange(len(output)); output[index] ^= 1 << randomizer.randrange(8)
        elif action == "delete" and output:
            start = randomizer.randrange(len(output)); del output[start:start + randomizer.randint(1, min(32, len(output) - start))]
        elif action == "insert":
            start = randomizer.randrange(len(output) + 1); output[start:start] = randomizer.randbytes(randomizer.randint(1, 32))
        elif action == "truncate" and output:
            del output[randomizer.randrange(len(output)):]
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=8841)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).parents[1] / "packages" / "test-fixtures" / "generated"
    fixtures = [(path.name, path.read_bytes()) for path in sorted(root.glob("*")) if path.suffix in {".schem", ".litematic"}]
    randomizer = random.Random(args.seed)
    errors = Counter(); successes = 0; unexpected = []
    limits = NBTLimits(max_decompressed_bytes=64 * 1024 * 1024, max_volume=4_000_000)
    started = time.perf_counter()
    slowest = 0.0
    for index in range(args.iterations):
        name, data = randomizer.choice(fixtures)
        payload = mutate(data, randomizer)
        case_start = time.perf_counter()
        try:
            import_build(payload, name, limits)
            successes += 1
        except MBIError as exc:
            errors[exc.code] += 1
        except Exception as exc:
            unexpected.append({"iteration": index, "type": type(exc).__name__, "message": str(exc)})
        slowest = max(slowest, time.perf_counter() - case_start)
    report = {
        "iterations": args.iterations, "seed": args.seed, "successes": successes, "expectedErrors": dict(errors.most_common()),
        "unexpectedExceptions": unexpected, "seconds": time.perf_counter() - started, "slowestCaseSeconds": slowest,
    }
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text, "utf-8")
    print(text)
    if unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
