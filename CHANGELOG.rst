==========
Change log
==========

`Next version`_
~~~~~~~~~~~~~~~

.. _Next version: https://github.com/matthiask/feincms3-data/compare/0.4...main


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
