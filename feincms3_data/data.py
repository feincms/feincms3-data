import io
import json
from collections import defaultdict
from copy import deepcopy
from functools import cache
from itertools import chain, count

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.module_loading import import_string

from feincms3_data.serializers import JSONEncoder, JSONSerializer


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


class InconsistentModelError(Exception):
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
    json.dump(specs, stream, cls=JSONEncoder)
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
        "json",
        json.dumps(data["objects"]),
        ignorenonexistent=ignorenonexistent,
        # handle_forward_references=True,
    ):
        objects[ds.object._meta.label_lower].append(ds)

    progress(f"Loaded {len(data['objects'])} objects")

    save_as_new_models = {
        spec["model"] for spec in data["specs"] if spec.get("save_as_new")
    }

    _check_mti_siblings(objects, save_as_new_models, using)

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


@cache
def _mti_siblings(model):
    """Concrete models sharing a parent -- and a primary key -- with ``model``"""
    return [
        rel.related_model
        for parent in model._meta.parents
        for rel in parent._meta.related_objects
        if rel.parent_link and rel.related_model is not model
    ]


def _check_mti_siblings(objects, save_as_new_models, using):
    """
    Refuse to load if the database disagrees with the dump about what an object is

    Multi table inheritance children share the primary key of their parent, so
    loading a child over a sibling's row leaves the stale sibling behind: the
    parent row is shared, which means nothing ever removes it, and the result
    is an object which is two things at once.

    We cannot clean this up ourselves. Deleting the stale row would take the
    shared parent row with it, and we cannot even know whether the row really
    is stale -- Django is fine with a parent having several children. So, fail
    loudly instead of silently producing a mess.
    """
    dumped = {label: {ds.object.pk for ds in objs} for label, objs in objects.items()}
    for label, pks in dumped.items():
        if label in save_as_new_models:
            # Those objects are inserted using fresh primary keys, so they
            # cannot land on top of a sibling's row.
            continue
        for sibling in _mti_siblings(apps.get_model(label)):
            sibling_label = sibling._meta.label_lower
            conflicting = sorted(
                sibling._default_manager.using(using)
                .filter(pk__in=pks)
                .exclude(pk__in=dumped.get(sibling_label, ()))
                .values_list("pk", flat=True)
            )
            if conflicting:
                raise InconsistentModelError(
                    f"The dump contains {label} objects with the primary keys"
                    f" {conflicting!r} which already exist as {sibling_label}"
                    f" objects in the database. Loading the dump would produce"
                    f" objects which are both. Remove the conflicting"
                    f" {sibling_label} objects first."
                )


def _save_objects(
    spec,
    objs,
    *,
    save_as_new_pk_map,
    save_as_new_models,
    ignore_missing_m2m_data,
    deferred_values,
    deferred_new_pks,
    deferred_m2m,
    seen_pks,
    models,
):
    for ds in objs:
        for field_name in spec.get("ignore_missing_m2m", ()):
            ignore_missing_m2m_data[ds][field_name] = ds.m2m_data.pop(field_name, [])

        random_value = _random_values()
        for field_name in spec.get("defer_values", ()):
            deferred_values.append((ds, field_name, getattr(ds.object, field_name)))
            setattr(ds.object, field_name, next(random_value))

        _do_save(
            ds,
            pk_map=save_as_new_pk_map,
            save_as_new_models=save_as_new_models,
            deferred_new_pks=deferred_new_pks,
            deferred_m2m=deferred_m2m,
        )
        seen_pks[ds.object._meta.label_lower].add(ds.object.pk)
        models.add(ds.object.__class__)


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
    deferred_m2m = []

    saved_models = set()
    for spec in data["specs"]:
        if spec["model"] in saved_models:
            # Objects are keyed by model label, not by spec, so a model
            # appearing in several specs (e.g. several ``delete_missing``
            # filters for the same model) would otherwise have all of its
            # objects saved again for each spec -- applying that spec's
            # flags (``save_as_new`` and friends) to objects which were
            # never meant to be governed by it.
            continue
        saved_models.add(spec["model"])

        objs = objects[spec["model"]]

        # Primary keys of ``save_as_new`` objects aren't known in advance, and
        # neither are the mapped filters of their dependents.
        if spec.get("delete_missing") is True and not spec.get("save_as_new") and objs:
            # Deleting conflicting rows has to happen before this model's own
            # objects are saved -- otherwise the unique constraint they hold
            # would reject the insert. Doing it here, right before that save
            # (rather than in one pass upfront for every spec), gives objects
            # of models appearing earlier in ``data["specs"]`` a chance to be
            # saved -- and therefore repointed away from the row about to be
            # deleted -- first, which narrows what an unrelated CASCADE can
            # sweep up. Models appearing later are not protected by this.
            _delete_conflicting(
                spec,
                objs,
                {ds.object.pk for ds in objs},
                progress,
            )

        _save_objects(
            spec,
            objs,
            save_as_new_pk_map=save_as_new_pk_map,
            save_as_new_models=save_as_new_models,
            ignore_missing_m2m_data=ignore_missing_m2m_data,
            deferred_values=deferred_values,
            deferred_new_pks=deferred_new_pks,
            deferred_m2m=deferred_m2m,
            seen_pks=seen_pks,
            models=models,
        )
        progress(f"Saved {len(objs)} {spec['model']} objects")

    _save_deferred_new_pks(deferred_new_pks)
    _save_deferred_m2m(deferred_m2m)

    for spec in reversed(data["specs"]):
        if not spec.get("delete_missing"):
            continue

        if isinstance(spec["delete_missing"], dict) and (
            map := spec["delete_missing"].get("map")
        ):
            queryset = _model_queryset(_map_spec(spec, map, save_as_new_pk_map))
        else:
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


