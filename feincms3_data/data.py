import io
import json
from collections import defaultdict
from functools import cache
from itertools import chain, count

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.utils.crypto import get_random_string
from django.utils.module_loading import import_string

from feincms3_data.serializers import JSONSerializer


def datasets():
    return import_string(settings.FEINCMS3_DATA_DATASETS)()


def _all_subclasses(cls):
    for sc in cls.__subclasses__():
        yield sc
        yield from _all_subclasses(sc)


def _only_concrete_models(iterable):
    for model in iterable:
        if not model._meta.abstract and not model._meta.proxy:
            yield model


def _random_values():
    """Generate a stream of values which are unlikely to cause conflicts"""
    prefix = get_random_string(20)
    for i in count():
        yield f"{prefix}-{i}"


class InvalidVersionError(Exception):
    pass


class InvalidSpecError(Exception):
    pass


_valid_keys = {
    "model",
    "filter",
    # Flags:
    "delete_missing",
    "ignore_missing_m2m",
    "save_as_new",
    "defer_values",
}


def _validate_spec(spec):
    if "model" not in spec:
        raise InvalidSpecError(f"The spec {spec!r} requires a 'model' key")
    if unknown := (set(spec.keys()) - _valid_keys):
        raise InvalidSpecError(f"The spec {spec!r} contains unknown keys: {unknown!r}")
    return spec


def specs_for_models(models, spec=None):
    spec = {} if spec is None else spec
    return [_validate_spec({**spec, "model": cls._meta.label_lower}) for cls in models]


def specs_for_derived_models(cls, spec=None):
    return specs_for_models(_only_concrete_models(_all_subclasses(cls)), spec)


def specs_for_app_models(app, spec=None):
    return specs_for_models(apps.get_app_config(app).get_models(), spec)


def _model_queryset(spec):
    queryset = apps.get_model(spec["model"])._default_manager.order_by("pk")
    if f := spec.get("filter"):
        queryset = queryset.filter(**f)
    return queryset


def silence(*a):
    pass


def dump_specs(specs, *, mappers=None, objects=None):
    stream = io.StringIO()
    stream.write('{"version": 1, "specs": ')
    json.dump(specs, stream)
    stream.write(', "objects": ')
    serializer = JSONSerializer(mappers=mappers or {})
    if objects is None:
        objects = chain.from_iterable(
            _model_queryset(spec).distinct() for spec in specs
        )
    serializer.serialize(objects, stream=stream)
    return stream.getvalue().rstrip("\n") + "}\n"


def load_dump(
    data, *, progress=silence, ignorenonexistent=False, using=DEFAULT_DB_ALIAS
):
    if data["version"] != 1:
        raise InvalidVersionError(f"Invalid dump version {data.get('version')!r}")
    for spec in data["specs"]:
        _validate_spec(spec)

    objects = defaultdict(list)
    seen_pks = defaultdict(set)

    # Yes, that is a bit stupid
    for ds in serializers.deserialize(
        "json", json.dumps(data["objects"]), ignorenonexistent=ignorenonexistent
    ):
        objects[ds.object._meta.label_lower].append(ds)

    progress(f"Loaded {len(data['objects'])} objects")

    save_as_new_models = {
        spec["model"] for spec in data["specs"] if spec.get("save_as_new")
    }

    with transaction.atomic(using=using):
        connection = connections[using]
        with connection.constraint_checks_disabled():
            models = set()
            _load_dump(
                data,
                objects,
                progress,
                seen_pks,
                save_as_new_models,
                models,
            )
            _finalize(
                progress,
                connection,
                models,
            )


def _load_dump(
    data,
    objects,
    progress,
    seen_pks,
    save_as_new_models,
    models,
):
    save_as_new_pk_map = defaultdict(dict)
    ignore_missing_m2m_data = defaultdict(dict)
    deferred_new_pks = []
    deferred_values = []

    for spec in data["specs"]:
        if objs := objects[spec["model"]]:
            for ds in objs:
                for field_name in spec.get("ignore_missing_m2m", ()):
                    ignore_missing_m2m_data[ds][field_name] = ds.m2m_data.pop(
                        field_name, []
                    )

                random_value = _random_values()
                for field_name in spec.get("defer_values", ()):
                    deferred_values.append(
                        (ds, field_name, getattr(ds.object, field_name))
                    )
                    setattr(ds.object, field_name, next(random_value))

                # _do_save changes the PK if the model is in
                # save_as_new_models
                seen_pks[ds.object._meta.label_lower].add(ds.object.pk)
                _do_save(
                    ds,
                    pk_map=save_as_new_pk_map,
                    save_as_new_models=save_as_new_models,
                    deferred_new_pks=deferred_new_pks,
                )
                seen_pks[ds.object._meta.label_lower].add(ds.object.pk)
                models.add(ds.object.__class__)

        progress(f"Saved {len(objs)} {spec['model']} objects")

    _save_deferred_new_pks(deferred_new_pks)

    for spec in reversed(data["specs"]):
        if not spec.get("delete_missing"):
            continue

        queryset = _model_queryset(spec)
        deleted = queryset.exclude(pk__in=seen_pks[spec["model"]]).delete()
        if deleted[0]:
            progress(f"Deleted {spec['model']} objects: {deleted}")

    pks = pk_cache()
    for ds, lists in ignore_missing_m2m_data.items():
        for field_name, field_pks in lists.items():
            field = ds.object._meta.get_field(field_name)
            existing = pks(field.related_model)
            getattr(ds.object, field_name).set(set(field_pks) & existing)

    for ds, field_name, value in deferred_values:
        setattr(ds.object, field_name, value)
        ds.save()


def _save_deferred_new_pks(deferred_new_pks):
    for ds, f_name, pk_map, fk in deferred_new_pks:
        setattr(ds.object, f_name, pk_map[fk])
        ds.save()


def _finalize(
    progress,
    connection,
    models,
):
    table_names = [model._meta.db_table for model in models]
    try:
        connection.check_constraints(table_names=table_names)
    except Exception as e:
        e.args = ("Problem installing fixtures: %s" % e,)
        raise

    sequence_sql = connection.ops.sequence_reset_sql(no_style(), models)
    if sequence_sql:
        progress("Resetting sequences")
        with connection.cursor() as cursor:
            for line in sequence_sql:
                cursor.execute(line)


def pk_cache():
    @cache
    def pks(model):
        return set(model._default_manager.values_list("pk", flat=True))

    return pks


_sentinel = object()


def _do_save(ds, *, pk_map, save_as_new_models, deferred_new_pks):
    # Map old PKs to new
    for f in ds.object._meta.get_fields():
        if (
            f.concrete
            and f.related_model
            and f.related_model._meta.label_lower in save_as_new_models
            and (fk := getattr(ds.object, f.column)) is not None
        ):
            if (new_pk := pk_map[f.related_model].get(fk, _sentinel)) is not _sentinel:
                setattr(ds.object, f.name, new_pk)
            else:
                # If foreign key isn't nullable we're toast.
                setattr(ds.object, f.name, None)
                # But if it is, we can defer.
                deferred_new_pks.append((ds, f.name, pk_map[f.related_model], fk))

    if ds.object._meta.label_lower in save_as_new_models:
        # Do the saving
        old_pk = ds.object.pk
        ds.object.pk = None
        ds.save(force_insert=True)
        pk_map[ds.object.__class__][old_pk] = ds.object

    else:
        ds.save()
