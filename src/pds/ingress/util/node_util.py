"""
============
node_util.py
============

Module containing functions for working with PDS Node identifiers.

"""


class NodeUtil:
    """Provides methods to validate PDS Node identifiers."""

    node_id_to_long_name = {
        "atm": "Atmospheres",
        "eng": "Engineering",
        "geo": "Geosciences",
        "img": "Cartography and Imaging Sciences Discipline",
        "naif": "Navigational and Ancillary Information Facility",
        "ppi": "Planetary Plasma Interactions",
        "rs": "Radio Science",
        "rms": "Ring-Moon Systems",
        "sbn": "Small Bodies",
    }

    @classmethod
    def permissible_node_ids(cls):
        """Returns a list of the Node IDs accepted by the Ingress client"""
        return cls.node_id_to_long_name.keys()

    @classmethod
    def node_id_to_group_name(cls, node_id):
        """Returns the Cognito group name for the given node ID"""
        if node_id.lower() not in cls.node_id_to_long_name.keys():
            raise ValueError(f'Unknown node ID "{node_id}"')

        return f"PDS_{node_id.upper()}_USERS"
