PDS Data Upload Manager
=======================

The Planetary Data System (PDS_) Data Upload Manager (DUM_) Service provides a
means for PDS Node end-users to request upload of files (PDS collections, labels, etc.)
to the PDS Nucleus Cloud Computing environment. Use of the DUM is typically the
first step in ingesting large data volumes to the PDS cloud for indexing, validation and
eventual dissemination.

Currently, the DUM service is deployed as a Python package, and consists of two
major facets:

* A client-side application (`pds-ingress-client`) to be used with on-prem environments
  to select the files to be uploaded to Nucleus.
* A server-side framework of AWS_ services to handle tasks such as
  user-authentication, mapping of requested files to S3 bucket(s), and log management.
  This framework can be deployed automatically via Terraform scripts bundled with the
  DUM repo.


Sitemap
=======

.. /overview

..  toctree::
    :glob:
    :caption: Contents:

    /installation/*
    /development/*
    /usage/*
    /terraform/*
    /api/*
    /support/*

.. _AWS: https://aws.amazon.com/
.. _DUM: https://github.com/NASA-PDS/data-upload-manager/
.. _PDS: https://pds.nasa.gov/
