from django.core.serializers import json
from django.db import models


def identity(data):
    return data


class JSONSerializer(json.Serializer):
    def __init__(self, *, mappers):
        self._mappers = mappers

    def get_dump_object(self, obj):
        data = super().get_dump_object(obj)
        return self._mappers.get(data["model"], identity)(data)


class JSONEncoder(json.DjangoJSONEncoder):
    def default(self, o):
        if issubclass(o, models.Model):
            return o._meta.label_lower
        return super().default(o)
