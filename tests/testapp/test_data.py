import json

from django import test
from testapp.models import Child, Parent

from feincms3_data.data import (
    dump_specs,
    load_dump,
    specs_for_app_models,
    specs_for_derived_models,
    specs_for_models,
)


class DataTest(test.TestCase):
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
