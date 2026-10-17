from mms_common.errors import Forbidden, NotFound, VersionConflict


def test_problem_body():
    body = NotFound("No such station").problem(request_id="r1")
    assert body["status"] == 404 and body["code"] == "not_found" and body["request_id"] == "r1"


def test_out_of_scope_is_404_not_403():
    assert NotFound.status == 404 and Forbidden.status == 403


def test_version_conflict_is_a_409():
    assert VersionConflict().status == 409
