import json

from django import test
from django.db import models
from testapp.models import Child, Parent

from feincms3_data.data import (
    dump_specs,
    load_dump,
    specs,
    specs_for_app_models,
    specs_for_derived_models,
    specs_for_models,
)


class DataTest(test.TestCase):
    def test_specs(self):
        self.assertCountEqual(
            specs(),
            [
                {"model": "testapp.parent"},
                {"model": "testapp.child1"},
                {"model": "testapp.child2"},
            ],
        )

    def test_specs_for_derived_models(self):
        specs = list(specs_for_derived_models(models.Model))

        self.assertIn({"model": "auth.user"}, specs)
        self.assertIn({"model": "testapp.parent"}, specs)
        self.assertIn({"model": "testapp.child1"}, specs)
        self.assertNotIn({"model": "testapp.child"}, specs)

    def test_specs_for_app_models(self):
        specs = list(specs_for_app_models("testapp"))

        self.assertCountEqual(
            specs,
            [
                {"model": "testapp.parent"},
                {"model": "testapp.child1"},
                {"model": "testapp.child2"},
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

    def test_force_insert_simple(self):
        p1 = Parent.objects.create(name="blub")

        specs = [
            *specs_for_models(
                [Parent],
                {"force_insert": True},
            ),
        ]

        dump = json.loads(dump_specs(specs))
        load_dump(dump)

        p2 = Parent.objects.latest("id")

        self.assertNotEqual(p1.pk, p2.pk)
        self.assertEqual(p1.name, p2.name)

    def test_force_insert_partial_graph(self):
        p1 = Parent.objects.create(name="blub-1")
        c1_1 = p1.child1_set.create(name="blub-1-1")

        p2 = Parent.objects.create(name="blub-2")
        p2.child1_set.create(name="blub-2-1")

        specs = [
            *specs_for_models(
                [Parent],
                {"filter": {"pk__in": [p1.pk]}},
            ),
            *specs_for_derived_models(
                Child,
                {"filter": {"parent__in": [p1.pk]}, "force_insert": True},
            ),
        ]

        dump = json.loads(dump_specs(specs))
        load_dump(dump)

        data = [
            (p.name, [c.name for c in p.child1_set.all()])
            for p in Parent.objects.order_by("id").prefetch_related("child1_set")
        ]
        self.assertEqual(data, [("blub-1", ["blub-1-1"]), ("blub-2", ["blub-2-1"])])

        self.assertNotEqual(c1_1.pk, p1.child1_set.get().pk)

    def test_force_insert_full_graph(self):
        Parent.objects.create(name="other")

        p1 = Parent.objects.create(name="blub-1")
        p1.child1_set.create(name="blub-1-1")

        specs = [
            *specs_for_models(
                [Parent],
                {"filter": {"pk__in": [p1.pk]}, "force_insert": True},
            ),
            *specs_for_derived_models(
                Child,
                {"filter": {"parent__in": [p1.pk]}, "force_insert": True},
            ),
        ]

        dump = json.loads(dump_specs(specs))
        load_dump(dump)

        data = [
            (p.name, [c.name for c in p.child1_set.all()])
            for p in Parent.objects.order_by("id").prefetch_related("child1_set")
        ]
        self.assertEqual(data, [("other", []), ("blub-1", ["blub-1-1"])])

        p1_new = Parent.objects.latest("pk")
        self.assertNotEqual(p1.pk, p1_new.pk)
