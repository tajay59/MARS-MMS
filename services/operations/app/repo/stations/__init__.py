"""Stations module collections (TRD §5.2, BSD "operations — stations module").

Every read for a user goes through `mms_common.auth.scoped` with the collection's org field
(rule 3): `owner_org_id` for stations, `current_org_id` for sensor units, `org_id` for
installations and calibrations. Sensor models carry no org: clients read them only through
the units installed at their stations.
"""
