"""Extract petstore generated files from out_local ZIP into fixtures cache."""
from __future__ import annotations

import zipfile
from pathlib import Path

from qa_gen_bot.gen_cache import save_gen_cache
from qa_gen_bot.scaffold import is_protected_path

_ROOT = Path(__file__).resolve().parents[1]
ZIP = _ROOT / "out_local" / "swaggerpetstore-qa-framework.zip"
OUT = _ROOT / "fixtures" / "petstore-gen-cache.json"
SPEC = _ROOT / "fixtures" / "petstore-swagger-api.json"
PKG = "com/swaggerpetstore"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def main() -> None:
    if not ZIP.is_file():
        raise SystemExit(f"Missing {ZIP} — run petstore generation once or provide ZIP")

    files: dict[str, str] = {}
    with zipfile.ZipFile(ZIP) as zf:
        for name in zf.namelist():
            p = _norm(name)
            if PKG not in p:
                continue
            if not p.endswith((".java", ".json")):
                continue
            if is_protected_path(p):
                continue
            if "/schemas/product" in p:
                continue
            # Generated output sometimes puts response DTOs under src/test — normalize to main
            if "/src/test/java/" in p and "/dto/response/" in p:
                p = p.replace("/src/test/java/", "/src/main/java/", 1)
            if p in files:
                continue
            files[p] = zf.read(name).decode("utf-8")

    files["src/test/resources/schemas/pet-schema.json"] = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": {"type": "integer"},
    "name": {"type": "string"},
    "photoUrls": {"type": "array", "items": {"type": "string"}},
    "status": {"type": "string"}
  }
}
"""
    files["src/test/resources/schemas/order-schema.json"] = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": {"type": "integer"},
    "petId": {"type": "integer"},
    "quantity": {"type": "integer"},
    "status": {"type": "string"},
    "complete": {"type": "boolean"}
  }
}
"""
    files["src/test/resources/schemas/user-schema.json"] = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": {"type": "integer"},
    "username": {"type": "string"},
    "firstName": {"type": "string"},
    "lastName": {"type": "string"},
    "email": {"type": "string"},
    "userStatus": {"type": "integer"}
  }
}
"""

    pet_int = files.get(
        "src/test/java/com/swaggerpetstore/tests/PetIntegrationTest.java", ""
    )
    if "client.update(updatedPet)" in pet_int:
        files["src/test/java/com/swaggerpetstore/tests/PetIntegrationTest.java"] = (
            pet_int.replace(
                "client.update(updatedPet)",
                "client.update(100501L, updatedPet)",
            )
        )

    save_gen_cache(
        OUT,
        spec_path=str(SPEC),
        package_hint="swaggerpetstore",
        files=files,
    )
    print(f"Wrote {len(files)} files -> {OUT}")


if __name__ == "__main__":
    main()
