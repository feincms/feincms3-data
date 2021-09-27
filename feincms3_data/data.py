import io
import json
from collections import defaultdict
from itertools import chain

from django.apps import apps
from django.core import serializers
from django.db import transaction


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


def load_dump(data, *, progress=silence):
    assert data["version"] == 1

    objects = defaultdict(list)
    seen_pks = defaultdict(set)

    # Yes, that is a bit stupid
    for ds in serializers.deserialize("json", json.dumps(data["objects"])):
        objects[ds.object._meta.label_lower].append(ds)

    progress(f"Loaded {len(data['objects'])} objects")

    with transaction.atomic():
        for spec in data["specs"]:
            if objs := objects[spec["model"]]:
                for ds in objs:
                    ds.save()
                    seen_pks[ds.object._meta.label_lower].add(ds.object.pk)

            progress(f"Saved {len(objs)} {spec['model']} objects")

        for spec in data["specs"]:
            queryset = _model_queryset(spec)
            if deleted := queryset.exclude(pk__in=seen_pks[spec["model"]]).delete():
                progress(f"Deleted {spec['model']} objects: {deleted}")
