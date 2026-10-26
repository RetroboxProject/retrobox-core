"""Loader of the feature YAML files, shared by the es_features generator and the launcher."""

from __future__ import annotations

import re
from typing import IO, Any

import yaml

_BOOL_TAG = "tag:yaml.org,2002:bool"
_BOOL_PATTERN = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class _FeatureLoader(yaml.SafeLoader):  # pylint: disable=too-many-ancestors
    """SafeLoader where only true and false are booleans, as in YAML 1.2.

    YAML 1.1 also reads yes, no, on and off as booleans, so a choice written as
    ``name: On`` or ``name: Off`` would be shown as True or False in the menu, and a
    value like ``no`` (a language) would become False.
    """


_FeatureLoader.yaml_implicit_resolvers = {
    first_char: [(tag, pattern) for tag, pattern in resolvers if tag != _BOOL_TAG]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_FeatureLoader.add_implicit_resolver(_BOOL_TAG, _BOOL_PATTERN, list("tTfF"))


def load_feature_yaml(source: str | IO[str]) -> Any:
    """Parse a feature YAML file or text.

    Raises:
        yaml.YAMLError: If the YAML is not valid.
    """
    return yaml.load(source, Loader=_FeatureLoader)  # noqa: S506  # the loader is a SafeLoader
