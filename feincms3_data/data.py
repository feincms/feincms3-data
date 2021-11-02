import io
import json
from collections import defaultdict
from itertools import chain

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import transaction
from django.utils.module_loading import import_string


def specs():
    return import_string(settings.FEINCMS3_DATA_SPECS)()


def _all_subclasses(cls):
    for sc in cls.__subclasses__():
        yield sc
        yield from _all_subclasses(sc)


def _only_concrete_models(iterable):
    for model in iterable:
        if not model._meta.abstract and model._meta.managed:
            yield model


def specs_for_models(models, spec=None):
    spec = {} if spec is None else spec
    return (spec | {"model": cls._meta.label_lower} for cls in models)


def specs_for_derived_models(cls, spec=None):
    return specs_for_models(_only_concrete_models(_all_subclasses(cls)), spec)


def specs_for_app_models(app, spec=None):
    return specs_for_models(
        apps.get_app_config(app).get_models(include_auto_created=True), spec
    )


def _model_queryset(spec):
    queryset = apps.get_model(spec["model"])._default_manager.all()
    if filter := spec.get("filter"):
        queryset = queryset.filter(**filter)
    return queryset


def silence(*a):
    pass


def dump_specs(specs):
    stream = io.StringIO()
    stream.write('{"version": 1, "specs": ')
    json.dump(specs, stream)
    stream.write(', "objects": ')
    serializers.serialize(
        "json",
        chain.from_iterable(_model_queryset(spec) for spec in specs),
        stream=stream,
    )
    stream.write("}")
    return stream.getvalue()


def load_dump(data, *, progress=silence, ignorenonexistent=False):
    assert data["version"] == 1

    objects = defaultdict(list)
    seen_pks = defaultdict(set)

    # Yes, that is a bit stupid
    for ds in serializers.deserialize(
        "json", json.dumps(data["objects"]), ignorenonexistent=ignorenonexistent
    ):
        objects[ds.object._meta.label_lower].append(ds)

    progress(f"Loaded {len(data['objects'])} objects")

    force_insert_pk_map = defaultdict(dict)
    force_insert_models = {
        spec["model"] for spec in data["specs"] if spec.get("force_insert")
    }

    with transaction.atomic():
        for spec in data["specs"]:
            if objs := objects[spec["model"]]:
                for ds in objs:
                    _do_save(ds, pk_map=force_insert_pk_map, models=force_insert_models)
                    seen_pks[ds.object._meta.label_lower].add(ds.object.pk)

            progress(f"Saved {len(objs)} {spec['model']} objects")

        for spec in data["specs"]:
            queryset = _model_queryset(spec)
            if deleted := queryset.exclude(pk__in=seen_pks[spec["model"]]).delete():
                progress(f"Deleted {spec['model']} objects: {deleted}")


def _do_save(ds, *, pk_map, models):
    if ds.object._meta.label_lower in models:
        # Map old PKs to new
        for f in ds.object._meta.get_fields():
            if (
                f.concrete
                and f.related_model
                and f.related_model._meta.label_lower in models
            ):
                if getattr(ds.object, f.column) in pk_map[f.related_model]:
                    setattr(
                        ds.object,
                        f.name,
                        pk_map[f.related_model][getattr(ds.object, f.column)],
                    )

        # Do the saving
        old_pk = ds.object.pk
        ds.object.pk = None
        ds.save(force_insert=True)
        pk_map[ds.object.__class__][old_pk] = ds.object

    else:
        ds.save()
