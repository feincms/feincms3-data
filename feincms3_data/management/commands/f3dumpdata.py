from django.core.management.base import BaseCommand

from feincms3_data.data import datasets, dump_specs


DATASETS = datasets()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "dataset",
            help=f"Model dataset which should be dumped. {', '.join(DATASETS)}",
        )

    def handle(self, *args, **options):
        dataset, sep, args = options["dataset"].partition(":")
        ds = DATASETS[dataset]
        self.stdout.write(dump_specs(ds["specs"](args), mappers=ds.get("mappers")))
