# feincms3-data

## Tests

    tox                      # full matrix
    python tests/manage.py test testapp   # single run, needs Django installed

The test app (`tests/testapp/`) has no migrations; tables are created directly
from the models, so new models don't need a migration.

`tests/testapp/test_data.py` contains assertions enumerating *all* testapp
models (`test_datasets`, `test_specs_for_app_models`) and one asserting the
exact dump JSON including primary keys (`test_json_format`) -- adding models
means updating those.

## Conventions

- Formatting and linting: `ruff` via `pre-commit`.
- Changes go into the "Next version" section of `CHANGELOG.rst`; spec flags are
  documented in `README.rst`.
- Commit proactively, even without being asked explicitly -- roughly one
  commit per logical feature/change. Never add Co-Authored-By or other AI
  attribution to commit messages.
