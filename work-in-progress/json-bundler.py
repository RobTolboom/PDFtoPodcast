import json
import re
from copy import deepcopy
from pathlib import Path

COMMON_ID = "https://example.org/schemas/common.schema.json"  # pas aan indien nodig
COMMON_REF_RX = re.compile(rf"^{re.escape(COMMON_ID)}#/\$defs/([^/]+)$")


def find_common_refs(node):
    """Yield alle def-namen uit common waarnaar verwezen wordt."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                m = COMMON_REF_RX.match(v)
                if m:
                    yield m.group(1)
            else:
                yield from find_common_refs(v)
    elif isinstance(node, list):
        for item in node:
            yield from find_common_refs(item)


def rewrite_refs_to_local(node):
    """Vervang externe common-refs door lokale #/$defs/<name> refs."""
    if isinstance(node, dict):
        new = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                m = COMMON_REF_RX.match(v)
                if m:
                    new[k] = f"#/$defs/{m.group(1)}"
                else:
                    new[k] = rewrite_refs_to_local(v)
            else:
                new[k] = rewrite_refs_to_local(v)
        return new
    elif isinstance(node, list):
        return [rewrite_refs_to_local(x) for x in node]
    return node


def bundle_schema(rct_schema, common_schema):
    bundled = deepcopy(rct_schema)

    # verzamel benodigde defs uit common
    needed = set(find_common_refs(bundled))

    # maak/merge lokale $defs
    bundled.setdefault("$defs", {})
    defs = bundled["$defs"]

    for name in sorted(needed):
        if name in defs:
            continue
        if name not in common_schema.get("$defs", {}):
            raise KeyError(f"Def '{name}' niet gevonden in common")
        defs[name] = deepcopy(common_schema["$defs"][name])

    # herschrijf $ref's naar lokale refs
    bundled = rewrite_refs_to_local(bundled)

    return bundled


if __name__ == "__main__":
    common = json.loads(Path("schemas/common.schema.json").read_text())
    rct = json.loads(Path("schemas/interventional_trial.schema.json").read_text())

    # Zorg dat COMMON_ID overeenkomt met common["$id"]
    assert common["$id"] == COMMON_ID, "COMMON_ID komt niet overeen met $id in common"

    bundled = bundle_schema(rct, common)
    Path("schemas/interventional_trial_bundled.json").write_text(
        json.dumps(bundled, ensure_ascii=False, indent=2)
    )
    print("Bundled schema geschreven naar schemas/interventional_trial_bundled.json")
