from typing import Dict, Any


def nested_update(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            dict1[key] = nested_update(dict1[key], value)
        else:
            dict1[key] = value
    return dict1
