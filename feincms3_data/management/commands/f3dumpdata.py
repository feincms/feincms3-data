from django.core.management.base import BaseCommand, CommandError

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
        try:
            ds = DATASETS[dataset]
        except KeyError:
            raise CommandError(
                f"Invalid dataset {dataset}; should be one of {', '.join(DATASETS)}"
            ) from None
        self.stdout.write(dump_specs(ds["specs"](args), mappers=ds.get("mappers")))
