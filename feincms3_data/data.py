import io
import json
from collections import defaultdict
from functools import lru_cache
from itertools import chain

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import transaction
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
        if not model._meta.abstract and model._meta.managed:
            yield model


class InvalidSpec(Exception):
    pass


_valid_keys = {
    "model",
    "filter",
    # Flags:
    "delete_missing",
    "ignore_missing_m2m",
    "save_as_new",
}


def _validate_spec(spec):
    if "model" not in spec:
        raise InvalidSpec(f"The spec {spec!r} requires a 'model' key")
    if unknown := (set(spec.keys()) - _valid_keys):
        raise InvalidSpec(f"The spec {spec!r} contains unknown keys: {unknown!r}")
    return spec


def specs_for_models(models, spec=None):
    spec = {} if spec is None else spec
    return (_validate_spec({**spec, "model": cls._meta.label_lower}) for cls in models)


def specs_for_derived_models(cls, spec=None):
    return specs_for_models(_only_concrete_models(_all_subclasses(cls)), spec)


def specs_for_app_models(app, spec=None):
    return specs_for_models(apps.get_app_config(app).get_models(), spec)


def _model_queryset(spec):
    queryset = apps.get_model(spec["model"])._default_manager.all()
    if filter := spec.get("filter"):
        queryset = queryset.filter(**filter)
    return queryset


def silence(*a):
    pass


def dump_specs(specs, *, mappers=None):
    stream = io.StringIO()
    stream.write('{"version": 1, "specs": ')
    json.dump(specs, stream)
    stream.write(', "objects": ')
    serializer = JSONSerializer(mappers=mappers or {})
    serializer.serialize(
        chain.from_iterable(_model_queryset(spec) for spec in specs),
        stream=stream,
    )
    stream.write("}")
    return stream.getvalue()


def load_dump(data, *, progress=silence, ignorenonexistent=False):
    assert data["version"] == 1
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

    save_as_new_pk_map = defaultdict(dict)
    save_as_new_models = {
        spec["model"] for spec in data["specs"] if spec.get("save_as_new")
    }
    ignore_missing_m2m_data = defaultdict(dict)

    with transaction.atomic():
        for spec in data["specs"]:
            if objs := objects[spec["model"]]:
                for ds in objs:
                    if ignore_missing_m2m := spec.get("ignore_missing_m2m"):
                        for field_name in ignore_missing_m2m:
                            ignore_missing_m2m_data[ds][field_name] = ds.m2m_data.pop(
                                field_name, []
                            )

                    _do_save(
                        ds,
                        pk_map=save_as_new_pk_map,
                        save_as_new_models=save_as_new_models,
                    )
                    seen_pks[ds.object._meta.label_lower].add(ds.object.pk)

            progress(f"Saved {len(objs)} {spec['model']} objects")

        for spec in data["specs"]:
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


def pk_cache():
    @lru_cache(maxsize=None)
    def pks(model):
        return set(model._default_manager.values_list("pk", flat=True))

    return pks


def _do_save(ds, *, pk_map, save_as_new_models):
    # Map old PKs to new
    for f in ds.object._meta.get_fields():
        if (
            f.concrete
            and f.related_model
            and f.related_model._meta.label_lower in save_as_new_models
        ):
            # XXX Do this unconditionally until we find a reason
            # if getattr(ds.object, f.column) in pk_map[f.related_model]:
            setattr(
                ds.object,
                f.name,
                pk_map[f.related_model][getattr(ds.object, f.column)],
            )

    if ds.object._meta.label_lower in save_as_new_models:
        # Do the saving
        old_pk = ds.object.pk
        ds.object.pk = None
        ds.save(force_insert=True)
        pk_map[ds.object.__class__][old_pk] = ds.object

    else:
        ds.save()
