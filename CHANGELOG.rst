==========
Change log
==========

Next version
~~~~~~~~~~~~


0.8 (2025-03-14)
~~~~~~~~~~~~~~~~

- Ensured that dumps only ever contain distinct objects from single specs.
- Raised the minimum version requirements to Python 3.10 and Django 4.2.
- Added Django 5.2.
- Changed the JSON dumps to include a final newline. This change is inspired by
  the same change to Django.


0.7 (2024-10-28)
~~~~~~~~~~~~~~~~

- Added ``./manage.py f3dumpdata -`` which allows reading JSON data from stdin.
- Added Python 3.12, 3.13 and Django 5.0, 5.1.
- Order objects by their primary key when dumping specs. This helps with
  comparing JSON files by hand.


0.6 (2023-06-12)
~~~~~~~~~~~~~~~~

- Fixed the broken argument validation of ``./manage.py f3dumpdata``.
- Switched to hatchling and ruff.
- Made ``specs_for_*_models`` helpers return a list instead of a generator.
- Changed the ``assert`` statement for checking the dump version into a
  ``raise`` statement since assertions could be optimized out.
- Renamed ``InvalidSpec`` to ``InvalidSpecError`` to make ruff happier.
- Added an ``objects`` argument to ``dump_specs`` which allows overriding the
  list of objects to dump.


`0.5`_ (2023-03-15)
~~~~~~~~~~~~~~~~~~~

.. _0.5: https://github.com/matthiask/feincms3-data/compare/0.4...0.5

- Added argument validation to ``./manage.py f3dumpdata`` instead of crashing
  when the dataset isn't known.
- Added the ``defer_values`` spec field which allows specifying a list of
  fields whose real values should be deferred and only saved after missing data
  has been deleted. This is especially useful when you have unique fields where
  partial updates could produce constraint validation errors (unique
  constraints cannot be deferred it seems).


`0.4`_ (2023-02-13)
~~~~~~~~~~~~~~~~~~~

.. _0.4: https://github.com/matthiask/feincms3-data/compare/0.3...0.4

- Added various tests for expected behavior.
- Refactored ``load_dump`` to pass the code complexity checker.
- Added an expected failure test which shows that handling unique fields isn't
  yet working in all cases.
- Added Django 4.2a1 to the CI matrix.
- Allowed data loading with ``save_as_new`` to work in more scenarios where the
  data contains cyclic dependencies.


`0.3`_ (2022-09-19)
~~~~~~~~~~~~~~~~~~~

.. _0.3: https://github.com/matthiask/feincms3-data/compare/0.2...0.3

- Fixed a crash when using nullable foreign keys to a model which uses
  ``save_as_new``.
- Fix a behavior when using ``save_as_new`` together with ``delete_missing``:
  When the parent of a model with both flags set is updated, the content is now
  duplicated (because the old object hadn't been removed and the new one has
  been saved according to ``save_as_new``). Previously, the old object has been
  removed automatically. Worse, this made is impossible to use ``save_as_new``
  for duplicating top-level objects (their object graph would be removed after
  inserting the copy). This change may still be backwards incompatible for you
  though, so better check twice.
- Fixed deletion of missing objects in the presence of protected objects by
  processing specs in reverse.
- Changed ``specs_for_derived_models`` to skip proxy models instead of skipping
  unmanaged models.
- Started deferring constraints and resetting sequences when loading dumps.


`0.2`_ (2022-09-02)
~~~~~~~~~~~~~~~~~~~

.. _0.2: https://github.com/matthiask/feincms3-data/compare/0.1...0.2

- Added Django 4.1.
- Added the ``mappers`` argument to ``dump_specs`` which allows changing the
  serialized representation of models before writing the JSON.
- Changed ``load_dump`` to also validate specs.
- Replaced ``FEINCMS3_DATA_SPECS`` with the more flexible and opinionated
  ``FEINCMS3_DATA_DATASETS``.


`0.1`_ (2021-09-27)
~~~~~~~~~~~~~~~~~~~

- Initial release!

.. _0.1: https://github.com/matthiask/feincms3-data/commit/e50451b5661
