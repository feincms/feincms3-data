from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from feincms3_data.data import dump_specs


SPECS = import_string(settings.FEINCMS3_DATA_SPECS)()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "args",
            nargs="*",
            help=f"Model specs which should be dumped ({', '.join(sorted(SPECS))}).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all_specs",
            help="Dump all model specs.",
        )

    def handle(self, *args, **options):
        if options["all_specs"]:
            args = SPECS.keys()
        specs = []
        for arg in args:
            try:
                model, sep, args = arg.partition(":")
                specs.extend(SPECS[model](args))
            except KeyError:
                raise CommandError(f'Invalid spec "{arg}"')
        self.stdout.write(dump_specs(specs))
