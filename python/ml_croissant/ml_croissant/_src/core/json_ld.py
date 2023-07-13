"""json_ld module."""

import json
from typing import Any

from ml_croissant._src.core import constants

import rdflib

Json = dict[str, Any]

_ML_COMMONS_PREFIX = str(constants.ML_COMMONS)
_SCHEMA_ORG_PREFIX = str(constants.SCHEMA_ORG)
# Mapping for non-trivial conversion:
_PREFIX_MAP = {
    "http://mlcommons.org/schema/Field": "field",
    "http://mlcommons.org/schema/RecordSet": "recordSet",
}


def _make_context():
    return {
        "@vocab": "https://schema.org/",
        "applyTransform": "ml:applyTransform",
        "data": "ml:data",
        "dataType": "ml:dataType",
        "field": "ml:Field",
        "format": "ml:format",
        "includes": "ml:includes",
        "ml": "http://mlcommons.org/schema/",
        "recordSet": "ml:RecordSet",
        "references": "ml:references",
        "regex": "ml:regex",
        "sc": "https://schema.org/",
        "separator": "ml:separator",
        "source": "ml:source",
        "subField": "ml:SubField",
        "wd": "https://www.wikidata.org/wiki/",
    }


def _is_dataset_node(node: Json) -> bool:
    """Checks if the type of a node is schema.org/Dataset/"""
    return node.get("@type") == [str(constants.SCHEMA_ORG_DATASET)]


def _sort_items(json_ld: Json) -> list[tuple[str, Any]]:
    """Sorts items from dict.items().

    For human readability, we want "@type"/"name"/"description" to be at the beginning
    of the JSON, while long lists (""distribution"/"recordSet") are at the end.
    """
    items = sorted(json_ld.items())
    start_keys = ["@context", "@type", "name", "description"]
    end_keys = ["distribution", "recordSet"]
    sorted_items = []
    for key in start_keys:
        if key in json_ld:
            sorted_items.append((key, json_ld[key]))
    for item in items:
        if item[0] not in start_keys and item[0] not in end_keys:
            sorted_items.append(item)
    for key in end_keys:
        if key in json_ld:
            sorted_items.append((key, json_ld[key]))
    return sorted_items


def _sort_dict(d: dict[str, Any]):
    """Sorts the keys of a nested dict."""
    return {k: _sort_dict(v) if isinstance(v, dict) else v for k, v in _sort_items(d)}


def _recursively_populate_fields(entry_node: Json, id_to_node: dict[str, Json]) -> Any:
    """Changes in place `entry_node` with its children."""
    if len(entry_node) == 1 and "@value" in entry_node:
        return entry_node["@value"]
    elif len(entry_node) == 1 and "@id" in entry_node:
        node_id = entry_node["@id"]
        node = id_to_node[node_id]
        return _recursively_populate_fields(node, id_to_node)
    for key, value in entry_node.items():
        if key == "@type":
            entry_node[key] = value[0]
        elif isinstance(value, list):
            value = [_recursively_populate_fields(child, id_to_node) for child in value]
            if len(value) == 1:
                entry_node[key] = value[0]
            else:
                entry_node[key] = value
    return entry_node


def expand_json_ld(data: Json) -> Json:
    graph = rdflib.Graph()
    graph.parse(
        data=data,
        format="json-ld",
    )
    # `graph.serialize` outputs a stringified list of JSON-LD nodes.
    nodes = graph.serialize(format="json-ld")
    nodes = json.loads(nodes)
    # Find the entry node (schema.org/Dataset).
    entry_node = next((record for record in nodes if _is_dataset_node(record)), None)
    if entry_node is None:
        raise ValueError(f"File does not define {constants.SCHEMA_ORG_DATASET}.")
    id_to_node: dict[str, Json] = {}
    for node in nodes:
        node_id = node.get("@id")
        id_to_node[node_id] = node
    _recursively_populate_fields(entry_node, id_to_node)
    entry_node["@context"] = _make_context()
    return entry_node


def reduce_json_ld(json: Any) -> Any:
    """Recursively reduces the JSON-LD value to human-readable values.

    For example: "http://schema.org/Dataset" -> "sc:Dataset".
    """
    if isinstance(json, list):
        return [reduce_json_ld(element) for element in json]
    elif not isinstance(json, dict):
        if isinstance(json, str) and _SCHEMA_ORG_PREFIX in json:
            return json.replace(_SCHEMA_ORG_PREFIX, "sc:")
        elif isinstance(json, str) and _ML_COMMONS_PREFIX in json:
            return json.replace(_ML_COMMONS_PREFIX, "ml:")
        else:
            return json
    for key, value in json.copy().items():
        if key == "@context":
            # `@context` is left untouched.
            continue
        new_value = reduce_json_ld(value)
        if key == "@id":
            del json[key]
        elif key in _PREFIX_MAP:
            del json[key]
            json[_PREFIX_MAP[key]] = new_value
        elif _SCHEMA_ORG_PREFIX in key:
            new_key = key.replace(_SCHEMA_ORG_PREFIX, "")
            del json[key]
            json[new_key] = new_value
        elif _ML_COMMONS_PREFIX in key:
            new_key = key.replace(_ML_COMMONS_PREFIX, "")
            del json[key]
            json[new_key] = new_value
        else:
            json[key] = new_value
    return _sort_dict(json)