@cache
def _unique_field_sets(model):
    """Field combinations which have to be unique for all rows of ``model``"""
    meta = model._meta
    return [
        *(
            (f.attname,)
            for f in meta.local_concrete_fields
            if f.unique and not f.primary_key
        ),
        *(
            tuple(meta.get_field(name).attname for name in fields)
            for fields in meta.unique_together
        ),
        *(
            tuple(meta.get_field(name).attname for name in constraint.fields)
            for constraint in meta.total_unique_constraints
        ),
    ]


def _delete_conflicting(spec, objs, seen_pks, progress):
    """
    Delete rows which conflict with objects from the dump

    Objects may be recreated on the source and therefore arrive with a new
    primary key while the row holding the same unique values still exists in
    the target database. ``delete_missing`` would get rid of the stale row, but
    only after the object from the dump has been saved -- too late, since
    unique constraints do not allow both rows to exist at the same time.

    Only rows which the spec's ``delete_missing`` would remove anyway are
    deleted here, just earlier.
    """
    field_sets = _unique_field_sets(apps.get_model(spec["model"]))
    if not field_sets:
        return

    q = Q()
    single = defaultdict(set)
    for ds in objs:
        for fields in field_sets:
            values = {field: getattr(ds.object, field) for field in fields}
            # NULLs do not conflict with anything (at least by default)
            if any(value is None for value in values.values()):
                continue
            if len(fields) == 1:
                # Avoid a needlessly long chain of ORs
                single[fields[0]].add(values[fields[0]])
            else:
                q |= Q(**values)
    for field, values in single.items():
        q |= Q(**{f"{field}__in": values})
    if not q:
        return

    deleted = _model_queryset(spec).filter(q).exclude(pk__in=seen_pks).delete()
    if deleted[0]:
        progress(f"Deleted conflicting {spec['model']} objects: {deleted}")


def _map_spec(spec, map, save_as_new_pk_map):
    spec = deepcopy(spec)
    for key, model in map:
        cls = apps.get_model(model)
        if isinstance(spec["filter"][key], (list, tuple)):
            spec["filter"][key] = [
                save_as_new_pk_map[cls][pk] for pk in spec["filter"][key]
            ]
        else:
            spec["filter"][key] = save_as_new_pk_map[cls][spec["filter"][key]]
    return spec


def _save_deferred_new_pks(deferred_new_pks):
    for ds, f_name, pk_map, fk in deferred_new_pks:
        setattr(ds.object, f_name, pk_map[fk])
        ds.save()


def _save_deferred_m2m(deferred_m2m):
    for ds, m2m_data, f_name, pk_map in deferred_m2m:
        if pks := m2m_data.get(f_name):
            getattr(ds, f_name).set([pk_map[pk] for pk in pks])


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


def _do_save(ds, *, pk_map, save_as_new_models, deferred_new_pks, deferred_m2m):
    # The primary key of a multi table inheritance child is the very field
    # pointing at its parent, so remember it before remapping foreign keys.
    old_pk = ds.object.pk

    # Map old PKs to new
    for f in ds.object._meta.get_fields():
        if f.many_to_many and f.related_model._meta.label_lower in save_as_new_models:
            # Always defer
            deferred_m2m.append(
                (ds.object, ds.m2m_data.copy(), f.name, pk_map[f.related_model])
            )

        elif (
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
        pk_related_model = ds.object._meta.pk.related_model
        if pk_related_model is None:
            ds.object.pk = None
        elif pk_related_model._meta.label_lower in save_as_new_models:
            # The primary key *is* the relation to the object this one extends,
            # and has been remapped to the new object above already. Nulling it
            # would only break the link (and the database would then hand out
            # some unrelated primary key of its own).
            pass
        else:
            raise InvalidSpecError(
                f"{ds.object._meta.label_lower!r} uses 'save_as_new', but its"
                f" primary key is the relation to"
                f" {pk_related_model._meta.label_lower!r}, which doesn't. It"
                f" cannot receive a new primary key of its own."
            )
        ds.save(force_insert=True)
        pk_map[ds.object.__class__][old_pk] = ds.object

    else:
        ds.save()
