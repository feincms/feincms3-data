import json

from django.db import models
from django.test import TransactionTestCase
from testapp.models import Child, Child1, Parent, Tag

from feincms3_data.data import (
    InvalidSpec,
    _validate_spec,
    datasets,
    dump_specs,
    load_dump,
    pk_cache,
    specs_for_app_models,
    specs_for_derived_models,
    specs_for_models,
)


def parent_child1_set():
    return [
        (p.name, [c.name for c in p.child1_set.all()])
        for p in Parent.objects.prefetch_related("child1_set")
    ]


def parent_tags():
    return {
        parent.name: {tag.name for tag in parent.tags.all()}
        for parent in Parent.objects.all()
    }


class DataTest(TransactionTestCase):
    def test_invalid_spec_missing_model(self):
        with self.assertRaises(InvalidSpec) as cm:
            _validate_spec({})
        self.assertIn("requires a 'model' key", str(cm.exception))

    def test_invalid_spec_unknown_keys(self):
        with self.assertRaises(InvalidSpec) as cm:
            list(specs_for_models([Parent], {"hello": "world"}))
        self.assertIn("contains unknown keys: {'hello'}", str(cm.exception))

    def test_datasets(self):
        self.assertEqual(
            datasets(),
            {
                "testapp": {
                    "specs": [
                        {"model": "testapp.tag"},
                        {"model": "testapp.parent"},
                        {"model": "testapp.child1"},
                        {"model": "testapp.child2"},
                    ]
                }
            },
        )

    def test_specs_for_derived_models(self):
        specs = list(specs_for_derived_models(models.Model))

        self.assertIn({"model": "auth.user"}, specs)
        self.assertIn({"model": "testapp.parent"}, specs)
        self.assertIn({"model": "testapp.child1"}, specs)
        self.assertNotIn({"model": "testapp.child"}, specs)

    def test_specs_for_app_models(self):
        specs = list(specs_for_app_models("testapp", {"delete_missing": True}))

        self.assertCountEqual(
            specs,
            [
                {"model": "testapp.parent", "delete_missing": True},
                {"model": "testapp.child1", "delete_missing": True},
                {"model": "testapp.child2", "delete_missing": True},
                {"model": "testapp.tag", "delete_missing": True},
            ],
        )

        p = Parent.objects.create()
        p.child1_set.create()
        p.child1_set.create()
        c2_1 = p.child2_set.create()

        dump = json.loads(dump_specs(specs))

        self.assertEqual(dump["version"], 1)
        self.assertCountEqual(dump["specs"], specs)
        self.assertEqual(len(dump["objects"]), 4)

        p.child2_set.create()

        load_dump(dump)

        self.assertCountEqual(p.child2_set.all(), [c2_1])

    def test_filter(self):
        p1 = Parent.objects.create()

        specs = [
            *specs_for_models(
                [Parent],
                {"filter": {"pk__in": [p1.pk]}},
            ),
            *specs_for_derived_models(
                Child,
                {"filter": {"parent__in": [p1.pk]}},
            ),
        ]

        Parent.objects.create()

        dump = json.loads(dump_specs(specs))
        self.assertEqual(len(dump["objects"]), 1)

        p1.delete()

        load_dump(dump)

        self.assertEqual(len(Parent.objects.all()), 2)

    def test_save_as_new_simple(self):
        p1 = Parent.objects.create(name="blub")

        specs = [
            *specs_for_models(
                [Parent],
                {"save_as_new": True},
            ),
        ]

        dump = json.loads(dump_specs(specs))
        load_dump(dump)

        p2 = Parent.objects.latest("id")

        self.assertNotEqual(p1.pk, p2.pk)
        self.assertEqual(p1.name, p2.name)

    def test_save_as_new_partial_graph(self):
        p1 = Parent.objects.create(name="blub-1")
        p1.child1_set.create(name="blub-1-1")

        p2 = Parent.objects.create(name="blub-2")
        p2.child1_set.create(name="blub-2-1")

        self.assertEqual(
            parent_child1_set(),
            [("blub-1", ["blub-1-1"]), ("blub-2", ["blub-2-1"])],
        )

        specs = [
            *specs_for_models(
                [Parent],
                {"filter": {"pk__in": [p1.pk]}},
            ),
            *specs_for_derived_models(
                Child,
                {
                    "filter": {"parent__in": [p1.pk]},
                    "save_as_new": True,
                    "delete_missing": True,
                },
            ),
        ]

        dump = json.loads(dump_specs(specs))
        load_dump(dump)

        self.assertEqual(
            parent_child1_set(),
            [("blub-1", ["blub-1-1", "blub-1-1"]), ("blub-2", ["blub-2-1"])],
        )

    def test_save_as_new_full_graph(self):
        Parent.objects.create(name="other")

        p1 = Parent.objects.create(name="blub-1")
        p1.child1_set.create(name="blub-1-1")

        self.assertEqual(
            parent_child1_set(),
            [("other", []), ("blub-1", ["blub-1-1"])],
        )

        specs = [
            *specs_for_models(
                [Parent],
                {
                    "filter": {"pk__in": [p1.pk]},
                    "save_as_new": True,
                },
            ),
            *specs_for_derived_models(
                Child,
                {
                    "filter": {"parent__in": [p1.pk]},
                    "save_as_new": True,
                    "delete_missing": True,  # Remove old child items
                },
            ),
        ]

        dump = json.loads(dump_specs(specs))
        # from pprint import pprint; print(); pprint(dump)
        load_dump(dump)

        self.assertEqual(
            parent_child1_set(),
            [
                ("other", []),
                ("blub-1", ["blub-1-1"]),
                ("blub-1", ["blub-1-1"]),
            ],
        )

        p1_new = Parent.objects.latest("pk")
        self.assertNotEqual(p1.pk, p1_new.pk)

    def test_save_as_new_parent_only(self):
        p1 = Parent.objects.create(name="p1")
        p1.child1_set.create(name="c1")

        specs = [
            *specs_for_models(
                [Parent],
                {"save_as_new": True},
            ),
            *specs_for_models(
                [Child1],
                {"save_as_new": False},
            ),
        ]

        dump = json.loads(dump_specs(specs))
        p1.name = "p1-old"
        p1.save()
        load_dump(dump)

        # c1 now hangs off second
        self.assertEqual(
            parent_child1_set(),
            [("p1-old", []), ("p1", ["c1"])],
        )

    def test_m2m_deletion_on_defining_side(self):
        t1 = Tag.objects.create(name="t1")
        t2 = Tag.objects.create(name="t2")
        t3 = Tag.objects.create(name="t3")

        p1 = Parent.objects.create(name="p1")
        p1.tags.set([t1, t2])
        p2 = Parent.objects.create(name="p2")
        p2.tags.set([t1, t2])

        specs = [
            *specs_for_models([Parent], {"delete_missing": True}),
        ]
        dump = json.loads(dump_specs(specs))

        p1.delete()
        p2.tags.add(t3)

        load_dump(dump)

        self.assertEqual(
            parent_tags(),
            {"p1": {"t1", "t2"}, "p2": {"t1", "t2"}},
        )

    def test_m2m_deletion_on_targeted_side(self):
        t1 = Tag.objects.create(name="t1")
        t2 = Tag.objects.create(name="t2")
        t3 = Tag.objects.create(name="t3")

        p1 = Parent.objects.create(name="p1")
        p1.tags.set([t1, t2])

        Parent.objects.create(name="p2")

        specs = [
            *specs_for_models([Parent], {"ignore_missing_m2m": ["tags"]}),
        ]
        dump = json.loads(dump_specs(specs))

        t2.delete()
        p1.tags.add(t3)

        self.assertEqual(
            parent_tags(),
            {"p1": {"t1", "t3"}, "p2": set()},
        )

        load_dump(dump)

        # After restore
        # - t3 has been removed again
        # - t2 isn't referenced because it has been deleted, but no foreign key
        #   error happens

        self.assertEqual(
            parent_tags(),
            {"p1": {"t1"}, "p2": set()},
        )

        Tag.objects.all().delete()

        self.assertEqual(
            parent_tags(),
            {"p1": set(), "p2": set()},
        )

    def test_pk_cache(self):
        pks = pk_cache()
        with self.assertNumQueries(1):
            self.assertEqual(pks(Parent), set())
        with self.assertNumQueries(0):
            self.assertEqual(pks(Parent), set())
        pks = pk_cache()
        with self.assertNumQueries(1):
            self.assertEqual(pks(Parent), set())

    def test_mappers(self):
        specs = list(specs_for_app_models("testapp"))

        self.assertCountEqual(
            specs,
            [
                {"model": "testapp.parent"},
                {"model": "testapp.child1"},
                {"model": "testapp.child2"},
                {"model": "testapp.tag"},
            ],
        )

        p = Parent.objects.create()
        p.child1_set.create()

        def parent_mapper(obj):
            obj["fields"]["name"] += "-hello"
            return obj

        dump = json.loads(
            dump_specs(
                specs,
                mappers={
                    "testapp.parent": parent_mapper,
                },
            )
        )

        self.assertEqual(
            dump["objects"][0]["fields"],
            {"name": "name-hello", "tags": []},
        )
        self.assertEqual(
            dump["objects"][1]["fields"],
            {"name": "name", "parent": p.pk},
        )

        # print(dump)

    def test_invalid_dumps(self):
        with self.assertRaises(AssertionError):
            load_dump({"version": -1})

        with self.assertRaises(InvalidSpec):
            load_dump(
                {
                    "version": 1,
                    "specs": [{"model": "testapp.parent", "hello": "world"}],
                }
            )

        with self.assertRaises(KeyError):
            load_dump(
                {
                    "version": 1,
                    "specs": [{"model": "testapp.parent"}],
                    # "objects": ...
                }
            )

    def test_multiple_specs_same_model(self):
        p1 = Parent.objects.create()
        p2 = Parent.objects.create()

        # Very artificial. But it may be important that this works.
        specs = [
            *specs_for_models([Parent], {"filter": {"pk__lte": p1.pk}}),
            *specs_for_models([Parent], {"filter": {"pk__lte": p2.pk}}),
        ]

        data = json.loads(dump_specs(specs))
        self.assertEqual(len(data["objects"]), 3)

    def test_nullable_fk_save_as_new(self):
        specs = [
            *specs_for_models([Tag], {"save_as_new": True}),
        ]

        Tag.objects.create(name="test")

        data = json.loads(dump_specs(specs))
        load_dump(data)

        self.assertEqual(len(Tag.objects.all()), 2)
