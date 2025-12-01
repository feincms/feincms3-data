=============
feincms3-data
=============

.. image:: https://github.com/matthiask/feincms3-data/actions/workflows/tests.yml/badge.svg
    :target: https://github.com/matthiask/feincms3-data/
    :alt: CI Status


Why
===

Utilities for loading and dumping database data as JSON.

These utilities (partially) replace Django's built-in ``dumpdata`` and
``loaddata`` management commands.

Suppose you want to move data between systems incrementally. In this case it
isn't sufficient to only know the data which has been created or updated; you
also want to know which data has been deleted in the meantime. Django's
``dumpdata`` and ``loaddata`` management commands only support the former case,
not the latter. They also do not including dependent objects in the dump.

This package offers utilities and management commands to address these
shortcomings.


How
===

``pip install feincms3-data``.

Add ``feincms3_data`` to ``INSTALLED_APPS`` so that the included management
commands are discovered.

Add datasets somewhere describing the models and relationships you want to
dump, e.g. in a module named ``app.f3datasets``:

.. code-block:: python

    from feincms3_data.data import (
        specs_for_app_models,
        specs_for_derived_models,
        specs_for_models,
    )
    from app.dashboard import models as dashboard_models
    from app.world import models as world_models


    def districts(args):
        pks = [int(arg) for arg in args.split(",") if arg]
        return [
            *specs_for_models(
                [world_models.District],
                {
                    "filter": {"pk__in": pks},
                    "delete_missing": True,
                },
            ),
            *specs_for_models(
                [world_models.Exercise],
                {
                    "filter": {"district__in": pks},
                    "delete_missing": True,
                },
            ),
            # All derived non-abstract models which aren't proxies:
            *specs_for_derived_models(
                world_models.ExercisePlugin,
                {
                    "filter": {"parent__district__in": pks},
                    "delete_missing": True,
                },
            ),
        ]


    def datasets():
        return {
            "articles": {
                "specs": lambda args: specs_for_app_models(
                    "articles",
                    {"delete_missing": True},
                ),
            },
            "pages": {
                "specs": lambda args: specs_for_app_models(
                    "pages",
                    {"delete_missing": True},
                ),
            },
            "teachingmaterials": {
                "specs": lambda args: specs_for_models(
                    [
                        dashboard_models.TeachingMaterialGroup,
                        dashboard_models.TeachingMaterial,
                    ],
                    {"delete_missing": True},
                ),
            },
            "districts": {
                "specs": districts,
            },
        }

Add a setting with the Python module path to the specs function:

.. code-block:: python

    FEINCMS3_DATA_DATASETS = "app.f3datasets.datasets"


Now, to dump e.g. pages you would run::

    ./manage.py f3dumpdata pages > tmp/pages.json

To dump the districts with the primary key of 42 and 43 you would run::

    ./manage.py f3dumpdata districts:42,43 > tmp/districts.json

The resulting JSON file has three top-level keys:

- ``"version": 1``: The version of the dump, because not versioning dumps is a
  recipe for pain down the road.
- ``"specs": [...]``: A list of model specs.
- ``"objects": [...]``: A list of model instances; uses the same serializer as
  Django's ``dumpdata``, everything looks the same.

Model specs consist of the following fields:

- ``"model"``: The lowercased label (``app_label.model_name``) of a model.
- ``"filter"``: A dictionary which can be passed to the ``.filter()`` queryset
  method as keyword arguments; used for determining the objects to dump and the
  objects to remove after loading.
- ``"delete_missing"``: This flag makes the loader delete all objects matching
  ``"filter"`` which do not exist in the dump.
- ``"ignore_missing_m2m"``: A list of field names where deletions of related
  models should be ignored when restoring. This may be especially useful when
  only transferring content partially between databases.
- ``"save_as_new"``: If present and truish, objects are inserted using new
  primary keys into the database instead of (potentially) overwriting
  pre-existing objects.
- ``"defer_values"``: A list of fields which should receive random garbage when
  loading initially and only receive their real value later. This is especially
  useful to avoid unique constraint errors when loading partial graphs.

.. note::
   When using ``save_as_new`` and ``delete_missing`` together, you may need to
   specify how primary keys should be mapped to avoid inadvertent deletion of
   objects. If you have a parent model with ``save_as_new`` and child models
   with both ``save_as_new`` and ``delete_missing``, you should use the
   dictionary form of ``delete_missing`` with a ``map`` parameter to map old
   primary keys to new ones. For example:

   .. code-block:: python

       {
           "filter": {"parent__in": [42]},
           "save_as_new": True,
           "delete_missing": {
               "map": [
                   ("parent__in", "app.Parent"),
               ],
           },
       }

   This ensures that child objects are matched against the new parent primary
   keys rather than the old ones, preventing old data from being kept and new
   data from being inadvertently deleted.

   Note that the mapping fails loudly on purpose if the primary key mapping
   isn't available. The reason could be that the parent model doesn't actually
   use ``save_as_new``. Since this is a potentially destructive operation it's
   better to fail loudly than to silently eat data.

The dumps can be loaded back into the database by running::

    ./manage.py f3loaddata -v2 tmp/pages.json tmp/districts.json

Each dump is processed in an individual transaction. The data is first loaded
into the database; at the end, data *matching* the filters but whose primary
key wasn't contained in the dump is deleted from the database (if
``"delete_missing": True``).
