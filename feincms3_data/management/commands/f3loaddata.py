import json

from django.core.management.base import BaseCommand

from feincms3_data.data import load_dump, silence


class Command(BaseCommand):
    help = "Loads the dumps into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ignorenonexistent",
            action="store_true",
            dest="ignorenonexistent",
            help=(
                "Ignore entries in the serialized data for fields that do not"
                " currently exist on the model."
            ),
        )
        parser.add_argument("args", metavar="dump", nargs="+", help="Dumps.")

    def handle(self, *dumps, **options):
        for dump in dumps:
            with open(dump, encoding="utf-8") as f:
                data = json.load(f)
            load_dump(
                data,
                progress=self.stderr.write if options["verbosity"] >= 2 else silence,
                ignorenonexistent=options["ignorenonexistent"],
            )
