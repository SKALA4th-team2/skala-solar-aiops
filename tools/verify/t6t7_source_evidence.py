"""Match source files to a recorded manual review, without claiming a new review."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


MANIFEST = Path(__file__).with_suffix(".json")
# The frozen manual record stores sources in this order.
SOURCE_ROLES = ("rule", "broker", "market")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for role in SOURCE_ROLES:
        parser.add_argument(f"--{role}", type=Path, required=True)
    parser.add_argument(
        "--broker-text",
        type=Path,
        help="Deprecated compatibility option; ignored. The HWP hash must match.",
    )
    args = parser.parse_args(argv)
    if args.broker_text is not None:
        print("--broker-text is ignored; the binary HWP is always checked.", file=sys.stderr)

    try:
        recorded_review = json.loads(MANIFEST.read_text(encoding="utf-8"))
        sources = recorded_review["sources"]
        if len(sources) != len(SOURCE_ROLES):
            raise ValueError("Manual review must contain rule, broker and market sources")
        for role, source in zip(SOURCE_ROLES, sources):
            actual = hashlib.sha256(getattr(args, role).read_bytes()).hexdigest()
            expected = source["sha256"]
            if actual != expected:
                raise ValueError(
                    f"{role}: SHA-256 mismatch (expected {expected}, got {actual}). "
                    "This file needs a separate manual review."
                )
    except (OSError, ValueError, KeyError, TypeError) as error:
        # No stdout or partial evidence is emitted when any input fails.
        parser.error(str(error))

    result = {
        "file_identity_check": {
            "kind": "sha256_match_to_recorded_manual_review",
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "matched_sources": list(SOURCE_ROLES),
        },
        # Dates, pages and visual-review flags belong only to the old review.
        "recorded_manual_review": recorded_review,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
