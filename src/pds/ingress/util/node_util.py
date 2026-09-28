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

    node_id_to_cognito_groups = {
        "atm": ["PDS_ATM_USERS"],
        "eng": ["PDS_ENG_USERS"],
        "geo": ["PDS_GEO_USERS"],
        "img": ["PDS_IMG_USERS"],
        "naif": ["PDS_NAIF_USERS"],
        "ppi": ["PDS_PPI_USERS"],
        "rs": ["PDS_RS_USERS"],
        "rms": ["PDS_RMS_USERS"],
        "sbn": ["PDS_SBN_USERS", "PDS_SBNUMD_USERS"],
    }

    @classmethod
    def permissible_node_ids(cls):
        """Returns a list of the Node IDs accepted by the Ingress client"""
        return cls.node_id_to_long_name.keys()

    @classmethod
    def node_id_to_group_names(cls, node_id):
        """Returns all Cognito group names permitted for the given node ID"""
        if node_id.lower() not in cls.node_id_to_cognito_groups:
            raise ValueError(f'Unknown node ID "{node_id}"')

        return cls.node_id_to_cognito_groups[node_id.lower()]

