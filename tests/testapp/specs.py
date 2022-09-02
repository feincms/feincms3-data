from feincms3_data.data import specs_for_app_models


def datasets():
    return {
        "testapp": {
            "specs": [
                *specs_for_app_models("testapp"),
            ],
        },
    }
