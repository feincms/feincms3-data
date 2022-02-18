from testapp import models

from feincms3_data.data import specs_for_app_models


def specs():
    return [
        *specs_for_app_models("testapp"),
    ]
