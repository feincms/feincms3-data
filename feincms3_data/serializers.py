from django.core.serializers import json


def identity(data):
    return data


class JSONSerializer(json.Serializer):
    def __init__(self, *, mappers):
        self._mappers = mappers

    def get_dump_object(self, obj):
        data = super().get_dump_object(obj)
        return self._mappers.get(data["model"], identity)(data)
