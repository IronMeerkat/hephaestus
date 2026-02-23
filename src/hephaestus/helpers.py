from typing import Dict, Any

from pydantic import BaseModel  


def nested_update(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            dict1[key] = nested_update(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Oligaton(type(BaseModel)):
    """Metaclass that caches one instance per (class, key). Like Singleton but allows multiple instances keyed by the first arg."""
    _instances: dict = {}
    # TODO dump this and the Singleton in hephaestus
    def __call__(cls, *args, **kwargs):
        
        cache_key = (cls, kwargs.pop("_key"))
        if cache_key not in cls._instances:
            cls._instances[cache_key] = super().__call__(*args, **kwargs)
        return cls._instances[cache_key]
