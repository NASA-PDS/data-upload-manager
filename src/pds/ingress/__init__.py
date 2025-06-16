# -*- coding: utf-8 -*-
"""PDS Data Upload Manager"""
from importlib.resources import files


__version__ = files("pds.ingress").joinpath("VERSION.txt").read_text().strip()
