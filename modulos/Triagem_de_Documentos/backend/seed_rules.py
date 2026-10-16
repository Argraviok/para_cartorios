"""Cria a coleção act_rules (validador + índice único) e insere/atualiza as regras.

Uso: python seed_rules.py   (idempotente; lê MONGO_URI e MONGO_DB do .env)
"""
import json
from pathlib import Path

from pymongo import MongoClient, UpdateOne

from app.core.config import settings

COLLECTION = "act_rules"
SEED_FILE = Path(__file__).parent / "seed_data" / "act_rules.json"

VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["act_type", "rule_code", "name", "description", "severity", "legal_ref"],
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "objectId"},
            "act_type": {"bsonType": "string", "pattern": "^[a-z0-9_]+$"},
            "rule_code": {"bsonType": "string", "pattern": "^REG-[0-9]{2}-[A-Z0-9-]+$"},
            "name": {"bsonType": "string", "minLength": 1},
            "description": {"bsonType": "string", "minLength": 1},
            "severity": {"enum": ["impeditiva", "recomendavel"]},
            "legal_ref": {"bsonType": "string", "minLength": 1},
            "active": {"bsonType": "bool"},
        },
    }
}


def main() -> None:
    db = MongoClient(settings.mongo_uri)[settings.mongo_db]
    if COLLECTION in db.list_collection_names():
        db.command("collMod", COLLECTION, validator=VALIDATOR, validationLevel="strict")
    else:
        db.create_collection(COLLECTION, validator=VALIDATOR, validationLevel="strict")
    db[COLLECTION].create_index("rule_code", unique=True)

    rules = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    result = db[COLLECTION].bulk_write([
        UpdateOne({"rule_code": r["rule_code"]}, {"$set": r}, upsert=True) for r in rules
    ])
    print(f"{COLLECTION}: {result.upserted_count} inseridas, {result.modified_count} atualizadas")


if __name__ == "__main__":
    main()
