# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

import ipylab.log


def test_log(app: ipylab.App):
    records = []

    def on_record(record):
        records.append(record)

    assert app.logging_handler
    app.logging_handler.register_callback(on_record)
    app.log_level = ipylab.log.LogLevel.ERROR

    # With objects via IpylabLoggerAdapter
    obj = object()
    app.log.error("An error", obj=obj)
    assert len(records) == 1
    record = records[0]
    assert record.owner() is app, "Via weakref"
    assert record.obj is obj, "Direct ref"

    # No objects direct log
    app.log.logger.error("No objects")
    assert len(records) == 2
    record = records[1]
    assert not hasattr(record, "owner"), "logging directly won't attach owner"
    assert not hasattr(record, "obj"), "logging directly won't attach obj"


def test_log_level_sync(app: ipylab.App):
    for level in ipylab.log.LogLevel:
        app.log_level = level
        assert app.log.getEffectiveLevel() == level
