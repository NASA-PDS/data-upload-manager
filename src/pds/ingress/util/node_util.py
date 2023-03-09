"""
============
node_util.py
============

Module containing functions for working with PDS Node identifiers.

"""
import logging

logger = logging.getLogger(__name__)

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
        "sbn": "Small Bodies"
    }

    @classmethod
    def permissible_node_ids(cls):
        return cls.node_id_to_long_name.keys()