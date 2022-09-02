==========
Change log
==========

`Next version`_
~~~~~~~~~~~~~~~

.. _Next version: https://github.com/matthiask/feincms3-data/compare/0.2...main


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
